"""Manifestos: upload -> OCR assíncrono -> conferência humana -> geração de rota.

O OCR nunca grava a rota direto: gera pré-rota com nível de confiança e
exige validação (status AGUARDANDO_CONFERENCIA -> CONFERIDO -> ROTA_GERADA).
"""
import json
import uuid
from datetime import date, time
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import Role, require_feature, require_roles, require_same_branch
from app.db.models import Branch, DockSession, Manifest, OcrResult, Route, RouteStop, User
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services import storage
from app.services.audit import log
from app.services.events import EventType, record_event
from app.workers.celery_app import enqueue_ocr

router = APIRouter(prefix="/manifests", tags=["manifests"], dependencies=[Depends(require_feature("feature_ocr"))])

ALLOWED_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/jpg", "image/tiff"}
EXTENSION_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


class ManifestOut(BaseModel):
    id: int
    branch_id: int
    route_id: int | None
    original_filename: str
    status: str
    ocr_confidence: float | None
    error_message: str | None

    class Config:
        from_attributes = True


class ConferenceUpdate(BaseModel):
    """Dados conferidos/corrigidos pelo operador antes de gerar a rota."""
    extracted_json: dict


class ManifestSuggestions(BaseModel):
    codigo_ut: list[str] = []
    origins: list[str] = []
    addresses: list[str] = []
    customers: list[str] = []
    cities: list[str] = []
    orders: list[str] = []


def _add_suggestion(target: set[str], value) -> None:
    text = str(value or "").strip()
    if text:
        target.add(text)


def _parse_date(value, field_name: str) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    value = str(value).strip()
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    try:
        day, month, year = value.replace("-", "/").split("/")
        if len(year) == 4:
            return date(int(year), int(month), int(day))
    except ValueError:
        pass
    raise HTTPException(status_code=400, detail=f"Data inválida em {field_name}: {value}. Use AAAA-MM-DD ou DD/MM/AAAA.")


def _parse_time(value, field_name: str) -> time | None:
    if value in (None, ""):
        return None
    if isinstance(value, time):
        return value
    value = str(value).strip()
    try:
        return time.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Hora inválida em {field_name}: {value}. Use HH:MM.")


def _resolve_branch(db: Session, user: User, branch_id: int | None = None) -> Branch:
    """Resolve a filial operacional sem depender do frontend.

    Para o Brasil usamos uma filial única por padrão. Se o banco veio de um
    scaffold antigo sem branches, criamos/reativamos a filial aqui para evitar
    erro de FK no upload.
    """
    target_id = branch_id or user.branch_id
    branch = db.get(Branch, target_id) if target_id else None
    if branch is None:
        branch = db.scalar(select(Branch).where(Branch.country == "BR"))
    if branch is None:
        branch = Branch(name="Admmendes Distribuição - Brasil (Santo André)", country="BR", locale="pt-BR")
        db.add(branch)
        db.flush()
    if user.branch_id is None or db.get(Branch, user.branch_id) is None:
        user.branch_id = branch.id
    return branch


def _resolve_content_type(file: UploadFile) -> str:
    content_type = file.content_type or "application/octet-stream"
    if content_type in ALLOWED_TYPES:
        return content_type
    if content_type == "application/octet-stream":
        guessed = EXTENSION_TYPES.get(Path(file.filename or "").suffix.lower())
        if guessed:
            return guessed
    raise HTTPException(status_code=415, detail=f"Tipo não suportado: {content_type}")


@router.get("", response_model=list[ManifestOut])
def list_manifests(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(Manifest)
    if user.branch_id:
        stmt = stmt.where(Manifest.branch_id == user.branch_id)
    return db.scalars(stmt.order_by(Manifest.created_at.desc())).all()


@router.get("/suggestions", response_model=ManifestSuggestions)
def manifest_suggestions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Sugestões para campos digitados manualmente a partir de manifestos já conferidos."""
    stmt = select(OcrResult.extracted_json).join(Manifest, Manifest.id == OcrResult.manifest_id)
    if user.branch_id:
        stmt = stmt.where(Manifest.branch_id == user.branch_id)
    stmt = stmt.where(OcrResult.extracted_json.is_not(None)).order_by(Manifest.created_at.desc()).limit(300)

    codigo_ut: set[str] = set()
    origins: set[str] = set()
    addresses: set[str] = set()
    customers: set[str] = set()
    cities: set[str] = set()
    orders: set[str] = set()
    for raw in db.scalars(stmt).all():
        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError:
            continue
        _add_suggestion(codigo_ut, payload.get("codigo_ut"))
        _add_suggestion(origins, payload.get("origem"))
        _add_suggestion(addresses, payload.get("morada_origem") or payload.get("endereco_origem"))
        for dest in payload.get("destinos") or []:
            if not isinstance(dest, dict):
                continue
            _add_suggestion(customers, dest.get("nome"))
            _add_suggestion(addresses, dest.get("morada") or dest.get("endereco"))
            _add_suggestion(cities, dest.get("cidade"))
            _add_suggestion(orders, dest.get("pedido") or dest.get("order_number"))

    return ManifestSuggestions(
        codigo_ut=sorted(codigo_ut)[:80],
        origins=sorted(origins)[:80],
        addresses=sorted(addresses)[:160],
        customers=sorted(customers)[:160],
        cities=sorted(cities)[:80],
        orders=sorted(orders)[:120],
    )


@router.post("/upload", response_model=ManifestOut,
             dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL, Role.OPERADOR_LOGISTICO, Role.GESTOR_BRASIL))])
async def upload_manifest(
    branch_id: int | None = None,
    route_id: int | None = None,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    branch = _resolve_branch(db, user, branch_id)
    require_same_branch(user, branch.id)
    route = db.get(Route, route_id) if route_id else None
    if route_id and route is None:
        raise HTTPException(status_code=404, detail="Rota não encontrada.")
    if route is not None:
        require_same_branch(user, route.branch_id)
        branch = db.get(Branch, route.branch_id) or branch
    content_type = _resolve_content_type(file)
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Arquivo acima de {settings.max_upload_mb} MB.")

    storage.ensure_buckets()
    key = f"{branch.id}/{uuid.uuid4().hex}-{file.filename}"
    storage.put_object(settings.minio_bucket_manifests, key, data, content_type)

    manifest = Manifest(
        branch_id=branch.id,
        route_id=route.id if route else None,
        original_filename=file.filename,
        storage_key=key,
        status="RECEBIDO",
        uploaded_by=user.id,
    )
    db.add(manifest)
    db.flush()
    log(db, user_id=user.id, action="upload", entity="manifest", entity_id=manifest.id)
    db.commit()

    # Dispara OCR assíncrono (fila "ocr" -> serviço ocr-worker)
    enqueue_ocr(manifest.id)
    return manifest


@router.get("/{manifest_id}")
def get_manifest(manifest_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    manifest = db.get(Manifest, manifest_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Manifesto não encontrado.")
    require_same_branch(user, manifest.branch_id)
    ocr = manifest.ocr_result
    return {
        "manifest": ManifestOut.model_validate(manifest).model_dump(),
        "file_url": storage.get_presigned_url(settings.minio_bucket_manifests, manifest.storage_key),
        "ocr": {
            "engine": ocr.engine if ocr else None,
            "confidence": ocr.confidence if ocr else None,
            "needs_review": ocr.needs_review if ocr else None,
            "extracted": json.loads(ocr.extracted_json) if (ocr and ocr.extracted_json) else None,
        } if ocr else None,
    }


@router.post("/{manifest_id}/confirm", response_model=ManifestOut,
             dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL, Role.OPERADOR_LOGISTICO, Role.GESTOR_BRASIL))])
def confirm_conference(manifest_id: int, data: ConferenceUpdate,
                       db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Salva os dados conferidos e marca CONFERIDO."""
    manifest = db.get(Manifest, manifest_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Manifesto não encontrado.")
    require_same_branch(user, manifest.branch_id)
    ocr = manifest.ocr_result or OcrResult(manifest_id=manifest.id, engine=settings.ocr_engine)
    ocr.extracted_json = json.dumps(data.extracted_json, ensure_ascii=False)
    ocr.needs_review = False
    if manifest.ocr_result is None:
        db.add(ocr)
    manifest.status = "CONFERIDO"
    manifest.error_message = None
    log(db, user_id=user.id, action="confirm", entity="manifest", entity_id=manifest.id)
    db.commit()
    db.refresh(manifest)
    return manifest


@router.post("/{manifest_id}/generate-route",
             dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL, Role.OPERADOR_LOGISTICO, Role.GESTOR_BRASIL))])
def generate_route(manifest_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Gera ou atualiza a rota definitiva a partir do manifesto conferido."""
    manifest = db.get(Manifest, manifest_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Manifesto não encontrado.")
    require_same_branch(user, manifest.branch_id)
    if manifest.status != "CONFERIDO":
        raise HTTPException(status_code=409, detail="Manifesto precisa estar CONFERIDO.")
    if manifest.ocr_result is None or not manifest.ocr_result.extracted_json:
        raise HTTPException(status_code=400, detail="Sem dados extraídos.")

    payload = json.loads(manifest.ocr_result.extracted_json)
    route_date = _parse_date(payload.get("data_carga"), "data_carga")
    if route_date is None:
        raise HTTPException(status_code=400, detail="Preencha data_carga antes de gerar a rota.")
    if not str(payload.get("codigo_ut") or "").strip():
        raise HTTPException(status_code=400, detail="Preencha codigo_ut antes de gerar a rota.")

    route = db.get(Route, manifest.route_id) if manifest.route_id else None
    if route is not None:
        require_same_branch(user, route.branch_id)
        if route.status == "cancelada":
            raise HTTPException(status_code=409, detail="Rota cancelada não pode receber manifesto.")
        # Rota criada manualmente: atualiza com os dados do manifesto, mas
        # preserva a data da carga e os horários de doca/CD já registrados.
        route.codigo_ut = str(payload.get("codigo_ut", "")).strip()[:40]
        route.origin_name = (payload.get("origem") or None) and str(payload.get("origem"))[:160]
        route.origin_address = (payload.get("origem_morada") or None) and str(payload.get("origem_morada"))[:255]
        route.toll_outbound = payload.get("portagem_ida")
        route.toll_return = payload.get("portagem_volta")
        route.km_total_informed = payload.get("km_total")
        route.stops.clear()
        if route.dock_session is None:
            route.dock_session = DockSession()
    else:
        route = Route(
            branch_id=manifest.branch_id,
            codigo_ut=str(payload.get("codigo_ut", "")).strip()[:40],
            route_date=route_date,
            origin_name=(payload.get("origem") or None) and str(payload.get("origem"))[:160],
            origin_address=(payload.get("origem_morada") or None) and str(payload.get("origem_morada"))[:255],
            toll_outbound=payload.get("portagem_ida"),
            toll_return=payload.get("portagem_volta"),
            km_total_informed=payload.get("km_total"),
            created_by=user.id,
            status="planejada",
        )
        route.dock_session = DockSession()
    for i, dest in enumerate(payload.get("destinos", []), start=1):
        route.stops.append(RouteStop(
            sequence=i,
            customer_name=dest.get("nome", "—"),
            customer_address=dest.get("morada"),
            city=dest.get("cidade"),
            planned_date=_parse_date(dest.get("data_limite"), f"destinos[{i}].data_limite"),
            planned_time=_parse_time(dest.get("hora_limite"), f"destinos[{i}].hora_limite"),
            temperature=dest.get("temperatura"),
            weight_kg=dest.get("peso_kg"),
            pallets=dest.get("paletes") or dest.get("pallets") or dest.get("pales"),
            order_number=dest.get("pedido"),
        ))
    db.add(route)
    db.flush()
    manifest.route_id = route.id
    manifest.status = "ROTA_GERADA"
    record_event(db, route_id=route.id, event_type=EventType.MANIFEST_VALIDATED, user_id=user.id)
    log(db, user_id=user.id, action="generate_route", entity="manifest", entity_id=manifest.id,
        detail=f"route_id={route.id}")
    db.commit()
    return {"route_id": route.id, "stops": len(route.stops)}

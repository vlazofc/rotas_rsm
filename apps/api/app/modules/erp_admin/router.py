"""Backoffice ERP: conteúdo próprio, almoxarifado e visão de ocorrências."""
from datetime import date, datetime, timezone
import hashlib
import io
import json
import re
import unicodedata
import uuid
from pathlib import Path
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.permissions import FINANCE_ACCOUNTS_MANAGE, FINANCE_VIEW, ROLE_EQUIVALENTS, Role, require_branch_access, require_permission, require_roles, scope_by_branch
from app.db.models import Attachment, Branch, ContentItem, Driver, DriverSettings, DriverStatementAdjustment, DriverStatementPeriod, Expense, FinancialAccount, FinancialCategory, MaintenanceOrder, OccurrenceCategory, Part, PurchaseItem, PurchaseTicket, Revenue, Route, RouteOccurrence, RouteOccurrenceEvent, RouteStop, StockMovement, Supplier, User, Vehicle, WorkflowTask, WorkflowTaskEvent
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services.audit import log
from app.services.events import notify_operational_audience
from app.services import storage
from app.core.config import settings

router = APIRouter(prefix="/erp", tags=["erp"])
_MANAGER = require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL)
_OCCURRENCE_REPORTER = require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL, Role.TORRE_CONTROLE, Role.MOTORISTA)
_OCCURRENCE_ACCESS = require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL, Role.TORRE_CONTROLE, Role.OPERADOR_LOGISTICO, Role.MOTORISTA)
_FINANCE = require_permission(FINANCE_VIEW, Role.GESTOR_BRASIL, Role.GESTOR_FINANCEIRO)
_FINANCE_MANAGE = require_permission(FINANCE_ACCOUNTS_MANAGE, Role.GESTOR_BRASIL, Role.GESTOR_FINANCEIRO)
_PURCHASE_STAFF = require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL, Role.GESTOR_FINANCEIRO, Role.OPERADOR_LOGISTICO)


DEFAULT_OCCURRENCE_CATEGORIES = (
    ("avaria", "Avaria"), ("acidente", "Acidente"), ("atraso", "Atraso"),
    ("seguranca", "Segurança"), ("outros", "Outros"),
)

class ContentIn(BaseModel):
    branch_id: int | None = None
    title: str = Field(min_length=2, max_length=180)
    body: str | None = None
    kind: str = "comunicado"
    published: bool = False

@router.get("/content")
def list_content(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(ContentItem).order_by(ContentItem.created_at.desc())
    if user.role != Role.ADMIN_GLOBAL.value:
        stmt = stmt.where(ContentItem.tenant_id == user.tenant_id, (ContentItem.branch_id.is_(None)) | (ContentItem.branch_id == (user.branch_id if user.branch_id is not None else -1)))
        if user.role not in {Role.GESTOR_BRASIL.value}: stmt = stmt.where(ContentItem.published.is_(True))
    return db.scalars(stmt).all()

@router.post("/content", dependencies=[Depends(_MANAGER)])
def create_content(data: ContentIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    branch_id = data.branch_id or user.branch_id
    if branch_id is None: raise HTTPException(400, "Informe a filial.")
    require_branch_access(db, user, branch_id)
    row = ContentItem(**data.model_dump(exclude={"branch_id"}), branch_id=branch_id, created_by=user.id)
    db.add(row); db.flush(); log(db, user_id=user.id, action="create", entity="content_item", entity_id=row.id); db.commit(); db.refresh(row)
    return row

@router.put("/content/{item_id}", dependencies=[Depends(_MANAGER)])
def update_content(item_id: int, data: ContentIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.get(ContentItem, item_id)
    if row is None: raise HTTPException(404, "Conteúdo não encontrado.")
    require_branch_access(db, user, row.branch_id or data.branch_id or 0)
    for key, value in data.model_dump(exclude={"branch_id"}).items(): setattr(row, key, value)
    db.commit(); db.refresh(row); return row

class PartIn(BaseModel):
    branch_id: int
    sku: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=2, max_length=160)
    unit: str = "un"
    minimum_quantity: float = Field(default=0, ge=0)
    average_cost: float | None = Field(default=None, ge=0)

class PartUpdate(BaseModel):
    sku: str | None = Field(default=None, min_length=1, max_length=60)
    name: str | None = Field(default=None, min_length=2, max_length=160)
    unit: str | None = Field(default=None, min_length=1, max_length=20)
    minimum_quantity: float | None = Field(default=None, ge=0)
    average_cost: float | None = Field(default=None, ge=0)

class MovementIn(BaseModel):
    kind: str
    quantity: float = Field(gt=0)
    unit_cost: float | None = Field(default=None, ge=0)
    reference: str | None = None

@router.get("/parts")
def parts(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(Part).where(Part.active.is_(True)).order_by(Part.name)
    stmt = scope_by_branch(stmt, Part.branch_id, user, db)
    return db.scalars(stmt).all()

@router.post("/parts", dependencies=[Depends(_MANAGER)])
def create_part(data: PartIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_branch_access(db, user, data.branch_id)
    if db.scalar(select(Part).where(Part.tenant_id == user.tenant_id, Part.sku == data.sku)):
        raise HTTPException(409, "SKU já cadastrado.")
    row = Part(**data.model_dump()); db.add(row); db.commit(); db.refresh(row); return row

@router.put("/parts/{part_id}", dependencies=[Depends(_MANAGER)])
def update_part(part_id: int, data: PartUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.get(Part, part_id)
    if row is None or not row.active: raise HTTPException(404, "Peça não encontrada.")
    require_branch_access(db, user, row.branch_id)
    updates = data.model_dump(exclude_unset=True)
    if "sku" in updates and updates["sku"] != row.sku and db.scalar(select(Part).where(Part.tenant_id == row.tenant_id, Part.sku == updates["sku"], Part.id != row.id)):
        raise HTTPException(409, "SKU já cadastrado.")
    for key, value in updates.items(): setattr(row, key, value)
    log(db, user_id=user.id, action="update", entity="part", entity_id=row.id)
    db.commit(); db.refresh(row); return row

@router.delete("/parts/{part_id}", dependencies=[Depends(_MANAGER)])
def delete_part(part_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.get(Part, part_id)
    if row is None or not row.active: raise HTTPException(404, "Peça não encontrada.")
    require_branch_access(db, user, row.branch_id)
    row.active = False
    log(db, user_id=user.id, action="delete", entity="part", entity_id=row.id)
    db.commit(); return {"deleted": part_id}

@router.post("/parts/{part_id}/movements", dependencies=[Depends(_MANAGER)])
def move_stock(part_id: int, data: MovementIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    part = db.get(Part, part_id)
    if part is None: raise HTTPException(404, "Peça não encontrada.")
    require_branch_access(db, user, part.branch_id)
    if data.kind not in {"entrada", "saida", "ajuste"}: raise HTTPException(400, "Tipo de movimento inválido.")
    delta = data.quantity if data.kind in {"entrada", "ajuste"} else -data.quantity
    if part.quantity + delta < 0: raise HTTPException(409, "Estoque insuficiente.")
    part.quantity += delta
    if data.kind == "entrada" and data.unit_cost is not None: part.average_cost = Decimal(str(data.unit_cost))
    row = StockMovement(part_id=part.id, kind=data.kind, quantity=data.quantity, unit_cost=data.unit_cost, reference=data.reference, user_id=user.id)
    db.add(row); db.commit(); return {"movement_id": row.id, "quantity": part.quantity, "low_stock": part.quantity <= part.minimum_quantity}

@router.get("/occurrences")
def occurrences(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = (select(RouteOccurrence, Route.codigo_ut, Vehicle.plate, Driver.name)
            .join(Route, Route.id == RouteOccurrence.route_id).outerjoin(Vehicle, Vehicle.id == Route.vehicle_id)
            .outerjoin(Driver, Driver.id == RouteOccurrence.driver_id).order_by(RouteOccurrence.created_at.desc()))
    if user.role != Role.MOTORISTA.value:
        stmt = scope_by_branch(stmt, RouteOccurrence.branch_id, user, db)
    if user.role == Role.MOTORISTA.value: stmt = stmt.where(RouteOccurrence.reported_by == user.id)
    rows = db.execute(stmt).all()
    assignees = {item.id: item.name for item in db.scalars(select(User).where(User.id.in_([o.assigned_to_id for o, *_ in rows if o.assigned_to_id]))).all()}
    evidence = {item.id: item for item in db.scalars(select(Attachment).where(Attachment.id.in_([o.evidence_attachment_id for o, *_ in rows if o.evidence_attachment_id]))).all()}
    return [{"id": o.id, "route_id": o.route_id, "codigo_ut": code, "plate": plate, "driver": driver,
             "category": o.category, "severity": o.severity, "description": o.description, "status": o.status,
             "latitude": o.latitude, "longitude": o.longitude, "resolution": o.resolution,
             "assigned_to_id": o.assigned_to_id, "assigned_to": assignees.get(o.assigned_to_id),
             "evidence_url": storage.get_presigned_url(evidence[o.evidence_attachment_id].bucket, evidence[o.evidence_attachment_id].storage_key) if o.evidence_attachment_id in evidence else None,
             "treatment_started_at": o.treatment_started_at, "resolved_at": o.resolved_at,
             "finalized_at": o.finalized_at, "created_at": o.created_at}
            for o, code, plate, driver in rows]


@router.post("/occurrences/{occurrence_id}/evidence", dependencies=[Depends(_OCCURRENCE_ACCESS)])
async def upload_occurrence_evidence(occurrence_id: int, evidence: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.get(RouteOccurrence, occurrence_id)
    if row is None: raise HTTPException(404, "Ocorrência não encontrada.")
    require_branch_access(db, user, row.branch_id)
    if not _can_manage_occurrence(user, row): raise HTTPException(403, "Sem permissão para evidenciar esta ocorrência.")
    content_type = evidence.content_type or "application/octet-stream"
    if content_type not in {"application/pdf", "image/png", "image/jpeg", "image/jpg", "image/webp"}:
        raise HTTPException(415, "A evidência deve ser uma foto ou PDF.")
    content = await evidence.read()
    if not content: raise HTTPException(400, "Arquivo vazio.")
    if len(content) > settings.max_upload_mb * 1024 * 1024: raise HTTPException(413, f"Arquivo acima de {settings.max_upload_mb} MB.")
    storage.ensure_buckets()
    filename = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(evidence.filename or "evidencia").name)[:120]
    key = f"ocorrencias/{row.branch_id}/{row.route_id}/{row.id}/{uuid.uuid4().hex}-{filename}"
    storage.put_object(settings.minio_bucket_proofs, key, content, content_type)
    attachment = Attachment(bucket=settings.minio_bucket_proofs, storage_key=key, content_type=content_type, size_bytes=len(content))
    db.add(attachment); db.flush(); row.evidence_attachment_id = attachment.id
    log(db, user_id=user.id, action="upload_evidence", entity="route_occurrence", entity_id=row.id)
    db.commit()
    return {"evidence_url": storage.get_presigned_url(attachment.bucket, attachment.storage_key)}

class OccurrenceCategoryIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)

class OccurrenceCategoryOut(BaseModel):
    id: int
    code: str
    name: str
    active: bool
    system: bool

    class Config:
        from_attributes = True

def _occurrence_category_code(value: str) -> str:
    normalized = "".join(character for character in unicodedata.normalize("NFD", value.lower().strip()) if unicodedata.category(character) != "Mn")
    code = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")[:40]
    if not code: raise HTTPException(422, "Informe um nome válido para a categoria.")
    return code

def _ensure_occurrence_categories(db: Session, tenant_id: int | None) -> None:
    if tenant_id is None: return
    existing_codes = set(db.scalars(select(OccurrenceCategory.code).where(OccurrenceCategory.tenant_id == tenant_id)).all())
    for code, name in DEFAULT_OCCURRENCE_CATEGORIES:
        if code not in existing_codes:
            db.add(OccurrenceCategory(tenant_id=tenant_id, code=code, name=name, active=True, system=True))
    legacy_codes = db.scalars(select(RouteOccurrence.category).where(RouteOccurrence.tenant_id == tenant_id).distinct()).all()
    default_names = dict(DEFAULT_OCCURRENCE_CATEGORIES)
    for code in legacy_codes:
        if code and code not in existing_codes:
            db.add(OccurrenceCategory(tenant_id=tenant_id, code=code, name=default_names.get(code, code.replace("_", " ").title()), active=True))
    db.flush()

def _require_occurrence_category(db: Session, tenant_id: int | None, code: str, *, allow_inactive: bool = False) -> OccurrenceCategory:
    _ensure_occurrence_categories(db, tenant_id)
    row = db.scalar(select(OccurrenceCategory).where(OccurrenceCategory.tenant_id == tenant_id, OccurrenceCategory.code == code))
    if row is None or (not row.active and not allow_inactive):
        raise HTTPException(422, "Selecione uma categoria de ocorrência ativa.")
    return row

@router.get("/occurrence-categories", response_model=list[OccurrenceCategoryOut], dependencies=[Depends(_OCCURRENCE_ACCESS)])
def occurrence_categories(include_inactive: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _ensure_occurrence_categories(db, user.tenant_id)
    stmt = select(OccurrenceCategory).where(OccurrenceCategory.tenant_id == user.tenant_id)
    if not include_inactive: stmt = stmt.where(OccurrenceCategory.active.is_(True))
    rows = db.scalars(stmt.order_by(OccurrenceCategory.name)).all()
    db.commit()
    return rows

@router.post("/occurrence-categories", response_model=OccurrenceCategoryOut, status_code=201, dependencies=[Depends(_MANAGER)])
def create_occurrence_category(data: OccurrenceCategoryIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.tenant_id is None: raise HTTPException(422, "Empresa não identificada.")
    code = _occurrence_category_code(data.name)
    existing = db.scalar(select(OccurrenceCategory).where(OccurrenceCategory.tenant_id == user.tenant_id, OccurrenceCategory.code == code))
    if existing:
        if existing.active: raise HTTPException(409, "Esta categoria já está cadastrada.")
        existing.name, existing.active = data.name.strip(), True
        row = existing
    else:
        row = OccurrenceCategory(tenant_id=user.tenant_id, code=code, name=data.name.strip())
        db.add(row)
    db.flush(); log(db, user_id=user.id, action="create", entity="occurrence_category", entity_id=row.id)
    db.commit(); db.refresh(row); return row

@router.put("/occurrence-categories/{category_id}", response_model=OccurrenceCategoryOut, dependencies=[Depends(_MANAGER)])
def update_occurrence_category(category_id: int, data: OccurrenceCategoryIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.get(OccurrenceCategory, category_id)
    if row is None or row.tenant_id != user.tenant_id: raise HTTPException(404, "Categoria não encontrada.")
    row.name = data.name.strip()
    log(db, user_id=user.id, action="update", entity="occurrence_category", entity_id=row.id)
    db.commit(); db.refresh(row); return row

@router.put("/occurrence-categories/{category_id}/toggle", response_model=OccurrenceCategoryOut, dependencies=[Depends(_MANAGER)])
def toggle_occurrence_category(category_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.get(OccurrenceCategory, category_id)
    if row is None or row.tenant_id != user.tenant_id: raise HTTPException(404, "Categoria não encontrada.")
    row.active = not row.active
    log(db, user_id=user.id, action="activate" if row.active else "deactivate", entity="occurrence_category", entity_id=row.id)
    db.commit(); db.refresh(row); return row

class OccurrenceIn(BaseModel):
    route_id: int
    category: str = "outros"
    severity: str = "media"
    description: str = Field(min_length=3)
    latitude: float | None = None
    longitude: float | None = None

@router.post("/occurrences", status_code=201, dependencies=[Depends(_OCCURRENCE_REPORTER)])
def create_occurrence(data: OccurrenceIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    route = db.get(Route, data.route_id)
    if route is None: raise HTTPException(404, "Rota não encontrada.")
    require_branch_access(db, user, route.branch_id)
    _require_occurrence_category(db, route.tenant_id, data.category)
    if data.severity not in {"baixa", "media", "alta", "critica"}: raise HTTPException(400, "Gravidade inválida.")
    driver = db.scalar(select(Driver).where(Driver.user_id == user.id)) if user.role == Role.MOTORISTA.value else None
    if user.role == Role.MOTORISTA.value and driver is None: raise HTTPException(403, "Usuário sem cadastro de motorista vinculado.")
    if driver and route.driver_id != driver.id: raise HTTPException(403, "Rota não atribuída a este motorista.")
    row = RouteOccurrence(tenant_id=route.tenant_id, branch_id=route.branch_id, route_id=route.id, driver_id=route.driver_id, reported_by=user.id, **data.model_dump(exclude={"route_id"}))
    db.add(row); db.flush()
    # Uma ocorrência interrompe somente o deslocamento automático. Check-ins já
    # realizados representam chegada real e, portanto, nunca são apagados.
    for stop in route.stops:
        if stop.status == "em_rota" and stop.checkin_at is None:
            stop.status = "pendente"
    db.add(RouteOccurrenceEvent(occurrence_id=row.id, actor_id=user.id, from_status=None,
                                to_status="aberta", description="Ocorrência registrada."))
    notify_operational_audience(
        db,
        route=route,
        event_type="OCCURRENCE_CREATED",
        title="Nova ocorrência registrada",
        body=f"Rota {route.codigo_ut} · {data.description[:120]}",
    )
    log(db, user_id=user.id, action="create", entity="route_occurrence", entity_id=row.id)
    db.commit(); db.refresh(row); return row


@router.post("/occurrences-with-evidence", status_code=201, dependencies=[Depends(_OCCURRENCE_REPORTER)])
async def create_occurrence_with_required_evidence(
    route_id: int = Form(...), category: str = Form(...), severity: str = Form("media"),
    description: str = Form(...), latitude: float | None = Form(None), longitude: float | None = Form(None),
    evidence: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    if category != "sobra": raise HTTPException(422, "Este envio é exclusivo para ocorrências de sobra.")
    row = create_occurrence(
        OccurrenceIn(route_id=route_id, category=category, severity=severity, description=description, latitude=latitude, longitude=longitude),
        db=db, user=user,
    )
    await upload_occurrence_evidence(row.id, evidence, db=db, user=user)
    db.refresh(row)
    return row

class OccurrenceUpdateIn(BaseModel):
    route_id: int | None = None
    category: str | None = None
    severity: str | None = None
    description: str | None = Field(default=None, min_length=3)
    status: str | None = None
    resolution: str | None = None
    treatment_note: str | None = Field(default=None, max_length=2000)

def _can_manage_occurrence(user: User, row: RouteOccurrence) -> bool:
    effective_role = ROLE_EQUIVALENTS.get(user.role, user.role)
    return effective_role in {Role.ADMIN_GLOBAL.value, Role.GESTOR_BRASIL.value, Role.TORRE_CONTROLE.value, Role.OPERADOR_LOGISTICO.value} or (
        user.role == Role.MOTORISTA.value and row.reported_by == user.id
    )

@router.put("/occurrences/{occurrence_id}", dependencies=[Depends(_OCCURRENCE_ACCESS)])
def update_occurrence(occurrence_id: int, data: OccurrenceUpdateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.get(RouteOccurrence, occurrence_id)
    if row is None: raise HTTPException(404, "Ocorrência não encontrada.")
    require_branch_access(db, user, row.branch_id)
    if not _can_manage_occurrence(user, row): raise HTTPException(403, "Sem permissão para alterar esta ocorrência.")
    if user.role == Role.MOTORISTA.value and row.status != "aberta": raise HTTPException(409, "Somente ocorrências abertas podem ser alteradas pelo motorista.")
    if data.route_id is not None and data.route_id != row.route_id:
        route = db.get(Route, data.route_id)
        if route is None: raise HTTPException(404, "Rota não encontrada.")
        require_branch_access(db, user, route.branch_id)
        if user.role == Role.MOTORISTA.value:
            driver = db.scalar(select(Driver).where(Driver.user_id == user.id))
            if driver is None or route.driver_id != driver.id: raise HTTPException(403, "Rota não atribuída a este motorista.")
        row.route_id, row.branch_id, row.driver_id = route.id, route.branch_id, route.driver_id
    if data.category is not None:
        _require_occurrence_category(db, row.tenant_id, data.category, allow_inactive=data.category == row.category)
        row.category = data.category
    if data.severity is not None:
        if data.severity not in {"baixa", "media", "alta", "critica"}: raise HTTPException(400, "Gravidade inválida.")
        row.severity = data.severity
    if data.description is not None: row.description = data.description
    old_status = row.status
    if data.status is not None:
        if user.role == Role.MOTORISTA.value: raise HTTPException(403, "Motoristas não podem alterar o status.")
        # Compatibilidade: ocorrências antigas em análise passam a tratamento.
        if row.status == "em_analise": row.status = "em_tratamento"
        transitions = {"aberta":{"em_tratamento","cancelada"}, "em_tratamento":{"resolvida","cancelada"},
                       "resolvida":{"finalizada","em_tratamento"}, "finalizada":set(), "cancelada":set()}
        if data.status != row.status and data.status not in transitions.get(row.status, set()):
            raise HTTPException(409, f"Transição inválida: {row.status} → {data.status}.")
        if data.status in {"resolvida", "finalizada"} and len((data.resolution or row.resolution or "").strip()) < 5:
            raise HTTPException(422, "Descreva o que foi feito para resolver a ocorrência.")
        row.status = data.status
        now = datetime.now(timezone.utc)
        if data.status == "em_tratamento":
            row.assigned_to_id = user.id; row.treatment_started_at = row.treatment_started_at or now
        elif data.status == "resolvida": row.resolved_at = now
        elif data.status == "finalizada": row.finalized_at = now
    if user.role != Role.MOTORISTA.value and data.resolution is not None: row.resolution = data.resolution.strip() or None
    if data.status is not None and old_status != row.status:
        db.add(RouteOccurrenceEvent(occurrence_id=row.id, actor_id=user.id, from_status=old_status,
                                    to_status=row.status, description=data.treatment_note or row.resolution))
    log(db, user_id=user.id, action="update", entity="route_occurrence", entity_id=row.id)
    db.commit(); db.refresh(row); return row

@router.get("/occurrences/{occurrence_id}/history")
def occurrence_history(occurrence_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.get(RouteOccurrence, occurrence_id)
    if row is None: raise HTTPException(404, "Ocorrência não encontrada.")
    require_branch_access(db, user, row.branch_id)
    if user.role == Role.MOTORISTA.value and row.reported_by != user.id: raise HTTPException(403, "Ocorrência de outro motorista.")
    events = db.execute(select(RouteOccurrenceEvent, User.name).outerjoin(User, User.id == RouteOccurrenceEvent.actor_id)
                        .where(RouteOccurrenceEvent.occurrence_id == row.id).order_by(RouteOccurrenceEvent.created_at)).all()
    return [{"id": event.id, "from_status": event.from_status, "to_status": event.to_status,
             "description": event.description, "actor": actor, "created_at": event.created_at}
            for event, actor in events]

@router.delete("/occurrences/{occurrence_id}", status_code=204, dependencies=[Depends(_OCCURRENCE_REPORTER)])
def delete_occurrence(occurrence_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.get(RouteOccurrence, occurrence_id)
    if row is None: raise HTTPException(404, "Ocorrência não encontrada.")
    require_branch_access(db, user, row.branch_id)
    if not _can_manage_occurrence(user, row): raise HTTPException(403, "Sem permissão para excluir esta ocorrência.")
    if user.role == Role.MOTORISTA.value and row.status != "aberta": raise HTTPException(409, "Somente ocorrências abertas podem ser excluídas pelo motorista.")
    log(db, user_id=user.id, action="delete", entity="route_occurrence", entity_id=row.id)
    db.delete(row); db.commit()

class PurchaseIn(BaseModel):
    branch_id: int
    department: str = "frota"
    description: str = Field(min_length=3)
    amount: float = Field(gt=0)
    supplier_id: int
    provider_id: int | None = None
    category: str = "outros"
    document: str | None = None
    due_date: date
    cost_center: str | None = None
    items: list[dict] = Field(default_factory=list)

def _purchase_out(db:Session,row:PurchaseTicket):
    supplier=db.get(Supplier,row.supplier_id) if row.supplier_id else None;requester=db.get(User,row.requester_id);approver=db.get(User,row.approved_by) if row.approved_by else None
    items=db.scalars(select(PurchaseItem).where(PurchaseItem.purchase_id==row.id)).all()
    if row.received_at:sla_status="completed_on_time" if row.delivery_due_date and row.received_at.date()<=row.delivery_due_date else "completed_late"
    elif row.delivery_due_date is None:sla_status="pending"
    else:
        remaining=(row.delivery_due_date-date.today()).days;sla_status="overdue" if remaining<0 else "attention" if remaining<=2 else "on_time"
    return {**row.__dict__,"supplier_name":supplier.trade_name or supplier.legal_name if supplier else None,"requester_name":requester.name if requester else None,"approver_name":approver.name if approver else None,"sla_status":sla_status,"items":[{"id":x.id,"description":x.description,"quantity":float(x.quantity),"unit":x.unit,"unit_price":float(x.unit_price)} for x in items]}

@router.get("/purchases")
def purchases(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(PurchaseTicket).order_by(PurchaseTicket.created_at.desc())
    stmt = scope_by_branch(stmt, PurchaseTicket.branch_id, user, db)
    purchase_viewers={Role.GESTOR_BRASIL.value,Role.GESTOR_FINANCEIRO.value,Role.OPERADOR_LOGISTICO.value}
    if user.role not in purchase_viewers and user.role!=Role.ADMIN_GLOBAL.value:
        stmt=stmt.where(PurchaseTicket.requester_id==user.id)
    return [_purchase_out(db,row) for row in db.scalars(stmt).all()]

@router.post("/purchases", status_code=201)
def create_purchase(data: PurchaseIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    branch=require_branch_access(db,user,data.branch_id);supplier=db.get(Supplier,data.supplier_id)
    if supplier is None or supplier.tenant_id!=branch.tenant_id:raise HTTPException(422,"Fornecedor inválido para esta empresa.")
    if not data.items:raise HTTPException(422,"Inclua ao menos um item na compra.")
    calculated_amount=Decimal("0")
    for item in data.items:
        if not item.get("description") or float(item.get("quantity",0))<=0 or float(item.get("unit_price",0))<0:raise HTTPException(422,"Item da compra inválido.")
        calculated_amount+=Decimal(str(item["quantity"]))*Decimal(str(item["unit_price"]))
    values=data.model_dump(exclude={"branch_id","items","amount"});row=PurchaseTicket(tenant_id=branch.tenant_id,branch_id=data.branch_id,ticket=f"CMP-{datetime.now().strftime('%Y%m%d%H%M%S%f')[-16:]}",requester_id=user.id,amount=calculated_amount,**values)
    db.add(row);db.flush()
    for item in data.items:
        db.add(PurchaseItem(purchase_id=row.id,description=item["description"],quantity=item["quantity"],unit=item.get("unit","un"),unit_price=item["unit_price"]))
    log(db,user_id=user.id,action="create",entity="purchase",entity_id=row.id,detail=f"fornecedor={supplier.legal_name}; valor={row.amount}");db.commit();db.refresh(row);return _purchase_out(db,row)

class PurchaseDecisionIn(BaseModel):
    note: str = Field(min_length=3, max_length=2000)

@router.post("/purchases/{purchase_id}/start-review", dependencies=[Depends(_PURCHASE_STAFF)])
def start_purchase_review(purchase_id: int, data: PurchaseDecisionIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row=db.get(PurchaseTicket,purchase_id)
    if row is None: raise HTTPException(404,"Solicitação não encontrada.")
    require_branch_access(db,user,row.branch_id)
    if row.status not in {"solicitada","ajuste_solicitado"}: raise HTTPException(409,"Esta solicitação não está disponível para análise.")
    row.status="em_analise";row.rejection_reason=None
    log(db,user_id=user.id,action="start_review",entity="purchase",entity_id=row.id,detail=data.note)
    db.commit();return _purchase_out(db,row)

@router.post("/purchases/{purchase_id}/submit-approval", dependencies=[Depends(_PURCHASE_STAFF)])
def submit_purchase_approval(purchase_id: int, data: PurchaseDecisionIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row=db.get(PurchaseTicket,purchase_id)
    if row is None: raise HTTPException(404,"Solicitação não encontrada.")
    require_branch_access(db,user,row.branch_id)
    if row.status!="em_analise": raise HTTPException(409,"A equipe de Compras deve iniciar a análise antes de enviar para aprovação.")
    row.status="aguardando_aprovacao"
    log(db,user_id=user.id,action="submit_approval",entity="purchase",entity_id=row.id,detail=data.note)
    db.commit();return _purchase_out(db,row)

@router.post("/purchases/{purchase_id}/request-adjustment")
def request_purchase_adjustment(purchase_id: int, data: PurchaseDecisionIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row=db.get(PurchaseTicket,purchase_id)
    if row is None: raise HTTPException(404,"Solicitação não encontrada.")
    require_branch_access(db,user,row.branch_id)
    allowed={Role.ADMIN_GLOBAL.value,Role.GESTOR_BRASIL.value,Role.GESTOR_FINANCEIRO.value,Role.OPERADOR_LOGISTICO.value}
    if user.role not in allowed: raise HTTPException(403,"Perfil sem permissão para devolver a solicitação.")
    if row.status not in {"em_analise","aguardando_aprovacao"}: raise HTTPException(409,"Esta solicitação não pode ser devolvida para ajuste.")
    row.status="ajuste_solicitado";row.rejection_reason=data.note
    log(db,user_id=user.id,action="request_adjustment",entity="purchase",entity_id=row.id,detail=data.note)
    db.commit();return _purchase_out(db,row)

@router.post("/purchases/{purchase_id}/approve", dependencies=[Depends(_FINANCE_MANAGE)])
def approve_purchase(purchase_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.get(PurchaseTicket, purchase_id)
    if row is None: raise HTTPException(404, "Solicitação não encontrada.")
    require_branch_access(db,user,row.branch_id)
    if row.status not in {"aguardando_aprovacao","solicitada"}:raise HTTPException(409,"A solicitação ainda não foi enviada para aprovação ou já foi analisada.")
    supplier=db.get(Supplier,row.supplier_id)
    account=FinancialAccount(branch_id=row.branch_id,kind="payable",description=f"Compra {row.ticket} — {row.description[:100]}",counterparty=(supplier.trade_name or supplier.legal_name),category=row.category,document=row.document,issue_date=date.today(),due_date=row.due_date or date.today(),amount=row.amount,status="pendente",notes=f"Gerada automaticamente após aprovação da compra {row.ticket}.",created_by=user.id)
    db.add(account);db.flush();row.financial_account_id=account.id;row.status="aprovada";row.approved_by=user.id;row.approved_at=datetime.now(timezone.utc)
    log(db,user_id=user.id,action="approve",entity="purchase",entity_id=row.id,detail=f"conta_a_pagar={account.id}");db.commit();db.refresh(row);return _purchase_out(db,row)

class RejectIn(BaseModel): reason: str = Field(min_length=3)
@router.post("/purchases/{purchase_id}/reject", dependencies=[Depends(_FINANCE_MANAGE)])
def reject_purchase(purchase_id: int, data: RejectIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row=db.get(PurchaseTicket,purchase_id)
    if row is None: raise HTTPException(404,"Solicitação não encontrada.")
    require_branch_access(db,user,row.branch_id)
    if row.status not in {"aguardando_aprovacao","solicitada"}:raise HTTPException(409,"A solicitação ainda não foi enviada para aprovação ou já foi analisada.")
    row.status="rejeitada";row.rejection_reason=data.reason;log(db,user_id=user.id,action="reject",entity="purchase",entity_id=row.id,detail=data.reason);db.commit();return _purchase_out(db,row)

class PurchaseExecutionIn(BaseModel):
    delivery_due_date: date

@router.post("/purchases/{purchase_id}/purchased",dependencies=[Depends(_PURCHASE_STAFF)])
def mark_purchase_executed(purchase_id:int,data:PurchaseExecutionIn,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    row=db.get(PurchaseTicket,purchase_id)
    if row is None:raise HTTPException(404,"Compra não encontrada.")
    require_branch_access(db,user,row.branch_id)
    if row.status!="aprovada":raise HTTPException(409,"Somente compras aprovadas podem ser executadas.")
    if data.delivery_due_date<date.today():raise HTTPException(422,"A previsão de entrega não pode estar no passado.")
    row.status="comprada";row.purchased_at=datetime.now(timezone.utc);row.delivery_due_date=data.delivery_due_date
    log(db,user_id=user.id,action="purchased",entity="purchase",entity_id=row.id,detail=f"previsao_entrega={data.delivery_due_date}");db.commit();return _purchase_out(db,row)

@router.post("/purchases/{purchase_id}/received",dependencies=[Depends(_PURCHASE_STAFF)])
def mark_purchase_received(purchase_id:int,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    row=db.get(PurchaseTicket,purchase_id)
    if row is None:raise HTTPException(404,"Compra não encontrada.")
    require_branch_access(db,user,row.branch_id)
    if row.status!="comprada":raise HTTPException(409,"Registre a compra e a previsão de entrega antes do recebimento.")
    row.status="recebida";row.received_at=datetime.now(timezone.utc);log(db,user_id=user.id,action="received",entity="purchase",entity_id=row.id);db.commit();return _purchase_out(db,row)

class FinancialAccountIn(BaseModel):
    branch_id: int
    kind: str
    description: str = Field(min_length=2, max_length=180)
    counterparty: str = Field(min_length=2, max_length=180)
    category: str = "outros"
    document: str | None = None
    issue_date: date
    due_date: date
    amount: float = Field(gt=0)
    notes: str | None = None
    driver_id: int | None = None
    route_id: int | None = None
    discount_reason: str | None = Field(default=None, max_length=180)

class FinancialAccountUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=2, max_length=180)
    counterparty: str | None = Field(default=None, min_length=2, max_length=180)
    category: str | None = None
    document: str | None = None
    issue_date: date | None = None
    due_date: date | None = None
    amount: float | None = Field(default=None, gt=0)
    notes: str | None = None
    driver_id: int | None = None
    route_id: int | None = None
    discount_reason: str | None = Field(default=None, max_length=180)

class FinancialCategoryIn(BaseModel):
    kind: str
    name: str = Field(min_length=2, max_length=120)

def _category_code(value: str) -> str:
    normalized = "".join(character for character in unicodedata.normalize("NFD", value.lower().strip()) if unicodedata.category(character) != "Mn")
    code = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    if not code: raise HTTPException(422, "Informe um nome válido para a categoria.")
    return code[:80]

def _require_financial_category(db: Session, user: User, kind: str, code: str) -> FinancialCategory:
    category = db.scalar(select(FinancialCategory).where(
        FinancialCategory.tenant_id == user.tenant_id,
        FinancialCategory.kind == kind,
        FinancialCategory.code == code,
        FinancialCategory.active.is_(True),
    ))
    if category is None: raise HTTPException(422, "Selecione uma categoria financeira ativa.")
    return category

@router.get("/financial-categories", dependencies=[Depends(_FINANCE)])
def financial_categories(kind: str, include_inactive: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if kind not in {"payable", "receivable"}: raise HTTPException(400, "Tipo de categoria inválido.")
    stmt = select(FinancialCategory).where(FinancialCategory.tenant_id == user.tenant_id, FinancialCategory.kind == kind)
    if not include_inactive: stmt = stmt.where(FinancialCategory.active.is_(True))
    rows = db.scalars(stmt.order_by(FinancialCategory.name)).all()
    return [{"id": row.id, "kind": row.kind, "code": row.code, "name": row.name, "active": row.active, "system": row.system} for row in rows]

@router.post("/financial-categories", status_code=201, dependencies=[Depends(_FINANCE_MANAGE)])
def create_financial_category(data: FinancialCategoryIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if data.kind not in {"payable", "receivable"}: raise HTTPException(400, "Tipo de categoria inválido.")
    code = _category_code(data.name)
    existing = db.scalar(select(FinancialCategory).where(FinancialCategory.tenant_id == user.tenant_id, FinancialCategory.kind == data.kind, FinancialCategory.code == code))
    if existing:
        if existing.active: raise HTTPException(409, "Esta categoria já está cadastrada.")
        existing.name = data.name.strip(); existing.active = True; db.commit(); db.refresh(existing); return existing
    row = FinancialCategory(tenant_id=user.tenant_id, kind=data.kind, code=code, name=data.name.strip(), active=True)
    db.add(row); db.commit(); db.refresh(row); return row

@router.put("/financial-categories/{category_id}/toggle", dependencies=[Depends(_FINANCE_MANAGE)])
def toggle_financial_category(category_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.get(FinancialCategory, category_id)
    if row is None or row.tenant_id != user.tenant_id: raise HTTPException(404, "Categoria não encontrada.")
    row.active = not row.active; db.commit(); db.refresh(row); return row

@router.get("/financial-accounts", dependencies=[Depends(_FINANCE)])
def financial_accounts(kind: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if kind not in {"payable", "receivable"}: raise HTTPException(400, "Tipo de conta inválido.")
    stmt = select(FinancialAccount).where(FinancialAccount.kind == kind).order_by(FinancialAccount.due_date, FinancialAccount.id)
    stmt = scope_by_branch(stmt, FinancialAccount.branch_id, user, db)
    rows = db.scalars(stmt).all()
    return [{
        "id": row.id, "kind": row.kind, "description": row.description,
        "counterparty": row.counterparty, "category": row.category, "document": row.document,
        "issue_date": row.issue_date, "due_date": row.due_date, "amount": row.amount,
        "status": row.status, "settled_at": row.settled_at, "notes": row.notes,
        "driver_id": row.driver_id, "route_id": row.route_id, "discount_reason": row.discount_reason,
        "service_invoice_number": row.service_invoice_number,
        "service_invoice_filename": Path(row.service_invoice_attachment.storage_key).name.split("-", 1)[-1] if row.service_invoice_attachment else None,
        "service_invoice_url": storage.get_presigned_url(row.service_invoice_attachment.bucket, row.service_invoice_attachment.storage_key) if row.service_invoice_attachment else None,
    } for row in rows]

@router.post("/financial-accounts", status_code=201, dependencies=[Depends(_FINANCE_MANAGE)])
def create_financial_account(data: FinancialAccountIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if data.kind not in {"payable", "receivable"}: raise HTTPException(400, "Tipo de conta inválido.")
    if data.due_date < data.issue_date: raise HTTPException(400, "O vencimento não pode ser anterior à emissão.")
    require_branch_access(db, user, data.branch_id)
    _require_financial_category(db, user, data.kind, data.category)
    discount_driver = None; discount_route = None
    if data.category == "desconto_motorista":
        if data.kind != "receivable": raise HTTPException(422, "Desconto de motorista deve ser lançado como receita.")
        if not data.driver_id or not data.route_id or len((data.discount_reason or "").strip()) < 3: raise HTTPException(422, "Selecione motorista, rota e informe o motivo do desconto.")
        discount_driver=db.get(Driver,data.driver_id);discount_route=db.get(Route,data.route_id)
        if discount_driver is None or discount_route is None or discount_route.driver_id != discount_driver.id: raise HTTPException(422,"A rota selecionada não pertence ao motorista informado.")
        require_branch_access(db,user,discount_driver.branch_id)
    row = FinancialAccount(**data.model_dump(), created_by=user.id)
    if discount_driver: row.counterparty=discount_driver.name;row.description=f"Desconto de motorista · {discount_driver.name} · {discount_route.codigo_ut}"
    db.add(row); db.flush()
    if discount_driver:
        db.add(DriverStatementAdjustment(tenant_id=user.tenant_id,branch_id=discount_driver.branch_id,driver_id=discount_driver.id,route_id=discount_route.id,entry_date=row.issue_date,kind="deduction",reason=(row.discount_reason or "").strip(),amount=row.amount,notes=f"Gerado pela conta a receber #{row.id}.",created_by=user.id,financial_account_id=row.id))
    log(db,user_id=user.id,action="create",entity="financial_account",entity_id=row.id,detail=f"{row.kind}; valor={row.amount}; vencimento={row.due_date}"); db.commit(); db.refresh(row); return row

@router.put("/financial-accounts/{account_id}", dependencies=[Depends(_FINANCE_MANAGE)])
def update_financial_account(account_id: int, data: FinancialAccountUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.get(FinancialAccount, account_id)
    if row is None: raise HTTPException(404, "Conta não encontrada.")
    require_branch_access(db,user,row.branch_id)
    if row.status != "pendente": raise HTTPException(409,"Somente contas pendentes podem ser alteradas.")
    updates=data.model_dump(exclude_unset=True)
    if "category" in updates: _require_financial_category(db, user, row.kind, updates["category"])
    effective_issue=updates.get("issue_date",row.issue_date);effective_due=updates.get("due_date",row.due_date)
    if effective_due < effective_issue: raise HTTPException(400,"O vencimento não pode ser anterior à emissão.")
    effective_category=updates.get("category",row.category)
    if effective_category == "desconto_motorista":
        driver_id=updates.get("driver_id",row.driver_id);route_id=updates.get("route_id",row.route_id);reason=updates.get("discount_reason",row.discount_reason)
        driver=db.get(Driver,driver_id) if driver_id else None;route=db.get(Route,route_id) if route_id else None
        if driver is None or route is None or route.driver_id != driver.id or len((reason or "").strip())<3: raise HTTPException(422,"Selecione motorista, uma rota dele e informe o motivo do desconto.")
        adjustment=db.scalar(select(DriverStatementAdjustment).where(DriverStatementAdjustment.financial_account_id==row.id))
        if adjustment is None:
            adjustment=DriverStatementAdjustment(tenant_id=user.tenant_id,branch_id=driver.branch_id,driver_id=driver.id,route_id=route.id,entry_date=effective_issue,kind="deduction",reason=reason.strip(),amount=updates.get("amount",row.amount),created_by=user.id,financial_account_id=row.id)
            db.add(adjustment)
        else:
            adjustment.driver_id=driver.id;adjustment.route_id=route.id;adjustment.entry_date=effective_issue;adjustment.reason=reason.strip();adjustment.amount=updates.get("amount",row.amount)
    elif row.category == "desconto_motorista":
        adjustment=db.scalar(select(DriverStatementAdjustment).where(DriverStatementAdjustment.financial_account_id==row.id))
        if adjustment and not adjustment.voided: adjustment.voided=True;adjustment.voided_by=user.id;adjustment.voided_at=datetime.now(timezone.utc);adjustment.void_reason="Categoria da conta alterada."
    for key,value in updates.items(): setattr(row,key,value)
    log(db,user_id=user.id,action="update",entity="financial_account",entity_id=row.id,detail=str(sorted(updates)))
    db.commit();db.refresh(row);return row

class SettlementIn(BaseModel):
    settled_at: date

@router.post("/financial-accounts/{account_id}/settle", dependencies=[Depends(_FINANCE_MANAGE)])
def settle_financial_account(account_id:int,data:SettlementIn,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    row=db.get(FinancialAccount,account_id)
    if row is None: raise HTTPException(404,"Conta não encontrada.")
    require_branch_access(db,user,row.branch_id)
    if row.status != "pendente": raise HTTPException(409,"Conta já finalizada.")
    if row.kind == "receivable": raise HTTPException(422,"Informe o número e anexe a nota de serviço para registrar o recebimento.")
    row.status="paga" if row.kind=="payable" else "recebida";row.settled_at=data.settled_at
    log(db,user_id=user.id,action="settle",entity="financial_account",entity_id=row.id,detail=f"status={row.status}; data={data.settled_at}; valor={row.amount}")
    db.commit();db.refresh(row);return row

_INVOICE_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/jpg", "image/webp"}
_INVOICE_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}

@router.post("/financial-accounts/{account_id}/settle-with-invoice", dependencies=[Depends(_FINANCE_MANAGE)])
async def settle_receivable_with_invoice(
    account_id: int,
    settled_at: date = Form(...),
    service_invoice_number: str = Form(...),
    service_invoice: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = db.get(FinancialAccount, account_id)
    if row is None: raise HTTPException(404, "Conta não encontrada.")
    require_branch_access(db, user, row.branch_id)
    if row.kind != "receivable": raise HTTPException(409, "Este fluxo é exclusivo para contas a receber.")
    if row.status != "pendente": raise HTTPException(409, "Conta já finalizada.")
    invoice_number = service_invoice_number.strip()
    if not invoice_number: raise HTTPException(422, "Informe o número da nota de serviço.")
    suffix = Path(service_invoice.filename or "").suffix.lower()
    if suffix not in _INVOICE_EXTENSIONS or (service_invoice.content_type or "") not in _INVOICE_TYPES:
        raise HTTPException(422, "Anexe a nota de serviço em PDF, PNG, JPG ou WEBP.")
    content = await service_invoice.read()
    if not content: raise HTTPException(422, "O arquivo da nota de serviço está vazio.")
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"Arquivo excede o limite de {settings.max_upload_mb} MB.")
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(service_invoice.filename or f"nota{suffix}").name)[:120]
    key = f"notas-servico/{row.branch_id}/{settled_at:%Y/%m}/{uuid.uuid4().hex}-{safe_name}"
    storage.put_object(settings.minio_bucket_proofs, key, content, service_invoice.content_type or "application/octet-stream")
    attachment = Attachment(bucket=settings.minio_bucket_proofs, storage_key=key, content_type=service_invoice.content_type, size_bytes=len(content))
    db.add(attachment); db.flush()
    row.service_invoice_number = invoice_number
    row.service_invoice_attachment_id = attachment.id
    row.status = "recebida"; row.settled_at = settled_at
    log(db, user_id=user.id, action="settle", entity="financial_account", entity_id=row.id, detail=f"status=recebida; data={settled_at}; valor={row.amount}; nota_servico={invoice_number}; anexo={attachment.id}")
    db.commit(); db.refresh(row)
    return {"id": row.id, "status": row.status, "settled_at": row.settled_at, "service_invoice_number": row.service_invoice_number}

@router.post("/financial-accounts/{account_id}/cancel", dependencies=[Depends(_FINANCE_MANAGE)])
def cancel_financial_account(account_id:int,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    row=db.get(FinancialAccount,account_id)
    if row is None: raise HTTPException(404,"Conta não encontrada.")
    require_branch_access(db,user,row.branch_id)
    if row.status != "pendente": raise HTTPException(409,"Somente contas pendentes podem ser canceladas.")
    row.status="cancelada"
    adjustment=db.scalar(select(DriverStatementAdjustment).where(DriverStatementAdjustment.financial_account_id==row.id))
    if adjustment and not adjustment.voided: adjustment.voided=True;adjustment.voided_by=user.id;adjustment.voided_at=datetime.now(timezone.utc);adjustment.void_reason="Conta a receber cancelada."
    log(db,user_id=user.id,action="cancel",entity="financial_account",entity_id=row.id);db.commit();db.refresh(row);return row

@router.get("/dre", dependencies=[Depends(_FINANCE)])
def dre(start: date | None = None, end: date | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    revenue = select(func.coalesce(func.sum(Revenue.amount), 0)); expense = select(func.coalesce(func.sum(Expense.amount), 0)).where(Expense.approval_status == "approved")
    if user.role != Role.ADMIN_GLOBAL.value:
        revenue = revenue.where(Revenue.branch_id == (user.branch_id if user.branch_id is not None else -1)); expense = expense.where(Expense.branch_id == (user.branch_id if user.branch_id is not None else -1))
    if start: revenue = revenue.where(Revenue.revenue_date >= start); expense = expense.where(Expense.expense_date >= start)
    if end: revenue = revenue.where(Revenue.revenue_date <= end); expense = expense.where(Expense.expense_date <= end)
    rv, ex = float(db.scalar(revenue) or 0), float(db.scalar(expense) or 0)
    return {"revenue": rv, "expense": ex, "result": rv - ex, "margin_percent": round((rv - ex) / rv * 100, 2) if rv else 0}

def _month_key(value: date) -> str:
    return value.strftime("%Y-%m")

@router.get("/financial-dashboard", dependencies=[Depends(_FINANCE)])
def financial_dashboard(months: int = 12, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    months = max(3, min(months, 24)); today = date.today()
    month_keys=[]; year,month=today.year,today.month
    for offset in range(months-1,-1,-1):
        absolute=year*12+(month-1)-offset; month_keys.append(f"{absolute//12:04d}-{absolute%12+1:02d}")
    start=date.fromisoformat(month_keys[0]+"-01")
    revenue_stmt=select(Revenue).where(Revenue.revenue_date>=start)
    expense_stmt=select(Expense).where(Expense.expense_date>=start, Expense.approval_status=="approved")
    account_stmt=select(FinancialAccount).where(FinancialAccount.due_date>=start)
    order_stmt=select(MaintenanceOrder,Vehicle.plate).join(Vehicle,Vehicle.id==MaintenanceOrder.vehicle_id).where(MaintenanceOrder.opened_at>=start)
    part_stmt=select(Part).where(Part.active.is_(True))
    if user.role!=Role.ADMIN_GLOBAL.value:
        revenue_stmt=revenue_stmt.where(Revenue.branch_id==user.branch_id);expense_stmt=expense_stmt.where(Expense.branch_id==user.branch_id)
        account_stmt=account_stmt.where(FinancialAccount.branch_id==user.branch_id);order_stmt=order_stmt.where(MaintenanceOrder.branch_id==user.branch_id);part_stmt=part_stmt.where(Part.branch_id==user.branch_id)
    revenues=list(db.scalars(revenue_stmt).all());expenses=list(db.scalars(expense_stmt).all());accounts=list(db.scalars(account_stmt).all());orders=list(db.execute(order_stmt).all());parts=list(db.scalars(part_stmt).all())
    route_ids={row.route_id for row in revenues if row.route_id};route_codes=dict(db.execute(select(Route.id,Route.codigo_ut).where(Route.id.in_(route_ids))).all()) if route_ids else {}
    series={key:{"month":key,"revenue":0.0,"expense":0.0,"payable":0.0,"receivable":0.0} for key in month_keys}
    expense_category={};vehicle_cost={};route_revenue={};account_category={"payable":{},"receivable":{}}
    for row in revenues:
        key=_month_key(row.revenue_date)
        if key in series: series[key]["revenue"]+=float(row.amount or 0)
        route_label=route_codes.get(row.route_id,"Sem rota");route_revenue[route_label]=route_revenue.get(route_label,0)+float(row.amount or 0)
    for row in expenses:
        amount=float(row.amount or 0);key=_month_key(row.expense_date)
        if key in series: series[key]["expense"]+=amount
        expense_category[row.reason]=expense_category.get(row.reason,0)+amount
        plate=row.vehicle.plate if row.vehicle else "Sem veículo";vehicle_cost[plate]=vehicle_cost.get(plate,0)+amount
    for row in accounts:
        amount=float(row.amount or 0);key=_month_key(row.due_date)
        if key in series and row.status!="cancelada":series[key][row.kind]+=amount
        bucket=account_category[row.kind];bucket[row.category]=bucket.get(row.category,0)+amount
    maintenance_total=0.0
    for order,plate in orders:
        maintenance_total+=float(order.cost or 0)
    customers_by_route={}
    if route_ids:
        for route_id,name in db.execute(select(RouteStop.route_id,RouteStop.customer_name).where(RouteStop.route_id.in_(route_ids))).all():
            if name: customers_by_route.setdefault(route_id,set()).add(name)
    customer_revenue={}
    for row in revenues:
        names=customers_by_route.get(row.route_id) or {"Cliente não identificado"};share=float(row.amount or 0)/len(names)
        for name in names:customer_revenue[name]=customer_revenue.get(name,0)+share
    total_revenue=sum(float(row.amount or 0) for row in revenues);total_expense=sum(float(row.amount or 0) for row in expenses);result=total_revenue-total_expense
    rank=lambda values:[{"label":label,"value":round(value,2)} for label,value in sorted(values.items(),key=lambda item:item[1],reverse=True)[:8]]
    return {"kpis":{"revenue":round(total_revenue,2),"expense":round(total_expense,2),"result":round(result,2),"margin_percent":round(result/total_revenue*100,2) if total_revenue else 0,"pending_payable":round(sum(float(row.amount) for row in accounts if row.kind=="payable" and row.status=="pendente"),2),"pending_receivable":round(sum(float(row.amount) for row in accounts if row.kind=="receivable" and row.status=="pendente"),2)},"monthly":list(series.values()),"expense_by_category":rank(expense_category),"payable_by_category":rank(account_category["payable"]),"receivable_by_category":rank(account_category["receivable"]),"vehicle_cost":rank(vehicle_cost),"route_revenue":rank(route_revenue),"customer_revenue":rank(customer_revenue),"operations":{"inventory_value":round(sum(float(part.quantity)*float(part.average_cost or 0) for part in parts),2),"maintenance_cost":round(maintenance_total,2),"low_stock_items":sum(1 for part in parts if part.quantity<=part.minimum_quantity)}}

@router.get("/statement", dependencies=[Depends(_FINANCE)])
def statement(start: date | None = None, end: date | None = None, driver_id:int|None=None, vehicle_id:int|None=None, customer:str|None=None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Extrato cronológico unificado de entradas e saídas."""
    if driver_id and start and end:
        _, payment_rows, _, _ = _driver_statement_data(driver_id, start, end, db, user)
        return sorted([{"id":f"driver-{row['id']}","date":row["date"],"kind":"ganho_motorista" if row["kind"]=="earning" else "desconto_motorista","description":row["reason"],"route":row["route"],"amount":row["amount"] if row["kind"]=="earning" else -row["amount"]} for row in payment_rows],key=lambda row:(row["date"],row["id"]),reverse=True)
    if not driver_id:
        return []
    revenues = select(Revenue, Route.codigo_ut).outerjoin(Route, Route.id == Revenue.route_id)
    expenses = select(Expense, Route.codigo_ut).outerjoin(Route, Route.id == Expense.route_id).where(Expense.approval_status == "approved")
    route_filter=select(Route.id)
    if driver_id:route_filter=route_filter.where(Route.driver_id==driver_id)
    if vehicle_id:route_filter=route_filter.where(Route.vehicle_id==vehicle_id)
    if customer:route_filter=route_filter.join(RouteStop,RouteStop.route_id==Route.id).where((RouteStop.customer_name.ilike(f"%{customer}%"))|(RouteStop.client_name.ilike(f"%{customer}%")))
    if driver_id or vehicle_id or customer:
        revenues=revenues.where(Revenue.route_id.in_(route_filter));expenses=expenses.where(Expense.route_id.in_(route_filter))
    if user.role != Role.ADMIN_GLOBAL.value:
        revenues = revenues.where(Revenue.branch_id == (user.branch_id if user.branch_id is not None else -1)); expenses = expenses.where(Expense.branch_id == (user.branch_id if user.branch_id is not None else -1))
    if start: revenues = revenues.where(Revenue.revenue_date >= start); expenses = expenses.where(Expense.expense_date >= start)
    if end: revenues = revenues.where(Revenue.revenue_date <= end); expenses = expenses.where(Expense.expense_date <= end)
    rows = ([{"id": f"r-{row.id}", "date": row.revenue_date, "kind": "entrada", "description": row.notes or "Receita", "route": code, "amount": float(row.amount)} for row, code in db.execute(revenues).all()] +
            [{"id": f"e-{row.id}", "date": row.expense_date, "kind": "saida", "description": row.reason, "route": code, "amount": -float(row.amount or 0)} for row, code in db.execute(expenses).all()])
    adjustments=select(DriverStatementAdjustment,Route.codigo_ut,Driver.name).join(Driver,Driver.id==DriverStatementAdjustment.driver_id).outerjoin(Route,Route.id==DriverStatementAdjustment.route_id).where(DriverStatementAdjustment.voided.is_(False))
    if user.role!=Role.ADMIN_GLOBAL.value:adjustments=adjustments.where(DriverStatementAdjustment.branch_id==user.branch_id)
    if driver_id:adjustments=adjustments.where(DriverStatementAdjustment.driver_id==driver_id)
    if vehicle_id or customer:adjustments=adjustments.where(DriverStatementAdjustment.route_id.in_(route_filter))
    if start:adjustments=adjustments.where(DriverStatementAdjustment.entry_date>=start)
    if end:adjustments=adjustments.where(DriverStatementAdjustment.entry_date<=end)
    rows += [{"id":f"a-{row.id}","date":row.entry_date,"kind":"ganho_motorista" if row.kind=="earning" else "desconto_motorista","description":f"{name}: {row.reason}","route":code,"amount":float(row.amount)*(1 if row.kind=="earning" else -1)} for row,code,name in db.execute(adjustments).all()]
    return sorted(rows, key=lambda row: (row["date"], row["id"]), reverse=True)

class DriverAdjustmentIn(BaseModel):
    driver_id:int;route_id:int|None=None;entry_date:date;kind:str;reason:str=Field(min_length=3,max_length=160);amount:float=Field(gt=0);notes:str|None=None

class DriverPayableIn(BaseModel):
    driver_id: int
    start: date
    end: date
    due_date: date

@router.post("/driver-statement/payable", status_code=201, dependencies=[Depends(_FINANCE_MANAGE)])
def create_driver_statement_payable(data: DriverPayableIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if data.end < data.start: raise HTTPException(422, "O fim do período não pode ser anterior ao início.")
    driver, rows, earnings, deductions = _driver_statement_data(data.driver_id, data.start, data.end, db, user)
    net = earnings - deductions
    if net <= 0: raise HTTPException(422, "O extrato não possui valor líquido positivo para pagamento.")
    existing = db.scalar(select(FinancialAccount).where(
        FinancialAccount.driver_id == driver.id,
        FinancialAccount.payment_period_start == data.start,
        FinancialAccount.payment_period_end == data.end,
    ))
    if existing: raise HTTPException(409, f"Este período já gerou a conta a pagar #{existing.id}.")
    category = _require_financial_category(db, user, "payable", "diaria_motorista")
    vínculo = "agregado" if driver.employment_type == "agregado" else "próprio"
    row = FinancialAccount(
        tenant_id=user.tenant_id, branch_id=driver.branch_id, kind="payable",
        description=f"Pagamento de motorista {vínculo} · {data.start:%d/%m/%Y} a {data.end:%d/%m/%Y}",
        counterparty=driver.name, category=category.code,
        document=f"EXT-MOT-{driver.id}-{data.start:%Y%m%d}-{data.end:%Y%m%d}",
        issue_date=date.today(), due_date=data.due_date, amount=net, status="pendente",
        notes=f"Extrato: ganhos R$ {earnings:.2f}; descontos R$ {deductions:.2f}.",
        created_by=user.id, driver_id=driver.id,
        payment_period_start=data.start, payment_period_end=data.end,
    )
    db.add(row); db.flush(); log(db,user_id=user.id,action="create",entity="driver_statement_payable",entity_id=row.id,detail=f"motorista={driver.id}; vinculo={vínculo}; liquido={net}"); db.commit(); db.refresh(row)
    return {"id": row.id, "amount": float(row.amount), "driver": driver.name, "employment_type": driver.employment_type}

@router.post("/driver-adjustments",dependencies=[Depends(_FINANCE_MANAGE)])
def create_driver_adjustment(data:DriverAdjustmentIn,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    if data.kind not in {"earning","deduction"}:raise HTTPException(422,"Tipo inválido.")
    driver=db.get(Driver,data.driver_id)
    if driver is None:raise HTTPException(404,"Motorista não encontrado.")
    require_branch_access(db,user,driver.branch_id)
    if data.route_id:
        route=db.get(Route,data.route_id)
        if route is None or route.branch_id!=driver.branch_id:raise HTTPException(422,"Rota inválida para o motorista.")
    row=DriverStatementAdjustment(branch_id=driver.branch_id,driver_id=driver.id,route_id=data.route_id,entry_date=data.entry_date,kind=data.kind,reason=data.reason,amount=data.amount,notes=data.notes,created_by=user.id)
    db.add(row);db.flush();log(db,user_id=user.id,action="create",entity="driver_statement_adjustment",entity_id=row.id,detail=f"motorista={driver.id}; tipo={row.kind}; valor={row.amount}; motivo={row.reason}");db.commit();db.refresh(row);return row

@router.post("/driver-adjustments/{adjustment_id}/void",dependencies=[Depends(_FINANCE_MANAGE)])
def void_driver_adjustment(adjustment_id:int,reason:str,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    row=db.get(DriverStatementAdjustment,adjustment_id)
    if row is None:raise HTTPException(404,"Lançamento não encontrado.")
    require_branch_access(db,user,row.branch_id)
    if row.voided:raise HTTPException(409,"Lançamento já estornado.")
    if len(reason.strip())<3:raise HTTPException(422,"Informe o motivo do estorno.")
    row.voided=True;row.voided_by=user.id;row.voided_at=datetime.now(timezone.utc);row.void_reason=reason.strip();log(db,user_id=user.id,action="void",entity="driver_statement_adjustment",entity_id=row.id,detail=reason);db.commit();return {"voided":adjustment_id}

def _driver_statement_data(driver_id:int,start:date,end:date,db:Session,user:User):
    driver=db.get(Driver,driver_id)
    if driver is None:raise HTTPException(404,"Motorista não encontrado.")
    require_branch_access(db,user,driver.branch_id)
    routes=db.scalars(select(Route).where(Route.driver_id==driver_id,Route.route_date>=start,Route.route_date<=end,Route.status=="finalizada",Route.excluded.is_(False)).order_by(Route.route_date,Route.id)).all()
    rows=[]
    if driver.employment_type=="agregado":
        rows += [{"id":f"route-{route.id}","date":route.route_date,"kind":"earning","reason":route.driver_payment_notes or "Pagamento negociado da rota","notes":route.driver_payment_notes,"route":route.codigo_ut,"amount":float(route.driver_payment_amount)} for route in routes if route.driver_payment_amount is not None]
    else:
        route_days={route.route_date for route in routes}
        rows += [{"id":f"daily-{day.isoformat()}","date":day,"kind":"earning","reason":"Diária de motorista próprio","notes":None,"route":", ".join(route.codigo_ut for route in routes if route.route_date==day),"amount":float(driver.daily_rate or 0)} for day in sorted(route_days)]
    stmt=select(DriverStatementAdjustment,Route.codigo_ut).outerjoin(Route,Route.id==DriverStatementAdjustment.route_id).where(DriverStatementAdjustment.driver_id==driver_id,DriverStatementAdjustment.entry_date>=start,DriverStatementAdjustment.entry_date<=end,DriverStatementAdjustment.voided.is_(False)).order_by(DriverStatementAdjustment.entry_date,DriverStatementAdjustment.id)
    rows += [{"id":f"adjustment-{row.id}","date":row.entry_date,"kind":row.kind,"reason":row.reason,"notes":row.notes,"route":code,"amount":float(row.amount)} for row,code in db.execute(stmt).all()]
    rows.sort(key=lambda row:(row["date"],str(row["id"])))
    earnings=sum(r["amount"] for r in rows if r["kind"]=="earning");deductions=sum(r["amount"] for r in rows if r["kind"]=="deduction")
    return driver,rows,earnings,deductions

@router.get("/driver-statement",dependencies=[Depends(_FINANCE)])
def driver_statement(driver_id:int,start:date,end:date,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    driver,rows,earnings,deductions=_driver_statement_data(driver_id,start,end,db,user)
    pending_routes=0
    if driver.employment_type=="agregado":pending_routes=db.scalar(select(func.count(Route.id)).where(Route.driver_id==driver.id,Route.route_date>=start,Route.route_date<=end,Route.status=="finalizada",Route.excluded.is_(False),Route.driver_payment_amount.is_(None))) or 0
    return {"driver":{"id":driver.id,"name":driver.name,"employment_type":driver.employment_type,"daily_rate":float(driver.daily_rate) if driver.daily_rate is not None else None},"start":start,"end":end,"earnings":earnings,"deductions":deductions,"net":earnings-deductions,"pending_routes":pending_routes,"daily_rate_missing":driver.employment_type=="proprio" and driver.daily_rate is None,"rows":rows}

def _period_out(period: DriverStatementPeriod):
    snapshot=json.loads(period.snapshot_json)
    return {"id":period.id,"driver_id":period.driver_id,"period_start":period.period_start,"period_end":period.period_end,"release_date":period.release_date,"status":period.status,"version":period.version,"snapshot_hash":period.snapshot_hash,"snapshot":snapshot,"contest":{"scope":period.contested_scope,"item_id":period.contested_item_id,"reason":period.contest_reason} if period.contest_reason else None,"accepted_at":period.accepted_at,"signature_name":period.signature_name,"payable_id":period.payable_id}

def _snapshot(driver: Driver, rows: list[dict], earnings: float, deductions: float) -> tuple[str,str]:
    payload={"driver":{"id":driver.id,"name":driver.name,"document":driver.document,"employment_type":driver.employment_type},"rows":[{**row,"date":row["date"].isoformat()} for row in rows],"earnings":round(earnings,2),"deductions":round(deductions,2),"net":round(earnings-deductions,2)}
    raw=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":"));return raw,hashlib.sha256(raw.encode("utf-8")).hexdigest()

class PeriodReleaseIn(BaseModel):
    driver_id:int;start:date;end:date

@router.post("/driver-statement-periods/release",dependencies=[Depends(_FINANCE_MANAGE)])
def release_driver_statement(data:PeriodReleaseIn,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    driver,rows,earnings,deductions=_driver_statement_data(data.driver_id,data.start,data.end,db,user)
    if earnings-deductions<=0:raise HTTPException(422,"O extrato não possui líquido positivo para liberação.")
    config=db.scalar(select(DriverSettings).where(DriverSettings.tenant_id==user.tenant_id)) or DriverSettings(tenant_id=user.tenant_id)
    if config.id is None:db.add(config);db.flush()
    next_month=(data.end.replace(day=1)+__import__('dateutil.relativedelta',fromlist=['relativedelta']).relativedelta(months=1))
    release_date=next_month.replace(day=min(config.statement_release_day,28))
    raw,digest=_snapshot(driver,rows,earnings,deductions)
    period=db.scalar(select(DriverStatementPeriod).where(DriverStatementPeriod.driver_id==driver.id,DriverStatementPeriod.period_start==data.start,DriverStatementPeriod.period_end==data.end))
    if period and period.status=="accepted":raise HTTPException(409,"Este extrato já foi aceito pelo motorista.")
    if period is None:
        period=DriverStatementPeriod(tenant_id=user.tenant_id,branch_id=driver.branch_id,driver_id=driver.id,period_start=data.start,period_end=data.end,release_date=release_date,status="released",snapshot_json=raw,snapshot_hash=digest,released_by=user.id)
        db.add(period)
    else:
        period.snapshot_json=raw;period.snapshot_hash=digest;period.version+=1;period.release_date=release_date;period.status="released";period.released_by=user.id;period.released_at=datetime.now(timezone.utc);period.contested_scope=None;period.contested_item_id=None;period.contest_reason=None
    db.commit();db.refresh(period);return _period_out(period)

def _driver_for_portal(db:Session,user:User)->Driver:
    driver=db.scalar(select(Driver).where(Driver.user_id==user.id,Driver.active.is_(True)))
    if driver is None:raise HTTPException(403,"Seu usuário não está vinculado a um motorista ativo.")
    return driver

@router.get("/driver-statement-periods/my")
def my_driver_statement_periods(db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    driver=_driver_for_portal(db,user)
    rows=db.scalars(select(DriverStatementPeriod).where(DriverStatementPeriod.driver_id==driver.id).order_by(DriverStatementPeriod.period_end.desc())).all()
    return [_period_out(row) for row in rows]

class PeriodContestIn(BaseModel):
    scope:str;item_id:str|None=None;reason:str=Field(min_length=10,max_length=3000)

@router.post("/driver-statement-periods/{period_id}/contest")
def contest_driver_statement(period_id:int,data:PeriodContestIn,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    driver=_driver_for_portal(db,user);period=db.get(DriverStatementPeriod,period_id)
    if period is None or period.driver_id!=driver.id:raise HTTPException(404,"Extrato não encontrado.")
    if period.status!="released":raise HTTPException(409,"Este extrato não está disponível para contestação.")
    if date.today()<period.release_date:raise HTTPException(409,f"O aceite será liberado em {period.release_date:%d/%m/%Y}.")
    if data.scope not in {"total","item"} or (data.scope=="item" and not data.item_id):raise HTTPException(422,"Informe se a contestação é total ou de um item.")
    if data.item_id and not any(str(row["id"])==data.item_id for row in json.loads(period.snapshot_json)["rows"]):raise HTTPException(422,"Item do extrato não encontrado.")
    period.status="contested";period.contested_scope=data.scope;period.contested_item_id=data.item_id;period.contest_reason=data.reason.strip();period.contested_at=datetime.now(timezone.utc)
    task=db.scalar(select(WorkflowTask).where(WorkflowTask.source_type=="driver_statement",WorkflowTask.source_id==period.id))
    action="reopened" if task else "created"
    if task:
        task.description=data.reason.strip();task.current_department="Financeiro";task.current_assignee_id=None;task.status="open";task.source_status="contested";task.priority=0;task.resolution=None
    else:
        task=WorkflowTask(tenant_id=period.tenant_id,branch_id=period.branch_id,source_type="driver_statement",source_id=period.id,title=f"Contestação prioritária do extrato · {driver.name}",description=data.reason.strip(),requester_id=user.id,current_department="Financeiro",status="open",source_status="contested",priority=0);db.add(task);db.flush()
    db.add(WorkflowTaskEvent(task_id=task.id,actor_id=user.id,action=action,to_department="Financeiro",to_status="open",note=f"Contestação {data.scope}; item={data.item_id or 'total'}"));db.commit();return {"status":"contested","task_id":task.id}

class PeriodAcceptIn(BaseModel):
    signature_name:str=Field(min_length=3,max_length=180);document:str=Field(min_length=5,max_length=40);declaration_accepted:bool

@router.post("/driver-statement-periods/{period_id}/accept")
def accept_driver_statement(period_id:int,data:PeriodAcceptIn,request:Request,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    driver=_driver_for_portal(db,user);period=db.get(DriverStatementPeriod,period_id)
    if period is None or period.driver_id!=driver.id:raise HTTPException(404,"Extrato não encontrado.")
    if period.status!="released":raise HTTPException(409,"Extrato bloqueado ou já finalizado.")
    if date.today()<period.release_date:raise HTTPException(409,f"O aceite será liberado em {period.release_date:%d/%m/%Y}.")
    if not data.declaration_accepted:raise HTTPException(422,"Confirme a declaração de aceite e assinatura eletrônica.")
    snapshot=json.loads(period.snapshot_json);net=float(snapshot["net"])
    account=FinancialAccount(tenant_id=period.tenant_id,branch_id=period.branch_id,kind="payable",description=f"Extrato aceito · {driver.name} · {period.period_start:%d/%m/%Y} a {period.period_end:%d/%m/%Y}",counterparty=driver.name,category="diaria_motorista",document=f"ACEITE-{period.id}-V{period.version}",issue_date=date.today(),due_date=date.today(),amount=net,status="pendente",notes=f"Aceite eletrônico; hash={period.snapshot_hash}",created_by=user.id,driver_id=driver.id,payment_period_start=period.period_start,payment_period_end=period.period_end)
    db.add(account);db.flush();period.status="accepted";period.accepted_at=datetime.now(timezone.utc);period.accepted_by_user_id=user.id;period.signature_name=data.signature_name.strip();period.signature_document=data.document.strip();period.signature_ip=request.client.host if request.client else None;period.signature_user_agent=request.headers.get("user-agent");period.signature_declaration="Declaro que conferi o extrato, reconheço os itens e valores apresentados e aceito o valor líquido para pagamento.";period.payable_id=account.id
    log(db,user_id=user.id,action="electronic_acceptance",entity="driver_statement_period",entity_id=period.id,detail=f"hash={period.snapshot_hash}; conta={account.id}; ip={period.signature_ip}");db.commit();return {"status":"accepted","payable_id":account.id,"snapshot_hash":period.snapshot_hash}

class PeriodResolveIn(BaseModel):
    adjustment_type:str;amount:float=Field(gt=0);reason:str=Field(min_length=5,max_length=1000)

@router.post("/driver-statement-periods/{period_id}/resolve",dependencies=[Depends(_FINANCE_MANAGE)])
def resolve_driver_statement(period_id:int,data:PeriodResolveIn,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    period=db.get(DriverStatementPeriod,period_id)
    if period is None:raise HTTPException(404,"Extrato não encontrado.")
    require_branch_access(db,user,period.branch_id)
    if period.status!="contested":raise HTTPException(409,"O extrato não possui contestação pendente.")
    if data.adjustment_type not in {"complement","deduction"}:raise HTTPException(422,"Escolha complemento ou desconto.")
    kind="earning" if data.adjustment_type=="complement" else "deduction"
    route_id=None
    if period.contested_item_id:
        contested=next((row for row in json.loads(period.snapshot_json)["rows"] if str(row["id"])==period.contested_item_id),None)
        if contested and contested.get("route"):
            code=str(contested["route"]).split(",",1)[0].strip();route_id=db.scalar(select(Route.id).where(Route.codigo_ut==code,Route.driver_id==period.driver_id))
    db.add(DriverStatementAdjustment(tenant_id=period.tenant_id,branch_id=period.branch_id,driver_id=period.driver_id,route_id=route_id,entry_date=period.period_end,kind=kind,reason=data.reason.strip(),amount=data.amount,notes=f"Ajuste da contestação do extrato #{period.id}.",created_by=user.id))
    db.flush();driver,rows,earnings,deductions=_driver_statement_data(period.driver_id,period.period_start,period.period_end,db,user);raw,digest=_snapshot(driver,rows,earnings,deductions)
    period.snapshot_json=raw;period.snapshot_hash=digest;period.version+=1;period.status="released";period.released_by=user.id;period.released_at=datetime.now(timezone.utc)
    task=db.scalar(select(WorkflowTask).where(WorkflowTask.source_type=="driver_statement",WorkflowTask.source_id==period.id))
    if task:
        old=task.status;task.status="returned";task.resolution=data.reason.strip();task.returned_at=datetime.now(timezone.utc);task.current_assignee_id=task.requester_id;db.add(WorkflowTaskEvent(task_id=task.id,actor_id=user.id,action="returned",from_department="Financeiro",to_department="Solicitante",from_status=old,to_status="returned",note=f"Ajuste {data.adjustment_type}: R$ {data.amount:.2f}. {data.reason}"))
    log(db,user_id=user.id,action="resolve_contest",entity="driver_statement_period",entity_id=period.id,detail=f"tipo={data.adjustment_type}; valor={data.amount}; versao={period.version}");db.commit();return _period_out(period)

@router.get("/driver-statement.pdf",dependencies=[Depends(_FINANCE)])
def driver_statement_pdf(driver_id:int,start:date,end:date,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph,SimpleDocTemplate,Spacer,Table,TableStyle
    driver,rows,earnings,deductions=_driver_statement_data(driver_id,start,end,db,user);output=io.BytesIO();doc=SimpleDocTemplate(output,pagesize=A4,rightMargin=15*mm,leftMargin=15*mm,topMargin=15*mm,bottomMargin=15*mm);styles=getSampleStyleSheet();story=[Paragraph("Extrato do motorista",styles["Title"]),Paragraph(f"{driver.name} · período de {start.strftime('%d/%m/%Y')} a {end.strftime('%d/%m/%Y')}",styles["Normal"]),Spacer(1,6*mm)]
    table=[["Data","Tipo","Descrição","Rota","Valor"]]+[[r["date"].strftime("%d/%m/%Y"),"Ganho" if r["kind"]=="earning" else "Desconto",r["reason"],r["route"] or "-",f"R$ {r['amount']:,.2f}"] for r in rows]
    table += [["","","Total de ganhos","",f"R$ {earnings:,.2f}"],["","","Total de descontos","",f"R$ {deductions:,.2f}"],["","","Líquido","",f"R$ {earnings-deductions:,.2f}"]]
    view=Table(table,colWidths=[25*mm,25*mm,70*mm,25*mm,30*mm],repeatRows=1);view.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#0f766e")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),.25,colors.grey),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("ALIGN",(-1,1),(-1,-1),"RIGHT"),("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#dcfce7"))]));story += [view,Spacer(1,12*mm),Paragraph("Declaro ciência dos créditos e descontos apresentados.",styles["Normal"]),Spacer(1,12*mm),Paragraph("____________________________________<br/>Assinatura do motorista",styles["Normal"])];doc.build(story);output.seek(0)
    return StreamingResponse(output,media_type="application/pdf",headers={"Content-Disposition":f'attachment; filename="extrato-motorista-{driver.id}-{start}-{end}.pdf"'})

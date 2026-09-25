"""Importação de rotas via planilha — modelo padrão (.xlsx/.csv), qualquer cliente."""
import io
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import Role, require_branch_access, require_roles
from app.core.config import settings
from app.db.models import Branch, Carrier, CarrierBranch, User
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services.audit import log
from app.services.generic_route_import import import_generic_routes
from app.services.import_changes import ImportConfirmationRequired
from app.workers.celery_app import optimize_imported_routes
from app.services.adimax_route_import import import_adimax_routes, is_adimax_workbook
from app.services.jm_load_import import build_jm_template_xlsx, import_jm_loads, is_jm_load_workbook

router = APIRouter(prefix="/routes-import", tags=["routes-import"])
logger = logging.getLogger(__name__)

_MANAGER = require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL, Role.OPERADOR_LOGISTICO)

ALLOWED_EXTENSIONS = (".xlsx", ".xlsm", ".csv")


def _resolve_import_branch(db: Session, user: User) -> int:
    """Usa a filial do usuário ou a única unidade ativa da sua empresa."""
    if user.branch_id is not None:
        require_branch_access(db, user, user.branch_id)
        return user.branch_id
    if user.tenant_id is None:
        raise HTTPException(status_code=409, detail="Usuário sem empresa associada para importar rotas.")
    branch_ids = list(db.scalars(
        select(Branch.id).where(Branch.tenant_id == user.tenant_id, Branch.active.is_(True)).order_by(Branch.id)
    ).all())
    if not branch_ids:
        raise HTTPException(status_code=409, detail="A empresa não possui uma filial ativa para importar rotas.")
    if len(branch_ids) > 1:
        raise HTTPException(status_code=409, detail="A empresa possui mais de uma filial ativa. Selecione a unidade da importação.")
    return branch_ids[0]


class ImportResult(BaseModel):
    rows_read: int
    routes_created: int
    routes_updated: int
    stops_created: int
    stops_updated: int
    routes_optimized: int
    routing_errors: int
    route_ids: list[int]
    errors: list[str]
    drivers_created: int = 0
    vehicles_created: int = 0
    customers_created: int = 0
    destinations_created: int = 0
    origins_created: int = 0
    carrier_pending: int = 0


@router.get("/template.xlsx", dependencies=[Depends(_MANAGER)])
def download_template(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    branch_id = _resolve_import_branch(db, user)
    carriers = db.execute(
        select(Carrier.id, Carrier.name)
        .join(CarrierBranch, CarrierBranch.carrier_id == Carrier.id)
        .where(CarrierBranch.branch_id == branch_id, CarrierBranch.active.is_(True), Carrier.active.is_(True))
        .order_by(Carrier.name)
    ).all()
    output = build_jm_template_xlsx([(row.id, row.name) for row in carriers])
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="modelo-importacao-cargas-jm.xlsx"'},
    )


@router.post("/upload", response_model=ImportResult)
async def upload_routes(file: UploadFile = File(...), confirm_overwrite: bool = Form(False), db: Session = Depends(get_db), user: User = Depends(_MANAGER)):
    filename = file.filename or ""
    if not filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(status_code=415, detail="Envie um arquivo .xlsx ou .csv.")
    branch_id = _resolve_import_branch(db, user)
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Arquivo acima de {settings.max_upload_mb} MB.")
    try:
        source = io.BytesIO(data)
        if filename.lower().endswith((".xlsx", ".xlsm")) and is_adimax_workbook(source):
            stats = import_adimax_routes(source, branch_id=branch_id, confirmed=confirm_overwrite, user_id=user.id)
        elif filename.lower().endswith((".xlsx", ".xlsm")) and is_jm_load_workbook(source):
            stats = import_jm_loads(source, branch_id=branch_id, confirmed=confirm_overwrite, user_id=user.id)
        else:
            stats = import_generic_routes(source, filename, branch_id=branch_id, confirmed=confirm_overwrite, user_id=user.id)
    except ImportConfirmationRequired as exc:
        raise HTTPException(status_code=409, detail={
            "code": "import_confirmation_required", "total": len(exc.changes),
            "changes": exc.changes[:5],
            "message": "Foram encontradas diferenças. Autorize a sobreposição para continuar.",
        })
    except Exception as exc:  # noqa: BLE001 — erro de leitura/parsing da planilha do usuário
        raise HTTPException(status_code=422, detail=f"Não foi possível ler a planilha: {exc}")
    log(db, user_id=user.id, action="import", entity="routes",
        detail=f"Importação via planilha: {stats['routes_created']} rotas criadas, {stats['routes_updated']} atualizadas.")
    db.commit()
    if stats["route_ids"]:
        try:
            optimize_imported_routes.delay(list(dict.fromkeys(stats["route_ids"])))
        except Exception:  # a planilha já foi gravada; indisponibilidade da fila não desfaz o trabalho
            logger.exception("Não foi possível enfileirar a atualização dos mapas importados")
    return ImportResult(**stats)

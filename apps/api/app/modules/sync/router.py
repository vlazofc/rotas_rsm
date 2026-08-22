"""Sincronização manual de fontes externas (planilha Torre de Controle no SharePoint)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import Role, require_roles
from app.db.models import AuditLog, Branch, User
from app.db.session import get_db
from app.services.audit import log
from app.workers.celery_app import sync_torre_controle

router = APIRouter(prefix="/sync", tags=["sync"])


class TorreControleSyncIn(BaseModel):
    branch_id: int | None = None


@router.get("/torre-controle/status")
def torre_controle_status(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL)),
):
    last = db.scalar(
        select(AuditLog)
        .where(AuditLog.action == "sync", AuditLog.entity == "torre_controle")
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    branch = db.get(Branch, settings.sharepoint_sync_branch_id) if settings.sharepoint_sync_branch_id else None
    return {
        "configured": settings.sharepoint_configured,
        "last_run_at": last.created_at if last else None,
        "last_run_detail": last.detail if last else None,
        "default_branch_id": settings.sharepoint_sync_branch_id,
        "default_branch_name": branch.name if branch else None,
    }


@router.post("/torre-controle")
def trigger_torre_controle_sync(
    data: TorreControleSyncIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL)),
):
    """Dispara a sincronização agora (botão "Sincronizar agora" no painel).

    Roda em segundo plano via Celery quando o worker estiver disponível;
    aqui apenas registramos o disparo e devolvemos imediatamente — o
    resultado fica disponível em GET /sync/torre-controle/status.
    `branch_id` é opcional: sem ele, usa o destino padrão (SHAREPOINT_SYNC_BRANCH_ID).
    """
    if not settings.sharepoint_configured:
        return {"queued": False, "detail": "Integração com SharePoint não configurada."}
    branch_id = data.branch_id or settings.sharepoint_sync_branch_id
    if branch_id is None:
        return {"queued": False, "detail": "Selecione a filial de destino da sincronização."}
    if db.get(Branch, branch_id) is None:
        return {"queued": False, "detail": "Filial de destino não encontrada."}
    sync_torre_controle.delay(branch_id=branch_id)
    log(db, user_id=user.id, action="sync", entity="torre_controle", detail=f"Disparado manualmente. branch_id={branch_id}")
    db.commit()
    return {"queued": True}

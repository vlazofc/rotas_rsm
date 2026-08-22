"""Motivos de falha de entrega (lista gerenciável usada na tela de entrega)."""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import Role, require_roles
from app.db.models import DeliveryFailureReason, RouteStop, User
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services.audit import log, log_update, snapshot

router = APIRouter(prefix="/failure-reasons", tags=["failure-reasons"])

_MANAGER = require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL)


class ReasonIn(BaseModel):
    label: str
    label_pt_br: str | None = None
    sort_order: int = 100


class ReasonUpdate(BaseModel):
    label: str | None = None
    label_pt_br: str | None = None
    sort_order: int | None = None
    active: bool | None = None


class ReasonOut(BaseModel):
    id: int
    code: str
    label: str
    label_pt_br: str | None = None
    sort_order: int
    active: bool

    class Config:
        from_attributes = True


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")
    return slug or "motivo"


@router.get("", response_model=list[ReasonOut])
def list_reasons(only_active: bool = False, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """Lista os motivos. only_active=true para a tela de entrega."""
    stmt = select(DeliveryFailureReason)
    if only_active:
        stmt = stmt.where(DeliveryFailureReason.active.is_(True))
    return db.scalars(stmt.order_by(DeliveryFailureReason.sort_order, DeliveryFailureReason.label)).all()


@router.post("", response_model=ReasonOut, dependencies=[Depends(_MANAGER)])
def create_reason(data: ReasonIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    base = _slugify(data.label)
    code, n = base, 2
    while db.scalar(select(DeliveryFailureReason).where(DeliveryFailureReason.code == code)):
        code, n = f"{base}_{n}", n + 1
    reason = DeliveryFailureReason(code=code, label=data.label, label_pt_br=data.label_pt_br, sort_order=data.sort_order)
    db.add(reason)
    db.flush()
    log(db, user_id=actor.id, action="create", entity="failure_reason", entity_id=reason.id)
    db.commit()
    db.refresh(reason)
    return reason


@router.put("/{reason_id}", response_model=ReasonOut, dependencies=[Depends(_MANAGER)])
def update_reason(reason_id: int, data: ReasonUpdate,
                  db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    reason = db.get(DeliveryFailureReason, reason_id)
    if reason is None:
        raise HTTPException(status_code=404, detail="Motivo não encontrado.")
    updates = data.model_dump(exclude_unset=True)
    before = snapshot(reason, list(updates))
    for field, value in updates.items():
        setattr(reason, field, value)
    log_update(db, user_id=actor.id, entity="failure_reason", entity_id=reason.id, before=before, obj=reason, updates=updates)
    db.commit()
    db.refresh(reason)
    return reason


@router.delete("/{reason_id}", dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL))])
def delete_reason(reason_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    reason = db.get(DeliveryFailureReason, reason_id)
    if reason is None:
        raise HTTPException(status_code=404, detail="Motivo não encontrado.")
    if db.scalar(select(RouteStop).where(RouteStop.failure_reason_id == reason_id)):
        raise HTTPException(status_code=409, detail="Motivo já foi usado em parada com falha. Inative para manter o histórico.")
    label = reason.label
    db.delete(reason)
    log(db, user_id=actor.id, action="delete", entity="failure_reason", entity_id=reason_id, detail=f'label: "{label}"')
    db.commit()
    return {"deleted": reason_id}

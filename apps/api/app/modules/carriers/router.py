"""Transportadoras — fornecedores de motoristas/veículos de cada cliente."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import Role, require_roles
from app.db.models import Carrier, Driver, Tenant, User
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services.audit import log, log_update, snapshot

router = APIRouter(prefix="/carriers", tags=["carriers"])

_MANAGER = require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL)


class CarrierIn(BaseModel):
    name: str
    document: str | None = None
    tenant_id: int | None = None  # admin_global pode cadastrar para qualquer cliente


class CarrierUpdate(BaseModel):
    name: str | None = None
    document: str | None = None
    active: bool | None = None


class CarrierOut(BaseModel):
    id: int
    tenant_id: int | None
    name: str
    document: str | None
    active: bool

    class Config:
        from_attributes = True


@router.get("", response_model=list[CarrierOut])
def list_carriers(
    only_active: bool = False, tenant_id: int | None = None,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    stmt = select(Carrier)
    if user.role == Role.ADMIN_GLOBAL.value:
        if tenant_id is not None:
            stmt = stmt.where(Carrier.tenant_id == tenant_id)
    else:
        stmt = stmt.where(Carrier.tenant_id == user.tenant_id)
    if only_active:
        stmt = stmt.where(Carrier.active.is_(True))
    return db.scalars(stmt.order_by(Carrier.name)).all()


@router.post("", response_model=CarrierOut, dependencies=[Depends(_MANAGER)])
def create_carrier(data: CarrierIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    tenant_id = data.tenant_id if actor.role == Role.ADMIN_GLOBAL.value else actor.tenant_id
    if tenant_id is None or db.get(Tenant, tenant_id) is None:
        raise HTTPException(status_code=422, detail="Selecione uma empresa válida.")
    carrier = Carrier(name=data.name, document=data.document, tenant_id=tenant_id)
    db.add(carrier)
    db.flush()
    log(db, user_id=actor.id, action="create", entity="carrier", entity_id=carrier.id)
    db.commit()
    db.refresh(carrier)
    return carrier


@router.put("/{carrier_id}", response_model=CarrierOut, dependencies=[Depends(_MANAGER)])
def update_carrier(carrier_id: int, data: CarrierUpdate,
                    db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    carrier = db.get(Carrier, carrier_id)
    if carrier is None:
        raise HTTPException(status_code=404, detail="Transportadora não encontrada.")
    if actor.role != Role.ADMIN_GLOBAL.value and carrier.tenant_id != actor.tenant_id:
        raise HTTPException(status_code=403, detail="Transportadora de outro cliente.")
    updates = data.model_dump(exclude_unset=True)
    before = snapshot(carrier, list(updates))
    for field, value in updates.items():
        setattr(carrier, field, value)
    log_update(db, user_id=actor.id, entity="carrier", entity_id=carrier.id, before=before, obj=carrier, updates=updates)
    db.commit()
    db.refresh(carrier)
    return carrier


@router.delete("/{carrier_id}", dependencies=[Depends(_MANAGER)])
def delete_carrier(carrier_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    carrier = db.get(Carrier, carrier_id)
    if carrier is None:
        raise HTTPException(status_code=404, detail="Transportadora não encontrada.")
    if actor.role != Role.ADMIN_GLOBAL.value and carrier.tenant_id != actor.tenant_id:
        raise HTTPException(status_code=403, detail="Transportadora de outro cliente.")
    if db.scalar(select(Driver).where(Driver.carrier_id == carrier_id)):
        raise HTTPException(status_code=409, detail="Transportadora em uso por motorista. Inative para manter o histórico.")
    name = carrier.name
    db.delete(carrier)
    log(db, user_id=actor.id, action="delete", entity="carrier", entity_id=carrier_id, detail=f'name: "{name}"')
    db.commit()
    return {"deleted": carrier_id}

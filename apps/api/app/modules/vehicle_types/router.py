"""Tipologias de veículo (lista gerenciável usada no cadastro de veículos)."""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import Role, require_roles
from app.db.models import User, Vehicle, VehicleType
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services.audit import log, log_update, snapshot

router = APIRouter(prefix="/vehicle-types", tags=["vehicle-types"])

_MANAGER = require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL)


class VehicleTypeIn(BaseModel):
    label: str
    label_pt_br: str | None = None
    sort_order: int = 100


class VehicleTypeUpdate(BaseModel):
    label: str | None = None
    label_pt_br: str | None = None
    sort_order: int | None = None
    active: bool | None = None


class VehicleTypeOut(BaseModel):
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
    return slug or "tipo"


@router.get("", response_model=list[VehicleTypeOut])
def list_vehicle_types(only_active: bool = False, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    """Lista as tipologias. only_active=true para o cadastro de veículos."""
    stmt = select(VehicleType)
    if only_active:
        stmt = stmt.where(VehicleType.active.is_(True))
    return db.scalars(stmt.order_by(VehicleType.sort_order, VehicleType.label)).all()


@router.post("", response_model=VehicleTypeOut, dependencies=[Depends(_MANAGER)])
def create_vehicle_type(data: VehicleTypeIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    base = _slugify(data.label)
    code, n = base, 2
    while db.scalar(select(VehicleType).where(VehicleType.code == code)):
        code, n = f"{base}_{n}", n + 1
    vtype = VehicleType(code=code, label=data.label, label_pt_br=data.label_pt_br, sort_order=data.sort_order)
    db.add(vtype)
    db.flush()
    log(db, user_id=actor.id, action="create", entity="vehicle_type", entity_id=vtype.id)
    db.commit()
    db.refresh(vtype)
    return vtype


@router.put("/{vehicle_type_id}", response_model=VehicleTypeOut, dependencies=[Depends(_MANAGER)])
def update_vehicle_type(vehicle_type_id: int, data: VehicleTypeUpdate,
                        db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    vtype = db.get(VehicleType, vehicle_type_id)
    if vtype is None:
        raise HTTPException(status_code=404, detail="Tipologia não encontrada.")
    updates = data.model_dump(exclude_unset=True)
    before = snapshot(vtype, list(updates))
    for field, value in updates.items():
        setattr(vtype, field, value)
    log_update(db, user_id=actor.id, entity="vehicle_type", entity_id=vtype.id, before=before, obj=vtype, updates=updates)
    db.commit()
    db.refresh(vtype)
    return vtype


@router.delete("/{vehicle_type_id}", dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL))])
def delete_vehicle_type(vehicle_type_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    vtype = db.get(VehicleType, vehicle_type_id)
    if vtype is None:
        raise HTTPException(status_code=404, detail="Tipologia não encontrada.")
    if db.scalar(select(Vehicle).where(Vehicle.vehicle_type_id == vehicle_type_id)):
        raise HTTPException(status_code=409, detail="Tipologia em uso por veículo. Inative para manter o histórico.")
    label = vtype.label
    db.delete(vtype)
    log(db, user_id=actor.id, action="delete", entity="vehicle_type", entity_id=vehicle_type_id, detail=f'label: "{label}"')
    db.commit()
    return {"deleted": vehicle_type_id}

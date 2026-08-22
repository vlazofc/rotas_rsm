from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import Role, require_branch_access, require_roles, require_same_branch
from app.db.models import Route, User, Vehicle, VehicleType
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services.audit import log, log_update, snapshot

router = APIRouter(prefix="/vehicles", tags=["vehicles"])

_MANAGER = require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL)


class VehicleIn(BaseModel):
    branch_id: int
    plate: str
    description: str | None = None
    vehicle_type_id: int | None = None
    temperature_controlled: bool = False


class VehicleUpdate(BaseModel):
    plate: str | None = None
    description: str | None = None
    vehicle_type_id: int | None = None
    temperature_controlled: bool | None = None
    active: bool | None = None


class VehicleOut(VehicleIn):
    id: int
    active: bool
    vehicle_type_code: str | None = None
    vehicle_type_label: str | None = None

    class Config:
        from_attributes = True


@router.get("", response_model=list[VehicleOut])
def list_vehicles(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(Vehicle).order_by(Vehicle.plate)
    if user.role != Role.ADMIN_GLOBAL.value and user.branch_id:
        stmt = stmt.where(Vehicle.branch_id == user.branch_id)
    vehicles = db.scalars(stmt).all()
    result = []
    for v in vehicles:
        out = VehicleOut.model_validate(v)
        if v.vehicle_type_id:
            vt = db.get(VehicleType, v.vehicle_type_id)
            if vt:
                out.vehicle_type_code = vt.code
                out.vehicle_type_label = vt.label_pt_br or vt.label
        result.append(out)
    return result


@router.post("", response_model=VehicleOut, dependencies=[Depends(_MANAGER)])
def create_vehicle(data: VehicleIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    require_branch_access(db, actor, data.branch_id)
    vehicle = Vehicle(**data.model_dump())
    db.add(vehicle)
    db.flush()
    log(db, user_id=actor.id, action="create", entity="vehicle", entity_id=vehicle.id)
    db.commit()
    db.refresh(vehicle)
    return vehicle


@router.put("/{vehicle_id}", response_model=VehicleOut, dependencies=[Depends(_MANAGER)])
def update_vehicle(vehicle_id: int, data: VehicleUpdate,
                   db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Veículo não encontrado.")
    require_same_branch(actor, vehicle.branch_id)
    updates = data.model_dump(exclude_unset=True)
    before = snapshot(vehicle, list(updates))
    for field, value in updates.items():
        setattr(vehicle, field, value)
    log_update(db, user_id=actor.id, entity="vehicle", entity_id=vehicle.id, before=before, obj=vehicle, updates=updates)
    db.commit()
    db.refresh(vehicle)
    return vehicle


@router.delete("/{vehicle_id}", dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL))])
def delete_vehicle(vehicle_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Veículo não encontrado.")
    if db.scalar(select(Route).where(Route.vehicle_id == vehicle_id)):
        raise HTTPException(status_code=409, detail="Veículo possui rota atribuída. Inative para manter o histórico.")
    plate = vehicle.plate
    db.delete(vehicle)
    log(db, user_id=actor.id, action="delete", entity="vehicle", entity_id=vehicle_id, detail=f'plate: "{plate}"')
    db.commit()
    return {"deleted": vehicle_id}

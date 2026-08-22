from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import Role, require_branch_access, require_roles, require_same_branch
from app.db.models import Carrier, Driver, Route, User
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services.audit import log, log_update, snapshot

router = APIRouter(prefix="/drivers", tags=["drivers"])

_MANAGER = require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL)


class DriverIn(BaseModel):
    branch_id: int
    name: str
    document: str | None = None
    phone: str | None = None
    carrier: str | None = None
    carrier_id: int | None = None
    user_id: int | None = None


class DriverUpdate(BaseModel):
    name: str | None = None
    document: str | None = None
    phone: str | None = None
    carrier: str | None = None
    carrier_id: int | None = None
    user_id: int | None = None
    active: bool | None = None


class DriverOut(DriverIn):
    id: int
    active: bool

    class Config:
        from_attributes = True


@router.get("", response_model=list[DriverOut])
def list_drivers(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(Driver).order_by(Driver.name)
    if user.role != Role.ADMIN_GLOBAL.value and user.branch_id:
        stmt = stmt.where(Driver.branch_id == user.branch_id)
    return db.scalars(stmt).all()


@router.post("", response_model=DriverOut, dependencies=[Depends(_MANAGER)])
def create_driver(data: DriverIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    branch = require_branch_access(db, actor, data.branch_id)
    if data.carrier_id is not None:
        carrier = db.get(Carrier, data.carrier_id)
        if carrier is None or carrier.tenant_id != branch.tenant_id:
            raise HTTPException(status_code=422, detail="Transportadora não pertence à empresa da filial.")
    if data.user_id is not None:
        linked_user = db.get(User, data.user_id)
        if linked_user is None or linked_user.tenant_id != branch.tenant_id:
            raise HTTPException(status_code=422, detail="Usuário não pertence à empresa da filial.")
    driver = Driver(**data.model_dump())
    db.add(driver)
    db.flush()
    log(db, user_id=actor.id, action="create", entity="driver", entity_id=driver.id)
    db.commit()
    db.refresh(driver)
    return driver


@router.put("/{driver_id}", response_model=DriverOut, dependencies=[Depends(_MANAGER)])
def update_driver(driver_id: int, data: DriverUpdate,
                  db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    driver = db.get(Driver, driver_id)
    if driver is None:
        raise HTTPException(status_code=404, detail="Motorista não encontrado.")
    require_same_branch(actor, driver.branch_id)
    updates = data.model_dump(exclude_unset=True)
    if data.carrier_id is not None:
        carrier = db.get(Carrier, data.carrier_id)
        if carrier is None or carrier.tenant_id != driver.tenant_id:
            raise HTTPException(status_code=422, detail="Transportadora não pertence à empresa do motorista.")
    if data.user_id is not None:
        linked_user = db.get(User, data.user_id)
        if linked_user is None or linked_user.tenant_id != driver.tenant_id:
            raise HTTPException(status_code=422, detail="Usuário não pertence à empresa do motorista.")
    before = snapshot(driver, list(updates))
    for field, value in updates.items():
        setattr(driver, field, value)
    log_update(db, user_id=actor.id, entity="driver", entity_id=driver.id, before=before, obj=driver, updates=updates)
    db.commit()
    db.refresh(driver)
    return driver


@router.delete("/{driver_id}", dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL))])
def delete_driver(driver_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    driver = db.get(Driver, driver_id)
    if driver is None:
        raise HTTPException(status_code=404, detail="Motorista não encontrado.")
    if db.scalar(select(Route).where(Route.driver_id == driver_id)):
        raise HTTPException(status_code=409, detail="Motorista possui rota atribuída. Inative para manter o histórico.")
    if driver.user_id is not None:
        raise HTTPException(status_code=409, detail="Motorista está vinculado a um usuário. Remova o vínculo antes de excluir.")
    name = driver.name
    db.delete(driver)
    log(db, user_id=actor.id, action="delete", entity="driver", entity_id=driver_id, detail=f'name: "{name}"')
    db.commit()
    return {"deleted": driver_id}

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import Role, has_all_environment_access, require_roles, require_same_tenant
from app.db.models import Branch, Driver, DriverBranch, Route, User, Vehicle
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services.audit import log, log_update, snapshot

router = APIRouter(prefix="/branches", tags=["branches"])


class BranchIn(BaseModel):
    name: str
    country: str = "BR"
    locale: str = "pt-BR"
    tenant_id: int | None = None


class BranchUpdate(BaseModel):
    name: str | None = None
    locale: str | None = None
    active: bool | None = None


class BranchOut(BranchIn):
    id: int
    active: bool

    class Config:
        from_attributes = True


@router.get("", response_model=list[BranchOut])
def list_branches(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(Branch).order_by(Branch.name)
    if not has_all_environment_access(user):
        stmt = stmt.where(Branch.tenant_id == user.tenant_id)
    return db.scalars(stmt).all()


@router.post("", response_model=BranchOut, dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL))])
def create_branch(data: BranchIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    tenant_id = data.tenant_id if actor.role == Role.ADMIN_GLOBAL.value else actor.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=422, detail="Selecione a empresa da filial.")
    branch = Branch(**data.model_dump(exclude={"tenant_id"}), tenant_id=tenant_id)
    db.add(branch)
    db.flush()
    driver_ids = db.scalars(select(Driver.id).where(Driver.tenant_id == tenant_id)).all()
    db.add_all(DriverBranch(driver_id=driver_id, branch_id=branch.id) for driver_id in driver_ids)
    log(db, user_id=actor.id, action="create", entity="branch", entity_id=branch.id)
    db.commit()
    db.refresh(branch)
    return branch


@router.put("/{branch_id}", response_model=BranchOut, dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL))])
def update_branch(branch_id: int, data: BranchUpdate,
                  db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(status_code=404, detail="Filial não encontrada.")
    require_same_tenant(actor, branch.tenant_id)
    updates = data.model_dump(exclude_unset=True)
    before = snapshot(branch, list(updates))
    for field, value in updates.items():
        setattr(branch, field, value)
    log_update(db, user_id=actor.id, entity="branch", entity_id=branch.id, before=before, obj=branch, updates=updates)
    db.commit()
    db.refresh(branch)
    return branch


@router.delete("/{branch_id}", dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL))])
def delete_branch(branch_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(status_code=404, detail="Filial não encontrada.")
    require_same_tenant(actor, branch.tenant_id)
    linked = [
        ("usuários", User, User.branch_id),
        ("motoristas", Driver, Driver.branch_id),
        ("veículos", Vehicle, Vehicle.branch_id),
        ("rotas", Route, Route.branch_id),
    ]
    for label, model, column in linked:
        if db.scalar(select(model).where(column == branch_id)):
            raise HTTPException(status_code=409, detail=f"Filial possui {label} vinculados. Inative para manter o histórico.")
    name = branch.name
    db.delete(branch)
    log(db, user_id=actor.id, action="delete", entity="branch", entity_id=branch_id, detail=f'name: "{name}"')
    db.commit()
    return {"deleted": branch_id}

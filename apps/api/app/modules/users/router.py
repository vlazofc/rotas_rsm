"""Gestão de usuários, perfis e liberação de acesso (RBAC)."""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import Role, require_branch_access, require_roles, require_same_tenant
from app.core.security import hash_password
from app.db.models import Branch, RoleProfile, User
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services.audit import log, log_update, snapshot
from app.services.entity_status import StatusChangeIn, apply_status

router = APIRouter(prefix="/users", tags=["users"])

_ADMIN_OR_MANAGER = require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL)


class UserIn(BaseModel):
    email: EmailStr
    name: str
    role: str = Role.MOTORISTA.value
    branch_id: int | None = None
    password: str | None = Field(default=None, min_length=8, max_length=72)
    department: str | None = Field(default=None, max_length=80)
    subgroup: str | None = Field(default=None, max_length=80)
    permissions: list[str] = Field(default_factory=list)


class UserUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    branch_id: int | None = None
    active: bool | None = None
    department: str | None = Field(default=None, max_length=80)
    subgroup: str | None = Field(default=None, max_length=80)
    permissions: list[str] | None = None


class ResetPasswordIn(BaseModel):
    new_password: str = Field(min_length=8, max_length=72)


class RoleProfileIn(BaseModel):
    value: str = Field(min_length=3, max_length=40)
    label: str = Field(min_length=3, max_length=120)
    description: str | None = None
    permissions: list[str] = Field(default_factory=list)
    sort_order: int = 100
    active: bool = True


class RoleProfileUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=3, max_length=120)
    description: str | None = None
    permissions: list[str] | None = None
    sort_order: int | None = None
    active: bool | None = None


class RoleProfileOut(BaseModel):
    value: str
    label: str
    description: str | None
    permissions: list[str]
    sort_order: int
    active: bool
    system: bool


class UserOut(BaseModel):
    id: int
    email: EmailStr
    name: str
    role: str
    branch_id: int | None
    tenant_id: int | None = None
    active: bool
    blocked: bool = False
    status_reason: str | None = None
    department: str | None = None
    subgroup: str | None = None
    permissions: list[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id, email=user.email, name=user.name, role=user.role,
        branch_id=user.branch_id, tenant_id=user.tenant_id, active=user.active, blocked=user.blocked, status_reason=user.status_reason,
        department=user.department, subgroup=user.subgroup,
        permissions=_parse_permissions(user.permissions_json),
    )


def _validate_role_value(value: str) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,39}", value):
        raise HTTPException(
            status_code=422,
            detail="Código do perfil deve usar letras minúsculas, números e underscore.",
        )


def _parse_permissions(value: str | None) -> list[str]:
    if not value:
        return []
    return [line.strip() for line in value.splitlines() if line.strip()]


def _permissions_text(values: list[str] | None) -> str:
    return "\n".join(v.strip() for v in (values or []) if v.strip())


def _role_out(role: RoleProfile) -> RoleProfileOut:
    return RoleProfileOut(
        value=role.value,
        label=role.label,
        description=role.description,
        permissions=_parse_permissions(role.permissions_json),
        sort_order=role.sort_order,
        active=role.active,
        system=role.system,
    )


def _ensure_role_exists(db: Session, value: str) -> None:
    _validate_role_value(value)
    profile = db.get(RoleProfile, value)
    if profile is None or not profile.active:
        raise HTTPException(status_code=422, detail=f"Perfil inexistente ou inativo: {value}")


def _guard_admin_assignment(actor: User, target_role: str | None) -> None:
    """Só admin_global pode conceder/alterar o perfil admin_global."""
    if target_role == Role.ADMIN_GLOBAL.value and actor.role != Role.ADMIN_GLOBAL.value:
        raise HTTPException(status_code=403, detail="Apenas admin global pode conceder este perfil.")


def _default_branch_id(db: Session, tenant_id: int | None) -> int | None:
    if tenant_id is None:
        return None
    return db.scalar(
        select(Branch.id)
        .where(Branch.tenant_id == tenant_id, Branch.active.is_(True))
        .order_by(Branch.id)
    )


@router.get("/roles", dependencies=[Depends(_ADMIN_OR_MANAGER)])
def list_roles(db: Session = Depends(get_db)):
    """Perfis ativos para selects no frontend."""
    rows = db.scalars(
        select(RoleProfile)
        .where(RoleProfile.active.is_(True))
        .order_by(RoleProfile.sort_order, RoleProfile.label)
    ).all()
    return [_role_out(row).model_dump() for row in rows]


@router.get("/role-profiles", response_model=list[RoleProfileOut], dependencies=[Depends(_ADMIN_OR_MANAGER)])
def list_role_profiles(db: Session = Depends(get_db)):
    rows = db.scalars(select(RoleProfile).order_by(RoleProfile.sort_order, RoleProfile.label)).all()
    return [_role_out(row) for row in rows]


@router.post("/role-profiles", response_model=RoleProfileOut, dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL))])
def create_role_profile(data: RoleProfileIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    _validate_role_value(data.value)
    if db.get(RoleProfile, data.value):
        raise HTTPException(status_code=409, detail="Perfil já existe.")
    role = RoleProfile(
        value=data.value,
        label=data.label,
        description=data.description,
        permissions_json=_permissions_text(data.permissions),
        sort_order=data.sort_order,
        active=data.active,
        system=False,
    )
    db.add(role)
    db.flush()
    log(db, user_id=actor.id, action="create", entity="role_profile", entity_id=role.value)
    db.commit()
    db.refresh(role)
    return _role_out(role)


@router.put("/role-profiles/{value}", response_model=RoleProfileOut, dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL))])
def update_role_profile(
    value: str,
    data: RoleProfileUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    role = db.get(RoleProfile, value)
    if role is None:
        raise HTTPException(status_code=404, detail="Perfil não encontrado.")
    updates = data.model_dump(exclude_unset=True)
    before = snapshot(role, ["label", "description", "permissions_json", "sort_order", "active"])
    if data.label is not None:
        role.label = data.label
    if data.description is not None:
        role.description = data.description
    if data.permissions is not None:
        role.permissions_json = _permissions_text(data.permissions)
    if data.sort_order is not None:
        role.sort_order = data.sort_order
    if data.active is not None:
        if data.active is False and db.scalar(select(User).where(User.role == value, User.active.is_(True))):
            raise HTTPException(status_code=409, detail="Não é possível inativar perfil usado por usuário ativo.")
        role.active = data.active
    detail_updates = dict(updates)
    if "permissions" in detail_updates:
        detail_updates["permissions_json"] = _permissions_text(data.permissions)
        detail_updates.pop("permissions", None)
    log_update(db, user_id=actor.id, entity="role_profile", entity_id=role.value, before=before, obj=role, updates=detail_updates)
    db.commit()
    db.refresh(role)
    return _role_out(role)


@router.delete("/role-profiles/{value}", dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL))])
def delete_role_profile(value: str, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    role = db.get(RoleProfile, value)
    if role is None:
        raise HTTPException(status_code=404, detail="Perfil não encontrado.")
    if role.system:
        raise HTTPException(status_code=409, detail="Perfil de sistema não pode ser excluído; inative se necessário.")
    if db.scalar(select(User).where(User.role == value)):
        raise HTTPException(status_code=409, detail="Perfil em uso por usuários.")
    db.delete(role)
    log(db, user_id=actor.id, action="delete", entity="role_profile", entity_id=value)
    db.commit()
    return {"deleted": value}


@router.get("", response_model=list[UserOut], dependencies=[Depends(_ADMIN_OR_MANAGER)])
def list_users(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    # Contas técnicas de simulação ("Simular ambiente") não são usuários reais.
    stmt = select(User).where(
        ~User.email.like("preview@%.admmendes.internal"), ~User.email.like("preview@%.jm.internal")
    ).order_by(User.name)
    if actor.role != Role.ADMIN_GLOBAL.value:
        stmt = stmt.where(User.tenant_id == actor.tenant_id)
    return [_user_out(row) for row in db.scalars(stmt).all()]


@router.post("", response_model=UserOut, dependencies=[Depends(_ADMIN_OR_MANAGER)])
def create_user(data: UserIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    _ensure_role_exists(db, data.role)
    _guard_admin_assignment(actor, data.role)
    if db.scalar(select(User).where(User.email == data.email)):
        raise HTTPException(status_code=409, detail="Email já cadastrado.")
    # Não-admin global só pode criar usuários na própria filial.
    branch_id = data.branch_id if actor.role == Role.ADMIN_GLOBAL.value else actor.branch_id
    branch_id = branch_id or _default_branch_id(db, actor.tenant_id)
    if branch_id is None:
        raise HTTPException(status_code=422, detail="Selecione uma filial para o usuário.")
    branch = require_branch_access(db, actor, branch_id)
    user = User(
        email=data.email,
        name=data.name,
        role=data.role,
        tenant_id=branch.tenant_id,
        branch_id=branch.id,
        hashed_password=hash_password(data.password) if data.password else None,
        department=data.department, subgroup=data.subgroup,
        permissions_json=_permissions_text(data.permissions),
    )
    db.add(user)
    db.flush()
    log(db, user_id=actor.id, action="create", entity="user", entity_id=user.id)
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.put("/{user_id}", response_model=UserOut, dependencies=[Depends(_ADMIN_OR_MANAGER)])
def update_user(user_id: int, data: UserUpdate,
                db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    require_same_tenant(actor, user.tenant_id)
    updates = data.model_dump(exclude_unset=True)
    if "active" in updates:
        raise HTTPException(422, "Use a ação de situação para ativar ou desativar o usuário.")
    before = snapshot(user, list(updates))
    if data.role is not None:
        _ensure_role_exists(db, data.role)
        _guard_admin_assignment(actor, data.role)
        if user.role == Role.ADMIN_GLOBAL.value and actor.role != Role.ADMIN_GLOBAL.value:
            raise HTTPException(status_code=403, detail="Sem permissão para alterar um admin global.")
        user.role = data.role
    if data.name is not None:
        user.name = data.name
    if "department" in updates:
        user.department = data.department
    if "subgroup" in updates:
        user.subgroup = data.subgroup
    if data.permissions is not None:
        user.permissions_json = _permissions_text(data.permissions)
    if data.branch_id is not None:
        # Não-admin global não pode mover usuários para outra filial.
        branch = require_branch_access(db, actor, data.branch_id)
        user.branch_id = branch.id
        user.tenant_id = branch.tenant_id
    if data.active is not None:
        if user.id == actor.id and data.active is False:
            raise HTTPException(status_code=400, detail="Não é possível desativar a própria conta.")
        user.active = data.active
    log_update(db, user_id=actor.id, entity="user", entity_id=user.id, before=before, obj=user, updates=updates)
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.post("/{user_id}/status", response_model=UserOut, dependencies=[Depends(_ADMIN_OR_MANAGER)])
def change_user_status(user_id:int,data:StatusChangeIn,db:Session=Depends(get_db),actor:User=Depends(get_current_user)):
    user=db.get(User,user_id)
    if user is None:raise HTTPException(404,"Usuário não encontrado.")
    require_same_tenant(actor,user.tenant_id)
    if user.id==actor.id and data.action in {"deactivate","block"}:raise HTTPException(400,"Não é possível bloquear ou desativar a própria conta.")
    if user.role==Role.ADMIN_GLOBAL.value and actor.role!=Role.ADMIN_GLOBAL.value:raise HTTPException(403,"Sem permissão para alterar um admin global.")
    apply_status(db,obj=user,data=data,user_id=actor.id,entity="user");user.auth_version += 1;db.commit();db.refresh(user);return _user_out(user)


@router.post("/{user_id}/reset-password", response_model=UserOut,
             dependencies=[Depends(_ADMIN_OR_MANAGER)])
def reset_password(user_id: int, data: ResetPasswordIn,
                   db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    require_same_tenant(actor, user.tenant_id)
    if user.role == Role.ADMIN_GLOBAL.value and actor.role != Role.ADMIN_GLOBAL.value:
        raise HTTPException(status_code=403, detail="Sem permissão para redefinir a senha de um admin global.")
    user.hashed_password = hash_password(data.new_password)
    user.auth_version += 1
    log(db, user_id=actor.id, action="reset_password", entity="user", entity_id=user.id)
    db.commit()
    db.refresh(user)
    return _user_out(user)

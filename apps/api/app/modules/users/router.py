"""Gestão de usuários, perfis e liberação de acesso (RBAC)."""
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import Role, has_all_environment_access, require_branch_access, require_permission, require_roles, require_same_tenant
from app.core.security import hash_password
from app.db.models import Branch, Carrier, CarrierBranch, CarrierUser, Driver, RoleProfile, User
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services.audit import log, log_update, snapshot
from app.services.entity_status import StatusChangeIn, apply_status

router = APIRouter(prefix="/users", tags=["users"])

_ADMIN_OR_MANAGER = require_permission("module.users", Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL)
_CARRIER_ASSIGNABLE_ROLES = {
    Role.ADMIN_SITE.value, Role.GERENTE.value, Role.LIDER.value,
    Role.PLANEJAMENTO.value, Role.MONITORAMENTO.value,
    Role.OPERADOR_LOGISTICO.value, Role.TORRE_CONTROLE.value,
    Role.MOTORISTA.value,
}

def _guard_carrier_user(db: Session, actor: User, target_user_id: int) -> None:
    membership = db.scalar(select(CarrierUser).where(CarrierUser.user_id == actor.id, CarrierUser.active.is_(True)))
    if membership is not None and db.scalar(select(CarrierUser).where(CarrierUser.user_id == target_user_id, CarrierUser.carrier_id == membership.carrier_id, CarrierUser.active.is_(True))) is None:
        raise HTTPException(403, "Usuário não pertence à sua transportadora.")

def _guard_carrier_assignment(membership: CarrierUser | None, role: str | None, permissions: list[str] | None) -> None:
    if membership is None:
        return
    if role is not None and role not in _CARRIER_ASSIGNABLE_ROLES:
        raise HTTPException(403, "Este perfil só pode ser atribuído pela administração Adimax.")
    if permissions:
        raise HTTPException(403, "Permissões individuais só podem ser atribuídas pela administração Adimax.")


class UserIn(BaseModel):
    email: EmailStr | None = None
    login: str | None = Field(default=None, min_length=3, max_length=80)
    name: str
    role: str = Role.MOTORISTA.value
    branch_id: int | None = None
    department: str | None = Field(default=None, max_length=80)
    subgroup: str | None = Field(default=None, max_length=80)
    permissions: list[str] = Field(default_factory=list)


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    login: str | None = Field(default=None, min_length=3, max_length=80)
    name: str | None = None
    role: str | None = None
    branch_id: int | None = None
    active: bool | None = None
    department: str | None = Field(default=None, max_length=80)
    subgroup: str | None = Field(default=None, max_length=80)
    permissions: list[str] | None = None


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
    login: str | None = None
    name: str
    role: str
    branch_id: int | None
    tenant_id: int | None = None
    active: bool
    must_change_password: bool = False
    blocked: bool = False
    status_reason: str | None = None
    department: str | None = None
    subgroup: str | None = None
    permissions: list[str] = Field(default_factory=list)
    carrier_id: int | None = None
    carrier_name: str | None = None

    class Config:
        from_attributes = True


class UserCredentialsOut(UserOut):
    initial_password: str


def _user_out(user: User, carrier_id: int | None = None, carrier_name: str | None = None) -> UserOut:
    return UserOut(
        id=user.id, email=user.email, login=user.login, name=user.name, role=user.role,
        branch_id=user.branch_id, tenant_id=user.tenant_id, active=user.active, blocked=user.blocked, status_reason=user.status_reason,
        department=user.department, subgroup=user.subgroup, must_change_password=user.must_change_password,
        permissions=_parse_permissions(user.permissions_json), carrier_id=carrier_id, carrier_name=carrier_name,
    )


def _validate_role_value(value: str) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,39}", value):
        raise HTTPException(
            status_code=422,
            detail="Código do perfil deve usar letras minúsculas, números e underscore.",
        )


def _normalize_login(value: str | None) -> str | None:
    login = (value or "").strip().lower()
    if not login:
        return None
    if not re.fullmatch(r"[a-z0-9]+(?:[._-][a-z0-9]+)+", login):
        raise HTTPException(status_code=422, detail="O usuário deve seguir o padrão nome.sobrenome, sem espaços ou acentos.")
    return login


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


@router.get("/roles", dependencies=[Depends(_ADMIN_OR_MANAGER)])
def list_roles(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    """Perfis ativos para selects no frontend."""
    rows = db.scalars(
        select(RoleProfile)
        .where(RoleProfile.active.is_(True))
        .order_by(RoleProfile.sort_order, RoleProfile.label)
    ).all()
    membership = db.scalar(select(CarrierUser).where(CarrierUser.user_id == actor.id, CarrierUser.active.is_(True)))
    if membership is not None:
        rows = [row for row in rows if row.value in _CARRIER_ASSIGNABLE_ROLES]
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
    stmt = select(User).order_by(User.name)
    membership = db.scalar(select(CarrierUser).where(CarrierUser.user_id == actor.id, CarrierUser.active.is_(True)))
    if membership is not None:
        stmt = stmt.join(CarrierUser, CarrierUser.user_id == User.id).where(CarrierUser.carrier_id == membership.carrier_id, CarrierUser.active.is_(True))
    elif not has_all_environment_access(actor):
        stmt = stmt.where(User.tenant_id == actor.tenant_id)
    rows = db.scalars(stmt).all()
    memberships = {
        user_id: (carrier_id, carrier_name)
        for user_id, carrier_id, carrier_name in db.execute(
            select(CarrierUser.user_id, Carrier.id, Carrier.name)
            .join(Carrier, Carrier.id == CarrierUser.carrier_id)
            .where(CarrierUser.active.is_(True), CarrierUser.user_id.in_([row.id for row in rows]))
        ).all()
    } if rows else {}
    return [_user_out(row, *(memberships.get(row.id, (None, None)))) for row in rows if not (
        row.email.startswith("preview@")
        and row.email.endswith((".admmendes.internal", ".jm.internal"))
    )]


@router.post("", response_model=UserCredentialsOut, dependencies=[Depends(_ADMIN_OR_MANAGER)])
def create_user(data: UserIn, response: Response, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    _ensure_role_exists(db, data.role)
    _guard_admin_assignment(actor, data.role)
    login = _normalize_login(data.login)
    if data.role == Role.MOTORISTA.value and not login:
        raise HTTPException(status_code=422, detail="Informe o usuário do motorista no padrão nome.sobrenome.")
    if data.role != Role.MOTORISTA.value and data.email is None:
        raise HTTPException(status_code=422, detail="Informe o e-mail do usuário.")
    email = str(data.email).lower() if data.email else f"{login}@acesso.adimax.com.br"
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Email já cadastrado.")
    if login and db.scalar(select(User).where(User.login == login)):
        raise HTTPException(status_code=409, detail="Nome de usuário já cadastrado.")
    actor_membership = db.scalar(select(CarrierUser).where(CarrierUser.user_id == actor.id, CarrierUser.active.is_(True)))
    _guard_carrier_assignment(actor_membership, data.role, data.permissions)
    branch = require_branch_access(db, actor, data.branch_id) if data.branch_id is not None else None
    if actor_membership is not None:
        if branch is None or db.scalar(select(CarrierBranch).where(CarrierBranch.carrier_id == actor_membership.carrier_id, CarrierBranch.branch_id == branch.id, CarrierBranch.active.is_(True))) is None:
            raise HTTPException(403, "Selecione uma filial habilitada para a transportadora.")
        if data.role == Role.ADMIN_GLOBAL.value:
            raise HTTPException(403, "O Master não pode criar administradores globais.")
    tenant_id = branch.tenant_id if branch else actor.tenant_id
    if tenant_id is None and data.role != Role.ADMIN_GLOBAL.value:
        raise HTTPException(status_code=422, detail="Empresa não identificada para o usuário.")
    initial_password = secrets.token_urlsafe(18)
    user = User(
        email=email,
        login=login,
        name=data.name,
        role=data.role,
        tenant_id=tenant_id,
        branch_id=branch.id if branch else None,
        hashed_password=hash_password(initial_password),
        must_change_password=True,
        department=data.department, subgroup=data.subgroup,
        permissions_json=_permissions_text(data.permissions),
    )
    db.add(user)
    db.flush()
    if actor_membership is not None:
        db.add(CarrierUser(carrier_id=actor_membership.carrier_id, user_id=user.id, active=True))
    log(db, user_id=actor.id, action="create", entity="user", entity_id=user.id)
    db.commit()
    db.refresh(user)
    return UserCredentialsOut(**_user_out(user).model_dump(), initial_password=initial_password)


@router.put("/{user_id}", response_model=UserOut, dependencies=[Depends(_ADMIN_OR_MANAGER)])
def update_user(user_id: int, data: UserUpdate,
                db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    _guard_carrier_user(db, actor, user.id)
    require_same_tenant(actor, user.tenant_id)
    _guard_admin_assignment(actor, user.role)
    updates = data.model_dump(exclude_unset=True)
    actor_membership = db.scalar(select(CarrierUser).where(CarrierUser.user_id == actor.id, CarrierUser.active.is_(True)))
    _guard_carrier_assignment(actor_membership, data.role, data.permissions)
    if "login" in updates:
        login = _normalize_login(data.login)
        if user.role == Role.MOTORISTA.value and not login:
            raise HTTPException(status_code=422, detail="Informe o usuário do motorista.")
        if login and db.scalar(select(User).where(User.login == login, User.id != user.id)):
            raise HTTPException(status_code=409, detail="Nome de usuário já cadastrado.")
        user.login = login
    if "active" in updates:
        raise HTTPException(422, "Use a ação de situação para ativar ou desativar o usuário.")
    audit_updates = dict(updates)
    if "permissions" in audit_updates:
        audit_updates["permissions_json"] = _permissions_text(data.permissions)
        audit_updates.pop("permissions")
    before = snapshot(user, list(audit_updates))
    if data.role is not None:
        _ensure_role_exists(db, data.role)
        _guard_admin_assignment(actor, data.role)
        linked_driver = db.scalar(select(Driver).where(Driver.user_id == user.id))
        if linked_driver is not None and data.role != Role.MOTORISTA.value:
            raise HTTPException(
                status_code=422,
                detail="Este usuário está vinculado a um motorista e deve permanecer com o perfil Motorista. Desvincule o acesso no cadastro do motorista antes de alterar o perfil.",
            )
        if user.role == Role.ADMIN_GLOBAL.value and actor.role != Role.ADMIN_GLOBAL.value:
            raise HTTPException(status_code=403, detail="Sem permissão para alterar um admin global.")
        user.role = data.role
    normalized_email = str(data.email).lower() if data.email is not None else None
    if normalized_email is not None and normalized_email != user.email:
        if actor.role != Role.ADMIN_GLOBAL.value:
            raise HTTPException(status_code=403, detail="Apenas o Admin Global pode alterar o e-mail de login.")
        if db.scalar(select(User).where(User.email == normalized_email, User.id != user.id)):
            raise HTTPException(status_code=409, detail="E-mail já cadastrado para outro usuário.")
        user.email = normalized_email
    if data.name is not None:
        user.name = data.name
    if "department" in updates:
        user.department = data.department
    if "subgroup" in updates:
        user.subgroup = data.subgroup
    if data.permissions is not None:
        user.permissions_json = _permissions_text(data.permissions)
    if "branch_id" in updates:
        branch = require_branch_access(db, actor, data.branch_id) if data.branch_id is not None else None
        if actor_membership is not None and (branch is None or db.scalar(select(CarrierBranch).where(
            CarrierBranch.carrier_id == actor_membership.carrier_id,
            CarrierBranch.branch_id == branch.id,
            CarrierBranch.active.is_(True),
        )) is None):
            raise HTTPException(403, "Selecione uma filial habilitada para a transportadora.")
        user.branch_id = branch.id if branch else None
        if branch:
            user.tenant_id = branch.tenant_id
    if data.active is not None:
        if user.id == actor.id and data.active is False:
            raise HTTPException(status_code=400, detail="Não é possível desativar a própria conta.")
        user.active = data.active
    log_update(db, user_id=actor.id, entity="user", entity_id=user.id, before=before, obj=user, updates=audit_updates)
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.post("/{user_id}/status", response_model=UserOut, dependencies=[Depends(_ADMIN_OR_MANAGER)])
def change_user_status(user_id:int,data:StatusChangeIn,db:Session=Depends(get_db),actor:User=Depends(get_current_user)):
    user=db.get(User,user_id)
    if user is None:raise HTTPException(404,"Usuário não encontrado.")
    _guard_carrier_user(db,actor,user.id)
    require_same_tenant(actor,user.tenant_id)
    if user.id==actor.id and data.action in {"deactivate","block"}:raise HTTPException(400,"Não é possível bloquear ou desativar a própria conta.")
    if user.role==Role.ADMIN_GLOBAL.value and actor.role!=Role.ADMIN_GLOBAL.value:raise HTTPException(403,"Sem permissão para alterar um admin global.")
    apply_status(db,obj=user,data=data,user_id=actor.id,entity="user");user.auth_version += 1;db.commit();db.refresh(user);return _user_out(user)


@router.post("/{user_id}/repair-driver-access", response_model=UserOut,
             dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL))])
def repair_driver_access(user_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    """Restaura perfil e escopo de uma conta que já possui vínculo operacional."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Usuário não encontrado.")
    driver = db.scalar(select(Driver).where(Driver.user_id == user.id))
    if driver is None:
        raise HTTPException(409, "Usuário sem cadastro de motorista vinculado.")
    before = snapshot(user, ["role", "tenant_id", "branch_id", "auth_version"])
    user.role = Role.MOTORISTA.value
    user.tenant_id = driver.tenant_id
    user.branch_id = driver.branch_id
    user.auth_version += 1
    log_update(
        db, user_id=actor.id, entity="driver_access_repair", entity_id=user.id,
        before=before, obj=user,
        updates={"role": user.role, "tenant_id": user.tenant_id, "branch_id": user.branch_id, "auth_version": user.auth_version},
    )
    db.commit(); db.refresh(user)
    return _user_out(user)


@router.post("/{user_id}/reset-password", response_model=UserCredentialsOut,
             dependencies=[Depends(_ADMIN_OR_MANAGER)])
def reset_password(user_id: int, response: Response,
                   db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    _guard_carrier_user(db, actor, user.id)
    require_same_tenant(actor, user.tenant_id)
    if user.role == Role.ADMIN_GLOBAL.value and actor.role != Role.ADMIN_GLOBAL.value:
        raise HTTPException(status_code=403, detail="Sem permissão para redefinir a senha de um admin global.")
    initial_password = secrets.token_urlsafe(18)
    user.hashed_password = hash_password(initial_password)
    user.must_change_password = True
    user.auth_version += 1
    log(db, user_id=actor.id, action="reset_password", entity="user", entity_id=user.id)
    db.commit()
    db.refresh(user)
    return UserCredentialsOut(**_user_out(user).model_dump(), initial_password=initial_password)

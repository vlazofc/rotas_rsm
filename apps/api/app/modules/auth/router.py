"""Autenticação local com JWT."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token, create_refresh_token, decode_token, hash_password, verify_password,
)
from app.db.models import AuditLog, Branch, Carrier, CarrierBranch, CarrierMaster, CarrierUser, User
from app.db.session import get_db
from app.modules.auth.deps import ensure_user_scope, get_current_user, get_authenticated_user
from app.modules.auth.schemas import TokenResponse, UserOut
from app.core.permissions import user_permissions
from app.core.rate_limit import limiter
from app.services.audit import log

router = APIRouter(prefix="/auth", tags=["auth"])


def _tokens(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(str(user.id), role=user.role, branch_id=user.branch_id,
                                         name=user.name, auth_version=user.auth_version),
        refresh_token=create_refresh_token(str(user.id), auth_version=user.auth_version),
        must_change_password=user.must_change_password,
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Login local por e-mail ou nome de usuário + senha."""
    identifier = form.username.strip().lower()
    user = db.scalar(select(User).where(or_(User.email == identifier, User.login == identifier)))
    if user is None or not user.hashed_password or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário/e-mail ou senha inválidos.")
    if not user.active or user.blocked:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuário inativo ou bloqueado.")
    ensure_user_scope(user, db)

    # O contexto de suporte nunca atravessa uma nova autenticação.
    if user.role == "admin_global" and (user.acting_branch_id is not None or user.acting_carrier_id is not None):
        user.acting_branch_id = None
        user.acting_carrier_id = None

    log(db, user_id=user.id, action="login", entity="user", entity_id=user.id)
    db.commit()
    return _tokens(user)


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=20)


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("30/minute")
def refresh(request: Request, data: RefreshIn, db: Session = Depends(get_db)):
    try:
        payload = decode_token(data.refresh_token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh inválido.")
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token não é refresh.")
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário inválido.")
    if payload.get("auth_version") != user.auth_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessão revogada.")
    ensure_user_scope(user, db)
    return _tokens(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_authenticated_user), db: Session = Depends(get_db)):
    membership = db.scalar(select(CarrierUser).where(CarrierUser.user_id == user.id, CarrierUser.active.is_(True)))
    master = db.scalar(select(CarrierMaster).where(CarrierMaster.user_id == user.id, CarrierMaster.active.is_(True)))
    acting_branch = db.get(Branch, user.acting_branch_id) if user.role == "admin_global" and user.acting_branch_id else None
    acting_carrier = db.get(Carrier, user.acting_carrier_id) if user.role == "admin_global" and user.acting_carrier_id else None
    return UserOut(
        id=user.id, email=user.email, name=user.name, role=user.role,
        branch_id=user.branch_id, tenant_id=user.tenant_id,
        carrier_id=membership.carrier_id if membership else None,
        is_carrier_master=master is not None,
        department=user.department, subgroup=user.subgroup,
        permissions=sorted(user_permissions(user, db)),
        navigation_layout=user.navigation_layout or "sidebar",
        must_change_password=user.must_change_password,
        acting_branch_id=acting_branch.id if acting_branch else None,
        acting_branch_name=acting_branch.name if acting_branch else None,
        acting_carrier_id=acting_carrier.id if acting_carrier else None,
        acting_carrier_name=acting_carrier.name if acting_carrier else None,
        acting_read_only=bool(acting_branch or acting_carrier),
    )


class ActingContextIn(BaseModel):
    branch_id: int | None = None
    carrier_id: int | None = None


@router.put("/acting-context", response_model=UserOut)
def set_acting_context(data: ActingContextIn, db: Session = Depends(get_db), user: User = Depends(get_authenticated_user)):
    if user.role != "admin_global":
        raise HTTPException(status_code=403, detail="Somente o administrador global pode usar Ver como.")
    branch = db.get(Branch, data.branch_id) if data.branch_id is not None else None
    carrier = db.get(Carrier, data.carrier_id) if data.carrier_id is not None else None
    if data.branch_id is not None and (branch is None or not branch.active):
        raise HTTPException(status_code=422, detail="Filial inválida ou inativa.")
    if data.carrier_id is not None and (carrier is None or not carrier.active):
        raise HTTPException(status_code=422, detail="Transportadora inválida ou inativa.")
    if branch and carrier:
        enabled = db.scalar(select(CarrierBranch.id).where(
            CarrierBranch.branch_id == branch.id,
            CarrierBranch.carrier_id == carrier.id,
            CarrierBranch.active.is_(True),
        ))
        if enabled is None:
            raise HTTPException(status_code=422, detail="Transportadora não habilitada na filial selecionada.")
    user.acting_branch_id = branch.id if branch else None
    user.acting_carrier_id = carrier.id if carrier else None
    log(db, user_id=user.id, action="acting_context", entity="user", entity_id=user.id,
        detail=f"branch_id={user.acting_branch_id}; carrier_id={user.acting_carrier_id}; read_only=true")
    db.commit()
    return me(user, db)


@router.get("/admin-security-status")
def admin_security_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role != "admin_global":
        raise HTTPException(status_code=403, detail="Acesso exclusivo do administrador global.")
    admin_ids = select(User.id).where(User.role == "admin_global", User.active.is_(True), User.blocked.is_(False))
    active_count = db.scalar(select(func.count()).select_from(User).where(User.role == "admin_global", User.active.is_(True), User.blocked.is_(False))) or 0
    recent = db.execute(
        select(AuditLog.created_at, User.name)
        .join(User, User.id == AuditLog.user_id)
        .where(AuditLog.action == "login", AuditLog.user_id.in_(admin_ids))
        .order_by(AuditLog.created_at.desc()).limit(5)
    ).all()
    return {"active_admin_count": active_count, "warning": active_count > 1,
            "recent_admin_logins": [{"name": row.name, "created_at": row.created_at} for row in recent]}


class PreferencesIn(BaseModel):
    navigation_layout: str


@router.put("/preferences", response_model=UserOut)
def update_preferences(data: PreferencesIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if data.navigation_layout not in {"sidebar", "top"}:
        raise HTTPException(status_code=422, detail="Posição de navegação inválida.")
    user.navigation_layout = data.navigation_layout
    db.commit()
    return me(user, db)


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=72)


@router.post("/change-password", response_model=TokenResponse)
def change_password(
    data: ChangePasswordIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_authenticated_user),
):
    """Troca da própria senha (exige a senha atual)."""
    if not user.hashed_password or not verify_password(data.current_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Senha atual incorreta.")
    if len(data.new_password.encode("utf-8")) > 72:
        raise HTTPException(status_code=422, detail="A nova senha deve ter no máximo 72 bytes.")
    if verify_password(data.new_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="A nova senha deve ser diferente da senha atual.")
    user.hashed_password = hash_password(data.new_password)
    user.must_change_password = False
    user.auth_version += 1
    log(db, user_id=user.id, action="change_password", entity="user", entity_id=user.id)
    db.commit()
    return _tokens(user)

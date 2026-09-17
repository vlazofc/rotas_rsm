"""Autenticação local com JWT."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token, create_refresh_token, decode_token, hash_password, verify_password,
)
from app.db.models import User
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
    if not user.active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuário inativo.")
    ensure_user_scope(user, db)

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
    return UserOut(
        id=user.id, email=user.email, name=user.name, role=user.role,
        branch_id=user.branch_id, tenant_id=user.tenant_id,
        department=user.department, subgroup=user.subgroup,
        permissions=sorted(user_permissions(user, db)),
        navigation_layout=user.navigation_layout or "sidebar",
        must_change_password=user.must_change_password,
    )


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

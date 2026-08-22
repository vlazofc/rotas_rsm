"""Autenticação local (JWT) + esqueleto de Microsoft Entra ID (OIDC)."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token, create_refresh_token, decode_token, hash_password, verify_password,
)
from app.db.models import User
from app.db.session import get_db
from app.modules.auth.deps import ensure_user_scope, get_current_user
from app.modules.auth.schemas import TokenResponse, UserOut
from app.services.audit import log

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Login local por email+senha (form OAuth2: campo username = email)."""
    user = db.scalar(select(User).where(User.email == form.username))
    if user is None or not user.hashed_password or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email ou senha inválidos.")
    if not user.active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuário inativo.")
    ensure_user_scope(user, db)

    log(db, user_id=user.id, action="login", entity="user", entity_id=user.id)
    db.commit()
    claims = {"role": user.role, "branch_id": user.branch_id, "name": user.name}
    return TokenResponse(
        access_token=create_access_token(str(user.id), **claims),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(refresh_token: str, db: Session = Depends(get_db)):
    try:
        payload = decode_token(refresh_token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh inválido.")
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token não é refresh.")
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário inválido.")
    ensure_user_scope(user, db)
    claims = {"role": user.role, "branch_id": user.branch_id, "name": user.name}
    return TokenResponse(
        access_token=create_access_token(str(user.id), **claims),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=72)


@router.post("/change-password")
def change_password(
    data: ChangePasswordIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Troca da própria senha (exige a senha atual)."""
    if not user.hashed_password or not verify_password(data.current_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Senha atual incorreta.")
    user.hashed_password = hash_password(data.new_password)
    log(db, user_id=user.id, action="change_password", entity="user", entity_id=user.id)
    db.commit()
    return {"status": "ok"}


@router.get("/entra/login")
def entra_login():
    """Inicia o fluxo OIDC com Microsoft Entra ID (Authorization Code)."""
    if settings.auth_mode != "entra":
        raise HTTPException(status_code=400, detail="AUTH_MODE não é 'entra'.")
    authorize = (
        f"https://login.microsoftonline.com/{settings.microsoft_tenant_id}/oauth2/v2.0/authorize"
        f"?client_id={settings.microsoft_client_id}"
        f"&response_type=code"
        f"&redirect_uri={settings.microsoft_redirect_uri}"
        f"&response_mode=query"
        f"&scope=openid%20profile%20email"
    )
    return {"authorization_url": authorize}


@router.get("/callback")
def entra_callback(code: str):
    """Troca o code por tokens na Microsoft e emite JWT interno.

    TODO: trocar code->token via httpx, validar id_token, mapear usuário/grupo->role.
    Esqueleto pronto para implementar quando o app registration estiver criado.
    """
    raise HTTPException(status_code=501, detail="Callback Entra ID a implementar (ver TODO).")

"""Autenticação de integrações externas via token fixo (header Authorization: Bearer)."""
import hashlib
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ApiToken, User
from app.db.session import get_db


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def get_api_token_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token de integração inválido.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise cred_exc
    raw_token = authorization[7:].strip()
    if not raw_token:
        raise cred_exc
    token = db.scalar(select(ApiToken).where(ApiToken.token_hash == _hash_token(raw_token)))
    if token is None or not token.active:
        raise cred_exc
    user = db.get(User, token.user_id)
    if user is None or not user.active or user.blocked:
        raise cred_exc
    token.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return user

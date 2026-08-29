from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.db.models import TrackingIntegration, User
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services.integration_secrets import encrypt_secret
from app.services.truckcontrol import DEFAULT_URL, PROVIDER, sync_positions, sync_vehicles

router = APIRouter(prefix="/integrations/truckcontrol", tags=["integrations"])


class TruckControlIn(BaseModel):
    base_url: str = DEFAULT_URL
    login: str | None = Field(default=None, min_length=1, max_length=120)
    password: str | None = Field(default=None, min_length=1, max_length=200)
    enabled: bool = False
    current_password: str = Field(min_length=1, max_length=200)


def _admin(user: User) -> None:
    if user.role != "admin_global":
        raise HTTPException(403, "Somente o administrador global pode configurar esta integração.")


def _row(db: Session) -> TrackingIntegration | None:
    return db.scalar(select(TrackingIntegration).where(TrackingIntegration.provider == PROVIDER))


@router.get("")
def status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    row = _row(db)
    return {"configured": bool(row and row.login_encrypted and row.password_encrypted),
            "base_url": row.base_url if row else DEFAULT_URL, "enabled": bool(row and row.enabled),
            "poll_interval_seconds": 30, "last_message_id": row.last_message_id if row else 1,
            "last_sync_at": row.last_sync_at if row else None, "last_success_at": row.last_success_at if row else None,
            "last_vehicle_sync_at": row.last_vehicle_sync_at if row else None,
            "last_error": row.last_error if row else None}


@router.put("")
def save(data: TruckControlIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    if not verify_password(data.current_password, user.hashed_password):
        raise HTTPException(403, "Senha atual inválida.")
    parsed = urlparse(data.base_url.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise HTTPException(422, "Informe uma URL HTTPS válida, sem credenciais ou parâmetros.")
    row = _row(db)
    if row is None:
        if not data.login or not data.password:
            raise HTTPException(422, "Login e senha são obrigatórios na primeira configuração.")
        row = TrackingIntegration(provider=PROVIDER, base_url=data.base_url.strip(), login_encrypted="", password_encrypted="")
        db.add(row)
    if data.login:
        row.login_encrypted = encrypt_secret(data.login)
    if data.password:
        row.password_encrypted = encrypt_secret(data.password)
    row.base_url, row.enabled, row.poll_interval_seconds = data.base_url.strip().rstrip("/"), data.enabled, 30
    db.commit()
    return status(db, user)


@router.post("/test")
def test_connection(current_password: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _admin(user)
    if not verify_password(current_password, user.hashed_password):
        raise HTTPException(403, "Senha atual inválida.")
    row = _row(db)
    if row is None:
        raise HTTPException(409, "Integração ainda não configurada.")
    try:
        vehicles = sync_vehicles(db, row)
        positions = sync_positions(db, row)
        return {"ok": True, **vehicles, **positions}
    except Exception as exc:
        row.last_sync_at, row.last_error = datetime.now(timezone.utc), str(exc)[:500]
        db.commit()
        raise HTTPException(502, "TruckControl indisponível ou credenciais inválidas.") from exc

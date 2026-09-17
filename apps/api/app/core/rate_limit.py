"""Limitador compartilhado para API e autenticação."""
from fastapi import Request
from slowapi import Limiter

from app.core.config import settings


def client_ip(request: Request) -> str:
    return (
        request.headers.get("CF-Connecting-IP")
        or request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
        or (request.client.host if request.client else "unknown")
    )


_testing = settings.app_env.strip().lower() in {"test", "testing"}
limiter = Limiter(
    key_func=client_ip,
    default_limits=[settings.api_rate_limit],
    storage_uri=None if _testing else settings.redis_url,
)

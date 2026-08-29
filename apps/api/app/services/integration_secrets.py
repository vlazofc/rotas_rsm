"""Cifra autenticada para segredos de integrações armazenados no banco."""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _fernet() -> Fernet:
    source = settings.integration_encryption_key.strip() or settings.jwt_secret
    key = hashlib.sha256(f"rotas-integrations:{source}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Não foi possível decifrar a credencial da integração.") from exc

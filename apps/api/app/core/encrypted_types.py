"""Tipos SQLAlchemy com criptografia transparente para dados pessoais."""
from __future__ import annotations

import base64
import hashlib

from cryptography.hazmat.primitives.ciphers.aead import AESSIV
from sqlalchemy.types import Text, TypeDecorator

from app.core.config import settings


PREFIX = "enc:v1:"


def _cipher() -> AESSIV | None:
    configured = settings.data_encryption_key.strip()
    if not configured:
        return None
    try:
        raw = base64.urlsafe_b64decode(configured + "=" * (-len(configured) % 4))
    except Exception:
        raw = configured.encode("utf-8")
    key = hashlib.sha512(b"adimax-log:data:v1:" + raw).digest()
    return AESSIV(key)


def encrypt_value(value: str | None, context: str) -> str | None:
    if value is None or value == "" or value.startswith(PREFIX):
        return value
    cipher = _cipher()
    if cipher is None:
        return value
    encrypted = cipher.encrypt(value.encode("utf-8"), [context.encode("utf-8")])
    return PREFIX + base64.urlsafe_b64encode(encrypted).decode("ascii")


def decrypt_value(value: str | None, context: str) -> str | None:
    if value is None or value == "" or not value.startswith(PREFIX):
        return value
    cipher = _cipher()
    if cipher is None:
        raise RuntimeError("DATA_ENCRYPTION_KEY ausente; dado protegido não pode ser lido.")
    try:
        encrypted = base64.urlsafe_b64decode(value[len(PREFIX):])
        return cipher.decrypt(encrypted, [context.encode("utf-8")]).decode("utf-8")
    except Exception as exc:
        raise RuntimeError(f"Falha ao descriptografar o campo {context}.") from exc


class EncryptedText(TypeDecorator[str]):
    """Texto cifrado no armazenamento e normal na camada Python/API."""

    impl = Text
    cache_ok = True

    def __init__(self, context: str):
        super().__init__()
        self.context = context

    def process_bind_param(self, value, dialect):
        return encrypt_value(value, self.context)

    def process_result_value(self, value, dialect):
        return decrypt_value(value, self.context)


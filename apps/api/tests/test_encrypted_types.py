import pytest

from app.core.config import settings
from app.core.encrypted_types import PREFIX, decrypt_value, encrypt_value


@pytest.fixture(autouse=True)
def encryption_key():
    previous = settings.data_encryption_key
    settings.data_encryption_key = "unit-test-key-with-at-least-thirty-two-characters"
    yield
    settings.data_encryption_key = previous


def test_roundtrip_is_deterministic_and_context_bound():
    first = encrypt_value("caio.haddad@adimax.com.br", "users.email")
    second = encrypt_value("caio.haddad@adimax.com.br", "users.email")
    other_context = encrypt_value("caio.haddad@adimax.com.br", "drivers.email")
    assert first == second
    assert first != other_context
    assert first.startswith(PREFIX)
    assert decrypt_value(first, "users.email") == "caio.haddad@adimax.com.br"


def test_tampered_ciphertext_is_rejected():
    encrypted = encrypt_value("12345678901", "drivers.document")
    with pytest.raises(RuntimeError):
        decrypt_value(encrypted[:-2] + "AA", "drivers.document")


def test_plaintext_is_read_during_controlled_migration():
    assert decrypt_value("12345678901", "drivers.document") == "12345678901"

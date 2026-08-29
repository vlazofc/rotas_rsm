import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.config import Settings
from app.core.permissions import require_same_branch


BASE = {
    "database_url": "postgresql+psycopg://user:password@postgres/app",
    "redis_url": "redis://:password@redis:6379/0",
    "celery_broker_url": "redis://:password@redis:6379/1",
    "celery_result_backend": "redis://:password@redis:6379/2",
}


def test_production_rejects_default_secrets():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", jwt_secret="trocar", **BASE)


def test_production_rejects_local_cors():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            jwt_secret="a" * 48,
            minio_root_password="b" * 20,
            seed_admin_password="c" * 20,
            allowed_origins="http://localhost:5173",
            **BASE,
        )


def test_branch_guard_blocks_cross_branch_access():
    user = type("UserStub", (), {"role": "gestor_brasil", "branch_id": 10})()
    with pytest.raises(HTTPException) as exc:
        require_same_branch(user, 11)
    assert exc.value.status_code == 403


def test_global_admin_can_cross_branches():
    user = type("UserStub", (), {"role": "admin_global", "branch_id": None})()
    require_same_branch(user, 11)

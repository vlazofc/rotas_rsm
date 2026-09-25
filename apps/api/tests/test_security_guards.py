import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.config import Settings
from app.core.security import create_access_token, decode_token
from app.core.permissions import AccessScope, has_all_environment_access, operational_scope, require_branch_access, require_same_branch
from app.db.models import Branch


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


def test_global_admin_acting_as_branch_loses_global_bypass():
    user = type("UserStub", (), {"role": "admin_global", "branch_id": 10, "acting_branch_id": 10, "acting_carrier_id": None, "permissions_json": None})()
    assert has_all_environment_access(user) is False
    assert operational_scope(user) == AccessScope.BRANCH


def test_adimax_tenant_name_does_not_grant_global_access():
    tenant = type("TenantStub", (), {"slug": "adimax"})()
    user = type("UserStub", (), {"role": "gerente", "tenant": tenant, "permissions_json": None})()
    assert has_all_environment_access(user) is False


def test_operational_scope_matrix():
    def user(role, **extra):
        values = {"role": role, "permissions_json": None, "tenant_id": 1, "branch_id": 10, **extra}
        return type("UserStub", (), values)()

    assert operational_scope(user("admin_global")) == AccessScope.GLOBAL
    assert operational_scope(user("gerente")) == AccessScope.TENANT
    assert operational_scope(user("monitoramento")) == AccessScope.TENANT
    assert operational_scope(user("operador_logistico")) == AccessScope.BRANCH
    assert operational_scope(user("motorista")) == AccessScope.ASSIGNED
    assert operational_scope(user("operador_logistico", permissions_json="scope.tenant")) == AccessScope.TENANT


def test_tenant_manager_can_access_another_branch_but_operator_cannot():
    branch = Branch(id=20, tenant_id=1, name="Filial B", active=True)

    class FakeDb:
        def get(self, model, value):
            return branch if model is Branch and value == branch.id else None

    manager = type("UserStub", (), {"role": "gerente", "permissions_json": None, "tenant_id": 1, "branch_id": 10})()
    operator = type("UserStub", (), {"role": "operador_logistico", "permissions_json": None, "tenant_id": 1, "branch_id": 10})()
    assert require_branch_access(FakeDb(), manager, branch.id) is branch
    with pytest.raises(HTTPException) as exc:
        require_branch_access(FakeDb(), operator, branch.id)
    assert exc.value.status_code == 403


def test_each_login_receives_a_distinct_session_identifier():
    first = decode_token(create_access_token("123"))
    second = decode_token(create_access_token("123"))
    assert first["jti"] != second["jti"]

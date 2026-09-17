import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import Branch, Tenant, User
from app.db.session import Base
from app.modules.routes_import.router import _resolve_import_branch


def _database():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine


def test_manager_without_primary_branch_uses_only_active_tenant_branch():
    engine = _database()
    try:
        with Session(engine) as db:
            tenant = Tenant(name="JM", slug="jm")
            db.add(tenant); db.flush()
            branch = Branch(name="Operação Adimax", tenant_id=tenant.id)
            manager = User(name="Gabriela", email="gabriela@example.com", role="gerente", tenant_id=tenant.id)
            db.add_all([branch, manager]); db.commit()

            assert _resolve_import_branch(db, manager) == branch.id
    finally:
        engine.dispose()


def test_manager_without_primary_branch_must_choose_when_tenant_has_multiple_branches():
    engine = _database()
    try:
        with Session(engine) as db:
            tenant = Tenant(name="JM", slug="jm")
            db.add(tenant); db.flush()
            db.add_all([Branch(name="A", tenant_id=tenant.id), Branch(name="B", tenant_id=tenant.id)])
            manager = User(name="Gabriela", email="gabriela@example.com", role="gerente", tenant_id=tenant.id)
            db.add(manager); db.commit()

            with pytest.raises(HTTPException) as error:
                _resolve_import_branch(db, manager)
            assert error.value.status_code == 409
            assert "mais de uma filial" in error.value.detail
    finally:
        engine.dispose()

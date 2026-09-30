import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import Branch, Carrier, CarrierBranch, CarrierUser, Tenant, User
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


def test_carrier_master_can_choose_only_a_branch_enabled_for_its_carrier():
    engine = _database()
    try:
        with Session(engine) as db:
            tenant = Tenant(name="JM", slug="jm")
            db.add(tenant); db.flush()
            enabled = Branch(name="Salto", tenant_id=tenant.id)
            blocked = Branch(name="Outra", tenant_id=tenant.id)
            carrier = Carrier(name="JM Transportes", tenant_id=tenant.id)
            master = User(name="Master", email="master@example.com", role="gestor_brasil", tenant_id=tenant.id)
            db.add_all([enabled, blocked, carrier, master]); db.flush()
            db.add_all([
                CarrierBranch(carrier_id=carrier.id, branch_id=enabled.id),
                CarrierUser(carrier_id=carrier.id, user_id=master.id),
            ])
            db.commit()

            assert _resolve_import_branch(db, master, enabled.id) == enabled.id
            with pytest.raises(HTTPException) as error:
                _resolve_import_branch(db, master, blocked.id)
            assert error.value.status_code == 403
            assert "não habilitada" in error.value.detail
    finally:
        engine.dispose()


def test_global_admin_can_choose_a_branch_even_without_tenant_or_primary_branch():
    engine = _database()
    try:
        with Session(engine) as db:
            first_tenant = Tenant(name="JM", slug="jm")
            second_tenant = Tenant(name="Adimax", slug="adimax")
            db.add_all([first_tenant, second_tenant]); db.flush()
            first_branch = Branch(name="Salto", tenant_id=first_tenant.id)
            selected_branch = Branch(name="Abreu e Lima", tenant_id=second_tenant.id)
            admin = User(name="Administrador", email="admin@example.com", role="admin_global")
            db.add_all([first_branch, selected_branch, admin]); db.commit()

            assert _resolve_import_branch(db, admin, selected_branch.id) == selected_branch.id
    finally:
        engine.dispose()

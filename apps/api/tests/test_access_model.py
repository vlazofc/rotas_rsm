import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import (
    Branch, Carrier, CarrierMaster, Driver, DriverBranch, Tenant, User,
)
from app.db.session import Base
from app.modules.access_model.router import (
    ApprovalPolicyIn, AvailabilityIn, add_master, configure_approval,
    enable_carrier_branch, set_driver_availability,
)


@pytest.fixture
def local_model():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        tenant = Tenant(name="Adimax", slug="adimax-access")
        db.add(tenant); db.flush()
        salto = Branch(name="Salto", tenant_id=tenant.id)
        barueri = Branch(name="Barueri", tenant_id=tenant.id)
        db.add_all([salto, barueri]); db.flush()
        admin = User(name="Admin", email="admin-access@example.com", role="admin_global", tenant_id=tenant.id, branch_id=salto.id)
        carrier = Carrier(name="Transportadora Alfa", document="12.345.678/0001-90", person_type="pessoa_juridica", tenant_id=tenant.id)
        db.add_all([admin, carrier]); db.flush()
        driver = Driver(name="João", tenant_id=tenant.id, branch_id=salto.id, carrier_id=carrier.id)
        masters = [User(name=f"Master {n}", email=f"master{n}@example.com", role="gestor_brasil", tenant_id=tenant.id, branch_id=salto.id) for n in range(1, 5)]
        db.add_all([driver, *masters]); db.commit()
        yield db, admin, carrier, driver, salto, barueri, masters
    engine.dispose()


def test_shared_driver_can_have_independent_branch_approval(local_model):
    db, admin, carrier, driver, salto, barueri, _ = local_model
    enable_carrier_branch(carrier.id, salto.id, db=db, actor=admin)
    enable_carrier_branch(carrier.id, barueri.id, db=db, actor=admin)
    configure_approval(salto.id, ApprovalPolicyIn(require_driver_approval=False), db=db, actor=admin)
    configure_approval(barueri.id, ApprovalPolicyIn(require_driver_approval=True), db=db, actor=admin)

    salto_link = set_driver_availability(driver.id, salto.id, AvailabilityIn(), db=db, actor=admin)
    barueri_link = set_driver_availability(driver.id, barueri.id, AvailabilityIn(), db=db, actor=admin)

    assert salto_link["approval_status"] == "approved"
    assert barueri_link["approval_status"] == "pending"
    assert db.scalar(select(DriverBranch).where(DriverBranch.driver_id == driver.id, DriverBranch.branch_id == salto.id)).active


def test_carrier_has_at_most_three_active_masters_across_branches(local_model):
    db, admin, carrier, _, _, _, masters = local_model
    for user in masters[:3]:
        add_master(carrier.id, user.id, db=db, actor=admin)
    assert db.scalar(select(CarrierMaster).where(CarrierMaster.user_id == masters[0].id)).is_first_master
    assert all(user.role == "gestor_brasil" for user in masters[:3])
    with pytest.raises(HTTPException) as error:
        add_master(carrier.id, masters[3].id, db=db, actor=admin)
    assert error.value.status_code == 409


def test_carrier_can_override_default_master_limit(local_model):
    db, admin, carrier, _, _, _, masters = local_model
    carrier.max_masters = 4
    db.commit()
    for user in masters:
        add_master(carrier.id, user.id, db=db, actor=admin)
    assert db.scalar(select(CarrierMaster).where(CarrierMaster.user_id == masters[3].id)) is not None


def test_carrier_must_be_enabled_before_driver_is_available(local_model):
    db, admin, _, driver, _, barueri, _ = local_model
    with pytest.raises(HTTPException) as error:
        set_driver_availability(driver.id, barueri.id, AvailabilityIn(), db=db, actor=admin)
    assert error.value.status_code == 422

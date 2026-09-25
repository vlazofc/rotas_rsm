from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import (
    Branch, Carrier, CarrierBranch, CarrierUser, Driver, Route,
    RouteCarrierChange, Tenant, User, UserBranchAccess, Vehicle,
)
from app.db.session import Base
from app.modules.routes.router import change_route_carrier, get_route, list_routes
from app.modules.routes.schemas import RouteCarrierChangeIn


@pytest.fixture
def carrier_routes():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        tenant = Tenant(name="Adimax", slug="adimax-route-carrier")
        db.add(tenant); db.flush()
        branch = Branch(name="Salto", tenant_id=tenant.id)
        db.add(branch); db.flush()
        alfa = Carrier(name="Alfa", document="11111111000111", person_type="pessoa_juridica", tenant_id=tenant.id)
        beta = Carrier(name="Beta", document="22222222000122", person_type="pessoa_juridica", tenant_id=tenant.id)
        db.add_all([alfa, beta]); db.flush()
        db.add_all([CarrierBranch(carrier_id=alfa.id, branch_id=branch.id), CarrierBranch(carrier_id=beta.id, branch_id=branch.id)])
        admin = User(name="Admin", email="admin-carrier@example.com", role="admin_global", tenant_id=tenant.id, branch_id=branch.id)
        alfa_user = User(name="Alfa User", email="alfa@example.com", role="operador_logistico", tenant_id=tenant.id, branch_id=branch.id)
        beta_user = User(name="Beta User", email="beta@example.com", role="operador_logistico", tenant_id=tenant.id, branch_id=branch.id)
        db.add_all([admin, alfa_user, beta_user]); db.flush()
        db.add_all([
            CarrierUser(carrier_id=alfa.id, user_id=alfa_user.id), CarrierUser(carrier_id=beta.id, user_id=beta_user.id),
            UserBranchAccess(user_id=alfa_user.id, branch_id=branch.id), UserBranchAccess(user_id=beta_user.id, branch_id=branch.id),
        ])
        driver = Driver(name="João", tenant_id=tenant.id, branch_id=branch.id, carrier_id=alfa.id)
        vehicle = Vehicle(plate="ABC1D23", tenant_id=tenant.id, branch_id=branch.id, carrier_id=alfa.id)
        db.add_all([driver, vehicle]); db.flush()
        route = Route(
            tenant_id=tenant.id, branch_id=branch.id, carrier_id=alfa.id,
            carrier_assignment_status="valid", codigo_ut="RT-00125", route_date=date.today(),
            driver_id=driver.id, vehicle_id=vehicle.id, status="planejada",
        )
        pending = Route(
            tenant_id=tenant.id, branch_id=branch.id, carrier_assignment_status="pending_carrier",
            carrier_assignment_issue="Transportadora ausente.", codigo_ut="RT-PENDING", route_date=date.today(),
        )
        db.add_all([route, pending]); db.commit()
        yield db, admin, alfa_user, beta_user, alfa, beta, route, pending
    engine.dispose()


def test_carrier_user_sees_only_valid_routes_assigned_to_its_carrier(carrier_routes):
    db, _, alfa_user, beta_user, _, _, route, pending = carrier_routes
    assert [item.id for item in list_routes(db=db, user=alfa_user)] == [route.id]
    assert list_routes(db=db, user=beta_user) == []
    with pytest.raises(HTTPException) as error:
        get_route(pending.id, db=db, user=alfa_user)
    assert error.value.status_code == 403


def test_change_carrier_revokes_old_access_unassigns_resources_and_audits(carrier_routes):
    db, admin, alfa_user, beta_user, alfa, beta, route, _ = carrier_routes
    changed = change_route_carrier(route.id, RouteCarrierChangeIn(carrier_id=beta.id, reason="Replanejamento operacional"), db=db, user=admin)
    assert changed.carrier_id == beta.id
    assert changed.driver_id is None and changed.vehicle_id is None
    assert list_routes(db=db, user=alfa_user) == []
    assert [item.id for item in list_routes(db=db, user=beta_user)] == [route.id]
    audit = db.scalar(select(RouteCarrierChange).where(RouteCarrierChange.route_id == route.id))
    assert audit.previous_carrier_id == alfa.id
    assert audit.new_carrier_id == beta.id
    assert audit.previous_driver_id is not None and audit.previous_vehicle_id is not None
    assert audit.route_status == "planejada"
    assert audit.reason == "Replanejamento operacional"


def test_only_global_admin_can_change_carrier(carrier_routes):
    db, _, alfa_user, _, _, beta, route, _ = carrier_routes
    with pytest.raises(HTTPException) as error:
        change_route_carrier(route.id, RouteCarrierChangeIn(carrier_id=beta.id, reason="Motivo válido"), db=db, user=alfa_user)
    assert error.value.status_code == 403


def test_global_admin_acting_as_carrier_gets_read_only_scoped_route_list(carrier_routes):
    db, admin, _, _, alfa, beta, route, _ = carrier_routes
    admin.acting_carrier_id = alfa.id
    assert [item.id for item in list_routes(db=db, user=admin)] == [route.id]
    admin.acting_carrier_id = beta.id
    assert list_routes(db=db, user=admin) == []

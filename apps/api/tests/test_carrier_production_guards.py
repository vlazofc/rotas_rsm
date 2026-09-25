from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import (
    Branch, Carrier, CarrierUser, Route, RouteOccurrence, Tenant, User,
    Vehicle, VehicleChangeRequest, VehicleOwner,
)
from app.db.session import Base
from app.modules.notifications.router import _tenant_rows
from app.modules.users.router import _guard_carrier_assignment
from app.modules.vehicles.router import list_owners, list_requests


@pytest.fixture
def carrier_scope():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        tenant = Tenant(name="Adimax", slug="carrier-production-guards")
        db.add(tenant); db.flush()
        branch = Branch(name="Salto", tenant_id=tenant.id)
        alfa = Carrier(name="Alfa", document="11111111000111", person_type="pessoa_juridica", tenant_id=tenant.id)
        beta = Carrier(name="Beta", document="22222222000122", person_type="pessoa_juridica", tenant_id=tenant.id)
        db.add_all([branch, alfa, beta]); db.flush()
        master = User(name="Master Alfa", email="master-guard@example.com", role="gestor_brasil", tenant_id=tenant.id, branch_id=branch.id)
        db.add(master); db.flush()
        membership = CarrierUser(carrier_id=alfa.id, user_id=master.id)
        db.add(membership)
        owner_a = VehicleOwner(tenant_id=tenant.id, carrier_id=alfa.id, name="Owner A", document="11111111111")
        owner_b = VehicleOwner(tenant_id=tenant.id, carrier_id=beta.id, name="Owner B", document="22222222222")
        db.add_all([owner_a, owner_b]); db.flush()
        vehicle_a = Vehicle(tenant_id=tenant.id, branch_id=branch.id, carrier_id=alfa.id, owner_id=owner_a.id, plate="AAA1A11")
        vehicle_b = Vehicle(tenant_id=tenant.id, branch_id=branch.id, carrier_id=beta.id, owner_id=owner_b.id, plate="BBB2B22")
        db.add_all([vehicle_a, vehicle_b]); db.flush()
        route_a = Route(tenant_id=tenant.id, branch_id=branch.id, carrier_id=alfa.id, codigo_ut="ALFA", route_date=date.today())
        route_b = Route(tenant_id=tenant.id, branch_id=branch.id, carrier_id=beta.id, codigo_ut="BETA", route_date=date.today())
        db.add_all([route_a, route_b]); db.flush()
        occurrence_a = RouteOccurrence(tenant_id=tenant.id, branch_id=branch.id, route_id=route_a.id, reported_by=master.id, description="Alfa")
        occurrence_b = RouteOccurrence(tenant_id=tenant.id, branch_id=branch.id, route_id=route_b.id, reported_by=master.id, description="Beta")
        db.add_all([occurrence_a, occurrence_b]); db.flush()
        db.add_all([
            VehicleChangeRequest(tenant_id=tenant.id, branch_id=branch.id, vehicle_id=vehicle_a.id, requested_by_id=master.id, reason="Alfa"),
            VehicleChangeRequest(tenant_id=tenant.id, branch_id=branch.id, vehicle_id=vehicle_b.id, requested_by_id=master.id, reason="Beta"),
        ])
        db.commit()
        yield db, master, membership, owner_a, route_a, occurrence_a
    engine.dispose()


def test_carrier_master_cannot_assign_privileged_role_or_custom_permissions(carrier_scope):
    _, _, membership, *_ = carrier_scope
    with pytest.raises(HTTPException) as role_error:
        _guard_carrier_assignment(membership, "gestor_financeiro", [])
    assert role_error.value.status_code == 403
    with pytest.raises(HTTPException) as permission_error:
        _guard_carrier_assignment(membership, "operador_logistico", ["finance.view"])
    assert permission_error.value.status_code == 403


def test_live_alert_source_is_scoped_to_carrier(carrier_scope):
    db, master, _, _, route_a, occurrence_a = carrier_scope
    assert [row.id for row in _tenant_rows(db, Route, master)] == [route_a.id]
    assert [row.id for row in _tenant_rows(db, RouteOccurrence, master)] == [occurrence_a.id]


def test_vehicle_owners_and_requests_are_scoped_to_carrier(carrier_scope):
    db, master, _, owner_a, *_ = carrier_scope
    assert [row.id for row in list_owners(db=db, actor=master)] == [owner_a.id]
    requests = list_requests(db=db, actor=master)
    assert len(requests) == 1
    assert requests[0].plate == "AAA1A11"

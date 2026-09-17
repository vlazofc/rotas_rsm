from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.rate_limit import limiter
from app.core.security import create_access_token
from app.db.models import Branch, DockSession, Driver, RoleProfile, Route, Tenant, User
from app.db.session import Base, get_db
from app.modules.drivers.router import router as drivers_router
from app.modules.routes.router import list_routes, router as routes_router


@pytest.fixture
def context():
    limiter.reset()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        tenant = Tenant(name="Empresa A", slug="empresa-a")
        other_tenant = Tenant(name="Empresa B", slug="empresa-b")
        db.add_all([tenant, other_tenant]); db.flush()
        branch = Branch(name="Filial A", tenant_id=tenant.id)
        db.add(branch); db.flush()
        manager = User(name="Gestor", email="manager@example.com", role="gestor_brasil", tenant_id=tenant.id, branch_id=branch.id)
        access = User(name="Motorista A", email="driver@example.com", login="motorista.a", role="motorista", tenant_id=tenant.id, branch_id=branch.id)
        internal = User(name="Operador", email="operator@example.com", role="operador_logistico", tenant_id=tenant.id, branch_id=branch.id)
        foreign = User(name="Motorista B", email="foreign@example.com", login="motorista.b", role="motorista", tenant_id=other_tenant.id)
        db.add_all([manager, access, internal, foreign, RoleProfile(value="motorista", label="Motorista")]); db.commit()
        app = FastAPI()
        app.include_router(drivers_router, prefix="/api")
        app.include_router(routes_router, prefix="/api")
        app.dependency_overrides[get_db] = lambda: db
        with TestClient(app) as client:
            headers = {"Authorization": "Bearer " + create_access_token(str(manager.id), auth_version=manager.auth_version)}
            yield client, db, headers, branch, access, internal, foreign
    engine.dispose()


def driver_payload(branch_id, user_id):
    return {"branch_id": branch_id, "branch_ids": [branch_id], "name": "Cadastro Motorista", "user_id": user_id}


def test_linked_driver_access_sees_assigned_route(context):
    client, db, headers, branch, access, *_ = context
    created = client.post("/api/drivers", headers=headers, json=driver_payload(branch.id, access.id))
    assert created.status_code == 200, created.text
    driver = db.get(Driver, created.json()["id"])
    route = Route(branch_id=branch.id, codigo_ut="UT-LINK", route_date=date.today(), driver_id=driver.id)
    db.add(route); db.commit()
    assert list_routes(db=db, user=access) == [route]


def test_access_must_be_driver_same_tenant_and_unique(context):
    client, _, headers, branch, access, internal, foreign = context
    wrong_role = client.post("/api/drivers", headers=headers, json=driver_payload(branch.id, internal.id))
    assert wrong_role.status_code == 422
    wrong_tenant = client.post("/api/drivers", headers=headers, json=driver_payload(branch.id, foreign.id))
    assert wrong_tenant.status_code == 422
    first = client.post("/api/drivers", headers=headers, json=driver_payload(branch.id, access.id))
    assert first.status_code == 200
    duplicate = client.post("/api/drivers", headers=headers, json={**driver_payload(branch.id, access.id), "name": "Outro cadastro"})
    assert duplicate.status_code == 409


def test_access_options_identify_existing_link(context):
    client, _, headers, branch, access, *_ = context
    created = client.post("/api/drivers", headers=headers, json=driver_payload(branch.id, access.id)).json()
    options = client.get("/api/drivers/access-options", headers=headers)
    assert options.status_code == 200
    assert options.json() == [{
        "id": access.id, "name": access.name, "login": access.login, "tenant_id": access.tenant_id,
        "branch_id": branch.id, "active": True, "blocked": False,
        "linked_driver_id": created["id"],
    }]


def test_linked_driver_can_release_only_assigned_route(context):
    client, db, headers, branch, access, *_ = context
    driver_id = client.post("/api/drivers", headers=headers, json=driver_payload(branch.id, access.id)).json()["id"]
    assigned = Route(branch_id=branch.id, tenant_id=branch.tenant_id, codigo_ut="UT-ASSIGNED", route_date=date.today(), driver_id=driver_id)
    other = Route(branch_id=branch.id, tenant_id=branch.tenant_id, codigo_ut="UT-OTHER", route_date=date.today())
    db.add_all([assigned, other]); db.flush()
    db.add_all([DockSession(route_id=assigned.id), DockSession(route_id=other.id)])
    db.commit()
    driver_headers = {"Authorization": "Bearer " + create_access_token(str(access.id), auth_version=access.auth_version)}

    denied = client.post(f"/api/routes/{other.id}/release", headers=driver_headers)
    assert denied.status_code == 403
    allowed = client.post(f"/api/routes/{assigned.id}/release", headers=driver_headers)
    assert allowed.status_code == 409
    assert allowed.json()["detail"] == "Registre a chegada ao CD antes da liberação."


def test_linked_driver_access_uses_link_even_when_legacy_profile_is_wrong(context):
    client, db, headers, branch, access, *_ = context
    driver_id = client.post("/api/drivers", headers=headers, json=driver_payload(branch.id, access.id)).json()["id"]
    assigned = Route(branch_id=branch.id, tenant_id=branch.tenant_id, codigo_ut="UT-WILLIAN", route_date=date.today(), driver_id=driver_id)
    other = Route(branch_id=branch.id, tenant_id=branch.tenant_id, codigo_ut="UT-OTHER", route_date=date.today())
    db.add_all([assigned, other]); db.flush()
    db.add_all([DockSession(route_id=assigned.id), DockSession(route_id=other.id)])
    access.role = "gerente"
    db.commit()
    legacy_headers = {"Authorization": "Bearer " + create_access_token(str(access.id), auth_version=access.auth_version)}

    visible = client.get("/api/routes", headers=legacy_headers)
    assert visible.status_code == 200
    assert [route["codigo_ut"] for route in visible.json()] == ["UT-WILLIAN"]
    assert client.post(f"/api/routes/{other.id}/release", headers=legacy_headers).status_code == 403
    assigned_response = client.post(f"/api/routes/{assigned.id}/release", headers=legacy_headers)
    assert assigned_response.status_code == 409
    assert assigned_response.json()["detail"] == "Registre a chegada ao CD antes da liberação."

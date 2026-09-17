import json
from datetime import date

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, verify_password
from app.core.rate_limit import limiter
from app.db.models import AuditLog, Branch, Driver, RoleProfile, Tenant, User
from app.db.session import Base, get_db
from app.modules.auth.deps import get_current_user
from app.modules.auth.router import router as auth_router
from app.modules.users.router import router as users_router


@pytest.fixture
def context():
    limiter.reset()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        tenant = Tenant(name="Empresa A", slug="empresa-a")
        other = Tenant(name="Empresa B", slug="empresa-b")
        db.add_all([tenant, other]); db.flush()
        branch = Branch(name="Filial A", tenant_id=tenant.id)
        other_branch = Branch(name="Filial B", tenant_id=other.id)
        db.add_all([branch, other_branch]); db.flush()
        admin = User(name="Admin", email="admin@example.com", role="admin_global", tenant_id=tenant.id)
        manager = User(name="Gestor", email="manager@example.com", role="gestor_brasil", tenant_id=tenant.id, branch_id=branch.id)
        db.add_all([admin, manager])
        for role in ["admin_global", "gestor_brasil", "motorista"]:
            db.add(RoleProfile(value=role, label=role))
        db.commit()
        app = FastAPI()
        app.include_router(auth_router, prefix="/api")
        app.include_router(users_router, prefix="/api")
        app.dependency_overrides[get_db] = lambda: db

        @app.get("/api/protected")
        def protected(user=Depends(get_current_user)):
            return {"id": user.id}

        with TestClient(app) as client:
            headers = {"Authorization": "Bearer " + create_access_token(str(admin.id), auth_version=admin.auth_version)}
            yield client, db, headers, manager.id, branch.id, other_branch.id
    engine.dispose()


def create(client, headers, **overrides):
    data = {"email": "new@example.com", "name": "Novo usuário", "role": "motorista", **overrides}
    if data["role"] == "motorista":
        data.setdefault("login", "novo.motorista")
    response = client.post("/api/users", headers=headers, json=data)
    assert response.status_code == 200, response.text
    return response.json()


def login(client, email, password):
    response = client.post("/api/auth/login", data={"username": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def bearer(session):
    return {"Authorization": "Bearer " + session["access_token"]}


@pytest.mark.parametrize("role", ["motorista", "admin_global"])
def test_generated_password_and_first_login_are_enforced(context, role):
    client, db, headers, *_ = context
    created = create(client, headers, role=role)
    assert created["branch_id"] is None
    assert created["tenant_id"] is not None
    assert created["must_change_password"] is True
    password = created["initial_password"]
    assert len(password) >= 20
    saved = db.get(User, created["id"])
    assert saved.hashed_password != password and verify_password(password, saved.hashed_password)
    listing = client.get("/api/users", headers=headers)
    assert "initial_password" not in listing.text and password not in listing.text
    audit = json.dumps([row.detail for row in db.scalars(select(AuditLog))])
    assert password not in audit

    identifier = created.get("login") or created["email"]
    session = login(client, identifier, password)
    assert session["must_change_password"] is True
    assert client.get("/api/auth/me", headers=bearer(session)).json()["must_change_password"] is True
    assert client.get("/api/protected", headers=bearer(session)).status_code == 403
    refreshed = client.post("/api/auth/refresh", json={"refresh_token": session["refresh_token"]})
    assert refreshed.status_code == 200
    assert client.get("/api/protected", headers=bearer(refreshed.json())).status_code == 403
    for old, new in [("incorrect", "personal-password"), (password, password)]:
        assert client.post("/api/auth/change-password", headers=bearer(session), json={"current_password": old, "new_password": new}).status_code == 400
    changed = client.post("/api/auth/change-password", headers=bearer(session), json={"current_password": password, "new_password": "personal-password"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["must_change_password"] is False
    assert client.get("/api/protected", headers=bearer(changed.json())).status_code == 200
    assert client.get("/api/protected", headers=bearer(session)).status_code == 401
    assert client.post("/api/auth/refresh", json={"refresh_token": session["refresh_token"]}).status_code == 401
    assert client.post("/api/auth/login", data={"username": identifier, "password": password}).status_code == 401
    assert login(client, identifier, "personal-password")["must_change_password"] is False


def test_reset_generates_unique_password_and_revokes_sessions(context):
    client, db, headers, *_ = context
    created = create(client, headers)
    identifier = created.get("login") or created["email"]
    session = login(client, identifier, created["initial_password"])
    reset = client.post(f'/api/users/{created["id"]}/reset-password', headers=headers)
    assert reset.status_code == 200
    assert reset.json()["initial_password"] != created["initial_password"]
    assert reset.json()["must_change_password"] is True
    assert client.get("/api/auth/me", headers=bearer(session)).status_code == 401
    assert login(client, identifier, reset.json()["initial_password"])["must_change_password"] is True


def test_branch_can_be_omitted_and_cleared_without_changing_tenant(context):
    client, db, headers, manager_id, branch_id, other_branch_id = context
    manager = db.get(User, manager_id)
    manager_headers = {"Authorization": "Bearer " + create_access_token(str(manager.id), auth_version=manager.auth_version)}
    created = create(client, manager_headers)
    assert created["branch_id"] is None
    assert created["tenant_id"] == manager.tenant_id
    assigned = client.put(f'/api/users/{created["id"]}', headers=manager_headers, json={"branch_id": branch_id})
    assert assigned.json()["branch_id"] == branch_id
    denied = client.put(f'/api/users/{created["id"]}', headers=manager_headers, json={"branch_id": other_branch_id})
    assert denied.status_code == 403
    cleared = client.put(f'/api/users/{created["id"]}', headers=manager_headers, json={"branch_id": None, "permissions": ["finance.view"]})
    assert cleared.status_code == 200
    assert cleared.json()["branch_id"] is None and cleared.json()["tenant_id"] == manager.tenant_id
    assert client.post("/api/users", headers=manager_headers, json={"email": "elevated@example.com", "name": "Test", "role": "admin_global"}).status_code == 403


def test_manager_queries_are_tenant_wide_without_becoming_global(context):
    from app.db.models import Route
    from app.modules.routes.router import list_routes
    client, db, headers, manager_id, branch_id, other_branch_id = context
    manager = db.get(User, manager_id)
    own = Route(branch_id=branch_id, codigo_ut="own-scope", route_date=date.today())
    foreign = Route(branch_id=other_branch_id, codigo_ut="foreign-scope", route_date=date.today())
    db.add_all([own, foreign]); db.commit()
    assert list_routes(db=db, user=manager) == [own]
    manager.branch_id = None
    assert list_routes(db=db, user=manager) == [own]


def test_existing_user_does_not_require_password_change(context):
    client, db, headers, *_ = context
    assert client.get("/api/auth/me", headers=headers).json()["must_change_password"] is False
    assert client.get("/api/protected", headers=headers).status_code == 200


def test_linked_driver_user_cannot_lose_driver_role(context):
    client, db, headers, manager_id, branch_id, *_ = context
    manager = db.get(User, manager_id)
    access = User(
        name="Willian Souza de Melo",
        email="willian@example.com",
        login="willian.melo",
        role="motorista",
        tenant_id=manager.tenant_id,
        branch_id=branch_id,
    )
    db.add(access); db.flush()
    db.add(Driver(name="Willian Souza de Melo", tenant_id=access.tenant_id, branch_id=branch_id, user_id=access.id))
    db.commit()

    response = client.put(f"/api/users/{access.id}", headers=headers, json={"role": "gestor_brasil"})
    assert response.status_code == 422
    assert "deve permanecer com o perfil Motorista" in response.json()["detail"]

    access.role = "gestor_brasil"
    access.tenant_id = None
    access.branch_id = None
    db.commit()
    repaired = client.post(f"/api/users/{access.id}/repair-driver-access", headers=headers)
    assert repaired.status_code == 200
    assert repaired.json()["role"] == "motorista"
    assert repaired.json()["tenant_id"] == manager.tenant_id
    assert repaired.json()["branch_id"] == branch_id


def test_dashboard_cache_does_not_share_global_access_with_branchless_user(context, monkeypatch):
    from app.db.models import Route
    from app.modules.dashboard import router as dashboard
    client, db, headers, manager_id, branch_id, other_branch_id = context
    admin = db.scalar(select(User).where(User.role == "admin_global"))
    manager = db.get(User, manager_id)
    manager.branch_id = None
    db.add_all([
        Route(branch_id=branch_id, codigo_ut="scope-test", route_date=date.today()),
        Route(branch_id=other_branch_id, codigo_ut="foreign-scope-test", route_date=date.today()),
    ])
    db.commit()
    cache = {}
    monkeypatch.setattr(dashboard, "get_json", cache.get)
    monkeypatch.setattr(dashboard, "set_json", lambda key, value, ttl: cache.update({key: value}))
    global_result = dashboard.summary(db=db, user=admin)
    restricted_result = dashboard.summary(db=db, user=manager)
    assert global_result["rotas_abertas"] == 2
    assert restricted_result["rotas_abertas"] == 1

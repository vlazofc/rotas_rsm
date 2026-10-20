from datetime import date, datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import (
    Attachment, Branch, Carrier, CarrierBranch, CarrierMaster, CarrierUser,
    DockSession, Route, RouteStop, Tenant, User,
)
from app.db.session import Base, get_db
from app.modules.auth.deps import get_current_user
from app.modules.routes import router as routes_module


def test_administrative_staff_and_own_carrier_master_can_close_backlog(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine, expire_on_commit=False) as db:
            tenant = Tenant(name="JM", slug="backlog-close-access")
            db.add(tenant)
            db.flush()
            branch = Branch(name="Barueri", tenant_id=tenant.id)
            carrier = Carrier(name="Alfa", tenant_id=tenant.id)
            other_carrier = Carrier(name="Beta", tenant_id=tenant.id)
            db.add_all([branch, carrier, other_carrier])
            db.flush()
            db.add_all([
                CarrierBranch(carrier_id=carrier.id, branch_id=branch.id),
                CarrierBranch(carrier_id=other_carrier.id, branch_id=branch.id),
            ])
            staff = User(name="Administrativo", email="backlog-staff@example.com", role="gestor_brasil", tenant_id=tenant.id, branch_id=branch.id)
            operator = User(name="Operador", email="backlog-operator@example.com", role="operador_logistico", tenant_id=tenant.id, branch_id=branch.id)
            master = User(name="Master Alfa", email="backlog-master@example.com", role="gestor_brasil", tenant_id=tenant.id, branch_id=branch.id)
            foreign_master = User(name="Master Beta", email="backlog-foreign@example.com", role="gestor_brasil", tenant_id=tenant.id, branch_id=branch.id)
            db.add_all([staff, operator, master, foreign_master])
            db.flush()
            db.add_all([
                CarrierUser(carrier_id=carrier.id, user_id=master.id),
                CarrierMaster(carrier_id=carrier.id, user_id=master.id, active=True),
                CarrierUser(carrier_id=other_carrier.id, user_id=foreign_master.id),
                CarrierMaster(carrier_id=other_carrier.id, user_id=foreign_master.id, active=True),
            ])
            photo = Attachment(bucket="tests", storage_key="empty.jpg", content_type="image/jpeg")
            db.add(photo)
            db.flush()

            def ready_route(code):
                route = Route(
                    tenant_id=tenant.id, branch_id=branch.id, carrier_id=carrier.id,
                    carrier_assignment_status="valid", codigo_ut=code,
                    route_date=date.today() - timedelta(days=7), status="em_rota",
                    empty_truck_photo_attachment_id=photo.id,
                )
                db.add(route)
                db.flush()
                db.add(DockSession(route_id=route.id, departure_cd_at=datetime.now(timezone.utc)))
                db.add(RouteStop(route_id=route.id, sequence=1, customer_name="Entregue", status="entregue"))
                return route

            routes = {name: ready_route(name) for name in ("staff", "operator", "master", "foreign")}
            db.commit()

            monkeypatch.setattr(routes_module.storage, "get_presigned_url", lambda *args: "https://example.invalid/photo")
            app = FastAPI()
            app.include_router(routes_module.router)
            app.dependency_overrides[get_db] = lambda: db
            with TestClient(app) as client:
                for actor, route in ((staff, routes["staff"]), (operator, routes["operator"]), (master, routes["master"])):
                    app.dependency_overrides[get_current_user] = lambda actor=actor: actor
                    response = client.post(f"/routes/{route.id}/close")
                    assert response.status_code == 200, response.text
                    assert response.json()["status"] == "finalizada"

                app.dependency_overrides[get_current_user] = lambda: foreign_master
                denied = client.post(f"/routes/{routes['foreign'].id}/close")
                assert denied.status_code == 403, denied.text
                assert denied.json()["detail"] == "Rota não atribuída à sua transportadora."

            assert db.scalar(select(Route.status).where(Route.id == routes["foreign"].id)) == "em_rota"
    finally:
        engine.dispose()

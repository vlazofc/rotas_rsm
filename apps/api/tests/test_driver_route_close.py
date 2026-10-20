from datetime import date, datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import Attachment, Branch, DockSession, Driver, Route, RouteStop, Tenant, User
from app.db.session import Base, get_db
from app.modules.auth.deps import get_current_user
from app.modules.routes import router as routes_module


def test_assigned_driver_can_close_route_but_not_another_drivers_route(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            tenant = Tenant(name="JM", slug="driver-route-close")
            db.add(tenant)
            db.flush()
            branch = Branch(name="Barueri", tenant_id=tenant.id)
            db.add(branch)
            db.flush()
            user = User(name="Motorista", email="driver-close@example.com", role="motorista", tenant_id=tenant.id, branch_id=branch.id)
            other_user = User(name="Outro motorista", email="other-close@example.com", role="motorista", tenant_id=tenant.id, branch_id=branch.id)
            db.add_all([user, other_user])
            db.flush()
            driver = Driver(name="Motorista", tenant_id=tenant.id, branch_id=branch.id, user_id=user.id)
            other_driver = Driver(name="Outro motorista", tenant_id=tenant.id, branch_id=branch.id, user_id=other_user.id)
            db.add_all([driver, other_driver])
            db.flush()
            photo = Attachment(bucket="tests", storage_key="empty.jpg", content_type="image/jpeg")
            db.add(photo)
            db.flush()
            route_date = date.today() - timedelta(days=1)
            own = Route(tenant_id=tenant.id, branch_id=branch.id, codigo_ut="OWN-CLOSE", route_date=route_date, status="em_rota", driver_id=driver.id, empty_truck_photo_attachment_id=photo.id)
            foreign = Route(tenant_id=tenant.id, branch_id=branch.id, codigo_ut="FOREIGN-CLOSE", route_date=route_date, status="em_rota", driver_id=other_driver.id, empty_truck_photo_attachment_id=photo.id)
            db.add_all([own, foreign])
            db.flush()
            now = datetime.now(timezone.utc)
            db.add_all([DockSession(route_id=own.id, departure_cd_at=now), DockSession(route_id=foreign.id, departure_cd_at=now)])
            db.add_all([RouteStop(route_id=own.id, sequence=1, customer_name="Entregue", status="entregue"), RouteStop(route_id=foreign.id, sequence=1, customer_name="Entregue", status="entregue")])
            db.commit()

            monkeypatch.setattr(routes_module.storage, "get_presigned_url", lambda *args: "https://example.invalid/photo")
            app = FastAPI()
            app.include_router(routes_module.router)
            app.dependency_overrides[get_current_user] = lambda: user
            app.dependency_overrides[get_db] = lambda: db
            with TestClient(app) as client:
                denied = client.post(f"/routes/{foreign.id}/close")
                assert denied.status_code == 403, denied.text
                assert denied.json()["detail"] == "Rota não atribuída a este motorista."

                closed = client.post(f"/routes/{own.id}/close")
                assert closed.status_code == 200, closed.text
                assert closed.json()["status"] == "finalizada"

            assert db.scalar(select(Route.status).where(Route.id == own.id)) == "finalizada"
            assert db.scalar(select(Route.status).where(Route.id == foreign.id)) == "em_rota"
    finally:
        engine.dispose()

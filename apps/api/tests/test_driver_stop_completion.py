from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import Branch, DeliveryFailureReason, DockSession, Driver, Route, RouteOccurrence, RouteOccurrenceEvent, RouteStop, Tenant, User
from app.db.session import Base
from app.modules.routes.router import arrive_cd, deliver, operator_release
from app.modules.routes.schemas import DeliverIn


def test_linked_driver_can_deliver_refuse_and_cannot_close_another_route():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            tenant = Tenant(name="JM", slug="jm")
            db.add(tenant); db.flush()
            branch = Branch(name="Adimax", tenant_id=tenant.id)
            db.add(branch); db.flush()
            user = User(name="Motorista", email="motorista@example.com", role="motorista", tenant_id=tenant.id, branch_id=branch.id)
            other_user = User(name="Outro", email="outro@example.com", role="motorista", tenant_id=tenant.id, branch_id=branch.id)
            db.add_all([user, other_user]); db.flush()
            driver = Driver(name="Motorista", tenant_id=tenant.id, branch_id=branch.id, user_id=user.id)
            other_driver = Driver(name="Outro", tenant_id=tenant.id, branch_id=branch.id, user_id=other_user.id)
            reason = DeliveryFailureReason(code="recusado", label="Recusado pelo cliente", label_pt_br="Recusado pelo cliente")
            db.add_all([driver, other_driver, reason]); db.flush()
            backlog_date = date.today() - timedelta(days=1)
            route = Route(tenant_id=tenant.id, branch_id=branch.id, codigo_ut="UT-MOTORISTA", route_date=backlog_date, status="planejada", driver_id=driver.id)
            other_route = Route(tenant_id=tenant.id, branch_id=branch.id, codigo_ut="UT-OUTRO", route_date=backlog_date, status="em_rota", driver_id=other_driver.id)
            db.add_all([route, other_route]); db.flush()
            now = datetime.now(timezone.utc)
            db.add_all([DockSession(route_id=route.id), DockSession(route_id=other_route.id, departure_cd_at=now)])
            delivered_stop = RouteStop(route_id=route.id, sequence=1, customer_name="Cliente entregue", stop_type="carga")
            refused_stop = RouteStop(route_id=route.id, sequence=2, customer_name="Cliente recusou", stop_type="carga")
            foreign_stop = RouteStop(route_id=other_route.id, sequence=1, customer_name="Outra rota", stop_type="carga")
            db.add_all([delivered_stop, refused_stop, foreign_stop]); db.commit()

            arrived = arrive_cd(route.id, db=db, user=user)
            assert arrived.dock_session.arrival_cd_at is not None
            with patch("app.modules.routes.router._minutes", return_value=0):
                released = operator_release(route.id, db=db, user=user)
            assert released.status == "em_rota"
            assert released.dock_session.operator_released_at is not None
            assert released.dock_session.departure_cd_at is not None

            delivered = deliver(route.id, delivered_stop.id, DeliverIn(success=True), db=db, user=user)
            assert next(stop for stop in delivered.stops if stop.id == delivered_stop.id).status == "entregue"
            db.refresh(delivered_stop)
            assert delivered_stop.checkin_at is not None
            assert delivered_stop.delivered_at is not None

            refused = deliver(
                route.id,
                refused_stop.id,
                DeliverIn(success=False, failure_reason_id=reason.id, return_type="total", notes="Cliente recusou"),
                db=db,
                user=user,
            )
            assert next(stop for stop in refused.stops if stop.id == refused_stop.id).status == "falha"
            db.refresh(refused_stop)
            assert refused_stop.checkin_at is not None
            assert refused_stop.failure_reason_id == reason.id
            assert refused_stop.return_type == "total"
            occurrence = db.scalar(select(RouteOccurrence).where(RouteOccurrence.route_id == route.id))
            assert occurrence is not None
            assert occurrence.category == "devolucao"
            assert occurrence.status == "aberta"
            assert occurrence.driver_id == driver.id
            assert "Cliente recusou" in occurrence.description
            assert "devolução total" in occurrence.description.lower()
            history = db.scalar(select(RouteOccurrenceEvent).where(RouteOccurrenceEvent.occurrence_id == occurrence.id))
            assert history is not None
            assert history.to_status == "aberta"

            with pytest.raises(HTTPException) as denied:
                deliver(other_route.id, foreign_stop.id, DeliverIn(success=True), db=db, user=user)
            assert denied.value.status_code == 403
            assert denied.value.detail == "Rota não atribuída a este motorista."
    finally:
        engine.dispose()

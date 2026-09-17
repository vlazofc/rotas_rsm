from datetime import date, datetime, timezone
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import Attachment, Branch, DockSession, OccurrenceCategory, Route, RouteEvent, RouteStop, Tenant, User
from app.db.session import Base
from app.modules.erp_admin.router import OccurrenceIn, create_occurrence
from app.modules.routes.router import deliver, operator_release
from app.modules.routes.schemas import DeliverIn


def test_release_and_delivery_automatically_start_next_stop():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            tenant = Tenant(name="Empresa", slug="empresa")
            db.add(tenant)
            db.flush()
            branch = Branch(name="Filial", tenant_id=tenant.id)
            db.add(branch)
            db.flush()
            db.add(OccurrenceCategory(tenant_id=tenant.id, code="atraso", name="Atraso", active=True))
            user = User(
                name="Operador",
                email="operador@example.com",
                role="operador_logistico",
                tenant_id=tenant.id,
                branch_id=branch.id,
            )
            route = Route(
                tenant_id=tenant.id,
                branch_id=branch.id,
                codigo_ut="UT-AUTO",
                route_date=date.today(),
                status="liberada",
            )
            db.add_all([user, route])
            db.flush()
            loaded_photo = Attachment(bucket="tests", storage_key="loaded.jpg", content_type="image/jpeg")
            db.add(loaded_photo)
            db.flush()
            route.loaded_return_photo_attachment_id = loaded_photo.id
            db.add(DockSession(route_id=route.id, arrival_cd_at=datetime.now(timezone.utc)))
            first = RouteStop(route_id=route.id, sequence=1, customer_name="Primeiro", stop_type="carga")
            second = RouteStop(route_id=route.id, sequence=2, customer_name="Segundo", stop_type="carga")
            db.add_all([first, second])
            db.commit()

            # SQLite descarta timezone em DateTime; PostgreSQL preserva. O cálculo
            # de minutos não faz parte deste teste de progressão das paradas.
            with patch("app.modules.routes.router._minutes", return_value=0):
                released = operator_release(route.id, db=db, user=user)
            released_stops = {stop.id: stop for stop in released.stops}
            assert released.status == "em_rota"
            assert released_stops[first.id].status == "em_rota"
            assert released_stops[first.id].checkin_at is None
            assert released_stops[second.id].status == "pendente"

            create_occurrence(
                OccurrenceIn(route_id=route.id, category="atraso", description="Veículo parado na via"),
                db=db,
                user=user,
            )
            db.refresh(first)
            assert first.status == "pendente"
            assert first.checkin_at is None

            delivered = deliver(route.id, first.id, DeliverIn(success=True), db=db, user=user)
            delivered_stops = {stop.id: stop for stop in delivered.stops}
            assert delivered_stops[first.id].status == "entregue"
            assert delivered_stops[first.id].checkin_at is not None
            assert delivered_stops[second.id].status == "pendente"
            assert delivered_stops[second.id].checkin_at is None

            travel_events = db.scalars(
                select(RouteEvent)
                .where(RouteEvent.route_id == route.id, RouteEvent.event_type == "DEPARTED_TO_STOP")
                .order_by(RouteEvent.id)
            ).all()
            assert [event.stop_id for event in travel_events] == [first.id]
    finally:
        engine.dispose()

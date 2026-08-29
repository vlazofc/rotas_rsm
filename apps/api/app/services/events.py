"""Tipos de evento operacional e helper para registrar eventos auditáveis."""
from enum import Enum

from sqlalchemy.orm import Session

from sqlalchemy import select
from app.db.models import AlertRule, Notification, Route, RouteEvent, User


class EventType(str, Enum):
    ARRIVED_CD = "ARRIVED_CD"
    ENTERED_DOCK = "ENTERED_DOCK"
    LOADING_STARTED = "LOADING_STARTED"
    LOADING_FINISHED = "LOADING_FINISHED"
    OPERATOR_RELEASED = "OPERATOR_RELEASED"
    DEPARTED_CD = "DEPARTED_CD"
    ARRIVED_STOP = "ARRIVED_STOP"
    DELIVERED = "DELIVERED"
    FAILED_DELIVERY = "FAILED_DELIVERY"
    RETURN_STARTED = "RETURN_STARTED"
    RETURN_COMPLETED = "RETURN_COMPLETED"
    ROUTE_CLOSED = "ROUTE_CLOSED"
    ROUTE_REOPENED = "ROUTE_REOPENED"


def record_event(
    db: Session,
    *,
    route_id: int,
    event_type: EventType,
    user_id: int | None = None,
    stop_id: int | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    source: str = "web",
    notes: str | None = None,
) -> RouteEvent:
    event = RouteEvent(
        route_id=route_id,
        stop_id=stop_id,
        event_type=event_type.value,
        user_id=user_id,
        latitude=latitude,
        longitude=longitude,
        source=source,
        notes=notes,
    )
    db.add(event)
    db.flush()
    # Alertas in-app para eventos operacionais relevantes. Uma regra explícita
    # desativada prevalece; na ausência de configuração, falhas ficam ligadas.
    if event_type in {EventType.FAILED_DELIVERY, EventType.ROUTE_CLOSED}:
        route = db.get(Route, route_id)
        if route:
            recipients = db.scalars(select(User).where(
                User.branch_id == route.branch_id, User.active.is_(True),
                User.role.in_(["gestor_brasil", "torre_controle", "operador_logistico"]),
            )).all()
            for recipient in recipients:
                rule = db.scalar(select(AlertRule).where(AlertRule.user_id == recipient.id, AlertRule.event_type == event_type.value))
                if rule is not None and (not rule.enabled or not rule.channel_app):
                    continue
                title = "Falha de entrega" if event_type == EventType.FAILED_DELIVERY else "Rota finalizada"
                db.add(Notification(user_id=recipient.id, title=title, body=f"Rota {route.codigo_ut}", channel="app"))
    return event

"""Tipos de evento operacional e helper para registrar eventos auditáveis."""
from enum import Enum

from sqlalchemy.orm import Session

from sqlalchemy import or_, select
from app.db.models import AlertRule, Notification, Route, RouteEvent, User


class EventType(str, Enum):
    ARRIVED_CD = "ARRIVED_CD"
    ENTERED_DOCK = "ENTERED_DOCK"
    LOADING_STARTED = "LOADING_STARTED"
    LOADING_FINISHED = "LOADING_FINISHED"
    OPERATOR_RELEASED = "OPERATOR_RELEASED"
    DEPARTED_CD = "DEPARTED_CD"
    DEPARTED_TO_STOP = "DEPARTED_TO_STOP"
    ARRIVED_STOP = "ARRIVED_STOP"
    DELIVERED = "DELIVERED"
    FAILED_DELIVERY = "FAILED_DELIVERY"
    RETURN_STARTED = "RETURN_STARTED"
    RETURN_COMPLETED = "RETURN_COMPLETED"
    ROUTE_CLOSED = "ROUTE_CLOSED"
    ROUTE_REOPENED = "ROUTE_REOPENED"
    CLOSING_PHOTO_UPLOADED = "CLOSING_PHOTO_UPLOADED"


def notify_operational_audience(
    db: Session,
    *,
    route: Route,
    event_type: str,
    title: str,
    body: str,
) -> None:
    """Envia somente notificações operacionais aos responsáveis pela operação."""
    recipients = db.scalars(select(User).where(
        User.tenant_id == route.tenant_id,
        User.active.is_(True),
        User.role.in_(["admin_global", "gestor_brasil", "torre_controle", "operador_logistico"]),
        or_(User.branch_id == route.branch_id, User.branch_id.is_(None)),
    )).all()
    for recipient in recipients:
        rule = db.scalar(select(AlertRule).where(
            AlertRule.user_id == recipient.id,
            AlertRule.event_type == event_type,
        ))
        if rule is not None and (not rule.enabled or not rule.channel_app):
            continue
        db.add(Notification(
            tenant_id=route.tenant_id,
            user_id=recipient.id,
            title=title,
            body=body,
            channel="app",
        ))


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
    # Neste projeto, eventos automáticos são limitados ao início e ao fim da rota.
    if event_type in {EventType.DEPARTED_CD, EventType.ROUTE_CLOSED}:
        route = db.get(Route, route_id)
        if route:
            title = "Rota iniciada" if event_type == EventType.DEPARTED_CD else "Rota finalizada"
            notify_operational_audience(
                db,
                route=route,
                event_type=event_type.value,
                title=title,
                body=f"Rota {route.codigo_ut}",
            )
    return event

"""Tipos de evento operacional e helper para registrar eventos auditáveis."""
from enum import Enum

from sqlalchemy.orm import Session

from app.db.models import RouteEvent


class EventType(str, Enum):
    ARRIVED_CD = "ARRIVED_CD"
    ENTERED_DOCK = "ENTERED_DOCK"
    LOADING_STARTED = "LOADING_STARTED"
    LOADING_FINISHED = "LOADING_FINISHED"
    OPERATOR_RELEASED = "OPERATOR_RELEASED"
    MANIFEST_RECEIVED = "MANIFEST_RECEIVED"
    MANIFEST_VALIDATED = "MANIFEST_VALIDATED"
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
    return event

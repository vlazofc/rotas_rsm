from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AlertDismissal, AlertRule, Notification, Route, RouteOccurrence, User,
)
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services.cache import get_json, set_json
from app.core.config import settings

router = APIRouter(prefix="/notifications", tags=["notifications"])

class RuleIn(BaseModel):
    event_type: str
    enabled: bool = True
    channel_app: bool = True
    channel_push: bool = False

class DismissAlertsIn(BaseModel):
    alert_ids: list[str]

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}
OPERATIONAL_EVENT_TYPES = {"DEPARTED_CD", "ROUTE_CLOSED", "OCCURRENCE_CREATED", "OCCURRENCE_OPEN", "ROUTE_DELAYED", "ROUTE_DELAY_RISK"}
OPERATIONAL_NOTIFICATION_TITLES = {"Rota iniciada", "Rota finalizada", "Nova ocorrência registrada", "Nova foto solicitada"}
MODEL_ROLES = {
    RouteOccurrence:{"admin_global","gestor_brasil","operador_logistico","torre_controle","auditor","diretoria"},
    Route:{"admin_global","gestor_brasil","operador_logistico","torre_controle","auditor","diretoria"},
}

def _operational_today(now: datetime | None = None) -> date:
    """Data operacional no fuso configurado, independente do relógio UTC do contêiner."""
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(ZoneInfo(settings.app_timezone)).date()

def _tenant_rows(db: Session, model, user: User):
    if model in MODEL_ROLES and user.role not in MODEL_ROLES[model]: return []
    stmt = select(model)
    if user.tenant_id is not None and hasattr(model, "tenant_id"):
        stmt = stmt.where(model.tenant_id == user.tenant_id)
    if user.branch_id and hasattr(model, "branch_id") and user.role not in {"admin_global", "gestor_brasil", "diretoria", "auditor"}:
        stmt = stmt.where(model.branch_id == user.branch_id)
    return db.scalars(stmt).all()

@router.get("/live")
def live_alerts(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Alertas vivos: derivados dos dados atuais e removidos automaticamente após tratamento."""
    dismissed = set(db.scalars(select(AlertDismissal.alert_id).where(AlertDismissal.user_id == user.id)).all())
    cache_key = f"live-alerts:v2:{user.tenant_id}:{user.branch_id}:{user.role}:{user.id}"
    cached = get_json(cache_key)
    if cached is not None:
        return [item for item in cached if item.get("id") not in dismissed]
    today = _operational_today()
    now = datetime.now(timezone.utc)
    disabled = {row.event_type for row in db.scalars(select(AlertRule).where(AlertRule.user_id == user.id, AlertRule.enabled.is_(False))).all()}
    alerts: list[dict] = []
    def add(event_type: str, entity_id: int, severity: str, category: str, title: str, body: str, href: str, due: date | None = None):
        alert_id = f"{event_type}:{entity_id}"
        if event_type not in disabled and alert_id not in dismissed:
            alerts.append({"id":alert_id,"event_type":event_type,"severity":severity,"category":category,"title":title,"body":body,"href":href,"due_date":due.isoformat() if due else None})

    for occurrence in _tenant_rows(db, RouteOccurrence, user):
        if occurrence.status in {"finalizada", "cancelada"}: continue
        severity = "critical" if occurrence.severity == "critica" else "warning" if occurrence.severity == "alta" else "info"
        add("OCCURRENCE_OPEN", occurrence.id, severity, "Operação", "Ocorrência em aberto", occurrence.description[:140], "/occurrences")

    for route in _tenant_rows(db, Route, user):
        if route.excluded or route.status in {"finalizada", "cancelada"}: continue
        if route.route_date < today: add("ROUTE_DELAYED", route.id, "critical", "Rotas", "Rota não finalizada na data prevista", f"{route.codigo_ut} · prevista para {route.route_date:%d/%m/%Y}", f"/routes/{route.id}", route.route_date)
        elif route.route_date == today and route.status in {"planejada", "em_carregamento", "liberada"} and route.planned_departure_at and route.planned_departure_at < now:
            add("ROUTE_DELAY_RISK", route.id, "warning", "Rotas", "Possível atraso no início da rota", f"{route.codigo_ut} · horário planejado ultrapassado", f"/routes/{route.id}", route.route_date)

    alerts.sort(key=lambda row: (SEVERITY_ORDER[row["severity"]], row["due_date"] or "9999-12-31", row["title"]))
    result = alerts[:200]
    set_json(cache_key, result, 90)
    return result

@router.post("/actions/dismiss-live")
def dismiss_live_alerts(data: DismissAlertsIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    alert_ids = {value.strip() for value in data.alert_ids if value and len(value.strip()) <= 100}
    if not alert_ids:
        return {"dismissed": 0}
    existing = set(db.scalars(select(AlertDismissal.alert_id).where(
        AlertDismissal.user_id == user.id,
        AlertDismissal.alert_id.in_(alert_ids),
    )).all())
    for alert_id in alert_ids - existing:
        db.add(AlertDismissal(tenant_id=user.tenant_id, user_id=user.id, alert_id=alert_id))
    db.commit()
    return {"dismissed": len(alert_ids)}

@router.get("")
def list_notifications(unread_only: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(Notification).where(
        Notification.user_id == user.id,
        Notification.title.in_(OPERATIONAL_NOTIFICATION_TITLES),
    ).order_by(Notification.created_at.desc()).limit(100)
    if unread_only: stmt = stmt.where(Notification.read.is_(False))
    return db.scalars(stmt).all()

@router.post("/{notification_id}/read")
def mark_read(notification_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.get(Notification, notification_id)
    if row is None or row.user_id != user.id: raise HTTPException(404, "Notificação não encontrada.")
    row.read = True; db.commit()
    return {"read": True}

@router.post("/actions/read-all")
def read_all(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    for row in db.scalars(select(Notification).where(Notification.user_id == user.id, Notification.read.is_(False))): row.read = True
    db.commit(); return {"read": True}

@router.get("/rules")
def rules(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(select(AlertRule).where(
        AlertRule.user_id == user.id,
        AlertRule.event_type.in_(OPERATIONAL_EVENT_TYPES),
    ).order_by(AlertRule.event_type)).all()

@router.put("/rules/{event_type}")
def save_rule(event_type: str, data: RuleIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if event_type not in OPERATIONAL_EVENT_TYPES:
        raise HTTPException(400, "Somente alertas operacionais podem ser configurados.")
    row = db.scalar(select(AlertRule).where(AlertRule.user_id == user.id, AlertRule.event_type == event_type))
    if row is None: row = AlertRule(user_id=user.id, event_type=event_type); db.add(row)
    row.enabled, row.channel_app, row.channel_push = data.enabled, data.channel_app, data.channel_push
    db.commit(); db.refresh(row); return row

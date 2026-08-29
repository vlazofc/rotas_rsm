from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AlertDismissal, AlertRule, Driver, DriverSettings, FinancialAccount, MaintenanceOrder, MaintenancePlan, Notification,
    OperationalSettings, Part, PurchaseTicket, Route, RouteOccurrence, Tire, User, Vehicle, WorkflowTask,
)
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services.cache import get_json, set_json

router = APIRouter(prefix="/notifications", tags=["notifications"])

class RuleIn(BaseModel):
    event_type: str
    enabled: bool = True
    channel_app: bool = True
    channel_push: bool = False

class DismissAlertsIn(BaseModel):
    alert_ids: list[str]

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}
MODEL_ROLES = {
    FinancialAccount:{"admin_global","gestor_brasil","gestor_financeiro","auditor","diretoria"},
    MaintenanceOrder:{"admin_global","gestor_brasil","operador_logistico","torre_controle","auditor","diretoria"},
    MaintenancePlan:{"admin_global","gestor_brasil","operador_logistico","torre_controle","auditor","diretoria"},
    Tire:{"admin_global","gestor_brasil","operador_logistico","torre_controle","auditor","diretoria"},
    Part:{"admin_global","gestor_brasil","operador_logistico","auditor","diretoria"},
    Vehicle:{"admin_global","gestor_brasil","operador_logistico","torre_controle","auditor","diretoria"},
    Driver:{"admin_global","gestor_brasil","operador_logistico","torre_controle","auditor","diretoria"},
    PurchaseTicket:{"admin_global","gestor_brasil","gestor_financeiro","operador_logistico","auditor","diretoria"},
    RouteOccurrence:{"admin_global","gestor_brasil","operador_logistico","torre_controle","auditor","diretoria"},
    Route:{"admin_global","gestor_brasil","operador_logistico","torre_controle","auditor","diretoria"},
}

def _tenant_rows(db: Session, model, user: User):
    if model in MODEL_ROLES and user.role not in MODEL_ROLES[model]: return []
    stmt = select(model)
    if user.tenant_id is not None and hasattr(model, "tenant_id"):
        stmt = stmt.where(model.tenant_id == user.tenant_id)
    if user.branch_id and hasattr(model, "branch_id") and user.role not in {"admin_global", "gestor_brasil", "diretoria", "auditor"}:
        stmt = stmt.where(model.branch_id == user.branch_id)
    if model is WorkflowTask and user.role == "motorista":
        stmt = stmt.where((WorkflowTask.requester_id == user.id) | (WorkflowTask.current_assignee_id == user.id))
    return db.scalars(stmt).all()

@router.get("/live")
def live_alerts(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Alertas vivos: derivados dos dados atuais e removidos automaticamente após tratamento."""
    dismissed = set(db.scalars(select(AlertDismissal.alert_id).where(AlertDismissal.user_id == user.id)).all())
    cache_key = f"live-alerts:v1:{user.tenant_id}:{user.branch_id}:{user.role}:{user.id}"
    cached = get_json(cache_key)
    if cached is not None:
        return [item for item in cached if item.get("id") not in dismissed]
    today = date.today(); config=db.get(OperationalSettings,1) or OperationalSettings(); due_days=config.alert_due_days or 3; document_days=config.alert_document_days or 30; tire_critical=config.tire_critical_mm if config.tire_critical_mm is not None else 1.6; tire_warning=config.tire_warning_mm if config.tire_warning_mm is not None else 3.0; warning_date = today + timedelta(days=due_days); document_date = today + timedelta(days=document_days)
    disabled = {row.event_type for row in db.scalars(select(AlertRule).where(AlertRule.user_id == user.id, AlertRule.enabled.is_(False))).all()}
    alerts: list[dict] = []
    def add(event_type: str, entity_id: int, severity: str, category: str, title: str, body: str, href: str, due: date | None = None):
        alert_id = f"{event_type}:{entity_id}"
        if event_type not in disabled and alert_id not in dismissed:
            alerts.append({"id":alert_id,"event_type":event_type,"severity":severity,"category":category,"title":title,"body":body,"href":href,"due_date":due.isoformat() if due else None})

    for account in _tenant_rows(db, FinancialAccount, user):
        if account.status != "pendente": continue
        kind = "Conta a pagar" if account.kind == "payable" else "Conta a receber"
        href = f"/financial-accounts?type={'payable' if account.kind == 'payable' else 'receivable'}"
        if account.due_date < today: add("FINANCE_OVERDUE", account.id, "critical", "Financeiro", f"{kind} vencida", f"{account.description} · vencimento {account.due_date:%d/%m/%Y}", href, account.due_date)
        elif account.due_date <= warning_date: add("FINANCE_DUE", account.id, "warning", "Financeiro", f"{kind} próxima do vencimento", f"{account.description} · vence em {account.due_date:%d/%m/%Y}", href, account.due_date)

    for order in _tenant_rows(db, MaintenanceOrder, user):
        if order.status in {"concluida", "cancelada"} or not order.expected_completion_date: continue
        if order.expected_completion_date < today: add("MAINTENANCE_OVERDUE", order.id, "critical", "Frota", "Ordem de serviço atrasada", order.description, "/fleet-maintenance?tab=orders", order.expected_completion_date)
        elif order.expected_completion_date <= warning_date: add("MAINTENANCE_DUE", order.id, "warning", "Frota", "Prazo da manutenção próximo", order.description, "/fleet-maintenance?tab=orders", order.expected_completion_date)

    for plan in _tenant_rows(db, MaintenancePlan, user):
        if not plan.active or not plan.interval_days or not plan.last_done_at: continue
        due=plan.last_done_at+timedelta(days=plan.interval_days)
        if due < today:add("MAINTENANCE_PLAN_OVERDUE",plan.id,"critical","Frota","Manutenção preventiva vencida",f"{plan.service_name} · prevista para {due:%d/%m/%Y}","/fleet-maintenance?tab=plans",due)
        elif due <= warning_date:add("MAINTENANCE_PLAN_DUE",plan.id,"warning","Frota","Manutenção preventiva próxima",f"{plan.service_name} · prevista para {due:%d/%m/%Y}","/fleet-maintenance?tab=plans",due)

    for tire in _tenant_rows(db, Tire, user):
        if tire.status == "descartado": continue
        label = f"Pneu {tire.fire_number}"
        if tire.tread_depth_mm is None: add("TIRE_UNMEASURED", tire.id, "info", "Pneus", "Pneu sem medição de sulco", label, "/fleet-maintenance?tab=tires")
        elif tire.tread_depth_mm <= tire_critical: add("TIRE_CRITICAL", tire.id, "critical", "Pneus", "Sulco no limite crítico", f"{label} · {tire.tread_depth_mm:g} mm", "/fleet-maintenance?tab=tires")
        elif tire.tread_depth_mm <= tire_warning: add("TIRE_WARNING", tire.id, "warning", "Pneus", "Pneu exige acompanhamento", f"{label} · {tire.tread_depth_mm:g} mm", "/fleet-maintenance?tab=tires")

    for part in _tenant_rows(db, Part, user):
        if not part.active or part.quantity > part.minimum_quantity: continue
        severity = "critical" if part.quantity <= 0 else "warning"
        add("STOCK_LOW", part.id, severity, "Estoque", "Item sem estoque" if severity == "critical" else "Estoque abaixo do mínimo", f"{part.name}: {part.quantity:g} {part.unit} · mínimo {part.minimum_quantity:g}", "/erp?tab=stock")

    for vehicle in _tenant_rows(db, Vehicle, user):
        if not vehicle.active: continue
        if not vehicle.crlv_expiry_date:
            add("CRLV_DATE_MISSING",vehicle.id,"info","Documentos","CRLV sem data de validade",f"{vehicle.plate} · complete o cadastro documental","/config/vehicles");continue
        if vehicle.crlv_expiry_date < today: add("CRLV_EXPIRED", vehicle.id, "critical", "Documentos", "CRLV vencido", f"{vehicle.plate} · venceu em {vehicle.crlv_expiry_date:%d/%m/%Y}", "/config/vehicles", vehicle.crlv_expiry_date)
        elif vehicle.crlv_expiry_date <= document_date: add("CRLV_DUE", vehicle.id, "warning", "Documentos", "CRLV próximo do vencimento", f"{vehicle.plate} · vence em {vehicle.crlv_expiry_date:%d/%m/%Y}", "/config/vehicles", vehicle.crlv_expiry_date)

    settings = db.scalar(select(DriverSettings).where(DriverSettings.tenant_id == user.tenant_id)) if user.tenant_id else None
    for driver in _tenant_rows(db, Driver, user):
        if not driver.active: continue
        deadlines = [("CNH", driver.cnh_expiry_date, settings.cnh_alert_days if settings else 30), ("RNTRC/ANTT", driver.antt_expiry_date, settings.antt_alert_days if settings else 30)]
        for document, due, days in deadlines:
            if not due:
                if document=="CNH":add("DRIVER_CNH_DATE_MISSING",driver.id,"info","Motoristas","CNH sem data de validade",f"{driver.name} · complete o cadastro documental","/config/drivers")
                continue
            if due < today: add(f"DRIVER_{document}_EXPIRED", driver.id, "critical", "Motoristas", f"{document} vencida", f"{driver.name} · venceu em {due:%d/%m/%Y}", "/config/drivers", due)
            elif due <= today + timedelta(days=days): add(f"DRIVER_{document}_DUE", driver.id, "warning", "Motoristas", f"{document} próxima do vencimento", f"{driver.name} · vence em {due:%d/%m/%Y}", "/config/drivers", due)
        if not driver.registration_updated_at:add("DRIVER_REGISTRATION_MISSING",driver.id,"info","Motoristas","Cadastro do motorista sem data-base",driver.name,"/config/drivers")
        else:
            renewal=driver.registration_updated_at+timedelta(days=(settings.registration_renewal_months if settings else 12)*30);days=settings.registration_alert_days if settings else 30
            if renewal<today:add("DRIVER_REGISTRATION_EXPIRED",driver.id,"critical","Motoristas","Renovação cadastral vencida",f"{driver.name} · prevista para {renewal:%d/%m/%Y}","/config/drivers",renewal)
            elif renewal<=today+timedelta(days=days):add("DRIVER_REGISTRATION_DUE",driver.id,"warning","Motoristas","Renovação cadastral próxima",f"{driver.name} · prevista para {renewal:%d/%m/%Y}","/config/drivers",renewal)

    for purchase in _tenant_rows(db, PurchaseTicket, user):
        if purchase.status != "comprada" or not purchase.delivery_due_date: continue
        if purchase.delivery_due_date < today: add("PURCHASE_OVERDUE", purchase.id, "critical", "Compras", "Entrega de compra atrasada", f"{purchase.ticket} · {purchase.description[:100]}", "/purchases", purchase.delivery_due_date)
        elif purchase.delivery_due_date <= warning_date: add("PURCHASE_DUE", purchase.id, "warning", "Compras", "Entrega de compra próxima", f"{purchase.ticket} · previsão {purchase.delivery_due_date:%d/%m/%Y}", "/purchases", purchase.delivery_due_date)

    for occurrence in _tenant_rows(db, RouteOccurrence, user):
        if occurrence.status in {"finalizada", "cancelada"}: continue
        if occurrence.severity in {"critica", "alta"}: add("OCCURRENCE_HIGH", occurrence.id, "critical" if occurrence.severity == "critica" else "warning", "Operação", "Ocorrência crítica em aberto" if occurrence.severity == "critica" else "Ocorrência de alta prioridade", occurrence.description[:140], "/occurrences")

    for task in _tenant_rows(db, WorkflowTask, user):
        if task.status in {"closed", "finalized"}: continue
        if task.priority <= 1 or task.status == "returned": add("TASK_PRIORITY", task.id, "critical" if task.priority == 0 else "warning", "Tarefas", "Tarefa prioritária exige ação" if task.status != "returned" else "Tarefa devolvida exige revisão", task.title, "/tasks")

    for route in _tenant_rows(db, Route, user):
        if route.excluded or route.status in {"finalizada", "cancelada"}: continue
        if route.route_date < today: add("ROUTE_DELAYED", route.id, "critical", "Rotas", "Rota não finalizada na data prevista", f"{route.codigo_ut} · prevista para {route.route_date:%d/%m/%Y}", f"/routes/{route.id}", route.route_date)
        elif route.route_date == today and (not route.driver_id or not route.vehicle_id): add("ROUTE_RESOURCE_MISSING", route.id, "warning", "Rotas", "Rota de hoje sem recurso definido", f"{route.codigo_ut} · confira motorista e veículo", f"/routes/{route.id}", route.route_date)

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
    stmt = select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(100)
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
    return db.scalars(select(AlertRule).where(AlertRule.user_id == user.id).order_by(AlertRule.event_type)).all()

@router.put("/rules/{event_type}")
def save_rule(event_type: str, data: RuleIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.scalar(select(AlertRule).where(AlertRule.user_id == user.id, AlertRule.event_type == event_type))
    if row is None: row = AlertRule(user_id=user.id, event_type=event_type); db.add(row)
    row.enabled, row.channel_app, row.channel_push = data.enabled, data.channel_app, data.channel_push
    db.commit(); db.refresh(row); return row

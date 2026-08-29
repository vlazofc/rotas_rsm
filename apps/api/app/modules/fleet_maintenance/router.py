"""Frota técnica: pneus (com histórico de sulco/CPK) e manutenção (planos + ordens de serviço).

Módulo aditivo — não altera nada do fluxo de rotas/doca já existente. Reaproveita
Vehicle, Attachment (MinIO) e o padrão de RBAC/auditoria já usado em vehicles/drivers.
"""
import re
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import Role, require_branch_access, require_roles, require_same_branch
from app.db.models import Attachment, Branch, Expense, FinancialAccount, MaintenanceOrder, MaintenancePlan, ServiceProvider, Tire, TireInspection, User, Vehicle
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services import storage
from app.services.audit import log, log_update, snapshot
from app.services.accounting import post_expense

router = APIRouter(prefix="/fleet-maintenance", tags=["fleet-maintenance"])

_MANAGER = require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL)
TIRE_STATUSES = {"novo", "em_uso", "recapado", "descartado"}
ORDER_KINDS = {"preventiva", "corretiva"}
ORDER_STATUSES = {"aberta", "em_andamento", "concluida", "cancelada"}
ALLOWED_ATTACHMENT_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/jpg", "image/webp"}
EXTENSION_TYPES = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TireIn(BaseModel):
    branch_id: int
    vehicle_id: int | None = None
    fire_number: str
    brand: str | None = None
    model: str | None = None
    position: str | None = None
    status: str = "novo"
    tread_depth_mm: float | None = None
    install_date: date | None = None
    install_km: float | None = None
    recap_count: int = 0
    cost: Decimal | None = None


class TireUpdate(BaseModel):
    vehicle_id: int | None = None
    brand: str | None = None
    model: str | None = None
    position: str | None = None
    status: str | None = None
    tread_depth_mm: float | None = None
    install_date: date | None = None
    install_km: float | None = None
    recap_count: int | None = None
    cost: Decimal | None = None
    active: bool | None = None


class TireMoveIn(BaseModel):
    vehicle_id: int | None = None
    position: str | None = None


class TireOut(BaseModel):
    id: int
    branch_id: int
    vehicle_id: int | None
    vehicle_plate: str | None = None
    fire_number: str
    brand: str | None
    model: str | None
    position: str | None
    status: str
    tread_depth_mm: float | None
    install_date: date | None
    install_km: float | None
    recap_count: int
    cost: Decimal | None
    active: bool
    latest_odometer_km: float | None = None
    km_rodado: float | None = None
    cpk: float | None = None

    class Config:
        from_attributes = True


class TireInspectionIn(BaseModel):
    inspected_at: date
    odometer_km: float | None = None
    tread_depth_mm: float | None = None
    notes: str | None = None


class TireInspectionOut(BaseModel):
    id: int
    tire_id: int
    inspected_at: date
    odometer_km: float | None
    tread_depth_mm: float | None
    notes: str | None

    class Config:
        from_attributes = True


class MaintenancePlanIn(BaseModel):
    branch_id: int
    vehicle_id: int
    service_name: str
    interval_km: float | None = None
    interval_days: int | None = None
    last_done_at: date | None = None
    last_done_km: float | None = None


class MaintenancePlanUpdate(BaseModel):
    vehicle_id: int | None = None
    service_name: str | None = None
    interval_km: float | None = None
    interval_days: int | None = None
    last_done_at: date | None = None
    last_done_km: float | None = None
    active: bool | None = None


class MaintenancePlanOut(BaseModel):
    id: int
    branch_id: int
    vehicle_id: int
    vehicle_plate: str | None = None
    service_name: str
    interval_km: float | None
    interval_days: int | None
    last_done_at: date | None
    last_done_km: float | None
    active: bool
    due: bool = False

    class Config:
        from_attributes = True


class MaintenanceOrderUpdate(BaseModel):
    vehicle_id: int | None = None
    plan_id: int | None = None
    kind: str | None = None
    status: str | None = None
    description: str | None = None
    opened_at: date | None = None
    odometer_km: float | None = None
    cost: Decimal | None = None
    closed_at: date | None = None
    expected_completion_date: date | None = None
    provider_id: int | None = None


class MaintenanceOrderOut(BaseModel):
    id: int
    branch_id: int
    vehicle_id: int
    vehicle_plate: str | None = None
    plan_id: int | None
    provider_id: int | None = None
    provider_name: str | None = None
    kind: str
    status: str
    description: str
    opened_at: date
    closed_at: date | None
    expected_completion_date: date | None = None
    sla_status: str = "pending"
    sla_days_remaining: int | None = None
    odometer_km: float | None
    cost: Decimal | None
    attachment_filename: str | None = None
    attachment_url: str | None = None
    attachment_id: int | None = None
    budget_filename: str | None = None
    budget_url: str | None = None
    budget_attachment_id: int | None = None
    approval_status: str
    approved_by_name: str | None = None
    approved_at: datetime | None = None
    expense_id: int | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class ApprovalIn(BaseModel):
    notes: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_filename(filename: str | None) -> str:
    name = Path(filename or "anexo").name
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:120] or "anexo"


def _resolve_content_type(file: UploadFile) -> str:
    content_type = file.content_type or "application/octet-stream"
    if content_type in ALLOWED_ATTACHMENT_TYPES:
        return content_type
    if content_type == "application/octet-stream":
        guessed = EXTENSION_TYPES.get(Path(file.filename or "").suffix.lower())
        if guessed:
            return guessed
    raise HTTPException(status_code=415, detail=f"Tipo de anexo não suportado: {content_type}")


async def _save_attachment(file: UploadFile, branch_id: int, when: date, folder: str) -> Attachment:
    content_type = _resolve_content_type(file)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Anexo vazio.")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Arquivo acima de {settings.max_upload_mb} MB.")
    storage.ensure_buckets()
    key = f"{folder}/{branch_id}/{when.strftime('%Y-%m')}/{uuid.uuid4().hex}-{_safe_filename(file.filename)}"
    storage.put_object(settings.minio_bucket_proofs, key, data, content_type)
    return Attachment(bucket=settings.minio_bucket_proofs, storage_key=key, content_type=content_type, size_bytes=len(data))


def _tenant_scoped(stmt, model, user: User):
    """Modelos antigos conservam branch_id, mas o acesso e por empresa."""
    if user.role != Role.ADMIN_GLOBAL.value and user.tenant_id is not None:
        stmt = stmt.join(Branch, Branch.id == model.branch_id).where(Branch.tenant_id == user.tenant_id)
    return stmt


def _tire_query(user: User):
    stmt = select(Tire)
    return _tenant_scoped(stmt, Tire, user)


def _serialize_tire(tire: Tire, db: Session) -> TireOut:
    latest = db.scalar(
        select(TireInspection)
        .where(TireInspection.tire_id == tire.id, TireInspection.odometer_km.is_not(None))
        .order_by(TireInspection.inspected_at.desc(), TireInspection.id.desc())
    )
    latest_km = latest.odometer_km if latest else None
    km_rodado = (latest_km - tire.install_km) if (latest_km is not None and tire.install_km is not None) else None
    cpk = float(tire.cost) / km_rodado if (km_rodado and km_rodado > 0 and tire.cost is not None) else None
    out = TireOut.model_validate(tire)
    out.vehicle_plate = tire.vehicle.plate if tire.vehicle else None
    out.latest_odometer_km = latest_km
    out.km_rodado = km_rodado
    out.cpk = round(cpk, 4) if cpk is not None else None
    return out


def _plan_due(plan: MaintenancePlan, latest_km: float | None) -> bool:
    if plan.interval_days and plan.last_done_at:
        if (date.today() - plan.last_done_at).days >= plan.interval_days:
            return True
    if plan.interval_km is not None and plan.last_done_km is not None and latest_km is not None:
        if (latest_km - plan.last_done_km) >= plan.interval_km:
            return True
    return False


def _latest_vehicle_km(db: Session, vehicle_id: int) -> float | None:
    latest = db.scalar(
        select(TireInspection.odometer_km)
        .join(Tire, Tire.id == TireInspection.tire_id)
        .where(Tire.vehicle_id == vehicle_id, TireInspection.odometer_km.is_not(None))
        .order_by(TireInspection.inspected_at.desc(), TireInspection.id.desc())
    )
    if latest is not None:
        return latest
    return db.scalar(
        select(MaintenanceOrder.odometer_km)
        .where(MaintenanceOrder.vehicle_id == vehicle_id, MaintenanceOrder.odometer_km.is_not(None))
        .order_by(MaintenanceOrder.opened_at.desc(), MaintenanceOrder.id.desc())
    )


def _serialize_plan(plan: MaintenancePlan, db: Session) -> MaintenancePlanOut:
    out = MaintenancePlanOut.model_validate(plan)
    out.vehicle_plate = plan.vehicle.plate if plan.vehicle else None
    out.due = _plan_due(plan, _latest_vehicle_km(db, plan.vehicle_id))
    return out


def _serialize_order(order: MaintenanceOrder) -> MaintenanceOrderOut:
    out = MaintenanceOrderOut.model_validate(order)
    out.vehicle_plate = order.vehicle.plate if order.vehicle else None
    out.provider_name = order.provider.name if order.provider else None
    out.approved_by_name = order.approved_by_user.name if order.approved_by_user else None
    out.expense_id = order.expense.id if order.expense else None
    if order.expected_completion_date:
        reference=order.closed_at or date.today();remaining=(order.expected_completion_date-reference).days
        out.sla_days_remaining=remaining
        out.sla_status="overdue" if remaining<0 else "attention" if not order.closed_at and remaining<=2 else "on_time"
    if order.attachment:
        out.attachment_id = order.attachment.id
        out.attachment_filename = Path(order.attachment.storage_key).name.split("-", 1)[-1]
        out.attachment_url = storage.get_presigned_url(order.attachment.bucket, order.attachment.storage_key)
    if order.budget_attachment:
        out.budget_attachment_id = order.budget_attachment.id
        out.budget_filename = Path(order.budget_attachment.storage_key).name.split("-", 1)[-1]
        out.budget_url = storage.get_presigned_url(order.budget_attachment.bucket, order.budget_attachment.storage_key)
    return out


# ---------------------------------------------------------------------------
# Pneus
# ---------------------------------------------------------------------------

@router.get("/tires", response_model=list[TireOut])
def list_tires(vehicle_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = _tire_query(user).order_by(Tire.fire_number)
    if vehicle_id:
        stmt = stmt.where(Tire.vehicle_id == vehicle_id)
    return [_serialize_tire(t, db) for t in db.scalars(stmt).all()]


@router.post("/tires", response_model=TireOut, dependencies=[Depends(_MANAGER)])
def create_tire(data: TireIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    require_branch_access(db, actor, data.branch_id)
    if data.status not in TIRE_STATUSES:
        raise HTTPException(status_code=400, detail="Status de pneu inválido.")
    tire = Tire(**data.model_dump())
    db.add(tire)
    db.flush()
    log(db, user_id=actor.id, action="create", entity="tire", entity_id=tire.id, detail=f'fogo: "{tire.fire_number}"')
    db.commit()
    db.refresh(tire)
    return _serialize_tire(tire, db)


@router.put("/tires/{tire_id}", response_model=TireOut, dependencies=[Depends(_MANAGER)])
def update_tire(tire_id: int, data: TireUpdate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    tire = db.get(Tire, tire_id)
    if tire is None:
        raise HTTPException(status_code=404, detail="Pneu não encontrado.")
    require_same_branch(actor, tire.branch_id)
    updates = data.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] not in TIRE_STATUSES:
        raise HTTPException(status_code=400, detail="Status de pneu inválido.")
    before = snapshot(tire, list(updates))
    for field, value in updates.items():
        setattr(tire, field, value)
    log_update(db, user_id=actor.id, entity="tire", entity_id=tire.id, before=before, obj=tire, updates=updates)
    db.commit()
    db.refresh(tire)
    return _serialize_tire(tire, db)


@router.post("/tires/{tire_id}/move", response_model=list[TireOut], dependencies=[Depends(_MANAGER)])
def move_tire(tire_id: int, data: TireMoveIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    """Move um pneu entre estoque/veículo e troca atomicamente posições ocupadas."""
    tire = db.get(Tire, tire_id)
    if tire is None:
        raise HTTPException(status_code=404, detail="Pneu não encontrado.")
    require_same_branch(actor, tire.branch_id)
    if (data.vehicle_id is None) != (data.position is None):
        raise HTTPException(status_code=422, detail="Para estoque, veículo e posição devem ficar vazios.")
    if data.vehicle_id is not None:
        vehicle = db.get(Vehicle, data.vehicle_id)
        if vehicle is None:
            raise HTTPException(status_code=422, detail="Veículo não encontrado.")
        require_same_branch(actor, vehicle.branch_id)

    origin_vehicle, origin_position = tire.vehicle_id, tire.position
    occupied = None
    if data.vehicle_id is not None:
        occupied = db.scalar(
            select(Tire).where(
                Tire.id != tire.id,
                Tire.vehicle_id == data.vehicle_id,
                Tire.position == data.position,
                Tire.active.is_(True),
                Tire.status != "descartado",
            )
        )

    moved = [tire]
    if occupied:
        # De estoque para uma vaga ocupada: o pneu retirado retorna ao estoque.
        # Entre posições instaladas: os dois pneus simplesmente trocam de lugar.
        occupied.vehicle_id = origin_vehicle
        occupied.position = origin_position
        occupied.status = "em_uso" if origin_vehicle is not None else "novo"
        moved.append(occupied)
        log(db, user_id=actor.id, action="swap", entity="tire", entity_id=occupied.id,
            detail=f"com_pneu={tire.fire_number}; destino={origin_vehicle or 'estoque'}:{origin_position or '-'}")

    tire.vehicle_id = data.vehicle_id
    tire.position = data.position
    tire.status = "em_uso" if data.vehicle_id is not None else "novo"
    log(db, user_id=actor.id, action="move", entity="tire", entity_id=tire.id,
        detail=f"de={origin_vehicle or 'estoque'}:{origin_position or '-'}; para={data.vehicle_id or 'estoque'}:{data.position or '-'}")
    db.commit()
    for item in moved: db.refresh(item)
    return [_serialize_tire(item, db) for item in moved]


@router.delete("/tires/{tire_id}", dependencies=[Depends(_MANAGER)])
def delete_tire(tire_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    tire = db.get(Tire, tire_id)
    if tire is None:
        raise HTTPException(status_code=404, detail="Pneu não encontrado.")
    require_same_branch(actor, tire.branch_id)
    fire_number = tire.fire_number
    db.delete(tire)
    log(db, user_id=actor.id, action="delete", entity="tire", entity_id=tire_id, detail=f'fogo: "{fire_number}"')
    db.commit()
    return {"deleted": tire_id}


@router.get("/tires/{tire_id}/inspections", response_model=list[TireInspectionOut])
def list_tire_inspections(tire_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tire = db.get(Tire, tire_id)
    if tire is None:
        raise HTTPException(status_code=404, detail="Pneu não encontrado.")
    require_same_branch(user, tire.branch_id)
    stmt = select(TireInspection).where(TireInspection.tire_id == tire_id).order_by(TireInspection.inspected_at.desc())
    return db.scalars(stmt).all()


@router.post("/tires/{tire_id}/inspections", response_model=TireInspectionOut, dependencies=[Depends(_MANAGER)])
def create_tire_inspection(tire_id: int, data: TireInspectionIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    tire = db.get(Tire, tire_id)
    if tire is None:
        raise HTTPException(status_code=404, detail="Pneu não encontrado.")
    require_same_branch(actor, tire.branch_id)
    inspection = TireInspection(tire_id=tire_id, recorded_by=actor.id, **data.model_dump())
    db.add(inspection)
    if data.tread_depth_mm is not None:
        tire.tread_depth_mm = data.tread_depth_mm
    log(db, user_id=actor.id, action="create", entity="tire_inspection", entity_id=tire_id)
    db.commit()
    db.refresh(inspection)
    return inspection


# ---------------------------------------------------------------------------
# Planos de manutenção preventiva
# ---------------------------------------------------------------------------

@router.get("/maintenance-plans", response_model=list[MaintenancePlanOut])
def list_maintenance_plans(vehicle_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(MaintenancePlan).order_by(MaintenancePlan.service_name)
    stmt = _tenant_scoped(stmt, MaintenancePlan, user)
    if vehicle_id:
        stmt = stmt.where(MaintenancePlan.vehicle_id == vehicle_id)
    return [_serialize_plan(p, db) for p in db.scalars(stmt).all()]


@router.post("/maintenance-plans", response_model=MaintenancePlanOut, dependencies=[Depends(_MANAGER)])
def create_maintenance_plan(data: MaintenancePlanIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    require_branch_access(db, actor, data.branch_id)
    if not data.interval_km and not data.interval_days:
        raise HTTPException(status_code=400, detail="Informe intervalo por km e/ou por dias.")
    plan = MaintenancePlan(**data.model_dump())
    db.add(plan)
    db.flush()
    log(db, user_id=actor.id, action="create", entity="maintenance_plan", entity_id=plan.id, detail=f'"{plan.service_name}"')
    db.commit()
    db.refresh(plan)
    return _serialize_plan(plan, db)


@router.put("/maintenance-plans/{plan_id}", response_model=MaintenancePlanOut, dependencies=[Depends(_MANAGER)])
def update_maintenance_plan(plan_id: int, data: MaintenancePlanUpdate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    plan = db.get(MaintenancePlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plano não encontrado.")
    require_same_branch(actor, plan.branch_id)
    updates = data.model_dump(exclude_unset=True)
    if "vehicle_id" in updates:
        vehicle = db.get(Vehicle, updates["vehicle_id"])
        if vehicle is None: raise HTTPException(status_code=404, detail="Veículo não encontrado.")
        require_same_branch(actor, vehicle.branch_id)
    interval_km = updates.get("interval_km", plan.interval_km)
    interval_days = updates.get("interval_days", plan.interval_days)
    if not interval_km and not interval_days: raise HTTPException(status_code=400, detail="Informe intervalo por km e/ou por dias.")
    before = snapshot(plan, list(updates))
    for field, value in updates.items():
        setattr(plan, field, value)
    log_update(db, user_id=actor.id, entity="maintenance_plan", entity_id=plan.id, before=before, obj=plan, updates=updates)
    db.commit()
    db.refresh(plan)
    return _serialize_plan(plan, db)


@router.delete("/maintenance-plans/{plan_id}", dependencies=[Depends(_MANAGER)])
def delete_maintenance_plan(plan_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    plan = db.get(MaintenancePlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plano não encontrado.")
    require_same_branch(actor, plan.branch_id)
    name = plan.service_name
    db.delete(plan)
    log(db, user_id=actor.id, action="delete", entity="maintenance_plan", entity_id=plan_id, detail=f'"{name}"')
    db.commit()
    return {"deleted": plan_id}


# ---------------------------------------------------------------------------
# Ordens de serviço
# ---------------------------------------------------------------------------

@router.get("/maintenance-orders", response_model=list[MaintenanceOrderOut])
def list_maintenance_orders(
    vehicle_id: int | None = None, status: str | None = None,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    stmt = select(MaintenanceOrder).order_by(MaintenanceOrder.opened_at.desc(), MaintenanceOrder.id.desc())
    stmt = _tenant_scoped(stmt, MaintenanceOrder, user)
    if vehicle_id:
        stmt = stmt.where(MaintenanceOrder.vehicle_id == vehicle_id)
    if status:
        stmt = stmt.where(MaintenanceOrder.status == status)
    return [_serialize_order(o) for o in db.scalars(stmt).all()]


@router.post("/maintenance-orders", response_model=MaintenanceOrderOut, dependencies=[Depends(_MANAGER)])
async def create_maintenance_order(
    branch_id: int = Form(...),
    vehicle_id: int = Form(...),
    plan_id: int | None = Form(None),
    provider_id: int | None = Form(None),
    kind: str = Form("corretiva"),
    description: str = Form(...),
    opened_at: date = Form(...),
    expected_completion_date: date = Form(...),
    odometer_km: float | None = Form(None),
    cost: Decimal | None = Form(None),
    attachment: UploadFile | None = File(None),
    budget: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    require_branch_access(db, actor, branch_id)
    if kind not in ORDER_KINDS:
        raise HTTPException(status_code=400, detail="Tipo de ordem inválido.")
    if expected_completion_date < opened_at:
        raise HTTPException(status_code=422, detail="A previsão de conclusão não pode ser anterior à abertura.")
    if db.get(Vehicle, vehicle_id) is None:
        raise HTTPException(status_code=404, detail="Veículo não encontrado.")
    if provider_id is not None and db.get(ServiceProvider, provider_id) is None:
        raise HTTPException(status_code=404, detail="Prestador não encontrado.")

    attachment_obj = None
    if attachment is not None and attachment.filename:
        attachment_obj = await _save_attachment(attachment, branch_id, opened_at, "manutencao")
        db.add(attachment_obj)
        db.flush()

    budget_obj = None
    if budget is not None and budget.filename:
        budget_obj = await _save_attachment(budget, branch_id, opened_at, "manutencao/orcamentos")
        db.add(budget_obj)
        db.flush()

    order = MaintenanceOrder(
        branch_id=branch_id, vehicle_id=vehicle_id, plan_id=plan_id, provider_id=provider_id, kind=kind,
        description=description, opened_at=opened_at, expected_completion_date=expected_completion_date, odometer_km=odometer_km, cost=cost,
        attachment_id=attachment_obj.id if attachment_obj else None,
        budget_attachment_id=budget_obj.id if budget_obj else None,
        approval_status="pendente",
        created_by=actor.id,
    )
    db.add(order)
    db.flush()
    log(db, user_id=actor.id, action="create", entity="maintenance_order", entity_id=order.id)
    db.commit()
    db.refresh(order)
    return _serialize_order(order)


@router.put("/maintenance-orders/{order_id}", response_model=MaintenanceOrderOut, dependencies=[Depends(_MANAGER)])
def update_maintenance_order(order_id: int, data: MaintenanceOrderUpdate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    order = db.get(MaintenanceOrder, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Ordem de serviço não encontrada.")
    require_same_branch(actor, order.branch_id)
    updates = data.model_dump(exclude_unset=True)
    effective_opened = updates.get("opened_at", order.opened_at)
    effective_expected = updates.get("expected_completion_date", order.expected_completion_date)
    if effective_expected is not None and effective_expected < effective_opened:
        raise HTTPException(status_code=422, detail="A previsão de conclusão não pode ser anterior à abertura.")
    if "kind" in updates and updates["kind"] not in ORDER_KINDS:
        raise HTTPException(status_code=400, detail="Tipo de ordem inválido.")
    if "status" in updates and updates["status"] not in ORDER_STATUSES:
        raise HTTPException(status_code=400, detail="Status de ordem inválido.")
    if "vehicle_id" in updates:
        vehicle = db.get(Vehicle, updates["vehicle_id"])
        if vehicle is None: raise HTTPException(status_code=404, detail="Veículo não encontrado.")
        require_same_branch(actor, vehicle.branch_id)
    if updates.get("plan_id") is not None:
        plan = db.get(MaintenancePlan, updates["plan_id"])
        if plan is None: raise HTTPException(status_code=404, detail="Plano não encontrado.")
        require_same_branch(actor, plan.branch_id)
        target_vehicle_id = updates.get("vehicle_id", order.vehicle_id)
        if plan.vehicle_id != target_vehicle_id: raise HTTPException(status_code=409, detail="O plano não pertence ao veículo selecionado.")
    if updates.get("provider_id") is not None and db.get(ServiceProvider, updates["provider_id"]) is None:
        raise HTTPException(status_code=404, detail="Prestador não encontrado.")
    if updates.get("status") == "concluida" and order.approval_status != "aprovado":
        raise HTTPException(
            status_code=409,
            detail="Esta ordem precisa ser aprovada antes da conclusão.",
        )
    before = snapshot(order, list(updates))
    if order.approval_status == "aprovado" and any(field in updates and updates[field] != getattr(order, field) for field in {"cost", "provider_id", "vehicle_id", "opened_at"}):
        _remove_linked_expense(db, order, actor, "dados financeiros da OS alterados; nova aprovação necessária")
        order.approval_status, order.approved_by, order.approved_at = "pendente", None, None
        log(db, user_id=actor.id, action="invalidate_approval", entity="maintenance_order", entity_id=order.id, detail="Alteração em custo/prestador/veículo/data")
    for field, value in updates.items():
        setattr(order, field, value)
    if updates.get("status") == "concluida":
        order.closed_at = order.closed_at or date.today()
        if order.plan_id:
            plan = db.get(MaintenancePlan, order.plan_id)
            if plan:
                plan.last_done_at = order.closed_at
                plan.last_done_km = order.odometer_km or plan.last_done_km
    log_update(db, user_id=actor.id, entity="maintenance_order", entity_id=order.id, before=before, obj=order, updates=updates)
    db.commit()
    db.refresh(order)
    return _serialize_order(order)


_APPROVER = require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL)

def _linked_expense(db: Session, order_id: int) -> Expense | None:
    return db.scalar(select(Expense).where(Expense.maintenance_order_id == order_id))

def _remove_linked_expense(db: Session, order: MaintenanceOrder, actor: User, reason: str) -> None:
    expense = _linked_expense(db, order.id)
    if expense is not None:
        expense_id = expense.id
        db.delete(expense)
        log(db, user_id=actor.id, action="delete", entity="expense", entity_id=expense_id, detail=f"OS #{order.id}: {reason}")


@router.post("/maintenance-orders/{order_id}/budget", response_model=MaintenanceOrderOut, dependencies=[Depends(_MANAGER)])
async def upload_order_budget(order_id: int, budget: UploadFile = File(...), db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    order = db.get(MaintenanceOrder, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Ordem de serviço não encontrada.")
    require_same_branch(actor, order.branch_id)
    _remove_linked_expense(db, order, actor, "novo orçamento anexado; aprovação invalidada")
    budget_obj = await _save_attachment(budget, order.branch_id, order.opened_at, "manutencao/orcamentos")
    db.add(budget_obj)
    db.flush()
    order.budget_attachment_id = budget_obj.id
    order.approval_status = "pendente"
    order.approved_by = None
    order.approved_at = None
    log(db, user_id=actor.id, action="upload_budget", entity="maintenance_order", entity_id=order.id, detail="status=pendente")
    db.commit()
    db.refresh(order)
    return _serialize_order(order)


@router.post("/maintenance-orders/{order_id}/approve", response_model=MaintenanceOrderOut, dependencies=[Depends(_APPROVER)])
def approve_order(order_id: int, data: ApprovalIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    order = db.get(MaintenanceOrder, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Ordem de serviço não encontrada.")
    require_same_branch(actor, order.branch_id)
    if order.budget_attachment_id is None:
        raise HTTPException(status_code=409, detail="Ordem não tem orçamento anexado para homologar.")
    if order.cost is None or order.cost <= 0:
        raise HTTPException(status_code=409, detail="Informe o custo da OS antes da aprovação financeira.")
    previous_status = order.approval_status
    order.approval_status = "aprovado"
    order.approved_by = actor.id
    order.approved_at = datetime.now(timezone.utc)
    expense = _linked_expense(db, order.id)
    if expense is None:
        expense = Expense(
            branch_id=order.branch_id, driver_id=None, vehicle_id=order.vehicle_id, user_id=actor.id,
            expense_date=order.opened_at, reason="manutencao", amount=order.cost,
            notes=f"Gerada pela aprovação da OS #{order.id}. {data.notes or ''}".strip(),
            attachment_id=order.budget_attachment_id, odometer_km=order.odometer_km,
            source="maintenance_order", maintenance_order_id=order.id,
            approval_status="approved", submitted_at=datetime.now(timezone.utc),
            reviewed_by_id=actor.id, reviewed_at=datetime.now(timezone.utc),
            decision_note="Aprovada pelo fluxo financeiro da OS.",
        )
        db.add(expense); db.flush()
        log(db, user_id=actor.id, action="create", entity="expense", entity_id=expense.id, detail=f"OS #{order.id}; valor={order.cost}")
    else:
        expense.vehicle_id, expense.expense_date, expense.amount = order.vehicle_id, order.opened_at, order.cost
        expense.attachment_id, expense.odometer_km = order.budget_attachment_id, order.odometer_km
        expense.approval_status, expense.reviewed_by_id = "approved", actor.id
        expense.reviewed_at, expense.decision_note = datetime.now(timezone.utc), "Aprovada pelo fluxo financeiro da OS."
        log(db, user_id=actor.id, action="update", entity="expense", entity_id=expense.id, detail=f"Sincronizada pela OS #{order.id}; valor={order.cost}")
    account = db.scalar(select(FinancialAccount).where(FinancialAccount.expense_id == expense.id))
    if account is None:
        account = FinancialAccount(
            branch_id=order.branch_id, kind="payable", description=f"OS #{order.id} · manutenção",
            counterparty="Prestador da ordem de serviço", category="manutencao",
            document=f"OS-{order.id}", issue_date=order.opened_at, due_date=order.opened_at,
            amount=order.cost, status="pendente", notes=data.notes, created_by=actor.id, expense_id=expense.id,
        )
        db.add(account); db.flush()
    post_expense(db, expense, actor.id)
    log(db, user_id=actor.id, action="approve", entity="maintenance_order", entity_id=order.id, detail=f"de={previous_status}; despesa={expense.id}; valor={order.cost}; notas={data.notes or '-'}")
    db.commit()
    db.refresh(order)
    return _serialize_order(order)


@router.post("/maintenance-orders/{order_id}/reject", response_model=MaintenanceOrderOut, dependencies=[Depends(_APPROVER)])
def reject_order(order_id: int, data: ApprovalIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    order = db.get(MaintenanceOrder, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Ordem de serviço não encontrada.")
    require_same_branch(actor, order.branch_id)
    if order.budget_attachment_id is None:
        raise HTTPException(status_code=409, detail="Ordem não tem orçamento anexado para homologar.")
    previous_status = order.approval_status
    _remove_linked_expense(db, order, actor, "aprovação da OS rejeitada")
    order.approval_status = "rejeitado"
    order.approved_by = actor.id
    order.approved_at = datetime.now(timezone.utc)
    log(db, user_id=actor.id, action="reject", entity="maintenance_order", entity_id=order.id, detail=f"de={previous_status}; notas={data.notes or '-'}")
    db.commit()
    db.refresh(order)
    return _serialize_order(order)


@router.delete("/maintenance-orders/{order_id}", dependencies=[Depends(_MANAGER)])
def delete_maintenance_order(order_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    order = db.get(MaintenanceOrder, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Ordem de serviço não encontrada.")
    require_same_branch(actor, order.branch_id)
    _remove_linked_expense(db, order, actor, "OS excluída")
    db.delete(order)
    log(db, user_id=actor.id, action="delete", entity="maintenance_order", entity_id=order_id)
    db.commit()
    return {"deleted": order_id}

import io
import re
import uuid
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font
from pydantic import BaseModel
from dateutil.relativedelta import relativedelta
from sqlalchemy import extract, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import (
    FINANCE_EXPENSE_APPROVE, FINANCE_EXPENSE_CREATE, FINANCE_VIEW, Role, has_permission, require_feature,
    require_permission, require_roles, require_same_branch,
)
from app.db.models import Attachment, Driver, Expense, ExpenseApprovalEvent, FinancialAccount, FinancialCategory, Notification, Route, User, Vehicle
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services import storage
from app.services.audit import log, log_update, snapshot
from app.services.accounting import post_expense

router = APIRouter(prefix="/expenses", tags=["expenses"], dependencies=[Depends(require_feature("feature_financeiro"))])
_EXPENSE_CREATOR = require_permission(
    FINANCE_EXPENSE_CREATE, Role.GESTOR_BRASIL, Role.GESTOR_FINANCEIRO,
    Role.OPERADOR_LOGISTICO, Role.MOTORISTA,
)
_EXPENSE_APPROVER = require_permission(FINANCE_EXPENSE_APPROVE, Role.GESTOR_BRASIL, Role.GESTOR_FINANCEIRO)
APPROVAL_STATUSES = {"pending", "in_review", "adjustment_requested", "approved", "rejected"}

ALLOWED_REASONS = {
    "combustivel", "manutencao", "limpeza", "outros",
    "diaria_motorista", "diaria_ajudante", "frete_transportadora",
}

@router.get("/categories", dependencies=[Depends(_EXPENSE_CREATOR)])
def expense_categories(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.scalars(select(FinancialCategory).where(
        FinancialCategory.tenant_id == user.tenant_id,
        FinancialCategory.kind == "payable",
        FinancialCategory.active.is_(True),
    ).order_by(FinancialCategory.name)).all()
    return [{"code": row.code, "name": row.name} for row in rows]
ALLOWED_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/jpg", "image/webp"}
EXTENSION_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class ExpenseOut(BaseModel):
    id: int
    branch_id: int
    driver_id: int | None
    vehicle_id: int | None
    vehicle_plate: str | None = None
    user_id: int | None
    route_id: int | None
    expense_date: date
    reason: str
    amount: Decimal | None
    notes: str | None
    attachment_id: int | None
    proof_filename: str | None = None
    proof_url: str | None = None
    odometer_km: float | None = None
    odometer_photo_filename: str | None = None
    odometer_photo_url: str | None = None
    driver_name: str | None = None
    created_at: datetime
    source: str = "manual"
    maintenance_order_id: int | None = None
    approval_status: str = "pending"
    submitted_at: datetime | None = None
    reviewed_by_id: int | None = None
    reviewer_name: str | None = None
    reviewed_at: datetime | None = None
    decision_note: str | None = None
    submitter_name: str | None = None
    due_date: date | None = None
    recurrence: str = "none"
    recurrence_count: int = 1

    class Config:
        from_attributes = True


class ExpenseUpdate(BaseModel):
    expense_date: date | None = None
    reason: str | None = None
    amount: Decimal | None = None
    notes: str | None = None
    route_id: int | None = None
    vehicle_id: int | None = None
    odometer_km: float | None = None


class ExpenseDecisionIn(BaseModel):
    action: str
    comment: str | None = None


class ApprovalEventOut(BaseModel):
    id: int
    actor_id: int | None
    actor_name: str | None = None
    from_status: str | None
    to_status: str
    comment: str | None
    created_at: datetime


def _safe_filename(filename: str | None) -> str:
    name = Path(filename or "comprovante").name
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:120] or "comprovante"


def _resolve_content_type(file: UploadFile) -> str:
    content_type = file.content_type or "application/octet-stream"
    if content_type in ALLOWED_TYPES:
        return content_type
    if content_type == "application/octet-stream":
        guessed = EXTENSION_TYPES.get(Path(file.filename or "").suffix.lower())
        if guessed:
            return guessed
    raise HTTPException(status_code=415, detail=f"Tipo de comprovante não suportado: {content_type}")


async def _save_proof(file: UploadFile, branch_id: int, expense_date: date, folder: str = "despesas") -> Attachment:
    content_type = _resolve_content_type(file)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Comprovante obrigatório.")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Arquivo acima de {settings.max_upload_mb} MB.")
    storage.ensure_buckets()
    month = expense_date.strftime("%Y-%m")
    filename = _safe_filename(file.filename)
    key = f"{folder}/{branch_id}/{month}/{uuid.uuid4().hex}-{filename}"
    storage.put_object(settings.minio_bucket_proofs, key, data, content_type)
    return Attachment(
        bucket=settings.minio_bucket_proofs,
        storage_key=key,
        content_type=content_type,
        size_bytes=len(data),
    )


def _driver_for_user(db: Session, user: User) -> Driver:
    driver = db.scalar(select(Driver).where(Driver.user_id == user.id, Driver.active.is_(True)))
    if driver is None:
        raise HTTPException(status_code=409, detail="Usuário não está vinculado a um motorista ativo.")
    return driver


def _assert_expense_access(user: User, expense: Expense) -> None:
    driver_expense = expense.source == "driver"
    if user.role == Role.MOTORISTA.value:
        if driver_expense and expense.user_id == user.id: return
        raise HTTPException(status_code=403, detail="Acesso restrito às próprias despesas de motorista.")
    if user.role == Role.ADMIN_GLOBAL.value: return
    if has_permission(user, FINANCE_VIEW, Role.GESTOR_BRASIL, Role.GESTOR_FINANCEIRO):
        require_same_branch(user, expense.branch_id)
        return
    if driver_expense or user.role != Role.OPERADOR_LOGISTICO.value:
        raise HTTPException(status_code=403, detail="Perfil sem permissão para esta ação.")
    require_same_branch(user, expense.branch_id)


def _serialize(expense: Expense) -> ExpenseOut:
    attachment = expense.attachment
    proof_filename = Path(attachment.storage_key).name.split("-", 1)[-1] if attachment else None
    proof_url = storage.get_presigned_url(attachment.bucket, attachment.storage_key) if attachment else None
    odometer_attachment = expense.odometer_attachment
    odometer_photo_filename = Path(odometer_attachment.storage_key).name.split("-", 1)[-1] if odometer_attachment else None
    odometer_photo_url = storage.get_presigned_url(odometer_attachment.bucket, odometer_attachment.storage_key) if odometer_attachment else None
    return ExpenseOut(
        id=expense.id,
        branch_id=expense.branch_id,
        driver_id=expense.driver_id,
        vehicle_id=expense.vehicle_id,
        vehicle_plate=expense.vehicle.plate if expense.vehicle else None,
        user_id=expense.user_id,
        route_id=expense.route_id,
        expense_date=expense.expense_date,
        reason=expense.reason,
        amount=expense.amount,
        notes=expense.notes,
        attachment_id=expense.attachment_id,
        proof_filename=proof_filename,
        proof_url=proof_url,
        odometer_km=expense.odometer_km,
        odometer_photo_filename=odometer_photo_filename,
        odometer_photo_url=odometer_photo_url,
        driver_name=expense.driver.name if expense.driver else None,
        created_at=expense.created_at,
        source=expense.source,
        maintenance_order_id=expense.maintenance_order_id,
        approval_status=expense.approval_status,
        submitted_at=expense.submitted_at,
        reviewed_by_id=expense.reviewed_by_id,
        reviewer_name=expense.reviewer.name if getattr(expense, "reviewer", None) else None,
        reviewed_at=expense.reviewed_at,
        decision_note=expense.decision_note,
        submitter_name=expense.submitter.name if getattr(expense, "submitter", None) else None,
        due_date=expense.due_date, recurrence=expense.recurrence, recurrence_count=expense.recurrence_count,
    )


def _approval_event(db: Session, expense: Expense, actor: User, target: str, comment: str | None = None) -> None:
    db.add(ExpenseApprovalEvent(
        expense_id=expense.id, actor_id=actor.id, from_status=expense.approval_status,
        to_status=target, comment=(comment or "").strip() or None,
    ))


def _notify(db: Session, user_id: int | None, title: str, body: str) -> None:
    if user_id:
        db.add(Notification(user_id=user_id, title=title, body=body))


def _create_payable(db: Session, expense: Expense, actor: User) -> FinancialAccount:
    account = db.scalar(select(FinancialAccount).where(FinancialAccount.expense_id == expense.id))
    if account:
        return account
    if expense.amount is None or expense.amount <= 0:
        raise HTTPException(status_code=409, detail="Informe um valor maior que zero antes da aprovação.")
    group=f"expense-{expense.id}";count=max(1,expense.recurrence_count or 1);months={"monthly":1,"quarterly":3,"semiannual":6,"annual":12}.get(expense.recurrence,0);first_due=expense.due_date or max(expense.expense_date,date.today())
    account = FinancialAccount(
        branch_id=expense.branch_id, kind="payable",
        description=f"Despesa #{expense.id} · {expense.reason}",
        counterparty=expense.driver.name if expense.driver else "Despesa administrativa",
        category=expense.reason, document=expense.attachment.storage_key if expense.attachment else None,
        issue_date=expense.expense_date, due_date=first_due,
        amount=expense.amount, notes=expense.notes, created_by=actor.id, expense_id=expense.id,
        recurrence_group=group if months else None,recurrence_sequence=1 if months else None,recurrence_total=count if months else None,
    )
    db.add(account)
    db.flush()
    if months:
        for sequence in range(2,count+1):
            due=first_due+relativedelta(months=months*(sequence-1))
            db.add(FinancialAccount(branch_id=expense.branch_id,kind="payable",description=f"Despesa recorrente #{expense.id} · {expense.reason} ({sequence}/{count})",counterparty=account.counterparty,category=expense.reason,document=account.document,issue_date=due,due_date=due,amount=expense.amount,status="pendente",notes=expense.notes,created_by=actor.id,recurrence_group=group,recurrence_sequence=sequence,recurrence_total=count))
    return account


def _validate_reason(reason: str, db: Session, user: User) -> str:
    value = reason.strip().lower()
    category = db.scalar(select(FinancialCategory).where(
        FinancialCategory.tenant_id == user.tenant_id,
        FinancialCategory.kind == "payable",
        FinancialCategory.code == value,
        FinancialCategory.active.is_(True),
    ))
    if category is None: raise HTTPException(status_code=400, detail="Selecione uma categoria de despesa ativa.")
    return value


def _expense_query(user: User):
    stmt = select(Expense).outerjoin(Driver, Driver.id == Expense.driver_id)
    if user.role == Role.MOTORISTA.value:
        stmt = stmt.where(Expense.user_id == user.id, Expense.source == "driver")
    elif has_permission(user, FINANCE_VIEW, Role.GESTOR_BRASIL, Role.GESTOR_FINANCEIRO):
        if user.role != Role.ADMIN_GLOBAL.value and user.branch_id:
            stmt = stmt.where(Expense.branch_id == user.branch_id)
    elif has_permission(user, FINANCE_EXPENSE_CREATE, Role.OPERADOR_LOGISTICO) and user.branch_id:
        stmt = stmt.where(Expense.branch_id == user.branch_id, Expense.source != "driver")
    else:
        raise HTTPException(status_code=403, detail="Acesso não liberado para despesas administrativas.")
    return stmt


@router.get("", response_model=list[ExpenseOut])
def list_expenses(
    month: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = _expense_query(user)
    if month:
        try:
            year, month_num = [int(part) for part in month.split("-", 1)]
        except ValueError:
            raise HTTPException(status_code=400, detail="Mês inválido. Use AAAA-MM.")
        stmt = stmt.where(
            extract("year", Expense.expense_date) == year,
            extract("month", Expense.expense_date) == month_num,
        )
    expenses = db.scalars(stmt.order_by(Expense.expense_date.desc(), Expense.id.desc())).all()
    return [_serialize(expense) for expense in expenses]


@router.post("", response_model=ExpenseOut, dependencies=[Depends(_EXPENSE_CREATOR)])
async def create_expense(
    expense_date: date = Form(...),
    reason: str = Form(...),
    amount: Decimal | None = Form(None),
    notes: str | None = Form(None),
    route_id: int | None = Form(None),
    driver_id: int | None = Form(None),
    vehicle_id: int | None = Form(None),
    odometer_km: float | None = Form(None),
    due_date: date | None = Form(None),
    recurrence: str = Form("none"),
    recurrence_count: int = Form(1),
    proof: UploadFile = File(...),
    odometer_photo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    reason = _validate_reason(reason, db, user)
    if recurrence not in {"none","monthly","quarterly","semiannual","annual"}: raise HTTPException(status_code=422, detail="Recorrência inválida.")
    if user.role == Role.MOTORISTA.value and recurrence != "none": raise HTTPException(status_code=403, detail="Recorrência é exclusiva para despesas administrativas.")
    if recurrence != "none" and not 2 <= recurrence_count <= 120: raise HTTPException(status_code=422, detail="Informe entre 2 e 120 ocorrências.")
    if reason == "combustivel" and odometer_km is None:
        raise HTTPException(status_code=422, detail="Informe o valor do hodômetro no abastecimento.")
    if reason == "combustivel" and (odometer_photo is None or not odometer_photo.filename):
        raise HTTPException(status_code=422, detail="Anexe uma foto do hodômetro.")
    route = db.get(Route, route_id) if route_id else None
    if route_id and route is None:
        raise HTTPException(status_code=404, detail="Rota não encontrada.")
    if route is not None:
        require_same_branch(user, route.branch_id)
    effective_driver_id = route.driver_id if route is not None else driver_id
    driver = _driver_for_user(db, user) if user.role == Role.MOTORISTA.value else (db.get(Driver, effective_driver_id) if effective_driver_id else None)
    if (user.role == Role.MOTORISTA.value or route is not None) and driver is None:
        raise HTTPException(status_code=422, detail="Informe o motorista para despesas do motorista ou vinculadas a uma viagem.")
    if driver is not None: require_same_branch(user, driver.branch_id)
    if not vehicle_id and route and route.vehicle_id:
        vehicle_id = route.vehicle_id
    if not vehicle_id and (user.role == Role.MOTORISTA.value or reason == "combustivel"):
        raise HTTPException(status_code=422, detail="Informe a placa do veículo.")
    vehicle = db.get(Vehicle, vehicle_id) if vehicle_id else None
    if vehicle_id and vehicle is None:
        raise HTTPException(status_code=404, detail="Veículo não encontrado.")
    if vehicle is not None:
        require_same_branch(user, vehicle.branch_id)
    branch_id = route.branch_id if route is not None else vehicle.branch_id if vehicle is not None else user.branch_id
    if branch_id is None:
        raise HTTPException(status_code=422, detail="Informe uma rota ou veículo para identificar a filial do lançamento.")
    attachment = await _save_proof(proof, branch_id, expense_date)
    db.add(attachment)
    db.flush()
    odometer_attachment = None
    if odometer_photo is not None and odometer_photo.filename:
        odometer_attachment = await _save_proof(odometer_photo, branch_id, expense_date, folder="hodometro")
        db.add(odometer_attachment)
        db.flush()
    expense = Expense(
        branch_id=branch_id,
        driver_id=driver.id if driver else None,
        vehicle_id=vehicle.id if vehicle else None,
        user_id=user.id,
        route_id=route_id,
        expense_date=expense_date,
        reason=reason,
        amount=amount,
        notes=notes,
        attachment_id=attachment.id,
        odometer_km=odometer_km,
        odometer_attachment_id=odometer_attachment.id if odometer_attachment else None,
        source="driver" if user.role == Role.MOTORISTA.value else "administrative",
        approval_status="pending", submitted_at=datetime.now(timezone.utc),
        due_date=due_date, recurrence=recurrence, recurrence_count=recurrence_count if recurrence != "none" else 1,
    )
    db.add(expense)
    db.flush()
    log(db, user_id=user.id, action="create", entity="expense", entity_id=expense.id)
    db.add(ExpenseApprovalEvent(expense_id=expense.id, actor_id=user.id, from_status=None, to_status="pending", comment="Enviada para análise financeira."))
    db.commit()
    db.refresh(expense)
    return _serialize(expense)


@router.get("/approval-tasks", response_model=list[ExpenseOut], dependencies=[Depends(_EXPENSE_APPROVER)])
def approval_tasks(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(Expense).where(Expense.approval_status.in_(["pending", "in_review"]))
    if user.role != Role.ADMIN_GLOBAL.value:
        stmt = stmt.where(Expense.branch_id == user.branch_id)
    rows = db.scalars(stmt.order_by(Expense.submitted_at, Expense.created_at)).all()
    return [_serialize(row) for row in rows]


@router.get("/{expense_id}/approval-history", response_model=list[ApprovalEventOut])
def approval_history(expense_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    expense = db.get(Expense, expense_id)
    if expense is None:
        raise HTTPException(status_code=404, detail="Despesa não encontrada.")
    _assert_expense_access(user, expense)
    rows = db.scalars(select(ExpenseApprovalEvent).where(ExpenseApprovalEvent.expense_id == expense_id).order_by(ExpenseApprovalEvent.id)).all()
    actor_ids = {row.actor_id for row in rows if row.actor_id}
    names = dict(db.execute(select(User.id, User.name).where(User.id.in_(actor_ids))).all()) if actor_ids else {}
    return [ApprovalEventOut(id=row.id, actor_id=row.actor_id, actor_name=names.get(row.actor_id), from_status=row.from_status, to_status=row.to_status, comment=row.comment, created_at=row.created_at) for row in rows]


@router.post("/{expense_id}/decision", response_model=ExpenseOut, dependencies=[Depends(_EXPENSE_APPROVER)])
def decide_expense(expense_id: int, data: ExpenseDecisionIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    expense = db.scalar(select(Expense).where(Expense.id == expense_id).with_for_update())
    if expense is None:
        raise HTTPException(status_code=404, detail="Despesa não encontrada.")
    require_same_branch(actor, expense.branch_id)
    action = data.action.strip().lower()
    targets = {"start_review": "in_review", "approve": "approved", "reject": "rejected", "request_adjustment": "adjustment_requested"}
    if action not in targets:
        raise HTTPException(status_code=422, detail="Decisão inválida.")
    if expense.approval_status not in {"pending", "in_review"}:
        raise HTTPException(status_code=409, detail="Esta solicitação já foi finalizada ou devolvida para ajuste.")
    if action in {"reject", "request_adjustment"} and not (data.comment or "").strip():
        raise HTTPException(status_code=422, detail="Informe a justificativa da decisão.")
    target = targets[action]
    _approval_event(db, expense, actor, target, data.comment)
    expense.approval_status = target
    expense.reviewed_by_id = actor.id
    expense.reviewed_at = datetime.now(timezone.utc)
    expense.decision_note = (data.comment or "").strip() or None
    account = _create_payable(db, expense, actor) if target == "approved" else None
    if target == "approved":
        post_expense(db, expense, actor.id)
    _notify(db, expense.user_id, f"Despesa #{expense.id}: {target}", expense.decision_note or "Decisão registrada pelo financeiro.")
    log(db, user_id=actor.id, action=action, entity="expense_approval", entity_id=expense.id, detail=f"status={target}; conta={account.id if account else '-'}; justificativa={expense.decision_note or '-'}")
    db.commit(); db.refresh(expense)
    return _serialize(expense)


@router.put("/{expense_id}", response_model=ExpenseOut)
async def update_expense(
    expense_id: int,
    expense_date: date | None = Form(None),
    reason: str | None = Form(None),
    amount: Decimal | None = Form(None),
    notes: str | None = Form(None),
    route_id: int | None = Form(None),
    vehicle_id: int | None = Form(None),
    odometer_km: float | None = Form(None),
    proof: UploadFile | None = File(None),
    odometer_photo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    expense = db.get(Expense, expense_id)
    if expense is None:
        raise HTTPException(status_code=404, detail="Despesa não encontrada.")
    if expense.maintenance_order_id is not None:
        raise HTTPException(status_code=409, detail="Despesa gerada por OS deve ser alterada pelo fluxo de aprovação da ordem de serviço.")
    _assert_expense_access(user, expense)
    if expense.approval_status in {"approved", "rejected", "in_review"}:
        raise HTTPException(status_code=409, detail="Despesa em análise ou finalizada não pode ser alterada.")
    if expense.user_id != user.id:
        raise HTTPException(status_code=403, detail="Somente o lançador pode alterar a solicitação; o financeiro deve pedir ajuste.")
    effective_reason = _validate_reason(reason, db, user) if reason else expense.reason
    if effective_reason == "combustivel":
        if odometer_km is None and expense.odometer_km is None:
            raise HTTPException(status_code=422, detail="Informe o valor do hodômetro no abastecimento.")
        if expense.odometer_attachment_id is None and (odometer_photo is None or not odometer_photo.filename):
            raise HTTPException(status_code=422, detail="Anexe uma foto do hodômetro.")
    updates = {
        "expense_date": expense_date,
        "reason": _validate_reason(reason, db, user) if reason else None,
        "amount": amount,
        "notes": notes,
        "route_id": route_id,
        "vehicle_id": vehicle_id,
        "odometer_km": odometer_km,
    }
    updates = {key: value for key, value in updates.items() if value is not None}
    if "vehicle_id" in updates:
        vehicle = db.get(Vehicle, updates["vehicle_id"])
        if vehicle is None:
            raise HTTPException(status_code=404, detail="Veículo não encontrado.")
        require_same_branch(user, vehicle.branch_id)
    before = snapshot(expense, list(updates))
    for field, value in updates.items():
        setattr(expense, field, value)
    if proof is not None and proof.filename:
        attachment = await _save_proof(proof, expense.branch_id, expense.expense_date)
        db.add(attachment)
        db.flush()
        expense.attachment_id = attachment.id
    if odometer_photo is not None and odometer_photo.filename:
        odometer_attachment = await _save_proof(odometer_photo, expense.branch_id, expense.expense_date, folder="hodometro")
        db.add(odometer_attachment)
        db.flush()
        expense.odometer_attachment_id = odometer_attachment.id
    if expense.approval_status == "adjustment_requested":
        _approval_event(db, expense, user, "pending", "Ajuste realizado e reenviado ao financeiro.")
        expense.approval_status = "pending"
        expense.submitted_at = datetime.now(timezone.utc)
        expense.reviewed_by_id = None
        expense.reviewed_at = None
        expense.decision_note = None
    log_update(db, user_id=user.id, entity="expense", entity_id=expense.id, before=before, obj=expense, updates=updates)
    db.commit()
    db.refresh(expense)
    return _serialize(expense)


@router.delete("/{expense_id}")
def delete_expense(expense_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    expense = db.scalar(select(Expense).where(Expense.id == expense_id).with_for_update())
    if expense is None:
        raise HTTPException(status_code=404, detail="Despesa não encontrada.")
    if expense.maintenance_order_id is not None:
        raise HTTPException(status_code=409, detail="Despesa gerada por OS deve ser revertida pela ordem de serviço.")
    _assert_expense_access(user, expense)
    if expense.approval_status not in {"pending", "adjustment_requested"}:
        raise HTTPException(status_code=409, detail="Despesa em análise ou finalizada não pode ser excluída.")
    if expense.user_id != user.id and user.role != Role.ADMIN_GLOBAL.value:
        raise HTTPException(status_code=403, detail="Somente o lançador pode excluir esta solicitação.")
    db.delete(expense)
    log(db, user_id=user.id, action="delete", entity="expense", entity_id=expense_id)
    db.commit()
    return {"deleted": expense_id}


@router.get("/export.xlsx")
def export_expenses_xlsx(
    month: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    expenses = list_expenses(month=month, db=db, user=user)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Despesas"
    headers = ["ID", "Data", "Motorista", "Placa", "Motivo", "Valor", "Hodômetro (km)", "Rota", "Observações", "Comprovante"]
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for item in expenses:
        sheet.append([
            item.id,
            item.expense_date.isoformat(),
            item.driver_name,
            item.vehicle_plate,
            item.reason,
            float(item.amount) if item.amount is not None else None,
            item.odometer_km,
            item.route_id,
            item.notes,
            item.proof_filename,
        ])
    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    filename = f"despesas-{month or date.today().strftime('%Y-%m')}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/batch/{year}/{month}.zip", dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL))])
def download_month_batch(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="Mês inválido.")
    stmt = _expense_query(user).where(
        extract("year", Expense.expense_date) == year,
        extract("month", Expense.expense_date) == month,
    )
    expenses = db.scalars(stmt.order_by(Expense.expense_date, Expense.id)).all()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for expense in expenses:
            attachment = expense.attachment
            if attachment is None:
                continue
            driver = _safe_filename(expense.driver.name if expense.driver else f"motorista-{expense.driver_id}")
            filename = Path(attachment.storage_key).name.split("-", 1)[-1]
            archive_name = f"{year}-{month:02d}/{driver}/{expense.expense_date.isoformat()}-{expense.id}-{filename}"
            archive.writestr(archive_name, storage.get_object_bytes(attachment.bucket, attachment.storage_key))
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="despesas-{year}-{month:02d}.zip"'},
    )

import io
import re
import uuid
import zipfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font
from pydantic import BaseModel
from sqlalchemy import extract, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import Role, require_feature, require_roles, require_same_branch
from app.db.models import Attachment, Driver, Expense, Route, User, Vehicle
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services import storage
from app.services.audit import log, log_update, snapshot

router = APIRouter(prefix="/expenses", tags=["expenses"], dependencies=[Depends(require_feature("feature_financeiro"))])

ALLOWED_REASONS = {
    "combustivel", "manutencao", "limpeza", "outros",
    "diaria_motorista", "diaria_ajudante", "frete_transportadora",
}
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
    driver_id: int
    vehicle_id: int | None
    vehicle_plate: str | None = None
    user_id: int | None
    route_id: int | None
    expense_date: date
    reason: str
    amount: Decimal | None
    notes: str | None
    attachment_id: int
    proof_filename: str | None = None
    proof_url: str | None = None
    odometer_km: float | None = None
    odometer_photo_filename: str | None = None
    odometer_photo_url: str | None = None
    driver_name: str | None = None
    created_at: datetime

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
    if user.role == Role.ADMIN_GLOBAL.value:
        return
    if user.role == Role.MOTORISTA.value and expense.user_id == user.id:
        return
    if user.role not in {Role.GESTOR_BRASIL.value, Role.GESTOR_FINANCEIRO.value}:
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
    )


def _validate_reason(reason: str) -> str:
    value = reason.strip().lower()
    if value not in ALLOWED_REASONS:
        raise HTTPException(status_code=400, detail="Motivo inválido.")
    return value


def _expense_query(user: User):
    stmt = select(Expense).join(Driver, Driver.id == Expense.driver_id)
    if user.role == Role.MOTORISTA.value:
        stmt = stmt.where(Expense.user_id == user.id)
    elif user.branch_id:
        stmt = stmt.where(Expense.branch_id == user.branch_id)
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


@router.post("", response_model=ExpenseOut)
async def create_expense(
    expense_date: date = Form(...),
    reason: str = Form(...),
    amount: Decimal | None = Form(None),
    notes: str | None = Form(None),
    route_id: int | None = Form(None),
    driver_id: int | None = Form(None),
    vehicle_id: int | None = Form(None),
    odometer_km: float | None = Form(None),
    proof: UploadFile = File(...),
    odometer_photo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    reason = _validate_reason(reason)
    if reason == "combustivel" and odometer_km is None:
        raise HTTPException(status_code=422, detail="Informe o valor do hodômetro no abastecimento.")
    if reason == "combustivel" and (odometer_photo is None or not odometer_photo.filename):
        raise HTTPException(status_code=422, detail="Anexe uma foto do hodômetro.")
    driver = db.get(Driver, driver_id) if driver_id and user.role != Role.MOTORISTA.value else _driver_for_user(db, user)
    if driver is None:
        raise HTTPException(status_code=404, detail="Motorista não encontrado.")
    require_same_branch(user, driver.branch_id)
    route = db.get(Route, route_id) if route_id else None
    if route_id and route is None:
        raise HTTPException(status_code=404, detail="Rota não encontrada.")
    if route is not None:
        require_same_branch(user, route.branch_id)
    if not vehicle_id and route and route.vehicle_id:
        vehicle_id = route.vehicle_id
    if not vehicle_id:
        raise HTTPException(status_code=422, detail="Informe a placa do veículo.")
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle_id and vehicle is None:
        raise HTTPException(status_code=404, detail="Veículo não encontrado.")
    if vehicle is not None:
        require_same_branch(user, vehicle.branch_id)
    attachment = await _save_proof(proof, driver.branch_id, expense_date)
    db.add(attachment)
    db.flush()
    odometer_attachment = None
    if odometer_photo is not None and odometer_photo.filename:
        odometer_attachment = await _save_proof(odometer_photo, driver.branch_id, expense_date, folder="hodometro")
        db.add(odometer_attachment)
        db.flush()
    expense = Expense(
        branch_id=driver.branch_id,
        driver_id=driver.id,
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
    )
    db.add(expense)
    db.flush()
    log(db, user_id=user.id, action="create", entity="expense", entity_id=expense.id)
    db.commit()
    db.refresh(expense)
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
    _assert_expense_access(user, expense)
    effective_reason = _validate_reason(reason) if reason else expense.reason
    if effective_reason == "combustivel":
        if odometer_km is None and expense.odometer_km is None:
            raise HTTPException(status_code=422, detail="Informe o valor do hodômetro no abastecimento.")
        if expense.odometer_attachment_id is None and (odometer_photo is None or not odometer_photo.filename):
            raise HTTPException(status_code=422, detail="Anexe uma foto do hodômetro.")
    updates = {
        "expense_date": expense_date,
        "reason": _validate_reason(reason) if reason else None,
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
    log_update(db, user_id=user.id, entity="expense", entity_id=expense.id, before=before, obj=expense, updates=updates)
    db.commit()
    db.refresh(expense)
    return _serialize(expense)


@router.delete("/{expense_id}")
def delete_expense(expense_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    expense = db.get(Expense, expense_id)
    if expense is None:
        raise HTTPException(status_code=404, detail="Despesa não encontrada.")
    _assert_expense_access(user, expense)
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

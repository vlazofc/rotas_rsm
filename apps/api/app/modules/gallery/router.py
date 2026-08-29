"""Galeria — agrega, só para leitura, os anexos já espalhados pelo sistema
(comprovantes de entrega/devolução, despesas, manutenção/orçamentos) numa
única tela com filtro por placa/motorista/data e download.

Não cria tabela nova: consulta Attachment através de quem já referencia cada
uma (route_stops, expenses, maintenance_orders).
"""
import io
from datetime import date
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from minio.error import S3Error
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.permissions import Role
from app.db.models import Attachment, Driver, Expense, MaintenanceOrder, Route, RouteStop, User, Vehicle
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services import storage

router = APIRouter(prefix="/gallery", tags=["gallery"])

KINDS = {"entrega", "devolucao", "despesa", "despesa_odometro", "manutencao", "orcamento"}


class GalleryItemOut(BaseModel):
    id: str
    kind: str
    occurred_at: date
    vehicle_plate: str | None = None
    driver_name: str | None = None
    reference: str | None = None  # ex.: código da rota, motivo da despesa, descrição da OS
    filename: str
    content_type: str | None = None
    url: str
    attachment_id: int


def _item(kind: str, source_id: int, occurred_at: date, plate: str | None, driver_name: str | None, reference: str | None, attachment: Attachment) -> GalleryItemOut:
    return GalleryItemOut(
        id=f"{kind}_{source_id}_{attachment.id}",
        kind=kind,
        occurred_at=occurred_at,
        vehicle_plate=plate,
        driver_name=driver_name,
        reference=reference,
        filename=Path(attachment.storage_key).name.split("-", 1)[-1],
        content_type=attachment.content_type,
        url=storage.get_presigned_url(attachment.bucket, attachment.storage_key),
        attachment_id=attachment.id,
    )


def _attachment_allowed(attachment_id: int, db: Session, user: User) -> bool:
    """Confirma que o anexo pertence a uma origem visível para o usuário."""
    def scoped(stmt, model):
        if user.role == Role.ADMIN_GLOBAL.value:
            return stmt
        if user.branch_id is not None:
            return stmt.where(model.branch_id == user.branch_id)
        if user.tenant_id is not None:
            return stmt.where(model.tenant_id == user.tenant_id)
        return stmt.where(False)

    route_stmt = select(RouteStop.id).join(Route, Route.id == RouteStop.route_id).where(
        or_(RouteStop.proof_attachment_id == attachment_id, RouteStop.warehouse_return_attachment_id == attachment_id)
    ).limit(1)
    expense_stmt = select(Expense.id).where(or_(Expense.attachment_id == attachment_id, Expense.odometer_attachment_id == attachment_id)).limit(1)
    maintenance_stmt = select(MaintenanceOrder.id).where(or_(MaintenanceOrder.attachment_id == attachment_id, MaintenanceOrder.budget_attachment_id == attachment_id)).limit(1)
    return bool(db.scalar(scoped(route_stmt, Route)) or db.scalar(scoped(expense_stmt, Expense)) or db.scalar(scoped(maintenance_stmt, MaintenanceOrder)))


@router.get("/files/{attachment_id}")
def open_gallery_file(attachment_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    attachment = db.get(Attachment, attachment_id)
    if attachment is None or not _attachment_allowed(attachment_id, db, user):
        raise HTTPException(404, "Documento não encontrado.")
    try:
        content = storage.get_object_bytes(attachment.bucket, attachment.storage_key)
    except S3Error as exc:
        if exc.code in {"NoSuchKey", "NoSuchObject"}:
            raise HTTPException(404, "O arquivo deste documento não foi localizado no armazenamento.") from exc
        raise HTTPException(503, "Não foi possível acessar o armazenamento de documentos.") from exc
    filename = Path(attachment.storage_key).name.split("-", 1)[-1]
    return StreamingResponse(io.BytesIO(content), media_type=attachment.content_type or "application/octet-stream", headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}", "Cache-Control": "private, max-age=300"})


@router.get("", response_model=list[GalleryItemOut])
def list_gallery(
    plate: str | None = None,
    driver_id: int | None = None,
    kind: str | None = None,
    query: str | None = None,
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    plate = plate.strip().upper() if plate and plate.strip() else None
    kind = kind.strip() if kind and kind.strip() else None
    query = query.strip().casefold() if query and query.strip() else None
    if kind and kind not in KINDS:
        raise HTTPException(422, "Tipo de documento inválido.")
    if start and end and start > end:
        raise HTTPException(422, "A data inicial não pode ser posterior à data final.")
    branch_filter = user.branch_id if user.role != Role.ADMIN_GLOBAL.value else None
    items: list[GalleryItemOut] = []

    if kind is None or kind in {"entrega", "devolucao"}:
        stmt = (
            select(RouteStop, Route, Vehicle.plate, Driver.name)
            .join(Route, Route.id == RouteStop.route_id)
            .outerjoin(Vehicle, Vehicle.id == Route.vehicle_id)
            .outerjoin(Driver, Driver.id == Route.driver_id)
        )
        if branch_filter:
            stmt = stmt.where(Route.branch_id == branch_filter)
        if plate:
            stmt = stmt.where(Vehicle.plate.ilike(f"%{plate}%"))
        if driver_id:
            stmt = stmt.where(Route.driver_id == driver_id)
        if start:
            stmt = stmt.where(Route.route_date >= start)
        if end:
            stmt = stmt.where(Route.route_date <= end)
        for stop, route, vplate, dname in db.execute(stmt).all():
            if stop.proof_attachment and (kind is None or kind == "entrega"):
                items.append(_item("entrega", stop.id, route.route_date, vplate, dname, f"{route.codigo_ut} — {stop.customer_name}", stop.proof_attachment))
            if stop.warehouse_return_attachment and (kind is None or kind == "devolucao"):
                items.append(_item("devolucao", stop.id, route.route_date, vplate, dname, f"{route.codigo_ut} — {stop.customer_name}", stop.warehouse_return_attachment))

    if kind is None or kind in {"despesa", "despesa_odometro"}:
        stmt = (
            select(Expense, Vehicle.plate, Driver.name)
            .outerjoin(Vehicle, Vehicle.id == Expense.vehicle_id)
            .outerjoin(Driver, Driver.id == Expense.driver_id)
        )
        if branch_filter:
            stmt = stmt.where(Expense.branch_id == branch_filter)
        if plate:
            stmt = stmt.where(Vehicle.plate.ilike(f"%{plate}%"))
        if driver_id:
            stmt = stmt.where(Expense.driver_id == driver_id)
        if start:
            stmt = stmt.where(Expense.expense_date >= start)
        if end:
            stmt = stmt.where(Expense.expense_date <= end)
        for expense, vplate, dname in db.execute(stmt).all():
            if expense.attachment and (kind is None or kind == "despesa"):
                items.append(_item("despesa", expense.id, expense.expense_date, vplate, dname, expense.reason, expense.attachment))
            if expense.odometer_attachment and (kind is None or kind == "despesa_odometro"):
                items.append(_item("despesa_odometro", expense.id, expense.expense_date, vplate, dname, expense.reason, expense.odometer_attachment))

    # Ordens de manutenção não possuem motorista associado. Portanto, elas não
    # podem compor um resultado que esteja explicitamente filtrado por motorista.
    if not driver_id and (kind is None or kind in {"manutencao", "orcamento"}):
        stmt = select(MaintenanceOrder, Vehicle.plate).outerjoin(Vehicle, Vehicle.id == MaintenanceOrder.vehicle_id)
        if branch_filter:
            stmt = stmt.where(MaintenanceOrder.branch_id == branch_filter)
        if plate:
            stmt = stmt.where(Vehicle.plate.ilike(f"%{plate}%"))
        if start:
            stmt = stmt.where(MaintenanceOrder.opened_at >= start)
        if end:
            stmt = stmt.where(MaintenanceOrder.opened_at <= end)
        for order, vplate in db.execute(stmt).all():
            if order.attachment and (kind is None or kind == "manutencao"):
                items.append(_item("manutencao", order.id, order.opened_at, vplate, None, order.description, order.attachment))
            if order.budget_attachment and (kind is None or kind == "orcamento"):
                items.append(_item("orcamento", order.id, order.opened_at, vplate, None, order.description, order.budget_attachment))

    if query:
        items = [item for item in items if query in " ".join(filter(None, [item.filename, item.reference, item.vehicle_plate, item.driver_name])).casefold()]
    items.sort(key=lambda i: i.occurred_at, reverse=True)
    return items

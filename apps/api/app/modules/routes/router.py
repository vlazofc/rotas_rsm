"""Rotas/voltas: criação, fluxo de doca, saída, check-in, entrega, fechamento.

Toda transição registra um RouteEvent auditável e atualiza os tempos da doca.
Edição é bloqueada quando a rota está finalizada/cancelada.
"""
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.permissions import Role, require_branch_access, require_roles, require_same_branch
from app.db.models import Attachment, DeliveryFailureReason, DockSession, Driver, Route, RouteStop, RouteStopOperation, RouteToll, Checkin, User, Vehicle
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.modules.routes.schemas import (
    AdminRouteCorrectionIn, AdminStopCorrectionIn, CheckinIn, DeliverIn, RouteIn, RouteKmIn, RouteOut,
    RouteTollIn, RouteUpdate, StopIn, StopUpdate,
)
from app.services.audit import format_changes, log, log_update, snapshot
from app.services.events import EventType, record_event
from app.services import storage
from app.services.routing import calculate_km

router = APIRouter(prefix="/routes", tags=["routes"])

CLOSED_STATES = {"finalizada", "cancelada"}
DOCK_FLOW = {
    "arrival_cd_at": None,
    "dock_entry_at": "arrival_cd_at",
    "loading_started_at": "dock_entry_at",
    "loading_finished_at": "loading_started_at",
    "operator_released_at": "loading_finished_at",
    "departure_cd_at": "operator_released_at",
}
ALLOWED_PROOF_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/jpg", "image/webp"}
EXTENSION_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _load(db: Session, route_id: int) -> Route:
    route = db.scalar(
        select(Route)
        .where(Route.id == route_id)
        .options(
            selectinload(Route.stops).selectinload(RouteStop.operations),
            selectinload(Route.stops).selectinload(RouteStop.proof_attachment),
            selectinload(Route.stops).selectinload(RouteStop.warehouse_return_attachment),
            selectinload(Route.events),
            selectinload(Route.dock_session),
            selectinload(Route.tolls),
        )
    )
    if route is None:
        raise HTTPException(status_code=404, detail="Rota não encontrada.")
    _attach_stop_proof_urls(route)
    return route


def _validate_route_resources(
    db: Session,
    branch_id: int,
    driver_id: int | None,
    vehicle_id: int | None,
) -> None:
    """Impede relacionamentos cruzados entre filiais/tenants numa rota."""
    if driver_id is not None:
        driver = db.get(Driver, driver_id)
        if driver is None or driver.branch_id != branch_id:
            raise HTTPException(status_code=422, detail="Motorista não pertence à filial da rota.")
        if not driver.active or driver.blocked:
            raise HTTPException(status_code=422, detail="Motorista inativo ou bloqueado não pode ser escalado.")
    if vehicle_id is not None:
        vehicle = db.get(Vehicle, vehicle_id)
        if vehicle is None or vehicle.branch_id != branch_id:
            raise HTTPException(status_code=422, detail="Veículo não pertence à filial da rota.")
        if not vehicle.active or vehicle.blocked:
            raise HTTPException(status_code=422, detail="Veículo inativo ou bloqueado não pode ser escalado.")


def _safe_filename(filename: str | None) -> str:
    name = Path(filename or "comprovante").name
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:120] or "comprovante"


def _resolve_content_type(file: UploadFile) -> str:
    content_type = file.content_type or "application/octet-stream"
    if content_type in ALLOWED_PROOF_TYPES:
        return content_type
    if content_type == "application/octet-stream":
        guessed = EXTENSION_TYPES.get(Path(file.filename or "").suffix.lower())
        if guessed:
            return guessed
    raise HTTPException(status_code=415, detail=f"Tipo de comprovante não suportado: {content_type}")


async def _save_proof(file: UploadFile, route: Route, stop: RouteStop, kind: str) -> Attachment:
    content_type = _resolve_content_type(file)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Comprovante obrigatório.")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Arquivo acima de {settings.max_upload_mb} MB.")
    storage.ensure_buckets()
    filename = _safe_filename(file.filename)
    key = f"rotas/{route.branch_id}/{route.route_date:%Y-%m}/{route.id}/parada-{stop.id}/{kind}/{uuid.uuid4().hex}-{filename}"
    storage.put_object(settings.minio_bucket_proofs, key, data, content_type)
    return Attachment(
        bucket=settings.minio_bucket_proofs,
        storage_key=key,
        content_type=content_type,
        size_bytes=len(data),
    )


def _proof_filename(attachment: Attachment | None) -> str | None:
    return Path(attachment.storage_key).name.split("-", 1)[-1] if attachment else None


def _attach_stop_proof_urls(route: Route) -> None:
    for stop in route.stops:
        proof = stop.proof_attachment
        warehouse = stop.warehouse_return_attachment
        stop.proof_filename = _proof_filename(proof)
        stop.proof_url = storage.get_presigned_url(proof.bucket, proof.storage_key) if proof else None
        stop.warehouse_return_filename = _proof_filename(warehouse)
        stop.warehouse_return_url = storage.get_presigned_url(warehouse.bucket, warehouse.storage_key) if warehouse else None


def _guard_editable(route: Route) -> None:
    if route.status in CLOSED_STATES:
        raise HTTPException(status_code=409, detail="Rota encerrada não pode ser alterada.")


def _driver_ids(db: Session, user: User) -> list[int]:
    return list(db.scalars(select(Driver.id).where(Driver.user_id == user.id)).all())


def _guard_driver_assignment(db: Session, user: User, route: Route) -> None:
    """Motorista só pode ver/operar rotas atribuídas a ele."""
    if user.role != Role.MOTORISTA.value:
        return
    if route.driver_id is None or route.driver_id not in _driver_ids(db, user):
        raise HTTPException(status_code=403, detail="Rota não atribuída a este motorista.")


def _guard_not_expired(route: Route, user: User) -> None:
    if user.role == Role.ADMIN_GLOBAL.value:
        return
    today = datetime.now(ZoneInfo(settings.app_timezone)).date()
    if route.route_date < today:
        raise HTTPException(
            status_code=409,
            detail="Data da carga ultrapassada. Apenas o administrador global pode corrigir esta rota.",
        )


def _guard_dock_sequence(dock: DockSession, field: str) -> None:
    if getattr(dock, field):
        raise HTTPException(status_code=409, detail="Esta etapa já foi registrada e não pode ser sobreposta.")
    previous = DOCK_FLOW.get(field)
    if previous and not getattr(dock, previous):
        raise HTTPException(status_code=409, detail="Siga a sequência operacional antes de registrar esta etapa.")


def _guard_departed(route: Route) -> None:
    if not route.dock_session or not route.dock_session.departure_cd_at:
        raise HTTPException(status_code=409, detail="Registre a saída do CD antes de abrir as paradas da rota.")


def _guard_all_stops_closed(route: Route) -> None:
    pending = [s for s in route.stops if s.status not in {"entregue", "falha", "devolvido"}]
    if pending:
        raise HTTPException(status_code=409, detail="Finalize todas as paradas antes de fechar a rota.")


def _guard_failed_stops_have_warehouse_proofs(route: Route) -> None:
    missing = [s.sequence for s in route.stops if s.status == "falha" and not s.warehouse_return_attachment_id]
    if missing:
        joined = ", ".join(str(seq) for seq in missing)
        raise HTTPException(
            status_code=409,
            detail=f"Envie o comprovante de devolução ao armazém das falhas: {joined}.",
        )


def _minutes(a: datetime | None, b: datetime | None) -> int | None:
    if a and b:
        seconds = int((b - a).total_seconds())
        return max(seconds // 60, 0)
    return None


def _recalc_dock(dock: DockSession) -> None:
    dock.waiting_before_dock_minutes = _minutes(dock.arrival_cd_at, dock.dock_entry_at)
    dock.loading_minutes = _minutes(dock.loading_started_at, dock.loading_finished_at)
    dock.waiting_release_minutes = _minutes(dock.loading_finished_at, dock.operator_released_at)
    dock.total_cd_minutes = _minutes(dock.arrival_cd_at, dock.departure_cd_at)


def _reset_stop_operational_fields(stop: RouteStop, *, clear_proofs: bool = False) -> None:
    stop.status = "pendente"
    stop.failure_reason_id = None
    stop.checkin_at = None
    stop.delivered_at = None
    stop.latitude = None
    stop.longitude = None
    stop.return_type = None
    stop.returned_quantity = None
    if clear_proofs:
        stop.proof_attachment_id = None
        stop.warehouse_return_attachment_id = None


def _reset_dock_flow(route: Route) -> None:
    dock = route.dock_session
    if dock is None:
        return
    for field in DOCK_FLOW:
        setattr(dock, field, None)
    dock.waiting_before_dock_minutes = None
    dock.loading_minutes = None
    dock.waiting_release_minutes = None
    dock.total_cd_minutes = None
    route.actual_departure_at = None
    route.closed_at = None


# ----------------------- CRUD básico -----------------------

@router.get("", response_model=list[RouteOut])
def list_routes(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    status_filter: str | None = None,
):
    stmt = select(Route).options(
        selectinload(Route.stops).selectinload(RouteStop.operations),
        selectinload(Route.stops).selectinload(RouteStop.proof_attachment),
        selectinload(Route.stops).selectinload(RouteStop.warehouse_return_attachment),
        selectinload(Route.events),
        selectinload(Route.dock_session),
        selectinload(Route.tolls),
    )
    if user.branch_id:
        stmt = stmt.where(Route.branch_id == user.branch_id)
    if user.role == Role.MOTORISTA.value:
        stmt = stmt.where(Route.driver_id.in_(_driver_ids(db, user) or [-1]))
    if status_filter:
        stmt = stmt.where(Route.status == status_filter)
    stmt = stmt.where(Route.excluded.is_(False))
    routes = db.scalars(stmt.order_by(Route.route_date.asc(), Route.id.asc())).all()
    for route in routes:
        route.stops.sort(key=lambda stop: (stop.sequence or 0, stop.id))
        _attach_stop_proof_urls(route)
    return routes


@router.get("/{route_id}", response_model=RouteOut)
def get_route(route_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    route = _load(db, route_id)
    require_same_branch(user, route.branch_id)
    _guard_driver_assignment(db, user, route)
    return route


@router.post("", response_model=RouteOut,
             dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL, Role.OPERADOR_LOGISTICO))])
def create_route(data: RouteIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_branch_access(db, user, data.branch_id)
    _validate_route_resources(db, data.branch_id, data.driver_id, data.vehicle_id)
    payload = data.model_dump(exclude={"stops"})
    route = Route(**payload, created_by=user.id)
    route.dock_session = DockSession()
    for s in data.stops:
        route.stops.append(RouteStop(**s.model_dump()))
    db.add(route)
    db.flush()
    log(db, user_id=user.id, action="create", entity="route", entity_id=route.id)
    db.commit()
    return _load(db, route.id)


# ----------------------- Edição de rota e paradas -----------------------

_EDITOR = Depends(require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL, Role.OPERADOR_LOGISTICO))


def _guard_not_cancelled(route: Route) -> None:
    if route.status == "cancelada":
        raise HTTPException(status_code=409, detail="Rota cancelada não pode ser alterada.")


@router.delete("/{route_id}/exclude", dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL))])
def exclude_route(route_id: int,
                  db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Marca a rota como excluída da visão do tenant (soft delete).
    A rota permanece no banco mas some de listas, dashboard e sincronizações futuras."""
    route = db.scalar(select(Route).where(Route.id == route_id))
    if route is None:
        raise HTTPException(status_code=404, detail="Rota não encontrada.")
    require_same_branch(user, route.branch_id)
    route.excluded = True
    log(db, user_id=user.id, action="exclude", entity="route", entity_id=route.id,
        detail=f"Rota {route.codigo_ut} excluída da visão do tenant.")
    db.commit()
    return {"ok": True, "route_id": route_id, "codigo_ut": route.codigo_ut}


@router.put("/{route_id}", response_model=RouteOut, dependencies=[_EDITOR])
def update_route(route_id: int, data: RouteUpdate,
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Edita os dados da rota (cabeçalho). Permitido salvo se cancelada."""
    route = _load(db, route_id)
    require_same_branch(user, route.branch_id)
    _guard_not_cancelled(route)
    updates = data.model_dump(exclude_unset=True)
    _validate_route_resources(
        db,
        route.branch_id,
        updates.get("driver_id", route.driver_id),
        updates.get("vehicle_id", route.vehicle_id),
    )
    before = snapshot(route, list(updates))
    for field, value in updates.items():
        setattr(route, field, value)
    log_update(db, user_id=user.id, entity="route", entity_id=route.id,
               before=before, obj=route, updates=updates)
    db.commit()
    return _load(db, route.id)


@router.post("/{route_id}/stops", response_model=RouteOut, dependencies=[_EDITOR])
def add_stop(route_id: int, data: StopIn,
             db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Adiciona uma parada manual à rota."""
    route = _load(db, route_id)
    require_same_branch(user, route.branch_id)
    _guard_not_cancelled(route)
    payload = data.model_dump()
    if not payload.get("sequence"):
        payload["sequence"] = (max((s.sequence for s in route.stops), default=0) + 1)
    stop = RouteStop(route_id=route.id, **payload)
    db.add(stop)
    db.flush()
    detail = format_changes({field: (None, value) for field, value in payload.items()})
    log(db, user_id=user.id, action="create", entity="route_stop", entity_id=stop.id,
        detail=f"route_id={route.id}; {detail}" if detail else f"route_id={route.id}")
    db.commit()
    return _load(db, route.id)


@router.put("/{route_id}/stops/{stop_id}", response_model=RouteOut, dependencies=[_EDITOR])
def update_stop(route_id: int, stop_id: int, data: StopUpdate,
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Edita os detalhes de uma parada (endereço, cidade, peso, etc.)."""
    route, stop = _get_stop(db, route_id, stop_id)
    require_same_branch(user, route.branch_id)
    _guard_not_cancelled(route)
    updates = data.model_dump(exclude_unset=True)
    before = snapshot(stop, list(updates))
    for field, value in updates.items():
        setattr(stop, field, value)
    log_update(db, user_id=user.id, entity="route_stop", entity_id=stop.id,
               before=before, obj=stop, updates=updates)
    db.commit()
    return _load(db, route.id)


@router.delete("/{route_id}/stops/{stop_id}", response_model=RouteOut, dependencies=[_EDITOR])
def delete_stop(route_id: int, stop_id: int,
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    route, stop = _get_stop(db, route_id, stop_id)
    require_same_branch(user, route.branch_id)
    _guard_not_cancelled(route)
    fields = ["sequence", "customer_name", "customer_address", "city", "planned_date", "planned_time",
              "temperature", "stop_type", "weight_kg", "pallets", "order_number", "status"]
    before = snapshot(stop, fields)
    db.delete(stop)
    detail = format_changes({field: (value, None) for field, value in before.items()})
    log(db, user_id=user.id, action="delete", entity="route_stop", entity_id=stop.id,
        detail=f"route_id={route.id}; {detail}" if detail else f"route_id={route.id}")
    db.commit()
    return _load(db, route.id)


def _stop_address(stop: RouteStop) -> str:
    """Monta o endereço textual para geocodificação, priorizando o mais específico."""
    if stop.customer_address and stop.city:
        return f"{stop.customer_address}, {stop.city}"
    if stop.postal_code:
        parts = [stop.customer_address or stop.province, stop.postal_code, stop.city or "Brasil"]
        return ", ".join(p for p in parts if p)
    parts = [stop.customer_address, stop.province, stop.city]
    address = ", ".join(p for p in parts if p)
    return address or stop.customer_name


@router.post("/{route_id}/optimize-sequence", response_model=RouteOut, dependencies=[_EDITOR])
def optimize_sequence(route_id: int,
                      db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Reordena as paradas pelo vizinho mais próximo: a cada passo, escolhe a
    parada ainda não visitada mais próxima do ponto atual (rota sai da origem,
    vai à parada 1, da 1 à 2, e assim por diante)."""
    route = _load(db, route_id)
    require_same_branch(user, route.branch_id)
    _guard_not_cancelled(route)
    origin = route.origin_address or route.origin_name or settings.sharepoint_sync_origin_address or None
    if not origin:
        raise HTTPException(status_code=422, detail="Defina o endereço de origem da rota antes de otimizar.")
    if len(route.stops) < 2:
        return route

    remaining = list(route.stops)
    ordered: list[RouteStop] = []
    current_address = origin
    while remaining:
        with ThreadPoolExecutor(max_workers=len(remaining)) as pool:
            distances = list(pool.map(
                lambda s: calculate_km(current_address, _stop_address(s)), remaining,
            ))
        best_index = min(
            range(len(remaining)),
            key=lambda i: distances[i] if distances[i] is not None else float("inf"),
        )
        nearest = remaining.pop(best_index)
        ordered.append(nearest)
        current_address = _stop_address(nearest)

    sequence_before = {stop.id: stop.sequence for stop in ordered}
    for position, stop in enumerate(ordered, start=1):
        stop.sequence = position
    changes = {f"stop_{stop.id}_sequence": (sequence_before[stop.id], stop.sequence)
               for stop in ordered if sequence_before[stop.id] != stop.sequence}
    log(db, user_id=user.id, action="optimize_sequence", entity="route", entity_id=route.id,
        detail=format_changes(changes) or "A sequência já estava otimizada.")
    db.commit()
    return _load(db, route.id)


# ----------------------- Fluxo de doca / CD -----------------------

def _set_dock_time(db, route_id, user, field, event_type, status_after=None):
    route = _load(db, route_id)
    require_same_branch(user, route.branch_id)
    _guard_driver_assignment(db, user, route)
    _guard_editable(route)
    _guard_not_expired(route, user)
    dock = route.dock_session or DockSession(route_id=route.id)
    if route.dock_session is None:
        db.add(dock)
    _guard_dock_sequence(dock, field)
    dock_before = snapshot(dock, [field])
    route_before = snapshot(route, ["status"])
    setattr(dock, field, datetime.now(timezone.utc))
    _recalc_dock(dock)
    if status_after:
        route.status = status_after
    record_event(db, route_id=route.id, event_type=event_type, user_id=user.id)
    log_update(db, user_id=user.id, entity="route_dock", entity_id=route.id,
               before=dock_before, obj=dock, updates={field: getattr(dock, field)})
    log_update(db, user_id=user.id, entity="route", entity_id=route.id,
               before=route_before, obj=route, updates={"status": route.status})
    db.commit()
    return _load(db, route.id)


_OP = Depends(require_roles(Role.ADMIN_GLOBAL, Role.OPERADOR_LOGISTICO, Role.MOTORISTA))


@router.post("/{route_id}/arrive-cd", response_model=RouteOut, dependencies=[_OP])
def arrive_cd(route_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _set_dock_time(db, route_id, user, "arrival_cd_at", EventType.ARRIVED_CD)


@router.post("/{route_id}/enter-dock", response_model=RouteOut, dependencies=[_OP])
def enter_dock(route_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _set_dock_time(db, route_id, user, "dock_entry_at", EventType.ENTERED_DOCK, "em_carregamento")


@router.post("/{route_id}/loading-start", response_model=RouteOut, dependencies=[_OP])
def loading_start(route_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _set_dock_time(db, route_id, user, "loading_started_at", EventType.LOADING_STARTED)


@router.post("/{route_id}/loading-finish", response_model=RouteOut, dependencies=[_OP])
def loading_finish(route_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _set_dock_time(db, route_id, user, "loading_finished_at", EventType.LOADING_FINISHED)


@router.post("/{route_id}/release", response_model=RouteOut,
             dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL, Role.OPERADOR_LOGISTICO))])
def operator_release(route_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _set_dock_time(db, route_id, user, "operator_released_at", EventType.OPERATOR_RELEASED, "liberada")


@router.post("/{route_id}/depart", response_model=RouteOut, dependencies=[_OP])
def depart_cd(route_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    route = _load(db, route_id)
    require_same_branch(user, route.branch_id)
    _guard_driver_assignment(db, user, route)
    _guard_editable(route)
    _guard_not_expired(route, user)
    dock = route.dock_session or DockSession(route_id=route.id)
    if route.dock_session is None:
        db.add(dock)
    _guard_dock_sequence(dock, "departure_cd_at")
    now = datetime.now(timezone.utc)
    route_before = snapshot(route, ["status", "actual_departure_at"])
    dock_before = snapshot(dock, ["departure_cd_at"])
    dock.departure_cd_at = now
    route.actual_departure_at = now
    route.status = "em_rota"
    _recalc_dock(dock)
    record_event(db, route_id=route.id, event_type=EventType.DEPARTED_CD, user_id=user.id)
    log_update(db, user_id=user.id, entity="route", entity_id=route.id, before=route_before,
               obj=route, updates={"status": route.status, "actual_departure_at": route.actual_departure_at})
    log_update(db, user_id=user.id, entity="route_dock", entity_id=route.id, before=dock_before,
               obj=dock, updates={"departure_cd_at": dock.departure_cd_at})
    db.commit()
    return _load(db, route.id)


# ----------------------- Check-in / entrega -----------------------

def _get_stop(db: Session, route_id: int, stop_id: int) -> tuple[Route, RouteStop]:
    route = _load(db, route_id)
    stop = next((s for s in route.stops if s.id == stop_id), None)
    if stop is None:
        raise HTTPException(status_code=404, detail="Ponto de entrega não encontrado.")
    return route, stop


def _ensure_stop_checkin(
    db: Session,
    *,
    route: Route,
    stop: RouteStop,
    user: User,
    latitude: float | None = None,
    longitude: float | None = None,
):
    if stop.checkin_at:
        return
    now = datetime.now(timezone.utc)
    stop.checkin_at = now
    if stop.status == "pendente":
        stop.status = "em_rota"
    stop.latitude = latitude
    stop.longitude = longitude
    db.add(Checkin(stop_id=stop.id, user_id=user.id, latitude=latitude, longitude=longitude, notes="Check-in automático no fechamento da parada."))
    record_event(
        db,
        route_id=route.id,
        stop_id=stop.id,
        event_type=EventType.ARRIVED_STOP,
        user_id=user.id,
        latitude=latitude,
        longitude=longitude,
        notes="Check-in automático no fechamento da parada.",
    )


@router.post("/{route_id}/stops/{stop_id}/checkin", response_model=RouteOut, dependencies=[_OP])
def checkin(route_id: int, stop_id: int, data: CheckinIn,
            db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    route, stop = _get_stop(db, route_id, stop_id)
    require_same_branch(user, route.branch_id)
    _guard_driver_assignment(db, user, route)
    _guard_editable(route)
    _guard_not_expired(route, user)
    _guard_departed(route)
    if stop.checkin_at:
        raise HTTPException(status_code=409, detail="Check-in já registrado para esta entrega.")
    now = datetime.now(timezone.utc)
    stop.checkin_at = now
    stop.status = "em_rota"
    stop.latitude = data.latitude
    stop.longitude = data.longitude
    db.add(Checkin(stop_id=stop.id, user_id=user.id, latitude=data.latitude,
                   longitude=data.longitude, notes=data.notes))
    record_event(db, route_id=route.id, stop_id=stop.id, event_type=EventType.ARRIVED_STOP,
                 user_id=user.id, latitude=data.latitude, longitude=data.longitude)
    db.commit()
    return _load(db, route.id)


@router.post("/{route_id}/stops/{stop_id}/deliver", response_model=RouteOut, dependencies=[_OP])
def deliver(route_id: int, stop_id: int, data: DeliverIn,
            db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    route, stop = _get_stop(db, route_id, stop_id)
    require_same_branch(user, route.branch_id)
    _guard_driver_assignment(db, user, route)
    _guard_editable(route)
    _guard_not_expired(route, user)
    _guard_departed(route)
    if stop.delivered_at or stop.status in {"entregue", "falha"}:
        raise HTTPException(status_code=409, detail="Entrega já encerrada e não pode ser sobreposta.")
    _ensure_stop_checkin(db, route=route, stop=stop, user=user, latitude=data.latitude, longitude=data.longitude)
    now = datetime.now(timezone.utc)
    notes = data.notes
    if data.success:
        if stop.stop_type != "carga" and stop.proof_attachment_id is None:
            raise HTTPException(status_code=422, detail="Comprovante de entrega obrigatório.")
        stop.status = "entregue"
        stop.delivered_at = now
        stop.failure_reason_id = None
        stop.return_type = None
        stop.returned_quantity = None
        ev = EventType.DELIVERED
    else:
        # Na falha o motivo é obrigatório e deve existir/estar ativo.
        if data.failure_reason_id is None:
            raise HTTPException(status_code=422, detail="Motivo da falha é obrigatório.")
        if data.return_type not in {"total", "parcial"}:
            raise HTTPException(status_code=422, detail="Informe se a devolução é total ou parcial.")
        if data.return_type == "parcial" and (data.returned_quantity is None or data.returned_quantity <= 0):
            raise HTTPException(status_code=422, detail="Informe a quantidade devolvida na devolução parcial.")
        reason = db.get(DeliveryFailureReason, data.failure_reason_id)
        if reason is None or not reason.active:
            raise HTTPException(status_code=422, detail="Motivo da falha inválido.")
        stop.status = "falha"
        stop.failure_reason_id = reason.id
        stop.return_type = data.return_type
        stop.returned_quantity = data.returned_quantity if data.return_type == "parcial" else None
        notes = reason.label if not notes else f"{reason.label}: {notes}"
        ev = EventType.FAILED_DELIVERY
    record_event(db, route_id=route.id, stop_id=stop.id, event_type=ev, user_id=user.id,
                 latitude=data.latitude, longitude=data.longitude, notes=notes)
    db.commit()
    return _load(db, route.id)


@router.post("/{route_id}/stops/{stop_id}/deliver-with-proof", response_model=RouteOut, dependencies=[_OP])
async def deliver_with_proof(
    route_id: int,
    stop_id: int,
    success: bool = Form(...),
    failure_reason_id: int | None = Form(None),
    return_type: str | None = Form(None),
    returned_quantity: float | None = Form(None),
    latitude: float | None = Form(None),
    longitude: float | None = Form(None),
    notes: str | None = Form(None),
    proof: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    route, stop = _get_stop(db, route_id, stop_id)
    require_same_branch(user, route.branch_id)
    _guard_driver_assignment(db, user, route)
    _guard_editable(route)
    _guard_not_expired(route, user)
    _guard_departed(route)
    if stop.delivered_at or stop.status in {"entregue", "falha"}:
        raise HTTPException(status_code=409, detail="Entrega já encerrada e não pode ser sobreposta.")
    _ensure_stop_checkin(db, route=route, stop=stop, user=user, latitude=latitude, longitude=longitude)

    if success:
        if stop.stop_type != "carga" and (proof is None or not proof.filename):
            raise HTTPException(status_code=422, detail="Comprovante de entrega obrigatório.")
        if proof is not None and proof.filename:
            attachment = await _save_proof(proof, route, stop, "entrega")
            db.add(attachment)
            db.flush()
            stop.proof_attachment_id = attachment.id
        stop.status = "entregue"
        stop.delivered_at = datetime.now(timezone.utc)
        stop.failure_reason_id = None
        stop.return_type = None
        stop.returned_quantity = None
        event_type = EventType.DELIVERED
        event_notes = notes
    else:
        if proof is None or not proof.filename:
            raise HTTPException(status_code=422, detail="Comprovante da falha é obrigatório.")
        if failure_reason_id is None:
            raise HTTPException(status_code=422, detail="Motivo da falha é obrigatório.")
        if return_type not in {"total", "parcial"}:
            raise HTTPException(status_code=422, detail="Informe se a devolução é total ou parcial.")
        if return_type == "parcial" and (returned_quantity is None or returned_quantity <= 0):
            raise HTTPException(status_code=422, detail="Informe a quantidade devolvida na devolução parcial.")
        reason = db.get(DeliveryFailureReason, failure_reason_id)
        if reason is None or not reason.active:
            raise HTTPException(status_code=422, detail="Motivo da falha inválido.")
        stop.status = "falha"
        stop.failure_reason_id = reason.id
        stop.return_type = return_type
        stop.returned_quantity = returned_quantity if return_type == "parcial" else None
        attachment = await _save_proof(proof, route, stop, "falha")
        db.add(attachment)
        db.flush()
        stop.proof_attachment_id = attachment.id
        event_type = EventType.FAILED_DELIVERY
        event_notes = reason.label if not notes else f"{reason.label}: {notes}"

    record_event(
        db,
        route_id=route.id,
        stop_id=stop.id,
        event_type=event_type,
        user_id=user.id,
        latitude=latitude,
        longitude=longitude,
        notes=event_notes,
    )
    db.commit()
    return _load(db, route.id)


@router.post("/{route_id}/stops/{stop_id}/warehouse-return-proof", response_model=RouteOut, dependencies=[_OP])
async def upload_warehouse_return_proof(
    route_id: int,
    stop_id: int,
    proof: UploadFile = File(...),
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    route, stop = _get_stop(db, route_id, stop_id)
    require_same_branch(user, route.branch_id)
    _guard_driver_assignment(db, user, route)
    _guard_editable(route)
    _guard_not_expired(route, user)
    if stop.status != "falha":
        raise HTTPException(status_code=409, detail="Comprovante de devolução ao armazém é permitido apenas para falhas.")
    attachment = await _save_proof(proof, route, stop, "devolucao-armazem")
    db.add(attachment)
    db.flush()
    stop.warehouse_return_attachment_id = attachment.id
    record_event(
        db,
        route_id=route.id,
        stop_id=stop.id,
        event_type=EventType.FAILED_DELIVERY,
        user_id=user.id,
        notes=notes or "Comprovante de devolução ao armazém enviado.",
    )
    log(db, user_id=user.id, action="warehouse_return_proof", entity="route_stop", entity_id=stop.id)
    db.commit()
    return _load(db, route.id)


@router.post("/{route_id}/close", response_model=RouteOut,
             dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL, Role.OPERADOR_LOGISTICO))])
def close_route(route_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    route = _load(db, route_id)
    require_same_branch(user, route.branch_id)
    _guard_editable(route)
    _guard_not_expired(route, user)
    if not route.dock_session or not route.dock_session.departure_cd_at:
        raise HTTPException(status_code=409, detail="Registre a saída do CD antes de fechar a rota.")
    _guard_all_stops_closed(route)
    _guard_failed_stops_have_warehouse_proofs(route)
    before = snapshot(route, ["status", "closed_at"])
    route.status = "finalizada"
    route.closed_at = datetime.now(timezone.utc)
    record_event(db, route_id=route.id, event_type=EventType.ROUTE_CLOSED, user_id=user.id)
    log_update(db, user_id=user.id, entity="route", entity_id=route.id, before=before,
               obj=route, updates={"status": route.status, "closed_at": route.closed_at})
    db.commit()
    return _load(db, route.id)


@router.post("/{route_id}/reopen", response_model=RouteOut,
             dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL))])
def reopen_route(route_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Reabre uma rota encerrada para correções. Só administrador global."""
    route = _load(db, route_id)
    require_same_branch(user, route.branch_id)
    if route.status not in CLOSED_STATES:
        raise HTTPException(status_code=409, detail="Apenas rotas finalizadas/canceladas podem ser reabertas.")
    before = snapshot(route, ["status", "closed_at"])
    route.status = "em_rota" if route.actual_departure_at else "planejada"
    route.closed_at = None
    record_event(db, route_id=route.id, event_type=EventType.ROUTE_REOPENED, user_id=user.id)
    log_update(db, user_id=user.id, entity="route", entity_id=route.id, before=before,
               obj=route, updates={"status": route.status, "closed_at": route.closed_at})
    db.commit()
    return _load(db, route.id)


@router.post("/{route_id}/admin-correction", response_model=RouteOut,
             dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL))])
def admin_route_correction(
    route_id: int,
    data: AdminRouteCorrectionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Correção operacional emergencial da rota, exclusiva do admin global."""
    route = _load(db, route_id)
    before = {
        "status": route.status,
        "actual_departure_at": route.actual_departure_at,
        "closed_at": route.closed_at,
        "reset_dock_flow": data.reset_dock_flow,
        "reset_all_stops": data.reset_all_stops,
    }
    if data.reset_dock_flow:
        _reset_dock_flow(route)
    if data.reset_all_stops:
        for stop in route.stops:
            _reset_stop_operational_fields(stop)
    if data.status:
        route.status = data.status
        route.closed_at = datetime.now(timezone.utc) if data.status == "finalizada" else None
        if data.status in {"planejada", "em_carregamento", "liberada"}:
            route.actual_departure_at = None
    elif data.reset_dock_flow:
        route.status = "planejada"
    detail = (
        f"justificativa={data.justification}; antes={before}; "
        f"status_final={route.status}; reset_dock={data.reset_dock_flow}; reset_stops={data.reset_all_stops}"
    )
    log(db, user_id=user.id, action="admin_route_correction", entity="route", entity_id=route.id, detail=detail)
    db.commit()
    return _load(db, route.id)


@router.post("/{route_id}/stops/{stop_id}/admin-correction", response_model=RouteOut,
             dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL))])
def admin_stop_correction(
    route_id: int,
    stop_id: int,
    data: AdminStopCorrectionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Correção operacional emergencial da parada, exclusiva do admin global."""
    route, stop = _get_stop(db, route_id, stop_id)
    before = {
        "status": stop.status,
        "failure_reason_id": stop.failure_reason_id,
        "checkin_at": stop.checkin_at,
        "delivered_at": stop.delivered_at,
        "return_type": stop.return_type,
        "returned_quantity": stop.returned_quantity,
        "proof_attachment_id": stop.proof_attachment_id,
        "warehouse_return_attachment_id": stop.warehouse_return_attachment_id,
    }
    if data.clear_checkin:
        stop.checkin_at = None
        stop.latitude = None
        stop.longitude = None
    if data.clear_delivery:
        stop.delivered_at = None
        stop.proof_attachment_id = None if data.clear_proofs else stop.proof_attachment_id
    if data.clear_failure:
        stop.failure_reason_id = None
        stop.return_type = None
        stop.returned_quantity = None
        stop.warehouse_return_attachment_id = None if data.clear_proofs else stop.warehouse_return_attachment_id
    if data.clear_proofs:
        stop.proof_attachment_id = None
        stop.warehouse_return_attachment_id = None
    if data.failure_reason_id is not None:
        reason = db.get(DeliveryFailureReason, data.failure_reason_id)
        if reason is None or not reason.active:
            raise HTTPException(status_code=422, detail="Motivo da falha inválido.")
        stop.failure_reason_id = reason.id
    if data.return_type is not None:
        stop.return_type = data.return_type
        stop.returned_quantity = data.returned_quantity if data.return_type == "parcial" else None
    if data.status:
        stop.status = data.status
        if data.status in {"pendente", "em_rota"}:
            stop.delivered_at = None
            stop.failure_reason_id = None
            stop.return_type = None
            stop.returned_quantity = None
        if data.status == "pendente":
            stop.checkin_at = None
        if data.status == "entregue" and stop.delivered_at is None:
            stop.delivered_at = datetime.now(timezone.utc)
        if data.status == "falha" and stop.failure_reason_id is None:
            raise HTTPException(status_code=422, detail="Motivo da falha é obrigatório para status falha.")
    detail = f"justificativa={data.justification}; antes={before}; status_final={stop.status}"
    log(db, user_id=user.id, action="admin_stop_correction", entity="route_stop", entity_id=stop.id, detail=detail)
    db.commit()
    return _load(db, route.id)


# ----------------------- Pedágios -----------------------

_TOLL_USER = Depends(require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL, Role.OPERADOR_LOGISTICO, Role.MOTORISTA))


@router.post("/{route_id}/tolls", response_model=RouteOut, dependencies=[_TOLL_USER])
def add_toll(route_id: int, data: RouteTollIn,
              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Registra um lançamento de pedágio (ida ou volta). Pode haver vários por sentido."""
    route = _load(db, route_id)
    require_same_branch(user, route.branch_id)
    _guard_driver_assignment(db, user, route)
    _guard_not_cancelled(route)
    if data.amount <= 0:
        raise HTTPException(status_code=422, detail="Valor do pedágio deve ser maior que zero.")
    toll = RouteToll(route_id=route.id, direction=data.direction, amount=data.amount, recorded_by=user.id)
    db.add(toll)
    db.flush()
    log(db, user_id=user.id, action="create", entity="route_toll", entity_id=toll.id,
        detail=f"route_id={route.id}; " + (format_changes({"direction": (None, toll.direction), "amount": (None, toll.amount)}) or ""))
    db.commit()
    return _load(db, route.id)


@router.delete("/{route_id}/tolls/{toll_id}", response_model=RouteOut, dependencies=[_EDITOR])
def delete_toll(route_id: int, toll_id: int,
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    route = _load(db, route_id)
    require_same_branch(user, route.branch_id)
    toll = next((t for t in route.tolls if t.id == toll_id), None)
    if toll is None:
        raise HTTPException(status_code=404, detail="Lançamento de pedágio não encontrado.")
    detail = format_changes({"direction": (toll.direction, None), "amount": (toll.amount, None)})
    db.delete(toll)
    log(db, user_id=user.id, action="delete", entity="route_toll", entity_id=toll.id,
        detail=f"route_id={route.id}; {detail}")
    db.commit()
    return _load(db, route.id)


# ----------------------- Forçar início de rota -----------------------

@router.post("/{route_id}/force-start", response_model=RouteOut, dependencies=[_OP])
def force_start_route(route_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Força o início da rota ignorando o fluxo de doca (preenche todos os passos com now)."""
    route = _load(db, route_id)
    require_same_branch(user, route.branch_id)
    _guard_editable(route)
    now = datetime.now(timezone.utc)
    route_before = snapshot(route, ["status", "actual_departure_at"])
    dock = route.dock_session
    if dock is None:
        dock = DockSession(route_id=route.id)
        db.add(dock)
        route.dock_session = dock
    dock_fields = ["arrival_cd_at", "dock_entry_at", "loading_started_at", "loading_finished_at", "operator_released_at", "departure_cd_at"]
    dock_before = snapshot(dock, dock_fields)
    if not dock.arrival_cd_at:
        dock.arrival_cd_at = now
    if not dock.dock_entry_at:
        dock.dock_entry_at = now
    if not dock.loading_started_at:
        dock.loading_started_at = now
    if not dock.loading_finished_at:
        dock.loading_finished_at = now
    if not dock.operator_released_at:
        dock.operator_released_at = now
    if not dock.departure_cd_at:
        dock.departure_cd_at = now
    route.actual_departure_at = route.actual_departure_at or now
    route.status = "em_rota"
    _recalc_dock(dock)
    record_event(db, route_id=route.id, event_type=EventType.DEPARTED_CD, user_id=user.id)
    route_updates = {"status": route.status, "actual_departure_at": route.actual_departure_at}
    log_update(db, user_id=user.id, entity="route", entity_id=route.id,
               before=route_before, obj=route, updates=route_updates)
    log_update(db, user_id=user.id, entity="route_dock", entity_id=route.id,
               before=dock_before, obj=dock, updates={field: getattr(dock, field) for field in dock_fields})
    db.commit()
    return _load(db, route.id)


# ----------------------- KM final (ida/volta) -----------------------

_KM_USER = Depends(require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL, Role.OPERADOR_LOGISTICO, Role.MOTORISTA))


@router.put("/{route_id}/km", response_model=RouteOut, dependencies=[_KM_USER])
def update_km(route_id: int, data: RouteKmIn,
               db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Registra o KM final informado pelo motorista para ida e/ou volta."""
    route = _load(db, route_id)
    require_same_branch(user, route.branch_id)
    _guard_driver_assignment(db, user, route)
    _guard_not_cancelled(route)
    updates = data.model_dump(exclude_unset=True)
    before = snapshot(route, list(updates))
    for field, value in updates.items():
        if value is not None and value < 0:
            raise HTTPException(status_code=422, detail="KM informado deve ser maior ou igual a zero.")
        setattr(route, field, value)
    log_update(db, user_id=user.id, entity="route", entity_id=route.id,
               before=before, obj=route, updates=updates)
    db.commit()
    return _load(db, route.id)

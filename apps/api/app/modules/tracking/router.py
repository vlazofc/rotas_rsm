"""Rastreamento consentido: recepção de posições e painel da torre de controle."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.permissions import Role, require_feature, require_same_branch
from app.db.models import Driver, ProviderVehiclePosition, Route, TrackingConsent, User, Vehicle, VehiclePosition
from app.db.session import get_db
from app.modules.auth.deps import get_current_user

router = APIRouter(prefix="/tracking", tags=["tracking"], dependencies=[Depends(require_feature("feature_rastreamento"))])

class ConsentIn(BaseModel):
    accepted: bool
    terms_version: str = "1.0"

class PositionIn(BaseModel):
    route_id: int
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, ge=0)
    speed_kmh: float | None = Field(default=None, ge=0)
    recorded_at: datetime | None = None

@router.get("/consent")
def consent(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.scalar(select(TrackingConsent).where(TrackingConsent.user_id == user.id).order_by(TrackingConsent.id.desc()))
    return {"accepted": bool(row and row.accepted), "terms_version": row.terms_version if row else "1.0"}

@router.put("/consent")
def update_consent(data: ConsentIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    row = TrackingConsent(user_id=user.id, accepted=data.accepted, terms_version=data.terms_version,
                          accepted_at=now if data.accepted else None, revoked_at=None if data.accepted else now)
    db.add(row); db.commit()
    return {"accepted": row.accepted, "terms_version": row.terms_version}

@router.post("/positions", status_code=201)
def record_position(data: PositionIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    accepted = db.scalar(select(TrackingConsent).where(TrackingConsent.user_id == user.id, TrackingConsent.accepted.is_(True)).order_by(TrackingConsent.id.desc()))
    if not accepted:
        raise HTTPException(409, "É necessário aceitar o termo de rastreamento.")
    route = db.get(Route, data.route_id)
    if route is None:
        raise HTTPException(404, "Rota não encontrada.")
    require_same_branch(user, route.branch_id)
    if user.role == Role.MOTORISTA.value:
        driver = db.scalar(select(Driver).where(Driver.user_id == user.id))
        if driver is None or route.driver_id != driver.id:
            raise HTTPException(403, "Rota não atribuída a este motorista.")
    row = VehiclePosition(branch_id=route.branch_id, route_id=route.id, vehicle_id=route.vehicle_id,
                          driver_id=route.driver_id, user_id=user.id, latitude=data.latitude,
                          longitude=data.longitude, accuracy_m=data.accuracy_m, speed_kmh=data.speed_kmh,
                          recorded_at=data.recorded_at or datetime.now(timezone.utc))
    db.add(row); db.commit()
    return {"id": row.id, "recorded_at": row.recorded_at}

@router.get("/live")
def live_positions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role not in {Role.ADMIN_GLOBAL.value, Role.GESTOR_BRASIL.value, Role.TORRE_CONTROLE.value}:
        raise HTTPException(403, "Perfil sem permissão para monitoramento.")
    latest = select(VehiclePosition.route_id, func.max(VehiclePosition.recorded_at).label("latest")).group_by(VehiclePosition.route_id).subquery()
    stmt = (select(VehiclePosition, Route.codigo_ut, Vehicle.plate, Driver.name)
            .join(latest, (latest.c.route_id == VehiclePosition.route_id) & (latest.c.latest == VehiclePosition.recorded_at))
            .join(Route, Route.id == VehiclePosition.route_id)
            .outerjoin(Vehicle, Vehicle.id == VehiclePosition.vehicle_id)
            .outerjoin(Driver, Driver.id == VehiclePosition.driver_id))
    if user.role != Role.ADMIN_GLOBAL.value and user.branch_id:
        stmt = stmt.where(VehiclePosition.branch_id == user.branch_id)
    result = [{"route_id": p.route_id, "codigo_ut": code, "vehicle_plate": plate, "driver_name": name,
             "latitude": p.latitude, "longitude": p.longitude, "accuracy_m": p.accuracy_m,
             "speed_kmh": p.speed_kmh, "recorded_at": p.recorded_at, "source": "app"} for p, code, plate, name in db.execute(stmt).all()]
    provider_latest = (select(ProviderVehiclePosition.route_id, func.max(ProviderVehiclePosition.recorded_at).label("latest"))
                       .where(ProviderVehiclePosition.route_id.is_not(None)).group_by(ProviderVehiclePosition.route_id).subquery())
    provider_stmt = (select(ProviderVehiclePosition, Route.codigo_ut, Vehicle.plate, Driver.name)
                     .join(provider_latest, (provider_latest.c.route_id == ProviderVehiclePosition.route_id) &
                           (provider_latest.c.latest == ProviderVehiclePosition.recorded_at))
                     .join(Route, Route.id == ProviderVehiclePosition.route_id)
                     .outerjoin(Vehicle, Vehicle.id == ProviderVehiclePosition.vehicle_id)
                     .outerjoin(Driver, Driver.id == Route.driver_id))
    if user.role != Role.ADMIN_GLOBAL.value and user.branch_id:
        provider_stmt = provider_stmt.where(ProviderVehiclePosition.branch_id == user.branch_id)
    provider_rows = [{"route_id": p.route_id, "codigo_ut": code, "vehicle_plate": plate, "driver_name": name,
                      "latitude": p.latitude, "longitude": p.longitude, "accuracy_m": None,
                      "speed_kmh": p.speed_kmh, "recorded_at": p.recorded_at, "source": "truckcontrol"}
                     for p, code, plate, name in db.execute(provider_stmt).all()]
    # Para a mesma rota, entrega somente a fonte com a posição mais recente.
    by_route = {row["route_id"]: row for row in result}
    for row in provider_rows:
        current = by_route.get(row["route_id"])
        if current is None or row["recorded_at"] > current["recorded_at"]:
            by_route[row["route_id"]] = row
    return list(by_route.values())

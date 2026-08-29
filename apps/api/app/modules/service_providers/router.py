"""Prestadores de serviço autorizados (oficina, borracharia, guincho etc.) e busca por raio de km.

Distinto de Carrier (transportadora). A distância é calculada em Python (Haversine),
adequada ao volume de prestadores cadastrados por filial.
"""
import math
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import Role, require_branch_access, require_roles, require_same_branch
from app.db.models import Route, RouteEvent, ServiceProvider, Supplier, User
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services.audit import log, log_update, snapshot

router = APIRouter(prefix="/service-providers", tags=["service-providers"])

_MANAGER = require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL)
CATEGORIES = {"oficina_mecanica", "borracharia", "eletrica", "guincho", "posto_combustivel", "lavagem", "outros"}
EARTH_RADIUS_KM = 6371.0


class ServiceProviderIn(BaseModel):
    branch_id: int | None = None
    supplier_id: int | None = None
    name: str
    document: str | None = None
    category: str = "outros"
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    authorized: bool = True


class ServiceProviderUpdate(BaseModel):
    supplier_id: int | None = None
    name: str | None = None
    document: str | None = None
    category: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    authorized: bool | None = None
    rating: float | None = None
    active: bool | None = None


class ServiceProviderOut(BaseModel):
    id: int
    branch_id: int | None
    supplier_id: int | None
    name: str
    document: str | None
    category: str
    phone: str | None
    email: str | None
    address: str | None
    latitude: float | None
    longitude: float | None
    authorized: bool
    rating: float | None
    active: bool

    class Config:
        from_attributes = True


class ServiceProviderNearbyOut(ServiceProviderOut):
    distance_km: float


class VehiclePositionOut(BaseModel):
    latitude: float | None
    longitude: float | None
    source: str | None = None  # route_event
    at: datetime | None = None


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r1, r2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(r1) * math.cos(r2) * math.sin(dlng / 2) ** 2
    return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(a))


def _validate_category(category: str) -> str:
    if category not in CATEGORIES:
        raise HTTPException(status_code=400, detail="Categoria inválida.")
    return category


def _provider_query(user: User):
    stmt = select(ServiceProvider).where(ServiceProvider.active.is_(True))
    if user.role != Role.ADMIN_GLOBAL.value and user.branch_id:
        stmt = stmt.where((ServiceProvider.branch_id == user.branch_id) | (ServiceProvider.branch_id.is_(None)))
    return stmt


@router.get("", response_model=list[ServiceProviderOut])
def list_providers(category: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = _provider_query(user).order_by(ServiceProvider.name)
    if category:
        stmt = stmt.where(ServiceProvider.category == _validate_category(category))
    return db.scalars(stmt).all()


@router.get("/nearby", response_model=list[ServiceProviderNearbyOut])
def nearby_providers(
    lat: float, lng: float, radius_km: float = 25, category: str | None = None,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    if radius_km <= 0 or radius_km > 500:
        raise HTTPException(status_code=400, detail="Raio inválido (use até 500 km).")
    stmt = _provider_query(user).where(
        ServiceProvider.latitude.is_not(None), ServiceProvider.longitude.is_not(None),
        ServiceProvider.authorized.is_(True),
    )
    if category:
        stmt = stmt.where(ServiceProvider.category == _validate_category(category))
    results = []
    for provider in db.scalars(stmt).all():
        distance = _haversine_km(lat, lng, provider.latitude, provider.longitude)
        if distance <= radius_km:
            out = ServiceProviderNearbyOut.model_validate(provider)
            out.distance_km = round(distance, 1)
            results.append(out)
    results.sort(key=lambda p: p.distance_km)
    return results


@router.get("/vehicle-position/{vehicle_id}", response_model=VehiclePositionOut)
def vehicle_position(vehicle_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Última posição conhecida do veículo — a partir do route_event mais recente
    (com lat/lng) entre as rotas desse veículo. Não é GPS em tempo real."""
    row = db.execute(
        select(RouteEvent.latitude, RouteEvent.longitude, RouteEvent.event_time)
        .join(Route, Route.id == RouteEvent.route_id)
        .where(Route.vehicle_id == vehicle_id, RouteEvent.latitude.is_not(None), RouteEvent.longitude.is_not(None))
        .order_by(RouteEvent.event_time.desc())
        .limit(1)
    ).first()
    if row is None:
        return VehiclePositionOut(latitude=None, longitude=None, source=None, at=None)
    return VehiclePositionOut(latitude=row[0], longitude=row[1], source="route_event", at=row[2])


@router.post("", response_model=ServiceProviderOut, dependencies=[Depends(_MANAGER)])
def create_provider(data: ServiceProviderIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if data.branch_id is not None:
        require_branch_access(db, actor, data.branch_id)
    _validate_category(data.category)
    if data.supplier_id is not None:
        supplier = db.get(Supplier, data.supplier_id)
        if supplier is None or supplier.tenant_id != actor.tenant_id or supplier.supplier_type not in {"service", "both"}:
            raise HTTPException(422, "Selecione um fornecedor de serviços válido.")
    provider = ServiceProvider(**data.model_dump())
    db.add(provider)
    db.flush()
    log(db, user_id=actor.id, action="create", entity="service_provider", entity_id=provider.id, detail=f'"{provider.name}"')
    db.commit()
    db.refresh(provider)
    return provider


@router.put("/{provider_id}", response_model=ServiceProviderOut, dependencies=[Depends(_MANAGER)])
def update_provider(provider_id: int, data: ServiceProviderUpdate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    provider = db.get(ServiceProvider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Prestador não encontrado.")
    if provider.branch_id is not None:
        require_same_branch(actor, provider.branch_id)
    updates = data.model_dump(exclude_unset=True)
    if updates.get("supplier_id") is not None:
        supplier = db.get(Supplier, updates["supplier_id"])
        if supplier is None or supplier.tenant_id != actor.tenant_id or supplier.supplier_type not in {"service", "both"}:
            raise HTTPException(422, "Selecione um fornecedor de serviços válido.")
    if "category" in updates:
        _validate_category(updates["category"])
    before = snapshot(provider, list(updates))
    for field, value in updates.items():
        setattr(provider, field, value)
    log_update(db, user_id=actor.id, entity="service_provider", entity_id=provider.id, before=before, obj=provider, updates=updates)
    db.commit()
    db.refresh(provider)
    return provider


@router.delete("/{provider_id}", dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL))])
def delete_provider(provider_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    provider = db.get(ServiceProvider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Prestador não encontrado.")
    name = provider.name
    db.delete(provider)
    log(db, user_id=actor.id, action="delete", entity="service_provider", entity_id=provider_id, detail=f'"{name}"')
    db.commit()
    return {"deleted": provider_id}

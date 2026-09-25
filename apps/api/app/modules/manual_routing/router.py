from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from app.core.permissions import Role, require_internal_permission
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.routing import calculate_manual_route, routing_enabled

router = APIRouter(prefix="/manual-routing", tags=["manual-routing"], dependencies=[Depends(require_internal_permission("module.routing", Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL, Role.OPERADOR_LOGISTICO, Role.TORRE_CONTROLE))])

class ManualRouteIn(BaseModel):
    origin: str = Field(min_length=3, max_length=300)
    destinations: list[str] = Field(min_length=1, max_length=50)
    vehicle: Literal["car", "truck_medium", "truck_large", "truck_articulated"] = "car"
    optimize: bool = True

@router.post("")
def manual_route(data: ManualRouteIn, db: Session = Depends(get_db)):
    if not routing_enabled(db):
        raise HTTPException(status_code=503, detail="Roteirizador desligado pelo Administrador Global.")
    result = calculate_manual_route(data.origin, data.destinations, data.vehicle, data.optimize)
    if not result:
        raise HTTPException(status_code=422, detail="O Maestro não conseguiu calcular este trajeto.")
    route = result.get("route", {})
    duration = route.get("time", route.get("duration"))
    return {
        "origin_coords": result.get("origin_coords"), "destination_coords": result.get("dest_coords"),
        "waypoint_coords": result.get("waypoint_coords", []), "waypoint_order": result.get("waypoint_order", []),
        "ordered_destinations": result.get("ordered_waypoints", []) + [data.destinations[-1]],
        "geometry": route.get("points", {}).get("coordinates", []),
        "distance_km": round(float(route.get("distance", 0)) / 1000, 1),
        "duration_minutes": round(float(duration) / 60000) if duration is not None else None,
    }

"""Cliente do Maestro e serviços de geocodificação/roteirização."""
from __future__ import annotations
import json
import re
from datetime import datetime, timezone
from typing import Any
import httpx
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.logging import logger
from app.db.models import Branch, OperationalSettings

def routing_enabled(db: Session) -> bool:
    row = db.get(OperationalSettings, 1)
    return row is None or row.routing_enabled is not False

VEHICLE_KEYWORDS = {"truck_articulated": ("carreta", "articulado", "bitrem", "rodotrem"), "truck_large": ("truck", "toco", "bau", "baú"), "truck_medium": ("3/4", "vuc", "ligeiro")}

def map_vehicle(label: str | None) -> str:
    value = (label or "").strip().lower()
    for vehicle, keywords in VEHICLE_KEYWORDS.items():
        if any(keyword in value for keyword in keywords): return vehicle
    return "car"

def _request_route(origin: str, destination: str, waypoints: list[str] | None = None, vehicle: str = "car", optimize: bool = False) -> dict[str, Any] | None:
    headers = {"Authorization": f"Bearer {settings.router_api_key}"} if settings.router_api_key else {}
    params: dict[str, Any] = {"origin": origin, "destination": destination, "vehicle": vehicle}
    if waypoints: params["waypoints"] = "|".join(waypoints)
    if optimize: params["optimize"] = "true"
    try:
        response = httpx.get(f"{settings.router_base_url.rstrip('/')}/api/route", params=params, headers=headers, timeout=90)
        response.raise_for_status(); data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Falha ao consultar Maestro: %s", exc); return None
    if not data.get("success"):
        logger.warning("Maestro recusou a rota: %s", data.get("error")); return None
    return data

def calculate_leg(origin_address: str, destination: str, vehicle: str = "car") -> tuple[float, int | None] | None:
    data = _request_route(origin_address, destination, vehicle=vehicle)
    if not data: return None
    route_data = data["route"]; duration = route_data.get("time", route_data.get("duration"))
    return round(float(route_data["distance"]) / 1000, 1), round(float(duration) / 60000) if duration is not None else None

def calculate_km(origin_address: str, destination: str, vehicle: str = "car") -> float | None:
    leg = calculate_leg(origin_address, destination, vehicle); return leg[0] if leg else None

def _address(stop) -> str:
    address = re.sub(r"\b(?:SOB\s*LJ|SOBRELOJA)\b", "", stop.customer_address or "", flags=re.IGNORECASE)
    address = re.sub(r"\s{2,}", " ", address).strip(" ,-.")
    address = re.sub(r"\s+,", ",", address)
    parts = [address, stop.province, stop.postal_code, stop.city, "Brasil"]
    return ", ".join(str(part).strip() for part in parts if part) or stop.customer_name

STATE_BOUNDS = {
    # Limites amplos do estado, usados como trava contra homônimos em outras UFs.
    "SP": (-25.4, -19.7, -53.2, -44.0),
}


def _coords(value: Any, province: str | None = None) -> tuple[float, float] | None:
    if not isinstance(value, dict): return None
    try: lat, lng = float(value["lat"]), float(value["lng"])
    except (KeyError, TypeError, ValueError): return None
    if not (-34.0 <= lat <= 6.0 and -74.0 <= lng <= -28.0):
        return None
    bounds = STATE_BOUNDS.get((province or "").strip().upper())
    if bounds and not (bounds[0] <= lat <= bounds[1] and bounds[2] <= lng <= bounds[3]):
        return None
    return lat, lng

def _geometry(data: dict[str, Any]) -> str | None:
    coordinates = data.get("route", {}).get("points", {}).get("coordinates")
    return json.dumps(coordinates, separators=(",", ":")) if isinstance(coordinates, list) and len(coordinates) >= 2 else None

def _route_in_legs(route, groups: list[list[Any]], actual_origin: str | None) -> dict[str, Any]:
    """Fallback tolerante para uma carga que o Maestro não aceita em lote."""
    vehicle = map_vehicle(route.vehicle_sent or route.vehicle_requested)
    current = actual_origin or _address(groups[0][0])
    start_index = 0 if actual_origin else 1
    coordinates: list[list[float]] = []; distance = 0.0; duration = 0.0; located = 0
    if not actual_origin:
        seed = _request_route(current, current, vehicle=vehicle)
        point = _coords(seed.get("origin_coords")) if seed else None
        if point:
            for stop in groups[0]: stop.latitude, stop.longitude = point
            located += len(groups[0])
    for group in groups[start_index:]:
        destination = _address(group[0]); data = _request_route(current, destination, vehicle=vehicle)
        if not data: continue
        if not actual_origin and located == 0:
            first_point = _coords(data.get("origin_coords"))
            if first_point:
                for stop in groups[0]: stop.latitude, stop.longitude = first_point
                located += len(groups[0])
        point = _coords(data.get("dest_coords"), group[0].province)
        if point:
            for stop in group: stop.latitude, stop.longitude = point
            located += len(group)
        leg = data.get("route", {}); distance += float(leg.get("distance", 0)); duration += float(leg.get("time", leg.get("duration", 0)) or 0)
        leg_coords = leg.get("points", {}).get("coordinates") or []
        if leg_coords: coordinates.extend(leg_coords[1:] if coordinates else leg_coords)
        current = destination
    return {"located": located, "distance": distance, "duration": duration, "coordinates": coordinates}

def route_through_stops(db: Session, route, *, optimize: bool = False) -> dict[str, Any]:
    """Geocodifica a carga inteira no Maestro e persiste pontos e linha viária."""
    if not routing_enabled(db):
        return {"success": False, "disabled": True, "error": "Roteirizador desligado pelo Administrador Global.", "route_id": route.id}
    stops = sorted(route.stops, key=lambda item: (item.sequence, item.id))
    if not stops: return {"success": False, "error": "A rota não possui paradas.", "route_id": route.id}
    # Não reaproveitar coordenadas de uma localização anterior que falhou.
    for stop in stops:
        stop.latitude = stop.longitude = None
    # Notas diferentes podem apontar para o mesmo cliente/endereço. O GraphHopper
    # rejeita alguns trechos consecutivos de distância zero; agrupamos esses casos
    # sem perder nenhuma parada nem sua sequência.
    groups: list[list[Any]] = []
    for stop in stops:
        if groups and _address(groups[-1][0]).casefold() == _address(stop).casefold(): groups[-1].append(stop)
        else: groups.append([stop])
    grouped_stops = [group[0] for group in groups]
    addresses = [_address(stop) for stop in grouped_stops]
    if route.source == "automatico" and not route.origin_address:
        # Recupera a coluna V de cargas já importadas sem substituir o CD
        # pelo endereço da primeira entrega.
        for stop in stops:
            try:
                imported = json.loads(stop.raw_import_json or '{}')
            except (TypeError, ValueError):
                continue
            if not isinstance(imported, dict):
                continue
            origin = next((str(value).strip() for key, value in imported.items()
                           if str(key).strip().upper() == 'ORIGEM' and value and str(value).strip()), None)
            if origin:
                route.origin_address = origin
                break
    if not route.origin_address:
        branch = db.get(Branch, route.branch_id)
        if branch and branch.default_origin_address:
            route.origin_address = branch.default_origin_address
    actual_origin = route.origin_address or route.origin_name or settings.sharepoint_sync_origin_address
    can_optimize = bool(actual_origin) and len(groups) > 1 and optimize
    if actual_origin:
        origin, destination, waypoint_addresses, mapped_groups, destination_group = actual_origin, addresses[-1], addresses[:-1], groups[:-1], groups[-1]
    elif len(groups) > 1:
        origin, destination, waypoint_addresses, mapped_groups, destination_group = addresses[0], addresses[-1], addresses[1:-1], groups[1:-1], groups[-1]
    else:
        origin = destination = addresses[0]; waypoint_addresses, mapped_groups, destination_group = [], [], groups[0]
    data = _request_route(origin, destination, waypoint_addresses, map_vehicle(route.vehicle_sent or route.vehicle_requested), can_optimize)
    if not data:
        fallback = _route_in_legs(route, groups, actual_origin)
        route.routing_geometry_json = json.dumps(fallback["coordinates"], separators=(",", ":")) if len(fallback["coordinates"]) >= 2 else None
        route.routing_distance_km = round(fallback["distance"] / 1000, 1)
        route.routing_duration_minutes = round(fallback["duration"] / 60000)
        missing = len(stops) - fallback["located"]
        if missing:
            route.routing_geometry_json = None
            route.suggested_geometry_json = None
            route.routing_distance_km = None
            route.routing_duration_minutes = None
        route.routing_status = "error" if missing else "pending"
        route.routing_error = f"{missing} parada(s) com localização pendente. Confira endereço e cidade; estimativa indisponível até a validação." if missing else None
        db.flush()
        return {"success": missing == 0, "error": route.routing_error, "route_id": route.id,
                "changed_stops": 0, "distance_km": route.routing_distance_km,
                "duration_minutes": route.routing_duration_minutes, "optimized": False}
    if not actual_origin:
        first = _coords(data.get("origin_coords"))
        if first:
            for stop in groups[0]: stop.latitude, stop.longitude = first
    waypoint_coords = data.get("waypoint_coords") or []
    waypoint_order = data.get("waypoint_order") or list(range(len(mapped_groups)))
    ordered_middle = [mapped_groups[index] for index in waypoint_order if 0 <= index < len(mapped_groups)]
    for group, raw_coord in zip(ordered_middle, waypoint_coords):
        point = _coords(raw_coord, group[0].province)
        if point:
            for stop in group: stop.latitude, stop.longitude = point
    last = _coords(data.get("dest_coords"), destination_group[0].province)
    if last:
        for stop in destination_group: stop.latitude, stop.longitude = last
    missing = [stop for stop in stops if stop.latitude is None or stop.longitude is None]
    if missing:
        route.routing_geometry_json = None
        route.suggested_geometry_json = None
        route.routing_distance_km = None
        route.routing_duration_minutes = None
        route.routing_status = "error"
        route.routing_error = f"{len(missing)} parada(s) retornaram localização incompatível com a UF informada. Confira endereço e CEP."
        db.flush()
        return {"success": False, "error": route.routing_error, "route_id": route.id,
                "changed_stops": 0, "distance_km": None, "duration_minutes": None,
                "optimized": False}
    route_data = data.get("route", {}); duration = route_data.get("time", route_data.get("duration"))
    distance = round(float(route_data.get("distance", 0)) / 1000, 1); minutes = round(float(duration) / 60000) if duration is not None else None
    geometry = _geometry(data)
    if can_optimize:
        ordered = [stop for group in ordered_middle + [destination_group] for stop in group]
        for sequence, stop in enumerate(ordered, 1): stop.optimized_sequence = sequence
        route.suggested_geometry_json = geometry; route.routing_status = "optimized"; route.routing_optimized_at = datetime.now(timezone.utc)
    else:
        route.routing_geometry_json = geometry
        route.suggested_geometry_json = None
        for stop in stops: stop.optimized_sequence = None
        route.routing_status = "pending"
    route.routing_distance_km = distance; route.routing_duration_minutes = minutes; route.routing_error = None; db.flush()
    changed = sum(int(stop.optimized_sequence is not None and stop.sequence != stop.optimized_sequence) for stop in stops)
    return {"success": True, "route_id": route.id, "changed_stops": changed, "distance_km": distance, "duration_minutes": minutes, "optimized": can_optimize}

def optimize_route(db: Session, route, *, origin: str | None = None, apply: bool = False) -> dict:
    if origin: route.origin_address = origin
    if not route.origin_address:
        branch = db.get(Branch, route.branch_id)
        if branch and branch.default_origin_address:
            route.origin_address = branch.default_origin_address
    if not (route.origin_address or route.origin_name or settings.sharepoint_sync_origin_address):
        result = route_through_stops(db, route, optimize=False)
        # A base JM atual não possui origem. Ainda assim, os clientes devem ser
        # geocodificados e exibidos no mapa; somente a otimização a partir do CD
        # fica pendente até que uma origem seja informada.
        return result
    result = route_through_stops(db, route, optimize=True)
    if result.get("success") and apply:
        for stop in route.stops: stop.sequence = stop.optimized_sequence
        route.routing_geometry_json = route.suggested_geometry_json
    return result

def calculate_round_trip_km(origin_address: str, destination: str, vehicle: str = "car") -> tuple[float | None, float | None]:
    return calculate_km(origin_address, destination, vehicle), calculate_km(destination, origin_address, vehicle)


def calculate_manual_route(origin: str, destinations: list[str], vehicle: str = "car", optimize: bool = True) -> dict[str, Any] | None:
    if not destinations:
        return None
    return _request_route(origin, destinations[-1], destinations[:-1], vehicle, optimize)

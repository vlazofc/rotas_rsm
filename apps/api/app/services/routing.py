"""Cliente do router_run (maestro/GraphHopper) — cálculo de KM filial -> destino."""
import httpx

from app.core.config import settings
from app.core.logging import logger

VEHICLE_KEYWORDS = {
    "truck_articulated": ("carreta", "articulado", "bitrem", "rodotrem"),
    "truck_large": ("truck", "toco", "bau", "baú"),
    "truck_medium": ("3/4", "vuc", "ligeiro"),
}


def map_vehicle(label: str | None) -> str:
    """Mapeia o texto livre de SOLICITADO/ENVIADO para o enum aceito pelo maestro."""
    if not label:
        return "car"
    value = label.strip().lower()
    for vehicle, keywords in VEHICLE_KEYWORDS.items():
        if any(keyword in value for keyword in keywords):
            return vehicle
    return "car"


def calculate_km(origin_address: str, destination: str, vehicle: str = "car") -> float | None:
    """Retorna a distância filial -> destino em km, ou None se o router falhar.

    O maestro geocodifica origem/destino internamente (ViaCEP/Photon/Nominatim) —
    não é necessário resolver coordenadas antes de chamar.
    """
    headers = {"Authorization": f"Bearer {settings.router_api_key}"} if settings.router_api_key else {}
    try:
        resp = httpx.get(
            f"{settings.router_base_url}/api/route",
            params={"origin": origin_address, "destination": destination, "vehicle": vehicle},
            headers=headers,
            timeout=15,
        )
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Falha ao consultar router_run para %r -> %r: %s", origin_address, destination, exc)
        return None
    if not data.get("success"):
        logger.warning("router_run não conseguiu rotear %r -> %r: %s", origin_address, destination, data.get("error"))
        return None
    return round(data["route"]["distance"] / 1000, 1)


def calculate_round_trip_km(origin_address: str, destination: str, vehicle: str = "car") -> tuple[float | None, float | None]:
    """KM de ida (filial -> destino) e volta (destino -> filial), calculados
    separadamente — a distância pode não ser simétrica (vias de mão única,
    restrições para caminhões, etc.)."""
    outbound = calculate_km(origin_address, destination, vehicle)
    inbound = calculate_km(destination, origin_address, vehicle)
    return outbound, inbound

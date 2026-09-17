"""Cliente XML TruckControl 6.7 e persistência de posições."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from defusedxml import ElementTree as ET

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ProviderVehicle, ProviderVehiclePosition, Route, TrackingIntegration, Vehicle
from app.services.integration_secrets import decrypt_secret

PROVIDER = "truckcontrol"
DEFAULT_URL = "https://webservice.newrastreamentoonline.com.br"


def _text(node: ET.Element, name: str) -> str:
    return (node.findtext(name) or "").strip()


def _request(config: TrackingIntegration, root_name: str, message_id: int | None = None) -> ET.Element:
    root = ET.Element(root_name)
    ET.SubElement(root, "login").text = decrypt_secret(config.login_encrypted)
    ET.SubElement(root, "senha").text = decrypt_secret(config.password_encrypted)
    if message_id is not None:
        ET.SubElement(root, "mId").text = str(message_id)
    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with httpx.Client(timeout=httpx.Timeout(12.0, connect=5.0), follow_redirects=False) as client:
        response = client.post(config.base_url, content=payload, headers={"Content-Type": "application/xml"})
        response.raise_for_status()
    if len(response.content) > 5_000_000:
        raise ValueError("Resposta TruckControl acima do limite de segurança.")
    return ET.fromstring(response.content)


def _plate(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def sync_vehicles(db: Session, config: TrackingIntegration) -> dict:
    root = _request(config, "RequestVeiculo")
    count = linked = 0
    for node in root.findall(".//Veiculo"):
        external_id, plate = _text(node, "veiID"), _plate(_text(node, "placa"))
        if not external_id:
            continue
        row = db.scalar(select(ProviderVehicle).where(
            ProviderVehicle.provider == PROVIDER, ProviderVehicle.external_vehicle_id == external_id))
        if row is None:
            row = ProviderVehicle(provider=PROVIDER, external_vehicle_id=external_id)
            db.add(row)
        vehicle = db.scalar(select(Vehicle).where(
            func_normalized_plate(Vehicle.plate) == plate,
            Vehicle.ownership_type == "proprio",
            Vehicle.active.is_(True),
        )) if plate else None
        row.plate, row.vehicle_id = plate or None, vehicle.id if vehicle else None
        row.raw_data = json.dumps({child.tag: (child.text or "") for child in node}, ensure_ascii=False)
        count += 1
        linked += int(vehicle is not None)
    now = datetime.now(timezone.utc)
    config.last_vehicle_sync_at = config.last_success_at = now
    config.last_error = None
    db.commit()
    return {"vehicles": count, "linked": linked}


def func_normalized_plate(column):
    from sqlalchemy import func
    return func.upper(func.replace(func.replace(column, "-", ""), " ", ""))


def _number(value: str) -> float | None:
    try:
        return float(value.replace(",", "."))
    except (TypeError, ValueError):
        return None


def _date(value: str) -> datetime:
    from dateutil import parser
    parsed = parser.parse(value, dayfirst=True)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def sync_positions(db: Session, config: TrackingIntegration) -> dict:
    root = _request(config, "RequestMensagemCB", config.last_message_id or 1)
    inserted = 0
    highest = config.last_message_id or 1
    for node in root.findall(".//MensagemCB"):
        message_text, external_vehicle_id = _text(node, "mId"), _text(node, "veiID")
        try:
            message_id = int(message_text)
        except ValueError:
            continue
        highest = max(highest, message_id)
        if db.scalar(select(ProviderVehiclePosition.id).where(
                ProviderVehiclePosition.provider == PROVIDER,
                ProviderVehiclePosition.external_message_id == message_id)):
            continue
        lat, lon = _number(_text(node, "lat")), _number(_text(node, "lon"))
        if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        provider_vehicle = db.scalar(select(ProviderVehicle).where(
            ProviderVehicle.provider == PROVIDER,
            ProviderVehicle.external_vehicle_id == external_vehicle_id,
            ProviderVehicle.vehicle_id.is_not(None)))
        vehicle = db.get(Vehicle, provider_vehicle.vehicle_id) if provider_vehicle and provider_vehicle.vehicle_id else None
        # Escopo obrigatório: a operação monitora exclusivamente frota própria ativa.
        # Mensagens de terceiros não são persistidas; o cursor global ainda avança
        # para que elas não sejam solicitadas repetidamente ao fornecedor.
        if vehicle is None or vehicle.ownership_type != "proprio" or not vehicle.active:
            continue
        route = None
        if vehicle:
            route = db.scalar(select(Route).where(
                Route.vehicle_id == vehicle.id,
                Route.status.in_(("planejada", "em_carregamento", "liberada", "em_rota")),
                Route.excluded.is_(False),
            ).order_by(Route.route_date.desc(), Route.id.desc()))
        speed = _number(_text(node, "vel"))
        db.add(ProviderVehiclePosition(
            provider=PROVIDER, external_message_id=message_id, external_vehicle_id=external_vehicle_id,
            vehicle_id=vehicle.id if vehicle else None, route_id=route.id if route else None,
            branch_id=vehicle.branch_id if vehicle else None, tenant_id=vehicle.tenant_id if vehicle else None,
            latitude=lat, longitude=lon, speed_kmh=speed if speed is not None and speed >= 0 else None,
            city=_text(node, "mun") or None, state=_text(node, "uf")[:2] or None,
            address=_text(node, "rua") or _text(node, "rod") or None,
            odometer_km=_number(_text(node, "odm")), recorded_at=_date(_text(node, "dt"))))
        inserted += 1
    now = datetime.now(timezone.utc)
    config.last_message_id = highest
    config.last_sync_at = config.last_success_at = now
    config.last_error = None
    db.commit()
    return {"received": inserted, "cursor": highest}

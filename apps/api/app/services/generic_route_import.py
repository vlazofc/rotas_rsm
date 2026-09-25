"""Importação genérica de rotas via planilha (.xlsx ou .csv) — modelo padrão.

Diferente de app.services.torre_controle_import (formato específico da
Adeste, 3 abas), este módulo lê UM modelo simples e único que serve para
qualquer cliente/operação: uma linha = uma parada; linhas com o mesmo
ROTA + DATA ROTA formam a mesma rota.

Usado por app.modules.routes_import.router (botão "Importar rotas" no
painel, disponível para qualquer cliente).
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import BinaryIO

import openpyxl
from openpyxl.styles import Font
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Branch, Driver, Route, RouteStop, Vehicle
from app.db.session import SessionLocal
from app.services.import_changes import snapshot_import, collect_changes, authorize_changes
from app.services.route_carrier import apply_import_carrier, resolve_import_carrier

# Cabeçalho humano (o que aparece no modelo baixável) -> chave canônica interna.
TEMPLATE_COLUMNS: dict[str, str] = {
    "DATA ROTA": "route_date",
    "ROTA": "rota",
    "ORIGEM CD": "origin_address",
    "PEDIDO": "order_number",
    "CLIENTE": "client_name",
    "DESTINO": "customer_name",
    "ENDERECO": "customer_address",
    "CEP": "postal_code",
    "CIDADE": "city",
    "BAIRRO": "province",
    "PESO_KG": "weight_kg",
    "VOLUMES": "volumes",
    "PALETES": "pallets",
    "MOTORISTA": "motorista",
    "PLACA": "placa",
    "ID TRANSPORTADORA": "carrier_id",
    "TRANSPORTADORA": "carrier_name",
    "OBSERVACOES": "notes",
}
REQUIRED_COLUMNS = ("DATA ROTA", "ROTA", "DESTINO")

EXAMPLE_ROW = [
    "2026-07-01", "ROTA 1", "Rod. Adimax, 1000, Salto de Pirapora - SP", "12345", "Cliente Exemplo Ltda", "Cliente Exemplo Ltda - Filial Centro",
    "Av. Paulista, 1000", "01310-100", "São Paulo", "Bela Vista", "150.5", "3", "1",
    "João da Silva", "ABC1D23", "1", "Transportadora Alfa", "Entregar até 12h",
]


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def _norm_header(value) -> str:
    text = _strip_accents(str(value or "")).strip().upper()
    return re.sub(r"\s+", " ", text)


def parse_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_money(value) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    text = re.sub(r"[^\d,.\-]", "", str(value))
    if not text or text == "-":
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def parse_number(value) -> float | None:
    money = parse_money(value)
    return float(money) if money is not None else None


def parse_int(value) -> int | None:
    number = parse_number(value)
    return int(number) if number is not None else None


def parse_str(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_plate(plate: str | None) -> str | None:
    if not plate:
        return None
    normalized = re.sub(r"[^A-Z0-9]", "", plate.strip().upper())
    return normalized if len(normalized) >= 6 else None


def get_or_create_driver(db: Session, branch_id: int, name: str | None) -> Driver | None:
    if not name:
        return None
    driver = db.scalar(select(Driver).where(Driver.branch_id == branch_id, Driver.name.ilike(name.strip())))
    if driver is None:
        driver = Driver(branch_id=branch_id, name=name.strip())
        db.add(driver)
        db.flush()
    return driver


def get_or_create_vehicle(db: Session, branch_id: int, plate: str | None) -> Vehicle | None:
    plate = normalize_plate(plate)
    if not plate:
        return None
    vehicle = db.scalar(select(Vehicle).where(Vehicle.branch_id == branch_id, Vehicle.plate == plate))
    if vehicle is None:
        vehicle = Vehicle(branch_id=branch_id, plate=plate)
        db.add(vehicle)
        db.flush()
    return vehicle


def _read_xlsx(source) -> list[dict]:
    wb = openpyxl.load_workbook(source, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows_iter = ws.iter_rows(values_only=True)
    header = [_norm_header(c) for c in next(rows_iter, [])]
    keys = [TEMPLATE_COLUMNS.get(h) for h in header]
    out = []
    for raw_row in rows_iter:
        if all(c is None or str(c).strip() == "" for c in raw_row):
            continue
        row = {key: value for key, value in zip(keys, raw_row) if key}
        out.append(row)
    return out


def _read_csv(source: BinaryIO) -> list[dict]:
    text = source.read()
    if isinstance(text, bytes):
        text = text.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text), delimiter=";" if text.count(";") > text.count(",") else ",")
    rows_iter = iter(reader)
    header = [_norm_header(c) for c in next(rows_iter, [])]
    keys = [TEMPLATE_COLUMNS.get(h) for h in header]
    out = []
    for raw_row in rows_iter:
        if not any(c.strip() for c in raw_row):
            continue
        row = {key: value for key, value in zip(keys, raw_row) if key}
        out.append(row)
    return out


def build_template_xlsx() -> io.BytesIO:
    """Gera o modelo .xlsx para download — cabeçalho + 1 linha de exemplo."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Rotas"
    headers = list(TEMPLATE_COLUMNS.keys())
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    ws.append(EXAMPLE_ROW)
    for idx, _ in enumerate(headers, start=1):
        ws.column_dimensions[ws.cell(row=1, column=idx).column_letter].width = 16

    notes = wb.create_sheet("Leia-me")
    notes_text = [
        ("Como preencher", ""),
        ("DATA ROTA", "Data da rota (AAAA-MM-DD ou DD/MM/AAAA). Obrigatório."),
        ("ROTA", "Nome da rota (ex.: ROTA 1). Linhas com a mesma ROTA + DATA ROTA formam uma só rota. Obrigatório."),
        ("ORIGEM CD", "Endereço completo do centro de distribuição. Necessário para a roteirização automática."),
        ("PEDIDO", "Número do pedido/ordem de venda (opcional)."),
        ("CLIENTE", "Cliente que está sendo cobrado (opcional, se diferente do destino)."),
        ("DESTINO", "Nome de quem recebe a entrega. Obrigatório."),
        ("ENDERECO", "Endereço completo da entrega (opcional)."),
        ("CEP / CIDADE / BAIRRO", "Localização da entrega (opcional, recomendado)."),
        ("PESO_KG / VOLUMES / PALETES", "Quantidades da carga (opcional)."),
        ("MOTORISTA / PLACA", "Se já souber quem vai dirigir (opcional) — cria o motorista/veículo automaticamente se não existir."),
        ("OBSERVACOES", "Qualquer observação da entrega (opcional)."),
    ]
    for row in notes_text:
        notes.append(row)
    for cell in notes["A"]:
        cell.font = Font(bold=True)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def import_generic_routes(source, filename: str, branch_id: int, *, confirmed: bool = False, user_id: int | None = None) -> dict:
    """Importa o modelo padrão (.xlsx ou .csv) para a filial indicada.

    `source`: caminho, bytes ou arquivo binário. `filename`: usado só para
    decidir o parser pela extensão.
    """
    if filename.lower().endswith(".csv"):
        rows = _read_csv(source if hasattr(source, "read") else io.BytesIO(source))
    else:
        rows = _read_xlsx(source)

    stats = {"rows_read": len(rows), "routes_created": 0, "routes_updated": 0,
              "stops_created": 0, "stops_updated": 0, "routes_optimized": 0,
              "routing_errors": 0, "carrier_pending": 0, "route_ids": [], "errors": []}

    with SessionLocal() as db:
        changes = []
        branch = db.get(Branch, branch_id)
        if branch is None:
            raise RuntimeError("Filial não encontrada.")

        groups: dict[tuple[str, date], list[dict]] = {}
        for i, row in enumerate(rows, start=2):  # linha 2 = primeira linha de dados
            route_date = parse_date(row.get("route_date"))
            rota_label = parse_str(row.get("rota"))
            destino = parse_str(row.get("customer_name"))
            if route_date is None or rota_label is None or destino is None:
                stats["errors"].append(f"Linha {i}: faltam DATA ROTA, ROTA ou DESTINO — ignorada.")
                continue
            groups.setdefault((rota_label, route_date), []).append(row)

        for (rota_label, route_date), group_rows in groups.items():
            base = group_rows[0]
            route = db.scalar(
                select(Route).where(
                    Route.branch_id == branch.id, Route.codigo_ut == rota_label, Route.route_date == route_date,
                )
            )
            is_new_route = route is None
            before_route = snapshot_import(route)
            if is_new_route:
                route = Route(branch_id=branch.id, codigo_ut=rota_label, route_date=route_date, source="automatico")
                db.add(route)

            if is_new_route:
                route.status = "planejada"
            route.origin_address = parse_str(base.get("origin_address")) or route.origin_address
            if is_new_route:
                driver_name = parse_str(base.get("motorista"))
                plate = normalize_plate(parse_str(base.get("placa")))
                driver = db.scalar(select(Driver).where(Driver.branch_id == branch.id, Driver.name.ilike(driver_name))) if driver_name else None
                vehicle = db.scalar(select(Vehicle).where(Vehicle.branch_id == branch.id, Vehicle.plate == plate)) if plate else None
                if driver: route.driver_id = driver.id
                if vehicle: route.vehicle_id = vehicle.id

            collect_changes(changes, before_route, route, rota_label)
            carrier, carrier_issue = resolve_import_carrier(
                db, branch.id, carrier_id=parse_int(base.get("carrier_id")),
                name=parse_str(base.get("carrier_name")),
            )
            apply_import_carrier(route, carrier, carrier_issue)
            if carrier_issue:
                stats["carrier_pending"] += 1
                stats["errors"].append(f"Rota {rota_label}: {carrier_issue}")
            db.flush()
            stats["route_ids"].append(route.id)
            stats["routes_created" if is_new_route else "routes_updated"] += 1

            for seq, row in enumerate(group_rows, start=1):
                order_number = parse_str(row.get("order_number"))
                stop = None
                if order_number:
                    stop = db.scalar(
                        select(RouteStop).where(RouteStop.route_id == route.id, RouteStop.order_number == order_number)
                    )
                is_new_stop = stop is None
                before_stop = snapshot_import(stop)
                if is_new_stop:
                    stop = RouteStop(route_id=route.id, customer_name="—", sequence=seq)
                    db.add(stop)
                stop.route_id = route.id
                stop.sequence = seq
                stop.order_number = order_number
                stop.customer_name = parse_str(row.get("customer_name")) or stop.customer_name
                stop.client_name = parse_str(row.get("client_name"))
                stop.customer_address = parse_str(row.get("customer_address"))
                stop.postal_code = parse_str(row.get("postal_code"))
                stop.city = parse_str(row.get("city"))
                stop.province = parse_str(row.get("province"))
                stop.weight_kg = parse_number(row.get("weight_kg"))
                stop.volumes = parse_int(row.get("volumes"))
                stop.pallets = parse_number(row.get("pallets"))
                stop.raw_import_json = parse_str(row.get("notes"))
                collect_changes(changes, before_stop, stop, rota_label)
                db.flush()
                stats["stops_created" if is_new_stop else "stops_updated"] += 1

        authorize_changes(db, changes, confirmed=confirmed, user_id=user_id)
        db.commit()

    return stats

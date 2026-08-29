"""Importação da planilha "Torre de Controle" (Excel) — Adeste/JM_MRD (legado) e clientes futuros da Admmendes.

Lê as abas MONITORAMENTO, PROGRAMAÇÃO e Sugestão, funde os dados por
ORDEM DE VENDA, e cria/atualiza Route + RouteStop. FRETE vira Revenue
(receita da rota); diária de motorista/ajudante vira Expense.

Usado por:
- scripts/import_torre_controle.py (CLI, arquivo local — testes manuais)
- app.services.sharepoint (download automático do SharePoint do cliente)
- app.workers.celery_app (tarefa agendada + botão "Sincronizar agora")

Idempotente — pode ser re-executado; routes/stops são upsert por chave natural.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import BinaryIO

import openpyxl
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Branch, Driver, Expense, FinancialAccount, Revenue, Route, RouteStop, Tenant, Vehicle, VehicleType
from app.db.session import SessionLocal
from app.services.routing import calculate_round_trip_km, map_vehicle

VEHICLE_TYPE_CODE_BY_LABEL = {
    "TOCO": "toco", "TRUCK": "truck", "VUC": "vuc", "VAN": "van",
    "3/4": "vuc", "MEDIO": "vuc", "MÉDIO": "vuc",
}

# Cabeçalho normalizado (sem espaços extras, maiúsculo) -> chave canônica.
PROGRAMACAO_MAP = {
    "DATA ROTA": "route_date", "FATURAMENTO": "invoicing_date", "ORDEM DE VENDA": "order_number",
    "NOTA FISCAL": "invoice_number", "REMESSA": "remessa_code", "CLIENTE": "client_name",
    "DESTINO": "customer_name", "CEP | CIDADE | BAIRRO": "location", "TIPO DE ENTREGA": "delivery_type",
    "VALOR NF": "invoice_value", "SACO": "qty_saco", "BOMBONA": "qty_bombona", "BALDE": "qty_balde",
    "TAMBOR": "qty_tambor", "IBC": "qty_ibc", "PESO BRUTO": "weight_kg", "VOLUMES": "volumes",
    "PALETES": "pallets", "ROTA": "rota", "SOLICITADO": "vehicle_requested", "ENVIADO": "vehicle_sent",
    "KM": "km", "FRETE": "frete", "MOTORISTA": "motorista", "PLACA": "placa", "AJUDANTE": "ajudante",
    "VALOR DO AJUDANTE": "valor_ajudante", "RASTREADA": "rastreada",
}
SUGESTAO_MAP = dict(PROGRAMACAO_MAP, **{"VEICULO": "vehicle_sent"})
MONITORAMENTO_MAP = {
    "DATA ROTA": "route_date", "FATURAMENTO": "invoicing_date", "ORDEMDEVENDA": "order_number",
    "NOTA FISCAL": "invoice_number", "REMESSA": "remessa_code", "CLIENTE": "client_name",
    "DESTINO": "customer_name", "CEP | CIDADE | BAIRRO": "location", "TIPO DE ENTREGA": "delivery_type",
    "VALOR NF": "invoice_value", "SACO": "qty_saco", "BOMBONA": "qty_bombona", "BALDE": "qty_balde",
    "TAMBOR": "qty_tambor", "IBC": "qty_ibc", "PESO BRUTO": "weight_kg", "VOLUMES": "volumes",
    "PALETES": "pallets", "ROTA": "rota", "PLACA": "placa", "DRIVER": "motorista",
    "STATUS FINAL": "status_final", "PROTOCOLO": "delivery_protocol",
}

STATUS_FINAL_TO_STOP_STATUS = {"CONCLUÍDA": "entregue", "DEVOLUÇÃO": "devolvido"}


def _norm_header(h) -> str:
    return re.sub(r"\s+", " ", str(h or "").strip().upper())


def _read_sheet(ws, header_map: dict[str, str]) -> list[dict]:
    rows_iter = ws.iter_rows(values_only=True)
    header = None
    for raw_row in rows_iter:
        candidate = [_norm_header(c) for c in raw_row]
        if "ORDEM DE VENDA" in candidate or "ORDEMDEVENDA" in candidate:
            header = candidate
            break
    if header is None:
        return []
    keys = [header_map.get(h) for h in header]
    out = []
    for raw_row in rows_iter:
        if all(c is None for c in raw_row):
            continue
        row = {}
        for key, value in zip(keys, raw_row):
            if key:
                row[key] = value
        if row.get("order_number") is not None:
            out.append(row)
    return out


def parse_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d"):
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


def parse_bool_sim_nao(value) -> bool | None:
    if value is None or value == "":
        return None
    text = str(value).strip().upper()
    if text in ("SIM", "S", "YES", "TRUE"):
        return True
    if text in ("NÃO", "NAO", "N", "NO", "FALSE", "-"):
        return False
    return None


def parse_str(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def split_location(value) -> tuple[str | None, str | None, str | None]:
    """"CEP | CIDADE | BAIRRO" -> (cep, cidade, bairro)."""
    text = parse_str(value)
    if not text:
        return None, None, None
    parts = [p.strip() for p in text.split("|")]
    cep_match = re.search(r"\d{5}-?\d{3}", parts[0]) if parts else None
    cep = cep_match.group(0) if cep_match else None
    city = parts[1] if len(parts) > 1 else (None if cep else (parts[0] or None))
    bairro = " ".join(parts[2:]) if len(parts) > 2 else None
    return cep, (city or None), bairro


def merge_rows(programacao: list[dict], monitoramento: list[dict], sugestao: list[dict]) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for row in programacao:
        key = str(row["order_number"]).strip()
        merged[key] = dict(row)
    for row in monitoramento:
        key = str(row["order_number"]).strip()
        base = merged.setdefault(key, {})
        for field, value in row.items():
            if value is not None and (field not in base or base.get(field) is None):
                base[field] = value
    for row in sugestao:
        key = str(row["order_number"]).strip()
        if key not in merged:
            merged[key] = dict(row)
    return merged


def get_or_create_driver(db: Session, branch_id: int, name: str | None) -> Driver | None:
    if not name:
        return None
    driver = db.scalar(
        select(Driver).where(Driver.branch_id == branch_id, Driver.name.ilike(name.strip()))
    )
    if driver is None:
        driver = Driver(branch_id=branch_id, name=name.strip())
        db.add(driver)
        db.flush()
    return driver


def normalize_plate(plate: str | None) -> str | None:
    if not plate:
        return None
    normalized = re.sub(r"[^A-Z0-9]", "", plate.strip().upper())
    return normalized if len(normalized) >= 6 else None


_vehicle_type_cache: dict[str, int | None] = {}


def resolve_vehicle_type_id(db: Session, label: str | None) -> int | None:
    if not label:
        return None
    code = VEHICLE_TYPE_CODE_BY_LABEL.get(label.strip().upper())
    if not code:
        return None
    if code not in _vehicle_type_cache:
        vtype = db.scalar(select(VehicleType).where(VehicleType.code == code))
        _vehicle_type_cache[code] = vtype.id if vtype else None
    return _vehicle_type_cache[code]


def get_or_create_vehicle(db: Session, branch_id: int, plate: str | None, type_label: str | None = None) -> Vehicle | None:
    plate = normalize_plate(plate)
    if not plate:
        return None
    vehicle = db.scalar(select(Vehicle).where(Vehicle.branch_id == branch_id, Vehicle.plate == plate))
    if vehicle is None:
        vehicle = Vehicle(branch_id=branch_id, plate=plate)
        db.add(vehicle)
        db.flush()
    if vehicle.vehicle_type_id is None:
        vehicle.vehicle_type_id = resolve_vehicle_type_id(db, type_label)
    return vehicle


def import_workbook(source: Path | str | BinaryIO, branch_id: int | None = None, origin_address: str | None = None) -> dict:
    """Importa a planilha (caminho local ou arquivo em memória) para a filial indicada.

    `branch_id`: se omitido, usa a primeira filial BR (compatibilidade com o
    fluxo atual de cliente único). `origin_address`: endereço da filial usado
    para calcular KM ida/volta quando a planilha não traz o KM informado.
    """
    wb = openpyxl.load_workbook(source, data_only=True)
    programacao = _read_sheet(wb["PROGRAMAÇÃO"], PROGRAMACAO_MAP)
    monitoramento = _read_sheet(wb["MONITORAMENTO"], MONITORAMENTO_MAP)
    sugestao = _read_sheet(wb["Sugestão"], SUGESTAO_MAP)

    merged = merge_rows(programacao, monitoramento, sugestao)

    today = date.today()
    stats = {
        "rows_programacao": len(programacao), "rows_monitoramento": len(monitoramento), "rows_sugestao": len(sugestao),
        "rows_merged": len(merged),
        "routes_created": 0, "routes_updated": 0, "stops_created": 0, "stops_updated": 0,
        "km_informado": 0, "km_calculado": 0, "expenses_created": 0, "revenues_created": 0,
    }

    with SessionLocal() as db:
        branch = db.get(Branch, branch_id) if branch_id else db.scalar(select(Branch).where(Branch.country == "BR"))
        if branch is None:
            raise RuntimeError("Filial não encontrada — rode a API uma vez para o bootstrap criá-la, ou informe branch_id.")
        tenant = db.get(Tenant, branch.tenant_id) if branch.tenant_id else None
        km_calc_enabled = tenant.feature_km_calculation if tenant and hasattr(tenant, "feature_km_calculation") else True

        groups: dict[tuple[str, date], list[dict]] = {}
        for row in merged.values():
            route_date = parse_date(row.get("route_date"))
            rota_label = parse_str(row.get("rota"))
            if route_date is None or rota_label is None:
                continue
            groups.setdefault((rota_label, route_date), []).append(row)

        for (rota_label, route_date), rows in groups.items():
            base = rows[0]
            route = db.scalar(
                select(Route).where(
                    Route.branch_id == branch.id,
                    Route.codigo_ut == rota_label,
                    Route.route_date == route_date,
                )
            )
            is_new_route = route is None
            if route is not None and route.excluded:
                stats["skipped_excluded"] = stats.get("skipped_excluded", 0) + 1
                continue
            if is_new_route:
                route = Route(branch_id=branch.id, codigo_ut=rota_label, route_date=route_date, source="automatico")
                db.add(route)

            route.status = "finalizada" if route_date <= today else "planejada"
            if not route.origin_address and origin_address:
                route.origin_address = origin_address
            if not route.origin_name and origin_address:
                route.origin_name = "Filial Santo André"

            route.vehicle_requested = parse_str(base.get("vehicle_requested")) or route.vehicle_requested
            route.vehicle_sent = parse_str(base.get("vehicle_sent")) or route.vehicle_sent
            ajudante = parse_bool_sim_nao(base.get("ajudante"))
            if ajudante is not None:
                route.helper_assigned = ajudante
            rastreada = parse_bool_sim_nao(base.get("rastreada"))
            if rastreada is not None:
                route.tracked = rastreada
            route.raw_import_json = json.dumps(rows, default=str, ensure_ascii=False)

            motorista_nome = parse_str(base.get("motorista"))
            placa = parse_str(base.get("placa"))
            driver = get_or_create_driver(db, branch.id, motorista_nome)
            vehicle_type_label = parse_str(base.get("vehicle_sent")) or parse_str(base.get("vehicle_requested"))
            vehicle = get_or_create_vehicle(db, branch.id, placa, vehicle_type_label)
            if driver:
                route.driver_id = driver.id
            if vehicle:
                route.vehicle_id = vehicle.id

            km = parse_number(base.get("km"))
            if km is not None:
                route.km_total_informed = km
                route.km_source = "informado"
                stats["km_informado"] += 1
            elif km_calc_enabled and route.km_total_informed is None and route.status == "planejada" and origin_address:
                cep, city, bairro = split_location(base.get("location"))
                destination = " ".join(filter(None, [cep, city, bairro]))
                if destination:
                    vehicle_code = map_vehicle(route.vehicle_sent or route.vehicle_requested)
                    outbound, inbound = calculate_round_trip_km(origin_address, destination, vehicle_code)
                    if outbound is not None and inbound is not None:
                        route.km_outbound_informed = outbound
                        route.km_return_informed = inbound
                        route.km_total_informed = round(outbound + inbound, 1)
                        route.km_source = "calculado"
                        stats["km_calculado"] += 1

            db.flush()
            stats["routes_created" if is_new_route else "routes_updated"] += 1

            for row in rows:
                order_number = str(row["order_number"]).strip()
                stop = db.scalar(select(RouteStop).where(RouteStop.order_number == order_number))
                is_new_stop = stop is None
                if is_new_stop:
                    stop = RouteStop(route_id=route.id, order_number=order_number, customer_name="—")
                    db.add(stop)
                stop.route_id = route.id
                stop.customer_name = parse_str(row.get("customer_name")) or stop.customer_name
                stop.client_name = parse_str(row.get("client_name"))
                cep, city, bairro = split_location(row.get("location"))
                stop.postal_code = cep
                stop.city = city
                stop.province = bairro
                stop.invoicing_date = parse_date(row.get("invoicing_date"))
                stop.invoice_number = parse_str(row.get("invoice_number"))
                stop.remessa_code = parse_str(row.get("remessa_code"))
                stop.delivery_type = parse_str(row.get("delivery_type"))
                stop.invoice_value = parse_money(row.get("invoice_value"))
                stop.qty_saco = parse_int(row.get("qty_saco"))
                stop.qty_bombona = parse_int(row.get("qty_bombona"))
                stop.qty_balde = parse_int(row.get("qty_balde"))
                stop.qty_tambor = parse_int(row.get("qty_tambor"))
                stop.qty_ibc = parse_int(row.get("qty_ibc"))
                stop.weight_kg = parse_number(row.get("weight_kg"))
                stop.volumes = parse_int(row.get("volumes"))
                stop.pallets = parse_number(row.get("pallets"))
                stop.delivery_protocol = parse_str(row.get("delivery_protocol"))
                status_final = parse_str(row.get("status_final"))
                if status_final in STATUS_FINAL_TO_STOP_STATUS:
                    stop.status = STATUS_FINAL_TO_STOP_STATUS[status_final]
                stop.raw_import_json = json.dumps(row, default=str, ensure_ascii=False)
                db.flush()
                stats["stops_created" if is_new_stop else "stops_updated"] += 1

            # FRETE é receita (valor cobrado do cliente pela rota) — não despesa.
            frete = parse_money(base.get("frete"))
            if frete is not None:
                existing_revenue = db.scalar(
                    select(Revenue).where(Revenue.route_id == route.id, Revenue.source == "import")
                )
                if existing_revenue is not None:
                    existing_revenue.amount = frete
                    revenue = existing_revenue
                else:
                    revenue = Revenue(
                        branch_id=branch.id, route_id=route.id, revenue_date=route_date,
                        amount=frete, notes="Frete (importado)", source="import",
                    )
                    db.add(revenue)
                    stats["revenues_created"] += 1
                db.flush()
                account = db.scalar(select(FinancialAccount).where(FinancialAccount.revenue_id == revenue.id))
                if account is None:
                    account = FinancialAccount(
                        branch_id=branch.id, kind="receivable", description=f"Receita da rota {route.codigo_ut}",
                        counterparty="Cliente da rota", category="frete", document=f"ROTA-{route.codigo_ut}",
                        issue_date=route_date, due_date=max(route_date, date.today()), amount=frete,
                        status="pendente", notes=revenue.notes, revenue_id=revenue.id,
                    )
                    db.add(account)
                elif account.status == "pendente":
                    account.amount, account.issue_date = frete, route_date
                    account.due_date = max(route_date, date.today())

            if driver:
                valor_motorista = None  # planilha não tem "Valor Motorista" nas abas atuais
                valor_ajudante = parse_money(base.get("valor_ajudante"))
                for reason, amount in (
                    ("diaria_motorista", valor_motorista),
                    ("diaria_ajudante", valor_ajudante),
                ):
                    if amount is None:
                        continue
                    existing = db.scalar(
                        select(Expense).where(Expense.route_id == route.id, Expense.reason == reason, Expense.source == "import")
                    )
                    if existing is not None:
                        existing.amount = amount
                        existing.driver_id = driver.id
                        existing.vehicle_id = vehicle.id if vehicle else None
                        continue
                    db.add(Expense(
                        branch_id=branch.id, driver_id=driver.id, vehicle_id=vehicle.id if vehicle else None,
                        route_id=route.id, expense_date=route_date, reason=reason, amount=amount,
                        source="import",
                    ))
                    stats["expenses_created"] += 1

        db.commit()

    return stats

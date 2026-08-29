"""Memoria de calculo financeira versionada e reproduzivel."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import hashlib
import io
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.permissions import FINANCE_VIEW, Role, require_permission
from app.db.models import CalculationMemory, Expense, Revenue, User
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services.audit import log

router = APIRouter(prefix="/calculation-memory", tags=["calculation-memory"])
_FINANCE = require_permission(FINANCE_VIEW, Role.GESTOR_BRASIL, Role.GESTOR_FINANCEIRO, Role.AUDITOR)


class SnapshotIn(BaseModel):
    period_start: date
    period_end: date


def _scope(stmt, model, user: User):
    if user.tenant_id is not None:
        return stmt.where(model.tenant_id == user.tenant_id)
    if user.branch_id is not None:
        return stmt.where(model.branch_id == user.branch_id)
    return stmt


def _money(value: object) -> str:
    return str(Decimal(str(value or 0)).quantize(Decimal("0.01")))


def _build(db: Session, user: User, start: date, end: date) -> tuple[dict, dict, str]:
    if end < start:
        raise HTTPException(422, "A data final deve ser igual ou posterior a data inicial.")
    revenues = _scope(
        select(Revenue.id, Revenue.revenue_date, Revenue.amount, Revenue.source)
        .where(Revenue.revenue_date.between(start, end)).order_by(Revenue.id), Revenue, user,
    )
    expenses = _scope(
        select(Expense.id, Expense.expense_date, Expense.amount, Expense.reason, Expense.source)
        .where(Expense.expense_date.between(start, end), Expense.approval_status == "approved")
        .order_by(Expense.id), Expense, user,
    )
    revenue_rows = [dict(row._mapping) for row in db.execute(revenues)]
    expense_rows = [dict(row._mapping) for row in db.execute(expenses)]
    revenue_total = sum((Decimal(str(row["amount"] or 0)) for row in revenue_rows), Decimal("0"))
    expense_total = sum((Decimal(str(row["amount"] or 0)) for row in expense_rows), Decimal("0"))
    result = revenue_total - expense_total
    by_category: dict[str, Decimal] = {}
    for row in expense_rows:
        key = row["reason"] or "outros"
        by_category[key] = by_category.get(key, Decimal("0")) + Decimal(str(row["amount"] or 0))
    inputs = {
        "receitas": [{"id": r["id"], "data": r["revenue_date"].isoformat(), "valor": _money(r["amount"]), "origem": r["source"]} for r in revenue_rows],
        "despesas_aprovadas": [{"id": r["id"], "data": r["expense_date"].isoformat(), "valor": _money(r["amount"]), "categoria": r["reason"], "origem": r["source"]} for r in expense_rows],
    }
    results = {
        "receita_total": _money(revenue_total), "despesa_total": _money(expense_total),
        "resultado": _money(result),
        "margem_percentual": str((result / revenue_total * 100).quantize(Decimal("0.01"))) if revenue_total else "0.00",
        "despesas_por_categoria": {key: _money(value) for key, value in sorted(by_category.items())},
        "formula": "resultado = receitas - despesas aprovadas; margem = resultado / receitas x 100",
    }
    canonical = json.dumps({"period_start": start.isoformat(), "period_end": end.isoformat(), "inputs": inputs, "results": results}, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return inputs, results, hashlib.sha256(canonical.encode()).hexdigest()


def _out(row: CalculationMemory) -> dict:
    return {
        "id": row.id, "period_start": row.period_start, "period_end": row.period_end,
        "formula_version": row.formula_version, "inputs": json.loads(row.inputs_json),
        "results": json.loads(row.results_json), "created_at": row.created_at,
        "created_by": row.created_by,
    }


@router.get("", dependencies=[Depends(_FINANCE)])
def list_memories(limit: int = 50, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(CalculationMemory).order_by(CalculationMemory.created_at.desc(), CalculationMemory.id.desc()).limit(min(max(limit, 1), 200))
    if user.tenant_id is not None:
        stmt = stmt.where(CalculationMemory.tenant_id == user.tenant_id)
    elif user.branch_id is not None:
        stmt = stmt.where(CalculationMemory.branch_id == user.branch_id)
    return [_out(row) for row in db.scalars(stmt)]


@router.post("/snapshot", dependencies=[Depends(_FINANCE)])
def create_snapshot(data: SnapshotIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    inputs, results, content_hash = _build(db, user, data.period_start, data.period_end)
    existing = db.scalar(select(CalculationMemory).where(CalculationMemory.tenant_id == user.tenant_id, CalculationMemory.content_hash == content_hash))
    if existing:
        return {**_out(existing), "created": False}
    row = CalculationMemory(tenant_id=user.tenant_id, branch_id=user.branch_id, created_by=user.id,
        period_start=data.period_start, period_end=data.period_end, content_hash=content_hash,
        inputs_json=json.dumps(inputs, ensure_ascii=False), results_json=json.dumps(results, ensure_ascii=False))
    db.add(row); db.flush()
    log(db, user_id=user.id, action="create", entity="calculation_memory", entity_id=row.id,
        detail=f"periodo={data.period_start.isoformat()}..{data.period_end.isoformat()}; resultado={results['resultado']}")
    db.commit(); db.refresh(row)
    return {**_out(row), "created": True}


@router.get("/{memory_id}/xlsx", dependencies=[Depends(_FINANCE)])
def export_memory(memory_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(CalculationMemory).where(CalculationMemory.id == memory_id)
    if user.tenant_id is not None: stmt = stmt.where(CalculationMemory.tenant_id == user.tenant_id)
    elif user.branch_id is not None: stmt = stmt.where(CalculationMemory.branch_id == user.branch_id)
    row = db.scalar(stmt)
    if not row: raise HTTPException(404, "Memoria de calculo nao encontrada.")
    data = _out(row); wb = Workbook(); summary = wb.active; summary.title = "Resumo"
    summary.append(["Memoria de calculo", row.id]); summary.append(["Periodo", f"{row.period_start} a {row.period_end}"])
    summary.append(["Gerada em", row.created_at.isoformat()]); summary.append([]); summary.append(["Indicador", "Valor"])
    for key, value in data["results"].items():
        if not isinstance(value, dict): summary.append([key, value])
    for title, key in (("Receitas", "receitas"), ("Despesas", "despesas_aprovadas")):
        ws = wb.create_sheet(title); rows = data["inputs"][key]
        headers = list(rows[0].keys()) if rows else ["sem_lancamentos"]
        ws.append(headers)
        for item in rows: ws.append([item.get(header) for header in headers])
    stream = io.BytesIO(); wb.save(stream); stream.seek(0)
    filename = f"memoria-calculo-{row.period_start}-{row.period_end}-v{row.id}.xlsx"
    return StreamingResponse(stream, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

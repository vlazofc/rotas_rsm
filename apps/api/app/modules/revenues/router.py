"""Receitas por rota (valor faturado ao cliente) — módulo financeiro."""
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import extract, select
from sqlalchemy.orm import Session

from app.core.permissions import Role, require_feature, require_roles, require_same_branch
from app.db.models import Revenue, Route, User
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services.audit import log, log_update, snapshot

router = APIRouter(prefix="/revenues", tags=["revenues"], dependencies=[Depends(require_feature("feature_financeiro"))])

_FINANCEIRO = require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL, Role.GESTOR_FINANCEIRO)


class RevenueOut(BaseModel):
    id: int
    branch_id: int
    route_id: int | None
    route_codigo_ut: str | None = None
    user_id: int | None
    revenue_date: date
    amount: Decimal
    notes: str | None
    source: str
    created_at: datetime

    class Config:
        from_attributes = True


class RevenueIn(BaseModel):
    route_id: int | None = None
    branch_id: int | None = None  # obrigatório se route_id não informado
    revenue_date: date
    amount: Decimal
    notes: str | None = None


class RevenueUpdate(BaseModel):
    revenue_date: date | None = None
    amount: Decimal | None = None
    notes: str | None = None
    route_id: int | None = None


def _serialize(revenue: Revenue) -> RevenueOut:
    return RevenueOut(
        id=revenue.id, branch_id=revenue.branch_id, route_id=revenue.route_id,
        route_codigo_ut=revenue.route.codigo_ut if revenue.route_id and revenue.route else None,
        user_id=revenue.user_id, revenue_date=revenue.revenue_date, amount=revenue.amount,
        notes=revenue.notes, source=revenue.source, created_at=revenue.created_at,
    )


def _revenue_query(user: User):
    stmt = select(Revenue)
    if user.branch_id:
        stmt = stmt.where(Revenue.branch_id == user.branch_id)
    return stmt


@router.get("", response_model=list[RevenueOut], dependencies=[Depends(_FINANCEIRO)])
def list_revenues(month: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = _revenue_query(user)
    if month:
        try:
            year, month_num = [int(part) for part in month.split("-", 1)]
        except ValueError:
            raise HTTPException(status_code=400, detail="Mês inválido. Use AAAA-MM.")
        stmt = stmt.where(
            extract("year", Revenue.revenue_date) == year,
            extract("month", Revenue.revenue_date) == month_num,
        )
    revenues = db.scalars(stmt.order_by(Revenue.revenue_date.desc(), Revenue.id.desc())).all()
    return [_serialize(r) for r in revenues]


@router.post("", response_model=RevenueOut, dependencies=[Depends(_FINANCEIRO)])
def create_revenue(data: RevenueIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    branch_id = data.branch_id
    route = None
    if data.route_id:
        route = db.get(Route, data.route_id)
        if route is None:
            raise HTTPException(status_code=404, detail="Rota não encontrada.")
        branch_id = route.branch_id
    if branch_id is None:
        raise HTTPException(status_code=422, detail="Informe a rota ou a filial da receita.")
    require_same_branch(user, branch_id)
    revenue = Revenue(
        branch_id=branch_id, route_id=data.route_id, user_id=user.id,
        revenue_date=data.revenue_date, amount=data.amount, notes=data.notes,
    )
    db.add(revenue)
    db.flush()
    log(db, user_id=user.id, action="create", entity="revenue", entity_id=revenue.id)
    db.commit()
    db.refresh(revenue)
    return _serialize(revenue)


@router.put("/{revenue_id}", response_model=RevenueOut, dependencies=[Depends(_FINANCEIRO)])
def update_revenue(revenue_id: int, data: RevenueUpdate,
                    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    revenue = db.get(Revenue, revenue_id)
    if revenue is None:
        raise HTTPException(status_code=404, detail="Receita não encontrada.")
    require_same_branch(user, revenue.branch_id)
    updates = data.model_dump(exclude_unset=True)
    before = snapshot(revenue, list(updates))
    for field, value in updates.items():
        setattr(revenue, field, value)
    log_update(db, user_id=user.id, entity="revenue", entity_id=revenue.id, before=before, obj=revenue, updates=updates)
    db.commit()
    db.refresh(revenue)
    return _serialize(revenue)


@router.delete("/{revenue_id}", dependencies=[Depends(_FINANCEIRO)])
def delete_revenue(revenue_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    revenue = db.get(Revenue, revenue_id)
    if revenue is None:
        raise HTTPException(status_code=404, detail="Receita não encontrada.")
    require_same_branch(user, revenue.branch_id)
    db.delete(revenue)
    log(db, user_id=user.id, action="delete", entity="revenue", entity_id=revenue_id)
    db.commit()
    return {"deleted": revenue_id}

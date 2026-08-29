"""Receitas por rota (valor faturado ao cliente) — módulo financeiro."""
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import extract, select
from sqlalchemy.orm import Session

from app.core.permissions import FINANCE_REVENUE_MANAGE, FINANCE_VIEW, Role, require_feature, require_permission, require_same_branch
from app.db.models import FinancialAccount, Revenue, RevenueRouteLink, Route, User
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services.audit import log, log_update, snapshot
from app.services.accounting import post_revenue, remove_posting, repost_revenue

router = APIRouter(prefix="/revenues", tags=["revenues"], dependencies=[Depends(require_feature("feature_financeiro"))])

_FINANCEIRO = require_permission(FINANCE_VIEW, Role.GESTOR_BRASIL, Role.GESTOR_FINANCEIRO)
_REVENUE_MANAGER = require_permission(FINANCE_REVENUE_MANAGE, Role.GESTOR_FINANCEIRO)


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
    created_by_name: str | None = None
    customers: list[str] = Field(default_factory=list)
    financial_account_id: int | None = None
    financial_status: str | None = None
    route_ids: list[int] = Field(default_factory=list)
    route_codes: list[str] = Field(default_factory=list)
    billed_customer_name: str | None = None

    class Config:
        from_attributes = True


class RevenueIn(BaseModel):
    route_ids: list[int] = Field(min_length=1)
    billed_customer_name: str = Field(min_length=2, max_length=180)
    revenue_date: date
    amount: Decimal = Field(gt=0)
    notes: str | None = None


class RevenueUpdate(BaseModel):
    revenue_date: date | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    notes: str | None = None
    route_id: int | None = None


def _serialize(revenue: Revenue) -> RevenueOut:
    account = revenue.financial_account
    db = Session.object_session(revenue)
    route_ids = list(db.scalars(select(RevenueRouteLink.route_id).where(RevenueRouteLink.revenue_id == revenue.id)).all()) if db else []
    if not route_ids and revenue.route_id: route_ids = [revenue.route_id]
    routes = list(db.scalars(select(Route).where(Route.id.in_(route_ids))).all()) if db and route_ids else ([revenue.route] if revenue.route else [])
    route_codes = [route.codigo_ut for route in routes]
    customers = [revenue.billed_customer_name] if revenue.billed_customer_name else sorted({(stop.client_name or stop.customer_name).strip() for route in routes for stop in route.stops if (stop.client_name or stop.customer_name or "").strip()})
    return RevenueOut(
        id=revenue.id, branch_id=revenue.branch_id, route_id=revenue.route_id,
        route_codigo_ut=", ".join(route_codes) or None,
        user_id=revenue.user_id, revenue_date=revenue.revenue_date, amount=revenue.amount,
        notes=revenue.notes, source=revenue.source, created_at=revenue.created_at,
        created_by_name=revenue.creator.name if revenue.creator else None,
        customers=customers, financial_account_id=account.id if account else None,
        financial_status=account.status if account else None,
        route_ids=route_ids, route_codes=route_codes, billed_customer_name=revenue.billed_customer_name,
    )


def _linked_account(db: Session, revenue_id: int) -> FinancialAccount | None:
    return db.scalar(select(FinancialAccount).where(FinancialAccount.revenue_id == revenue_id))


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


@router.post("", response_model=RevenueOut, dependencies=[Depends(_REVENUE_MANAGER)])
def create_revenue(data: RevenueIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    route_ids = list(dict.fromkeys(data.route_ids))
    routes = list(db.scalars(select(Route).where(Route.id.in_(route_ids))).all())
    if len(routes) != len(route_ids): raise HTTPException(status_code=404, detail="Uma ou mais rotas não foram encontradas.")
    branch_ids = {route.branch_id for route in routes}
    if len(branch_ids) != 1: raise HTTPException(status_code=422, detail="Todas as rotas devem pertencer à mesma filial.")
    branch_id = routes[0].branch_id
    require_same_branch(user, branch_id)
    customer = data.billed_customer_name.strip()
    for route in routes:
        names = {(stop.client_name or stop.customer_name or "").strip().casefold() for stop in route.stops}
        if customer.casefold() not in names: raise HTTPException(status_code=422, detail=f"A rota {route.codigo_ut} não pertence ao cliente {customer}.")
    duplicate = db.scalar(select(RevenueRouteLink).join(Revenue).where(RevenueRouteLink.route_id.in_(route_ids), Revenue.source == "manual"))
    if duplicate: raise HTTPException(status_code=409, detail=f"Uma das rotas selecionadas já está faturada na receita #{duplicate.revenue_id}.")
    revenue = Revenue(
        branch_id=branch_id, route_id=route_ids[0], user_id=user.id, billed_customer_name=customer,
        revenue_date=data.revenue_date, amount=data.amount, notes=data.notes,
    )
    db.add(revenue)
    db.flush()
    for route_id in route_ids: db.add(RevenueRouteLink(revenue_id=revenue.id, route_id=route_id))
    route_codes = ", ".join(route.codigo_ut for route in routes)
    account = FinancialAccount(
        branch_id=branch_id, kind="receivable", description=f"Receita das rotas {route_codes}"[:180],
        counterparty=customer[:180],
        category="frete", document=f"ROTAS-{route_codes}"[:80], issue_date=data.revenue_date,
        due_date=max(data.revenue_date, date.today()), amount=data.amount, status="pendente",
        notes=data.notes, created_by=user.id, revenue_id=revenue.id,
    )
    db.add(account); db.flush()
    post_revenue(db, revenue, user.id)
    log(db, user_id=user.id, action="create", entity="revenue", entity_id=revenue.id, detail=f"cliente={customer}; rotas={route_codes}; conta_receber={account.id}; valor={data.amount}")
    db.commit()
    db.refresh(revenue)
    return _serialize(revenue)


@router.put("/{revenue_id}", response_model=RevenueOut, dependencies=[Depends(_REVENUE_MANAGER)])
def update_revenue(revenue_id: int, data: RevenueUpdate,
                    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    revenue = db.get(Revenue, revenue_id)
    if revenue is None:
        raise HTTPException(status_code=404, detail="Receita não encontrada.")
    require_same_branch(user, revenue.branch_id)
    account = _linked_account(db, revenue.id)
    if account and account.status != "pendente":
        raise HTTPException(status_code=409, detail="Receita com título recebido ou cancelado não pode ser alterada.")
    updates = data.model_dump(exclude_unset=True)
    if "route_id" in updates and updates["route_id"] != revenue.route_id:
        raise HTTPException(status_code=409, detail="A rota de uma receita lançada não pode ser trocada; exclua e faça um novo lançamento.")
    before = snapshot(revenue, list(updates))
    for field, value in updates.items():
        setattr(revenue, field, value)
    if account:
        account.issue_date = revenue.revenue_date
        account.due_date = max(revenue.revenue_date, date.today())
        account.amount = revenue.amount
        account.notes = revenue.notes
    repost_revenue(db, revenue, user.id)
    log_update(db, user_id=user.id, entity="revenue", entity_id=revenue.id, before=before, obj=revenue, updates=updates)
    db.commit()
    db.refresh(revenue)
    return _serialize(revenue)


@router.delete("/{revenue_id}", dependencies=[Depends(_REVENUE_MANAGER)])
def delete_revenue(revenue_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    revenue = db.get(Revenue, revenue_id)
    if revenue is None:
        raise HTTPException(status_code=404, detail="Receita não encontrada.")
    require_same_branch(user, revenue.branch_id)
    account = _linked_account(db, revenue.id)
    if account and account.status != "pendente":
        raise HTTPException(status_code=409, detail="Receita com título recebido ou cancelado não pode ser excluída.")
    if account:
        db.delete(account)
        db.flush()
    remove_posting(db, "revenue", revenue.id)
    db.delete(revenue)
    log(db, user_id=user.id, action="delete", entity="revenue", entity_id=revenue_id)
    db.commit()
    return {"deleted": revenue_id}

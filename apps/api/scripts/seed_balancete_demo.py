"""Cria lançamentos contábeis demonstrativos idempotentes para agosto/2026.

Executar no container da API: python scripts/seed_balancete_demo.py
Remover somente os dados deste script: python scripts/seed_balancete_demo.py --remove
"""
import sys
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, select

from app.db.models import (
    AccountingEntry, AccountingLine, Expense, FinancialAccount, Revenue,
    RevenueRouteLink, Route, TaxRule, User,
)
from app.db.session import SessionLocal
from app.services.accounting import post_expense, post_revenue, remove_posting

MARKER = "[DEMO-BALANCETE-2026-08]"


def remove_demo(db):
    revenues = list(db.scalars(select(Revenue).where(Revenue.notes.contains(MARKER))).all())
    expenses = list(db.scalars(select(Expense).where(Expense.notes.contains(MARKER))).all())
    for row in revenues:
        remove_posting(db, "revenue", row.id)
        db.execute(delete(RevenueRouteLink).where(RevenueRouteLink.revenue_id == row.id))
        account = db.scalar(select(FinancialAccount).where(FinancialAccount.revenue_id == row.id))
        if account: db.delete(account)
        db.delete(row)
    for row in expenses:
        remove_posting(db, "expense", row.id)
        account = db.scalar(select(FinancialAccount).where(FinancialAccount.expense_id == row.id))
        if account: db.delete(account)
        db.delete(row)
    for rule in db.scalars(select(TaxRule).where(TaxRule.tax_code == "ISS-DEMO")).all(): db.delete(rule)
    db.commit()
    print(f"Removidos: {len(revenues)} receitas e {len(expenses)} despesas demonstrativas.")


def main():
    db = SessionLocal()
    try:
        if "--remove" in sys.argv:
            remove_demo(db); return
        if db.scalar(select(Revenue.id).where(Revenue.notes.contains(MARKER))):
            print("Dados demonstrativos já existem; nenhuma duplicação foi criada."); return
        branch_id = 1
        actor = db.scalar(select(User).where(User.tenant_id == 1, User.role == "admin_global"))
        if actor is None: raise RuntimeError("Administrador do tenant 1 não encontrado.")
        routes = {row.id: row for row in db.scalars(select(Route).where(Route.id.in_([33,34,35,36,37,38,39,40]), Route.branch_id == branch_id)).all()}
        if len(routes) != 8: raise RuntimeError("Rotas RSM-DEMO esperadas não foram encontradas.")
        rule = TaxRule(tenant_id=1, name="ISS demonstrativo", tax_code="ISS-DEMO", applies_to="revenue", rate_percent=Decimal("2.00"), effective_from=date(2026,8,1), debit_account_code="6.1.01", credit_account_code="2.2.01", legal_basis="Regra exclusivamente demonstrativa", active=True)
        db.add(rule); db.flush()
        revenue_specs = [
            (date(2026,8,20), Decimal("18500.00"), "Atacado Santista", [33,34,35]),
            (date(2026,8,23), Decimal("21750.00"), "Distribuidora Jundiaí", [36,37]),
            (date(2026,8,26), Decimal("16400.00"), "Loja São Bernardo", [38,39,40]),
        ]
        for when, amount, customer, route_ids in revenue_specs:
            codes = ", ".join(routes[item].codigo_ut for item in route_ids)
            row = Revenue(tenant_id=1, branch_id=branch_id, route_id=route_ids[0], user_id=actor.id, revenue_date=when, amount=amount, notes=f"{MARKER} Faturamento consolidado", source="manual", billed_customer_name=customer)
            db.add(row); db.flush()
            db.add_all([RevenueRouteLink(revenue_id=row.id, route_id=item) for item in route_ids])
            db.add(FinancialAccount(tenant_id=1, branch_id=branch_id, kind="receivable", description=f"Receita consolidada {codes}"[:180], counterparty=customer, category="frete", document=f"ROTAS-{codes}"[:80], issue_date=when, due_date=when, amount=amount, status="pendente", notes=MARKER, created_by=actor.id, revenue_id=row.id))
            post_revenue(db, row, actor.id)
        expense_specs = [
            (date(2026,8,19), "combustivel", Decimal("3850.00"), 33),
            (date(2026,8,21), "manutencao", Decimal("2750.00"), 35),
            (date(2026,8,22), "diaria_motorista", Decimal("1680.00"), 36),
            (date(2026,8,24), "combustivel", Decimal("4120.00"), 38),
            (date(2026,8,25), "outros", Decimal("940.00"), 39),
        ]
        for when, reason, amount, route_id in expense_specs:
            row = Expense(tenant_id=1, branch_id=branch_id, user_id=actor.id, route_id=route_id, expense_date=when, reason=reason, amount=amount, notes=f"{MARKER} Despesa operacional", source="administrative", approval_status="approved", due_date=when, recurrence="none", recurrence_count=1)
            db.add(row); db.flush()
            db.add(FinancialAccount(tenant_id=1, branch_id=branch_id, kind="payable", description=f"Despesa demonstrativa · {reason}", counterparty="Fornecedor demonstrativo", category=reason, document=f"DEMO-{row.id}", issue_date=when, due_date=when, amount=amount, status="pendente", notes=MARKER, created_by=actor.id, expense_id=row.id))
            post_expense(db, row, actor.id)
        db.commit()
        print("Criados: 3 receitas consolidadas, 5 despesas, 8 partidas e 1 regra tributária demonstrativa.")
    except Exception:
        db.rollback(); raise
    finally:
        db.close()


if __name__ == "__main__": main()

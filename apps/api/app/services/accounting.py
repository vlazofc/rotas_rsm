"""Partidas dobradas e snapshots tributários dos lançamentos financeiros."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

from app.db.models import AccountingEntry, AccountingLine, AccountingPeriod, ChartAccount, Expense, FinancialAccount, Revenue, TaxRule

DEFAULT_CHART = [
    ("1", "Ativo", "asset", "debit", False), ("1.1", "Ativo circulante", "asset", "debit", False),
    ("1.1.01", "Caixa e bancos", "asset", "debit", True), ("1.1.02", "Contas a receber", "asset", "debit", True),
    ("2", "Passivo", "liability", "credit", False), ("2.1", "Passivo circulante", "liability", "credit", False),
    ("2.1.01", "Contas a pagar", "liability", "credit", True), ("2.2.01", "Tributos a recolher", "liability", "credit", True),
    ("3", "Patrimônio líquido", "equity", "credit", False), ("3.1.01", "Resultados acumulados", "equity", "credit", True),
    ("4", "Receitas", "revenue", "credit", False), ("4.1.01", "Receita de fretes", "revenue", "credit", True),
    ("5", "Despesas", "expense", "debit", False), ("5.1.01", "Combustíveis", "expense", "debit", True),
    ("5.1.02", "Manutenção", "expense", "debit", True), ("5.1.03", "Diárias e pessoal", "expense", "debit", True),
    ("5.1.99", "Outras despesas operacionais", "expense", "debit", True),
    ("6", "Tributos e deduções", "expense", "debit", False), ("6.1.01", "Tributos sobre faturamento", "expense", "debit", True),
]
EXPENSE_CODES = {"combustivel":"5.1.01", "manutencao":"5.1.02", "diaria_motorista":"5.1.03", "diaria_ajudante":"5.1.03"}


def payable_preview(db: Session, user, end: date, chart: dict[str, ChartAccount]) -> list[dict]:
    """Project pending payables by due date, without persisting accounting entries."""
    posted = select(AccountingEntry.id).where(
        AccountingEntry.tenant_id == FinancialAccount.tenant_id,
        AccountingEntry.branch_id == FinancialAccount.branch_id,
        AccountingEntry.status == "posted",
        or_(
            and_(AccountingEntry.source_type == "expense", AccountingEntry.source_id == FinancialAccount.expense_id),
            and_(AccountingEntry.source_type == "financial_account", AccountingEntry.source_id == FinancialAccount.id),
        ),
    ).exists()
    stmt = select(FinancialAccount).where(
        FinancialAccount.tenant_id == user.tenant_id,
        FinancialAccount.kind == "payable",
        FinancialAccount.status == "pendente",
        FinancialAccount.due_date <= end,
        ~posted,
    )
    if user.role != "admin_global":
        stmt = stmt.where(FinancialAccount.branch_id == (user.branch_id if user.branch_id is not None else -1))
    rows = []
    for title in db.scalars(stmt.order_by(FinancialAccount.due_date, FinancialAccount.id)).all():
        code = EXPENSE_CODES.get(title.category, "5.1.99")
        custom = chart.get(title.category)
        if custom and custom.account_type == "expense" and custom.accepts_entries:
            code = custom.code
        amount = _money(title.amount)
        for account_code, debit, credit in [(code, amount, Decimal("0")), ("2.1.01", Decimal("0"), amount)]:
            rows.append({"account_id": chart[account_code].id, "entry_id": -title.id,
                "date": title.due_date, "memo": f"Prévia · {title.description} · {title.counterparty}",
                "source_type": "financial_account", "source_id": title.id,
                "debit": debit, "credit": credit, "is_preview": True})
    return rows

def ensure_default_chart(db: Session, tenant_id: int | None) -> dict[str, ChartAccount]:
    rows = list(db.scalars(select(ChartAccount).where(ChartAccount.tenant_id == tenant_id)).all())
    by_code = {row.code: row for row in rows}
    for code, name, kind, nature, accepts in DEFAULT_CHART:
        if code not in by_code:
            row = ChartAccount(tenant_id=tenant_id, code=code, name=name, account_type=kind, nature=nature, accepts_entries=accepts, active=True, system=True)
            db.add(row); db.flush(); by_code[code] = row
    for code, row in by_code.items():
        parent_code = code.rsplit(".", 1)[0] if "." in code else None
        if parent_code and parent_code in by_code and row.parent_id is None: row.parent_id = by_code[parent_code].id
    return by_code

def _assert_open(db: Session, branch_id: int, entry_date: date) -> None:
    closed = db.scalar(select(AccountingPeriod.id).where(AccountingPeriod.branch_id == branch_id, AccountingPeriod.status == "closed", AccountingPeriod.start_date <= entry_date, AccountingPeriod.end_date >= entry_date))
    if closed: raise HTTPException(409, "Período contábil fechado; reabertura formal é necessária.")

def _money(value) -> Decimal: return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def _new_entry(db: Session, *, branch_id:int, tenant_id:int|None, entry_date:date, memo:str, source_type:str, source_id:int, actor_id:int|None) -> AccountingEntry | None:
    existing=db.scalar(select(AccountingEntry).where(AccountingEntry.source_type==source_type,AccountingEntry.source_id==source_id))
    if existing:return None
    _assert_open(db,branch_id,entry_date)
    row=AccountingEntry(tenant_id=tenant_id,branch_id=branch_id,entry_date=entry_date,memo=memo,source_type=source_type,source_id=source_id,posted_by=actor_id,status="posted")
    db.add(row);db.flush();return row

def post_expense(db:Session, expense:Expense, actor_id:int|None=None)->AccountingEntry|None:
    entry=_new_entry(db,branch_id=expense.branch_id,tenant_id=expense.tenant_id,entry_date=expense.expense_date,memo=f"Despesa #{expense.id} · {expense.reason}",source_type="expense",source_id=expense.id,actor_id=actor_id)
    if entry is None:return None
    chart=ensure_default_chart(db,expense.tenant_id);amount=_money(expense.amount);expense_code=EXPENSE_CODES.get(expense.reason,"5.1.99")
    custom=chart.get(expense.reason)
    if custom and custom.account_type=="expense" and custom.accepts_entries: expense_code=custom.code
    db.add_all([AccountingLine(entry_id=entry.id,account_id=chart[expense_code].id,debit=amount,credit=0),AccountingLine(entry_id=entry.id,account_id=chart["2.1.01"].id,debit=0,credit=amount)])
    return entry

def post_revenue(db:Session,revenue:Revenue,actor_id:int|None=None)->AccountingEntry|None:
    entry=_new_entry(db,branch_id=revenue.branch_id,tenant_id=revenue.tenant_id,entry_date=revenue.revenue_date,memo=f"Receita #{revenue.id} · rota {revenue.route_id or '-'}",source_type="revenue",source_id=revenue.id,actor_id=actor_id)
    if entry is None:return None
    chart=ensure_default_chart(db,revenue.tenant_id);amount=_money(revenue.amount)
    db.add_all([AccountingLine(entry_id=entry.id,account_id=chart["1.1.02"].id,debit=amount,credit=0),AccountingLine(entry_id=entry.id,account_id=chart["4.1.01"].id,debit=0,credit=amount)])
    rules=db.scalars(select(TaxRule).where(TaxRule.tenant_id==revenue.tenant_id,TaxRule.active.is_(True),TaxRule.applies_to=="revenue",TaxRule.effective_from<=revenue.revenue_date,or_(TaxRule.effective_to.is_(None),TaxRule.effective_to>=revenue.revenue_date))).all()
    for rule in rules:
        tax=_money(amount*Decimal(str(rule.rate_percent))/Decimal("100"))
        if tax<=0:continue
        debit=chart.get(rule.debit_account_code);credit=chart.get(rule.credit_account_code)
        if not debit or not credit:raise HTTPException(409,f"Contas da regra tributária {rule.tax_code} não existem no plano de contas.")
        db.add_all([AccountingLine(entry_id=entry.id,account_id=debit.id,debit=tax,credit=0,tax_rule_id=rule.id,tax_code_snapshot=rule.tax_code,tax_rate_snapshot=rule.rate_percent,tax_base_snapshot=amount),AccountingLine(entry_id=entry.id,account_id=credit.id,debit=0,credit=tax,tax_rule_id=rule.id,tax_code_snapshot=rule.tax_code,tax_rate_snapshot=rule.rate_percent,tax_base_snapshot=amount)])
    return entry

def remove_posting(db:Session,source_type:str,source_id:int)->None:
    entry=db.scalar(select(AccountingEntry).where(AccountingEntry.source_type==source_type,AccountingEntry.source_id==source_id))
    if entry is None:return
    _assert_open(db,entry.branch_id,entry.entry_date)
    db.execute(delete(AccountingLine).where(AccountingLine.entry_id==entry.id));db.delete(entry);db.flush()

def repost_revenue(db:Session,revenue:Revenue,actor_id:int|None=None)->AccountingEntry|None:
    remove_posting(db,"revenue",revenue.id)
    return post_revenue(db,revenue,actor_id)

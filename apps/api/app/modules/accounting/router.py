"""Contabilidade: plano de contas, balancete, regras tributárias e fechamentos."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.core.permissions import FINANCE_ACCOUNTS_MANAGE, FINANCE_VIEW, Role, require_permission
from app.db.models import AccountingEntry, AccountingLine, AccountingPeriod, ChartAccount, Expense, Revenue, TaxRule, User
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services.accounting import ensure_default_chart
from app.services.audit import log

router=APIRouter(prefix="/accounting",tags=["accounting"])
_VIEW=require_permission(FINANCE_VIEW,Role.GESTOR_BRASIL,Role.GESTOR_FINANCEIRO)
_MANAGE=require_permission(FINANCE_ACCOUNTS_MANAGE,Role.GESTOR_FINANCEIRO)

class TaxRuleIn(BaseModel):
    name:str=Field(min_length=2,max_length=120);tax_code:str=Field(min_length=2,max_length=40);applies_to:str="revenue";rate_percent:Decimal=Field(ge=0,le=100);effective_from:date;effective_to:date|None=None;debit_account_code:str="6.1.01";credit_account_code:str="2.2.01";legal_basis:str|None=None;source_url:str|None=None
class CloseIn(BaseModel):
    start_date:date;end_date:date;cadence:str="monthly"

@router.get("/chart",dependencies=[Depends(_VIEW)])
def chart(db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    ensure_default_chart(db,user.tenant_id);db.commit()
    return db.scalars(select(ChartAccount).where(ChartAccount.tenant_id==user.tenant_id).order_by(ChartAccount.code)).all()

@router.get("/tax-rules",dependencies=[Depends(_VIEW)])
def tax_rules(db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    return db.scalars(select(TaxRule).where(TaxRule.tenant_id==user.tenant_id).order_by(TaxRule.tax_code,TaxRule.effective_from.desc())).all()

@router.post("/tax-rules",dependencies=[Depends(_MANAGE)])
def create_tax_rule(data:TaxRuleIn,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    if data.applies_to not in {"revenue","expense"}:raise HTTPException(422,"Aplicação tributária inválida.")
    if data.effective_to and data.effective_to<data.effective_from:raise HTTPException(422,"Fim da vigência anterior ao início.")
    chart=ensure_default_chart(db,user.tenant_id)
    if data.debit_account_code not in chart or data.credit_account_code not in chart:raise HTTPException(422,"Conta contábil tributária não encontrada.")
    tax_code=data.tax_code.strip().upper()
    previous=db.scalars(select(TaxRule).where(
        TaxRule.tenant_id==user.tenant_id,
        TaxRule.tax_code==tax_code,
        TaxRule.applies_to==data.applies_to,
        TaxRule.active.is_(True),
        TaxRule.effective_from<data.effective_from,
        or_(TaxRule.effective_to.is_(None),TaxRule.effective_to>=data.effective_from),
    )).all()
    for item in previous:
        item.effective_to=data.effective_from-timedelta(days=1)
    duplicate=db.scalar(select(TaxRule.id).where(
        TaxRule.tenant_id==user.tenant_id,
        TaxRule.tax_code==tax_code,
        TaxRule.applies_to==data.applies_to,
        TaxRule.effective_from==data.effective_from,
    ))
    if duplicate:raise HTTPException(409,"Já existe uma vigência deste tributo iniciando nessa data.")
    payload=data.model_dump();payload["tax_code"]=tax_code
    row=TaxRule(tenant_id=user.tenant_id,**payload,active=True);db.add(row);db.flush()
    # Fim vazio representa vigência aberta. Uma nova versão do mesmo código
    # encerra a anterior no dia precedente, sem recalcular lançamentos passados.
    log(db,user_id=user.id,action="create",entity="tax_rule",entity_id=row.id,detail=f"{row.tax_code}; aliquota={row.rate_percent}; vigencia={row.effective_from}; anteriores_encerradas={len(previous)}");db.commit();db.refresh(row);return row

@router.post("/tax-rules/{rule_id}/activate",dependencies=[Depends(_MANAGE)])
def activate_tax_rule(rule_id:int,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    row=db.get(TaxRule,rule_id)
    if row is None or row.tenant_id!=user.tenant_id:raise HTTPException(404,"Regra tributária não encontrada.")
    if row.active:return row
    previous=db.scalars(select(TaxRule).where(TaxRule.tenant_id==row.tenant_id,TaxRule.id!=row.id,TaxRule.tax_code==row.tax_code,TaxRule.applies_to==row.applies_to,TaxRule.active.is_(True),TaxRule.effective_from<=row.effective_from)).all()
    for item in previous:
        if item.effective_from==row.effective_from:item.active=False
        elif item.effective_to is None or item.effective_to>=row.effective_from:item.effective_to=row.effective_from-timedelta(days=1)
    row.active=True
    log(db,user_id=user.id,action="activate",entity="tax_rule",entity_id=row.id,detail=f"Revisada e aprovada; {row.tax_code}; {row.rate_percent}%; vigencia={row.effective_from}")
    db.commit();db.refresh(row);return row

@router.get("/trial-balance",dependencies=[Depends(_VIEW)])
def trial_balance(start:date,end:date,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    if end<start:raise HTTPException(422,"Período inválido.")
    ensure_default_chart(db,user.tenant_id);db.commit()
    accounts=db.scalars(select(ChartAccount).where(ChartAccount.tenant_id==user.tenant_id).order_by(ChartAccount.code)).all()
    def sums(before:bool=False):
        stmt=select(AccountingLine.account_id,func.coalesce(func.sum(AccountingLine.debit),0),func.coalesce(func.sum(AccountingLine.credit),0)).join(AccountingEntry,AccountingEntry.id==AccountingLine.entry_id).where(AccountingEntry.status=="posted")
        stmt=stmt.where(AccountingEntry.entry_date<start) if before else stmt.where(AccountingEntry.entry_date>=start,AccountingEntry.entry_date<=end)
        if user.role!=Role.ADMIN_GLOBAL.value:stmt=stmt.where(AccountingEntry.branch_id==user.branch_id)
        return {row[0]:(Decimal(row[1]),Decimal(row[2])) for row in db.execute(stmt.group_by(AccountingLine.account_id)).all()}
    opening,period=sums(True),sums(False);rows=[];total_debit=Decimal("0");total_credit=Decimal("0")
    for account in accounts:
        descendants=[item.id for item in accounts if item.code==account.code or item.code.startswith(account.code+".")]
        od=sum((opening.get(item,(Decimal("0"),Decimal("0")))[0] for item in descendants),Decimal("0"));oc=sum((opening.get(item,(Decimal("0"),Decimal("0")))[1] for item in descendants),Decimal("0"));debit=sum((period.get(item,(Decimal("0"),Decimal("0")))[0] for item in descendants),Decimal("0"));credit=sum((period.get(item,(Decimal("0"),Decimal("0")))[1] for item in descendants),Decimal("0"));opening_balance=(od-oc) if account.nature=="debit" else (oc-od);current=opening_balance+((debit-credit) if account.nature=="debit" else (credit-debit))
        if account.accepts_entries:total_debit+=debit;total_credit+=credit
        rows.append({"id":account.id,"code":account.code,"name":account.name,"account_type":account.account_type,"nature":account.nature,"accepts_entries":account.accepts_entries,"opening":float(opening_balance),"debit":float(debit),"credit":float(credit),"balance":float(current)})
    periods=db.scalars(select(AccountingPeriod).where(AccountingPeriod.branch_id==user.branch_id,AccountingPeriod.start_date<=end,AccountingPeriod.end_date>=start)).all() if user.branch_id else []
    return {"start":start,"end":end,"rows":rows,"total_debit":float(total_debit),"total_credit":float(total_credit),"difference":float(total_debit-total_credit),"balanced":total_debit==total_credit,"closed":any(row.status=="closed" for row in periods)}

@router.get("/ledger",dependencies=[Depends(_VIEW)])
def ledger(account_id:int,start:date,end:date,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    account=db.get(ChartAccount,account_id)
    if account is None or account.tenant_id!=user.tenant_id:raise HTTPException(404,"Conta contábil não encontrada.")
    stmt=select(AccountingLine,AccountingEntry).join(AccountingEntry,AccountingEntry.id==AccountingLine.entry_id).where(AccountingLine.account_id==account_id,AccountingEntry.entry_date>=start,AccountingEntry.entry_date<=end,AccountingEntry.status=="posted").order_by(AccountingEntry.entry_date,AccountingEntry.id)
    if user.role!=Role.ADMIN_GLOBAL.value:stmt=stmt.where(AccountingEntry.branch_id==user.branch_id)
    balance=Decimal("0");rows=[]
    for line,entry in db.execute(stmt).all():
        movement=Decimal(line.debit)-Decimal(line.credit) if account.nature=="debit" else Decimal(line.credit)-Decimal(line.debit);balance+=movement
        rows.append({"entry_id":entry.id,"date":entry.entry_date,"memo":entry.memo,"source_type":entry.source_type,"source_id":entry.source_id,"debit":float(line.debit),"credit":float(line.credit),"balance":float(balance),"tax_code":line.tax_code_snapshot,"tax_rate":float(line.tax_rate_snapshot) if line.tax_rate_snapshot is not None else None})
    return {"account":{"id":account.id,"code":account.code,"name":account.name,"nature":account.nature},"rows":rows}

@router.post("/periods/close",dependencies=[Depends(_MANAGE)])
def close_period(data:CloseIn,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    if user.branch_id is None:raise HTTPException(422,"Selecione uma filial para fechar.")
    if data.end_date<data.start_date:raise HTTPException(422,"Período inválido.")
    if data.cadence not in {"daily","weekly","monthly"}:raise HTTPException(422,"Periodicidade inválida.")
    pending=db.scalar(select(Expense.id).where(Expense.branch_id==user.branch_id,Expense.expense_date>=data.start_date,Expense.expense_date<=data.end_date,Expense.approval_status.in_(["pending","in_review","adjustment_requested"])))
    if pending:raise HTTPException(409,f"Existe despesa pendente de decisão no período (#{pending}).")
    unbalanced=db.scalar(select(AccountingEntry.id).join(AccountingLine,AccountingLine.entry_id==AccountingEntry.id).where(AccountingEntry.branch_id==user.branch_id,AccountingEntry.entry_date>=data.start_date,AccountingEntry.entry_date<=data.end_date,AccountingEntry.status=="posted").group_by(AccountingEntry.id).having(func.sum(AccountingLine.debit)!=func.sum(AccountingLine.credit)))
    if unbalanced:raise HTTPException(409,f"Lançamento contábil #{unbalanced} não está equilibrado.")
    missing_expense=db.scalar(select(Expense.id).where(Expense.branch_id==user.branch_id,Expense.expense_date>=data.start_date,Expense.expense_date<=data.end_date,Expense.approval_status=="approved",~Expense.id.in_(select(AccountingEntry.source_id).where(AccountingEntry.source_type=="expense"))))
    missing_revenue=db.scalar(select(Revenue.id).where(Revenue.branch_id==user.branch_id,Revenue.revenue_date>=data.start_date,Revenue.revenue_date<=data.end_date,~Revenue.id.in_(select(AccountingEntry.source_id).where(AccountingEntry.source_type=="revenue"))))
    if missing_expense or missing_revenue:raise HTTPException(409,f"Há documento sem contabilização: {('despesa #'+str(missing_expense)) if missing_expense else ('receita #'+str(missing_revenue))}.")
    duplicate=db.scalar(select(AccountingPeriod).where(AccountingPeriod.branch_id==user.branch_id,AccountingPeriod.start_date==data.start_date,AccountingPeriod.end_date==data.end_date))
    if duplicate:raise HTTPException(409,"Período já cadastrado.")
    period=AccountingPeriod(tenant_id=user.tenant_id,branch_id=user.branch_id,start_date=data.start_date,end_date=data.end_date,cadence=data.cadence,status="closed",closed_by=user.id,closed_at=datetime.now(timezone.utc));db.add(period);db.flush();log(db,user_id=user.id,action="close",entity="accounting_period",entity_id=period.id,detail=f"{data.start_date} a {data.end_date}; {data.cadence}");db.commit();db.refresh(period);return period

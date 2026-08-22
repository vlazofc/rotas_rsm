"""Gestão de clientes (tenants) — plataforma SaaS multicliente.

Cada cliente da Admmendes (ex.: Adeste) é um tenant isolado: filiais, motoristas,
veículos, rotas e personalização visual (branding) próprios.
"""
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import Role, require_roles
from app.core.security import create_access_token, create_refresh_token
from app.db.models import Branch, Tenant, User
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.modules.auth.schemas import TokenResponse
from app.services.audit import log

router = APIRouter(prefix="/tenants", tags=["tenants"])

DUE_SOON_DAYS = 5  # avisa como "a vencer" a partir de N dias antes do vencimento


class TenantIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", min_length=2, max_length=60)
    country: str = Field(default="BR", min_length=2, max_length=2)

    @field_validator("country")
    @classmethod
    def normalize_country(cls, value: str) -> str:
        return value.upper()


class TenantUpdate(BaseModel):
    name: str | None = None
    country: str | None = None
    active: bool | None = None
    feature_ocr: bool | None = None
    feature_sharepoint_sync: bool | None = None
    feature_financeiro: bool | None = None
    feature_rastreamento: bool | None = None
    feature_route_optimization: bool | None = None
    feature_km_calculation: bool | None = None
    billing_plan: str | None = None
    billing_amount: Decimal | None = None
    billing_due_day: int | None = Field(default=None, ge=1, le=28)


class TenantOut(BaseModel):
    id: int
    name: str
    slug: str
    country: str
    active: bool
    feature_ocr: bool
    feature_sharepoint_sync: bool
    feature_financeiro: bool
    feature_rastreamento: bool
    feature_route_optimization: bool = True
    feature_km_calculation: bool = True
    billing_plan: str | None = None
    billing_amount: Decimal | None = None
    billing_due_day: int | None = None
    billing_last_payment_date: date | None = None
    billing_status: str | None = None  # em_dia | a_vencer | atrasado | sem_plano (computado)
    billing_next_due_date: date | None = None  # computado

    class Config:
        from_attributes = True


def _next_due_date(due_day: int, today: date) -> date:
    """Próxima data de vencimento (este mês se ainda não passou, senão mês seguinte)."""
    candidate = today.replace(day=min(due_day, 28))
    return candidate if candidate >= today else candidate + relativedelta(months=1)


def _serialize_tenant(tenant: Tenant) -> TenantOut:
    out = TenantOut.model_validate(tenant)
    if not tenant.billing_due_day:
        out.billing_status = "sem_plano"
        return out
    today = date.today()
    due_this_cycle = date(today.year, today.month, min(tenant.billing_due_day, 28))
    cycle_start = due_this_cycle.replace(day=1)
    paid_this_cycle = (
        tenant.billing_last_payment_date is not None
        and tenant.billing_last_payment_date >= cycle_start
    )
    out.billing_next_due_date = _next_due_date(tenant.billing_due_day, today)
    if paid_this_cycle:
        out.billing_status = "em_dia"
    elif today > due_this_cycle:
        out.billing_status = "atrasado"
    elif (due_this_cycle - today).days <= DUE_SOON_DAYS:
        out.billing_status = "a_vencer"
    else:
        out.billing_status = "em_dia"
    return out


@router.get("", response_model=list[TenantOut],
            dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL))])
def list_tenants(db: Session = Depends(get_db)):
    return [_serialize_tenant(t) for t in db.scalars(select(Tenant).order_by(Tenant.name)).all()]


@router.get("/me", response_model=TenantOut)
def my_tenant(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.tenant_id is None:
        raise HTTPException(status_code=404, detail="Utilizador sem empresa associada.")
    tenant = db.get(Tenant, user.tenant_id)
    if tenant is None or not tenant.active:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    return _serialize_tenant(tenant)


@router.post("", response_model=TenantOut,
              dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL))])
def create_tenant(data: TenantIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if db.scalar(select(Tenant).where(Tenant.slug == data.slug)) is not None:
        raise HTTPException(status_code=400, detail="Já existe uma empresa com este identificador (slug).")
    tenant = Tenant(**data.model_dump())
    db.add(tenant)
    db.flush()
    # Cada cliente já nasce com seu próprio ambiente interno (filial padrão).
    branch = Branch(name=tenant.name, country=tenant.country, locale="pt-BR", tenant_id=tenant.id)
    db.add(branch)
    log(db, user_id=actor.id, action="create", entity="tenant", entity_id=tenant.id)
    db.commit()
    db.refresh(tenant)
    return _serialize_tenant(tenant)


@router.put("/{tenant_id}", response_model=TenantOut,
            dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL))])
def update_tenant(tenant_id: int, data: TenantUpdate,
                  db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    if not tenant.active:
        raise HTTPException(status_code=409, detail="Empresa inativa; ative-a antes de simular.")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(tenant, field, value)
    log(db, user_id=actor.id, action="update", entity="tenant", entity_id=tenant.id)
    db.commit()
    db.refresh(tenant)
    return _serialize_tenant(tenant)


@router.post("/{tenant_id}/mark-paid", response_model=TenantOut,
             dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL))])
def mark_tenant_paid(tenant_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    """Marca a mensalidade do ciclo atual como paga (controle interno, sem boleto)."""
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    tenant.billing_last_payment_date = date.today()
    log(db, user_id=actor.id, action="mark_paid", entity="tenant", entity_id=tenant.id)
    db.commit()
    db.refresh(tenant)
    return _serialize_tenant(tenant)


@router.post("/{tenant_id}/preview-session", response_model=TokenResponse,
             dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL))])
def create_preview_session(tenant_id: int, db: Session = Depends(get_db)):
    """Gera uma sessão temporária para simular o ambiente completo de um
    cliente (rotas, motoristas, dashboard — tudo como o cliente veria),
    sem precisar de uma senha. Usado pelo botão "Simular ambiente"."""
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    branch = db.scalar(select(Branch).where(Branch.tenant_id == tenant.id).order_by(Branch.id))
    if branch is None:
        raise HTTPException(status_code=409, detail="Este cliente ainda não tem nenhuma filial — crie uma antes de simular.")

    preview_email = f"preview@{tenant.slug}.admmendes.internal"
    preview_user = db.scalar(select(User).where(User.email == preview_email))
    if preview_user is None:
        preview_user = User(
            tenant_id=tenant.id, branch_id=branch.id, email=preview_email,
            name=f"Visualização — {tenant.name}", role=Role.GESTOR_BRASIL.value,
            hashed_password=None, active=True,
        )
        db.add(preview_user)
        db.flush()
    elif preview_user.branch_id != branch.id:
        preview_user.branch_id = branch.id

    db.commit()
    claims = {"role": preview_user.role, "branch_id": preview_user.branch_id, "name": preview_user.name}
    return TokenResponse(
        access_token=create_access_token(str(preview_user.id), **claims),
        refresh_token=create_refresh_token(str(preview_user.id)),
    )

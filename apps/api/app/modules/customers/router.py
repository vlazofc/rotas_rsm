"""Clientes finais atendidos por cada empresa da plataforma."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.permissions import Role, require_roles, require_same_tenant
from app.db.models import Customer, User
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services.audit import log, log_update, snapshot

router = APIRouter(prefix="/customers", tags=["customers"])
_MANAGER = require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL)


class CustomerIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    document: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=255)
    tenant_id: int | None = None


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    document: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=255)
    active: bool | None = None


class CustomerOut(BaseModel):
    id: int
    tenant_id: int
    name: str
    document: str | None
    email: EmailStr | None
    phone: str | None
    address: str | None
    active: bool

    class Config:
        from_attributes = True


@router.get("", response_model=list[CustomerOut])
def list_customers(
    only_active: bool = False,
    tenant_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Customer)
    if user.role == Role.ADMIN_GLOBAL.value:
        if tenant_id is not None:
            stmt = stmt.where(Customer.tenant_id == tenant_id)
    else:
        stmt = stmt.where(Customer.tenant_id == user.tenant_id)
    if only_active:
        stmt = stmt.where(Customer.active.is_(True))
    return db.scalars(stmt.order_by(Customer.name)).all()


@router.post("", response_model=CustomerOut, dependencies=[Depends(_MANAGER)])
def create_customer(data: CustomerIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    tenant_id = data.tenant_id if actor.role == Role.ADMIN_GLOBAL.value else actor.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=422, detail="Selecione a empresa do cliente.")
    customer = Customer(**data.model_dump(exclude={"tenant_id"}), tenant_id=tenant_id)
    db.add(customer)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Documento já cadastrado nesta empresa.")
    log(db, user_id=actor.id, action="create", entity="customer", entity_id=customer.id)
    db.commit()
    db.refresh(customer)
    return customer


@router.put("/{customer_id}", response_model=CustomerOut, dependencies=[Depends(_MANAGER)])
def update_customer(
    customer_id: int,
    data: CustomerUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    require_same_tenant(actor, customer.tenant_id)
    updates = data.model_dump(exclude_unset=True)
    before = snapshot(customer, list(updates))
    for field, value in updates.items():
        setattr(customer, field, value)
    log_update(db, user_id=actor.id, entity="customer", entity_id=customer.id, before=before, obj=customer, updates=updates)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Documento já cadastrado nesta empresa.")
    db.refresh(customer)
    return customer


@router.delete("/{customer_id}", dependencies=[Depends(_MANAGER)])
def delete_customer(customer_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    require_same_tenant(actor, customer.tenant_id)
    customer.active = False
    log(db, user_id=actor.id, action="deactivate", entity="customer", entity_id=customer.id)
    db.commit()
    return {"deactivated": customer_id}

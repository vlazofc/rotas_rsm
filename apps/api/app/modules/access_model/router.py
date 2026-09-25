from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.permissions import Role, require_branch_access, require_roles
from app.db.models import (
    Branch, BranchApprovalPolicy, Carrier, CarrierBranch, CarrierMaster, Driver, Tenant,
    CarrierUser, DriverBranch, User, Vehicle, VehicleBranch,
)
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services.audit import log
from app.services.documents import is_valid_document, normalize_document

router = APIRouter(prefix="/access-model", tags=["access-model"])
_ADMIN = require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL)
_APPROVAL = {"pending", "approved", "rejected"}


class ApprovalPolicyIn(BaseModel):
    require_driver_approval: bool = False
    require_vehicle_approval: bool = False
    activation_mode: str = Field(default="new_only", pattern="^(new_only|review_existing)$")


class AvailabilityIn(BaseModel):
    active: bool = True


class ReviewIn(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    reason: str | None = None


def _policy(db: Session, branch_id: int) -> BranchApprovalPolicy:
    row = db.scalar(select(BranchApprovalPolicy).where(BranchApprovalPolicy.branch_id == branch_id))
    if row is None:
        row = BranchApprovalPolicy(branch_id=branch_id)
        db.add(row)
        db.flush()
    return row


def _carrier_branch(db: Session, carrier_id: int, branch_id: int) -> CarrierBranch | None:
    return db.scalar(select(CarrierBranch).where(
        CarrierBranch.carrier_id == carrier_id,
        CarrierBranch.branch_id == branch_id,
        CarrierBranch.active.is_(True),
    ))


@router.get("/carrier-masters", dependencies=[Depends(_ADMIN)])
def list_carrier_masters(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    stmt = (
        select(CarrierMaster, Carrier, User)
        .join(Carrier, Carrier.id == CarrierMaster.carrier_id)
        .join(User, User.id == CarrierMaster.user_id)
        .where(CarrierMaster.active.is_(True))
        .order_by(Carrier.name, User.name)
    )
    membership = db.scalar(select(CarrierUser).where(CarrierUser.user_id == actor.id, CarrierUser.active.is_(True)))
    if membership is not None:
        stmt = stmt.where(CarrierMaster.carrier_id == membership.carrier_id)
    elif actor.role != Role.ADMIN_GLOBAL.value:
        stmt = stmt.where(Carrier.tenant_id == actor.tenant_id)
    return [{
        "carrier_id": carrier.id,
        "carrier_name": carrier.name,
        "user_id": user.id,
        "user_name": user.name,
        "user_email": user.email,
        "is_first_master": master.is_first_master,
    } for master, carrier, user in db.execute(stmt).all()]




@router.get("/branches/{branch_id}", dependencies=[Depends(_ADMIN)])
def branch_overview(branch_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    branch = require_branch_access(db, actor, branch_id)
    policy = _policy(db, branch_id)
    carriers = db.execute(
        select(Carrier.id, Carrier.name, Carrier.document, CarrierBranch.active)
        .join(CarrierBranch, CarrierBranch.carrier_id == Carrier.id)
        .where(CarrierBranch.branch_id == branch_id)
        .order_by(Carrier.name)
    ).all()
    db.commit()
    return {
        "branch": {"id": branch.id, "name": branch.name},
        "approval_policy": {
            "require_driver_approval": policy.require_driver_approval,
            "require_vehicle_approval": policy.require_vehicle_approval,
        },
        "carriers": [
            {"id": row.id, "name": row.name, "document": row.document, "active": row.active}
            for row in carriers
        ],
    }


@router.put("/branches/{branch_id}/approval-policy", dependencies=[Depends(_ADMIN)])
def configure_approval(branch_id: int, data: ApprovalPolicyIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    require_branch_access(db, actor, branch_id)
    policy = _policy(db, branch_id)
    enabling_drivers = data.require_driver_approval and not policy.require_driver_approval
    enabling_vehicles = data.require_vehicle_approval and not policy.require_vehicle_approval
    policy.require_driver_approval = data.require_driver_approval
    policy.require_vehicle_approval = data.require_vehicle_approval
    if data.activation_mode == "review_existing":
        if enabling_drivers:
            for link in db.scalars(select(DriverBranch).where(DriverBranch.branch_id == branch_id, DriverBranch.active.is_(True))).all():
                link.approval_status = "pending"
        if enabling_vehicles:
            for link in db.scalars(select(VehicleBranch).where(VehicleBranch.branch_id == branch_id, VehicleBranch.active.is_(True))).all():
                link.approval_status = "pending"
    log(db, user_id=actor.id, action="update", entity="branch_approval_policy", entity_id=branch_id,
        detail=f"drivers={data.require_driver_approval}; vehicles={data.require_vehicle_approval}; mode={data.activation_mode}")
    db.commit()
    return {"branch_id": branch_id, **data.model_dump()}


@router.put("/carriers/{carrier_id}/branches/{branch_id}", dependencies=[Depends(_ADMIN)])
def enable_carrier_branch(carrier_id: int, branch_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    branch = require_branch_access(db, actor, branch_id)
    carrier = db.get(Carrier, carrier_id)
    if carrier is None or carrier.tenant_id != branch.tenant_id:
        raise HTTPException(422, "Transportadora e filial devem pertencer ao mesmo ambiente operacional.")
    if not is_valid_document(carrier.document, carrier.person_type):
        raise HTTPException(422, "A transportadora precisa de um CPF/CNPJ válido para ser vinculada.")
    normalized = normalize_document(carrier.document)
    duplicate = next(
        (item for item in db.scalars(select(Carrier).where(Carrier.id != carrier.id)).all()
         if normalize_document(item.document) == normalized),
        None,
    )
    if duplicate is not None:
        raise HTTPException(409, "CPF/CNPJ já cadastrado em outra transportadora.")
    link = db.scalar(select(CarrierBranch).where(CarrierBranch.carrier_id == carrier_id, CarrierBranch.branch_id == branch_id))
    if link is None:
        link = CarrierBranch(carrier_id=carrier_id, branch_id=branch_id)
        db.add(link)
    else:
        link.active = True
    db.commit()
    return {"carrier_id": carrier_id, "branch_id": branch_id, "active": True}


@router.post("/carriers/{carrier_id}/masters/{user_id}", dependencies=[Depends(_ADMIN)])
def add_master(carrier_id: int, user_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    # Trava a linha da transportadora para serializar concorrentes: sem isso, duas
    # requisições simultâneas podem ler active_count < 3 ao mesmo tempo e ambas
    # inserirem, estourando o limite de três masters ativos.
    carrier = db.scalar(select(Carrier).where(Carrier.id == carrier_id).with_for_update())
    user = db.get(User, user_id)
    if carrier is None or user is None or user.tenant_id != carrier.tenant_id:
        raise HTTPException(422, "Master e transportadora devem pertencer ao mesmo ambiente operacional.")
    actor_membership = db.scalar(select(CarrierUser).where(CarrierUser.user_id == actor.id, CarrierUser.active.is_(True)))
    if actor_membership is not None:
        actor_master = db.scalar(select(CarrierMaster).where(
            CarrierMaster.user_id == actor.id,
            CarrierMaster.carrier_id == carrier_id,
            CarrierMaster.active.is_(True),
            CarrierMaster.is_first_master.is_(True),
        ))
        if actor_membership.carrier_id != carrier_id or actor_master is None:
            raise HTTPException(403, "Somente o primeiro master pode nomear outros masters desta transportadora.")
    existing = db.scalar(select(CarrierMaster).where(CarrierMaster.user_id == user_id))
    if existing is not None and existing.carrier_id != carrier_id:
        raise HTTPException(409, "Usuário já é master de outra transportadora.")
    tenant = db.get(Tenant, carrier.tenant_id) if carrier.tenant_id else None
    master_limit = carrier.max_masters or (tenant.max_carrier_masters if tenant else 3)
    active_count = db.scalar(select(func.count()).select_from(CarrierMaster).where(CarrierMaster.carrier_id == carrier_id, CarrierMaster.active.is_(True))) or 0
    if existing is None and active_count >= master_limit:
        raise HTTPException(409, f"Limite de {master_limit} masters ativos atingido para esta transportadora.")
    if existing is None:
        existing = CarrierMaster(carrier_id=carrier_id, user_id=user_id, active=True, is_first_master=active_count == 0)
        db.add(existing)
    else:
        existing.active = True
    membership = db.scalar(select(CarrierUser).where(CarrierUser.user_id == user_id))
    if membership is None:
        db.add(CarrierUser(carrier_id=carrier_id, user_id=user_id, active=True))
    elif membership.carrier_id != carrier_id:
        raise HTTPException(409, "Usuário já pertence a outra transportadora.")
    else:
        membership.active = True
    user.role = Role.GESTOR_BRASIL.value
    db.commit()
    current_count = db.scalar(select(func.count()).select_from(CarrierMaster).where(CarrierMaster.carrier_id == carrier_id, CarrierMaster.active.is_(True))) or 0
    return {"carrier_id": carrier_id, "user_id": user_id, "active": True, "is_first_master": existing.is_first_master, "active_count": current_count, "limit": master_limit}


def _availability(db: Session, *, kind: str, resource_id: int, branch_id: int, active: bool):
    branch = db.get(Branch, branch_id)
    model, link_model, fk = (Driver, DriverBranch, "driver_id") if kind == "driver" else (Vehicle, VehicleBranch, "vehicle_id")
    resource = db.get(model, resource_id)
    if branch is None or resource is None or resource.tenant_id != branch.tenant_id:
        raise HTTPException(422, "Cadastro e filial devem pertencer ao mesmo ambiente operacional.")
    if resource.carrier_id is None or _carrier_branch(db, resource.carrier_id, branch_id) is None:
        raise HTTPException(422, "A transportadora do cadastro não está habilitada nesta filial.")
    link = db.scalar(select(link_model).where(getattr(link_model, fk) == resource_id, link_model.branch_id == branch_id))
    policy = _policy(db, branch_id)
    required = policy.require_driver_approval if kind == "driver" else policy.require_vehicle_approval
    if link is None:
        link = link_model(**{fk: resource_id}, branch_id=branch_id)
        db.add(link)
    link.active = active
    if active:
        link.approval_status = "pending" if required else "approved"
        link.approval_reason = None
        link.reviewed_by_id = None
        link.reviewed_at = None
    return link


@router.put("/drivers/{driver_id}/branches/{branch_id}", dependencies=[Depends(_ADMIN)])
def set_driver_availability(driver_id: int, branch_id: int, data: AvailabilityIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    require_branch_access(db, actor, branch_id)
    link = _availability(db, kind="driver", resource_id=driver_id, branch_id=branch_id, active=data.active)
    db.commit()
    return {"driver_id": driver_id, "branch_id": branch_id, "active": link.active, "approval_status": link.approval_status}


@router.put("/vehicles/{vehicle_id}/branches/{branch_id}", dependencies=[Depends(_ADMIN)])
def set_vehicle_availability(vehicle_id: int, branch_id: int, data: AvailabilityIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    require_branch_access(db, actor, branch_id)
    link = _availability(db, kind="vehicle", resource_id=vehicle_id, branch_id=branch_id, active=data.active)
    db.commit()
    return {"vehicle_id": vehicle_id, "branch_id": branch_id, "active": link.active, "approval_status": link.approval_status}


@router.post("/{kind}/{resource_id}/branches/{branch_id}/review", dependencies=[Depends(_ADMIN)])
def review_availability(kind: str, resource_id: int, branch_id: int, data: ReviewIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    require_branch_access(db, actor, branch_id)
    if kind not in {"drivers", "vehicles"}:
        raise HTTPException(404, "Tipo de cadastro inválido.")
    link_model, fk = (DriverBranch, "driver_id") if kind == "drivers" else (VehicleBranch, "vehicle_id")
    link = db.scalar(select(link_model).where(getattr(link_model, fk) == resource_id, link_model.branch_id == branch_id))
    if link is None:
        raise HTTPException(404, "Disponibilidade não encontrada.")
    link.approval_status = data.decision
    link.approval_reason = data.reason
    link.reviewed_by_id = actor.id
    link.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    return {"resource_id": resource_id, "branch_id": branch_id, "approval_status": link.approval_status}

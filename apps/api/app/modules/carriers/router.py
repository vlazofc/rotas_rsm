"""Arrendatários/beneficiários e autorização por veículo/placa."""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.permissions import Role, require_internal_permission, require_internal_roles, require_roles
from app.db.models import Carrier, CarrierUser, CarrierVehicleLink, Driver, Route, Tenant, User, Vehicle
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services.audit import log, log_update, snapshot
from app.services.documents import normalize_document

router = APIRouter(prefix="/carriers", tags=["carriers"])
_MANAGER = require_internal_permission("module.carriers", Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL)

class CarrierData(BaseModel):
    name: str | None = None
    document: str | None = None
    person_type: str | None = None
    kind: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    bank_name: str | None = None
    bank_agency: str | None = None
    bank_account: str | None = None
    bank_account_type: str | None = None
    pix_key_type: str | None = None
    pix_key: str | None = None
    antt_number: str | None = None
    antt_expiry_date: date | None = None
    vehicle_ids: list[int] | None = None
    active: bool | None = None
    max_masters: int | None = Field(default=None, ge=1, le=20)

class CarrierIn(CarrierData):
    name: str
    document: str
    person_type: str = "pessoa_fisica"
    kind: str = "arrendatario"
    vehicle_ids: list[int] = []
    tenant_id: int | None = None

class VehicleLinkOut(BaseModel):
    id: int
    plate: str
    description: str | None = None
    antt_authorized: bool = True
    freight_beneficiary: bool = False

class CarrierOut(BaseModel):
    id: int
    tenant_id: int | None
    name: str
    document: str | None
    person_type: str
    kind: str
    phone: str | None
    email: str | None
    address: str | None
    bank_name: str | None
    bank_agency: str | None
    bank_account: str | None
    bank_account_type: str | None
    pix_key_type: str | None
    pix_key: str | None
    antt_number: str | None
    antt_expiry_date: date | None
    active: bool
    max_masters: int | None = None
    vehicles: list[VehicleLinkOut]

def _scope(carrier: Carrier, actor: User) -> None:
    if actor.role != Role.ADMIN_GLOBAL.value and carrier.tenant_id != actor.tenant_id:
        raise HTTPException(403, detail="Responsável de outra empresa.")

def _validate(data: CarrierData, current: Carrier | None = None) -> None:
    kind = data.kind or (current.kind if current else None)
    person_type = data.person_type or (current.person_type if current else None)
    document = data.document if data.document is not None else (current.document if current else None)
    antt = data.antt_number if data.antt_number is not None else (current.antt_number if current else None)
    if kind not in {"arrendatario", "beneficiario"}: raise HTTPException(422, detail="Tipo de responsável inválido.")
    if person_type not in {"pessoa_fisica", "pessoa_juridica"}: raise HTTPException(422, detail="Selecione CPF ou CNPJ.")
    digits = "".join(filter(str.isdigit, document or "")); expected = 11 if person_type == "pessoa_fisica" else 14
    # Cadastros antigos podem estar sem documento; uma simples ativação não deve ser bloqueada.
    if (current is None or data.document is not None or data.person_type is not None) and len(digits) != expected:
        raise HTTPException(422, detail=f"Informe um {'CPF' if expected == 11 else 'CNPJ'} com {expected} dígitos.")
    if data.vehicle_ids and not (antt or "").strip():
        raise HTTPException(422, detail="Informe a ANTT/RNTRC para liberar o responsável nas placas selecionadas.")

def _ensure_unique_document(db: Session, document: str | None, current_id: int | None = None) -> str | None:
    if document is None:
        return None
    normalized = normalize_document(document)
    for carrier in db.scalars(select(Carrier).where(Carrier.id != (current_id or -1))).all():
        if normalize_document(carrier.document) == normalized:
            raise HTTPException(409, detail="CPF/CNPJ já cadastrado em outro responsável.")
    return normalized

def _vehicle_links(db: Session, carrier: Carrier) -> list[VehicleLinkOut]:
    rows = db.execute(select(Vehicle, CarrierVehicleLink).join(CarrierVehicleLink, CarrierVehicleLink.vehicle_id == Vehicle.id).where(CarrierVehicleLink.carrier_id == carrier.id).order_by(Vehicle.plate)).all()
    return [VehicleLinkOut(id=v.id, plate=v.plate, description=v.description, antt_authorized=l.antt_authorized, freight_beneficiary=l.freight_beneficiary) for v, l in rows]

def _out(db: Session, carrier: Carrier) -> CarrierOut:
    values = {field: getattr(carrier, field) for field in CarrierOut.model_fields if field != "vehicles"}
    return CarrierOut(**values, vehicles=_vehicle_links(db, carrier))

def _sync_vehicles(db: Session, carrier: Carrier, vehicle_ids: list[int], actor: User) -> None:
    ids = list(dict.fromkeys(vehicle_ids)); vehicles = db.scalars(select(Vehicle).where(Vehicle.id.in_(ids))).all() if ids else []
    if len(vehicles) != len(ids) or any(v.tenant_id != carrier.tenant_id for v in vehicles): raise HTTPException(422, detail="Uma ou mais placas não pertencem à empresa selecionada.")
    if any(v.ownership_type != "agregado" for v in vehicles): raise HTTPException(422, detail="Somente veículos agregados podem ser vinculados a arrendatários ou beneficiários.")
    if any(not v.active or v.blocked for v in vehicles): raise HTTPException(422, detail="Veículo inativo ou bloqueado não pode receber novo vínculo.")
    occupied = db.scalar(select(CarrierVehicleLink).where(CarrierVehicleLink.vehicle_id.in_(ids), CarrierVehicleLink.carrier_id != carrier.id).limit(1)) if ids else None
    if occupied: raise HTTPException(409, detail="Uma das placas já possui responsável. Desvincule o responsável atual antes de realizar um novo vínculo.")
    old_links = db.scalars(select(CarrierVehicleLink).where(CarrierVehicleLink.carrier_id == carrier.id)).all(); old_ids = [link.vehicle_id for link in old_links]
    for link in old_links: db.delete(link)
    db.flush()
    for vehicle in vehicles:
        beneficiary = carrier.kind == "beneficiario"
        db.add(CarrierVehicleLink(carrier_id=carrier.id, vehicle_id=vehicle.id, antt_authorized=True, freight_beneficiary=beneficiary))
        vehicle.carrier_id = carrier.id
        vehicle.freight_receiver_type = "terceiro"
    for vehicle in db.scalars(select(Vehicle).where(Vehicle.carrier_id == carrier.id, Vehicle.id.not_in(ids))).all():
        vehicle.carrier_id = None
        vehicle.freight_receiver_type = "proprietario"
    if old_ids != ids: log(db, user_id=actor.id, action="update", entity="carrier_vehicle_link", entity_id=carrier.id, detail=f'vehicle_ids: "{old_ids}" -> "{ids}"; antt_authorized: "Sim"')

@router.get("", response_model=list[CarrierOut])
def list_carriers(only_active: bool = False, tenant_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(Carrier)
    membership = db.scalar(select(CarrierUser).where(CarrierUser.user_id == user.id, CarrierUser.active.is_(True)))
    if membership is not None:
        stmt = stmt.where(Carrier.id == membership.carrier_id)
    elif user.role == Role.MOTORISTA.value:
        driver_ids = select(Driver.id).where(Driver.user_id == user.id)
        stmt = stmt.where(Carrier.id.in_(select(Route.carrier_id).where(Route.driver_id.in_(driver_ids))))
    elif user.role == Role.ADMIN_GLOBAL.value:
        acting_carrier_id = getattr(user, "acting_carrier_id", None)
        if acting_carrier_id is not None: stmt = stmt.where(Carrier.id == acting_carrier_id)
        elif tenant_id is not None: stmt = stmt.where(Carrier.tenant_id == tenant_id)
    else: stmt = stmt.where(Carrier.tenant_id == user.tenant_id)
    if only_active: stmt = stmt.where(Carrier.active.is_(True))
    return [_out(db, item) for item in db.scalars(stmt.order_by(Carrier.name)).all()]

@router.post("", response_model=CarrierOut, dependencies=[Depends(_MANAGER)])
def create_carrier(data: CarrierIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    tenant_id = data.tenant_id if actor.role == Role.ADMIN_GLOBAL.value else actor.tenant_id
    if tenant_id is None or db.get(Tenant, tenant_id) is None: raise HTTPException(422, detail="Selecione uma empresa válida.")
    _validate(data); fields = data.model_dump(exclude={"vehicle_ids", "tenant_id", "active"})
    fields["document"] = _ensure_unique_document(db, data.document)
    carrier = Carrier(**fields, tenant_id=tenant_id, active=True); db.add(carrier); db.flush()
    _sync_vehicles(db, carrier, data.vehicle_ids, actor)
    log(db, user_id=actor.id, action="create", entity="carrier", entity_id=carrier.id, detail=f'name: "{carrier.name}"; document: "{carrier.document}"; ANTT: "{carrier.antt_number or "-"}"')
    db.commit(); db.refresh(carrier); return _out(db, carrier)

@router.put("/{carrier_id}", response_model=CarrierOut, dependencies=[Depends(_MANAGER)])
def update_carrier(carrier_id: int, data: CarrierData, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    carrier = db.get(Carrier, carrier_id)
    if carrier is None: raise HTTPException(404, detail="Arrendatário/beneficiário não encontrado.")
    _scope(carrier, actor); _validate(data, carrier); updates = data.model_dump(exclude_unset=True, exclude={"vehicle_ids"}); before = snapshot(carrier, list(updates))
    if "document" in updates: updates["document"] = _ensure_unique_document(db, updates["document"], carrier.id)
    for field, value in updates.items(): setattr(carrier, field, value)
    if data.vehicle_ids is not None: _sync_vehicles(db, carrier, data.vehicle_ids, actor)
    log_update(db, user_id=actor.id, entity="carrier", entity_id=carrier.id, before=before, obj=carrier, updates=updates)
    db.commit(); db.refresh(carrier); return _out(db, carrier)

@router.delete("/{carrier_id}", dependencies=[Depends(_MANAGER)])
def delete_carrier(carrier_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    carrier = db.get(Carrier, carrier_id)
    if carrier is None: raise HTTPException(404, detail="Responsável não encontrado.")
    _scope(carrier, actor)
    if db.scalar(select(Driver).where(Driver.carrier_id == carrier_id)) or db.scalar(select(Vehicle).where(Vehicle.carrier_id == carrier_id)): raise HTTPException(409, detail="Responsável em uso. Inative para manter o histórico.")
    name = carrier.name; db.delete(carrier); log(db, user_id=actor.id, action="delete", entity="carrier", entity_id=carrier_id, detail=f'name: "{name}"'); db.commit(); return {"deleted": carrier_id}

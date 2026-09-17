from datetime import date, datetime, timezone
from pathlib import Path
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import Role, has_all_environment_access, require_branch_access, require_roles, require_same_tenant
from app.db.models import Attachment, Carrier, CarrierVehicleLink, Route, Tenant, User, Vehicle, VehicleChangeRequest, VehicleOwner, VehicleType
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services import storage
from app.services.audit import log, log_update, snapshot
from app.services.entity_status import StatusChangeIn, apply_status

router = APIRouter(prefix="/vehicles", tags=["vehicles"])
_MANAGER = require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL)
_STAFF = require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL, Role.OPERADOR_LOGISTICO)
PROTECTED = {"renavam", "vehicle_type_id", "axles"}

class OwnerIn(BaseModel):
    name: str; document: str; person_type: str = "pessoa_fisica"; phone: str | None = None; email: str | None = None; address: str | None = None
    bank_name: str | None = None; bank_agency: str | None = None; bank_account: str | None = None
    bank_account_type: str | None = None; pix_key_type: str | None = None; pix_key: str | None = None

class OwnerOut(OwnerIn):
    id: int; active: bool; blocked: bool = False; status_reason: str | None = None; is_tenant_company: bool = False
    class Config: from_attributes = True

class VehicleUpdate(BaseModel):
    plate: str | None = None; description: str | None = None; owner_id: int | None = None
    renavam: str | None = None; chassis: str | None = None; registry_state: str | None = None
    brand: str | None = None; model: str | None = None; manufacture_year: int | None = None; model_year: int | None = None
    color: str | None = None; fuel: str | None = None; crlv_expiry_date: date | None = None
    vehicle_type_id: int | None = None; axles: int | None = None; length_m: float | None = None; width_m: float | None = None
    rear_dual_wheels: bool | None = None
    height_m: float | None = None; gross_weight_kg: float | None = None; temperature_controlled: bool | None = None
    active: bool | None = None; change_reason: str | None = None
    ownership_type: str | None = None
    freight_receiver_type: str | None = None; carrier_id: int | None = None
    antt_number: str | None = None; antt_expiry_date: date | None = None

class VehicleOut(BaseModel):
    id: int; branch_id: int; plate: str; active: bool; blocked: bool = False; status_reason: str | None = None; description: str | None = None
    owner_id: int | None = None; owner_name: str | None = None; renavam: str | None = None; chassis: str | None = None
    registry_state: str | None = None; brand: str | None = None; model: str | None = None
    manufacture_year: int | None = None; model_year: int | None = None; color: str | None = None; fuel: str | None = None
    crlv_expiry_date: date | None = None; vehicle_type_id: int | None = None; vehicle_type_label: str | None = None
    axles: int | None = None; length_m: float | None = None; width_m: float | None = None; height_m: float | None = None
    rear_dual_wheels: bool = True
    gross_weight_kg: float | None = None; temperature_controlled: bool = False; crlv_url: str | None = None; age: int | None = None
    ownership_type: str = "proprio"
    freight_receiver_type: str = "proprietario"; carrier_id: int | None = None; carrier_name: str | None = None
    antt_number: str | None = None; antt_expiry_date: date | None = None
    class Config: from_attributes = True

class ChangeIn(BaseModel):
    renavam: str | None = None; vehicle_type_id: int | None = None; axles: int | None = None; reason: str

class DecisionIn(BaseModel):
    decision: str; note: str | None = None

class ChangeOut(BaseModel):
    id: int; vehicle_id: int; plate: str; requested_by_id: int; requested_by_name: str; reason: str; status: str
    requested_renavam: str | None; requested_vehicle_type_id: int | None; requested_axles: int | None
    previous_renavam: str | None; previous_vehicle_type_id: int | None; previous_axles: int | None
    reviewed_by_id: int | None; reviewed_by_name: str | None; reviewed_at: datetime | None; decision_note: str | None; created_at: datetime

def _vehicle_out(db: Session, vehicle: Vehicle) -> VehicleOut:
    owner = db.get(VehicleOwner, vehicle.owner_id) if vehicle.owner_id else None
    carrier = db.get(Carrier, vehicle.carrier_id) if vehicle.carrier_id else None
    kind = db.get(VehicleType, vehicle.vehicle_type_id) if vehicle.vehicle_type_id else None
    values = {**vehicle.__dict__, "owner_name": owner.name if owner else None, "carrier_name": carrier.name if carrier else None,
              "vehicle_type_label": (kind.label_pt_br or kind.label) if kind else None,
              "crlv_url": storage.get_presigned_url(vehicle.crlv_attachment.bucket, vehicle.crlv_attachment.storage_key) if vehicle.crlv_attachment else None,
              "age": date.today().year - vehicle.manufacture_year if vehicle.manufacture_year else None}
    return VehicleOut.model_validate(values)

def _request_out(db: Session, row: VehicleChangeRequest) -> ChangeOut:
    vehicle=db.get(Vehicle,row.vehicle_id); requester=db.get(User,row.requested_by_id); reviewer=db.get(User,row.reviewed_by_id) if row.reviewed_by_id else None
    return ChangeOut.model_validate({**row.__dict__,"plate":vehicle.plate,"requested_by_name":requester.name,"reviewed_by_name":reviewer.name if reviewer else None})

def _validate_owner(db: Session, tenant_id: int | None, owner_id: int | None):
    if owner_id is None: return
    owner=db.get(VehicleOwner,owner_id)
    if owner is None or owner.tenant_id != tenant_id: raise HTTPException(422,"Proprietário não pertence à empresa.")
    if not owner.active or owner.blocked:raise HTTPException(422,"Proprietário inativo ou bloqueado não pode ser vinculado ao veículo.")

def _validate_receiver(db:Session,tenant_id:int|None,ownership_type:str,receiver_type:str,carrier_id:int|None,current:Vehicle|None=None)->Carrier|None:
    if ownership_type != "agregado": return None
    if receiver_type not in {"proprietario","terceiro"}: raise HTTPException(422,"Selecione se o recebedor é o proprietário ou um terceiro.")
    if receiver_type == "proprietario": return None
    if not carrier_id: raise HTTPException(422,"Selecione o arrendatário/beneficiário que receberá o frete.")
    if current and current.carrier_id and current.carrier_id != carrier_id:
        raise HTTPException(409,"Este veículo já possui responsável. Desvincule o atual, salve, e depois vincule o novo.")
    carrier=db.get(Carrier,carrier_id)
    if carrier is None or carrier.tenant_id!=tenant_id or not carrier.active: raise HTTPException(422,"Arrendatário/beneficiário inválido ou inativo.")
    if not (carrier.antt_number or "").strip(): raise HTTPException(422,"O terceiro selecionado não possui ANTT/RNTRC liberada.")
    return carrier

def _sync_receiver_link(db:Session,vehicle:Vehicle,carrier:Carrier|None,actor:User)->None:
    old_id=vehicle.carrier_id
    old_links=db.scalars(select(CarrierVehicleLink).where(CarrierVehicleLink.vehicle_id==vehicle.id)).all()
    for link in old_links: db.delete(link)
    db.flush()
    vehicle.carrier_id=carrier.id if carrier else None
    vehicle.freight_receiver_type="terceiro" if carrier else "proprietario"
    if carrier: db.add(CarrierVehicleLink(carrier_id=carrier.id,vehicle_id=vehicle.id,antt_authorized=True,freight_beneficiary=True))
    if old_id != vehicle.carrier_id:
        log(db,user_id=actor.id,action="update",entity="vehicle_freight_receiver",entity_id=vehicle.id,detail=f'carrier_id: "{old_id or "-"}" -> "{vehicle.carrier_id or "proprietário"}"')

def _company_owner(db:Session,tenant_id:int|None)->tuple[VehicleOwner,Tenant]:
    tenant=db.get(Tenant,tenant_id) if tenant_id else None
    if tenant is None:raise HTTPException(422,"Empresa contratante não identificada.")
    if not tenant.document or not tenant.legal_name or not tenant.address or not tenant.antt_number:
        raise HTTPException(422,"Complete CNPJ, razão social, endereço e ANTT em Configuração > Dados da empresa antes de cadastrar a frota própria.")
    owner=db.scalar(select(VehicleOwner).where(VehicleOwner.tenant_id==tenant.id,VehicleOwner.is_tenant_company.is_(True)))
    values={"name":tenant.legal_name,"document":tenant.document,"person_type":"pessoa_juridica","phone":tenant.phone,"email":tenant.email,"address":", ".join(filter(None,[tenant.address,tenant.city,tenant.state])),"active":True,"is_tenant_company":True}
    if owner is None:
        owner=VehicleOwner(tenant_id=tenant.id,**values);db.add(owner);db.flush()
    else:
        for key,value in values.items():setattr(owner,key,value)
    return owner,tenant

async def _save_crlv(file: UploadFile, branch_id: int, vehicle_id: int) -> Attachment:
    content_type=file.content_type or "application/octet-stream"
    if content_type not in {"application/pdf","image/png","image/jpeg","image/jpg","image/webp"}: raise HTTPException(415,"CRLV deve ser PDF, JPG, PNG ou WEBP.")
    content=await file.read()
    if not content: raise HTTPException(400,"Arquivo do CRLV está vazio.")
    if len(content)>settings.max_upload_mb*1024*1024: raise HTTPException(413,f"Arquivo acima de {settings.max_upload_mb} MB.")
    storage.ensure_buckets();name=Path(file.filename or "crlv").name;key=f"veiculos/{branch_id}/{vehicle_id}/crlv-{uuid.uuid4().hex}-{name}"
    storage.put_object(settings.minio_bucket_proofs,key,content,content_type)
    return Attachment(bucket=settings.minio_bucket_proofs,storage_key=key,content_type=content_type,size_bytes=len(content))

@router.get("/owners",response_model=list[OwnerOut],dependencies=[Depends(_STAFF)])
def list_owners(q:str|None=None,db:Session=Depends(get_db),actor:User=Depends(get_current_user)):
    stmt=select(VehicleOwner).where(VehicleOwner.tenant_id==actor.tenant_id)
    rows=db.scalars(stmt.order_by(VehicleOwner.name).limit(250)).all()
    if q and len(q.strip())>=3:
        term=q.strip().casefold()
        rows=[row for row in rows if term in row.name.casefold() or term in row.document.casefold()]
    return rows[:50]

@router.post("/owners",response_model=OwnerOut,dependencies=[Depends(_STAFF)])
def create_owner(data:OwnerIn,db:Session=Depends(get_db),actor:User=Depends(get_current_user)):
    if actor.tenant_id is None: raise HTTPException(422,"Empresa não identificada.")
    if data.person_type not in {"pessoa_fisica","pessoa_juridica"}:raise HTTPException(422,"Tipo de proprietário inválido.")
    document="".join(char for char in data.document if char.isdigit())
    expected=11 if data.person_type=="pessoa_fisica" else 14
    if len(document)!=expected:raise HTTPException(422,f"Informe um {'CPF' if expected==11 else 'CNPJ'} válido com {expected} dígitos.")
    duplicate=db.scalar(select(VehicleOwner).where(VehicleOwner.tenant_id==actor.tenant_id,VehicleOwner.document==document))
    if duplicate:raise HTTPException(409,"Já existe um proprietário com este CPF/CNPJ.")
    payload=data.model_dump();payload["document"]=document
    row=VehicleOwner(tenant_id=actor.tenant_id,**payload);db.add(row);db.flush();log(db,user_id=actor.id,action="create",entity="vehicle_owner",entity_id=row.id);db.commit();db.refresh(row);return row

@router.put("/owners/{owner_id}",response_model=OwnerOut,dependencies=[Depends(_STAFF)])
def update_owner(owner_id:int,data:OwnerIn,db:Session=Depends(get_db),actor:User=Depends(get_current_user)):
    row=db.get(VehicleOwner,owner_id)
    if row is None:raise HTTPException(404,"Proprietário não encontrado.")
    require_same_tenant(actor,row.tenant_id);before=snapshot(row,list(data.model_fields))
    for key,value in data.model_dump().items():setattr(row,key,value)
    log_update(db,user_id=actor.id,entity="vehicle_owner",entity_id=row.id,before=before,obj=row,updates=data.model_dump());db.commit();db.refresh(row);return row

@router.post("/owners/{owner_id}/status",response_model=OwnerOut,dependencies=[Depends(_STAFF)])
def change_owner_status(owner_id:int,data:StatusChangeIn,db:Session=Depends(get_db),actor:User=Depends(get_current_user)):
    row=db.get(VehicleOwner,owner_id)
    if row is None:raise HTTPException(404,"Proprietário não encontrado.")
    require_same_tenant(actor,row.tenant_id)
    if row.is_tenant_company and data.action in {"deactivate","block"}:raise HTTPException(409,"O proprietário institucional da frota própria não pode ser bloqueado ou desativado.")
    apply_status(db,obj=row,data=data,user_id=actor.id,entity="vehicle_owner");db.commit();db.refresh(row);return row

@router.get("/change-requests",response_model=list[ChangeOut],dependencies=[Depends(_STAFF)])
def list_requests(db:Session=Depends(get_db),actor:User=Depends(get_current_user)):
    rows=db.scalars(select(VehicleChangeRequest).where(VehicleChangeRequest.tenant_id==actor.tenant_id).order_by(VehicleChangeRequest.created_at.desc())).all()
    return [_request_out(db,row) for row in rows]

@router.post("/change-requests/{request_id}/decision",response_model=ChangeOut,dependencies=[Depends(_MANAGER)])
def decide_request(request_id:int,data:DecisionIn,db:Session=Depends(get_db),actor:User=Depends(get_current_user)):
    if data.decision not in {"approved","rejected"}:raise HTTPException(422,"Decisão inválida.")
    row=db.get(VehicleChangeRequest,request_id)
    if row is None or row.tenant_id!=actor.tenant_id:raise HTTPException(404,"Solicitação não encontrada.")
    if row.status!="pending":raise HTTPException(409,"Solicitação já decidida.")
    vehicle=db.get(Vehicle,row.vehicle_id);require_branch_access(db,actor,vehicle.branch_id)
    if data.decision=="approved":vehicle.renavam=row.requested_renavam;vehicle.vehicle_type_id=row.requested_vehicle_type_id;vehicle.axles=row.requested_axles
    row.status=data.decision;row.reviewed_by_id=actor.id;row.reviewed_at=datetime.now(timezone.utc);row.decision_note=data.note
    log(db,user_id=actor.id,action=data.decision,entity="vehicle_change_request",entity_id=row.id,detail=data.note);db.commit();db.refresh(row);return _request_out(db,row)

@router.get("",response_model=list[VehicleOut],dependencies=[Depends(_STAFF)])
def list_vehicles(db:Session=Depends(get_db),actor:User=Depends(get_current_user)):
    stmt=select(Vehicle).order_by(Vehicle.plate)
    if not has_all_environment_access(actor):stmt=stmt.where(Vehicle.tenant_id==actor.tenant_id)
    return [_vehicle_out(db,row) for row in db.scalars(stmt).all()]

@router.post("/with-crlv",response_model=VehicleOut,dependencies=[Depends(_STAFF)])
async def create_vehicle(branch_id:int=Form(...),plate:str=Form(...),renavam:str=Form(...),chassis:str=Form(...),owner_id:int|None=Form(None),vehicle_type_id:int=Form(...),axles:int=Form(...),crlv:UploadFile=File(...),description:str|None=Form(None),registry_state:str|None=Form(None),brand:str|None=Form(None),model:str|None=Form(None),manufacture_year:int|None=Form(None),model_year:int|None=Form(None),color:str|None=Form(None),fuel:str|None=Form(None),crlv_expiry_date:date|None=Form(None),length_m:float|None=Form(None),width_m:float|None=Form(None),height_m:float|None=Form(None),gross_weight_kg:float|None=Form(None),temperature_controlled:bool=Form(False),ownership_type:str=Form("proprio"),freight_receiver_type:str=Form("proprietario"),carrier_id:int|None=Form(None),antt_number:str|None=Form(None),antt_expiry_date:date|None=Form(None),db:Session=Depends(get_db),actor:User=Depends(get_current_user)):
    branch=require_branch_access(db,actor,branch_id)
    if ownership_type not in {"proprio","agregado"}:raise HTTPException(422,"Vínculo do veículo inválido.")
    if ownership_type=="proprio":
        company_owner,tenant=_company_owner(db,branch.tenant_id);owner_id=company_owner.id;antt_number=tenant.antt_number;antt_expiry_date=tenant.antt_expiry_date;freight_receiver_type="proprietario";carrier_id=None
    _validate_owner(db,branch.tenant_id,owner_id)
    if ownership_type=="agregado" and not owner_id:raise HTTPException(422,"Veículo agregado deve estar vinculado a um proprietário.")
    if ownership_type=="agregado" and not (antt_number or "").strip():raise HTTPException(422,"Informe a ANTT vinculada ao veículo agregado.")
    receiver=_validate_receiver(db,branch.tenant_id,ownership_type,freight_receiver_type,carrier_id)
    vehicle=Vehicle(tenant_id=branch.tenant_id,branch_id=branch_id,plate=plate.upper(),renavam=renavam,chassis=chassis.upper(),owner_id=owner_id,vehicle_type_id=vehicle_type_id,axles=axles,description=description,registry_state=registry_state,brand=brand,model=model,manufacture_year=manufacture_year,model_year=model_year,color=color,fuel=fuel,crlv_expiry_date=crlv_expiry_date,length_m=length_m,width_m=width_m,height_m=height_m,gross_weight_kg=gross_weight_kg,temperature_controlled=temperature_controlled,ownership_type=ownership_type,freight_receiver_type=freight_receiver_type,carrier_id=carrier_id,antt_number=antt_number,antt_expiry_date=antt_expiry_date)
    db.add(vehicle);db.flush();_sync_receiver_link(db,vehicle,receiver,actor);attachment=await _save_crlv(crlv,branch_id,vehicle.id);db.add(attachment);db.flush();vehicle.crlv_attachment_id=attachment.id
    log(db,user_id=actor.id,action="create",entity="vehicle",entity_id=vehicle.id,detail="CRLV anexado");db.commit();db.refresh(vehicle);return _vehicle_out(db,vehicle)

@router.post("/{vehicle_id}/change-request",response_model=ChangeOut,dependencies=[Depends(_STAFF)])
def request_change(vehicle_id:int,data:ChangeIn,db:Session=Depends(get_db),actor:User=Depends(get_current_user)):
    if len(data.reason.strip())<10:raise HTTPException(422,"Descreva o motivo da alteração com pelo menos 10 caracteres.")
    vehicle=db.get(Vehicle,vehicle_id)
    if vehicle is None:raise HTTPException(404,"Veículo não encontrado.")
    require_branch_access(db,actor,vehicle.branch_id)
    row=VehicleChangeRequest(branch_id=vehicle.branch_id,vehicle_id=vehicle.id,requested_by_id=actor.id,reason=data.reason.strip(),requested_renavam=data.renavam,requested_vehicle_type_id=data.vehicle_type_id,requested_axles=data.axles,previous_renavam=vehicle.renavam,previous_vehicle_type_id=vehicle.vehicle_type_id,previous_axles=vehicle.axles)
    db.add(row);db.flush();log(db,user_id=actor.id,action="request_change",entity="vehicle",entity_id=vehicle.id,detail=data.reason);db.commit();db.refresh(row);return _request_out(db,row)

@router.put("/{vehicle_id}",response_model=VehicleOut,dependencies=[Depends(_STAFF)])
def update_vehicle(vehicle_id:int,data:VehicleUpdate,db:Session=Depends(get_db),actor:User=Depends(get_current_user)):
    vehicle=db.get(Vehicle,vehicle_id)
    if vehicle is None:raise HTTPException(404,"Veículo não encontrado.")
    require_branch_access(db,actor,vehicle.branch_id);updates=data.model_dump(exclude_unset=True);reason=updates.pop("change_reason",None)
    if "active" in updates:raise HTTPException(422,"Use a ação de situação para ativar ou desativar o veículo.")
    ownership_type=updates.get("ownership_type",vehicle.ownership_type)
    if ownership_type not in {"proprio","agregado"}:raise HTTPException(422,"Vínculo do veículo inválido.")
    if ownership_type=="proprio":
        company_owner,tenant=_company_owner(db,vehicle.tenant_id);updates["owner_id"]=company_owner.id;updates["antt_number"]=tenant.antt_number;updates["antt_expiry_date"]=tenant.antt_expiry_date;updates["freight_receiver_type"]="proprietario";updates["carrier_id"]=None
    if ownership_type=="agregado" and not updates.get("owner_id",vehicle.owner_id):raise HTTPException(422,"Veículo agregado deve estar vinculado a um proprietário.")
    if ownership_type=="agregado" and not (updates.get("antt_number",vehicle.antt_number) or "").strip():raise HTTPException(422,"Informe a ANTT vinculada ao veículo agregado.")
    receiver_type=updates.get("freight_receiver_type",vehicle.freight_receiver_type)
    requested_carrier_id=updates.get("carrier_id",vehicle.carrier_id)
    receiver=_validate_receiver(db,vehicle.tenant_id,ownership_type,receiver_type,requested_carrier_id,vehicle)
    protected={key:value for key,value in updates.items() if key in PROTECTED and value!=getattr(vehicle,key)};manager=actor.role in {Role.ADMIN_GLOBAL.value,Role.GESTOR_BRASIL.value}
    if protected and not manager:
        if not reason or len(reason.strip())<10:raise HTTPException(422,"Informe o motivo para solicitar alteração de RENAVAM, tipologia ou eixos.")
        request_change(vehicle_id,ChangeIn(renavam=updates.get("renavam",vehicle.renavam),vehicle_type_id=updates.get("vehicle_type_id",vehicle.vehicle_type_id),axles=updates.get("axles",vehicle.axles),reason=reason),db,actor)
        for key in protected:updates.pop(key,None)
    _validate_owner(db,vehicle.tenant_id,updates.get("owner_id"));before=snapshot(vehicle,list(updates))
    for key,value in updates.items():setattr(vehicle,key,value)
    _sync_receiver_link(db,vehicle,receiver,actor)
    log_update(db,user_id=actor.id,entity="vehicle",entity_id=vehicle.id,before=before,obj=vehicle,updates=updates);db.commit();db.refresh(vehicle);return _vehicle_out(db,vehicle)

@router.post("/{vehicle_id}/status",response_model=VehicleOut,dependencies=[Depends(_STAFF)])
def change_vehicle_status(vehicle_id:int,data:StatusChangeIn,db:Session=Depends(get_db),actor:User=Depends(get_current_user)):
    vehicle=db.get(Vehicle,vehicle_id)
    if vehicle is None:raise HTTPException(404,"Veículo não encontrado.")
    require_branch_access(db,actor,vehicle.branch_id);apply_status(db,obj=vehicle,data=data,user_id=actor.id,entity="vehicle");db.commit();db.refresh(vehicle);return _vehicle_out(db,vehicle)

@router.post("/{vehicle_id}/crlv",response_model=VehicleOut,dependencies=[Depends(_STAFF)])
async def replace_crlv(vehicle_id:int,crlv:UploadFile=File(...),reason:str|None=Form(None),db:Session=Depends(get_db),actor:User=Depends(get_current_user)):
    vehicle=db.get(Vehicle,vehicle_id)
    if vehicle is None:raise HTTPException(404,"Veículo não encontrado.")
    if actor.role not in {Role.ADMIN_GLOBAL.value,Role.GESTOR_BRASIL.value} and (not reason or len(reason.strip())<10):raise HTTPException(422,"Informe o motivo da substituição do CRLV com pelo menos 10 caracteres.")
    require_branch_access(db,actor,vehicle.branch_id);attachment=await _save_crlv(crlv,vehicle.branch_id,vehicle.id);db.add(attachment);db.flush();vehicle.crlv_attachment_id=attachment.id
    log(db,user_id=actor.id,action="replace_crlv",entity="vehicle",entity_id=vehicle.id,detail=reason);db.commit();db.refresh(vehicle);return _vehicle_out(db,vehicle)

@router.delete("/{vehicle_id}",dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL))])
def delete_vehicle(vehicle_id:int,db:Session=Depends(get_db),actor:User=Depends(get_current_user)):
    vehicle=db.get(Vehicle,vehicle_id)
    if vehicle is None:raise HTTPException(404,"Veículo não encontrado.")
    if db.scalar(select(Route).where(Route.vehicle_id==vehicle_id)):raise HTTPException(409,"Veículo possui rota atribuída. Inative para manter o histórico.")
    db.delete(vehicle);log(db,user_id=actor.id,action="delete",entity="vehicle",entity_id=vehicle_id);db.commit();return {"deleted":vehicle_id}

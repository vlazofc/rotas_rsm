from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.permissions import Role,require_roles,require_same_tenant
from app.db.models import PurchaseTicket,ServiceProvider,Supplier,User
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services.audit import log,log_update,snapshot

router=APIRouter(prefix="/suppliers",tags=["suppliers"]);_STAFF=require_roles(Role.ADMIN_GLOBAL,Role.GESTOR_BRASIL,Role.GESTOR_FINANCEIRO,Role.OPERADOR_LOGISTICO)
class SupplierIn(BaseModel):
 legal_name:str;trade_name:str|None=None;document:str;state_registration:str|None=None;municipal_registration:str|None=None;supplier_type:str="product";contact_name:str|None=None;phone:str|None=None;email:str|None=None;postal_code:str|None=None;address:str|None=None;address_number:str|None=None;complement:str|None=None;district:str|None=None;city:str|None=None;state:str|None=None;bank_name:str|None=None;pix_key:str|None=None;notes:str|None=None
class SupplierUpdate(SupplierIn):active:bool|None=None
class SupplierOut(SupplierIn):
 id:int;active:bool
 class Config:from_attributes=True
def valid_type(value:str):
 if value not in {"product","service","both"}:raise HTTPException(422,"Tipo de fornecedor inválido.")
@router.get("",response_model=list[SupplierOut])
def listing(only_active:bool=False,db:Session=Depends(get_db),actor:User=Depends(get_current_user)):
 stmt=select(Supplier).where(Supplier.tenant_id==actor.tenant_id)
 if only_active:stmt=stmt.where(Supplier.active.is_(True))
 return db.scalars(stmt.order_by(Supplier.legal_name)).all()
@router.post("",response_model=SupplierOut,dependencies=[Depends(_STAFF)])
def create(data:SupplierIn,db:Session=Depends(get_db),actor:User=Depends(get_current_user)):
 valid_type(data.supplier_type)
 if actor.tenant_id is None:raise HTTPException(422,"Empresa não identificada.")
 row=Supplier(tenant_id=actor.tenant_id,**data.model_dump());db.add(row)
 try:db.flush()
 except IntegrityError:db.rollback();raise HTTPException(409,"Já existe fornecedor com este CPF/CNPJ.")
 log(db,user_id=actor.id,action="create",entity="supplier",entity_id=row.id);db.commit();db.refresh(row);return row
@router.put("/{supplier_id}",response_model=SupplierOut,dependencies=[Depends(_STAFF)])
def update(supplier_id:int,data:SupplierUpdate,db:Session=Depends(get_db),actor:User=Depends(get_current_user)):
 row=db.get(Supplier,supplier_id)
 if row is None:raise HTTPException(404,"Fornecedor não encontrado.")
 require_same_tenant(actor,row.tenant_id);updates=data.model_dump(exclude_unset=True);valid_type(updates.get("supplier_type",row.supplier_type));before=snapshot(row,list(updates))
 for key,value in updates.items():setattr(row,key,value)
 log_update(db,user_id=actor.id,entity="supplier",entity_id=row.id,before=before,obj=row,updates=updates);db.commit();db.refresh(row);return row
@router.delete("/{supplier_id}",dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL))])
def delete(supplier_id:int,db:Session=Depends(get_db),actor:User=Depends(get_current_user)):
 row=db.get(Supplier,supplier_id)
 if row is None:raise HTTPException(404,"Fornecedor não encontrado.")
 require_same_tenant(actor,row.tenant_id)
 if db.scalar(select(PurchaseTicket).where(PurchaseTicket.supplier_id==supplier_id)) or db.scalar(select(ServiceProvider).where(ServiceProvider.supplier_id==supplier_id)):raise HTTPException(409,"Fornecedor possui vínculos. Inative para preservar o histórico.")
 db.delete(row);log(db,user_id=actor.id,action="delete",entity="supplier",entity_id=supplier_id);db.commit();return {"deleted":supplier_id}

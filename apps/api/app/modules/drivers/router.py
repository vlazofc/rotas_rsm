from datetime import date
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import Role, has_all_environment_access, require_branch_access, require_roles
from app.core.config import settings
from app.db.models import Attachment, Branch, Carrier, Driver, DriverBranch, DriverSettings, Route, User
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services.audit import log, log_update, snapshot
from app.services.entity_status import StatusChangeIn, apply_status
from app.services import storage

router = APIRouter(prefix="/drivers", tags=["drivers"])

_MANAGER = require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL, Role.OPERADOR_LOGISTICO)


class DriverIn(BaseModel):
    branch_id: int
    branch_ids: list[int] = Field(default_factory=list)
    name: str
    document: str | None = None
    phone: str | None = None
    carrier: str | None = None
    carrier_id: int | None = None
    user_id: int | None = None
    email: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    birth_date: date | None = None
    cnh_number: str | None = None
    cnh_category: str | None = None
    cnh_expiry_date: date | None = None
    antt_number: str | None = None
    antt_expiry_date: date | None = None
    registration_updated_at: date | None = None
    employment_type: str = "proprio"
    daily_rate: float | None = None


class DriverUpdate(BaseModel):
    branch_id: int | None = None
    branch_ids: list[int] | None = None
    name: str | None = None
    document: str | None = None
    phone: str | None = None
    carrier: str | None = None
    carrier_id: int | None = None
    user_id: int | None = None
    active: bool | None = None
    email: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    birth_date: date | None = None
    cnh_number: str | None = None
    cnh_category: str | None = None
    cnh_expiry_date: date | None = None
    antt_number: str | None = None
    antt_expiry_date: date | None = None
    registration_updated_at: date | None = None
    employment_type: str | None = None
    daily_rate: float | None = None


class DriverOut(DriverIn):
    id: int
    active: bool
    blocked: bool = False
    status_reason: str | None = None
    document_url: str | None = None
    cnh_url: str | None = None
    cnh_status: str = "missing"
    antt_status: str = "not_applicable"
    registration_due_date: date | None = None
    registration_status: str = "missing"

    class Config:
        from_attributes = True

class DriverAccessOut(BaseModel):
    id: int
    name: str
    login: str | None = None
    tenant_id: int | None = None
    branch_id: int | None = None
    active: bool
    blocked: bool
    linked_driver_id: int | None = None

class DriverSettingsIn(BaseModel):
    cnh_alert_days:int=30
    antt_alert_days:int=30
    registration_renewal_months:int=12
    registration_alert_days:int=30
    statement_release_day:int=Field(default=1,ge=1,le=28)


def _settings(db:Session,tenant_id:int|None)->DriverSettings:
    if tenant_id is None: raise HTTPException(422,"Empresa não identificada.")
    row=db.scalar(select(DriverSettings).where(DriverSettings.tenant_id==tenant_id))
    if row is None:row=DriverSettings(tenant_id=tenant_id);db.add(row);db.flush()
    return row

def _deadline_status(value:date|None,alert_days:int,*,optional:bool=False)->str:
    if value is None:return "not_applicable" if optional else "missing"
    days=(value-date.today()).days
    return "expired" if days<0 else "warning" if days<=alert_days else "ok"

def _out(db:Session,driver:Driver,config:DriverSettings)->DriverOut:
    renewal=(driver.registration_updated_at+relativedelta(months=config.registration_renewal_months)) if driver.registration_updated_at else None
    branch_ids=list(db.scalars(select(DriverBranch.branch_id).where(DriverBranch.driver_id==driver.id)).all()) or [driver.branch_id]
    return DriverOut.model_validate({**driver.__dict__,"branch_ids":branch_ids,"document_url":storage.get_presigned_url(driver.document_attachment.bucket,driver.document_attachment.storage_key) if driver.document_attachment else None,"cnh_url":storage.get_presigned_url(driver.cnh_attachment.bucket,driver.cnh_attachment.storage_key) if driver.cnh_attachment else None,"cnh_status":_deadline_status(driver.cnh_expiry_date,config.cnh_alert_days),"antt_status":_deadline_status(driver.antt_expiry_date,config.antt_alert_days,optional=not bool(driver.antt_number)),"registration_due_date":renewal,"registration_status":_deadline_status(renewal,config.registration_alert_days)})

def _sync_branches(db:Session,driver:Driver,_branch_ids:list[int],_actor:User)->None:
    # Todos os motoristas ficam disponíveis em todas as filiais da própria empresa.
    # A filial principal permanece apenas para compatibilidade com dados históricos.
    primary=db.get(Branch,driver.branch_id)
    if primary is None or primary.tenant_id!=driver.tenant_id:
        raise HTTPException(422,"Filial principal inválida para a empresa do motorista.")
    ids=list(db.scalars(select(Branch.id).where(Branch.tenant_id==driver.tenant_id)).all())
    if not ids:raise HTTPException(422,"A empresa do motorista não possui filiais cadastradas.")
    db.query(DriverBranch).filter(DriverBranch.driver_id==driver.id).delete(synchronize_session=False)
    db.add_all([DriverBranch(driver_id=driver.id,branch_id=branch_id) for branch_id in ids])

def _validate_linked_user(db: Session, user_id: int | None, tenant_id: int | None, *, driver_id: int | None = None) -> None:
    if user_id is None:
        return
    linked_user = db.get(User, user_id)
    if linked_user is None or linked_user.tenant_id != tenant_id:
        raise HTTPException(status_code=422, detail="Usuário não pertence à empresa do motorista.")
    if linked_user.role != Role.MOTORISTA.value:
        raise HTTPException(status_code=422, detail="Selecione um usuário com perfil motorista.")
    existing = db.scalar(select(Driver).where(Driver.user_id == user_id, Driver.id != (driver_id or -1)))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Este acesso já está vinculado a outro motorista.")

@router.get("", response_model=list[DriverOut], dependencies=[Depends(_MANAGER)])
def list_drivers(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(Driver).order_by(Driver.name)
    if not has_all_environment_access(user) and user.tenant_id is not None:
        stmt = stmt.where(Driver.tenant_id == user.tenant_id)
    config=_settings(db,user.tenant_id);rows=db.scalars(stmt).all();db.commit();return [_out(db,row,config) for row in rows]


@router.get("/access-options", response_model=list[DriverAccessOut], dependencies=[Depends(_MANAGER)])
def list_driver_access_options(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    stmt = select(User).where(User.role == Role.MOTORISTA.value).order_by(User.name)
    if not has_all_environment_access(actor):
        stmt = stmt.where(User.tenant_id == actor.tenant_id)
    users = db.scalars(stmt).all()
    links = dict(db.execute(select(Driver.user_id, Driver.id).where(Driver.user_id.is_not(None))).all())
    return [DriverAccessOut(
        id=user.id, name=user.name, login=user.login, tenant_id=user.tenant_id, branch_id=user.branch_id,
        active=user.active, blocked=user.blocked, linked_driver_id=links.get(user.id),
    ) for user in users]


@router.post("", response_model=DriverOut, dependencies=[Depends(_MANAGER)])
def create_driver(data: DriverIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    branch = require_branch_access(db, actor, data.branch_id)
    if data.employment_type not in {"proprio", "agregado"}:
        raise HTTPException(422, "Vínculo do motorista inválido.")
    if data.carrier_id is not None:
        carrier = db.get(Carrier, data.carrier_id)
        if carrier is None or carrier.tenant_id != branch.tenant_id:
            raise HTTPException(status_code=422, detail="Transportadora não pertence à empresa da filial.")
    _validate_linked_user(db, data.user_id, branch.tenant_id)
    payload=data.model_dump(exclude={"branch_ids"})
    driver = Driver(tenant_id=branch.tenant_id, **payload)
    db.add(driver)
    db.flush()
    _sync_branches(db,driver,data.branch_ids or [data.branch_id],actor)
    log(db, user_id=actor.id, action="create", entity="driver", entity_id=driver.id)
    db.commit()
    db.refresh(driver)
    config = _settings(db, driver.tenant_id)
    db.commit()
    return _out(db,driver, config)


@router.get("/settings/alerts", response_model=DriverSettingsIn, dependencies=[Depends(_MANAGER)])
def get_driver_settings(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    row = _settings(db, actor.tenant_id)
    db.commit()
    return row


@router.put("/settings/alerts", response_model=DriverSettingsIn, dependencies=[Depends(_MANAGER)])
def update_driver_settings(data: DriverSettingsIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if not 1 <= data.cnh_alert_days <= 365 or not 1 <= data.antt_alert_days <= 365 or not 1 <= data.registration_alert_days <= 365 or not 1 <= data.registration_renewal_months <= 60:
        raise HTTPException(422, "Parâmetros de alerta fora dos limites permitidos.")
    row = _settings(db, actor.tenant_id)
    before = snapshot(row, list(data.model_fields))
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    log_update(db, user_id=actor.id, entity="driver_settings", entity_id=row.id, before=before, obj=row, updates=data.model_dump())
    db.commit()
    db.refresh(row)
    return row


@router.put("/{driver_id}", response_model=DriverOut, dependencies=[Depends(_MANAGER)])
def update_driver(driver_id: int, data: DriverUpdate,
                  db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    driver = db.get(Driver, driver_id)
    if driver is None:
        raise HTTPException(status_code=404, detail="Motorista não encontrado.")
    require_branch_access(db, actor, driver.branch_id)
    updates = data.model_dump(exclude_unset=True,exclude={"branch_ids"})
    if "active" in updates:
        raise HTTPException(422, "Use a ação de situação para ativar ou desativar o motorista.")
    employment_type = updates.get("employment_type", driver.employment_type)
    if employment_type not in {"proprio", "agregado"}:
        raise HTTPException(422, "Vínculo do motorista inválido.")
    if data.carrier_id is not None:
        carrier = db.get(Carrier, data.carrier_id)
        if carrier is None or carrier.tenant_id != driver.tenant_id:
            raise HTTPException(status_code=422, detail="Transportadora não pertence à empresa do motorista.")
    if "user_id" in updates:
        _validate_linked_user(db, data.user_id, driver.tenant_id, driver_id=driver.id)
    before = snapshot(driver, list(updates))
    for field, value in updates.items():
        setattr(driver, field, value)
    if data.branch_ids is not None:
        _sync_branches(db,driver,data.branch_ids,actor)
    log_update(db, user_id=actor.id, entity="driver", entity_id=driver.id, before=before, obj=driver, updates=updates)
    db.commit()
    db.refresh(driver)
    config = _settings(db, driver.tenant_id)
    db.commit()
    return _out(db,driver, config)

@router.post("/{driver_id}/status", response_model=DriverOut, dependencies=[Depends(_MANAGER)])
def change_driver_status(driver_id:int,data:StatusChangeIn,db:Session=Depends(get_db),actor:User=Depends(get_current_user)):
    driver=db.get(Driver,driver_id)
    if driver is None:raise HTTPException(404,"Motorista não encontrado.")
    require_branch_access(db,actor,driver.branch_id);apply_status(db,obj=driver,data=data,user_id=actor.id,entity="driver");db.commit();db.refresh(driver)
    config=_settings(db,driver.tenant_id);db.commit();return _out(db,driver,config)

async def _store_driver_file(file:UploadFile,driver:Driver,kind:str)->Attachment:
    allowed={"application/pdf","image/png","image/jpeg","image/jpg","image/webp"};content_type=file.content_type or "application/octet-stream"
    if content_type not in allowed:raise HTTPException(415,"Documento deve ser PDF, JPG, PNG ou WEBP.")
    content=await file.read()
    if not content:raise HTTPException(400,"Arquivo vazio.")
    if len(content)>settings.max_upload_mb*1024*1024:raise HTTPException(413,f"Arquivo acima de {settings.max_upload_mb} MB.")
    storage.ensure_buckets();filename=Path(file.filename or kind).name;key=f"motoristas/{driver.branch_id}/{driver.id}/{kind}-{uuid.uuid4().hex}-{filename}";storage.put_object(settings.minio_bucket_proofs,key,content,content_type);return Attachment(bucket=settings.minio_bucket_proofs,storage_key=key,content_type=content_type,size_bytes=len(content))

@router.post("/{driver_id}/documents",response_model=DriverOut,dependencies=[Depends(_MANAGER)])
async def upload_driver_documents(driver_id:int,document_photo:UploadFile|None=File(None),cnh_document:UploadFile|None=File(None),db:Session=Depends(get_db),actor:User=Depends(get_current_user)):
    driver=db.get(Driver,driver_id)
    if driver is None:raise HTTPException(404,"Motorista não encontrado.")
    require_branch_access(db,actor,driver.branch_id)
    if document_photo and document_photo.filename:
        attachment=await _store_driver_file(document_photo,driver,"documento");db.add(attachment);db.flush();driver.document_attachment_id=attachment.id
    if cnh_document and cnh_document.filename:
        attachment=await _store_driver_file(cnh_document,driver,"cnh");db.add(attachment);db.flush();driver.cnh_attachment_id=attachment.id
    log(db,user_id=actor.id,action="upload_documents",entity="driver",entity_id=driver.id,detail=f"documento={bool(document_photo and document_photo.filename)}; cnh={bool(cnh_document and cnh_document.filename)}")
    db.commit()
    db.refresh(driver)
    config = _settings(db, driver.tenant_id)
    db.commit()
    return _out(db,driver, config)


@router.delete("/{driver_id}", dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL))])
def delete_driver(driver_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    driver = db.get(Driver, driver_id)
    if driver is None:
        raise HTTPException(status_code=404, detail="Motorista não encontrado.")
    if db.scalar(select(Route).where(Route.driver_id == driver_id)):
        raise HTTPException(status_code=409, detail="Motorista possui rota atribuída. Inative para manter o histórico.")
    if driver.user_id is not None:
        raise HTTPException(status_code=409, detail="Motorista está vinculado a um usuário. Remova o vínculo antes de excluir.")
    name = driver.name
    db.delete(driver)
    log(db, user_id=actor.id, action="delete", entity="driver", entity_id=driver_id, detail=f'name: "{name}"')
    db.commit()
    return {"deleted": driver_id}

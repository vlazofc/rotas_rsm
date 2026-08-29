"""Checklist de veículo: catálogo configurável de itens + execução (saída/retorno/periódica).

O módulo mantém catálogo, execução e histórico dos itens inspecionados.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.permissions import Role, require_branch_access, require_roles
from app.db.models import ChecklistTemplateItem, Driver, Tire, TireInspection, User, Vehicle, VehicleChecklist, VehicleChecklistItem
from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.services.audit import log

router = APIRouter(prefix="/vehicle-checklist", tags=["vehicle-checklist"])

_MANAGER = require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL)
_EXECUTOR = require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL, Role.OPERADOR_LOGISTICO, Role.MOTORISTA)
ITEM_CATEGORIES = {"freios", "pneus", "eletrica", "documentacao", "fluidos", "seguranca", "outros"}
CHECKLIST_KINDS = {"saida", "retorno", "periodica"}
ITEM_STATUSES = {"ok", "nao_ok", "nao_aplicavel"}
OVERALL_STATUSES = {"aprovado", "aprovado_com_ressalvas", "reprovado"}


# ---------------------------------------------------------------------------
# Catálogo (template)
# ---------------------------------------------------------------------------

class TemplateItemIn(BaseModel):
    code: str
    label: str
    label_pt_br: str | None = None
    category: str = "outros"
    required: bool = True
    sort_order: int = 100


class TemplateItemUpdate(BaseModel):
    label: str | None = None
    label_pt_br: str | None = None
    category: str | None = None
    required: bool | None = None
    sort_order: int | None = None
    active: bool | None = None


class TemplateItemOut(BaseModel):
    id: int
    code: str
    label: str
    label_pt_br: str | None
    category: str
    required: bool
    sort_order: int
    active: bool

    class Config:
        from_attributes = True


@router.get("/template-items", response_model=list[TemplateItemOut])
def list_template_items(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(ChecklistTemplateItem).where(ChecklistTemplateItem.active.is_(True)).order_by(ChecklistTemplateItem.sort_order, ChecklistTemplateItem.label)
    return db.scalars(stmt).all()


@router.post("/template-items", response_model=TemplateItemOut, dependencies=[Depends(_MANAGER)])
def create_template_item(data: TemplateItemIn, db: Session = Depends(get_db)):
    if data.category not in ITEM_CATEGORIES:
        raise HTTPException(status_code=400, detail="Categoria inválida.")
    if db.scalar(select(ChecklistTemplateItem).where(ChecklistTemplateItem.code == data.code)):
        raise HTTPException(status_code=409, detail="Já existe um item com este código.")
    item = ChecklistTemplateItem(**data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/template-items/{item_id}", response_model=TemplateItemOut, dependencies=[Depends(_MANAGER)])
def update_template_item(item_id: int, data: TemplateItemUpdate, db: Session = Depends(get_db)):
    item = db.get(ChecklistTemplateItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    updates = data.model_dump(exclude_unset=True)
    if "category" in updates and updates["category"] not in ITEM_CATEGORIES:
        raise HTTPException(status_code=400, detail="Categoria inválida.")
    for field, value in updates.items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/template-items/{item_id}", dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL))])
def delete_template_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(ChecklistTemplateItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    item.active = False  # mantém histórico de checklists antigos referenciando o item
    db.commit()
    return {"deleted": item_id}


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------

class ChecklistItemIn(BaseModel):
    template_item_id: int
    status: str = "ok"
    notes: str | None = None

class TireMeasurementIn(BaseModel):
    tire_id: int
    tread_depth_mm: float

class TireMeasurementOut(TireMeasurementIn):
    fire_number: str | None = None
    position: str | None = None


class ChecklistIn(BaseModel):
    branch_id: int
    vehicle_id: int
    driver_id: int | None = None
    route_id: int | None = None
    kind: str = "periodica"
    performed_at: date
    notes: str | None = None
    items: list[ChecklistItemIn]
    tire_measurements: list[TireMeasurementIn] = []


class ChecklistItemOut(BaseModel):
    id: int
    template_item_id: int
    item_label: str | None = None
    status: str
    notes: str | None

    class Config:
        from_attributes = True


class ChecklistOut(BaseModel):
    id: int
    branch_id: int
    vehicle_id: int
    vehicle_plate: str | None = None
    driver_id: int | None
    driver_name: str | None = None
    route_id: int | None
    kind: str
    performed_at: date
    overall_status: str
    notes: str | None
    items: list[ChecklistItemOut] = []
    tire_measurements: list[TireMeasurementOut] = []

    class Config:
        from_attributes = True


def _serialize(checklist: VehicleChecklist) -> ChecklistOut:
    out = ChecklistOut.model_validate(checklist)
    out.vehicle_plate = checklist.vehicle.plate if checklist.vehicle else None
    out.driver_name = checklist.driver.name if checklist.driver else None
    out.items = [
        ChecklistItemOut(
            id=i.id, template_item_id=i.template_item_id,
            item_label=i.template_item.label_pt_br or i.template_item.label if i.template_item else None,
            status=i.status, notes=i.notes,
        )
        for i in checklist.items
    ]
    inspections = checklist_tire_inspections(checklist)
    out.tire_measurements = [TireMeasurementOut(tire_id=row.tire_id, tread_depth_mm=row.tread_depth_mm or 0, fire_number=row.tire.fire_number if row.tire else None, position=row.tire.position if row.tire else None) for row in inspections]
    return out

def checklist_tire_inspections(checklist: VehicleChecklist):
    db = Session.object_session(checklist)
    if db is None: return []
    return db.scalars(select(TireInspection).options(selectinload(TireInspection.tire)).where(TireInspection.checklist_id == checklist.id).order_by(TireInspection.id)).all()

def save_tire_measurements(db: Session, checklist: VehicleChecklist, measurements: list[TireMeasurementIn], actor_id: int):
    installed = db.scalars(select(Tire).where(Tire.vehicle_id == checklist.vehicle_id, Tire.status != "descartado")).all()
    installed_by_id = {tire.id:tire for tire in installed}
    supplied = {item.tire_id for item in measurements}
    if installed_by_id and supplied != set(installed_by_id):
        raise HTTPException(status_code=422, detail="Informe a profundidade do sulco de todos os pneus instalados.")
    if any(item.tread_depth_mm < 0 or item.tread_depth_mm > 30 for item in measurements):
        raise HTTPException(status_code=422, detail="A profundidade do sulco deve estar entre 0 e 30 mm.")
    db.query(TireInspection).filter(TireInspection.checklist_id == checklist.id).delete(synchronize_session=False)
    for item in measurements:
        tire=installed_by_id.get(item.tire_id)
        if tire is None: raise HTTPException(status_code=422, detail="Pneu não pertence ao veículo selecionado.")
        tire.tread_depth_mm=item.tread_depth_mm
        db.add(TireInspection(tire_id=tire.id, checklist_id=checklist.id, inspected_at=checklist.performed_at, tread_depth_mm=item.tread_depth_mm, notes="Medição registrada pelo checklist do veículo.", recorded_by=actor_id))


def _overall_status(items: list[ChecklistItemIn], template_by_id: dict[int, ChecklistTemplateItem]) -> str:
    has_required_fail = any(
        i.status == "nao_ok" and template_by_id.get(i.template_item_id) and template_by_id[i.template_item_id].required
        for i in items
    )
    has_any_fail = any(i.status == "nao_ok" for i in items)
    if has_required_fail:
        return "reprovado"
    if has_any_fail:
        return "aprovado_com_ressalvas"
    return "aprovado"


@router.get("", response_model=list[ChecklistOut])
def list_checklists(vehicle_id: int | None = None, route_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(VehicleChecklist).options(
        selectinload(VehicleChecklist.items).selectinload(VehicleChecklistItem.template_item),
        selectinload(VehicleChecklist.vehicle), selectinload(VehicleChecklist.driver),
    ).order_by(VehicleChecklist.performed_at.desc(), VehicleChecklist.id.desc())
    if user.role != Role.ADMIN_GLOBAL.value and user.branch_id:
        stmt = stmt.where(VehicleChecklist.branch_id == user.branch_id)
    if vehicle_id:
        stmt = stmt.where(VehicleChecklist.vehicle_id == vehicle_id)
    if route_id:
        stmt = stmt.where(VehicleChecklist.route_id == route_id)
    return [_serialize(c) for c in db.scalars(stmt).all()]


@router.post("", response_model=ChecklistOut, dependencies=[Depends(_EXECUTOR)])
def create_checklist(data: ChecklistIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    require_branch_access(db, actor, data.branch_id)
    if data.kind not in CHECKLIST_KINDS:
        raise HTTPException(status_code=400, detail="Tipo de checklist inválido.")
    if db.get(Vehicle, data.vehicle_id) is None:
        raise HTTPException(status_code=404, detail="Veículo não encontrado.")
    if data.driver_id is not None and db.get(Driver, data.driver_id) is None:
        raise HTTPException(status_code=404, detail="Motorista não encontrado.")
    if not data.items:
        raise HTTPException(status_code=400, detail="Informe ao menos um item de checklist.")

    template_ids = {i.template_item_id for i in data.items}
    templates = db.scalars(select(ChecklistTemplateItem).where(ChecklistTemplateItem.id.in_(template_ids))).all()
    template_by_id = {t.id: t for t in templates}
    if len(template_by_id) != len(template_ids):
        raise HTTPException(status_code=404, detail="Um ou mais itens de checklist não foram encontrados.")
    for item in data.items:
        if item.status not in ITEM_STATUSES:
            raise HTTPException(status_code=400, detail="Status de item inválido.")

    checklist = VehicleChecklist(
        branch_id=data.branch_id, vehicle_id=data.vehicle_id, driver_id=data.driver_id, route_id=data.route_id,
        kind=data.kind, performed_at=data.performed_at, notes=data.notes,
        overall_status=_overall_status(data.items, template_by_id), performed_by=actor.id,
    )
    db.add(checklist)
    db.flush()
    for item in data.items:
        db.add(VehicleChecklistItem(checklist_id=checklist.id, template_item_id=item.template_item_id, status=item.status, notes=item.notes))
    save_tire_measurements(db, checklist, data.tire_measurements, actor.id)
    log(db, user_id=actor.id, action="create", entity="vehicle_checklist", entity_id=checklist.id, detail=f"status={checklist.overall_status}")
    db.commit()
    db.refresh(checklist)
    return _serialize(checklist)

@router.put("/{checklist_id}", response_model=ChecklistOut, dependencies=[Depends(_MANAGER)])
def update_checklist(checklist_id: int, data: ChecklistIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    checklist = db.scalar(select(VehicleChecklist).options(selectinload(VehicleChecklist.items)).where(VehicleChecklist.id == checklist_id))
    if checklist is None: raise HTTPException(status_code=404, detail="Checklist não encontrado.")
    require_branch_access(db, actor, checklist.branch_id)
    if data.branch_id != checklist.branch_id: raise HTTPException(status_code=403, detail="Não é permitido mover o checklist para outra filial.")
    if data.kind not in CHECKLIST_KINDS: raise HTTPException(status_code=400, detail="Tipo de checklist inválido.")
    vehicle = db.get(Vehicle, data.vehicle_id)
    if vehicle is None: raise HTTPException(status_code=404, detail="Veículo não encontrado.")
    if data.driver_id is not None and db.get(Driver, data.driver_id) is None: raise HTTPException(status_code=404, detail="Motorista não encontrado.")
    if not data.items: raise HTTPException(status_code=400, detail="Informe ao menos um item de checklist.")
    template_ids = {item.template_item_id for item in data.items}
    templates = db.scalars(select(ChecklistTemplateItem).where(ChecklistTemplateItem.id.in_(template_ids))).all()
    template_by_id = {item.id: item for item in templates}
    if len(template_by_id) != len(template_ids): raise HTTPException(status_code=404, detail="Um ou mais itens de checklist não foram encontrados.")
    if any(item.status not in ITEM_STATUSES for item in data.items): raise HTTPException(status_code=400, detail="Status de item inválido.")
    checklist.vehicle_id, checklist.driver_id, checklist.route_id = data.vehicle_id, data.driver_id, data.route_id
    checklist.kind, checklist.performed_at, checklist.notes = data.kind, data.performed_at, data.notes
    checklist.overall_status = _overall_status(data.items, template_by_id)
    checklist.items.clear()
    for item in data.items:
        checklist.items.append(VehicleChecklistItem(template_item_id=item.template_item_id, status=item.status, notes=item.notes))
    save_tire_measurements(db, checklist, data.tire_measurements, actor.id)
    log(db, user_id=actor.id, action="update", entity="vehicle_checklist", entity_id=checklist.id, detail=f"status={checklist.overall_status}")
    db.commit(); db.refresh(checklist); return _serialize(checklist)


@router.delete("/{checklist_id}", dependencies=[Depends(_MANAGER)])
def delete_checklist(checklist_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    checklist = db.get(VehicleChecklist, checklist_id)
    if checklist is None:
        raise HTTPException(status_code=404, detail="Checklist não encontrado.")
    require_branch_access(db, actor, checklist.branch_id)
    db.delete(checklist)
    log(db, user_id=actor.id, action="delete", entity="vehicle_checklist", entity_id=checklist_id)
    db.commit()
    return {"deleted": checklist_id}

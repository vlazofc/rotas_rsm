"""Configurações das obrigatoriedades operacionais."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.permissions import Role, require_roles
from app.db.models import OperationalSettings, User
from app.db.session import get_db
from app.services.audit import log_update, snapshot

router = APIRouter(prefix="/operational-settings", tags=["operational-settings"])


class OperationalSettingsIn(BaseModel):
    require_manual_justification: bool = True
    require_checkin_before_delivery: bool = True
    require_delivery_proof: bool = True
    require_failure_proof: bool = True
    require_warehouse_return_proof: bool = True
    require_failure_reason: bool = True
    require_returned_quantity: bool = True


class OperationalSettingsOut(OperationalSettingsIn):
    pass


FIELDS = list(OperationalSettingsIn.model_fields)


def get_or_create_operational_settings(db: Session) -> OperationalSettings:
    row = db.get(OperationalSettings, 1)
    if row is None:
        row = OperationalSettings(id=1)
        db.add(row)
        db.flush()
    return row


def serialize_operational_settings(row: OperationalSettings) -> OperationalSettingsOut:
    return OperationalSettingsOut(**{field: bool(getattr(row, field)) for field in FIELDS})


@router.get("", response_model=OperationalSettingsOut)
def get_operational_settings(db: Session = Depends(get_db)):
    return serialize_operational_settings(get_or_create_operational_settings(db))


@router.put("", response_model=OperationalSettingsOut)
def update_operational_settings(
    data: OperationalSettingsIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(Role.ADMIN_GLOBAL)),
):
    row = get_or_create_operational_settings(db)
    before = snapshot(row, FIELDS)
    for field in FIELDS:
        setattr(row, field, getattr(data, field))
    log_update(db, user_id=actor.id, entity="operational_settings", entity_id=row.id, before=before, obj=row, updates=data.model_dump())
    db.commit()
    db.refresh(row)
    return serialize_operational_settings(row)

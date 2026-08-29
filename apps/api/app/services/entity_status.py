from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.services.audit import log_update, snapshot


class StatusChangeIn(BaseModel):
    action: str
    reason: str | None = None


def apply_status(db: Session, *, obj, data: StatusChangeIn, user_id: int, entity: str) -> None:
    if data.action not in {"activate", "deactivate", "block", "unblock"}:
        raise HTTPException(422, "Ação de situação inválida.")
    reason = (data.reason or "").strip()
    if data.action in {"deactivate", "block"} and len(reason) < 10:
        raise HTTPException(422, "Informe um motivo com pelo menos 10 caracteres.")
    before = snapshot(obj, ["active", "blocked", "status_reason"])
    if data.action == "activate":
        obj.active, obj.blocked, obj.status_reason = True, False, None
    elif data.action == "deactivate":
        obj.active, obj.blocked, obj.status_reason = False, False, reason
    elif data.action == "block":
        obj.active, obj.blocked, obj.status_reason = False, True, reason
    else:
        obj.active, obj.blocked, obj.status_reason = True, False, None
    updates = {"active": obj.active, "blocked": obj.blocked, "status_reason": obj.status_reason}
    log_update(db, user_id=user_id, entity=entity, entity_id=obj.id,
               before=before, obj=obj, updates=updates)

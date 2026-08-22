from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import Role, require_roles
from app.db.models import AuditLog, User
from app.db.session import get_db
from app.modules.auth.deps import get_current_user

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("",
            dependencies=[Depends(require_roles(Role.ADMIN_GLOBAL, Role.GESTOR_BRASIL, Role.AUDITOR))])
def list_audit(limit: int = 200, entity: str | None = None, action: str | None = None,
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = select(AuditLog, User.name, User.email).join(User, User.id == AuditLog.user_id, isouter=True)
    if user.role != Role.ADMIN_GLOBAL.value:
        query = query.where(AuditLog.tenant_id == user.tenant_id)
    if entity:
        query = query.where(AuditLog.entity == entity)
    if action:
        query = query.where(AuditLog.action == action)
    query = query.order_by(AuditLog.created_at.desc()).limit(limit)
    rows = db.execute(query).all()
    return [
        {
            "id": r.AuditLog.id, "user_id": r.AuditLog.user_id,
            "user_name": r.name, "user_email": r.email,
            "action": r.AuditLog.action, "entity": r.AuditLog.entity,
            "entity_id": r.AuditLog.entity_id, "detail": r.AuditLog.detail,
            "ip": r.AuditLog.ip, "created_at": r.AuditLog.created_at,
        }
        for r in rows
    ]

"""Registro de auditoria (acesso e alteração)."""
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models import AuditLog


def log(
    db: Session,
    *,
    user_id: int | None,
    action: str,
    entity: str,
    entity_id: str | int | None = None,
    detail: str | None = None,
    ip: str | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity=entity,
            entity_id=str(entity_id) if entity_id is not None else None,
            detail=detail,
            ip=ip,
        )
    )
    db.flush()


def snapshot(obj, fields: list[str]) -> dict[str, object]:
    return {field: getattr(obj, field) for field in fields}


def changed_fields(before: dict[str, object], obj, updates: dict[str, object]) -> dict[str, tuple[object, object]]:
    changes: dict[str, tuple[object, object]] = {}
    for field in updates:
        old = before.get(field)
        new = getattr(obj, field)
        if old != new:
            changes[field] = (old, new)
    return changes


def format_changes(changes: dict[str, tuple[object, object]]) -> str | None:
    if not changes:
        return None
    return "; ".join(
        f'{field}: "{_audit_value(old)}" -> "{_audit_value(new)}"'
        for field, (old, new) in changes.items()
    )


def log_update(
    db: Session,
    *,
    user_id: int | None,
    entity: str,
    entity_id: str | int | None,
    before: dict[str, object],
    obj,
    updates: dict[str, object],
) -> None:
    detail = format_changes(changed_fields(before, obj, updates))
    if detail:
        log(db, user_id=user_id, action="update", entity=entity, entity_id=entity_id, detail=detail)


def _audit_value(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "Sim" if value else "Não"
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, list):
        return ", ".join(_audit_value(item) for item in value)
    return str(value)

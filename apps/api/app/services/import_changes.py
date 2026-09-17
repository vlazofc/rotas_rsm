"""Transactional confirmation and audit for spreadsheet overwrites."""
import json

from sqlalchemy import inspect

from app.services.audit import log


class ImportConfirmationRequired(Exception):
    def __init__(self, changes):
        self.changes = changes
        super().__init__("A planilha altera registros existentes.")


def snapshot_import(obj):
    if obj is None:
        return None
    return {column.key: getattr(obj, column.key) for column in inspect(obj).mapper.column_attrs}


def collect_changes(changes, before, obj, route_code):
    if before is None:
        return
    for field, old in before.items():
        new = getattr(obj, field)
        if field in {"updated_at", "created_at", "raw_import_json"} or old == new:
            continue
        changes.append({"route": str(route_code), "entity": obj.__tablename__,
                        "entity_id": obj.id, "field": field,
                        "old": None if old is None else str(old),
                        "new": None if new is None else str(new)})


def authorize_changes(db, changes, *, confirmed, user_id):
    if changes and (not confirmed or user_id is None):
        raise ImportConfirmationRequired(changes)
    for change in changes:
        log(db, user_id=user_id, action="import_overwrite", entity=change["entity"],
            entity_id=change["entity_id"],
            detail=json.dumps({"authorization": "Sobreposição autorizada na importação", **change}, ensure_ascii=False))

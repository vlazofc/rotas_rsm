"""One-off, narrowly scoped removal requested for the legacy MRD administrator."""
import json
from datetime import datetime, timezone
from sqlalchemy import inspect, text
from app.db.session import engine, SessionLocal

engine.echo = False
SOURCE = "admin@mrdtransportes.com.br"
TARGET = "admin@jmdistribuicao.com.br"
BACKUP = "/tmp/admin-mrdtransportes-deleted.json"

def rows(db, sql, params):
    return [dict(row) for row in db.execute(text(sql), params).mappings().all()]

with SessionLocal() as db:
    source = db.execute(text("select * from users where lower(email)=lower(:email)"), {"email": SOURCE}).mappings().one_or_none()
    target = db.execute(text("select id, email from users where lower(email)=lower(:email)"), {"email": TARGET}).mappings().one_or_none()
    if source is None:
        raise SystemExit("Source user not found; no changes made")
    if target is None:
        raise SystemExit("Replacement administrator not found; no changes made")
    source_id, target_id = source["id"], target["id"]
    inspector = inspect(engine)
    references = []
    for table in inspector.get_table_names():
        for fk in inspector.get_foreign_keys(table):
            if fk.get("referred_table") != "users": continue
            for column in fk["constrained_columns"]:
                found = rows(db, f'SELECT * FROM "{table}" WHERE "{column}"=:id', {"id": source_id})
                if found: references.append({"table": table, "column": column, "rows": found})
    conversation_ids = [row["id"] for ref in references if ref["table"] == "executive_ai_conversations" for row in ref["rows"]]
    conversation_messages = rows(db, 'SELECT * FROM executive_ai_messages WHERE conversation_id = ANY(:ids)', {"ids": conversation_ids}) if conversation_ids else []
    with open(BACKUP, "w", encoding="utf-8") as handle:
        json.dump({"deleted_at": datetime.now(timezone.utc), "user": dict(source), "references": references,
                   "executive_ai_messages": conversation_messages}, handle, ensure_ascii=False, indent=2, default=str)

    # Dados pessoais e preferências não têm utilidade sem o usuário.
    if conversation_ids:
        db.execute(text('DELETE FROM executive_ai_messages WHERE conversation_id = ANY(:ids)'), {"ids": conversation_ids})
    for table in ("executive_ai_conversations", "alert_dismissals", "notifications", "alert_rules",
                  "legal_consents", "app_permission_consents", "gps_positions"):
        if table in inspector.get_table_names():
            db.execute(text(f'DELETE FROM "{table}" WHERE user_id=:id'), {"id": source_id})

    # Registros operacionais e auditoria permanecem; referências opcionais são anonimizadas.
    for ref in references:
        table, column = ref["table"], ref["column"]
        if table in {"executive_ai_conversations", "alert_dismissals", "notifications", "alert_rules",
                     "legal_consents", "app_permission_consents", "gps_positions"}: continue
        nullable = next(item["nullable"] for item in inspector.get_columns(table) if item["name"] == column)
        if nullable:
            db.execute(text(f'UPDATE "{table}" SET "{column}"=NULL WHERE "{column}"=:id'), {"id": source_id})
        elif table == "workflow_tasks" and column == "requester_id":
            db.execute(text('UPDATE workflow_tasks SET requester_id=:target WHERE requester_id=:id'), {"target": target_id, "id": source_id})
        else:
            raise RuntimeError(f"Unmanaged required reference: {table}.{column}")
    db.execute(text("DELETE FROM users WHERE id=:id"), {"id": source_id})
    db.commit()
    print(json.dumps({"deleted_user_id": source_id, "replacement_user_id": target_id,
                      "reference_groups": len(references), "backup": BACKUP}))

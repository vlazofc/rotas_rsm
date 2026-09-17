from sqlalchemy import inspect, text
from app.db.session import engine, SessionLocal
engine.echo = False

EMAIL = "admin@mrdtransportes.com.br"
with SessionLocal() as db:
    user = db.execute(text("select id, name, email, role, tenant_id, branch_id from users where lower(email)=lower(:email)"), {"email": EMAIL}).mappings().first()
    print("USER", dict(user) if user else None)
    if user:
        for table in inspect(engine).get_table_names():
            for fk in inspect(engine).get_foreign_keys(table):
                if fk.get("referred_table") != "users":
                    continue
                for column in fk["constrained_columns"]:
                    count = db.execute(text(f'SELECT count(*) FROM "{table}" WHERE "{column}"=:id'), {"id": user["id"]}).scalar_one()
                    if count:
                        nullable = next(c["nullable"] for c in inspect(engine).get_columns(table) if c["name"] == column)
                        print("REF", table, column, count, "nullable=" + str(nullable), "ondelete=" + str(fk.get("options", {}).get("ondelete")))

from sqlalchemy import inspect, text
from sqlalchemy.sql.sqltypes import String, Text
from app.db.session import engine, SessionLocal

engine.echo = False
DOMAIN = "%mrdtransportes.com.br%"
inspector = inspect(engine)
with SessionLocal() as db:
    for table in inspector.get_table_names():
        for column in inspector.get_columns(table):
            if not isinstance(column["type"], (String, Text)):
                continue
            count = db.execute(text(f'SELECT count(*) FROM "{table}" WHERE CAST("{column["name"]}" AS text) ILIKE :domain'), {"domain": DOMAIN}).scalar_one()
            if count:
                print("MATCH", table, column["name"], count)

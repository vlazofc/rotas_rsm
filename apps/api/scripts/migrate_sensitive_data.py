"""Migra dados pessoais entre texto puro e criptografia transparente.

Sem opção, apenas informa quantos valores ainda estão em texto puro.
Use --apply para criptografar e --decrypt somente em recuperação controlada.
"""
from __future__ import annotations

import argparse

from sqlalchemy import text

from app.core.encrypted_types import PREFIX, decrypt_value, encrypt_value
from app.db.session import engine


FIELDS = {
    "tenants": ("document", "phone", "email", "antt_number"),
    "users": ("email", "login"),
    "drivers": ("document", "phone", "email", "address", "postal_code", "cnh_number", "antt_number"),
    "vehicle_owners": ("document", "phone", "email", "bank_agency", "bank_account", "pix_key"),
    "vehicles": ("renavam", "chassis", "antt_number"),
    "vehicle_change_requests": ("requested_renavam", "previous_renavam"),
}


def migrate(*, apply: bool, decrypt: bool) -> dict[str, int]:
    counts = {"plaintext": 0, "encrypted": 0, "changed": 0}
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(824691357)"))
        duplicates = connection.execute(text("""
            SELECT lower(email), count(*) FROM users GROUP BY lower(email) HAVING count(*) > 1
        """)).all()
        if duplicates:
            raise RuntimeError("Existem e-mails duplicados sem diferenciar maiúsculas/minúsculas.")

        for table, columns in FIELDS.items():
            exists = connection.scalar(text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name=:table)"
            ), {"table": table})
            if not exists:
                continue
            for column in columns:
                column_exists = connection.scalar(text(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name=:table AND column_name=:column)"
                ), {"table": table, "column": column})
                if not column_exists:
                    continue
                if apply:
                    connection.execute(text(f'ALTER TABLE "{table}" ALTER COLUMN "{column}" TYPE TEXT USING "{column}"::text'))
                rows = connection.execute(text(
                    f'SELECT id, "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL AND "{column}" <> :empty'
                ), {"empty": ""}).all()
                context = f"{table}.{column}"
                for row_id, stored in rows:
                    protected = stored.startswith(PREFIX)
                    counts["encrypted" if protected else "plaintext"] += 1
                    replacement = None
                    if apply and not protected:
                        value = stored.lower() if table == "users" and column in {"email", "login"} else stored
                        replacement = encrypt_value(value, context)
                    elif decrypt and protected:
                        replacement = decrypt_value(stored, context)
                    if replacement is not None:
                        connection.execute(text(
                            f'UPDATE "{table}" SET "{column}"=:value WHERE id=:id'
                        ), {"value": replacement, "id": row_id})
                        counts["changed"] += 1
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--apply", action="store_true", help="Criptografa os valores ainda em texto puro")
    action.add_argument("--decrypt", action="store_true", help="Descriptografa para recuperação controlada")
    args = parser.parse_args()
    result = migrate(apply=args.apply, decrypt=args.decrypt)
    print(" ".join(f"{key}={value}" for key, value in result.items()))

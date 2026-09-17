#!/bin/sh
set -eu

TEST_DB="rotas_encryption_test_20260913"
BACKUP="/backups/admmendes_rotas_20260913_191146.sql.gz"

cleanup() {
  docker exec rotas_postgres dropdb -U rene_rotas --if-exists "${TEST_DB}" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

cleanup
docker exec rotas_postgres createdb -U rene_rotas "${TEST_DB}"
docker exec rotas_backup gzip -dc "${BACKUP}" \
  | sed '/^\\restrict /d; /^\\unrestrict /d' \
  | docker exec -i rotas_postgres psql -v ON_ERROR_STOP=1 -U rene_rotas -d "${TEST_DB}" >/dev/null

docker run --rm --network admmendes-rotas_internal --env-file .env \
  -e TEST_DB="${TEST_DB}" adimax-encryption-test sh -c '
    set -eu
    export PYTHONPATH=/app
    export DATABASE_URL="${DATABASE_URL%/*}/${TEST_DB}"
    python scripts/migrate_sensitive_data.py
    python scripts/migrate_sensitive_data.py --apply
    python scripts/migrate_sensitive_data.py
    python -c "from app.db.session import SessionLocal; from app.db.models import User,Driver,Vehicle; s=SessionLocal(); assert s.query(User).count() >= 1; list(s.query(User).all()); list(s.query(Driver).all()); list(s.query(Vehicle).all()); s.close(); print(\"ORM_DECRYPT_OK\")"
  '

plaintext_users=$(docker exec rotas_postgres psql -v ON_ERROR_STOP=1 -U rene_rotas -d "${TEST_DB}" -Atc \
  "SELECT count(*) FROM users WHERE email NOT LIKE 'enc:v1:%'")
test "${plaintext_users}" = "0"
echo "RAW_ENCRYPTION_OK"

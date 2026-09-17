#!/bin/sh
set -eu

i=0
state=""
while [ "${i}" -lt 6 ]; do
  state=$(docker inspect -f '{{.State.Health.Status}}' rotas_api 2>/dev/null || true)
  [ "${state}" = "healthy" ] && break
  i=$((i + 1))
  sleep 5
done
echo "API_HEALTH=${state}"
test "${state}" = "healthy"
curl -fsS http://127.0.0.1:8001/health
echo

docker exec rotas_api python -c "from sqlalchemy import select; from app.db.session import SessionLocal; from app.db.models import User, Driver, Vehicle; s=SessionLocal(); u=s.scalar(select(User).where(User.email == 'caio.haddad@adimax.com.br')); assert u and u.email == 'caio.haddad@adimax.com.br'; assert all(not (d.document or '').startswith('enc:v1:') for d in s.scalars(select(Driver))); assert all(not (v.renavam or '').startswith('enc:v1:') for v in s.scalars(select(Vehicle))); s.close(); print('TRANSPARENT_READ_AND_LOOKUP_OK')"

docker run --rm --network admmendes-rotas_internal --env-file .env -e PYTHONPATH=/app \
  admmendes-rotas-api python scripts/migrate_sensitive_data.py 2>/dev/null | tail -1

if docker logs --tail 50 rotas_api 2>&1 | grep -Eiq 'error|traceback|critical'; then
  docker logs --tail 50 rotas_api 2>&1 | grep -Ei 'error|traceback|critical'
  exit 1
fi

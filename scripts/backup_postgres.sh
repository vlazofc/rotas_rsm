#!/bin/sh
# Backup diário do PostgreSQL (executado pelo serviço "backup").
set -e

TS=$(date +%Y%m%d_%H%M%S)
OUT="/backups/admmendes_rotas_${TS}.sql.gz"

export PGPASSWORD="${POSTGRES_PASSWORD}"
pg_dump -h postgres -U "${POSTGRES_USER}" "${POSTGRES_DB}" | gzip > "${OUT}"
echo "Backup criado: ${OUT}"

# Retenção: mantém últimos 14 dias
find /backups -name "admmendes_rotas_*.sql.gz" -mtime +14 -delete
find /backups -name "jm_rotas_*.sql.gz" -mtime +14 -delete

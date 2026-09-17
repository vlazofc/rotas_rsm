#!/bin/sh
# Backup diário do PostgreSQL (executado pelo serviço "backup").
set -e
umask 077

TS=$(date +%Y%m%d_%H%M%S)
OUT="/backups/admmendes_rotas_${TS}.sql.gz"
TMP="${OUT}.tmp"
trap 'rm -f -- "${TMP}"' EXIT INT TERM

DB_URL="postgresql://${DATABASE_URL#postgresql+psycopg://}"
pg_dump "${DB_URL}" | gzip > "${TMP}"
gzip -t "${TMP}"
mv "${TMP}" "${OUT}"
trap - EXIT INT TERM
echo "Backup criado: ${OUT}"

# Retenção: mantém últimos 14 dias
find /backups -name "admmendes_rotas_*.sql.gz" -mtime +14 -delete
find /backups -name "jm_rotas_*.sql.gz" -mtime +14 -delete

#!/bin/sh
# Restaura um dump. Uso: sh restore_postgres.sh /backups/admmendes_rotas_XXXX.sql.gz
set -e

FILE="$1"
[ -z "$FILE" ] && echo "Uso: restore_postgres.sh <arquivo.sql.gz>" && exit 1
[ ! -f "$FILE" ] && echo "Arquivo de backup não encontrado." && exit 1
gzip -t "$FILE"

export PGPASSWORD="${POSTGRES_PASSWORD}"
gunzip -c "$FILE" | psql -v ON_ERROR_STOP=1 -h postgres -U "${POSTGRES_USER}" "${POSTGRES_DB}"
echo "Restaurado de: $FILE"

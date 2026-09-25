#!/bin/sh
set -eu

SOURCE="${1:-}"
[ -n "${SOURCE}" ] || { echo "Uso: restore_minio.sh /backups/minio/AAAAMMDD_HHMMSS" >&2; exit 1; }
[ -f "${SOURCE}/BACKUP_COMPLETE" ] || { echo "Backup MinIO incompleto ou inexistente." >&2; exit 1; }

mc alias set target "http://minio:9000" "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}" >/dev/null
for bucket in comprovantes custom; do
  if [ -d "${SOURCE}/${bucket}" ]; then
    mc mb --ignore-existing "target/${bucket}" >/dev/null
    mc mirror --overwrite --preserve "${SOURCE}/${bucket}" "target/${bucket}" >/dev/null
  fi
done
echo "MinIO restaurado de: ${SOURCE}"

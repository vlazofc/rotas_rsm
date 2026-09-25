#!/bin/sh
set -eu
umask 077

TS=$(date +%Y%m%d_%H%M%S)
DEST="/backups/minio/${TS}"
TMP="${DEST}.tmp"
trap 'rm -rf -- "${TMP}"' EXIT INT TERM

attempt=0
until mc alias set source "http://minio:9000" "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}" >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "${attempt}" -ge 12 ]; then
    echo "MinIO indisponível após ${attempt} tentativas." >&2
    exit 1
  fi
  sleep 5
done
mkdir -p "${TMP}"
for bucket in comprovantes custom; do
  if mc stat "source/${bucket}" >/dev/null 2>&1; then
    mkdir -p "${TMP}/${bucket}"
    mc mirror --overwrite --preserve "source/${bucket}" "${TMP}/${bucket}" >/dev/null
  fi
done
printf '%s\n' "${TS}" > "${TMP}/BACKUP_COMPLETE"
mv "${TMP}" "${DEST}"
trap - EXIT INT TERM

echo "Backup MinIO criado: ${DEST}"

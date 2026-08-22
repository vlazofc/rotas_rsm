#!/bin/bash
# Deploy / atualização na VPS Hostinger.
set -e

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "Crie o .env a partir do .env.example antes de subir."
  echo "  cp .env.example .env && nano .env"
  exit 1
fi

echo "==> git pull (se for repositório)"
git pull --ff-only 2>/dev/null || echo "(sem git remoto, seguindo)"

echo "==> build + up"
docker compose --profile cloudflare -f docker-compose.yml up -d --build

echo "==> status"
docker compose ps
echo "Logs da API:  docker compose logs -f api"

#!/bin/bash
# Preparação inicial da VPS Hostinger (Ubuntu/Debian). Rode como root.
set -e

apt update && apt upgrade -y

# Docker, se ainda não vier na imagem
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi

# Usuário de deploy
if ! id deploy >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" deploy
  usermod -aG docker deploy
fi

echo "Servidor preparado. Próximo passo (como deploy):"
echo "  git clone <repo> rotas-admmendes && cd rotas-admmendes"
echo "  cp .env.example .env && nano .env"
echo "  sh scripts/deploy.sh"

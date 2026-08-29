#!/bin/sh
set -eu

if git ls-files --error-unmatch .env >/dev/null 2>&1; then
  echo "ERRO: .env está versionado no Git."
  exit 1
fi

tracked_secrets=$(git ls-files | grep -E '(^|/)(\.env|id_rsa|id_ed25519|.*\.(pem|p12|pfx|key))$' || true)
if [ -n "$tracked_secrets" ]; then
  echo "ERRO: arquivo potencialmente secreto encontrado no índice Git:"
  echo "$tracked_secrets"
  exit 1
fi

echo "Verificação de arquivos secretos concluída."

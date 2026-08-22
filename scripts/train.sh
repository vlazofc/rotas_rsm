#!/bin/bash
# ============================================================
# Treina/atualiza a IA do manifesto e a base de conhecimento.
#
# Faz, em sequência:
#   1) Atualiza a base a partir do BANCO (conferências dos operadores)
#   2) Reconstrói o dataset de treino (dataset.jsonl)
#   3) Gera o Modelfile (base de conhecimento embutida)
#   4) Cria/atualiza o modelo 'admmendes-manifesto' no Ollama (se ativo)
#
# Uso (no servidor, na pasta do projeto):
#   sh scripts/train.sh                  # base = OCR_LLM_MODEL do .env, ou llama3.1:8b
#   sh scripts/train.sh --include-auto   # inclui também rotas geradas automaticamente
# ============================================================
set -e

cd "$(dirname "$0")/.."

OLLAMA_CT=rotas_ollama
OCR_SVC=ocr-worker
TRAIN_DIR=knowledge_base/training
MODELFILE_HOST=apps/ocr-worker/knowledge_base/training/Modelfile
MODEL_NAME=admmendes-manifesto

echo "==> 1/4  Exportando conferências do banco para a base de conhecimento"
docker compose exec -T $OCR_SVC python $TRAIN_DIR/export_training_data.py "$@"

echo "==> 2/4  Reconstruindo o dataset de treino"
docker compose exec -T $OCR_SVC python $TRAIN_DIR/build_dataset.py

echo "==> 3/4  Gerando o Modelfile (base de conhecimento embutida)"
docker compose exec -T $OCR_SVC python $TRAIN_DIR/build_modelfile.py

echo "==> 4/4  Atualizando o modelo no Ollama"
if docker ps --format '{{.Names}}' | grep -q "^${OLLAMA_CT}$"; then
  BASE_MODEL=$(grep -E '^OCR_LLM_MODEL=' .env 2>/dev/null | cut -d= -f2)
  BASE_MODEL=${BASE_MODEL:-llama3.1:8b}
  echo "    - garantindo modelo base ($BASE_MODEL) baixado"
  docker exec $OLLAMA_CT ollama pull "$BASE_MODEL" || true
  echo "    - copiando Modelfile para o Ollama"
  docker cp "$MODELFILE_HOST" ${OLLAMA_CT}:/root/Modelfile
  echo "    - criando/atualizando o modelo '$MODEL_NAME'"
  docker exec $OLLAMA_CT ollama create $MODEL_NAME -f /root/Modelfile
  echo ""
  echo "OK! Modelo '$MODEL_NAME' atualizado."
  echo "Para usá-lo, no .env defina:  EXTRACTOR=llm  e  OCR_LLM_MODEL=$MODEL_NAME"
  echo "Depois:  docker compose up -d ocr-worker"
else
  echo "    Ollama não está ativo — etapas 1-3 concluídas (base e dataset atualizados)."
  echo "    Para treinar o modelo, ative o Ollama e rode de novo:"
  echo "      docker compose --profile llm up -d ollama"
  echo "      sh scripts/train.sh"
fi

echo ""
echo "Concluído."

# Como treinar a IA do manifesto (servidor Ubuntu)

O sistema aprende em ciclo: **few-shot agora → captura automática de cada conferência →
fine-tuning quando houver exemplos suficientes**. Nada de treinar do zero.

> Substitua `IP_DO_SERVIDOR` e `USUARIO` pelos do seu Ubuntu. Não guarde senhas em arquivos do projeto.

---

## Fase 1 — Ligar a IA local (Ollama), sem treino — funciona já

A IA usa a base de conhecimento (`knowledge_base/`) como contexto (few-shot).

```bash
ssh USUARIO@IP_DO_SERVIDOR
cd ~/jm-rotas-portugal

# 1) Subir o Ollama junto da stack
docker compose --profile llm up -d ollama

# 2) Baixar um modelo (escolha conforme a RAM/GPU):
docker exec -it jmrotas_ollama ollama pull llama3.1:8b     # ~8 GB RAM, CPU ok
# alternativas: qwen2.5:7b  | mistral:7b  | llama3.1:70b (precisa GPU)

# 3) Apontar o extrator para a IA, no .env:
#    EXTRACTOR=llm
#    OCR_LLM_BASE_URL=http://ollama:11434/v1
#    OCR_LLM_MODEL=llama3.1:8b
nano .env

# 4) Reiniciar o worker de OCR
docker compose up -d ocr-worker
```

A partir daqui, todo manifesto novo passa pela IA. Se a IA falhar, o sistema
cai automaticamente para o extrator por regras (nunca trava).

---

## Fase 2 — Ensinar automaticamente (a base cresce sozinha)

**Já é automático:** cada vez que o operador confere um manifesto na tela e clica
*Confirmar conferência*, o sistema grava no banco o par
`raw_text` (entrada) + `extracted_json` corrigido (gold).

Para transformar essas conferências em base de conhecimento + dataset de treino:

```bash
# Dentro do container do worker (tem o DATABASE_URL e as libs):
docker compose exec ocr-worker python knowledge_base/training/export_training_data.py

# Gera:
#  knowledge_base/examples/<codigo_ut>.ocr.txt   (entrada)
#  knowledge_base/examples/<codigo_ut>.gold.json (saída correta)
#  knowledge_base/training/dataset.jsonl         (treino)
```

Rode isso periodicamente (ou agende um cron). Quanto mais conferências, mais a IA
acerta. Dica: deixe `EXTRACTOR=llm` e os operadores só corrigem o que a IA errou —
cada correção vira exemplo melhor.

> Versione os `examples/*.gold.json` no Git: é o histórico do que a IA aprendeu.

---

## Fase 3 — Fine-tuning (modelo próprio) — quando tiver ~20–50 exemplos

```bash
# 1) Atualizar o dataset com tudo que foi conferido
docker compose exec ocr-worker python knowledge_base/training/export_training_data.py

# 2) Copiar o dataset para fora do container
docker cp jmrotas_ocr_worker:/app/knowledge_base/training/dataset.jsonl ./dataset.jsonl

# 3a) Fine-tune local com Ollama (cria um modelo a partir de um Modelfile + adapter
#     treinado com Unsloth/LLaMA-Factory usando dataset.jsonl como SFT).
#     Depois:
docker exec -it jmrotas_ollama ollama create jmrotas-manifesto -f Modelfile
#     e no .env: OCR_LLM_MODEL=jmrotas-manifesto

# 3b) Ou fine-tune gerenciado (OpenAI):
#     openai api fine_tunes.create -t dataset.jsonl -m gpt-4o-mini
#     e aponte OCR_LLM_BASE_URL/MODEL/API_KEY para o modelo treinado.
```

---

## Avaliar (medir acurácia)

```bash
# separa 20% dos exemplos para avaliação
docker compose exec ocr-worker python knowledge_base/training/build_dataset.py --eval
```
Compare a saída da IA com `eval.jsonl` nos campos críticos
(codigo_ut, nº de paradas, peso/palés/pedido por parada).

## Resumo do fluxo
```
Manifesto -> OCR -> IA (few-shot/treinada) -> pré-rota
                                   │
                          Conferência humana (corrige)
                                   │
                    export_training_data.py  ──►  base cresce
                                   │
                       (periodicamente) fine-tuning
```

# Base de conhecimento — extração de manifestos (treino da IA)

Tudo que a IA precisa para aprender a transformar um **manifesto Salvesen** em
**rota + paradas** estruturadas. Serve para 3 coisas: **few-shot** (prompt),
**fine-tuning** (treino) e **avaliação** (medir acurácia).

```
knowledge_base/
├── schema/manifest.schema.json     # formato EXATO da saída (contrato)
├── extraction_rules.md             # regras de extração (filtro de página, agrupamento, normalização)
├── field_dictionary.md             # rótulos ES/PT → campos; fornecedores conhecidos
├── prompts/system_prompt.md        # prompt do extrator (regras + saída JSON)
├── examples/
│   ├── 3466594.gold.json           # exemplo rotulado (saída correta) — Código UT 3466594
│   ├── 3469205.gold.json           # exemplo rotulado — Código UT 3469205
│   └── 3469205.ocr.txt             # entrada OCR aproximada pareada com o gold
└── training/
    ├── build_dataset.py            # gera dataset.jsonl (gold -> chat JSONL)
    └── dataset.jsonl               # (gerado) pronto para fine-tuning
```

## Como adicionar mais exemplos (quanto mais, melhor)
Para cada manifesto novo (idealmente **20–50** para um bom resultado):
1. Salve o OCR/transcrição em `examples/<codigo_ut>.ocr.txt`.
2. Crie a saída correta em `examples/<codigo_ut>.gold.json` seguindo o schema.
   - Dica: rode o sistema, faça o upload, **corrija na tela de conferência** e exporte o JSON conferido como gold. Assim cada conferência humana vira dado de treino.
3. `python training/build_dataset.py --eval`

## Como usar (3 modos)

### A) Few-shot (sem treino) — já funciona
O extrator LLM (`EXTRACTOR=llm`) injeta `system_prompt.md` + 2 exemplos gold como
contexto e pede o JSON. Bom para começar com um modelo capaz (GPT-4o, Gemini, Llama 3.1 70B).

### B) Fine-tuning (modelo próprio/local)
```bash
cd knowledge_base/training
python build_dataset.py --eval        # -> dataset.jsonl + eval.jsonl
```
- **OpenAI:** `openai api fine_tunes.create -t dataset.jsonl -m gpt-4o-mini`
- **Local (Ollama/Unsloth/LLaMA-Factory):** use `dataset.jsonl` (formato mensagens) como SFT.
  Ex.: criar `Modelfile` apontando para o adapter treinado e servir em `OCR_LLM_BASE_URL`.

### C) Avaliação
Compare a saída do extrator com `eval.jsonl` campo a campo (codigo_ut, nº de paradas,
peso/pales por parada). Meta inicial: ≥ 95% nos campos críticos do cabeçalho e
≥ 85% nas linhas de parada (o resto fica para a conferência humana).

## Regras-chave (resumo)
- Só páginas com **MANIFIESTO** no cabeçalho.
- **Código UT = rota**; cada **DESTINO = parada**; 2 linhas por parada → agrupar.
- Números PT/ES: `.`=milhar, `,`=decimal.
- A IA gera **pré-rota**; operador confere; só então a rota é criada.

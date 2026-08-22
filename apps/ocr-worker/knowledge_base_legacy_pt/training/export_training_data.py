"""Exporta as conferências do banco como base de conhecimento + dataset de treino.

CICLO DE APRENDIZADO AUTOMÁTICO:
- Cada manifesto conferido pelo operador grava em `ocr_results`:
    raw_text       = texto OCR (entrada)
    extracted_json = JSON corrigido pela conferência (rótulo "gold")
- Este script lê esses pares e gera:
    knowledge_base/examples/<codigo_ut>.ocr.txt   (entrada)
    knowledge_base/examples/<codigo_ut>.gold.json (saída correta)
    knowledge_base/training/dataset.jsonl         (pronto p/ fine-tuning)

Uso (dentro do container ou com o .env carregado):
    python export_training_data.py
    python export_training_data.py --include-auto   # inclui rotas geradas automaticamente
"""
import argparse
import json
import os
from pathlib import Path

from sqlalchemy import bindparam, create_engine, text

KB = Path(__file__).resolve().parents[1]
EXAMPLES = KB / "examples"


def export() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-auto", action="store_true",
                    help="inclui status ROTA_GERADA (conferência automática, menos confiável)")
    args = ap.parse_args()

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL não definido (rode com o .env carregado ou dentro do container).")

    statuses = ["CONFERIDO"]
    if args.include_auto:
        statuses.append("ROTA_GERADA")

    engine = create_engine(db_url, pool_pre_ping=True)
    stmt = text(
        "SELECT m.id, o.raw_text, o.extracted_json "
        "FROM ocr_results o JOIN manifests m ON m.id = o.manifest_id "
        "WHERE m.status IN :st AND o.raw_text IS NOT NULL AND o.extracted_json IS NOT NULL"
    ).bindparams(bindparam("st", expanding=True))
    with engine.connect() as conn:
        rows = conn.execute(stmt, {"st": statuses}).fetchall()

    EXAMPLES.mkdir(parents=True, exist_ok=True)
    saved = 0
    for manifest_id, raw_text, extracted_json in rows:
        try:
            gold = json.loads(extracted_json)
        except (TypeError, json.JSONDecodeError):
            continue
        stem = str(gold.get("codigo_ut") or f"manifest_{manifest_id}")
        (EXAMPLES / f"{stem}.ocr.txt").write_text(raw_text, encoding="utf-8")
        (EXAMPLES / f"{stem}.gold.json").write_text(
            json.dumps(gold, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        saved += 1

    print(f"{saved} conferências exportadas para {EXAMPLES}")

    # Regenera o dataset.jsonl a partir de TODOS os exemplos (sementes + banco)
    from build_dataset import build_records, _dump
    records = build_records()
    _dump(KB / "training" / "dataset.jsonl", records)
    return saved


if __name__ == "__main__":
    export()

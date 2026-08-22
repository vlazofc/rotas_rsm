"""Gera o dataset de fine-tuning (JSONL chat) a partir dos exemplos rotulados.

Pareia cada `<id>.ocr.txt` (entrada) com `<id>.gold.json` (saída esperada),
no formato de mensagens compatível com OpenAI/together/Ollama fine-tuning.

Uso:
    python build_dataset.py            # gera training/dataset.jsonl
    python build_dataset.py --eval     # separa 20% para avaliação
"""
import argparse
import json
import random
from pathlib import Path

KB = Path(__file__).resolve().parents[1]
EXAMPLES = KB / "examples"
SYSTEM_PROMPT = (KB / "prompts" / "system_prompt.md").read_text(encoding="utf-8")


def build_records() -> list[dict]:
    records = []
    for gold_path in sorted(EXAMPLES.glob("*.gold.json")):
        stem = gold_path.name.replace(".gold.json", "")
        ocr_path = EXAMPLES / f"{stem}.ocr.txt"
        if not ocr_path.exists():
            print(f"[aviso] sem OCR para {stem}, pulando")
            continue
        ocr_text = ocr_path.read_text(encoding="utf-8")
        gold = json.loads(gold_path.read_text(encoding="utf-8"))
        records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Texto OCR do manifesto:\n\n{ocr_text}"},
                {"role": "assistant", "content": json.dumps(gold, ensure_ascii=False)},
            ]
        })
    return records


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", action="store_true", help="separa 20% para avaliação")
    args = ap.parse_args()

    records = build_records()
    if not records:
        print("Nenhum par exemplo encontrado em examples/*.gold.json + *.ocr.txt")
        return

    out_dir = KB / "training"
    if args.eval and len(records) >= 5:
        random.seed(42)
        random.shuffle(records)
        k = max(1, len(records) // 5)
        _dump(out_dir / "eval.jsonl", records[:k])
        _dump(out_dir / "dataset.jsonl", records[k:])
    else:
        _dump(out_dir / "dataset.jsonl", records)


def _dump(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(records)} exemplos -> {path}")


if __name__ == "__main__":
    main()

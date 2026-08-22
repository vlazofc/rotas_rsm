"""Gera um Modelfile do Ollama que 'assa' a base de conhecimento no modelo.

Embute o system prompt + os exemplos rotulados (few-shot) num modelo nomeado,
sem precisar de GPU. É a forma prática de "treinar" no servidor: o modelo
`jmrotas-manifesto` já nasce sabendo extrair o manifesto.

Uso:
    python build_modelfile.py                 # base = OCR_LLM_MODEL ou llama3.1:8b
    python build_modelfile.py --base qwen2.5:7b --max-examples 15
"""
import argparse
import json
import os
from pathlib import Path

KB = Path(__file__).resolve().parents[1]
EXAMPLES = KB / "examples"
OUT = KB / "training" / "Modelfile"


def _q(text: str) -> str:
    """Triple-quote seguro para Modelfile."""
    return '"""' + text.replace('"""', '\\"\\"\\"') + '"""'


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("OCR_LLM_MODEL", "llama3.1:8b"))
    ap.add_argument("--max-examples", type=int, default=20)
    args = ap.parse_args()

    system = (KB / "prompts" / "system_prompt.md").read_text(encoding="utf-8")

    lines = [
        f"FROM {args.base}",
        "PARAMETER temperature 0",
        "PARAMETER num_ctx 8192",
        f"SYSTEM {_q(system)}",
    ]

    count = 0
    for ocr_path in sorted(EXAMPLES.glob("*.ocr.txt")):
        if count >= args.max_examples:
            break
        gold_path = EXAMPLES / f"{ocr_path.name.replace('.ocr.txt', '')}.gold.json"
        if not gold_path.exists():
            continue
        user = f"Texto OCR do manifesto:\n\n{ocr_path.read_text(encoding='utf-8')}"
        gold = json.dumps(json.loads(gold_path.read_text(encoding="utf-8")), ensure_ascii=False)
        lines.append(f"MESSAGE user {_q(user)}")
        lines.append(f"MESSAGE assistant {_q(gold)}")
        count += 1

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Modelfile gerado em {OUT} (base={args.base}, exemplos few-shot={count})")


if __name__ == "__main__":
    main()

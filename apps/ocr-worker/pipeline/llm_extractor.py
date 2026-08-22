"""Extrator por IA (pluggable) — usa a base de conhecimento como few-shot.

Compatível com qualquer endpoint estilo OpenAI: OpenAI, Ollama (/v1), vLLM,
LM Studio, Together. Configurável por env (ver settings.py):
    EXTRACTOR=llm
    OCR_LLM_BASE_URL=http://ollama:11434/v1
    OCR_LLM_MODEL=llama3.1:8b
    OCR_LLM_API_KEY=ollama   (qualquer valor para endpoints locais)

Se a chamada falhar, o worker cai automaticamente para o extrator por regras.
"""
import json
from pathlib import Path

import requests

from settings import settings

# TODO: base de conhecimento herdada do piloto Portugal/Salvesen — substituir
# por exemplos reais de manifesto Brasil quando disponíveis.
KB = Path(__file__).resolve().parents[1] / "knowledge_base_legacy_pt"


def _load_few_shot() -> list[dict]:
    system = (KB / "prompts" / "system_prompt.md").read_text(encoding="utf-8")
    messages = [{"role": "system", "content": system}]
    # Exemplos rotulados (gold) pareados com o OCR de entrada.
    for ocr_path in sorted((KB / "examples").glob("*.ocr.txt")):
        stem = ocr_path.name.replace(".ocr.txt", "")
        gold_path = KB / "examples" / f"{stem}.gold.json"
        if not gold_path.exists():
            continue
        messages.append({"role": "user", "content": f"Texto OCR do manifesto:\n\n{ocr_path.read_text(encoding='utf-8')}"})
        messages.append({"role": "assistant", "content": gold_path.read_text(encoding="utf-8").strip()})
    return messages


def extract_with_llm(ocr_text: str) -> dict:
    """Chama o LLM e devolve o JSON estruturado. Lança em caso de erro."""
    messages = _load_few_shot()
    messages.append({"role": "user", "content": f"Texto OCR do manifesto:\n\n{ocr_text}"})

    resp = requests.post(
        f"{settings.ocr_llm_base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {settings.ocr_llm_api_key}"},
        json={
            "model": settings.ocr_llm_model,
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        },
        timeout=settings.ocr_llm_timeout,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    data = json.loads(content)
    data.setdefault("necessita_revisao", True)  # IA sempre passa por conferência
    return data

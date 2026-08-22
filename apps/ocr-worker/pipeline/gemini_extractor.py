"""Extrator por IA visual via Google Gemini (API gratuita) — lê a imagem do manifesto diretamente.

Mesma ideia do `vision_extractor` (Ollama local), mas usando a API do Gemini,
que é muito mais rápida (roda na nuvem da Google) e tem camada gratuita.

Ativação (settings.py / .env):
    OCR_ENGINE=gemini
    GEMINI_API_KEY=<chave da Google AI Studio>
    GEMINI_MODEL=gemini-2.0-flash

Se a chamada falhar, o worker cai automaticamente para o OCR local.
"""
import base64
import json
from pathlib import Path

import cv2
import numpy as np
import requests

from settings import settings

# TODO: base de conhecimento herdada do piloto Portugal/Salvesen — substituir
# por exemplos reais de manifesto Brasil quando disponíveis.
KB = Path(__file__).resolve().parents[1] / "knowledge_base_legacy_pt"


def _load_few_shot() -> tuple[str, list[dict]]:
    system = (KB / "prompts" / "system_prompt.md").read_text(encoding="utf-8")
    contents: list[dict] = []
    for ocr_path in sorted((KB / "examples").glob("*.ocr.txt")):
        stem = ocr_path.name.replace(".ocr.txt", "")
        gold_path = KB / "examples" / f"{stem}.gold.json"
        if not gold_path.exists():
            continue
        contents.append({
            "role": "user",
            "parts": [{"text": f"Texto OCR do manifesto:\n\n{ocr_path.read_text(encoding='utf-8')}"}],
        })
        contents.append({
            "role": "model",
            "parts": [{"text": gold_path.read_text(encoding="utf-8").strip()}],
        })
    return system, contents


def _encode_image(img: np.ndarray) -> str:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise RuntimeError("Falha ao codificar imagem para envio ao modelo de visão.")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def extract_with_gemini(images: list[np.ndarray]) -> dict:
    """Envia as páginas (imagens BGR) ao Gemini e devolve o JSON estruturado.

    Lança em caso de erro (o worker cai para o OCR local nesse caso).
    """
    system, contents = _load_few_shot()

    parts: list[dict] = [{
        "text": (
            "Leia as imagens das páginas deste manifesto (anexas) e devolva o JSON "
            "estruturado conforme as regras do prompt do sistema. Considere apenas "
            "páginas com 'MANIFIESTO' no cabeçalho."
        ),
    }]
    for img in images:
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": _encode_image(img)}})
    contents.append({"role": "user", "parts": parts})

    url = f"{settings.gemini_base_url.rstrip('/')}/models/{settings.gemini_model}:generateContent"
    resp = requests.post(
        url,
        params={"key": settings.gemini_api_key},
        json={
            "system_instruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {"temperature": 0, "response_mime_type": "application/json"},
        },
        timeout=settings.gemini_timeout,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Gemini generateContent retornou {resp.status_code}: {resp.text[:500]}")

    body = resp.json()
    content = body["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(content)
    data.setdefault("necessita_revisao", True)
    data.setdefault("confianca_ocr", 0.85)
    return data


def should_use_gemini() -> bool:
    return (settings.ocr_engine or "").strip().lower() == "gemini"

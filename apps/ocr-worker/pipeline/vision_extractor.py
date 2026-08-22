"""Extrator por IA visual local (Ollama) — lê a imagem do manifesto diretamente.

Em vez de depender de OCR (EasyOCR/Tesseract) + extrator de texto, este motor
envia as páginas do manifesto como imagens para um modelo multimodal local
(ex.: qwen2.5vl) via Ollama, usando o mesmo prompt/few-shot da base de
conhecimento. Tende a acertar muito mais em manifestos com tabelas e
qualidade de digitalização ruim.

Ativação (settings.py / .env):
    OCR_ENGINE=vision_llm
    VISION_LLM_BASE_URL=http://ollama:11434
    VISION_LLM_MODEL=qwen2.5vl:7b

Requer o serviço `ollama` ativo (profile "llm") com o modelo já baixado:
    docker compose --profile llm up -d ollama
    docker compose exec ollama ollama pull qwen2.5vl:7b

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


def _load_few_shot() -> list[dict]:
    system = (KB / "prompts" / "system_prompt.md").read_text(encoding="utf-8")
    messages = [{"role": "system", "content": system}]
    for ocr_path in sorted((KB / "examples").glob("*.ocr.txt")):
        stem = ocr_path.name.replace(".ocr.txt", "")
        gold_path = KB / "examples" / f"{stem}.gold.json"
        if not gold_path.exists():
            continue
        messages.append({"role": "user", "content": f"Texto OCR do manifesto:\n\n{ocr_path.read_text(encoding='utf-8')}"})
        messages.append({"role": "assistant", "content": gold_path.read_text(encoding="utf-8").strip()})
    return messages


def _encode_image(img: np.ndarray) -> str:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise RuntimeError("Falha ao codificar imagem para envio ao modelo de visão.")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def extract_with_vision_llm(images: list[np.ndarray]) -> dict:
    """Envia as páginas (imagens BGR) ao modelo de visão e devolve o JSON estruturado.

    Lança em caso de erro (o worker cai para o OCR local nesse caso).
    """
    messages = _load_few_shot()
    messages.append({
        "role": "user",
        "content": (
            "Leia as imagens das páginas deste manifesto (anexas) e devolva o JSON "
            "estruturado conforme as regras do prompt do sistema. Considere apenas "
            "páginas com 'MANIFIESTO' no cabeçalho."
        ),
        "images": [_encode_image(img) for img in images],
    })

    resp = requests.post(
        f"{settings.vision_llm_base_url.rstrip('/')}/api/chat",
        json={
            "model": settings.vision_llm_model,
            "messages": messages,
            "format": "json",
            "stream": False,
            "options": {"temperature": 0, "num_ctx": settings.vision_llm_num_ctx},
        },
        timeout=settings.vision_llm_timeout,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Ollama /api/chat retornou {resp.status_code}: {resp.text[:500]}")
    content = resp.json()["message"]["content"]
    data = json.loads(content)
    data.setdefault("necessita_revisao", True)
    data.setdefault("confianca_ocr", 0.85)
    return data


def should_use_vision_llm() -> bool:
    return (settings.ocr_engine or "").strip().lower() == "vision_llm"

"""Cliente para motores OCR/IA externos.

Entrada: bytes do PDF/imagem vindo do MinIO.
Saida: texto bruto, confiança aproximada e nome do motor usado.
"""
from __future__ import annotations

from typing import Any
import json

import requests

from settings import settings


AI_ENGINES = {"ai", "ocrspace", "custom", "custom_ai", "jmhelpdesk"}


def should_use_ai_ocr() -> bool:
    return (settings.ocr_engine or "").lower() in AI_ENGINES


def read_ai_ocr(data: bytes, filename: str, content_type: str) -> tuple[str, float, str]:
    provider = (settings.ai_ocr_provider or "ocrspace").lower()
    if provider == "ocrspace" or (settings.ocr_engine or "").lower() == "ocrspace":
        return _read_ocrspace(data, filename, content_type)
    if provider in {"custom", "jmhelpdesk"} or (settings.ocr_engine or "").lower() in {"custom", "custom_ai", "jmhelpdesk"}:
        return _read_custom(data, filename, content_type)
    raise RuntimeError(f"Provider OCR/IA não suportado: {provider}")


def _request_auth() -> tuple[dict[str, str], tuple[str, str] | None]:
    auth_type = (settings.ai_ocr_auth_type or "header").lower()
    if auth_type == "none":
        return {}, None
    if auth_type == "basic":
        username = settings.ai_ocr_basic_username or settings.ai_ocr_api_key
        password = settings.ai_ocr_basic_password
        if not username and not password:
            raise RuntimeError("Basic Auth OCR/IA sem usuário/senha configurados.")
        return {}, (username, password)
    if not settings.ai_ocr_api_key:
        raise RuntimeError("AI_OCR_API_KEY não configurada no .env.")
    if auth_type == "bearer":
        return {"Authorization": f"Bearer {settings.ai_ocr_api_key}"}, None
    return {settings.ai_ocr_api_key_header: settings.ai_ocr_api_key}, None


def _extra_form() -> dict[str, str]:
    try:
        value = json.loads(settings.ai_ocr_extra_form_json or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError("AI_OCR_EXTRA_FORM_JSON inválido.") from exc
    if not isinstance(value, dict):
        raise RuntimeError("AI_OCR_EXTRA_FORM_JSON deve ser um objeto JSON.")
    return {str(k): str(v) for k, v in value.items()}


def _read_ocrspace(data: bytes, filename: str, content_type: str) -> tuple[str, float, str]:
    payload = {
        "language": settings.ai_ocr_language or "por",
        "isOverlayRequired": "false",
        "detectOrientation": "true",
        "scale": "true",
        "OCREngine": "2",
    }
    headers, auth = _request_auth()
    try:
        response = requests.post(
            settings.ai_ocr_api_url,
            headers=headers,
            auth=auth,
            data=payload,
            files={"file": (filename, data, content_type)},
            timeout=settings.ai_ocr_timeout_seconds,
        )
    except requests.Timeout as exc:
        raise RuntimeError(
            f"OCR/IA externo excedeu {settings.ai_ocr_timeout_seconds}s sem resposta."
        ) from exc
    response.raise_for_status()
    body = response.json()
    if body.get("IsErroredOnProcessing"):
        errors = body.get("ErrorMessage") or body.get("ErrorDetails") or "erro desconhecido"
        raise RuntimeError(f"OCRSpace falhou: {errors}")

    results = body.get("ParsedResults") or []
    text = "\n".join((item.get("ParsedText") or "").strip() for item in results).strip()
    return text, _confidence_from_text(text), "ocrspace"


def _read_custom(data: bytes, filename: str, content_type: str) -> tuple[str, float, str]:
    headers, auth = _request_auth()
    try:
        response = requests.post(
            settings.ai_ocr_api_url,
            headers=headers,
            auth=auth,
            data=_extra_form(),
            files={"file": (filename, data, content_type)},
            timeout=settings.ai_ocr_timeout_seconds,
        )
    except requests.Timeout as exc:
        raise RuntimeError(
            f"OCR/IA externo excedeu {settings.ai_ocr_timeout_seconds}s sem resposta."
        ) from exc
    response.raise_for_status()
    body = response.json()
    text = _extract_text(body)
    if not text:
        if isinstance(body, dict) and body.get("status") == "recebido" and body.get("caminho"):
            raise RuntimeError(
                "API OCR/IA recebeu o arquivo, mas não devolveu texto. "
                "Configure AI_OCR_API_URL para o endpoint que retorna a leitura/OCR, não apenas upload."
            )
        raise RuntimeError("API OCR/IA não devolveu texto reconhecido na resposta.")
    confidence = _extract_confidence(body, text)
    return text, confidence, "custom_ai"


def _extract_text(body: Any) -> str:
    if isinstance(body, str):
        return body.strip()
    if not isinstance(body, dict):
        return ""
    for key in ("text", "raw_text", "parsed_text", "ParsedText", "result", "content", "ocr", "leitura", "response"):
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if isinstance(body.get("result"), dict):
        return _extract_text(body["result"])
    if isinstance(body.get("data"), dict):
        return _extract_text(body["data"])
    if isinstance(body.get("results"), list):
        return "\n".join(_extract_text(item) for item in body["results"]).strip()
    return ""


def _extract_confidence(body: Any, text: str) -> float:
    if isinstance(body, dict):
        for key in ("confidence", "score", "ocr_confidence"):
            value = body.get(key)
            if isinstance(value, (int, float)):
                return float(value)
    return _confidence_from_text(text)


def _confidence_from_text(text: str) -> float:
    return 0.9 if text.strip() else 0.0

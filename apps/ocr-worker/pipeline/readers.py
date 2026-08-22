"""Motores de OCR: EasyOCR (IA local gratuita) e Tesseract (fallback).

Módulo isolado e trocável — depois pode-se plugar Azure Document Intelligence,
Gemini ou OpenAI Vision sem mexer no restante do pipeline.
"""
import numpy as np

from settings import settings

_easyocr = None


def _get_easyocr():
    global _easyocr
    if _easyocr is None:
        import easyocr

        lang = settings.ocr_lang or "pt"
        _easyocr = easyocr.Reader([lang], gpu=False, verbose=False)
    return _easyocr


def read_easyocr(img: np.ndarray) -> tuple[str, float]:
    reader = _get_easyocr()
    result = reader.readtext(img, detail=1, paragraph=False)
    lines, confs = [], []
    for _box, text, conf in result or []:
        if text.strip():
            lines.append(text.strip())
            confs.append(float(conf))
    avg = sum(confs) / len(confs) if confs else 0.0
    return "\n".join(lines), avg


def read_tesseract(img: np.ndarray) -> tuple[str, float]:
    import pytesseract
    data = pytesseract.image_to_data(img, lang="por", output_type=pytesseract.Output.DICT)
    words, confs = [], []
    for text, conf in zip(data["text"], data["conf"]):
        if text.strip() and conf not in ("-1", -1):
            words.append(text)
            confs.append(float(conf) / 100.0)
    avg = sum(confs) / len(confs) if confs else 0.0
    return " ".join(words), avg


def run_ocr(img: np.ndarray) -> tuple[str, float, str]:
    """Executa o motor principal; cai para o fallback se confiança baixa."""
    engine = settings.ocr_engine
    if engine == "tesseract":
        text, conf = read_tesseract(img)
        return text, conf, "tesseract"

    try:
        text, conf = read_easyocr(img)
        used = "easyocr"
    except Exception:  # noqa: BLE001 — qualquer falha do EasyOCR cai para Tesseract
        text, conf = read_tesseract(img)
        return text, conf, "tesseract"

    if conf < settings.ocr_min_confidence:
        t_text, t_conf = read_tesseract(img)
        if t_conf > conf:
            return t_text, t_conf, "tesseract"
    return text, conf, used

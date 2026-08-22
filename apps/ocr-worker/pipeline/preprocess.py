"""Normalização de imagem antes do OCR: rotação, contraste, deskew, ruído."""
import io

import cv2
import numpy as np
from PIL import Image


def pdf_or_image_to_images(data: bytes, content_type: str) -> list[np.ndarray]:
    """Converte bytes (PDF ou imagem) em lista de imagens BGR (OpenCV)."""
    if content_type == "application/pdf":
        from pdf2image import convert_from_bytes
        pages = convert_from_bytes(data, dpi=300)
        return [cv2.cvtColor(np.array(p), cv2.COLOR_RGB2BGR) for p in pages]
    img = Image.open(io.BytesIO(data)).convert("RGB")
    return [cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)]


def normalize(img: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Aumenta contraste
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    # Remoção de ruído
    gray = cv2.fastNlMeansDenoising(gray, h=10)
    # Binarização adaptativa
    gray = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15
    )
    return _deskew(gray)


def _deskew(gray: np.ndarray) -> np.ndarray:
    coords = np.column_stack(np.where(gray < 255))
    if coords.size == 0:
        return gray
    angle = cv2.minAreaRect(coords)[-1]
    angle = -(90 + angle) if angle < -45 else -angle
    if abs(angle) < 0.5:
        return gray
    h, w = gray.shape
    m = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(gray, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

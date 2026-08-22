"""Filtro de páginas: só processamos páginas com 'MANIFIESTO' no cabeçalho."""
import re

MANIFEST_MARK = re.compile(r"MANIFI?ESTO", re.IGNORECASE)
UT_RE = re.compile(r"\b(\d{6,9})\b")


def is_manifest_page(text: str) -> bool:
    """True se a página parece um MANIFIESTO (marca no topo do texto)."""
    head = "\n".join(text.splitlines()[:12])
    return bool(MANIFEST_MARK.search(head))


def extract_codigo_ut(text: str) -> str | None:
    """Procura o Código UT logo após o rótulo; senão, primeiro número 6-9 dígitos."""
    m = re.search(r"C[oó]digo\s*UT\D{0,20}?(\d{6,9})", text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = UT_RE.search(text)
    return m.group(1) if m else None


def select_manifest_pages(pages_text: list[str]) -> list[tuple[int, str, str | None]]:
    """Recebe o texto de cada página; devolve só as MANIFIESTO.

    Retorna lista de (indice_1based, texto, codigo_ut).
    """
    selected = []
    for i, text in enumerate(pages_text, start=1):
        if is_manifest_page(text):
            selected.append((i, text, extract_codigo_ut(text)))
    return selected

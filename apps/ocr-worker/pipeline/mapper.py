"""Extração estruturada do manifesto por REGRAS (fallback determinístico).

Produz o schema canônico (knowledge_base/schema/manifest.schema.json):
cabeçalho -> rota; cada linha de DESTINO -> parada (2 linhas agrupadas).
É best-effort: o que ficar incerto vai para conferência humana. Para maior
acurácia use o extrator LLM (pipeline/llm_extractor.py) treinado na base.
"""
import re

_DATE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
_TIME = re.compile(r"\b([0-2]?\d):([0-5]\d)\b")
_WEIGHT = re.compile(r"(\d{1,3}(?:\.\d{3})*,\d{2})\s*Kg", re.IGNORECASE)
_PALES = re.compile(r"(\d{1,3},\d{2})\s*Pal", re.IGNORECASE)
_TEMP = re.compile(r"\b(Amb\.?|Ambiente|\d{1,2})\b", re.IGNORECASE)
_FORN = re.compile(r"^(.{2,40}?\(\d{3}\))")
_ORIGIN = re.compile(r"SALVESEN\s+LOG[IÍ]STICA\s+(?:PORTUGAL|AZAMBUJA\s*\d+)", re.IGNORECASE)
_POSTAL = re.compile(r"(\d{4}-\d{3})")
_UT = re.compile(r"C[oó]digo\s*UT\D{0,20}?(\d{6,9})", re.IGNORECASE)
_LOAD_DT = re.compile(r"(\d{1,2})\s*([a-zç]{3,4})\.?\s*(\d{4})\s+(\d{1,2}):(\d{2})", re.IGNORECASE)

_MONTHS = {
    "jan": "01", "fev": "02", "feb": "02", "mar": "03", "abr": "04", "apr": "04",
    "mai": "05", "may": "05", "jun": "06", "jul": "07", "ago": "08", "aug": "08",
    "set": "09", "sep": "09", "out": "10", "oct": "10", "nov": "11", "dez": "12", "dec": "12",
}


def _num(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))


def _iso(d: str, m: str, y: str) -> str:
    return f"{y}-{m}-{d}"


def _temperatura(token: str) -> str:
    t = token.strip().lower()
    return "Ambiente" if t.startswith("amb") else token.strip()


def _parse_header(text: str) -> dict:
    head = {"origem": None, "origem_morada": None, "transportadora": None,
            "matricula": None, "natureza": None, "data_carga": None, "hora_carga": None}

    ut = _UT.search(text)
    if ut:
        head["codigo_ut"] = ut.group(1)
    else:
        # rótulo e número podem estar em colunas/linhas diferentes:
        # pega o 1º número de 6-9 dígitos no topo do documento (antes da tabela).
        head_block = "\n".join(text.splitlines()[:15])
        m = re.search(r"\b(\d{6,9})\b", head_block)
        head["codigo_ut"] = m.group(1) if m else None

    if (m := _LOAD_DT.search(text)):
        day, mon, year, hh, mm = m.groups()
        mon_iso = _MONTHS.get(mon[:3].lower())
        if mon_iso:
            head["data_carga"] = _iso(f"{int(day):02d}", mon_iso, year)
        head["hora_carga"] = f"{int(hh):02d}:{mm}"
    else:
        # formato dd/mm/aaaa hh:mm
        if (m := re.search(r"(\d{2})/(\d{2})/(\d{4})\s+(\d{1,2}):(\d{2})", text)):
            d, mo, y, hh, mm = m.groups()
            head["data_carga"] = _iso(d, mo, y)
            head["hora_carga"] = f"{int(hh):02d}:{mm}"

    for line in text.splitlines():
        u = line.upper()
        if "ORIGEN" in u and "SALVESEN" in u and not head["origem"]:
            mo = _ORIGIN.search(line)
            if mo:
                head["origem"] = mo.group(0).upper()
        if "TRANSPORTISTA" in u and not head["transportadora"]:
            t = re.sub(r".*TRANSPORTISTA[:\s]*", "", line, flags=re.IGNORECASE)
            t = re.sub(r"\bPTG\d+\s*-\s*", "", t, flags=re.IGNORECASE)
            t = re.split(r"C\.?I\.?F", t)[0].strip()
            if t:
                head["transportadora"] = t
        if "MATRÍCULA" in u or "MATRICULA" in u:
            mm = re.search(r"([0-9A-Z]{2}-[0-9A-Z]{2}-[0-9A-Z]{2})", line)
            if mm:
                head["matricula"] = mm.group(1)
        if "NATUREZA" in u and not head["natureza"]:
            head["natureza"] = re.sub(r".*MERCANC[IÍ]A\s*", "", line, flags=re.IGNORECASE).strip() or None
    return head


def _split_origin_destino(left: str) -> tuple[str | None, str]:
    mo = _ORIGIN.search(left)
    if mo:
        origem = mo.group(0).upper()
        destino = left[mo.end():].strip(" -\t")
        return origem, destino
    return None, left.strip()


def parse_page(text: str, confidence: float = 0.0) -> dict:
    """Extrai cabeçalho + paradas de UMA página MANIFIESTO."""
    result = _parse_header(text)
    destinos: list[dict] = []
    seq = 0

    for raw in text.splitlines():
        line = raw.rstrip()
        d = _DATE.search(line)
        w = _WEIGHT.search(line)
        if not (d and w):
            # linha de morada: anexa à última parada
            if destinos and _is_address_line(line):
                _append_address(destinos[-1], line)
            continue

        # --- é uma linha de dados (data + peso) ---
        left = line[: d.start()].strip()
        tail = line[d.start():]
        time_m = _TIME.search(tail)
        pales_m = _PALES.search(tail)
        # temperatura: entre hora e peso
        temp = None
        if time_m:
            mid = tail[time_m.end(): w.start() - (d.start())] if w.start() > d.start() else ""
            tm = _TEMP.search(mid)
            temp = _temperatura(tm.group(1)) if tm else None
        # pedido: tudo após PALÉS
        pedido = None
        if pales_m:
            after = tail[pales_m.end():].strip()
            if "PEDIDO" not in after.upper() and not re.fullmatch(r"\d+\s*Pedidos?", after, re.IGNORECASE):
                nums = re.findall(r"[A-Z0-9.\-]{5,}", after)
                pedido = " / ".join(nums) if nums else None

        forn = _FORN.match(left)
        is_detail = forn is not None and not _ORIGIN.search(left)

        if is_detail and destinos:
            # linha de detalhe: preenche fornecedor + pedido da parada anterior
            destinos[-1]["fornecedor"] = forn.group(1).strip()
            if pedido:
                destinos[-1]["pedido"] = pedido
            continue

        # linha principal: nova parada
        seq += 1
        origem, destino_name = _split_origin_destino(left)
        destinos.append({
            "sequencia": seq,
            "origem": origem,
            "nome": destino_name or "—",
            "morada": None,
            "codigo_postal": None,
            "cidade": None,
            "data_limite": _iso(*d.groups()),
            "hora_limite": f"{int(time_m.group(1)):02d}:{time_m.group(2)}" if time_m else None,
            "temperatura": temp,
            "peso_kg": _num(w.group(1)),
            "pales": _num(pales_m.group(1)) if pales_m else None,
            "pedido": pedido,
            "fornecedor": None,
            "confianca": round(confidence, 3),
        })

    result["tipo_documento"] = "MANIFIESTO"
    result["destinos"] = destinos
    result["confianca_ocr"] = round(confidence, 3)
    result["necessita_revisao"] = _needs_review(result, confidence)
    return result


def _is_address_line(line: str) -> bool:
    u = line.upper()
    if any(k in u for k in ("ORIGEN", "DESTINO", "F.ENTR", "TRANSPORTISTA", "NATUREZA", "MANIFIESTO")):
        return False
    return bool(line.strip())


def _append_address(stop: dict, line: str) -> None:
    txt = line.strip()
    if _ORIGIN.search(txt):
        return
    # Há 2 colunas (origem à esquerda, destino à direita). O destino fica à
    # direita, então usamos o ÚLTIMO código postal da linha e a cidade após ele.
    postals = list(_POSTAL.finditer(txt))
    if postals and not stop.get("codigo_postal"):
        last = postals[-1]
        stop["codigo_postal"] = last.group(1)
        after = txt[last.end():].strip(" -\t")
        city = re.split(r"\s*[-\[]\s*", after)[0].strip()
        city = re.sub(r"\s{2,}.*$", "", city).strip()  # corta coluna seguinte
        if city and not stop.get("cidade"):
            stop["cidade"] = city.upper()
        return
    if not postals:
        # linha de morada sem CP: pega a coluna da direita (após espaços largos)
        cols = re.split(r"\s{2,}", txt.strip())
        frag = cols[-1] if cols else txt.strip()
        stop["morada"] = (f"{stop['morada']}, {frag}" if stop.get("morada") else frag)


def _needs_review(result: dict, confidence: float) -> bool:
    if confidence < 0.82:
        return True
    if not result.get("codigo_ut") or not result.get("destinos"):
        return True
    for d in result["destinos"]:
        if not d.get("nome") or not d.get("peso_kg") or not d.get("pedido"):
            return True
    return False


def _split_manifest_blocks(text: str) -> list[str]:
    """Quebra o texto OCR em blocos por ocorrência de 'MANIFIESTO'.

    Só blocos com a marca são considerados (requisito: ignorar páginas sem MANIFIESTO).
    Se não houver marca (ex.: foto única de 1 manifesto), trata o texto todo como 1 bloco.
    """
    from pipeline.page_filter import MANIFEST_MARK

    marks = [m.start() for m in MANIFEST_MARK.finditer(text)]
    if not marks:
        return [text]
    blocks = []
    for i, start in enumerate(marks):
        end = marks[i + 1] if i + 1 < len(marks) else len(text)
        blocks.append(text[start:end])
    return blocks


def map_manifest(text: str, confidence: float = 0.0) -> dict:
    """Entrada pública usada pelo worker.

    1) filtra/recorta só páginas MANIFIESTO;
    2) escolhe o motor de extração (EXTRACTOR=rules|llm);
    3) extrai cada página e junta as paradas (multipágina = mesma rota).
    """
    try:
        from settings import settings
        extractor = getattr(settings, "extractor", "rules")
    except Exception:  # noqa: BLE001 — sem config disponível: usa regras
        extractor = "rules"

    blocks = _split_manifest_blocks(text)

    if extractor == "llm":
        try:
            from pipeline.llm_extractor import extract_with_llm
            data = extract_with_llm("\n\n".join(blocks))
            data.setdefault("confianca_ocr", round(confidence, 3))
            return data
        except Exception:  # noqa: BLE001 — IA indisponível: cai para regras
            pass

    pages = [parse_page(b, confidence) for b in blocks]
    pages = [p for p in pages if p.get("destinos") or p.get("codigo_ut")]
    if not pages:
        return parse_page(text, confidence)
    merged = merge_pages(pages)
    merged["paginas_consideradas"] = list(range(1, len(pages) + 1))
    return merged


def merge_pages(pages: list[dict]) -> dict:
    """Junta páginas com o mesmo Código UT numa única rota."""
    if not pages:
        return {}
    base = dict(pages[0])
    destinos = list(base.get("destinos", []))
    confs = [p.get("confianca_ocr", 0.0) for p in pages]
    for p in pages[1:]:
        destinos.extend(p.get("destinos", []))
    for i, dst in enumerate(destinos, start=1):
        dst["sequencia"] = i
    base["destinos"] = destinos
    base["confianca_ocr"] = round(sum(confs) / len(confs), 3) if confs else 0.0
    base["necessita_revisao"] = _needs_review(base, base["confianca_ocr"])
    return base

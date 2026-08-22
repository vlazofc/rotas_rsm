"""Worker Celery de OCR — consome a fila 'ocr'.

Fluxo: baixa o arquivo do MinIO -> normaliza -> OCR (EasyOCR/Tesseract) ->
extrai JSON -> grava OcrResult.

Se a confiança do OCR atingir OCR_MIN_CONFIDENCE e os campos obrigatórios
(codigo_ut, data_carga) tiverem sido extraídos, a conferência e a criação
da rota acontecem automaticamente (status ROTA_GERADA). Caso contrário, o
manifesto vai para AGUARDANDO_CONFERENCIA e exige conferência humana.
"""
import json
import logging
from datetime import date, time as dt_time

from celery import Celery
from minio import Minio
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from settings import settings
from pipeline.preprocess import normalize, pdf_or_image_to_images
from pipeline.readers import run_ocr
from pipeline.ai_client import read_ai_ocr, should_use_ai_ocr
from pipeline.vision_extractor import extract_with_vision_llm, should_use_vision_llm
from pipeline.gemini_extractor import extract_with_gemini, should_use_gemini
from pipeline.mapper import map_manifest

logger = logging.getLogger(__name__)

celery_app = Celery(
    "admmendes_ocr",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.update(timezone=settings.app_timezone, enable_utc=True)

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


def _run_local_ocr(data: bytes, content_type: str) -> tuple[str, float, str]:
    images = pdf_or_image_to_images(data, content_type)
    all_text, confs, engine_used = [], [], settings.ocr_engine
    for img in images:
        norm = normalize(img)
        txt, conf, used = run_ocr(norm)
        all_text.append(txt)
        confs.append(conf)
        engine_used = used

    raw_text = "\n".join(all_text)
    confidence = sum(confs) / len(confs) if confs else 0.0
    return raw_text, confidence, engine_used


def _parse_iso_date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _parse_iso_time(value) -> dt_time | None:
    if not value:
        return None
    try:
        return dt_time.fromisoformat(str(value))
    except ValueError:
        return None


def _auto_generate_route(db, manifest_id: int, branch_id: int, uploaded_by: int | None, extracted: dict, existing_route_id: int | None = None) -> int | None:
    """Cria ou atualiza a rota + paradas direto do JSON extraído (conferência automática).

    Se o manifesto já estiver associado a uma rota (ex.: enviado manualmente
    para uma rota criada antes), essa rota é atualizada com os dados do
    manifesto (substituindo as paradas) em vez de criar uma rota nova.

    Retorna o id da rota criada/atualizada, ou None se faltar codigo_ut/data_carga
    (nesse caso o manifesto segue para conferência humana).
    """
    route_date = _parse_iso_date(extracted.get("data_carga"))
    codigo_ut = str(extracted.get("codigo_ut") or "").strip()[:40]
    if not route_date or not codigo_ut:
        return None

    origin_name = extracted.get("origem")
    origin_name = str(origin_name)[:160] if origin_name else None
    origin_address = extracted.get("origem_morada")
    origin_address = str(origin_address)[:255] if origin_address else None

    existing_status = None
    if existing_route_id:
        existing_status = db.execute(text("SELECT status FROM routes WHERE id=:r"), {"r": existing_route_id}).scalar()

    if existing_route_id and existing_status and existing_status != "cancelada":
        # Rota criada manualmente: atualiza com os dados do manifesto, mas
        # preserva a data da carga e os horários de doca/CD já registrados.
        route_id = existing_route_id
        db.execute(text(
            "UPDATE routes SET codigo_ut=:codigo_ut, origin_name=:origin_name, origin_address=:origin_address, "
            "toll_outbound=:toll_ida, toll_return=:toll_volta, km_total_informed=:km_total, updated_at=now() "
            "WHERE id=:route_id"
        ), {
            "route_id": route_id,
            "codigo_ut": codigo_ut,
            "origin_name": origin_name,
            "origin_address": origin_address,
            "toll_ida": extracted.get("portagem_ida"),
            "toll_volta": extracted.get("portagem_volta"),
            "km_total": extracted.get("km_total"),
        })
        db.execute(text("DELETE FROM route_stops WHERE route_id=:r"), {"r": route_id})
        if not db.execute(text("SELECT 1 FROM dock_sessions WHERE route_id=:r"), {"r": route_id}).first():
            db.execute(text("INSERT INTO dock_sessions (route_id, created_at, updated_at) VALUES (:r, now(), now())"),
                       {"r": route_id})
    else:
        tenant_id = db.execute(text("SELECT tenant_id FROM branches WHERE id=:b"), {"b": branch_id}).scalar()

        route_id = db.execute(text(
            "INSERT INTO routes (tenant_id, branch_id, codigo_ut, route_date, origin_name, origin_address, "
            "toll_outbound, toll_return, km_total_informed, status, created_by, created_at, updated_at) "
            "VALUES (:tenant_id, :branch_id, :codigo_ut, :route_date, :origin_name, :origin_address, "
            ":toll_ida, :toll_volta, :km_total, 'planejada', :created_by, now(), now()) RETURNING id"
        ), {
            "tenant_id": tenant_id,
            "branch_id": branch_id,
            "codigo_ut": codigo_ut,
            "route_date": route_date,
            "origin_name": origin_name,
            "origin_address": origin_address,
            "toll_ida": extracted.get("portagem_ida"),
            "toll_volta": extracted.get("portagem_volta"),
            "km_total": extracted.get("km_total"),
            "created_by": uploaded_by,
        }).scalar()

        db.execute(text("INSERT INTO dock_sessions (route_id, created_at, updated_at) VALUES (:r, now(), now())"),
                   {"r": route_id})

    for i, dest in enumerate(extracted.get("destinos") or [], start=1):
        db.execute(text(
            "INSERT INTO route_stops (route_id, sequence, customer_name, customer_address, city, "
            "planned_date, planned_time, temperature, weight_kg, pallets, order_number, status, created_at, updated_at) "
            "VALUES (:route_id, :seq, :name, :addr, :city, :pdate, :ptime, :temp, :weight, :pallets, :order, "
            "'pendente', now(), now())"
        ), {
            "route_id": route_id,
            "seq": i,
            "name": dest.get("nome") or "—",
            "addr": dest.get("morada"),
            "city": dest.get("cidade"),
            "pdate": _parse_iso_date(dest.get("data_limite")),
            "ptime": _parse_iso_time(dest.get("hora_limite")),
            "temp": dest.get("temperatura"),
            "weight": dest.get("peso_kg"),
            "pallets": dest.get("paletes") or dest.get("pallets") or dest.get("pales"),
            "order": dest.get("pedido"),
        })

    db.execute(text(
        "INSERT INTO route_events (route_id, event_type, user_id, source) "
        "VALUES (:r, 'MANIFEST_VALIDATED', :u, 'system')"
    ), {"r": route_id, "u": uploaded_by})

    db.execute(text(
        "INSERT INTO audit_logs (user_id, action, entity, entity_id, detail, created_at) "
        "VALUES (:u, 'auto_generate_route', 'manifest', :m, :detail, now())"
    ), {"u": uploaded_by, "m": str(manifest_id), "detail": f"route_id={route_id} (conferência automática)"})

    return route_id


def _minio() -> Minio:
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_root_user,
        secret_key=settings.minio_root_password,
        secure=settings.minio_use_ssl,
    )


@celery_app.task(name="ocr.process_manifest", queue="ocr")
def process_manifest(manifest_id: int) -> dict:
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT storage_key, original_filename, branch_id, uploaded_by, route_id FROM manifests WHERE id=:id"),
            {"id": manifest_id},
        ).first()
        if row is None:
            return {"manifest_id": manifest_id, "error": "not_found"}
        storage_key, filename, branch_id, uploaded_by, existing_route_id = row

        db.execute(text("UPDATE manifests SET status='PROCESSANDO_OCR' WHERE id=:id"),
                   {"id": manifest_id})
        db.commit()

        obj = _minio().get_object(settings.minio_bucket_manifests, storage_key)
        data = obj.read()
        obj.close()
        content_type = "application/pdf" if filename.lower().endswith(".pdf") else "image/png"

        if should_use_gemini():
            try:
                images = pdf_or_image_to_images(data, content_type)
                extracted = extract_with_gemini(images)
                confidence = float(extracted.get("confianca_ocr") or 0.0)
                raw_text = json.dumps(extracted, ensure_ascii=False)
                engine_used = "gemini"
            except Exception as exc:  # noqa: BLE001 — Gemini indisponível/lenta: cai para OCR local
                logger.warning("Gemini falhou (manifest_id=%s): %s. Usando OCR local.", manifest_id, exc)
                raw_text, confidence, engine_used = _run_local_ocr(data, content_type)
                extracted = map_manifest(raw_text, confidence)
        elif should_use_vision_llm():
            try:
                images = pdf_or_image_to_images(data, content_type)
                extracted = extract_with_vision_llm(images)
                confidence = float(extracted.get("confianca_ocr") or 0.0)
                raw_text = json.dumps(extracted, ensure_ascii=False)
                engine_used = "vision_llm"
            except Exception as exc:  # noqa: BLE001 — IA visual indisponível/lenta: cai para OCR local
                logger.warning("IA visual falhou (manifest_id=%s): %s. Usando OCR local.", manifest_id, exc)
                raw_text, confidence, engine_used = _run_local_ocr(data, content_type)
                extracted = map_manifest(raw_text, confidence)
        elif should_use_ai_ocr():
            try:
                raw_text, confidence, engine_used = read_ai_ocr(data, filename, content_type)
            except Exception as exc:  # noqa: BLE001 — IA externa indisponível/lenta: cai para OCR local
                logger.warning("OCR/IA externo falhou (manifest_id=%s): %s. Usando OCR local.", manifest_id, exc)
                raw_text, confidence, engine_used = _run_local_ocr(data, content_type)
            extracted = map_manifest(raw_text, confidence)
        else:
            raw_text, confidence, engine_used = _run_local_ocr(data, content_type)
            extracted = map_manifest(raw_text, confidence)

        # Upsert OcrResult
        existing = db.execute(
            text("SELECT id FROM ocr_results WHERE manifest_id=:m"), {"m": manifest_id}
        ).first()
        params = {
            "m": manifest_id,
            "engine": engine_used,
            "raw": raw_text,
            "json": json.dumps(extracted, ensure_ascii=False),
            "conf": confidence,
            "review": confidence < settings.ocr_min_confidence or bool(extracted.get("necessita_revisao")),
        }
        if existing:
            db.execute(text(
                "UPDATE ocr_results SET engine=:engine, raw_text=:raw, extracted_json=:json, "
                "confidence=:conf, needs_review=:review WHERE manifest_id=:m"), params)
        else:
            db.execute(text(
                "INSERT INTO ocr_results (manifest_id, engine, raw_text, extracted_json, confidence, needs_review, created_at, updated_at) "
                "VALUES (:m, :engine, :raw, :json, :conf, :review, now(), now())"), params)

        route_id = None
        if not params["review"]:
            route_id = _auto_generate_route(db, manifest_id, branch_id, uploaded_by, extracted, existing_route_id)

        if route_id:
            db.execute(text(
                "UPDATE manifests SET status='ROTA_GERADA', route_id=:rid, ocr_confidence=:c, "
                "error_message=NULL WHERE id=:id"),
                {"rid": route_id, "c": confidence, "id": manifest_id})
        else:
            db.execute(text(
                "UPDATE manifests SET status='AGUARDANDO_CONFERENCIA', ocr_confidence=:c, "
                "error_message=NULL WHERE id=:id"),
                {"c": confidence, "id": manifest_id})
        db.commit()
        return {"manifest_id": manifest_id, "confidence": confidence, "engine": engine_used, "route_id": route_id}
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        db.execute(text("UPDATE manifests SET status='ERRO_OCR', error_message=:e WHERE id=:id"),
                   {"e": str(exc)[:500], "id": manifest_id})
        db.commit()
        return {"manifest_id": manifest_id, "error": str(exc)}
    finally:
        db.close()

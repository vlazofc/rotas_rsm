"""Aplicação Celery (notificações, cálculos e sincronização SharePoint)."""
from celery import Celery
from celery.schedules import crontab

from app.core.config import settings
from app.core.logging import logger

celery_app = Celery(
    "admmendes",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone=settings.app_timezone,
    enable_utc=True,
    beat_schedule={
        "sync-torre-controle-sharepoint": {
            "task": "sync.torre_controle",
            "schedule": crontab(minute=0),  # a cada hora; ajuste conforme a operação
        },
        "research-tax-rules-morning": {
            "task": "accounting.research_tax_rules",
            "schedule": crontab(hour=6, minute=0),
        },
        "research-tax-rules-night": {
            "task": "accounting.research_tax_rules",
            "schedule": crontab(hour=23, minute=59),
        },
        "truckcontrol-positions": {
            "task": "sync.truckcontrol_positions",
            "schedule": 30.0,
        },
        "truckcontrol-vehicles": {
            "task": "sync.truckcontrol_vehicles",
            "schedule": 300.0,
        },
    },
)


def _truckcontrol_sync(kind: str) -> dict:
    """Executa uma única rotina por vez; o lock expira se o worker cair."""
    from redis import Redis
    from sqlalchemy import select
    from app.db.models import TrackingIntegration
    from app.db.session import SessionLocal
    from app.services.truckcontrol import PROVIDER, sync_positions, sync_vehicles

    redis = Redis.from_url(settings.redis_url)
    lock = redis.lock(f"lock:truckcontrol:{kind}", timeout=25 if kind == "positions" else 240, blocking=False)
    if not lock.acquire(blocking=False):
        redis.close()
        return {"status": "skipped", "reason": "already_running"}
    db = SessionLocal()
    try:
        config = db.scalar(select(TrackingIntegration).where(
            TrackingIntegration.provider == PROVIDER, TrackingIntegration.enabled.is_(True)))
        if config is None:
            return {"status": "skipped", "reason": "not_configured"}
        result = sync_positions(db, config) if kind == "positions" else sync_vehicles(db, config)
        return {"status": "success", **result}
    except Exception as exc:
        db.rollback()
        config = locals().get("config")
        if config is not None:
            from datetime import datetime, timezone
            config.last_sync_at, config.last_error = datetime.now(timezone.utc), str(exc)[:500]
            db.commit()
        logger.exception("sync.truckcontrol_%s: falha sem exposição de credenciais", kind)
        return {"status": "error", "error": "provider_sync_failed"}
    finally:
        db.close()
        try:
            lock.release()
        except Exception:
            pass
        redis.close()


@celery_app.task(name="sync.truckcontrol_positions")
def sync_truckcontrol_positions() -> dict:
    return _truckcontrol_sync("positions")


@celery_app.task(name="sync.truckcontrol_vehicles")
def sync_truckcontrol_vehicles() -> dict:
    return _truckcontrol_sync("vehicles")


@celery_app.task(name="notifications.send")
def send_notification(user_id: int, title: str, body: str = "") -> dict:
    """Placeholder de notificação (app/email/whatsapp na Fase 4)."""
    return {"user_id": user_id, "title": title, "delivered": True}


@celery_app.task(name="accounting.research_tax_rules")
def research_tax_rules_daily() -> dict:
    """Pesquisa alterações; grava somente propostas inativas para aprovação."""
    if not settings.groq_api_key:
        logger.info("accounting.research_tax_rules: GROQ_API_KEY não configurada, pulando.")
        return {"status": "skipped", "reason": "groq_not_configured"}
    from sqlalchemy import select
    from app.db.models import Tenant
    from app.db.session import SessionLocal
    from app.services.tax_updates import research_tax_updates, stage_tax_updates
    db = SessionLocal()
    try:
        # Uma única consulta Groq por execução; o mesmo conjunto validado é
        # distribuído aos tenants sem multiplicar consumo por empresa.
        candidates = research_tax_updates()
        results = [stage_tax_updates(db, tenant_id, None, candidates) for tenant_id in db.scalars(select(Tenant.id).where(Tenant.active.is_(True))).all()]
        return {"status": "success", "candidates": len(candidates), "tenants": results}
    except Exception as exc:
        db.rollback(); logger.exception("accounting.research_tax_rules: falha: %s", exc)
        return {"status": "error", "error": str(exc)}
    finally:
        db.close()


@celery_app.task(name="sync.torre_controle")
def sync_torre_controle(branch_id: int | None = None) -> dict:
    """Baixa a planilha Torre de Controle do SharePoint do cliente e importa.

    Usada pelo agendamento (beat_schedule acima, sempre com a filial padrão)
    e pelo botão "Sincronizar agora" (app.modules.sync.router, que pode
    informar uma filial diferente). Sem SHAREPOINT_* configurado, só loga
    um aviso e retorna — não derruba o scheduler.
    """
    if not settings.sharepoint_configured:
        logger.info("sync.torre_controle: SharePoint não configurado, pulando.")
        return {"status": "skipped", "reason": "sharepoint_not_configured"}

    target_branch_id = branch_id or settings.sharepoint_sync_branch_id
    if target_branch_id is None:
        logger.info("sync.torre_controle: nenhuma filial de destino definida, pulando.")
        return {"status": "skipped", "reason": "no_branch_id"}

    from app.services.sharepoint import download_torre_controle_xlsx
    from app.services.torre_controle_import import import_workbook

    try:
        xlsx = download_torre_controle_xlsx()
        stats = import_workbook(
            xlsx,
            branch_id=target_branch_id,
            origin_address=settings.sharepoint_sync_origin_address or None,
        )
        logger.info("sync.torre_controle: importação concluída: %s", stats)
        return {"status": "success", **stats}
    except Exception as exc:  # noqa: BLE001 — tarefa de fundo, precisa registrar e seguir
        logger.exception("sync.torre_controle: falha na sincronização: %s", exc)
        return {"status": "error", "error": str(exc)}

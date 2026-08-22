"""Aplicação Celery (notificações, cálculos, disparo de OCR, sync SharePoint)."""
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
    task_routes={
        # tarefas de OCR são consumidas pelo serviço ocr-worker (fila "ocr")
        "ocr.process_manifest": {"queue": "ocr"},
    },
    beat_schedule={
        "sync-torre-controle-sharepoint": {
            "task": "sync.torre_controle",
            "schedule": crontab(minute=0),  # a cada hora; ajuste conforme a operação
        },
    },
)


@celery_app.task(name="notifications.send")
def send_notification(user_id: int, title: str, body: str = "") -> dict:
    """Placeholder de notificação (app/email/whatsapp na Fase 4)."""
    return {"user_id": user_id, "title": title, "delivered": True}


def enqueue_ocr(manifest_id: int) -> None:
    """Coloca um manifesto na fila de OCR (consumida pelo ocr-worker)."""
    celery_app.send_task("ocr.process_manifest", args=[manifest_id], queue="ocr")


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

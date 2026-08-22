"""Logging estruturado em JSON."""
import logging
import sys

from pythonjsonlogger import json as jsonlogger

from app.core.config import settings


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"asctime": "ts", "levelname": "level", "name": "logger"},
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level.upper())

    # Silencia ruído do uvicorn access em produção
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


logger = logging.getLogger("admmendes")

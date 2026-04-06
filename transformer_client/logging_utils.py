from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOG_FILE_NAME = "client-live.log"


def setup_logging(workdir: Path) -> Path:
    root_logger = logging.getLogger()
    if getattr(root_logger, "_transformer_client_logging_ready", False):
        return workdir / LOG_FILE_NAME

    log_path = workdir / LOG_FILE_NAME
    handler = RotatingFileHandler(
        log_path,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)
    root_logger._transformer_client_logging_ready = True  # type: ignore[attr-defined]
    return log_path

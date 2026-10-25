"""Конфигурация системы логирования с поддержкой ротации файлов."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from valutatrade_hub.infra.settings import SettingsLoader

LOGGER_NAME = "valutatrade.actions"


def setup_logging() -> logging.Logger:
    """Настраивает и возвращает логгер доменных операций с файловой ротацией."""
    settings = SettingsLoader()
    log_file = Path(settings.get("LOG_FILE", "logs/actions.log"))
    log_level_name = str(settings.get("LOG_LEVEL", "INFO")).upper()
    max_bytes = int(settings.get("LOG_MAX_BYTES", 1_048_576))
    backup_count = int(settings.get("LOG_BACKUP_COUNT", 5))

    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(LOGGER_NAME)
    level = getattr(logging, log_level_name, logging.INFO)
    logger.setLevel(level)
    logger.propagate = False

    if not logger.handlers:
        handler = RotatingFileHandler(
            filename=log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        formatter = logging.Formatter("%(levelname)s %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def get_action_logger() -> logging.Logger:
    """Возвращает настроенный экземпляр логгера операций."""
    return setup_logging()

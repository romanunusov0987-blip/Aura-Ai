"""Конфигурация логирования административного бота."""
from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(log_file: Path) -> logging.Logger:
    """Настраивает логирование и возвращает основной логгер."""

    logger = logging.getLogger("admin_bot")
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Потоковый вывод (консоль)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    # Файловый вывод
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

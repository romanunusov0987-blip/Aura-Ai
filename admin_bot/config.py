"""Настройки административного бота."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Set

from dotenv import load_dotenv


@dataclass(slots=True)
class Settings:
    """Описание конфигурации административного бота."""

    token: str
    admin_ids: Set[int]
    database_path: Path
    log_file: Path


def load_settings() -> Settings:
    """Загружает настройки из переменных окружения."""

    load_dotenv()

    token = os.getenv("ADMIN_TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Не задан ADMIN_TELEGRAM_BOT_TOKEN")

    raw_admins = os.getenv("ADMIN_USER_IDS", "")
    admin_ids: Set[int] = {
        int(user_id.strip())
        for user_id in raw_admins.split(",")
        if user_id.strip()
    }
    if not admin_ids:
        raise RuntimeError(
            "Перечень администраторов пуст. Укажите ADMIN_USER_IDS через запятую."
        )

    database_path = Path(os.getenv("ADMIN_DATABASE_PATH", "admin_panel.db")).resolve()
    log_file = Path(os.getenv("ADMIN_LOG_FILE", "admin_panel.log")).resolve()

    # Убеждаемся, что каталоги для файлов существуют.
    database_path.parent.mkdir(parents=True, exist_ok=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    return Settings(
        token=token,
        admin_ids=admin_ids,
        database_path=database_path,
        log_file=log_file,
    )

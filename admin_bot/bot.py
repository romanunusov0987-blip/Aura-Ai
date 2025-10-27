"""Точка входа административного бота."""
from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

from .commands import create_router
from .config import load_settings
from .database import Database
from .logging_config import configure_logging


async def main() -> None:
    settings = load_settings()
    logger = configure_logging(settings.log_file)

    bot = Bot(settings.token, parse_mode=ParseMode.HTML)
    dispatcher = Dispatcher()

    database = Database(settings.database_path)
    await database.connect()
    await database.init_models()

    dispatcher.include_router(create_router(database, settings.admin_ids, logger))

    logger.info("Административный бот запущен")

    try:
        await dispatcher.start_polling(bot)
    finally:
        await database.close()
        await bot.session.close()
        logger.info("Административный бот остановлен")


if __name__ == "__main__":
    asyncio.run(main())

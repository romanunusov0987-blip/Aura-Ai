"""Маршруты команд административного бота."""
from __future__ import annotations

import asyncio
from logging import Logger
from typing import Iterable

from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import BaseFilter, Command, CommandObject, CommandStart
from aiogram.types import Message
from aiogram.exceptions import TelegramForbiddenError

from .database import Database


class AdminFilter(BaseFilter):
    """Разрешает доступ к хендлеру только администраторам."""

    def __init__(self, admin_ids: Iterable[int]) -> None:
        self._admin_ids = set(admin_ids)

    async def __call__(self, message: Message) -> bool:
        return bool(message.from_user and message.from_user.id in self._admin_ids)


def create_router(db: Database, admin_ids: Iterable[int], logger: Logger) -> Router:
    router = Router()
    admin_filter = AdminFilter(admin_ids)

    @router.message(CommandStart())
    async def cmd_start(message: Message) -> None:
        from_user = message.from_user
        if not from_user:
            return

        await db.upsert_user(
            user_id=from_user.id,
            username=from_user.username,
            first_name=from_user.first_name,
            last_name=from_user.last_name,
        )

        if await db.is_banned(from_user.id):
            await message.answer(
                "Вы заблокированы и не можете пользоваться ботом."
            )
            return

        await message.answer(
            "Привет! Этот бот собирает пользователей и предоставляет админ-панель."
        )

    @router.message(~Command())
    async def register_user(message: Message) -> None:
        if not message.text:
            return
        from_user = message.from_user
        if not from_user:
            return

        await db.upsert_user(
            user_id=from_user.id,
            username=from_user.username,
            first_name=from_user.first_name,
            last_name=from_user.last_name,
        )

        if await db.is_banned(from_user.id):
            await message.answer(
                "Вы заблокированы. Обратитесь к администратору."
            )
            return

    @router.message(admin_filter, Command("stats"))
    async def cmd_stats(message: Message) -> None:
        stats = await db.get_stats()
        response = (
            "<b>Статистика пользователей</b>\n"
            f"Всего: {stats['total']}\n"
            f"Активных: {stats['active']}\n"
            f"Забанено: {stats['banned']}"
        )
        await message.answer(response, parse_mode=ParseMode.HTML)
        await db.log_action(message.from_user.id, "stats")
        logger.info("Admin %s запросил статистику", message.from_user.id)

    @router.message(admin_filter, Command("users"))
    async def cmd_users(message: Message, command: CommandObject) -> None:
        limit = 20
        if command.args and command.args.isdigit():
            limit = max(1, min(100, int(command.args)))

        users = await db.list_users(limit=limit)
        if not users:
            await message.answer("Пользователи пока не зарегистрированы.")
            return

        parts = []
        for user in users:
            name = user.get("username") or user.get("first_name") or "—"
            parts.append(
                f"<b>{user['user_id']}</b>: {name}"
                f" (заблокирован: {'да' if user['is_banned'] else 'нет'})"
            )
        text = "\n".join(parts)
        await message.answer(text, parse_mode=ParseMode.HTML)
        await db.log_action(message.from_user.id, "users", payload=f"limit={limit}")
        logger.info(
            "Admin %s запросил список пользователей (limit=%s)",
            message.from_user.id,
            limit,
        )

    @router.message(admin_filter, Command("ban"))
    async def cmd_ban(message: Message, command: CommandObject) -> None:
        if not command.args or not command.args.isdigit():
            await message.answer("Укажите ID пользователя: /ban 123456")
            return
        target_id = int(command.args)
        updated = await db.mark_ban(target_id, True)
        if not updated:
            await message.answer("Пользователь не найден.")
            return
        await db.log_action(message.from_user.id, "ban", target_user_id=target_id)
        logger.warning("Admin %s заблокировал %s", message.from_user.id, target_id)
        await message.answer(f"Пользователь {target_id} заблокирован.")

    @router.message(admin_filter, Command("unban"))
    async def cmd_unban(message: Message, command: CommandObject) -> None:
        if not command.args or not command.args.isdigit():
            await message.answer("Укажите ID пользователя: /unban 123456")
            return
        target_id = int(command.args)
        updated = await db.mark_ban(target_id, False)
        if not updated:
            await message.answer("Пользователь не найден.")
            return
        await db.log_action(message.from_user.id, "unban", target_user_id=target_id)
        logger.warning("Admin %s разблокировал %s", message.from_user.id, target_id)
        await message.answer(f"Пользователь {target_id} разблокирован.")

    @router.message(admin_filter, Command("broadcast"))
    async def cmd_broadcast(message: Message, command: CommandObject) -> None:
        if not command.args:
            await message.answer(
                "Использование: /broadcast Текст рассылки"
            )
            return

        sent = 0
        failed = 0
        text = command.args

        async def send_one(user_id: int) -> None:
            nonlocal sent, failed
            try:
                await message.bot.send_message(user_id, text)
                sent += 1
            except TelegramForbiddenError:
                failed += 1
            except Exception as exc:  # noqa: BLE001
                logger.exception("Не удалось отправить сообщение %s: %s", user_id, exc)
                failed += 1

        tasks = [send_one(user_id) async for user_id in db.get_audience()]
        if not tasks:
            await message.answer("Нет активных пользователей для рассылки.")
            return

        await asyncio.gather(*tasks)

        await db.log_action(
            message.from_user.id,
            "broadcast",
            payload=f"sent={sent};failed={failed}"
        )
        logger.info(
            "Admin %s отправил рассылку (успех %s, ошибки %s)",
            message.from_user.id,
            sent,
            failed,
        )
        await message.answer(
            f"Рассылка завершена. Успешно: {sent}. Ошибок: {failed}."
        )

    return router

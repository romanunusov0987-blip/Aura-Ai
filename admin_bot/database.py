"""Работа с базой данных административного бота."""
from __future__ import annotations

from pathlib import Path
import aiosqlite
from typing import AsyncIterator, Optional


class Database:
    """Обёртка над SQLite для хранения пользователей и логов."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._connection: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self._connection = await aiosqlite.connect(str(self._path))
        self._connection.row_factory = aiosqlite.Row

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("База данных не подключена")
        return self._connection

    async def init_models(self) -> None:
        """Создаёт таблицы при первом запуске."""

        await self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                is_banned INTEGER DEFAULT 0,
                joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_seen TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                target_user_id INTEGER,
                payload TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        await self.connection.commit()

    async def upsert_user(
        self,
        user_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> None:
        """Создаёт или обновляет пользователя."""

        await self.connection.execute(
            """
            INSERT INTO users (user_id, username, first_name, last_name)
            VALUES (:user_id, :username, :first_name, :last_name)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                last_seen = CURRENT_TIMESTAMP
            """,
            {
                "user_id": user_id,
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
            },
        )
        await self.connection.commit()

    async def mark_ban(self, user_id: int, banned: bool) -> bool:
        """Помечает пользователя заблокированным/разблокированным."""

        async with self.connection.execute(
            "SELECT user_id FROM users WHERE user_id = :user_id",
            {"user_id": user_id},
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return False

        await self.connection.execute(
            "UPDATE users SET is_banned = :is_banned WHERE user_id = :user_id",
            {"user_id": user_id, "is_banned": int(banned)},
        )
        await self.connection.commit()
        return True

    async def is_banned(self, user_id: int) -> bool:
        async with self.connection.execute(
            "SELECT is_banned FROM users WHERE user_id = :user_id",
            {"user_id": user_id},
        ) as cursor:
            row = await cursor.fetchone()
            return bool(row["is_banned"]) if row else False

    async def list_users(self, limit: int = 20) -> list[dict[str, object]]:
        async with self.connection.execute(
            """
            SELECT user_id, username, first_name, last_name, is_banned, joined_at, last_seen
            FROM users
            ORDER BY joined_at DESC
            LIMIT :limit
            """,
            {"limit": limit},
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_stats(self) -> dict[str, int]:
        async with self.connection.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN is_banned = 0 THEN 1 ELSE 0 END) AS active,
                SUM(CASE WHEN is_banned = 1 THEN 1 ELSE 0 END) AS banned
            FROM users
            """
        ) as cursor:
            row = await cursor.fetchone()
            return {
                "total": row["total"] or 0,
                "active": row["active"] or 0,
                "banned": row["banned"] or 0,
            }

    async def get_audience(self) -> AsyncIterator[int]:
        async with self.connection.execute(
            "SELECT user_id FROM users WHERE is_banned = 0"
        ) as cursor:
            async for row in cursor:
                yield row["user_id"]

    async def log_action(
        self,
        admin_id: int,
        action: str,
        target_user_id: int | None = None,
        payload: str | None = None,
    ) -> None:
        await self.connection.execute(
            """
            INSERT INTO admin_logs (admin_id, action, target_user_id, payload)
            VALUES (:admin_id, :action, :target_user_id, :payload)
            """,
            {
                "admin_id": admin_id,
                "action": action,
                "target_user_id": target_user_id,
                "payload": payload,
            },
        )
        await self.connection.commit()

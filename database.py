from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

import aiosqlite


SCHEMA = """
CREATE TABLE IF NOT EXISTS operators (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id       INTEGER UNIQUE NOT NULL,
    full_name   TEXT    NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 1,
    is_online   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS chats (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_tg_id      INTEGER NOT NULL,
    user_name       TEXT    NOT NULL,
    user_question   TEXT,
    operator_tg_id  INTEGER,
    status          TEXT    NOT NULL,   -- 'waiting' | 'active' | 'ended'
    started_at      TEXT    NOT NULL,
    ended_at        TEXT
);

CREATE INDEX IF NOT EXISTS idx_chats_user     ON chats(user_tg_id, status);
CREATE INDEX IF NOT EXISTS idx_chats_operator ON chats(operator_tg_id, status);
CREATE INDEX IF NOT EXISTS idx_chats_status   ON chats(status);
"""


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def init(self) -> None:
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not initialized — call init() first")
        return self._conn

    # ---------- Operators ----------

    async def add_operator(self, tg_id: int, full_name: str) -> bool:
        async with self._lock:
            cur = await self.conn.execute(
                "INSERT OR IGNORE INTO operators (tg_id, full_name, created_at) VALUES (?, ?, ?)",
                (tg_id, full_name, _now()),
            )
            await self.conn.commit()
            return cur.rowcount > 0

    async def remove_operator(self, tg_id: int) -> bool:
        async with self._lock:
            cur = await self.conn.execute("DELETE FROM operators WHERE tg_id = ?", (tg_id,))
            await self.conn.commit()
            return cur.rowcount > 0

    async def get_operator(self, tg_id: int) -> Optional[dict]:
        cur = await self.conn.execute("SELECT * FROM operators WHERE tg_id = ?", (tg_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def list_operators(self) -> list[dict]:
        cur = await self.conn.execute("SELECT * FROM operators ORDER BY id")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def set_operator_online(self, tg_id: int, online: bool) -> None:
        async with self._lock:
            await self.conn.execute(
                "UPDATE operators SET is_online = ? WHERE tg_id = ?",
                (1 if online else 0, tg_id),
            )
            await self.conn.commit()

    async def find_free_operator(self) -> Optional[dict]:
        """Onlayn, aktiv va hech qaysi suhbatda bo'lmagan operator."""
        cur = await self.conn.execute(
            """
            SELECT o.* FROM operators o
            WHERE o.is_active = 1 AND o.is_online = 1
              AND NOT EXISTS (
                  SELECT 1 FROM chats c
                  WHERE c.operator_tg_id = o.tg_id AND c.status = 'active'
              )
            ORDER BY o.id
            LIMIT 1
            """
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    # ---------- Chats ----------

    async def create_waiting_chat(self, user_tg_id: int, user_name: str, question: str) -> int:
        async with self._lock:
            cur = await self.conn.execute(
                """INSERT INTO chats (user_tg_id, user_name, user_question, status, started_at)
                   VALUES (?, ?, ?, 'waiting', ?)""",
                (user_tg_id, user_name, question, _now()),
            )
            await self.conn.commit()
            return cur.lastrowid  # type: ignore[return-value]

    async def assign_operator(self, chat_id: int, operator_tg_id: int) -> None:
        async with self._lock:
            await self.conn.execute(
                "UPDATE chats SET operator_tg_id = ?, status = 'active' WHERE id = ?",
                (operator_tg_id, chat_id),
            )
            await self.conn.commit()

    async def end_chat(self, chat_id: int) -> None:
        async with self._lock:
            await self.conn.execute(
                "UPDATE chats SET status = 'ended', ended_at = ? WHERE id = ?",
                (_now(), chat_id),
            )
            await self.conn.commit()

    async def get_active_chat_by_user(self, user_tg_id: int) -> Optional[dict]:
        cur = await self.conn.execute(
            """SELECT * FROM chats
               WHERE user_tg_id = ? AND status IN ('waiting', 'active')
               ORDER BY id DESC LIMIT 1""",
            (user_tg_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def get_active_chat_by_operator(self, operator_tg_id: int) -> Optional[dict]:
        cur = await self.conn.execute(
            """SELECT * FROM chats
               WHERE operator_tg_id = ? AND status = 'active'
               ORDER BY id DESC LIMIT 1""",
            (operator_tg_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def get_oldest_waiting_chat(self) -> Optional[dict]:
        cur = await self.conn.execute(
            "SELECT * FROM chats WHERE status = 'waiting' ORDER BY id ASC LIMIT 1"
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def get_stats(self) -> dict:
        out: dict = {}
        queries = {
            "total_operators":   "SELECT COUNT(*) AS c FROM operators",
            "online_operators":  "SELECT COUNT(*) AS c FROM operators WHERE is_online=1 AND is_active=1",
            "waiting":           "SELECT COUNT(*) AS c FROM chats WHERE status='waiting'",
            "active":            "SELECT COUNT(*) AS c FROM chats WHERE status='active'",
            "total_chats":       "SELECT COUNT(*) AS c FROM chats",
            "ended_today":       "SELECT COUNT(*) AS c FROM chats WHERE status='ended' AND DATE(ended_at)=DATE('now')",
        }
        for key, q in queries.items():
            cur = await self.conn.execute(q)
            row = await cur.fetchone()
            out[key] = row["c"] if row else 0
        return out

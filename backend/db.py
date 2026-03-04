import re

import asyncpg

from config import settings

_pool: asyncpg.Pool | None = None

SCHEMA_STATEMENTS = [
    """\
    CREATE TABLE IF NOT EXISTS sessions (
        id         TEXT PRIMARY KEY,
        user_id    TEXT NOT NULL,
        started_at TEXT NOT NULL,
        ended_at   TEXT,
        status     TEXT NOT NULL DEFAULT 'active',
        mode       TEXT NOT NULL DEFAULT 'conversation',
        topic_id   TEXT
    )""",
    """\
    CREATE TABLE IF NOT EXISTS segments (
        id         SERIAL PRIMARY KEY,
        session_id TEXT NOT NULL REFERENCES sessions(id),
        turn_index INTEGER NOT NULL,
        user_text  TEXT NOT NULL,
        ai_text    TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(session_id, turn_index)
    )""",
    """\
    CREATE TABLE IF NOT EXISTS ai_marks (
        id          SERIAL PRIMARY KEY,
        segment_id  INTEGER NOT NULL REFERENCES segments(id),
        issue_types TEXT NOT NULL,
        original    TEXT NOT NULL,
        suggestion  TEXT NOT NULL,
        explanation TEXT NOT NULL
    )""",
    """\
    CREATE TABLE IF NOT EXISTS corrections (
        id              SERIAL PRIMARY KEY,
        session_id      TEXT NOT NULL REFERENCES sessions(id),
        segment_id      INTEGER NOT NULL REFERENCES segments(id),
        user_message    TEXT NOT NULL,
        correction      TEXT NOT NULL,
        explanation     TEXT NOT NULL,
        created_at      TEXT NOT NULL
    )""",
    """\
    CREATE TABLE IF NOT EXISTS user_profiles (
        user_id      TEXT PRIMARY KEY,
        level        TEXT,
        learning_goal TEXT,
        profile_data TEXT NOT NULL DEFAULT '{}',
        updated_at   TEXT NOT NULL
    )""",
    """\
    CREATE TABLE IF NOT EXISTS session_summaries (
        session_id       TEXT PRIMARY KEY REFERENCES sessions(id),
        user_id          TEXT NOT NULL,
        strengths        TEXT NOT NULL,
        weaknesses       TEXT NOT NULL,
        overall          TEXT NOT NULL,
        created_at       TEXT NOT NULL
    )""",
    """\
    CREATE TABLE IF NOT EXISTS chat_summaries (
        session_id TEXT PRIMARY KEY REFERENCES sessions(id),
        topic_id   TEXT NOT NULL,
        summary    TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """\
    CREATE TABLE IF NOT EXISTS review_summaries (
        session_id   TEXT PRIMARY KEY REFERENCES sessions(id),
        user_id      TEXT NOT NULL,
        practiced    TEXT NOT NULL,
        notes        TEXT NOT NULL,
        created_at   TEXT NOT NULL
    )""",
]


def _convert_placeholders(sql: str) -> str:
    """Convert SQLite-style ? placeholders to PostgreSQL $1, $2, ... style."""
    counter = 0

    def replacer(match):
        nonlocal counter
        counter += 1
        return f"${counter}"

    return re.sub(r"\?", replacer, sql)


class Database:
    """Wrapper around asyncpg pool that provides an aiosqlite-compatible interface."""

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def execute_fetchall(self, sql: str, params: tuple | list = ()) -> list[dict]:
        """Execute a query and return all rows as list of dicts."""
        converted = _convert_placeholders(sql)
        rows = await self._pool.fetch(converted, *params)
        return [dict(r) for r in rows]

    async def execute(self, sql: str, params: tuple | list = ()) -> dict | None:
        """Execute a statement. If SQL contains RETURNING, fetch and return the row as dict."""
        converted = _convert_placeholders(sql)
        if "RETURNING" in converted.upper() or "returning" in converted:
            row = await self._pool.fetchrow(converted, *params)
            return dict(row) if row else None
        await self._pool.execute(converted, *params)
        return None

    async def commit(self) -> None:
        """No-op: asyncpg auto-commits each statement."""
        pass


_db: Database | None = None


async def init_db() -> None:
    global _pool, _db
    _pool = await asyncpg.create_pool(dsn=settings.DATABASE_URL)
    _db = Database(_pool)
    async with _pool.acquire() as conn:
        for stmt in SCHEMA_STATEMENTS:
            await conn.execute(stmt)
        await conn.execute(
            "ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS learning_goal TEXT"
        )


async def get_db() -> Database:
    if _db is None:
        raise RuntimeError("Database not initialized — call init_db() first")
    return _db


async def close_db() -> None:
    global _pool, _db
    if _pool is not None:
        await _pool.close()
        _pool = None
        _db = None

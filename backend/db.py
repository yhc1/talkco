import aiosqlite

from config import settings

_db: aiosqlite.Connection | None = None

SCHEMA = """\
CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at   TEXT,
    status     TEXT NOT NULL DEFAULT 'active',
    mode       TEXT NOT NULL DEFAULT 'conversation'
);

CREATE TABLE IF NOT EXISTS segments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    turn_index INTEGER NOT NULL,
    user_text  TEXT NOT NULL,
    ai_text    TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(session_id, turn_index)
);

CREATE TABLE IF NOT EXISTS ai_marks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_id  INTEGER NOT NULL REFERENCES segments(id),
    issue_types TEXT NOT NULL,   -- JSON array: ["grammar", "naturalness", ...]
    original    TEXT NOT NULL,
    suggestion  TEXT NOT NULL,
    explanation TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS corrections (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL REFERENCES sessions(id),
    segment_id      INTEGER NOT NULL REFERENCES segments(id),
    user_message    TEXT NOT NULL,
    correction      TEXT NOT NULL,
    explanation     TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id      TEXT PRIMARY KEY,
    level        TEXT NOT NULL DEFAULT 'intermediate',
    profile_data TEXT NOT NULL DEFAULT '{}',
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_summaries (
    session_id       TEXT PRIMARY KEY REFERENCES sessions(id),
    user_id          TEXT NOT NULL,
    strengths        TEXT NOT NULL,      -- JSON array
    weaknesses       TEXT NOT NULL,      -- JSON object { grammar: "...", ... }
    overall          TEXT NOT NULL,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_summaries (
    session_id TEXT PRIMARY KEY REFERENCES sessions(id),
    topic_id   TEXT NOT NULL,
    summary    TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_summaries (
    session_id   TEXT PRIMARY KEY REFERENCES sessions(id),
    user_id      TEXT NOT NULL,
    practiced    TEXT NOT NULL,
    notes        TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
"""


async def init_db() -> None:
    global _db
    _db = await aiosqlite.connect(settings.DB_PATH)
    _db.row_factory = aiosqlite.Row
    await _db.executescript(SCHEMA)
    await _db.execute("PRAGMA foreign_keys = ON")

    # Migration: add mode column to sessions if missing
    cols = await _db.execute_fetchall("PRAGMA table_info(sessions)")
    col_names = [c["name"] for c in cols]
    if "mode" not in col_names:
        await _db.execute("ALTER TABLE sessions ADD COLUMN mode TEXT NOT NULL DEFAULT 'conversation'")
    if "topic_id" not in col_names:
        await _db.execute("ALTER TABLE sessions ADD COLUMN topic_id TEXT")

    # Migration: drop level_assessment from session_summaries if present
    ss_cols = await _db.execute_fetchall("PRAGMA table_info(session_summaries)")
    ss_col_names = [c["name"] for c in ss_cols]
    if "level_assessment" in ss_col_names:
        await _db.execute("ALTER TABLE session_summaries DROP COLUMN level_assessment")

    # Migration: add user_id and created_at to session_summaries
    if "user_id" not in ss_col_names:
        await _db.execute("ALTER TABLE session_summaries ADD COLUMN user_id TEXT NOT NULL DEFAULT ''")
    if "created_at" not in ss_col_names:
        await _db.execute("ALTER TABLE session_summaries ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")

    # Migration: add created_at to chat_summaries
    cs_cols = await _db.execute_fetchall("PRAGMA table_info(chat_summaries)")
    cs_col_names = [c["name"] for c in cs_cols]
    if "created_at" not in cs_col_names:
        await _db.execute("ALTER TABLE chat_summaries ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")

    await _db.commit()


async def get_db() -> aiosqlite.Connection:
    if _db is None:
        raise RuntimeError("Database not initialized — call init_db() first")
    return _db


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None

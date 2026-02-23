import asyncio
import logging
import uuid
from datetime import datetime, timezone

from db import get_db
from providers.openai_s2s import RealtimeSession
from review import generate_review

log = logging.getLogger(__name__)

_sessions: dict[str, RealtimeSession] = {}
_session_user_ids: dict[str, str] = {}


async def create_session(user_id: str) -> dict:
    session_id = str(uuid.uuid4())
    session = RealtimeSession(session_id)
    _sessions[session_id] = session
    _session_user_ids[session_id] = user_id

    now = datetime.now(timezone.utc).isoformat()

    # Persist to DB
    db = await get_db()
    await db.execute(
        "INSERT INTO sessions (id, user_id, started_at, status) VALUES (?, ?, ?, ?)",
        (session_id, user_id, now, "active"),
    )
    await db.commit()

    # Connect in background so the endpoint can return immediately
    asyncio.create_task(_connect_with_retry(session_id, session))

    return {
        "session_id": session_id,
        "created_at": now,
    }


async def _connect_with_retry(session_id: str, session: RealtimeSession) -> None:
    try:
        await session.connect()
        log.info("Session %s connected", session_id)
    except Exception as e:
        log.error("Failed to connect session %s: %s", session_id, e)
        _sessions.pop(session_id, None)


def get_session(session_id: str) -> RealtimeSession | None:
    return _sessions.get(session_id)


def get_session_user_id(session_id: str) -> str | None:
    return _session_user_ids.get(session_id)


async def delete_session(session_id: str) -> bool:
    session = _sessions.pop(session_id, None)
    if session is None:
        return False
    await session.close()

    now = datetime.now(timezone.utc).isoformat()
    db = await get_db()
    await db.execute(
        "UPDATE sessions SET status = ?, ended_at = ? WHERE id = ?",
        ("reviewing", now, session_id),
    )
    await db.commit()

    # Launch review generation in background
    asyncio.create_task(_run_review(session_id))

    log.info("Session %s ended, review generation started", session_id)
    return True


async def _run_review(session_id: str) -> None:
    try:
        await generate_review(session_id)
        log.info("Review generated for session %s", session_id)
    except Exception as e:
        log.error("Failed to generate review for session %s: %s", session_id, e)

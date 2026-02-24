import asyncio
import logging
import uuid
from datetime import datetime, timezone

from db import get_db
from profile import get_or_create_profile
from providers.openai_s2s import RealtimeSession
from review import generate_review

log = logging.getLogger(__name__)

_sessions: dict[str, RealtimeSession] = {}
_session_user_ids: dict[str, str] = {}


def _build_learner_summary(profile: dict) -> str:
    """Build a brief learner summary string from profile data."""
    level = profile.get("level", "intermediate")
    data = profile.get("profile_data", {})
    session_count = data.get("session_count", 0)

    parts = [f"Level: {level}", f"Sessions completed: {session_count}"]

    weak_points = data.get("weak_points", {})
    if isinstance(weak_points, dict):
        weak_items = []
        for dim, points in weak_points.items():
            if points:
                weak_items.append(f"{dim}: {', '.join(points[:2])}")
        if weak_items:
            parts.append(f"Weak points: {'; '.join(weak_items)}")
    elif isinstance(weak_points, list) and weak_points:
        parts.append(f"Weak points: {', '.join(str(p) for p in weak_points[:4])}")

    return ". ".join(parts)


async def create_session(user_id: str, topic: dict) -> dict:
    session_id = str(uuid.uuid4())

    # Fetch learner profile for context
    profile = await get_or_create_profile(user_id)
    learner_summary = _build_learner_summary(profile)

    # Build topic string from structured topic dict
    topic_label = topic.get("label_en", "free conversation")
    prompt_hint = topic.get("prompt_hint", "")
    topic_str = f"{topic_label} — {prompt_hint}" if prompt_hint else topic_label

    session = RealtimeSession(session_id, topic=topic_str, learner_summary=learner_summary)
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

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from constants import SessionMode, SessionStatus, DIMENSION_LABELS
from db import get_db
from profile import get_or_create_profile
from providers.openai_s2s import RealtimeSession
from profile import update_profile_after_session
from review import generate_review, generate_review_summary

log = logging.getLogger(__name__)

_sessions: dict[str, RealtimeSession] = {}
_session_user_ids: dict[str, str] = {}
_session_modes: dict[str, str] = {}


def _build_weak_points_for_review(profile: dict) -> str:
    """Build a detailed weak points description for review mode."""
    data = profile.get("profile_data", {})
    weak_points = data.get("weak_points", {})
    if not isinstance(weak_points, dict):
        return ""

    lines = []
    for dim, labels in DIMENSION_LABELS.items():
        label = labels["en"]
        patterns = weak_points.get(dim, [])
        if not patterns:
            continue
        # Take top 3 patterns per dimension
        for p in patterns[:3]:
            if isinstance(p, dict):
                lines.append(f"- [{label}] {p['pattern']}")
                for ex in p.get("examples", [])[:3]:
                    lines.append(f"  Wrong: \"{ex['wrong']}\" → Correct: \"{ex['correct']}\"")
            elif isinstance(p, str):
                lines.append(f"- [{label}] {p}")

    return "\n".join(lines) if lines else ""


async def create_session(user_id: str, topic: dict | None = None, mode: str = SessionMode.CONVERSATION) -> dict:
    session_id = str(uuid.uuid4())
    profile = await get_or_create_profile(user_id)
    topic_id = topic.get("id") if topic else None
    history_summaries: list[str] = []
    # Query same-topic chat history for conversation mode
    # TODO: Extract retrieve chat history number to a configuration file.
    if mode == SessionMode.CONVERSATION and topic_id:
        db = await get_db()
        rows = await db.execute_fetchall(
            "SELECT cs.summary FROM chat_summaries cs "
            "JOIN sessions s ON cs.session_id = s.id "
            "WHERE s.user_id = ? AND cs.topic_id = ? "
            "ORDER BY s.started_at DESC LIMIT 5",
            (user_id, topic_id),
        )
        history_summaries = [r["summary"] for r in rows]

    review_history: list[str] | None = None
    if mode == SessionMode.REVIEW:
        db = await get_db()
        rows = await db.execute_fetchall(
            "SELECT rs.notes FROM review_summaries rs "
            "JOIN sessions s ON rs.session_id = s.id "
            "WHERE s.user_id = ? ORDER BY rs.created_at DESC LIMIT 5",
            (user_id,),
        )
        review_history = [r["notes"] for r in rows] or None

    session = RealtimeSession(
        session_id, mode=mode, profile=profile, topic=topic.get("label_en") if topic else None,
        conversation_history_summary=history_summaries or None,
        review_history=review_history,
    )
    _sessions[session_id] = session
    _session_user_ids[session_id] = user_id
    _session_modes[session_id] = mode

    now = datetime.now(timezone.utc).isoformat()

    # Persist to DB
    db = await get_db()
    await db.execute(
        "INSERT INTO sessions (id, user_id, started_at, status, mode, topic_id) VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, user_id, now, SessionStatus.ACTIVE, mode, topic_id),
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


def get_session_mode(session_id: str) -> str:
    return _session_modes.get(session_id, SessionMode.CONVERSATION)


async def delete_session(session_id: str) -> dict | None:
    session = _sessions.pop(session_id, None)
    if session is None:
        return None
    mode = _session_modes.pop(session_id, SessionMode.CONVERSATION)
    await session.close()

    now = datetime.now(timezone.utc).isoformat()
    db = await get_db()

    if mode == SessionMode.REVIEW:
        # Review mode: skip AI marks generation, just mark as ended
        await db.execute(
            "UPDATE sessions SET status = ?, ended_at = ? WHERE id = ?",
            (SessionStatus.ENDED, now, session_id),
        )
        await db.commit()
        log.info("Review session %s ended (no review generation)", session_id)

        user_id = _session_user_ids.pop(session_id, None)
        if user_id:
            asyncio.create_task(_finalize_review(session_id, user_id))

        return {"session_id": session_id, "status": SessionStatus.ENDED, "mode": mode}

    await db.execute(
        "UPDATE sessions SET status = ?, ended_at = ? WHERE id = ?",
        (SessionStatus.REVIEWING, now, session_id),
    )
    await db.commit()

    # Launch review generation in background
    asyncio.create_task(_run_review(session_id))

    log.info("Session %s ended, review generation started", session_id)
    return {"session_id": session_id, "status": SessionStatus.REVIEWING, "mode": mode}


async def _run_review(session_id: str) -> None:
    try:
        await generate_review(session_id)
        log.info("Review generated for session %s", session_id)
    except Exception as e:
        log.error("Failed to generate review for session %s: %s", session_id, e)


async def _finalize_review(session_id: str, user_id: str) -> None:
    """Background task: generate review summary and update profile after review session."""
    try:
        await asyncio.gather(
            generate_review_summary(session_id, user_id),
            update_profile_after_session(user_id, session_id),
        )
        log.info("Review session %s finalized for user %s", session_id, user_id)
    except Exception as e:
        log.error("Failed to finalize review session %s: %s", session_id, e)

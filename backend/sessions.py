import asyncio
import json
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
_session_modes: dict[str, str] = {}


def _build_learner_summary(profile: dict) -> str:
    """Build a brief learner summary string from profile data."""
    parts = []
    level = profile.get("level")
    if level:
        parts.append([f"Level: {level}"])
    data = profile.get("profile_data")

    weak_points = data.get("weak_points", {})
    if isinstance(weak_points, dict):
        weak_items = []
        for dim, patterns in weak_points.items():
            if patterns:
                if isinstance(patterns[0], dict):
                    names = [p["pattern"] for p in patterns[:2]]
                    weak_items.append(f"{dim}: {', '.join(names)}")
                elif isinstance(patterns[0], str):
                    weak_items.append(f"{dim}: {', '.join(patterns[:2])}")
        if weak_items:
            parts.append(f"Weak points: {'; '.join(weak_items)}")
    elif isinstance(weak_points, list) and weak_points:
        parts.append(f"Weak points: {', '.join(str(p) for p in weak_points[:4])}")

    return ". ".join(parts)


def _build_weak_points_for_review(profile: dict) -> str:
    """Build a detailed weak points description for review mode."""
    data = profile.get("profile_data", {})
    weak_points = data.get("weak_points", {})
    if not isinstance(weak_points, dict):
        return ""

    dim_labels = {
        "grammar": "Grammar",
        "naturalness": "Naturalness",
        "vocabulary": "Vocabulary",
        "sentence_structure": "Sentence Structure",
    }

    lines = []
    for dim, label in dim_labels.items():
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


async def create_session(user_id: str, topic: dict | None = None, mode: str = "conversation") -> dict:
    session_id = str(uuid.uuid4())

    # Fetch learner profile for context
    profile = await get_or_create_profile(user_id)
    learner_summary = _build_learner_summary(profile)

    topic_str = "free conversation"
    weak_points_detail = ""
    topic_id = None
    history_summaries: list[str] = []

    if mode == "review":
        weak_points_detail = _build_weak_points_for_review(profile)
        topic_str = "weak point review"
    elif topic:
        topic_id = topic.get("id")
        topic_label = topic.get("label_en", "free conversation")
        prompt_hint = topic.get("prompt_hint", "")
        topic_str = f"{topic_label} — {prompt_hint}" if prompt_hint else topic_label

    # Query same-topic chat history for conversation mode
    if mode == "conversation" and topic_id:
        db = await get_db()
        rows = await db.execute_fetchall(
            "SELECT cs.summary FROM chat_summaries cs "
            "JOIN sessions s ON cs.session_id = s.id "
            "WHERE s.user_id = ? AND cs.topic_id = ? "
            "ORDER BY s.started_at DESC LIMIT 5",
            (user_id, topic_id),
        )
        history_summaries = [r["summary"] for r in rows]
        if history_summaries:
            log.info("Found %d prior chat summaries for topic %s", len(history_summaries), topic_id)

    log.info(
        "Session context for user=%s: level=%s, mode=%s, learner_summary=%s",
        user_id,
        profile.get("level", "unknown"),
        mode,
        learner_summary,
    )

    session = RealtimeSession(
        session_id, topic=topic_str, learner_summary=learner_summary,
        mode=mode, weak_points_detail=weak_points_detail,
        prior_topic_summaries=history_summaries or None,
    )
    _sessions[session_id] = session
    _session_user_ids[session_id] = user_id
    _session_modes[session_id] = mode

    now = datetime.now(timezone.utc).isoformat()

    # Persist to DB
    db = await get_db()
    await db.execute(
        "INSERT INTO sessions (id, user_id, started_at, status, mode, topic_id) VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, user_id, now, "active", mode, topic_id),
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
    return _session_modes.get(session_id, "conversation")


async def delete_session(session_id: str) -> dict | None:
    session = _sessions.pop(session_id, None)
    if session is None:
        return None
    mode = _session_modes.pop(session_id, "conversation")
    await session.close()

    now = datetime.now(timezone.utc).isoformat()
    db = await get_db()

    if mode == "review":
        # Review mode: skip AI marks generation, just mark as ended
        await db.execute(
            "UPDATE sessions SET status = ?, ended_at = ? WHERE id = ?",
            ("ended", now, session_id),
        )
        await db.commit()
        log.info("Review session %s ended (no review generation)", session_id)
        return {"session_id": session_id, "status": "ended", "mode": mode}

    await db.execute(
        "UPDATE sessions SET status = ?, ended_at = ? WHERE id = ?",
        ("reviewing", now, session_id),
    )
    await db.commit()

    # Launch review generation in background
    asyncio.create_task(_run_review(session_id))

    log.info("Session %s ended, review generation started", session_id)
    return {"session_id": session_id, "status": "reviewing", "mode": mode}


async def _run_review(session_id: str) -> None:
    try:
        await generate_review(session_id)
        log.info("Review generated for session %s", session_id)
    except Exception as e:
        log.error("Failed to generate review for session %s: %s", session_id, e)

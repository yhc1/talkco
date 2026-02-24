import json
import logging
from datetime import datetime, timezone

from db import get_db
from providers.openai_chat import chat_json

log = logging.getLogger(__name__)

PROFILE_UPDATE_SYSTEM_PROMPT = """\
You are an English language learning assessment system for Mandarin Chinese native speakers.

Given a learner's current profile and their latest session data (AI-identified issues, \
learner corrections, and session review with 4-dimension weaknesses), update the learner's profile.

Assess their level as one of: beginner, elementary, intermediate, upper-intermediate, advanced.

The session review evaluates four weakness dimensions:
- grammar: verb tense, agreement, articles, prepositions
- naturalness: technically correct but unnatural phrasing
- vocabulary: word choice precision and range
- sentence_structure: word order, Chinese-influenced patterns

Respond with JSON:
{
  "level": "intermediate",
  "profile_data": {
    "learned_expressions": ["expression 1", "expression 2"],
    "weak_points": {
      "grammar": ["pattern 1"],
      "naturalness": ["pattern 1"],
      "vocabulary": ["pattern 1"],
      "sentence_structure": ["pattern 1"]
    },
    "progress_notes": "Brief note on progress compared to previous state",
    "session_count": 1,
    "common_errors": ["error pattern 1"]
  }
}

Merge new learned expressions and weak points with existing ones. \
Remove weak points that the learner has clearly improved on. \
Increment session_count from the current value.\
"""


async def get_or_create_profile(user_id: str) -> dict:
    """Get existing profile or create a default one."""
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT user_id, level, profile_data, updated_at FROM user_profiles WHERE user_id = ?",
        (user_id,),
    )
    if rows:
        row = rows[0]
        return {
            "user_id": row["user_id"],
            "level": row["level"],
            "profile_data": json.loads(row["profile_data"]),
            "updated_at": row["updated_at"],
        }

    # Create default profile
    now = datetime.now(timezone.utc).isoformat()
    default_data = {
        "learned_expressions": [],
        "weak_points": [],
        "progress_notes": "",
        "session_count": 0,
        "common_errors": [],
    }
    await db.execute(
        "INSERT INTO user_profiles (user_id, level, profile_data, updated_at) VALUES (?, ?, ?, ?)",
        (user_id, "intermediate", json.dumps(default_data), now),
    )
    await db.commit()
    return {
        "user_id": user_id,
        "level": "intermediate",
        "profile_data": default_data,
        "updated_at": now,
    }


async def update_profile_after_session(user_id: str, session_id: str) -> dict:
    """Gather session data and call GPT-4o to update the user's learning profile."""
    db = await get_db()
    profile = await get_or_create_profile(user_id)

    # Gather session data: segments, marks, corrections, summary
    segments = await db.execute_fetchall(
        "SELECT id, turn_index, user_text, ai_text FROM segments "
        "WHERE session_id = ? ORDER BY turn_index",
        (session_id,),
    )

    seg_ids = [s["id"] for s in segments]
    marks = []
    if seg_ids:
        placeholders = ",".join("?" * len(seg_ids))
        marks = await db.execute_fetchall(
            f"SELECT segment_id, issue_types, original, suggestion FROM ai_marks "
            f"WHERE segment_id IN ({placeholders})",
            seg_ids,
        )

    corrections = await db.execute_fetchall(
        "SELECT segment_id, user_message, correction FROM corrections WHERE session_id = ?",
        (session_id,),
    )

    summary_rows = await db.execute_fetchall(
        "SELECT strengths, weaknesses, level_assessment, overall FROM session_summaries WHERE session_id = ?",
        (session_id,),
    )
    summary = summary_rows[0] if summary_rows else None

    # Build prompt
    user_msg_parts = [
        f"Current profile: {json.dumps(profile, ensure_ascii=False)}",
        "",
        "Session transcript:",
    ]
    for seg in segments:
        user_msg_parts.append(f"  Turn {seg['turn_index']}: User: {seg['user_text']} | AI: {seg['ai_text']}")

    if marks:
        user_msg_parts.append("\nAI-identified issues:")
        for m in marks:
            types = json.loads(m["issue_types"]) if isinstance(m["issue_types"], str) else m["issue_types"]
            types_str = ", ".join(types)
            user_msg_parts.append(f"  [{types_str}] \"{m['original']}\" → \"{m['suggestion']}\"")

    if corrections:
        user_msg_parts.append("\nLearner corrections:")
        for c in corrections:
            user_msg_parts.append(f"  Asked: {c['user_message']}, Correction: {c['correction']}")

    if summary:
        user_msg_parts.append(f"\nSession review: {summary['overall']}")
        user_msg_parts.append(f"Strengths: {summary['strengths']}")
        user_msg_parts.append(f"Weaknesses: {summary['weaknesses']}")
        user_msg_parts.append(f"Level assessment: {summary['level_assessment']}")

    result = await chat_json(PROFILE_UPDATE_SYSTEM_PROMPT, "\n".join(user_msg_parts))

    # Update DB
    now = datetime.now(timezone.utc).isoformat()
    new_level = result.get("level", profile["level"])
    new_data = json.dumps(result.get("profile_data", profile["profile_data"]), ensure_ascii=False)

    await db.execute(
        "UPDATE user_profiles SET level = ?, profile_data = ?, updated_at = ? WHERE user_id = ?",
        (new_level, new_data, now, user_id),
    )
    await db.commit()

    return {
        "user_id": user_id,
        "level": new_level,
        "profile_data": result.get("profile_data", profile["profile_data"]),
        "updated_at": now,
    }

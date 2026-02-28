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

Assess their level using the CEFR scale:
- A1: Can understand and use familiar everyday expressions and very basic phrases.
- A2: Can communicate in simple, routine tasks on familiar topics.
- B1: Can deal with most situations likely to arise while travelling or discussing familiar matters.
- B2: Can interact with a degree of fluency and spontaneity with native speakers.
- C1: Can express ideas fluently and spontaneously without much searching for expressions.
- C2: Can understand virtually everything heard or read with ease.

The session review evaluates three weakness dimensions:
- grammar: verb tense, agreement, articles, prepositions
- naturalness: unnatural phrasing or imprecise/basic word choices
- sentence_structure: word order, Chinese-influenced patterns

weak_points uses a structured format. Each dimension is an array of pattern objects:
{
  "pattern": "描述錯誤模式（繁體中文）",
  "examples": [
    { "wrong": "learner's actual utterance", "correct": "natural native expression" }
  ]
}

Rules for updating weak_points:
- If the same error pattern already exists, append new examples to that pattern's examples array.
- Keep at most 5 examples per pattern (drop oldest if over).
- If the learner has clearly improved on a pattern (no new occurrences, used correctly), remove it.
- Use 繁體中文 for pattern descriptions.

Extract personal facts the learner reveals during conversation (e.g. occupation, hobbies, \
residence, family, travel plans). Merge with existing personal_facts: keep unique facts, \
remove duplicates, and replace outdated or contradictory facts with newer information.

Respond with JSON:
{
  "level": "B1",
  "profile_data": {
    "learned_expressions": ["expression 1", "expression 2"],
    "weak_points": {
      "grammar": [
        {
          "pattern": "過去式混用為現在式",
          "examples": [
            { "wrong": "I go to store yesterday", "correct": "I went to the store yesterday" }
          ]
        }
      ],
      "naturalness": [],
      "sentence_structure": []
    },
    "progress_notes": "Brief note on progress compared to previous state",
    "common_errors": ["error pattern 1"],
    "personal_facts": ["software engineer", "lives in Taipei", "enjoys hiking"]
  }
}

Merge new learned expressions with existing ones. \
Remove weak points that the learner has clearly improved on.\
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
        "weak_points": {
            "grammar": [],
            "naturalness": [],
            "sentence_structure": [],
        },
        "progress_notes": "",
        "common_errors": [],
        "personal_facts": [],
    }
    await db.execute(
        "INSERT INTO user_profiles (user_id, level, profile_data, updated_at) VALUES (?, ?, ?, ?)",
        (user_id, None, json.dumps(default_data), now),
    )
    await db.commit()
    return {
        "user_id": user_id,
        "level": None,
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
        "SELECT strengths, weaknesses, overall FROM session_summaries WHERE session_id = ?",
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

    # Fetch last 5 completed session summaries for trend context
    recent_summaries = await db.execute_fetchall(
        "SELECT overall, weaknesses "
        "FROM session_summaries "
        "WHERE user_id = ? "
        "ORDER BY created_at DESC LIMIT 5",
        (user_id,),
    )
    if recent_summaries:
        user_msg_parts.append("\nRecent session history (most recent first):")
        for i, rs in enumerate(recent_summaries, 1):
            user_msg_parts.append(f"  Session {i}: {rs['overall']}")
            user_msg_parts.append(f"    Weaknesses: {rs['weaknesses']}")

    result = await chat_json(PROFILE_UPDATE_SYSTEM_PROMPT, "\n".join(user_msg_parts))

    # Update DB — keep existing level, only update profile_data
    now = datetime.now(timezone.utc).isoformat()
    new_data = json.dumps(result.get("profile_data", profile["profile_data"]), ensure_ascii=False)

    await db.execute(
        "UPDATE user_profiles SET profile_data = ?, updated_at = ? WHERE user_id = ?",
        (new_data, now, user_id),
    )
    await db.commit()

    return {
        "user_id": user_id,
        "level": profile["level"],
        "profile_data": result.get("profile_data", profile["profile_data"]),
        "updated_at": now,
    }


LEVEL_EVAL_SYSTEM_PROMPT = """\
You are an English language level assessment system for Mandarin Chinese native speakers.

Given a learner's current profile and their recent session summaries, evaluate their CEFR level.

CEFR scale:
- A1: Can understand and use familiar everyday expressions and very basic phrases.
- A2: Can communicate in simple, routine tasks on familiar topics.
- B1: Can deal with most situations likely to arise while travelling or discussing familiar matters.
- B2: Can interact with a degree of fluency and spontaneity with native speakers.
- C1: Can express ideas fluently and spontaneously without much searching for expressions.
- C2: Can understand virtually everything heard or read with ease.

Respond with JSON:
{
  "level": "B1"
}
"""


async def evaluate_level(user_id: str) -> dict:
    """Evaluate and update the user's CEFR level based on recent sessions."""
    db = await get_db()
    profile = await get_or_create_profile(user_id)

    # Fetch recent completed session summaries
    recent_summaries = await db.execute_fetchall(
        "SELECT strengths, weaknesses, overall "
        "FROM session_summaries "
        "WHERE user_id = ? "
        "ORDER BY created_at DESC LIMIT 10",
        (user_id,),
    )

    user_msg_parts = [
        f"Current profile: {json.dumps(profile, ensure_ascii=False)}",
        "",
    ]

    if recent_summaries:
        user_msg_parts.append("Recent session summaries (most recent first):")
        for i, rs in enumerate(recent_summaries, 1):
            user_msg_parts.append(f"  Session {i}:")
            user_msg_parts.append(f"    Strengths: {rs['strengths']}")
            user_msg_parts.append(f"    Weaknesses: {rs['weaknesses']}")
            user_msg_parts.append(f"    Overall: {rs['overall']}")
    else:
        user_msg_parts.append("No completed sessions yet.")

    result = await chat_json(LEVEL_EVAL_SYSTEM_PROMPT, "\n".join(user_msg_parts))

    new_level = result.get("level", profile["level"])
    now = datetime.now(timezone.utc).isoformat()

    await db.execute(
        "UPDATE user_profiles SET level = ?, updated_at = ? WHERE user_id = ?",
        (new_level, now, user_id),
    )
    await db.commit()

    log.info("User %s level evaluated: %s → %s", user_id, profile["level"], new_level)

    return {
        "user_id": user_id,
        "level": new_level,
        "profile_data": profile["profile_data"],
        "updated_at": now,
    }


def compute_needs_review(profile_data: dict) -> bool:
    """Check if any weak point pattern has 3+ examples, indicating repeated errors."""
    weak_points = profile_data.get("weak_points", {})
    if not isinstance(weak_points, dict):
        return False
    for patterns in weak_points.values():
        if not isinstance(patterns, list):
            continue
        for p in patterns:
            if isinstance(p, dict) and len(p.get("examples", [])) >= 3:
                return True
    return False
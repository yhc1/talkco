import json
import logging
from datetime import datetime, timezone

from config import settings
from constants import IssueDimension
from db import get_db
from providers.openai_chat import chat_json

log = logging.getLogger(__name__)

PROFILE_UPDATE_SYSTEM_PROMPT = """\
You are an English language learning profile updater for Mandarin Chinese native speakers.

Given the learner's current profile and their latest session data, update the profile.

**Input data:**
- Current profile (personal_facts, weak_points, common_errors)
- Session transcript (user/AI turns)
- AI-identified issues (categorized by grammar/naturalness/sentence_structure)
- Learner's self-corrections during review

**Output rules:**

1. personal_facts:
   - Extract personal information revealed during conversation
   - Merge with existing facts; remove duplicates; replace outdated info
   - Use 繁體中文

2. weak_points: Three dimensions (grammar, naturalness, sentence_structure).
   Each is an array of pattern objects:
   {{ "pattern": "繁中描述", "examples": [{{ "wrong": "...", "correct": "..." }}] }}
   - Same pattern exists → append new examples (max {max_examples}, drop oldest)
   - Learner improved on a pattern → remove it
   - New error pattern → add it

3. common_errors:
   - Short list of the learner's most frequent/persistent error tendencies
   - Use 繁體中文, each item is a brief description
   - Update based on session data: add new patterns, remove resolved ones

Respond with JSON:
{{
  "profile_data": {{
    "personal_facts": ["住在台北", "是軟體工程師"],
    "weak_points": {{
      "grammar": [
        {{
          "pattern": "過去式混用為現在式",
          "examples": [
            {{ "wrong": "I go to store yesterday", "correct": "I went to the store yesterday" }}
          ]
        }}
      ],
      "naturalness": [],
      "sentence_structure": []
    }},
    "common_errors": ["經常漏掉冠詞 a/the"]
  }}
}}\
""".format(max_examples=settings.MAX_EXAMPLES_PER_PATTERN)


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
        "personal_facts": [],
        "weak_points": {
            IssueDimension.GRAMMAR: [],
            IssueDimension.NATURALNESS: [],
            IssueDimension.SENTENCE_STRUCTURE: [],
        },
        "common_errors": [],
        "progress_notes": "",
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

    # Gather session data: segments, marks, corrections
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

    # Build prompt
    user_msg_parts = [
        f"Current profile: {json.dumps(profile['profile_data'], ensure_ascii=False)}",
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
### Role
You are an expert CEFR (Common European Framework of Reference for Languages) Assessor. Your task is to analyze chat logs of Mandarin Chinese native speakers and determine their current English proficiency level.

### Assessment Criteria
Evaluate the input based on these detailed linguistic markers:

* **A1 (Beginner):** Uses isolated words, short phrases, and basic S+V+O structures. High reliance on memorized formulas.
* **A2 (Elementary):** Can link groups of words with simple connectors (and, but, because). Uses past simple and future (going to) basic forms. Limited to everyday topics.
* **B1 (Intermediate):** Can maintain a conversation but with noticeable pauses to plan. Uses a mix of simple and some complex sentences. Understandable even if there are L1 (Mandarin) interference patterns.
* **B2 (Upper Intermediate):** Shows "effective operational proficiency." Can correct their own mistakes. Uses modal verbs for hypothesis (would/could have). Can discuss abstract topics with clear, detailed expression.
* **C1 (Advanced):** Smooth, natural flow. Wide range of vocabulary (idioms, phrasal verbs). Rarely needs to search for expressions. Can use complex grammar (inversion, relative clauses) with high accuracy.
* **C2 (Mastery):** Native-like precision. Can convey finer shades of meaning even in complex situations.

### Instructions
1. Analyze the user's grammar accuracy, vocabulary range, and conversational coherence.
2. Consider typical "Chinglish" errors as indicators of lower levels (A1-B1).
3. First, provide a brief internal justification for the level chosen.
4. Output the final result in the specified JSON format.

### Output Format
{
  "analysis": "Briefly describe the grammar, vocab, and fluency observed.",
  "level": "A1 | A2 | B1 | B2 | C1 | C2"
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
        f"ORDER BY created_at DESC LIMIT {settings.LEVEL_EVAL_SESSION_LIMIT}",
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


PROGRESS_NOTES_SYSTEM_PROMPT = """\
You are a learning progress summarizer for a Mandarin Chinese native speaker learning English.

Given the learner's current profile and their recent session data (conversation summaries and review summaries), \
produce a concise learning progress summary in 繁體中文.

Include:
1. 最近練習了什麼主題或內容
2. 有什麼明顯的進步或改善
3. 接下來建議加強的方向

Keep the summary brief (3-5 sentences). Be encouraging but honest.

Respond with JSON:
{
  "progress_notes": "繁體中文摘要..."
}\
"""


async def generate_progress_notes(user_id: str) -> dict:
    """Generate a learning progress summary based on recent sessions."""
    db = await get_db()
    profile = await get_or_create_profile(user_id)

    limit = settings.PROGRESS_NOTES_SESSION_LIMIT

    # Fetch recent conversation session summaries
    session_summaries = await db.execute_fetchall(
        "SELECT strengths, weaknesses, overall "
        "FROM session_summaries "
        "WHERE user_id = ? "
        f"ORDER BY created_at DESC LIMIT {limit}",
        (user_id,),
    )

    # Fetch recent review summaries
    review_summaries = await db.execute_fetchall(
        "SELECT practiced, notes "
        "FROM review_summaries "
        "WHERE user_id = ? "
        f"ORDER BY created_at DESC LIMIT {limit}",
        (user_id,),
    )

    user_msg_parts = [
        f"Current profile: {json.dumps(profile['profile_data'], ensure_ascii=False)}",
        f"Current level: {profile['level'] or 'Not evaluated'}",
        "",
    ]

    if session_summaries:
        user_msg_parts.append("Recent conversation session summaries (most recent first):")
        for i, ss in enumerate(session_summaries, 1):
            user_msg_parts.append(f"  Session {i}:")
            user_msg_parts.append(f"    Strengths: {ss['strengths']}")
            user_msg_parts.append(f"    Weaknesses: {ss['weaknesses']}")
            user_msg_parts.append(f"    Overall: {ss['overall']}")
    else:
        user_msg_parts.append("No conversation sessions yet.")

    if review_summaries:
        user_msg_parts.append("\nRecent review session summaries (most recent first):")
        for i, rs in enumerate(review_summaries, 1):
            user_msg_parts.append(f"  Review {i}:")
            user_msg_parts.append(f"    Practiced: {rs['practiced']}")
            user_msg_parts.append(f"    Notes: {rs['notes']}")
    else:
        user_msg_parts.append("\nNo review sessions yet.")

    result = await chat_json(PROGRESS_NOTES_SYSTEM_PROMPT, "\n".join(user_msg_parts))

    progress_notes = result.get("progress_notes", "")

    # Update DB — merge progress_notes into profile_data
    now = datetime.now(timezone.utc).isoformat()
    profile["profile_data"]["progress_notes"] = progress_notes
    new_data = json.dumps(profile["profile_data"], ensure_ascii=False)

    await db.execute(
        "UPDATE user_profiles SET profile_data = ?, updated_at = ? WHERE user_id = ?",
        (new_data, now, user_id),
    )
    await db.commit()

    log.info("User %s progress notes updated", user_id)

    return {
        "user_id": user_id,
        "level": profile["level"],
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
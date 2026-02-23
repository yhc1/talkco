import json
import logging
from datetime import datetime, timezone

from db import get_db
from providers.openai_chat import chat_json

log = logging.getLogger(__name__)

REVIEW_SYSTEM_PROMPT = """\
You are an English language learning assistant for Mandarin Chinese speakers.

Analyze the conversation transcript. For each user turn, identify issues in 4 categories:
- "grammar": grammatical errors (tense, agreement, articles, prepositions)
- "naturalness": grammatically correct but unnatural phrasing
- "vocabulary": imprecise or overly basic word choices
- "sentence_structure": Chinese-influenced word order or sentence patterns

For each issue, provide:
- original: the problematic phrase
- suggestion: how a native speaker would say it
- explanation: brief explanation in Traditional Chinese (繁體中文)

IMPORTANT: A single phrase can have multiple layers of issues. For example,
"The weather, I think good" has a grammar issue (missing 'is') AND even after
fixing grammar, "I think the weather is good" has a naturalness issue (native
speakers would say "The weather's pretty nice today, I think").
Report each layer as a separate mark.

Respond as JSON: { "marks": [ { "turn_index": 0, "issues": [...] } ] }

If a turn has no issues, omit it from the marks array. \
Keep explanations concise and in Traditional Chinese (繁體中文). \
Suggestions should be natural, level-appropriate English.\
"""

CORRECTION_SYSTEM_PROMPT = """\
You are an English learning assistant for Mandarin Chinese speakers.
The learner is reviewing their conversation and pointing at something they
struggled with. They may explain in Chinese, broken English, or a mix.

Given the segment context and the learner's message, provide:
1. How a native speaker would naturally say it
2. Brief explanation in Traditional Chinese (繁體中文)

Respond as JSON: { "correction": "...", "explanation": "..." }\
"""

SESSION_REVIEW_SYSTEM_PROMPT = """\
You are an English learning assessment system for Mandarin Chinese speakers.

Analyze the full conversation, AI-identified issues, and learner's self-corrections.

Evaluate across four dimensions:
- grammar: verb tense, agreement, articles, prepositions
- naturalness: technically correct but unnatural phrasing
- vocabulary: word choice precision and range
- sentence_structure: word order, Chinese-influenced patterns

Respond as JSON:
{
  "strengths": ["...", "..."],
  "weaknesses": {
    "grammar": "...",
    "naturalness": "...",
    "vocabulary": "...",
    "sentence_structure": "..."
  },
  "level_assessment": "...",
  "overall": "..."
}

strengths: 2-3 bullet points in Traditional Chinese (繁體中文).
weaknesses: 1-2 sentences in Traditional Chinese (繁體中文) with examples for each dimension. null if no issues.
level_assessment: level + justification in Traditional Chinese (繁體中文).
overall: 2-3 sentence summary in Traditional Chinese (繁體中文).\
"""


async def generate_review(session_id: str) -> None:
    """Fetch all segments for a session, call GPT-4o to generate AI Marks, write to DB."""
    db = await get_db()

    rows = await db.execute_fetchall(
        "SELECT id, turn_index, user_text, ai_text FROM segments "
        "WHERE session_id = ? ORDER BY turn_index",
        (session_id,),
    )

    if not rows:
        log.warning("No segments found for session %s, skipping review", session_id)
        return

    transcript_lines = []
    for row in rows:
        transcript_lines.append(f"Turn {row['turn_index']}:")
        transcript_lines.append(f"  User: {row['user_text']}")
        transcript_lines.append(f"  AI: {row['ai_text']}")
    transcript = "\n".join(transcript_lines)

    result = await chat_json(REVIEW_SYSTEM_PROMPT, transcript)

    marks = result.get("marks", [])
    seg_map = {row["turn_index"]: row["id"] for row in rows}

    for mark in marks:
        turn_idx = mark.get("turn_index")
        segment_id = seg_map.get(turn_idx)
        if segment_id is None:
            continue
        for issue in mark.get("issues", []):
            issue_type = issue.get("issue_type")
            original = issue.get("original")
            suggestion = issue.get("suggestion")
            explanation = issue.get("explanation")
            if not all([issue_type, original, suggestion, explanation]):
                log.warning("Skipping malformed issue in turn %s: %s", turn_idx, issue)
                continue
            await db.execute(
                "INSERT INTO ai_marks (segment_id, issue_type, original, suggestion, explanation) "
                "VALUES (?, ?, ?, ?, ?)",
                (segment_id, issue_type, original, suggestion, explanation),
            )

    await db.commit()
    log.info("Review written for session %s: %d marks", session_id, sum(len(m.get("issues", [])) for m in marks))


async def generate_correction(session_id: str, segment_id: int, user_message: str) -> dict:
    """Generate a correction for a user's question about a segment. Synchronous call."""
    db = await get_db()

    rows = await db.execute_fetchall(
        "SELECT id, user_text, ai_text FROM segments WHERE id = ? AND session_id = ?",
        (segment_id, session_id),
    )
    if not rows:
        raise ValueError(f"Segment {segment_id} not found in session {session_id}")

    seg = rows[0]
    user_msg = (
        f"Segment context:\n"
        f"  User said: {seg['user_text']}\n"
        f"  AI responded: {seg['ai_text']}\n\n"
        f"Learner's message: {user_message}"
    )

    result = await chat_json(CORRECTION_SYSTEM_PROMPT, user_msg)

    correction = result.get("correction", "")
    explanation = result.get("explanation", "")

    now = datetime.now(timezone.utc).isoformat()
    cursor = await db.execute(
        "INSERT INTO corrections (session_id, segment_id, user_message, correction, explanation, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, segment_id, user_message, correction, explanation, now),
    )
    await db.commit()

    return {
        "id": cursor.lastrowid,
        "segment_id": segment_id,
        "user_message": user_message,
        "correction": correction,
        "explanation": explanation,
        "created_at": now,
    }


async def generate_session_review(session_id: str) -> dict:
    """Generate final session review with strengths, weaknesses, level assessment."""
    db = await get_db()

    # Fetch transcript
    segments = await db.execute_fetchall(
        "SELECT id, turn_index, user_text, ai_text FROM segments "
        "WHERE session_id = ? ORDER BY turn_index",
        (session_id,),
    )

    # Fetch AI marks
    seg_ids = [s["id"] for s in segments]
    marks = []
    if seg_ids:
        placeholders = ",".join("?" * len(seg_ids))
        marks = await db.execute_fetchall(
            f"SELECT segment_id, issue_type, original, suggestion, explanation "
            f"FROM ai_marks WHERE segment_id IN ({placeholders})",
            seg_ids,
        )

    # Fetch corrections
    corrections = await db.execute_fetchall(
        "SELECT segment_id, user_message, correction, explanation "
        "FROM corrections WHERE session_id = ?",
        (session_id,),
    )

    # Build prompt
    parts = ["Conversation transcript:"]
    for seg in segments:
        parts.append(f"  Turn {seg['turn_index']}: User: {seg['user_text']} | AI: {seg['ai_text']}")

    if marks:
        parts.append("\nAI-identified issues:")
        for m in marks:
            parts.append(f"  [{m['issue_type']}] \"{m['original']}\" → \"{m['suggestion']}\" ({m['explanation']})")

    if corrections:
        parts.append("\nLearner's self-corrections:")
        for c in corrections:
            parts.append(f"  Learner asked: {c['user_message']} → Correction: {c['correction']}")

    result = await chat_json(SESSION_REVIEW_SYSTEM_PROMPT, "\n".join(parts))

    strengths = result.get("strengths", [])
    weaknesses = result.get("weaknesses", {})
    level_assessment = result.get("level_assessment", "")
    overall = result.get("overall", "")

    # Write to session_summaries
    await db.execute(
        "INSERT OR REPLACE INTO session_summaries (session_id, strengths, weaknesses, level_assessment, overall) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            session_id,
            json.dumps(strengths, ensure_ascii=False),
            json.dumps(weaknesses, ensure_ascii=False),
            level_assessment,
            overall,
        ),
    )
    await db.commit()

    return {
        "strengths": strengths,
        "weaknesses": weaknesses,
        "level_assessment": level_assessment,
        "overall": overall,
    }

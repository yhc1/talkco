import json
import logging
from datetime import datetime, timezone

from db import get_db
from providers.openai_chat import chat_json

log = logging.getLogger(__name__)

REVIEW_SYSTEM_PROMPT = """\
You are an English language learning assistant for Mandarin Chinese speakers.

Analyze the conversation transcript. For each user utterance that has issues, provide ONE record covering all problems found in that utterance.

Issue categories:
- "grammar": grammatical errors (tense, agreement, articles, prepositions)
- "naturalness": unnatural phrasing or imprecise/basic word choices
- "sentence_structure": Chinese-influenced word order or sentence patterns

For each user utterance with issues, provide:
- issue_types: array of applicable categories (e.g. ["grammar", "naturalness"])
- original: what the user said
- suggestion: how a native speaker would naturally say it (addressing all issues at once)
- explanation: one concise explanation in Traditional Chinese (繁體中文) covering all issues together

Respond as JSON: { "marks": [ { "turn_index": 0, "issue_types": [...], "original": "...", "suggestion": "...", "explanation": "..." } ] }

If a user utterance has no issues, omit it. \
Keep explanations clear and concise in Traditional Chinese (繁體中文). \
Suggestions should be natural, level-appropriate English.\
"""

CORRECTION_SYSTEM_PROMPT = """\
You are an English learning assistant for Mandarin Chinese speakers.
The learner is reviewing their conversation and pointing at something they
struggled with. They may explain in Chinese, broken English, or a mix.

You must answer the learner's request based on the current segment and its
detected issues, not translate or paraphrase the learner's message itself.

Rules:
- Focus on fixing the sentence in the segment context.
- If the learner asks for more examples (e.g. "多一點範例"), provide 2-3 short
  example sentences that follow the same corrected pattern.
- Never output a translation of the learner's request as the correction.
- Keep explanation concise in Traditional Chinese (繁體中文).

Given the segment context, AI marks, and learner message, provide:
1. correction: How a native speaker would naturally say the target sentence
2. explanation: Brief Traditional Chinese explanation. Include examples when
   requested.

Respond as JSON: { "correction": "...", "explanation": "..." }\
"""

SESSION_REVIEW_SYSTEM_PROMPT = """\
You are an English learning assessment system for Mandarin Chinese speakers.

Analyze the full conversation, AI-identified issues, and learner's self-corrections.

Evaluate across three dimensions:
- grammar: verb tense, agreement, articles, prepositions
- naturalness: unnatural phrasing or imprecise/basic word choices
- sentence_structure: word order, Chinese-influenced patterns

Respond as JSON:
{
  "strengths": ["...", "..."],
  "weaknesses": {
    "grammar": "...",
    "naturalness": "...",
    "sentence_structure": "..."
  },
  "overall": "..."
}

strengths: 2-3 bullet points in Traditional Chinese (繁體中文).
weaknesses: 1-2 sentences in Traditional Chinese (繁體中文) with examples for each dimension. null if no issues.
overall: 2-3 sentence summary in Traditional Chinese (繁體中文).\
"""


REVIEW_SUMMARY_SYSTEM_PROMPT = """\
You are an English language learning assessment system for Mandarin Chinese speakers.

Analyze the review-mode conversation transcript below. The learner was practicing their weak points with a teacher.

Your task:
1. Identify which weak points were practiced (dimension + pattern).
2. Assess the learner's performance on each pattern:
   - "improved": learner mostly got it right after guidance
   - "still_struggling": learner kept making the same mistake
   - "mixed": some correct, some incorrect attempts

Respond as JSON:
{
  "practiced": [
    {
      "dimension": "grammar",
      "patterns": ["過去式混用為現在式"],
      "performance": "improved"
    }
  ],
  "notes": "2-3 sentence summary in Traditional Chinese (繁體中文) describing what was practiced and overall performance."
}

Dimensions: grammar, naturalness, sentence_structure.
notes must be in 繁體中文, 2-3 sentences.\
"""


CHAT_SUMMARY_SYSTEM_PROMPT = """\
Summarize the conversation content briefly (2-3 sentences in English).
Focus on: what topic was discussed, what key points were covered, what opinions or experiences the learner shared.
Do NOT include language assessment or learning feedback.
Respond as JSON: { "summary": "..." }\
"""


async def generate_chat_summary(session_id: str, topic_id: str) -> dict:
    """Generate a brief content summary of the conversation and store in chat_summaries."""
    db = await get_db()

    rows = await db.execute_fetchall(
        "SELECT turn_index, user_text, ai_text FROM segments "
        "WHERE session_id = ? ORDER BY turn_index",
        (session_id,),
    )

    if not rows:
        log.warning("No segments for session %s, skipping chat summary", session_id)
        return {"summary": ""}

    transcript_lines = []
    for row in rows:
        transcript_lines.append(f"Turn {row['turn_index']}:")
        transcript_lines.append(f"  User: {row['user_text']}")
        transcript_lines.append(f"  AI: {row['ai_text']}")
    transcript = "\n".join(transcript_lines)

    result = await chat_json(CHAT_SUMMARY_SYSTEM_PROMPT, transcript)
    summary = result.get("summary", "")

    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO chat_summaries (session_id, topic_id, summary, created_at) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT (session_id) DO UPDATE SET topic_id = EXCLUDED.topic_id, summary = EXCLUDED.summary, created_at = EXCLUDED.created_at",
        (session_id, topic_id, summary, now),
    )
    await db.commit()
    log.info("Chat summary saved for session %s: %s", session_id, summary[:100])

    return {"summary": summary}


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
    log.info("Review input for session %s (%d segments):\n%s", session_id, len(rows), transcript)

    result = await chat_json(REVIEW_SYSTEM_PROMPT, transcript)
    log.info("Review raw response for session %s: %s", session_id, json.dumps(result, ensure_ascii=False))

    marks = result.get("marks", [])
    log.info("Review result for session %s: %d marks", session_id, len(marks))
    seg_map = {row["turn_index"]: row["id"] for row in rows}

    inserted = 0
    for mark in marks:
        turn_idx = mark.get("turn_index")
        segment_id = seg_map.get(turn_idx)
        if segment_id is None:
            continue
        issue_types = mark.get("issue_types", [])
        original = mark.get("original")
        suggestion = mark.get("suggestion")
        explanation = mark.get("explanation")
        if not issue_types or not all([original, suggestion, explanation]):
            log.warning("Skipping malformed mark for turn %s: %s", turn_idx, mark)
            continue
        await db.execute(
            "INSERT INTO ai_marks (segment_id, issue_types, original, suggestion, explanation) "
            "VALUES (?, ?, ?, ?, ?)",
            (segment_id, json.dumps(issue_types, ensure_ascii=False), original, suggestion, explanation),
        )
        inserted += 1

    await db.commit()
    log.info("Review written for session %s: %d marks", session_id, inserted)


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
    marks = await db.execute_fetchall(
        "SELECT issue_types, original, suggestion, explanation FROM ai_marks WHERE segment_id = ?",
        (segment_id,),
    )

    marks_lines = []
    for idx, mark in enumerate(marks, 1):
        issue_types = json.loads(mark["issue_types"]) if mark["issue_types"] else []
        marks_lines.append(
            f"  Mark {idx}: issue_types={issue_types}, original={mark['original']}, "
            f"suggestion={mark['suggestion']}, explanation={mark['explanation']}"
        )

    marks_text = "\n".join(marks_lines) if marks_lines else "  (No AI marks for this segment yet)"

    user_msg = (
        f"Segment context:\n"
        f"  User said: {seg['user_text']}\n"
        f"  AI responded: {seg['ai_text']}\n"
        f"AI marks:\n{marks_text}\n\n"
        f"Learner's message: {user_message}"
    )

    result = await chat_json(CORRECTION_SYSTEM_PROMPT, user_msg)

    correction = result.get("correction", "")
    explanation = result.get("explanation", "")

    now = datetime.now(timezone.utc).isoformat()
    row = await db.execute(
        "INSERT INTO corrections (session_id, segment_id, user_message, correction, explanation, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?) RETURNING id",
        (session_id, segment_id, user_message, correction, explanation, now),
    )
    await db.commit()

    return {
        "id": row["id"],
        "segment_id": segment_id,
        "user_message": user_message,
        "correction": correction,
        "explanation": explanation,
        "created_at": now,
    }


async def generate_session_review(session_id: str, user_id: str) -> dict | None:
    """Generate final session review with strengths, weaknesses, level assessment.
    Returns None if no segments exist (nothing to review)."""
    db = await get_db()

    # Fetch transcript
    segments = await db.execute_fetchall(
        "SELECT id, turn_index, user_text, ai_text FROM segments "
        "WHERE session_id = ? ORDER BY turn_index",
        (session_id,),
    )

    if not segments:
        log.warning("No segments for session %s, skipping session review", session_id)
        return None

    # Fetch AI marks
    seg_ids = [s["id"] for s in segments]
    marks = []
    if seg_ids:
        placeholders = ",".join("?" * len(seg_ids))
        marks = await db.execute_fetchall(
            f"SELECT segment_id, issue_types, original, suggestion, explanation "
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
            types = json.loads(m["issue_types"]) if isinstance(m["issue_types"], str) else m["issue_types"]
            types_str = ", ".join(types)
            parts.append(f"  [{types_str}] \"{m['original']}\" → \"{m['suggestion']}\" ({m['explanation']})")

    if corrections:
        parts.append("\nLearner's self-corrections:")
        for c in corrections:
            parts.append(f"  Learner asked: {c['user_message']} → Correction: {c['correction']}")

    result = await chat_json(SESSION_REVIEW_SYSTEM_PROMPT, "\n".join(parts))

    strengths = result.get("strengths", [])
    weaknesses = result.get("weaknesses", {})
    overall = result.get("overall", "")

    # Write to session_summaries
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO session_summaries (session_id, user_id, strengths, weaknesses, overall, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (session_id) DO UPDATE SET user_id = EXCLUDED.user_id, strengths = EXCLUDED.strengths, weaknesses = EXCLUDED.weaknesses, overall = EXCLUDED.overall, created_at = EXCLUDED.created_at",
        (
            session_id,
            user_id,
            json.dumps(strengths, ensure_ascii=False),
            json.dumps(weaknesses, ensure_ascii=False),
            overall,
            now,
        ),
    )
    await db.commit()

    return {
        "strengths": strengths,
        "weaknesses": weaknesses,
        "overall": overall,
    }


async def generate_review_summary(session_id: str, user_id: str) -> dict | None:
    """Generate a structured summary of a review session and store in review_summaries.
    Returns None if no segments exist."""
    db = await get_db()

    rows = await db.execute_fetchall(
        "SELECT turn_index, user_text, ai_text FROM segments "
        "WHERE session_id = ? ORDER BY turn_index",
        (session_id,),
    )

    if not rows:
        log.warning("No segments for review session %s, skipping review summary", session_id)
        return None

    transcript_lines = []
    for row in rows:
        transcript_lines.append(f"Turn {row['turn_index']}:")
        transcript_lines.append(f"  User: {row['user_text']}")
        transcript_lines.append(f"  AI: {row['ai_text']}")
    transcript = "\n".join(transcript_lines)

    result = await chat_json(REVIEW_SUMMARY_SYSTEM_PROMPT, transcript)

    practiced = result.get("practiced", [])
    notes = result.get("notes", "")

    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO review_summaries (session_id, user_id, practiced, notes, created_at) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT (session_id) DO UPDATE SET user_id = EXCLUDED.user_id, practiced = EXCLUDED.practiced, notes = EXCLUDED.notes, created_at = EXCLUDED.created_at",
        (session_id, user_id, json.dumps(practiced, ensure_ascii=False), notes, now),
    )
    await db.commit()
    log.info("Review summary saved for session %s", session_id)

    return {"practiced": practiced, "notes": notes}

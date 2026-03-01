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

Given input data from the user message, update the learner profile.

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

Return ONLY valid JSON with this exact shape:
{{
  "profile_data": {{
    "personal_facts": ["..."],
    "weak_points": {{
      "grammar": [{{ "pattern": "...", "examples": [{{ "wrong": "...", "correct": "..." }}] }}],
      "naturalness": [{{ "pattern": "...", "examples": [{{ "wrong": "...", "correct": "..." }}] }}],
      "sentence_structure": [{{ "pattern": "...", "examples": [{{ "wrong": "...", "correct": "..." }}] }}]
    }},
    "common_errors": ["..."]
  }}
}}\
""".format(
    max_examples=settings.MAX_EXAMPLES_PER_PATTERN,
)


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
        "quick_review": [],
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

    input_payload = {
        "current_profile": profile["profile_data"],
        "session_transcript": [
            {
                "segment_id": seg["id"],
                "turn_index": seg["turn_index"],
                "user_text": seg["user_text"],
                "ai_text": seg["ai_text"],
            }
            for seg in segments
        ],
        "ai_identified_issues": [
            {
                "segment_id": m["segment_id"],
                "issue_types": json.loads(m["issue_types"])
                if isinstance(m["issue_types"], str)
                else m["issue_types"],
                "original": m["original"],
                "suggestion": m["suggestion"],
            }
            for m in marks
        ],
        "learner_corrections": [
            {
                "segment_id": c["segment_id"],
                "user_message": c["user_message"],
                "correction": c["correction"],
            }
            for c in corrections
        ],
    }

    transcript_lines = "\n".join(
        '  Turn {turn_index}: User: {user_text} | AI: {ai_text}'.format(
            turn_index=turn["turn_index"],
            user_text=turn["user_text"],
            ai_text=turn["ai_text"],
        )
        for turn in input_payload["session_transcript"]
    ) or "  (No transcript turns)"

    mark_lines = "\n".join(
        '  [{types}] "{original}" → "{suggestion}"'.format(
            types=", ".join(issue["issue_types"]),
            original=issue["original"],
            suggestion=issue["suggestion"],
        )
        for issue in input_payload["ai_identified_issues"]
    ) or "  (No AI-identified issues)"

    correction_lines = "\n".join(
        "  Asked: {user_message}, Correction: {correction}".format(
            user_message=correction["user_message"],
            correction=correction["correction"],
        )
        for correction in input_payload["learner_corrections"]
    ) or "  (No learner corrections)"

    user_message = """\
Current profile: {profile_json}

Session transcript:
{transcript_lines}

AI-identified issues:
{mark_lines}

Learner corrections:
{correction_lines}

Input data (JSON):
{input_payload_json}\
""".format(
        profile_json=json.dumps(profile["profile_data"], ensure_ascii=False),
        transcript_lines=transcript_lines,
        mark_lines=mark_lines,
        correction_lines=correction_lines,
        input_payload_json=json.dumps(input_payload, ensure_ascii=False, indent=2),
    )

    result = await chat_json(PROFILE_UPDATE_SYSTEM_PROMPT, user_message)

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

    summaries_block = (
        "Recent session summaries (most recent first):\n{lines}".format(
            lines="\n".join(
                "  Session {index}:\n"
                "    Strengths: {strengths}\n"
                "    Weaknesses: {weaknesses}\n"
                "    Overall: {overall}".format(
                    index=i,
                    strengths=rs["strengths"],
                    weaknesses=rs["weaknesses"],
                    overall=rs["overall"],
                )
                for i, rs in enumerate(recent_summaries, 1)
            )
        )
        if recent_summaries
        else "No completed sessions yet."
    )

    user_message = """\
Current profile: {profile_json}

{summaries_block}\
""".format(
        profile_json=json.dumps(profile, ensure_ascii=False),
        summaries_block=summaries_block,
    )

    result = await chat_json(LEVEL_EVAL_SYSTEM_PROMPT, user_message)

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

    session_summary_block = (
        "Recent conversation session summaries (most recent first):\n{lines}".format(
            lines="\n".join(
                "  Session {index}:\n"
                "    Strengths: {strengths}\n"
                "    Weaknesses: {weaknesses}\n"
                "    Overall: {overall}".format(
                    index=i,
                    strengths=ss["strengths"],
                    weaknesses=ss["weaknesses"],
                    overall=ss["overall"],
                )
                for i, ss in enumerate(session_summaries, 1)
            )
        )
        if session_summaries
        else "No conversation sessions yet."
    )

    review_summary_block = (
        "Recent review session summaries (most recent first):\n{lines}".format(
            lines="\n".join(
                "  Review {index}:\n"
                "    Practiced: {practiced}\n"
                "    Notes: {notes}".format(
                    index=i,
                    practiced=rs["practiced"],
                    notes=rs["notes"],
                )
                for i, rs in enumerate(review_summaries, 1)
            )
        )
        if review_summaries
        else "No review sessions yet."
    )

    user_message = """\
Current profile: {profile_json}
Current level: {level}

{session_summary_block}

{review_summary_block}\
""".format(
        profile_json=json.dumps(profile["profile_data"], ensure_ascii=False),
        level=profile["level"] or "Not evaluated",
        session_summary_block=session_summary_block,
        review_summary_block=review_summary_block,
    )

    result = await chat_json(PROGRESS_NOTES_SYSTEM_PROMPT, user_message)

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


QUICK_REVIEW_SYSTEM_PROMPT = """\
You are a language learning assistant for a Mandarin Chinese native speaker learning English.

Given the learner's recent errors and corrections, produce a concise quick-review list.

**Priority rules:**
1. **Highest priority — corrections**: Sentences the learner explicitly asked "how do I say this?" \
These represent conscious learning intent and MUST appear first.
2. **Second priority — AI marks (naturalness / sentence_structure)**: Unnatural phrasing or \
Chinese-influenced sentence patterns are more valuable to review than simple grammar.
3. **Lowest priority — simple grammar** (tense, articles): Include only if space remains.
4. Cross-reference with review_summaries "still_struggling" patterns — these indicate \
the learner hasn't improved yet, so they deserve extra weight.

**Output rules:**
- Each item: {{ "chinese": "簡短中文意思", "english": "correct English expression" }}
- chinese should be a brief, natural 繁體中文 description of the intended meaning
- english should be the correct, natural way to say it
- Maximum {limit} items
- No duplicates; merge if the same sentence appears in both corrections and ai_marks

Respond with JSON:
{{
  "quick_review": [
    {{ "chinese": "...", "english": "..." }}
  ]
}}\
""".format(
    limit=settings.QUICK_REVIEW_LIMIT,
)


async def generate_quick_review(user_id: str) -> dict:
    """Generate a quick-review list of sentences the learner should practice."""
    db = await get_db()
    profile = await get_or_create_profile(user_id)

    limit = settings.PROGRESS_NOTES_SESSION_LIMIT

    # Fetch recent conversation session IDs
    recent_sessions = await db.execute_fetchall(
        "SELECT id FROM sessions "
        "WHERE user_id = ? AND mode = 'conversation' "
        f"ORDER BY started_at DESC LIMIT {limit}",
        (user_id,),
    )
    session_ids = [s["id"] for s in recent_sessions]

    corrections_data = []
    marks_data = []

    if session_ids:
        placeholders = ",".join("?" * len(session_ids))

        # Corrections — user explicitly asked "how to say this"
        corrections = await db.execute_fetchall(
            f"SELECT user_message, correction, explanation FROM corrections "
            f"WHERE session_id IN ({placeholders})",
            session_ids,
        )
        corrections_data = [
            {
                "user_message": c["user_message"],
                "correction": c["correction"],
                "explanation": c["explanation"],
            }
            for c in corrections
        ]

        # AI marks — segments + ai_marks
        seg_rows = await db.execute_fetchall(
            f"SELECT id, user_text FROM segments WHERE session_id IN ({placeholders})",
            session_ids,
        )
        seg_ids = [s["id"] for s in seg_rows]
        seg_text_map = {s["id"]: s["user_text"] for s in seg_rows}

        if seg_ids:
            mark_placeholders = ",".join("?" * len(seg_ids))
            marks = await db.execute_fetchall(
                f"SELECT segment_id, issue_types, original, suggestion "
                f"FROM ai_marks WHERE segment_id IN ({mark_placeholders})",
                seg_ids,
            )
            marks_data = [
                {
                    "issue_types": json.loads(m["issue_types"])
                    if isinstance(m["issue_types"], str)
                    else m["issue_types"],
                    "original": m["original"],
                    "suggestion": m["suggestion"],
                    "user_text": seg_text_map.get(m["segment_id"], ""),
                }
                for m in marks
            ]

    # Review summaries — still_struggling patterns
    review_summaries = await db.execute_fetchall(
        "SELECT practiced, notes FROM review_summaries "
        "WHERE user_id = ? "
        f"ORDER BY created_at DESC LIMIT {limit}",
        (user_id,),
    )
    struggling_patterns = []
    for rs in review_summaries:
        try:
            practiced = json.loads(rs["practiced"]) if isinstance(rs["practiced"], str) else rs["practiced"]
            if isinstance(practiced, list):
                for item in practiced:
                    if isinstance(item, dict) and item.get("performance") == "still_struggling":
                        struggling_patterns.extend(item.get("patterns", []))
        except (json.JSONDecodeError, TypeError):
            pass

    user_message = """\
Corrections (learner explicitly asked — highest priority):
{corrections_block}

AI-identified issues:
{marks_block}

Still-struggling patterns from review sessions:
{struggling_block}\
""".format(
        corrections_block=json.dumps(corrections_data, ensure_ascii=False, indent=2) if corrections_data else "  (None)",
        marks_block=json.dumps(marks_data, ensure_ascii=False, indent=2) if marks_data else "  (None)",
        struggling_block=json.dumps(struggling_patterns, ensure_ascii=False) if struggling_patterns else "  (None)",
    )

    result = await chat_json(QUICK_REVIEW_SYSTEM_PROMPT, user_message)

    quick_review = result.get("quick_review", [])

    # Re-read latest profile_data to avoid race with parallel updates
    now = datetime.now(timezone.utc).isoformat()
    rows = await db.execute_fetchall(
        "SELECT profile_data FROM user_profiles WHERE user_id = ?", (user_id,),
    )
    current_data = json.loads(rows[0]["profile_data"]) if rows else profile["profile_data"]
    current_data["quick_review"] = quick_review
    new_data = json.dumps(current_data, ensure_ascii=False)

    await db.execute(
        "UPDATE user_profiles SET profile_data = ?, updated_at = ? WHERE user_id = ?",
        (new_data, now, user_id),
    )
    await db.commit()

    log.info("User %s quick review updated (%d items)", user_id, len(quick_review))

    return {
        "user_id": user_id,
        "level": profile["level"],
        "profile_data": current_data,
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

"""Tests for review.py — generate_review, generate_correction, generate_session_review, generate_review_summary."""

import json
import sys
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Patch settings before importing any app modules
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from db import init_db, close_db, get_db
import review


@pytest.fixture(autouse=True)
async def setup_db(tmp_path):
    """Create an in-memory-like temp DB for each test."""
    import config
    config.settings.DB_PATH = str(tmp_path / "test.db")

    # Re-init with fresh DB
    import db as db_mod
    db_mod._db = None
    await init_db()
    yield
    await close_db()


async def _insert_session_and_segments(session_id="s1", user_id="u1", turns=None, topic_id=None):
    """Helper to insert a session with segments."""
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO sessions (id, user_id, started_at, status, topic_id) VALUES (?, ?, ?, ?, ?)",
        (session_id, user_id, now, "reviewing", topic_id),
    )
    if turns is None:
        turns = [
            ("How's your day?", "It's going well! How about you?"),
            ("The weather, I think good", "That's great to hear! The weather has been lovely."),
        ]
    for i, (user_text, ai_text) in enumerate(turns):
        await db.execute(
            "INSERT INTO segments (session_id, turn_index, user_text, ai_text, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, i, user_text, ai_text, now),
        )
    await db.commit()


# --- generate_review tests ---

@pytest.mark.asyncio
@patch("review.chat_json", new_callable=AsyncMock)
async def test_generate_review_writes_marks(mock_chat):
    """AI marks are written to DB from well-formed LLM response."""
    mock_chat.return_value = {
        "marks": [
            {
                "turn_index": 1,
                "issue_types": ["grammar", "naturalness"],
                "original": "The weather, I think good",
                "suggestion": "The weather's pretty nice today, I think",
                "explanation": "需要加 be 動詞；母語者更常把 I think 放在句尾",
            }
        ]
    }

    await _insert_session_and_segments()
    await review.generate_review("s1")

    db = await get_db()
    marks = await db.execute_fetchall("SELECT * FROM ai_marks")
    assert len(marks) == 1
    import json
    assert json.loads(marks[0]["issue_types"]) == ["grammar", "naturalness"]
    assert marks[0]["original"] == "The weather, I think good"


@pytest.mark.asyncio
@patch("review.chat_json", new_callable=AsyncMock)
async def test_generate_review_skips_malformed_marks(mock_chat):
    """Marks missing required fields are skipped, not crash."""
    mock_chat.return_value = {
        "marks": [
            {
                "turn_index": 1,
                # missing issue_types
                "original": "something",
                "suggestion": "something else",
                "explanation": "reason",
            },
            {
                "turn_index": 1,
                "issue_types": ["grammar"],
                "original": "The weather, I think good",
                "suggestion": "I think the weather is good",
                "explanation": "需要加 is",
            },
        ]
    }

    await _insert_session_and_segments()
    await review.generate_review("s1")

    db = await get_db()
    marks = await db.execute_fetchall("SELECT * FROM ai_marks")
    assert len(marks) == 1  # only the valid one


@pytest.mark.asyncio
@patch("review.chat_json", new_callable=AsyncMock)
async def test_generate_review_no_segments(mock_chat):
    """No segments → no crash, no LLM call."""
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO sessions (id, user_id, started_at, status) VALUES (?, ?, ?, ?)",
        ("empty", "u1", now, "reviewing"),
    )
    await db.commit()

    await review.generate_review("empty")
    mock_chat.assert_not_called()


@pytest.mark.asyncio
@patch("review.chat_json", new_callable=AsyncMock)
async def test_generate_review_unknown_turn_index(mock_chat):
    """LLM returns a turn_index that doesn't exist → skipped gracefully."""
    mock_chat.return_value = {
        "marks": [
            {
                "turn_index": 999,
                "issue_types": ["grammar"],
                "original": "x",
                "suggestion": "y",
                "explanation": "z",
            }
        ]
    }

    await _insert_session_and_segments()
    await review.generate_review("s1")

    db = await get_db()
    marks = await db.execute_fetchall("SELECT * FROM ai_marks")
    assert len(marks) == 0


# --- generate_correction tests ---

@pytest.mark.asyncio
@patch("review.chat_json", new_callable=AsyncMock)
async def test_generate_correction_success(mock_chat):
    """Correction is returned and stored in DB."""
    mock_chat.return_value = {
        "correction": "I think the weather is really nice today",
        "explanation": "可以用 nice 代替 good 來形容天氣",
    }

    await _insert_session_and_segments()

    # Get the segment_id for turn 1
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT id FROM segments WHERE session_id = 's1' AND turn_index = 1"
    )
    seg_id = rows[0]["id"]

    result = await review.generate_correction("s1", seg_id, "這句我想說天氣很好但不知道怎麼講")

    assert result["correction"] == "I think the weather is really nice today"
    assert result["explanation"] == "可以用 nice 代替 good 來形容天氣"
    assert result["segment_id"] == seg_id

    # Check DB
    corrections = await db.execute_fetchall("SELECT * FROM corrections")
    assert len(corrections) == 1
    assert corrections[0]["user_message"] == "這句我想說天氣很好但不知道怎麼講"


@pytest.mark.asyncio
@patch("review.chat_json", new_callable=AsyncMock)
async def test_generate_correction_invalid_segment(mock_chat):
    """Non-existent segment raises ValueError."""
    await _insert_session_and_segments()

    with pytest.raises(ValueError, match="Segment 9999 not found"):
        await review.generate_correction("s1", 9999, "help")

    mock_chat.assert_not_called()


# --- generate_session_review tests ---

@pytest.mark.asyncio
@patch("review.chat_json", new_callable=AsyncMock)
async def test_generate_session_review_success(mock_chat):
    """Final review is returned and stored in session_summaries."""
    mock_chat.return_value = {
        "strengths": ["能主動開啟話題", "回應速度快"],
        "weaknesses": {
            "grammar": "缺少 be 動詞，例如 'I think good' 應為 'I think it is good'",
            "naturalness": "用詞偏基礎，例如用 good 而非 nice/great",
            "sentence_structure": None,
        },
        "overall": "學習者能參與基本對話，但語法和自然度需要加強。",
    }

    await _insert_session_and_segments()

    # Pre-insert some AI marks
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT id FROM segments WHERE session_id = 's1' AND turn_index = 1"
    )
    seg_id = rows[0]["id"]
    await db.execute(
        "INSERT INTO ai_marks (segment_id, issue_types, original, suggestion, explanation) "
        "VALUES (?, ?, ?, ?, ?)",
        (seg_id, '["grammar"]', "I think good", "I think it is good", "缺少 be 動詞"),
    )
    await db.commit()

    result = await review.generate_session_review("s1", "u1")

    assert len(result["strengths"]) == 2
    assert result["weaknesses"]["grammar"] is not None
    assert result["weaknesses"]["sentence_structure"] is None

    # Check DB
    summary = await db.execute_fetchall("SELECT * FROM session_summaries WHERE session_id = 's1'")
    assert len(summary) == 1
    assert json.loads(summary[0]["weaknesses"])["grammar"] is not None


# --- generate_chat_summary tests ---

@pytest.mark.asyncio
@patch("review.chat_json", new_callable=AsyncMock)
async def test_generate_chat_summary_success(mock_chat):
    """Chat summary is generated and stored in chat_summaries table."""
    mock_chat.return_value = {
        "summary": "Discussed favorite weekend activities. The learner shared they enjoy hiking and cooking."
    }

    await _insert_session_and_segments(topic_id="weekend")

    result = await review.generate_chat_summary("s1", "weekend")

    assert result["summary"] == "Discussed favorite weekend activities. The learner shared they enjoy hiking and cooking."
    mock_chat.assert_called_once()

    # Verify DB write
    db = await get_db()
    rows = await db.execute_fetchall("SELECT * FROM chat_summaries WHERE session_id = 's1'")
    assert len(rows) == 1
    assert rows[0]["topic_id"] == "weekend"
    assert "hiking" in rows[0]["summary"]


@pytest.mark.asyncio
@patch("review.chat_json", new_callable=AsyncMock)
async def test_generate_chat_summary_no_segments(mock_chat):
    """No segments → no LLM call, returns empty summary."""
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO sessions (id, user_id, started_at, status, topic_id) VALUES (?, ?, ?, ?, ?)",
        ("empty", "u1", now, "reviewing", "weekend"),
    )
    await db.commit()

    result = await review.generate_chat_summary("empty", "weekend")

    assert result["summary"] == ""
    mock_chat.assert_not_called()


# --- generate_review_summary tests ---

@pytest.mark.asyncio
@patch("review.chat_json", new_callable=AsyncMock)
async def test_generate_review_summary_success(mock_chat):
    """Review summary is generated and stored in review_summaries table."""
    mock_chat.return_value = {
        "practiced": [
            {
                "dimension": "grammar",
                "patterns": ["過去式混用為現在式"],
                "performance": "improved",
            }
        ],
        "notes": "本次練習了過去式的使用，學習者大部分能正確回答，表現有進步。",
    }

    await _insert_session_and_segments(session_id="r1", user_id="u1")

    result = await review.generate_review_summary("r1", "u1")

    assert result is not None
    assert len(result["practiced"]) == 1
    assert result["practiced"][0]["dimension"] == "grammar"
    assert result["practiced"][0]["performance"] == "improved"
    assert "過去式" in result["notes"]
    mock_chat.assert_called_once()

    # Verify DB write
    db = await get_db()
    rows = await db.execute_fetchall("SELECT * FROM review_summaries WHERE session_id = 'r1'")
    assert len(rows) == 1
    assert rows[0]["user_id"] == "u1"
    assert "過去式" in rows[0]["notes"]
    practiced_db = json.loads(rows[0]["practiced"])
    assert practiced_db[0]["dimension"] == "grammar"


@pytest.mark.asyncio
@patch("review.chat_json", new_callable=AsyncMock)
async def test_generate_review_summary_no_segments(mock_chat):
    """No segments → return None, no LLM call."""
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO sessions (id, user_id, started_at, status, mode) VALUES (?, ?, ?, ?, ?)",
        ("empty_review", "u1", now, "ended", "review"),
    )
    await db.commit()

    result = await review.generate_review_summary("empty_review", "u1")

    assert result is None
    mock_chat.assert_not_called()

    # Verify nothing written to DB
    rows = await db.execute_fetchall("SELECT * FROM review_summaries WHERE session_id = 'empty_review'")
    assert len(rows) == 0

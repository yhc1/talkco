"""Tests for profile.py — update_profile_after_session, get_or_create_profile."""

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
import profile


@pytest.fixture(autouse=True)
async def setup_db(tmp_path):
    """Create a temp DB for each test."""
    import config
    config.settings.DB_PATH = str(tmp_path / "test.db")

    import db as db_mod
    db_mod._db = None
    await init_db()
    yield
    await close_db()


async def _create_user_profile(user_id="u1"):
    """Helper to insert a user profile so get_or_create_profile doesn't hit NOT NULL constraint."""
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    default_data = {
        "personal_facts": [],
        "weak_points": {"grammar": [], "naturalness": [], "sentence_structure": []},
        "common_errors": [],
    }
    await db.execute(
        "INSERT OR IGNORE INTO user_profiles (user_id, level, profile_data, updated_at) VALUES (?, ?, ?, ?)",
        (user_id, "intermediate", json.dumps(default_data), now),
    )
    await db.commit()


async def _insert_session_with_marks(session_id="s1", user_id="u1"):
    """Helper to insert a session with segments, marks, and corrections."""
    await _create_user_profile(user_id)
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO sessions (id, user_id, started_at, status) VALUES (?, ?, ?, ?)",
        (session_id, user_id, now, "reviewing"),
    )
    # Insert segments
    await db.execute(
        "INSERT INTO segments (session_id, turn_index, user_text, ai_text, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (session_id, 0, "I go to store yesterday", "Oh, what did you buy?", now),
    )
    await db.execute(
        "INSERT INTO segments (session_id, turn_index, user_text, ai_text, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (session_id, 1, "I buy some apple", "Sounds great!", now),
    )

    # Get segment IDs
    rows = await db.execute_fetchall(
        "SELECT id, turn_index FROM segments WHERE session_id = ?", (session_id,)
    )
    seg_map = {r["turn_index"]: r["id"] for r in rows}

    # Insert AI marks
    await db.execute(
        "INSERT INTO ai_marks (segment_id, issue_types, original, suggestion, explanation) "
        "VALUES (?, ?, ?, ?, ?)",
        (seg_map[0], '["grammar"]', "I go to store yesterday",
         "I went to the store yesterday", "過去式"),
    )
    await db.execute(
        "INSERT INTO ai_marks (segment_id, issue_types, original, suggestion, explanation) "
        "VALUES (?, ?, ?, ?, ?)",
        (seg_map[1], '["grammar", "naturalness"]', "I buy some apple",
         "I bought some apples", "過去式 + 可數名詞複數"),
    )

    # Insert a correction
    await db.execute(
        "INSERT INTO corrections (session_id, segment_id, user_message, correction, explanation, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, seg_map[0], "這句要怎麼說比較好", "I went to the store yesterday", "用過去式", now),
    )
    await db.commit()


@pytest.mark.asyncio
async def test_get_or_create_profile_default():
    """Default profile has expected fields including progress_notes."""
    result = await profile.get_or_create_profile("new_user")

    data = result["profile_data"]
    assert set(data.keys()) == {"personal_facts", "weak_points", "common_errors", "progress_notes"}
    assert data["personal_facts"] == []
    assert data["common_errors"] == []
    assert data["progress_notes"] == ""
    assert set(data["weak_points"].keys()) == {"grammar", "naturalness", "sentence_structure"}


@pytest.mark.asyncio
@patch("profile.chat_json", new_callable=AsyncMock)
async def test_update_profile_only_sends_transcript_marks_corrections(mock_chat):
    """update_profile_after_session sends only transcript, marks, corrections — no session_summary."""
    mock_chat.return_value = {
        "profile_data": {
            "personal_facts": [],
            "weak_points": {"grammar": [], "naturalness": [], "sentence_structure": []},
            "common_errors": [],
        }
    }

    await _insert_session_with_marks()
    await profile.update_profile_after_session("u1", "s1")

    mock_chat.assert_called_once()
    system_prompt, user_msg = mock_chat.call_args[0]

    # Verify transcript is included
    assert "Turn 0: User: I go to store yesterday" in user_msg
    assert "Turn 1: User: I buy some apple" in user_msg

    # Verify AI marks are included
    assert "[grammar]" in user_msg
    assert '"I go to store yesterday"' in user_msg

    # Verify corrections are included
    assert "Learner corrections:" in user_msg
    assert "這句要怎麼說比較好" in user_msg

    # Verify NO session summary or trend data
    assert "Session review:" not in user_msg
    assert "Strengths:" not in user_msg
    assert "Recent session history" not in user_msg


@pytest.mark.asyncio
@patch("profile.chat_json", new_callable=AsyncMock)
async def test_update_profile_sends_profile_data_only(mock_chat):
    """The prompt sends only profile_data, not the full profile (user_id, level, etc.)."""
    mock_chat.return_value = {
        "profile_data": {
            "personal_facts": ["住在台北"],
            "weak_points": {"grammar": [], "naturalness": [], "sentence_structure": []},
            "common_errors": [],
        }
    }

    await _insert_session_with_marks()
    await profile.update_profile_after_session("u1", "s1")

    _, user_msg = mock_chat.call_args[0]

    # Should contain profile_data content, not user_id or level
    assert "Current profile:" in user_msg
    assert "personal_facts" in user_msg
    assert '"user_id"' not in user_msg


@pytest.mark.asyncio
@patch("profile.chat_json", new_callable=AsyncMock)
async def test_update_profile_output_has_3_fields(mock_chat):
    """Output profile_data stored in DB has exactly 3 fields."""
    mock_chat.return_value = {
        "profile_data": {
            "personal_facts": ["住在台北", "是軟體工程師"],
            "weak_points": {
                "grammar": [
                    {
                        "pattern": "過去式混用為現在式",
                        "examples": [
                            {"wrong": "I go to store yesterday", "correct": "I went to the store yesterday"}
                        ],
                    }
                ],
                "naturalness": [],
                "sentence_structure": [],
            },
            "common_errors": ["經常漏掉冠詞 a/the"],
        }
    }

    await _insert_session_with_marks()
    result = await profile.update_profile_after_session("u1", "s1")

    data = result["profile_data"]
    assert set(data.keys()) == {"personal_facts", "weak_points", "common_errors"}
    assert data["personal_facts"] == ["住在台北", "是軟體工程師"]
    assert len(data["weak_points"]["grammar"]) == 1
    assert data["common_errors"] == ["經常漏掉冠詞 a/the"]

    # Verify DB persistence
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT profile_data FROM user_profiles WHERE user_id = 'u1'"
    )
    stored = json.loads(rows[0]["profile_data"])
    assert set(stored.keys()) == {"personal_facts", "weak_points", "common_errors"}


@pytest.mark.asyncio
async def test_compute_needs_review():
    """compute_needs_review returns True when any pattern has 3+ examples."""
    data_no_review = {
        "weak_points": {
            "grammar": [{"pattern": "test", "examples": [{"wrong": "a", "correct": "b"}]}],
        }
    }
    assert profile.compute_needs_review(data_no_review) is False

    data_needs_review = {
        "weak_points": {
            "grammar": [
                {
                    "pattern": "test",
                    "examples": [
                        {"wrong": "a", "correct": "b"},
                        {"wrong": "c", "correct": "d"},
                        {"wrong": "e", "correct": "f"},
                    ],
                }
            ],
        }
    }
    assert profile.compute_needs_review(data_needs_review) is True


@pytest.mark.asyncio
@patch("profile.chat_json", new_callable=AsyncMock)
async def test_generate_progress_notes(mock_chat):
    """generate_progress_notes queries session + review summaries and updates profile."""
    mock_chat.return_value = {
        "progress_notes": "你最近練習了日常對話，過去式的使用有明顯進步。建議加強自然度。"
    }

    await _create_user_profile("u2")
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()

    # Insert a conversation session with summary
    await db.execute(
        "INSERT INTO sessions (id, user_id, started_at, status, mode) VALUES (?, ?, ?, ?, ?)",
        ("s10", "u2", now, "completed", "conversation"),
    )
    await db.execute(
        "INSERT INTO session_summaries (session_id, user_id, strengths, weaknesses, overall, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("s10", "u2", '["Good vocabulary"]', '{"grammar": "Tense errors"}', "Making progress", now),
    )

    # Insert a review session with summary
    await db.execute(
        "INSERT INTO sessions (id, user_id, started_at, status, mode) VALUES (?, ?, ?, ?, ?)",
        ("s11", "u2", now, "ended", "review"),
    )
    await db.execute(
        "INSERT INTO review_summaries (session_id, user_id, practiced, notes, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("s11", "u2", "Past tense drills", "Improved accuracy", now),
    )
    await db.commit()

    result = await profile.generate_progress_notes("u2")

    # Verify chat_json was called with relevant data
    mock_chat.assert_called_once()
    system_prompt, user_msg = mock_chat.call_args[0]
    assert "progress" in system_prompt.lower() or "學習" in system_prompt
    assert "Good vocabulary" in user_msg
    assert "Past tense drills" in user_msg

    # Verify result
    assert result["profile_data"]["progress_notes"] == "你最近練習了日常對話，過去式的使用有明顯進步。建議加強自然度。"

    # Verify DB persistence
    rows = await db.execute_fetchall(
        "SELECT profile_data FROM user_profiles WHERE user_id = 'u2'"
    )
    stored = json.loads(rows[0]["profile_data"])
    assert stored["progress_notes"] == "你最近練習了日常對話，過去式的使用有明顯進步。建議加強自然度。"

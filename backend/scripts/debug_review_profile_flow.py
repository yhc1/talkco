"""
Seed a fake completed conversation and drive review/profile endpoints.

Usage (run backend first under debugger):
    cd backend
    python scripts/debug_review_profile_flow.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

import httpx
import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def seed_data(database_url: str, user_id: str, session_id: str) -> None:
    conn = psycopg2.connect(database_url)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Make reruns idempotent for the same session_id/user_id.
    cur.execute("DELETE FROM corrections WHERE session_id = %s", (session_id,))
    cur.execute(
        "DELETE FROM ai_marks WHERE segment_id IN (SELECT id FROM segments WHERE session_id = %s)",
        (session_id,),
    )
    cur.execute("DELETE FROM segments WHERE session_id = %s", (session_id,))
    cur.execute("DELETE FROM session_summaries WHERE session_id = %s", (session_id,))
    cur.execute("DELETE FROM chat_summaries WHERE session_id = %s", (session_id,))
    cur.execute("DELETE FROM review_summaries WHERE session_id = %s", (session_id,))
    cur.execute("DELETE FROM sessions WHERE id = %s", (session_id,))

    profile_data = {
        "personal_facts": ["住在台北", "是 PM"],
        "weak_points": {"grammar": [], "naturalness": [], "sentence_structure": []},
        "common_errors": [],
        "progress_notes": "",
    }
    cur.execute(
        "INSERT INTO user_profiles (user_id, level, profile_data, updated_at) VALUES (%s, %s, %s, %s) "
        "ON CONFLICT DO NOTHING",
        (user_id, "B1", json.dumps(profile_data, ensure_ascii=False), now_iso()),
    )

    cur.execute(
        "INSERT INTO sessions (id, user_id, started_at, status, mode, topic_id) VALUES (%s, %s, %s, %s, %s, %s)",
        (session_id, user_id, now_iso(), "reviewing", "conversation", "daily_life"),
    )

    turns = [
        ("Yesterday I go to office and discuss project with my boss.", "Got it. What was the key discussion?"),
        ("We discuss about timeline, and I very worry can not finish.", "Thanks for sharing. What made you most worried?"),
    ]
    for idx, (u, a) in enumerate(turns):
        cur.execute(
            "INSERT INTO segments (session_id, turn_index, user_text, ai_text, created_at) VALUES (%s, %s, %s, %s, %s)",
            (session_id, idx, u, a, now_iso()),
        )

    conn.commit()

    cur.execute(
        "SELECT id, turn_index FROM segments WHERE session_id = %s ORDER BY turn_index",
        (session_id,),
    )
    seg_rows = cur.fetchall()
    seg_id = {r["turn_index"]: r["id"] for r in seg_rows}

    cur.execute(
        "INSERT INTO ai_marks (segment_id, issue_types, original, suggestion, explanation) VALUES (%s, %s, %s, %s, %s)",
        (
            seg_id[0],
            json.dumps(["grammar"], ensure_ascii=False),
            "Yesterday I go to office",
            "Yesterday I went to the office",
            "過去式與冠詞",
        ),
    )
    cur.execute(
        "INSERT INTO ai_marks (segment_id, issue_types, original, suggestion, explanation) VALUES (%s, %s, %s, %s, %s)",
        (
            seg_id[1],
            json.dumps(["grammar", "sentence_structure"], ensure_ascii=False),
            "I very worry can not finish",
            "I am very worried that I can't finish",
            "be 動詞與子句結構",
        ),
    )
    cur.execute(
        "INSERT INTO corrections (session_id, segment_id, user_message, correction, explanation, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (
            session_id,
            seg_id[1],
            "這句怎麼講比較自然",
            "I'm very worried that I can't finish on time.",
            "加入 on time 並修正文法",
            now_iso(),
        ),
    )

    conn.commit()
    cur.close()
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--user-id", default="debug-user")
    parser.add_argument("--session-id", default="debug-session")
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set in environment / .env")
        sys.exit(1)

    seed_data(database_url, args.user_id, args.session_id)
    print(f"Seeded session={args.session_id}, user={args.user_id}")

    with httpx.Client(base_url=args.base_url, timeout=20.0) as client:
        before = client.get(f"/sessions/{args.session_id}/review")
        before.raise_for_status()
        before_payload = before.json()
        print("Before /end status:", before_payload.get("status"))

        # Optional: trigger real LLM correction output from main.py endpoint.
        segments = before_payload.get("segments", [])
        if segments:
            target_seg = segments[-1]
            corr_resp = client.post(
                f"/sessions/{args.session_id}/corrections",
                json={
                    "segment_id": target_seg["id"],
                    "user_message": "請幫我把這句改成自然、口語一點的英文，並解釋原因",
                },
            )
            corr_resp.raise_for_status()
            print("POST /corrections:", json.dumps(corr_resp.json(), ensure_ascii=False, indent=2))

        end_resp = client.post(f"/sessions/{args.session_id}/end")
        end_resp.raise_for_status()
        print("POST /end:", end_resp.json())

        for _ in range(30):
            r = client.get(f"/sessions/{args.session_id}/review")
            r.raise_for_status()
            payload = r.json()
            if payload.get("status") == "completed":
                print("Review status: completed")
                print("Session summary:", json.dumps(payload.get("summary"), ensure_ascii=False, indent=2))
                break
            time.sleep(1)
        else:
            print("Timed out waiting for completed status")

        p = client.get(f"/users/{args.user_id}/profile")
        p.raise_for_status()
        print("Updated profile_data:")
        print(json.dumps(p.json().get("profile_data"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

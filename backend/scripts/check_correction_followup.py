"""
Verify correction follow-up behavior through backend endpoint.

Goal:
- User asks a follow-up like "請給我多一點範例"
- AI should answer based on current segment error context
- AI should not just translate the follow-up request itself

Usage:
    cd backend
    python scripts/check_correction_followup.py --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

import httpx
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from openai import OpenAI


load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CheckResult:
    passed: bool
    score: int
    confidence: str
    checks: list[str]
    warnings: list[str]
    raw: dict


@dataclass
class FollowupScenario:
    name: str
    learner_message: str
    expected_focus: str
    required_behaviors: list[str]


JUDGE_SYSTEM_PROMPT = """\
You are a strict QA judge for an English-learning backend feature.

Task: Judge whether the model response to a learner follow-up is correct.

Pass criteria:
1) The response is grounded in the target sentence error context.
2) It does NOT simply translate/paraphrase the learner follow-up request itself.
3) Because learner asked for "請給我多一點範例", the response should provide extra examples or clear pattern practice.
4) correction/explanation must be coherent and useful for learning.

Return JSON only:
{
  "passed": true,
  "score": 0,
  "confidence": "high|medium|low",
  "checks": ["..."],
  "warnings": ["..."]
}

Scoring (0-100):
- 90-100: fully meets all criteria
- 70-89: mostly good with minor gaps
- 50-69: mixed quality, significant miss
- <50: wrong behavior
"""


def default_followup_scenarios() -> list[FollowupScenario]:
    return [
        FollowupScenario(
            name="more_examples",
            learner_message="請給我多一點範例",
            expected_focus="grammar+sentence_structure",
            required_behaviors=[
                "must stay on the target sentence error context",
                "should provide extra examples or pattern drills",
                "must not translate learner request as correction",
            ],
        ),
        FollowupScenario(
            name="grammar_why",
            learner_message="這句文法錯在哪？為什麼要這樣改？",
            expected_focus="grammar",
            required_behaviors=[
                "should explain grammar mistake precisely",
                "should connect explanation to corrected sentence",
            ],
        ),
        FollowupScenario(
            name="natural_rephrase",
            learner_message="這句可以更口語自然嗎？",
            expected_focus="naturalness",
            required_behaviors=[
                "should provide a more natural rephrase",
                "should avoid overly literal/chinglish phrasing",
            ],
        ),
        FollowupScenario(
            name="alt_phrasings",
            learner_message="還有其他說法嗎？給我 2 個版本",
            expected_focus="naturalness+variation",
            required_behaviors=[
                "should provide at least two viable alternatives in explanation or correction",
                "alternatives should preserve original meaning",
            ],
        ),
        FollowupScenario(
            name="chinglish_check",
            learner_message="我這句是不是中式英文？要怎麼改？",
            expected_focus="sentence_structure+naturalness",
            required_behaviors=[
                "should identify structure/naturalness issue",
                "should provide corrected native-like pattern",
            ],
        ),
    ]


def build_judge_input(
    scenario_name: str,
    learner_message: str,
    expected_focus: str,
    required_behaviors: list[str],
    segment_user_text: str,
    segment_ai_text: str,
    ai_marks: list[dict],
    correction: str,
    explanation: str,
) -> str:
    payload = {
        "scenario_name": scenario_name,
        "learner_message": learner_message,
        "expected_focus": expected_focus,
        "required_behaviors": required_behaviors,
        "segment_context": {
            "user_text": segment_user_text,
            "ai_text": segment_ai_text,
            "ai_marks": ai_marks,
        },
        "model_output": {
            "correction": correction,
            "explanation": explanation,
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def evaluate_response_with_llm(
    judge_model: str,
    openai_api_key: str,
    scenario_name: str,
    learner_message: str,
    expected_focus: str,
    required_behaviors: list[str],
    segment_user_text: str,
    segment_ai_text: str,
    ai_marks: list[dict],
    correction: str,
    explanation: str,
) -> CheckResult:
    client = OpenAI(api_key=openai_api_key)
    judge_input = build_judge_input(
        scenario_name=scenario_name,
        learner_message=learner_message,
        expected_focus=expected_focus,
        required_behaviors=required_behaviors,
        segment_user_text=segment_user_text,
        segment_ai_text=segment_ai_text,
        ai_marks=ai_marks,
        correction=correction,
        explanation=explanation,
    )

    resp = client.chat.completions.create(
        model=judge_model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": judge_input},
        ],
    )
    content = resp.choices[0].message.content or "{}"
    raw = json.loads(content)

    return CheckResult(
        passed=bool(raw.get("passed", False)),
        score=int(raw.get("score", 0)),
        confidence=str(raw.get("confidence", "low")),
        checks=list(raw.get("checks", [])),
        warnings=list(raw.get("warnings", [])),
        raw=raw,
    )


def seed_data(database_url: str, user_id: str, session_id: str) -> tuple[int, str, str, list[dict]]:
    conn = psycopg2.connect(database_url)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("DELETE FROM corrections WHERE session_id = %s", (session_id,))
    cur.execute(
        "DELETE FROM ai_marks WHERE segment_id IN (SELECT id FROM segments WHERE session_id = %s)",
        (session_id,),
    )
    cur.execute("DELETE FROM segments WHERE session_id = %s", (session_id,))
    cur.execute("DELETE FROM sessions WHERE id = %s", (session_id,))

    segment_user_text = "We discuss about timeline, and I very worry can not finish."
    segment_ai_text = "Thanks for sharing. What made you most worried?"
    cur.execute(
        "INSERT INTO sessions (id, user_id, started_at, status, mode, topic_id) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (session_id, user_id, now_iso(), "reviewing", "conversation", "daily_life"),
    )
    cur.execute(
        "INSERT INTO segments (session_id, turn_index, user_text, ai_text, created_at) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (
            session_id,
            0,
            segment_user_text,
            segment_ai_text,
            now_iso(),
        ),
    )
    segment_id = cur.fetchone()["id"]

    ai_mark = {
        "issue_types": ["grammar", "sentence_structure"],
        "original": "I very worry can not finish",
        "suggestion": "I am very worried that I can't finish on time.",
        "explanation": "需要 be 動詞，並改成 that 子句結構。",
    }
    cur.execute(
        "INSERT INTO ai_marks (segment_id, issue_types, original, suggestion, explanation) "
        "VALUES (%s, %s, %s, %s, %s)",
        (
            segment_id,
            json.dumps(ai_mark["issue_types"], ensure_ascii=False),
            ai_mark["original"],
            ai_mark["suggestion"],
            ai_mark["explanation"],
        ),
    )

    conn.commit()
    cur.close()
    conn.close()
    return segment_id, segment_user_text, segment_ai_text, [ai_mark]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--user-id", default="check-user")
    parser.add_argument("--session-id", default=f"check-correction-{uuid4().hex[:8]}")
    parser.add_argument("--judge-model", default=os.environ.get("CHAT_MODEL", "gpt-4o"))
    parser.add_argument(
        "--single-message",
        default=None,
        help="Override scenario set and run only one learner follow-up message.",
    )
    parser.add_argument("--strict", action="store_true", help="Fail on warnings as well.")
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set (backend/.env or shell env)")
        return 2
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if not openai_api_key:
        print("ERROR: OPENAI_API_KEY not set (required for LLM-as-a-judge)")
        return 2

    segment_id, segment_user_text, segment_ai_text, ai_marks = seed_data(
        database_url, args.user_id, args.session_id
    )
    print(f"Seeded session_id={args.session_id}, segment_id={segment_id}")

    scenarios = default_followup_scenarios()
    if args.single_message:
        scenarios = [
            FollowupScenario(
                name="single_message",
                learner_message=args.single_message,
                expected_focus="general",
                required_behaviors=[
                    "must answer based on current segment and ai_marks",
                    "must not translate learner request as correction",
                ],
            )
        ]

    failures = 0
    with httpx.Client(base_url=args.base_url, timeout=30.0) as client:
        for idx, scenario in enumerate(scenarios, 1):
            resp = client.post(
                f"/sessions/{args.session_id}/corrections",
                json={"segment_id": segment_id, "user_message": scenario.learner_message},
            )
            resp.raise_for_status()
            payload = resp.json()

            correction = payload.get("correction", "")
            explanation = payload.get("explanation", "")
            result = evaluate_response_with_llm(
                judge_model=args.judge_model,
                openai_api_key=openai_api_key,
                scenario_name=scenario.name,
                learner_message=scenario.learner_message,
                expected_focus=scenario.expected_focus,
                required_behaviors=scenario.required_behaviors,
                segment_user_text=segment_user_text,
                segment_ai_text=segment_ai_text,
                ai_marks=ai_marks,
                correction=correction,
                explanation=explanation,
            )

            print(f"\n=== Scenario {idx}/{len(scenarios)}: {scenario.name} ===")
            print(f"learner_message={scenario.learner_message}")
            print("Endpoint response:")
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            print(f"Judge ({args.judge_model}): passed={result.passed} score={result.score} confidence={result.confidence}")
            for c in result.checks:
                print(f"- {c}")
            for w in result.warnings:
                print(f"- WARNING: {w}")
            print("Raw judge JSON:")
            print(json.dumps(result.raw, ensure_ascii=False, indent=2))

            scenario_failed = (not result.passed) or (args.strict and bool(result.warnings))
            if scenario_failed:
                failures += 1

    if failures > 0:
        print(f"\nRESULT: FAIL ({failures}/{len(scenarios)} scenarios failed)")
        return 1
    print(f"\nRESULT: PASS ({len(scenarios)} scenarios)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

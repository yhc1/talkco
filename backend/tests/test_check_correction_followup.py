"""Tests for correction follow-up checker prompt wiring/parsing."""

import sys
import os


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.check_correction_followup import build_judge_input, default_followup_scenarios


def test_build_judge_input_contains_required_sections():
    judge_input = build_judge_input(
        scenario_name="more_examples",
        learner_message="請給我多一點範例",
        expected_focus="grammar+sentence_structure",
        required_behaviors=[
            "must stay on target context",
            "must not translate request",
        ],
        segment_user_text="We discuss about timeline, and I very worry can not finish.",
        segment_ai_text="What made you most worried?",
        ai_marks=[
            {
                "issue_types": ["grammar", "sentence_structure"],
                "original": "I very worry can not finish",
                "suggestion": "I am very worried that I can't finish on time.",
                "explanation": "需要 be 動詞，並改成 that 子句。",
            }
        ],
        correction="I am very worried that I can't finish on time.",
        explanation="你可以說：I am very worried that I can't finish on time.",
    )
    assert "learner_message" in judge_input
    assert "scenario_name" in judge_input
    assert "expected_focus" in judge_input
    assert "required_behaviors" in judge_input
    assert "segment_context" in judge_input
    assert "model_output" in judge_input
    assert "I very worry can not finish" in judge_input


def test_default_followup_scenarios_cover_grammar_and_naturalness():
    scenarios = default_followup_scenarios()
    assert len(scenarios) >= 5
    focuses = " ".join(s.expected_focus for s in scenarios).lower()
    assert "grammar" in focuses
    assert "naturalness" in focuses

"""Predefined conversation topics loaded from shared JSON."""

import json
from pathlib import Path

_JSON_PATH = Path(__file__).resolve().parent.parent / "shared" / "topics.json"

with open(_JSON_PATH, encoding="utf-8") as _f:
    _ALL_TOPICS = json.load(_f)

# Backend doesn't need the icon field
TOPICS = [{k: v for k, v in t.items() if k != "icon"} for t in _ALL_TOPICS]

_TOPICS_BY_ID = {t["id"]: t for t in TOPICS}


def get_topics() -> list[dict]:
    """Return all available topics."""
    return TOPICS


def get_topic_by_id(topic_id: str) -> dict | None:
    """Look up a topic by ID. Returns None if not found."""
    return _TOPICS_BY_ID.get(topic_id)

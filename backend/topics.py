"""Predefined conversation topics for the first version."""

TOPICS = [
    {
        "id": "daily_life",
        "label_en": "Daily Life",
        "label_zh": "日常生活",
        "prompt_hint": "Everyday routines, hobbies, weekend plans, food, weather",
    },
    {
        "id": "travel",
        "label_en": "Travel",
        "label_zh": "旅遊",
        "prompt_hint": "Travel experiences, planning trips, airports, hotels, sightseeing",
    },
    {
        "id": "workplace",
        "label_en": "Workplace",
        "label_zh": "職場",
        "prompt_hint": "Office conversations, meetings, emails, colleagues, career",
    },
    {
        "id": "food_dining",
        "label_en": "Food & Dining",
        "label_zh": "美食",
        "prompt_hint": "Ordering at restaurants, cooking, recipes, food culture",
    },
    {
        "id": "entertainment",
        "label_en": "Entertainment",
        "label_zh": "娛樂",
        "prompt_hint": "Movies, music, TV shows, games, social media",
    },
    {
        "id": "current_events",
        "label_en": "Current Events",
        "label_zh": "時事",
        "prompt_hint": "News, trends, technology, social topics",
    },
]

_TOPICS_BY_ID = {t["id"]: t for t in TOPICS}


def get_topics() -> list[dict]:
    """Return all available topics."""
    return TOPICS


def get_topic_by_id(topic_id: str) -> dict | None:
    """Look up a topic by ID. Returns None if not found."""
    return _TOPICS_BY_ID.get(topic_id)

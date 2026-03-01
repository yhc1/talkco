"""Shared constants loaded from shared/constants.json."""

import json
from enum import StrEnum
from pathlib import Path

_JSON_PATH = Path(__file__).resolve().parent.parent / "shared" / "constants.json"

with open(_JSON_PATH, encoding="utf-8") as _f:
    _CONSTANTS = json.load(_f)


# --- Session Modes ---

SessionMode = StrEnum("SessionMode", {
    v.upper(): v for v in _CONSTANTS["session_modes"]
})


# --- Session Statuses ---

SessionStatus = StrEnum("SessionStatus", {
    v.upper(): v for v in _CONSTANTS["session_statuses"]
})


# --- Issue Dimensions ---

IssueDimension = StrEnum("IssueDimension", {
    v.upper(): v for v in _CONSTANTS["issue_dimensions"]
})

DIMENSION_LABELS: dict[str, dict[str, str]] = {
    dim: {"en": info["en"], "zh": info["zh"]}
    for dim, info in _CONSTANTS["issue_dimensions"].items()
}

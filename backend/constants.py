"""Shared constants loaded from shared/constants.json."""

import json
from enum import StrEnum
from pathlib import Path

_JSON_PATH = Path(__file__).resolve().parent.parent / "shared" / "constants.json"

with open(_JSON_PATH, encoding="utf-8") as _f:
    _CONSTANTS = json.load(_f)


# --- Session Modes ---

class SessionMode(StrEnum):
    CONVERSATION = "conversation"
    REVIEW = "review"


# --- Session Statuses ---

class SessionStatus(StrEnum):
    ACTIVE = "active"
    REVIEWING = "reviewing"
    COMPLETING = "completing"
    COMPLETED = "completed"
    ENDED = "ended"


# --- Issue Dimensions ---

class IssueDimension(StrEnum):
    GRAMMAR = "grammar"
    NATURALNESS = "naturalness"
    SENTENCE_STRUCTURE = "sentence_structure"


DIMENSION_LABELS: dict[str, dict[str, str]] = {
    dim: {"en": info["en"], "zh": info["zh"]}
    for dim, info in _CONSTANTS["issue_dimensions"].items()
}


# --- Validate enums match JSON (fail fast on mismatch) ---

def _validate() -> None:
    for enum_cls, key in [
        (SessionMode, "session_modes"),
        (SessionStatus, "session_statuses"),
        (IssueDimension, "issue_dimensions"),
    ]:
        json_values = set(
            _CONSTANTS[key] if isinstance(_CONSTANTS[key], list)
            else _CONSTANTS[key].keys()
        )
        enum_values = {e.value for e in enum_cls}
        if json_values != enum_values:
            raise ValueError(
                f"{enum_cls.__name__} mismatch with constants.json[{key}]: "
                f"json={json_values}, enum={enum_values}"
            )


_validate()

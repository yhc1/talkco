from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    OPENAI_API_KEY: str
    S2S_MODEL: str = "gpt-4o-realtime-preview"
    S2S_VOICE: str = "alloy"
    CHAT_MODEL: str = "gpt-4o"
    DB_PATH: str = "talkco.db"

    # Query limits
    CONVERSATION_HISTORY_LIMIT: int = 5
    REVIEW_HISTORY_LIMIT: int = 5
    LEVEL_EVAL_SESSION_LIMIT: int = 10
    PROGRESS_NOTES_SESSION_LIMIT: int = 5

    # Profile constraints
    MAX_EXAMPLES_PER_PATTERN: int = 5
    MAX_PATTERNS_FOR_REVIEW: int = 3
    MAX_EXAMPLES_FOR_REVIEW: int = 3

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

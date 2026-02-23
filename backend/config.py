from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    OPENAI_API_KEY: str
    S2S_MODEL: str = "gpt-4o-realtime-preview"
    S2S_VOICE: str = "alloy"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

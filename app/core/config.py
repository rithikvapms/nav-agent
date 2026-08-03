from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI APMS Navigation Agent"
    environment: str = "development"
    api_prefix: str = "/v1"
    database_url: str
    groq_api_key: str
    groq_model: str = "llama-3.3-70b-versatile"
    api_keys: str = ""
    rate_limit_per_minute: int = 60
    max_history_messages: int = 8

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_api_keys(self) -> set[str]:
        return {key.strip() for key in self.api_keys.split(",") if key.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()

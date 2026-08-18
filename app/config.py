from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    github_webhook_secret: str
    github_token: str
    llm_base_url: str = "http://127.0.0.1:1234/v1"
    llm_api_key: str = "lm-studio"
    llm_model: str = ""
    max_files: int = 30
    max_patch_chars: int = 20_000
    llm_timeout_seconds: float = 180.0
    repos_file: Path = Path("repos.yaml")
    allow_unregistered: bool = False
    github_api_base: str = "https://api.github.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()

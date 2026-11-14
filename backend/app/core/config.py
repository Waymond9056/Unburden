from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> repo root is parents[3]
REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Unburden"
    api_prefix: str = "/api"
    cors_origins: str = "http://localhost:3000"

    database_url: str = f"sqlite:///{REPO_ROOT / 'data' / 'db' / 'unburden.db'}"
    upload_dir: str = str(REPO_ROOT / "data" / "uploads")
    seed_dir: str = str(REPO_ROOT / "data" / "seed")

    # LLM (used from Milestone 2 onward)
    llm_api_key: str = ""
    llm_base_url: str = "https://api.x.ai/v1"
    llm_model: str = "grok-4-1-fast-reasoning"

    default_patient_id: str = "patient-alex-rivera"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

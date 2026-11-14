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

    # Optional DeBERTa NLI signal (negation / high-precision support). Off by
    # default so CI and offline runs stay deterministic without model weights.
    use_nli_support: bool = False
    # Empty → MoritzLaurer zero-shot checkpoint. Set to a local fine-tune path
    # (e.g. backend/models/deberta-trec-nli) after TREC fine-tuning.
    nli_model_name: str = ""
    # Defaults aligned with TREC calibration (araag2/TREC_Clinical-Trials).
    # Runtime still prefers benchmarks/nli_calibrated_thresholds.json unless env set.
    nli_contradiction_min: float = 0.45
    nli_contradiction_margin: float = 0.15
    nli_entailment_min: float = 0.70

    default_patient_id: str = "patient-raymond-yao"

    # Chert FaceTime document intake (outbound video → frame capture → PDF upload)
    chert_api_key: str = ""
    chert_project_id: str = ""
    chert_line_id: str = ""
    chert_destination_phone: str = ""
    chert_agent_name: str = "document-intake"

    # LiveKit project used for BYOR outbound rooms (required to ring)
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

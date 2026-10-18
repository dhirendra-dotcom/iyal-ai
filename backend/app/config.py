from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "arthistics"
    google_cloud_project: str
    google_cloud_location: str = "global"
    google_genai_use_vertexai: str = "TRUE"
    gcs_bucket: str
    gemini_model: str = "gemini-3.8-flash"
    gemini_segmentation_model: str = "gemini-3.8-flash"
    gemini_transcription_model: str = "gemini-3.8-flash"
    gemini_image_model: str = "gemini-nano-banana-2.1"
    allowed_origins: str = "http://localhost:3000"
    max_upload_mb: int = Field(default=80, ge=1, le=250)
    max_transcription_mb: int = Field(default=10, ge=1, le=14)
    openscad_binary: str = "openscad"
    session_db_url: str | None = None

    # Optional Gemini Enterprise Agent Platform context services. Cloud Run stays
    # the execution runtime; these IDs point to managed Sessions / Memory Bank.
    agent_platform_location: str = ""
    vertex_session_runtime_id: str = ""
    vertex_memory_bank_id: str = ""
    memory_enabled: bool = False

    # Logging / observability. Cloud Run automatically switches auto -> JSON.
    arthistics_log_level: str = "INFO"
    arthistics_log_format: str = "auto"

    # Keep long-running SSE chat streams active through proxies while Gemini/tools are busy.
    sse_heartbeat_seconds: float = Field(default=10.0, ge=3.0, le=60.0)

    # Optional SMTP settings for real product-support booking confirmations.
    # When not configured, booking still works and email delivery is marked simulated.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    support_email_from: str = ""

    # Prototype market check. Gemini + Google Search grounding discovers current
    # off-the-shelf candidates before Arthistics considers custom fabrication.
    product_search_enabled: bool = True
    product_search_model: str = "gemini-3.8-flash"
    product_search_country: str = "India"
    product_search_top_k: int = Field(default=4, ge=1, le=8)
    product_search_timeout_seconds: int = Field(default=45, ge=15, le=120)
    product_search_retry_unparseable: bool = False  # unused since v0.13 (no JSON parsing)

    # v0.13.2 market-research efficiency controls.
    # Identical searches across sessions reuse a recent grounded answer (per instance).
    product_search_cache_ttl_seconds: int = Field(default=6 * 3600, ge=0, le=7 * 24 * 3600)
    product_search_cache_max_entries: int = Field(default=128, ge=0, le=2000)
    # Live grounded searches allowed per conversation; later calls reuse earlier research.
    product_search_max_per_session: int = Field(default=3, ge=1, le=10)
    # Links shown under the research answer, ranked by how much of the answer they support.
    product_search_max_sources: int = Field(default=5, ge=1, le=10)
    # Grounded calls normally finish in ~7-18 s but occasionally stall until the server
    # deadline (504, or 499 CANCELLED). Each attempt gets this deadline, with one retry on
    # 429/499/5xx/timeout, so the worst case is about 2 x 25 s instead of a 45 s stall + failure.
    product_search_attempt_timeout_seconds: int = Field(default=25, ge=10, le=60)
    product_search_max_attempts: int = Field(default=2, ge=1, le=3)
    # Calibrated measurement: Gemini localizes the target on a downscaled copy (OpenCV keeps
    # full resolution). Bounded attempts replace a single unbounded call (125 s observed).
    segmentation_max_image_px: int = Field(default=1536, ge=512, le=4096)
    segmentation_attempt_timeout_seconds: int = Field(default=30, ge=10, le=90)
    segmentation_max_attempts: int = Field(default=2, ge=1, le=3)

    # Main agent model: if no output arrives within this time, resend once.
    # The final attempt waits without a limit. 0 disables the retry.
    # Normal first chunks arrive in 1-4 s (up to ~21 s under load); a 94 s stall was seen with 40.
    agent_model_first_chunk_timeout_seconds: float = Field(default=25.0, ge=0.0, le=300.0)
    agent_model_max_attempts: int = Field(default=2, ge=1, le=3)

    # Calibrated physical measurement (OpenCV ArUco marker).
    calibration_marker_dictionary: str = "DICT_4X4_50"
    calibration_marker_id: int = Field(default=23, ge=0, le=49)
    calibration_marker_size_mm: float = Field(default=100.0, gt=10.0, le=300.0)

    # Default no-print reference for guided capture. ISO A4 dimensions.
    a4_short_side_mm: float = 210.0
    a4_long_side_mm: float = 297.0

    @property
    def allowed_origin_list(self) -> list[str]:
        return [x.strip() for x in self.allowed_origins.split(",") if x.strip()]

    @property
    def managed_sessions_enabled(self) -> bool:
        return bool(self.vertex_session_runtime_id.strip())

    @property
    def managed_memory_enabled(self) -> bool:
        return bool(self.memory_enabled and self.vertex_memory_bank_id.strip())

    @property
    def context_service_location(self) -> str:
        return (self.agent_platform_location or self.google_cloud_location).strip()

    def configure_google_environment(self) -> None:
        os.environ["GOOGLE_CLOUD_PROJECT"] = self.google_cloud_project
        os.environ["GOOGLE_CLOUD_LOCATION"] = self.google_cloud_location
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = self.google_genai_use_vertexai
        if self.managed_sessions_enabled or self.managed_memory_enabled:
            os.environ.setdefault("GOOGLE_GENAI_USE_ENTERPRISE", "TRUE")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.configure_google_environment()
    return settings


settings = get_settings()

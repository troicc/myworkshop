from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment or ``.env``.

    Every variable uses the ``MW_`` prefix so the application can live beside
    other AI tooling without collisions.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="MW_",
        case_sensitive=False,
        extra="ignore",
    )

    workspace_root: Path = Path("workspace")
    brand_file: Path = Path("brand/default/brand.yaml")
    max_image_retries: int = Field(default=1, ge=0, le=4)
    request_timeout: float = Field(default=180.0, ge=5, le=900)

    llm_provider: str = "mock"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-5-mini"
    llm_json_schema: bool = True
    llm_temperature: float = Field(default=0.2, ge=0, le=2)
    llm_max_tokens: int = Field(default=8000, ge=512, le=131072)

    image_provider: str = "mock"
    image_base_url: str = "https://api.openai.com/v1"
    image_api_key: str = ""
    image_model: str = "gpt-image-2"
    image_size: str = "1024x1536"
    image_quality: str = "high"
    image_output_format: str = "png"
    image_use_reference_edit: bool = False

    vision_provider: str = "off"
    vision_base_url: str = "https://api.openai.com/v1"
    vision_api_key: str = ""
    vision_model: str = "gpt-5-mini"

    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)

    @field_validator("llm_provider")
    @classmethod
    def validate_llm_provider(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"mock", "openai_compatible"}:
            raise ValueError("llm_provider must be mock or openai_compatible")
        return value

    @field_validator("image_provider")
    @classmethod
    def validate_image_provider(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"mock", "manual", "openai"}:
            raise ValueError("image_provider must be mock, manual, or openai")
        return value

    @field_validator("vision_provider")
    @classmethod
    def validate_vision_provider(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"off", "openai_compatible"}:
            raise ValueError("vision_provider must be off or openai_compatible")
        return value

    def ensure_directories(self) -> None:
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        (self.workspace_root / "projects").mkdir(parents=True, exist_ok=True)
        (self.workspace_root / "references").mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings

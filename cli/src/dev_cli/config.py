from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DEV_CLI_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- Paths ---
    dev_cli_home: Path = Field(
        default_factory=lambda: Path.home() / ".dev-cli",
        description="System-level config directory",
    )

    # --- Mode ---
    mode: Literal["direct", "proxy"] = Field(
        default="direct",
        description="'direct' calls the LLM API directly; 'proxy' routes through backend API",
    )

    # --- LLM (OpenAI-compatible, direct mode) ---
    # Set LLM_BASE_URL to any OpenAI-compatible endpoint:
    #   OpenAI:          https://api.openai.com/v1
    #   Anthropic:       https://api.anthropic.com/v1  (via openai SDK compat layer)
    #   Azure OpenAI:    https://<resource>.openai.azure.com/openai/deployments/<deploy>
    #   Ollama (local):  http://localhost:11434/v1
    #   LM Studio:       http://localhost:1234/v1
    llm_base_url: str = Field(default="https://api.openai.com/v1")
    llm_api_key: str = Field(default="", description="API key — set via DEV_CLI_LLM_API_KEY env var")
    llm_model: str = Field(default="gpt-4o", description="Model ID for the chosen provider")
    llm_max_tokens: int = Field(default=4096)
    llm_temperature: float = Field(default=0.7)

    # --- Backend proxy (Phase 2) ---
    api_endpoint: str = Field(default="https://api.internal.company.com")
    okta_domain: str = Field(default="")
    okta_client_id: str = Field(default="")

    # --- Conversation ---
    history_limit: int = Field(default=50, description="Max messages to load per session")
    manifest_ttl_seconds: int = Field(
        default=3600, description="Seconds before re-scanning project manifest"
    )

    # --- Logging ---
    log_level: str = Field(default="INFO")
    verbose: bool = Field(default=False)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

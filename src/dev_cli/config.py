from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Literal

import typer
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from rich.console import Console

_console = Console(stderr=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DEV_CLI_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
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
    # DEV_CLI_LLM_BASE_URL — choose your provider endpoint:
    #   OpenAI:          https://api.openai.com/v1
    #   Anthropic:       https://api.anthropic.com/v1  (via openai SDK compat layer)
    #   Azure OpenAI:    https://<resource>.openai.azure.com/openai/deployments/<deploy>
    #   Ollama (local):  http://localhost:11434/v1
    #   LM Studio:       http://localhost:1234/v1
    llm_base_url: str = Field(default="", description="Base URL of the OpenAI-compatible API — set via DEV_CLI_LLM_BASE_URL env var")
    llm_api_key: str = Field(default="", description="API key — set via DEV_CLI_LLM_API_KEY env var")
    llm_model: str = Field(default="gpt-4o", description="Model ID for the chosen provider")
    llm_max_tokens: int = Field(default=4096)
    llm_temperature: float = Field(default=0.7)
    llm_verify_ssl: bool = Field(
        default=True,
        description="Verify SSL certificates. Set to false for self-signed certs (e.g. vLLM dev servers).",
    )

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

    @model_validator(mode="after")
    def _check_required(self) -> Settings:
        """Validate required settings and print a clear error if any are missing."""
        errors: list[str] = []

        if self.mode == "direct":
            if not self.llm_api_key:
                errors.append(
                    "  [bold]DEV_CLI_LLM_API_KEY[/bold] is not set\n"
                    "    → Your API key for the LLM provider (OpenAI, Anthropic, etc.)\n"
                    "    → Example:  export DEV_CLI_LLM_API_KEY=sk-..."
                )
            if not self.llm_base_url:
                errors.append(
                    "  [bold]DEV_CLI_LLM_BASE_URL[/bold] is not set\n"
                    "    → Base URL of the OpenAI-compatible API endpoint\n"
                    "    → Example:  export DEV_CLI_LLM_BASE_URL=https://api.openai.com/v1"
                )
            if not self.llm_model:
                errors.append(
                    "  [bold]DEV_CLI_LLM_MODEL[/bold] is not set\n"
                    "    → Model ID to use, e.g. gpt-4o, claude-3-5-sonnet-20241022\n"
                    "    → Example:  export DEV_CLI_LLM_MODEL=gpt-4o"
                )

        if errors:
            _console.print()
            _console.print("[bold red]✗ Missing required configuration:[/bold red]")
            for err in errors:
                _console.print(f"\n{err}")
            _console.print()
            _console.print(
                "[dim]Tip: create a [bold].env[/bold] file in your project root "
                "or set the environment variables shown above.[/dim]"
            )
            _console.print()
            raise typer.Exit(code=1)

        return self


def _env_file_paths() -> list[str]:
    """Return .env search paths: CWD first, then binary directory (for standalone builds)."""
    cwd_env = Path.cwd() / ".env"
    paths = [str(cwd_env)]

    # When running as a PyInstaller frozen binary, also check next to the executable
    if getattr(sys, "frozen", False):
        binary_env = Path(sys.executable).parent / ".env"
        if binary_env.resolve() != cwd_env.resolve():
            paths.append(str(binary_env))

    return paths


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(_env_file=_env_file_paths())

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from dev_cli.config import get_settings
from dev_cli.storage.conversation import ConversationDB
from dev_cli.storage.manifest import ManifestStore
from dev_cli.version import __version__

console = Console()


def status_command(
    project_path: Path = typer.Option(Path("."), "--project-path", "-p", resolve_path=True),
) -> None:
    """Show dev-cli status: project info, conversation stats, config."""
    asyncio.run(_status(project_path))


async def _status(project_path: Path) -> None:
    settings = get_settings()
    manifest = ManifestStore.load(project_path)

    lines = [f"[bold]dev-cli[/bold] v{__version__}"]
    lines.append(f"  Mode:    [cyan]{settings.mode}[/cyan]")
    lines.append(f"  Project: {project_path.resolve()}")

    if manifest:
        lang_str = ", ".join(manifest.language_names) or "none detected"
        lines.append(f"  Languages: {lang_str}")
        fw_str = ", ".join(manifest.all_frameworks) or "none"
        lines.append(f"  Frameworks: {fw_str}")
    else:
        lines.append("  [yellow]No project manifest. Run [bold]dev-cli init[/bold].[/yellow]")

    dev_cli_dir = project_path / ".dev-cli"
    if dev_cli_dir.exists():
        db = ConversationDB(project_path)
        await db.initialize()
        conv = await db.get_or_create_conversation(str(project_path.resolve()))
        lines.append(f"  Messages: {conv.message_count} stored")
    else:
        lines.append("  Messages: [yellow]not initialized[/yellow]")

    if settings.mode == "direct":
        lines.append(f"\n[bold]LLM (direct mode)[/bold]")
        lines.append(f"  Model:   {settings.llm_model}")
        lines.append(f"  API URL: {settings.llm_base_url}")
        key_hint = "set" if settings.llm_api_key else "[yellow]NOT SET — set DEV_CLI_LLM_API_KEY[/yellow]"
        lines.append(f"  API key: {key_hint}")
    else:
        lines.append(f"\n[bold]Backend proxy[/bold]")
        lines.append(f"  Endpoint: {settings.api_endpoint}")
        lines.append("  Auth: [yellow]not configured (Phase 2)[/yellow]")

    console.print(Panel("\n".join(lines), title="dev-cli status", expand=False))

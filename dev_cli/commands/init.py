from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from dev_cli.detectors.detector import ProjectDetector
from dev_cli.storage.conversation import ConversationDB
from dev_cli.storage.manifest import ManifestStore

console = Console()


def init_command(
    project_path: Path = typer.Option(
        Path("."),
        "--project-path",
        "-p",
        help="Project root directory",
        resolve_path=True,
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing .dev-cli/ folder"),
) -> None:
    """Initialize .dev-cli/ in the current project."""
    asyncio.run(_init(project_path, force))


async def _init(project_path: Path, force: bool) -> None:
    dev_cli_dir = project_path / ".dev-cli"

    if dev_cli_dir.exists() and not force:
        console.print(
            f"[yellow].dev-cli/ already exists at {dev_cli_dir}[/yellow]\n"
            "Use [bold]--force[/bold] to reinitialize."
        )
        raise typer.Exit(1)

    # 1. Create directory + gitignore
    dev_cli_dir.mkdir(parents=True, exist_ok=True)
    gitignore = dev_cli_dir / ".gitignore"
    gitignore.write_text("*\n", encoding="utf-8")
    console.print(f"[green]✓[/green] Created {dev_cli_dir}")

    # 2. Initialize SQLite DB
    db = ConversationDB(project_path)
    await db.initialize()
    console.print("[green]✓[/green] Initialized conversation.db")

    # 3. Scan project
    console.print("[dim]Scanning project...[/dim]")
    detector = ProjectDetector()
    manifest = detector.detect(project_path)
    ManifestStore.save(project_path, manifest)

    # 4. Print summary
    if manifest.languages:
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Language")
        table.add_column("Frameworks")
        table.add_column("Files")
        for lang in manifest.languages:
            table.add_row(
                lang.language,
                ", ".join(lang.frameworks) or "—",
                str(lang.file_count),
            )
        console.print(table)
    else:
        console.print("[yellow]No languages detected (empty project)[/yellow]")

    # 5. System-level ~/.dev-cli/
    from dev_cli.config import get_settings
    settings = get_settings()
    settings.dev_cli_home.mkdir(parents=True, exist_ok=True)

    console.print(
        Panel(
            f"[green]Project initialized![/green]\n\n"
            f"  Project: [bold]{manifest.project_name}[/bold]\n"
            f"  Path:    {project_path.resolve()}\n\n"
            "Run [bold cyan]dev-cli chat[/bold cyan] to start a conversation.",
            title="dev-cli init",
            expand=False,
        )
    )

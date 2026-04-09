from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from dev_cli.detectors.detector import ProjectDetector
from dev_cli.storage.manifest import ManifestStore

console = Console()

OutputFormat = str  # "text" | "json" | "md"


def analyze_command(
    project_path: Path = typer.Option(
        Path("."),
        "--project-path",
        "-p",
        resolve_path=True,
    ),
    output: str = typer.Option("text", "--output", "-o", help="text | json | md"),
    depth: int = typer.Option(3, "--depth", help="Max folder scan depth"),
    refresh: bool = typer.Option(False, "--refresh", help="Force re-scan even if manifest is fresh"),
) -> None:
    """Analyze project structure and detect languages/frameworks."""
    if refresh or ManifestStore.is_stale(project_path, ttl_seconds=0 if refresh else 3600):
        detector = ProjectDetector()
        manifest = detector.detect(project_path)
        ManifestStore.save(project_path, manifest)
    else:
        manifest = ManifestStore.load(project_path)
        if manifest is None:
            detector = ProjectDetector()
            manifest = detector.detect(project_path)

    if output == "json":
        console.print_json(manifest.model_dump_json(indent=2))
        return

    if output == "md":
        lines = [f"# Project Analysis: {manifest.project_name}", ""]
        if manifest.languages:
            lines.append("## Languages Detected")
            for lang in manifest.languages:
                fw = f" ({', '.join(lang.frameworks)})" if lang.frameworks else ""
                ver = f" {lang.version}" if lang.version else ""
                lines.append(f"- {lang.language}{ver}{fw}")
            lines.append("")
            lines.append("## Key Files")
            for lang in manifest.languages:
                for f in lang.key_files:
                    lines.append(f"- `{f}`")
        console.print("\n".join(lines))
        return

    # Default: text with Rich table
    table = Table(title=f"Project: {manifest.project_name}", show_header=True, header_style="bold cyan")
    table.add_column("Language", style="bold")
    table.add_column("Version")
    table.add_column("Frameworks")
    table.add_column("Files", justify="right")
    table.add_column("Key Files")

    for lang in manifest.languages:
        table.add_row(
            lang.language,
            lang.version or "—",
            "\n".join(lang.frameworks) or "—",
            str(lang.file_count),
            "\n".join(lang.key_files[:5]),
        )

    console.print(table)

    if not manifest.languages:
        console.print("[yellow]No languages detected.[/yellow]")

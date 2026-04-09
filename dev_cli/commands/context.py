from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from dev_cli.storage.conversation import ConversationDB

console = Console()


def context_command(
    project_path: Path = typer.Option(Path("."), "--project-path", "-p", resolve_path=True),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of recent messages to show"),
    clear: bool = typer.Option(False, "--clear", help="Clear conversation history"),
    export: Path | None = typer.Option(None, "--export", help="Export history to file"),
) -> None:
    """View or manage conversation history."""
    asyncio.run(_context(project_path, limit, clear, export))


async def _context(
    project_path: Path,
    limit: int,
    clear: bool,
    export: Path | None,
) -> None:
    db = ConversationDB(project_path)

    dev_cli_dir = project_path / ".dev-cli"
    if not dev_cli_dir.exists():
        console.print("[yellow]No .dev-cli/ found. Run [bold]dev-cli init[/bold] first.[/yellow]")
        raise typer.Exit(1)

    await db.initialize()
    conv = await db.get_or_create_conversation(str(project_path.resolve()))

    if clear:
        confirmed = typer.confirm(
            f"Clear all {conv.message_count} messages in this conversation?", default=False
        )
        if confirmed:
            deleted = await db.clear_conversation(conv.id)
            console.print(f"[green]✓ Cleared {deleted} messages.[/green]")
        else:
            console.print("Cancelled.")
        return

    messages = await db.get_recent_messages(conv.id, limit=limit)

    if not messages:
        console.print("[dim]No conversation history yet.[/dim]")
        return

    if export:
        lines = [f"# Conversation History — {project_path.resolve().name}\n"]
        for msg in messages:
            role_label = "**You**" if msg.role == "user" else "**Assistant**"
            lines.append(f"## {role_label}\n{msg.content}\n")
        export.write_text("\n".join(lines), encoding="utf-8")
        console.print(f"[green]✓ Exported {len(messages)} messages to {export}[/green]")
        return

    table = Table(show_header=True, header_style="bold cyan", show_lines=True)
    table.add_column("#", justify="right", width=4)
    table.add_column("Role", width=10)
    table.add_column("Message", no_wrap=False)
    table.add_column("Time", width=20)

    for i, msg in enumerate(messages, 1):
        role_style = "bold green" if msg.role == "user" else "bold blue"
        snippet = msg.content[:200] + ("…" if len(msg.content) > 200 else "")
        table.add_row(
            str(i),
            f"[{role_style}]{msg.role}[/{role_style}]",
            snippet,
            msg.created_at.strftime("%Y-%m-%d %H:%M"),
        )

    console.print(table)
    console.print(f"[dim]Showing last {len(messages)} of {conv.message_count} messages[/dim]")

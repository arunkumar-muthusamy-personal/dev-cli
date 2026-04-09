from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from dev_cli.llm.client import LLMClient, LLMError
from dev_cli.llm.streaming import StreamingRenderer
from dev_cli.config import get_settings
from dev_cli.detectors.detector import ProjectDetector
from dev_cli.prompts.base import build_system_prompt
from dev_cli.storage.conversation import ConversationDB
from dev_cli.storage.manifest import ManifestStore

console = Console()

_HELP_TEXT = """
[bold cyan]In-chat commands:[/bold cyan]
  /history   Show conversation history
  /clear     Clear conversation history
  /context   Show project manifest
  /analyze   Re-scan project
  /exit      Exit chat (also: /quit, Ctrl+C)
  /help      Show this help
"""


def chat_command(
    project_path: Path = typer.Option(
        Path("."), "--project-path", "-p", resolve_path=True
    ),
    no_history: bool = typer.Option(False, "--no-history", help="Start fresh without loading history"),
    limit: int = typer.Option(50, "--limit", "-n", help="Max messages to load from history"),
) -> None:
    """Start an interactive AI chat session for this project."""
    asyncio.run(_chat(project_path, no_history, limit))


async def _chat(
    project_path: Path,
    no_history: bool,
    limit: int,
) -> None:
    settings = get_settings()

    # --- Ensure .dev-cli/ exists ---
    dev_cli_dir = project_path / ".dev-cli"
    if not dev_cli_dir.exists():
        console.print("[yellow]No .dev-cli/ found — initializing...[/yellow]")
        from dev_cli.commands.init import _init
        await _init(project_path, force=False)

    # --- Load / refresh manifest ---
    if ManifestStore.is_stale(project_path, ttl_seconds=settings.manifest_ttl_seconds):
        manifest = ProjectDetector().detect(project_path)
        ManifestStore.save(project_path, manifest)
    else:
        manifest = ManifestStore.load(project_path) or ProjectDetector().detect(project_path)

    # --- Project header ---
    lang_str = ", ".join(manifest.language_names) or "unknown"
    fw_str = ", ".join(manifest.all_frameworks)
    header = f"[bold]{manifest.project_name}[/bold]  •  {lang_str}"
    if fw_str:
        header += f"  •  {fw_str}"
    console.print(Panel(header, subtitle="dev-cli chat  •  /help for commands", expand=False))

    # --- Conversation storage ---
    db = ConversationDB(project_path)
    await db.initialize()
    conv = await db.get_or_create_conversation(str(project_path.resolve()))

    # --- Build initial messages list ---
    messages: list[dict[str, str]] = []
    if not no_history:
        history = await db.get_recent_messages(conv.id, limit=limit)
        messages = [{"role": m.role, "content": m.content} for m in history]
        if history:
            console.print(f"[dim]Loaded {len(history)} messages from history.[/dim]")

    # --- LLM client + renderer ---
    client = LLMClient()
    renderer = StreamingRenderer(console=console)
    system_prompt = build_system_prompt(manifest)

    console.print("[dim]Type your question or /help. Ctrl+C to exit.[/dim]\n")

    # --- REPL ---
    while True:
        try:
            user_input = Prompt.ask("[bold green]>[/bold green]", console=console).strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not user_input:
            continue

        # Slash commands
        if user_input.startswith("/"):
            handled = await _handle_slash(
                user_input, db, conv.id, manifest, project_path, console
            )
            if handled == "exit":
                console.print("[dim]Goodbye![/dim]")
                break
            continue

        # Save user message
        await db.add_message(conv.id, "user", user_input)
        messages.append({"role": "user", "content": user_input})

        # Stream response
        console.print()
        try:
            token_stream = client.stream(system_prompt=system_prompt, messages=messages)
            response_text = await renderer.render(token_stream)
        except LLMError as e:
            console.print(f"\n[red]Error: {e}[/red]")
            # Remove the failed user message from in-memory list to avoid corrupting history
            messages.pop()
            continue

        console.print()

        # Save assistant response
        estimated_tokens = len(response_text) // 4  # rough estimate
        await db.add_message(conv.id, "assistant", response_text, tokens=estimated_tokens)
        messages.append({"role": "assistant", "content": response_text})

        # Trim in-memory history to avoid unbounded growth
        if len(messages) > limit * 2:
            messages = messages[-(limit * 2):]


async def _handle_slash(
    cmd: str,
    db: ConversationDB,
    conv_id: str,
    manifest,
    project_path: Path,
    console: Console,
) -> str | None:
    """Handle slash commands. Returns 'exit' to signal loop exit, None otherwise."""
    cmd_lower = cmd.lower().split()[0]

    if cmd_lower in ("/exit", "/quit"):
        return "exit"

    if cmd_lower == "/help":
        console.print(Markdown(_HELP_TEXT))

    elif cmd_lower == "/history":
        from dev_cli.commands.context import _context
        await _context(project_path, limit=20, clear=False, export=None)

    elif cmd_lower == "/clear":
        confirmed = typer.confirm("Clear conversation history?", default=False)
        if confirmed:
            deleted = await db.clear_conversation(conv_id)
            console.print(f"[green]✓ Cleared {deleted} messages.[/green]")

    elif cmd_lower == "/context":
        console.print_json(manifest.model_dump_json(indent=2))

    elif cmd_lower == "/analyze":
        from dev_cli.commands.analyze import analyze_command
        new_manifest = ProjectDetector().detect(project_path)
        ManifestStore.save(project_path, new_manifest)
        console.print("[green]✓ Project re-analyzed.[/green]")
        from dev_cli.commands.analyze import analyze_command as _analyze
        _analyze(project_path=project_path)

    else:
        console.print(f"[yellow]Unknown command: {cmd}. Type /help.[/yellow]")

    return None

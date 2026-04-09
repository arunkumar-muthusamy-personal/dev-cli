from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from src.dev_cli.aws_cli.manager import AWSCLIManager, detect_aws_intent, is_aws_related
from src.dev_cli.git_cli.manager import GitManager
from src.dev_cli.git_cli.intent_detector import is_git_related
from src.dev_cli.config import get_settings
from src.dev_cli.context.file_ops import FileOpsManager, detect_file_op
from src.dev_cli.context.file_reader import FileContextReader
from src.dev_cli.context.file_writer import FileWriter
from src.dev_cli.detectors.detector import ProjectDetector
from src.dev_cli.llm.client import LLMClient, LLMError
from src.dev_cli.llm.streaming import StreamingRenderer
from src.dev_cli.prompts.base import build_system_prompt
from src.dev_cli.shell.runner import ShellRunner
from src.dev_cli.shell.task_detector import detect_task, resolve_command
from src.dev_cli.storage.conversation import ConversationDB
from src.dev_cli.storage.manifest import ManifestStore

console = Console()

_HELP_TEXT = """
[bold cyan]In-chat commands:[/bold cyan]
  /history        Show conversation history
  /clear          Clear conversation history
  /context        Show project manifest
  /analyze        Re-scan project
  /run <cmd>      Run a shell command and include output in context
  /git <cmd>      Run a git command and include output in context
  /aws <cmd>      Run an AWS CLI command and include output in context
  /files <paths>  Read specific files into context (space-separated)
  /exit           Exit chat (also: /quit, Ctrl+C)
  /help           Show this help
"""


def chat_command(
    project_path: Path = typer.Option(
        Path("."), "--project-path", "-p", resolve_path=True
    ),
    aws_profile: str | None = typer.Option(None, "--aws-profile", help="AWS profile to use"),
    no_history: bool = typer.Option(False, "--no-history", help="Start fresh without loading history"),
    no_files: bool = typer.Option(False, "--no-files", help="Disable automatic file context"),
    limit: int = typer.Option(50, "--limit", "-n", help="Max messages to load from history"),
) -> None:
    """Start an interactive AI chat session for this project."""
    asyncio.run(_chat(project_path, aws_profile, no_history, no_files, limit))


async def _chat(
    project_path: Path,
    aws_profile: str | None,
    no_history: bool,
    no_files: bool,
    limit: int,
) -> None:
    settings = get_settings()

    # --- Ensure .dev-cli/ exists ---
    dev_cli_dir = project_path / ".dev-cli"
    if not dev_cli_dir.exists():
        console.print("[yellow]No .dev-cli/ found — initializing...[/yellow]")
        from src.dev_cli.commands.init import _init
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

    # --- Tool instances ---
    file_reader  = FileContextReader(project_path)
    file_writer  = FileWriter(project_path, console=console)
    file_ops     = FileOpsManager(project_path, console=console)
    shell_runner = ShellRunner(console=console)
    aws_manager  = AWSCLIManager(console=console, aws_profile=aws_profile)
    git_manager  = GitManager(project_path, console=console)

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

        # --- Slash commands ---
        if user_input.startswith("/"):
            result = await _handle_slash(
                user_input, db, conv.id, manifest, project_path,
                shell_runner, aws_manager, console,
            )
            if result == "exit":
                console.print("[dim]Goodbye![/dim]")
                break
            # If slash command produced tool output, inject it as a user turn
            if isinstance(result, str) and result:
                await db.add_message(conv.id, "user", result)
                messages.append({"role": "user", "content": result})
                # Fall through to LLM call below
                user_input = result
            else:
                continue

        # --- Build enriched user message with file + AWS context ---
        extra_context_parts: list[str] = [user_input]

        # 0a. File operation detection — "delete X", "rename X to Y"
        if not user_input.startswith("["):
            file_op = detect_file_op(user_input)
            if file_op:
                op_result = file_ops.execute(file_op)
                if op_result:
                    extra_context_parts.append(op_result)

        # 0b. Dev task detection — "run tests", "build", "lint", etc.
        if not user_input.startswith("["):
            task = detect_task(user_input)
            if task:
                command = resolve_command(task, project_path, manifest)
                if command:
                    result = await shell_runner.run_with_confirm(command, cwd=str(project_path))
                    if result:
                        extra_context_parts.append(result.to_context_block())
                        console.print()

        # 1. File context (auto, unless disabled or message is slash-injected output)
        if not no_files and not user_input.startswith("["):
            file_ctx = file_reader.build(user_input)
            if file_ctx.files:
                console.print(f"[dim]Including files: {file_ctx.summary}[/dim]")
                extra_context_parts.append(file_ctx.to_prompt_block())

        # 2. Git context (auto-detect git intents)
        if is_git_related(user_input) and not user_input.startswith("["):
            git_result = await git_manager.run_from_message(user_input)
            if git_result:
                extra_context_parts.append(git_result.to_context_block())

        # 3. AWS context (auto-detect if message mentions AWS resources)
        if is_aws_related(user_input) and not user_input.startswith("["):
            intent = detect_aws_intent(user_input)
            if intent and "{" not in intent:  # skip templates needing placeholders
                aws_result = await aws_manager.run(intent, auto_confirm=False)
                if aws_result:
                    extra_context_parts.append(aws_result.to_context_block())

        enriched_message = "\n\n".join(extra_context_parts)

        # Save original user input (not enriched) for display
        if enriched_message != user_input:
            await db.add_message(conv.id, "user", user_input)
        else:
            await db.add_message(conv.id, "user", user_input)

        messages.append({"role": "user", "content": enriched_message})

        # --- Stream LLM response ---
        console.print()
        try:
            token_stream = client.stream(system_prompt=system_prompt, messages=messages)
            response_text = await renderer.render(token_stream)
        except LLMError as e:
            console.print(f"\n[red]LLM error: {e}[/red]")
            messages.pop()
            continue
        except Exception as e:
            console.print(f"\n[red]Unexpected error: {e}[/red]")
            messages.pop()
            continue

        console.print()

        # Save assistant response
        estimated_tokens = len(response_text) // 4
        await db.add_message(conv.id, "assistant", response_text, tokens=estimated_tokens)
        messages.append({"role": "assistant", "content": response_text})

        # Offer to write any files detected in the response
        file_writer.prompt_and_write(response_text)

        # Trim in-memory history
        if len(messages) > limit * 2:
            messages = messages[-(limit * 2):]


async def _handle_slash(
    cmd: str,
    db: ConversationDB,
    conv_id: str,
    manifest,
    project_path: Path,
    shell_runner: ShellRunner,
    aws_manager: AWSCLIManager,
    console: Console,
) -> str | None:
    """Handle slash commands.
    Returns:
      'exit'     → exit the chat loop
      str        → tool output to inject into LLM context
      None       → handled, no LLM call needed
    """
    parts = cmd.strip().split(None, 1)
    cmd_name = parts[0].lower()
    cmd_args = parts[1] if len(parts) > 1 else ""

    if cmd_name in ("/exit", "/quit"):
        return "exit"

    if cmd_name == "/help":
        console.print(Markdown(_HELP_TEXT))

    elif cmd_name == "/history":
        from src.dev_cli.commands.context import _context
        await _context(project_path, limit=20, clear=False, export=None)

    elif cmd_name == "/clear":
        confirmed = typer.confirm("Clear conversation history?", default=False)
        if confirmed:
            deleted = await db.clear_conversation(conv_id)
            console.print(f"[green]✓ Cleared {deleted} messages.[/green]")

    elif cmd_name == "/context":
        console.print_json(manifest.model_dump_json(indent=2))

    elif cmd_name == "/analyze":
        new_manifest = ProjectDetector().detect(project_path)
        ManifestStore.save(project_path, new_manifest)
        console.print("[green]✓ Project re-analyzed.[/green]")

    elif cmd_name == "/run":
        # Run arbitrary shell command and inject output into LLM context
        if not cmd_args:
            console.print("[yellow]Usage: /run <command>[/yellow]")
            return None
        result = await shell_runner.run_with_confirm(cmd_args, cwd=str(project_path))
        if result:
            return f"[Shell command output]\n{result.to_context_block()}"

    elif cmd_name == "/git":
        if not cmd_args:
            console.print("[yellow]Usage: /git <subcommand>  e.g. /git log --oneline -10[/yellow]")
            return None
        result = await git_manager.run(cmd_args)
        if result:
            return f"[Git output]\n{result.to_context_block()}"

    elif cmd_name == "/aws":
        # Run AWS CLI command and inject output
        if not cmd_args:
            console.print("[yellow]Usage: /aws <subcommand>[/yellow]")
            return None
        result = await aws_manager.run(cmd_args)
        if result:
            return f"[AWS CLI output]\n{result.to_context_block()}"

    elif cmd_name == "/files":
        # Read specific files into context
        if not cmd_args:
            console.print("[yellow]Usage: /files <path1> <path2> ...[/yellow]")
            return None
        file_paths = cmd_args.split()
        reader = FileContextReader(project_path)
        file_ctx = reader.read_explicit(file_paths)
        if file_ctx.files:
            console.print(f"[green]✓ Loaded: {file_ctx.summary}[/green]")
            return f"[File contents loaded]\n{file_ctx.to_prompt_block()}"
        else:
            console.print("[yellow]No readable files found at those paths.[/yellow]")

    else:
        console.print(f"[yellow]Unknown command: {cmd_name}. Type /help.[/yellow]")

    return None

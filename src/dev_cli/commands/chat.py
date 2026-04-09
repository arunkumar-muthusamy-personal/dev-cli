from __future__ import annotations

import asyncio
import re
from pathlib import Path

import typer
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion, PathCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from dev_cli.aws_cli.manager import AWSCLIManager, detect_aws_intent, is_aws_related
from dev_cli.config import get_settings
from dev_cli.context.file_ops import FileOpsManager, detect_file_op
from dev_cli.context.file_reader import FileContextReader
from dev_cli.context.file_writer import FileWriter
from dev_cli.detectors.detector import ProjectDetector
from dev_cli.git_cli.intent_detector import is_git_related
from dev_cli.git_cli.manager import GitManager
from dev_cli.llm.client import LLMClient, LLMError
from dev_cli.llm.streaming import StreamingRenderer
from dev_cli.prompts.base import build_system_prompt
from dev_cli.shell.runner import ShellRunner
from dev_cli.shell.task_detector import detect_task, resolve_command
from dev_cli.storage.conversation import ConversationDB
from dev_cli.storage.manifest import ManifestStore

console = Console()

# ---------------------------------------------------------------------------
# Intent helpers
# ---------------------------------------------------------------------------

_CREATE_INTENT = re.compile(
    r"\b(create|write|generate|make|scaffold|add|init(ialise|ialize)?)\b.{0,80}?\b(file|script|module|class|function|config|template)\b",
    re.I,
)
_CREATE_INTENT_LOOSE = re.compile(
    r"\b(create|write|generate|make|build)\b",
    re.I,
)
_QUESTION_WORDS = re.compile(
    r"^\s*(what|how|why|when|where|which|who|can you give|give me|show me|what'?s|whats|is there|are there|do you|could you|would you|tell me)",
    re.I,
)

def _is_question(message: str) -> bool:
    """Return True if the message looks like a question rather than a file-creation request."""
    if _CREATE_INTENT.search(message):
        return False
    # "can you create it?" / "can you make one?" end with ? but are creation requests
    if _CREATE_INTENT_LOOSE.search(message) and message.strip().endswith("?"):
        return False
    return bool(_QUESTION_WORDS.search(message) or message.strip().endswith("?"))

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


# ---------------------------------------------------------------------------
# prompt_toolkit input — multi-line paste + tab completion
# ---------------------------------------------------------------------------

_SLASH_CMDS = [
    "/help", "/history", "/clear", "/context", "/analyze",
    "/run", "/git", "/aws", "/files", "/exit", "/quit",
]


class _ChatCompleter(Completer):
    """Tab-complete slash commands and file paths."""

    def __init__(self, project_root: Path) -> None:
        self._path = PathCompleter(expanduser=True)
        self._root = project_root

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor

        # Slash command completion (no space yet)
        if text.startswith("/") and " " not in text:
            for cmd in _SLASH_CMDS:
                if cmd.startswith(text):
                    yield Completion(cmd[len(text):], display=cmd)
            return

        # Path completion: after /run or /files, or when the current word starts with ./ or /
        word = document.get_word_before_cursor(WORD=True)
        in_path_cmd = any(text.startswith(c + " ") for c in ("/run", "/files"))
        is_path_word = word.startswith(("./", "../", "/", "~"))
        if in_path_cmd or is_path_word:
            from prompt_toolkit.document import Document as _Doc
            yield from self._path.get_completions(_Doc(word, len(word)), complete_event)


def _make_session(project_root: Path) -> PromptSession:
    kb = KeyBindings()

    @kb.add("enter")
    def _send(event):
        """Enter submits the message."""
        event.current_buffer.validate_and_handle()

    @kb.add("escape", "enter")  # Alt+Enter / Option+Enter on macOS
    def _newline(event):
        """Alt+Enter inserts a newline (for typing multi-line manually)."""
        event.current_buffer.insert_text("\n")

    return PromptSession(
        history=InMemoryHistory(),
        completer=_ChatCompleter(project_root),
        complete_while_typing=False,
        multiline=True,
        prompt_continuation=lambda _w, _ln, _sw: "  ",
        key_bindings=kb,
    )


def chat_command(
    project_path: Path = typer.Option(
        Path("."), "--project-path", "-p", resolve_path=True
    ),
    aws_profile: str | None = typer.Option(None, "--aws-profile", help="AWS profile to use"),
    no_history: bool = typer.Option(False, "--no-history", help="Start fresh without loading history"),
    no_files: bool = typer.Option(False, "--no-files", help="Disable automatic file context"),
    no_hints: bool = typer.Option(False, "--no-hints", help="Hide the bottom key-binding toolbar"),
    limit: int = typer.Option(50, "--limit", "-n", help="Max messages to load from history"),
) -> None:
    """Start an interactive AI chat session for this project."""
    asyncio.run(_chat(project_path, aws_profile, no_history, no_files, no_hints, limit))


async def _chat(
    project_path: Path,
    aws_profile: str | None,
    no_history: bool,
    no_files: bool,
    no_hints: bool,
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

    console.print("[dim]Type your question and press Enter to send. Paste multi-line text freely. Ctrl+C to exit.[/dim]\n")

    session = _make_session(project_path)
    show_hints = settings.show_hints and not no_hints
    toolbar = HTML(" <b>Enter</b>=send  <b>Alt+Enter</b>=newline  <b>Tab</b>=complete  <b>/help</b>=commands ") if show_hints else None

    # --- REPL ---
    while True:
        try:
            user_input = (
                await session.prompt_async(HTML("<ansigreen><b>❯ </b></ansigreen>"), bottom_toolbar=toolbar)
            ).strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not user_input:
            continue

        # --- Slash commands ---
        if user_input.startswith("/"):
            result = await _handle_slash(
                user_input, db, conv.id, manifest, project_path,
                shell_runner, aws_manager, git_manager, console,
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

        # 0. Scan any absolute directory/file paths mentioned in the message
        if not user_input.startswith("["):
            dir_listing = file_reader.scan_mentioned_dirs(user_input)
            if dir_listing:
                extra_context_parts.append(dir_listing)

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

        # 1. File context (auto, unless disabled, slash-injected, or pure knowledge question)
        if not no_files and not user_input.startswith("[") and not _is_question(user_input):
            with console.status("[dim]Reading files…[/dim]", spinner="dots"):
                file_ctx = file_reader.build(user_input)
            if file_ctx.files:
                console.print(f"[dim]Including files: {file_ctx.summary}[/dim]")
                extra_context_parts.append(file_ctx.to_prompt_block())

        # 2. Git context (auto-detect git intents)
        if is_git_related(user_input) and not user_input.startswith("["):
            with console.status("[dim]Running git…[/dim]", spinner="dots"):
                git_result = await git_manager.run_from_message(user_input)
            if git_result:
                extra_context_parts.append(git_result.to_context_block())

        # 3. AWS context (auto-detect if message mentions AWS resources)
        if is_aws_related(user_input) and not user_input.startswith("["):
            intent = detect_aws_intent(user_input)
            if intent and "{" not in intent:  # skip templates needing placeholders
                with console.status("[dim]Running AWS CLI…[/dim]", spinner="dots"):
                    aws_result = await aws_manager.run(intent, auto_confirm=False)
                if aws_result:
                    extra_context_parts.append(aws_result.to_context_block())

        enriched_message = "\n\n".join(extra_context_parts)

        # If the user is asking a question (not requesting file creation), tell the LLM explicitly
        if _is_question(user_input):
            enriched_message += "\n\n[IMPORTANT: This is a question — respond with inline commands or explanations only. Do NOT produce any file output or scripts.]"
        elif not user_input.startswith("[") and _CREATE_INTENT_LOOSE.search(user_input):
            enriched_message += (
                "\n\n[INSTRUCTION: The user wants you to CREATE actual code. "
                "Generate the COMPLETE file content now. "
                "ALWAYS use the ### `filename.ext` header before the code block. "
                "Do NOT give instructions or tutorials — write the actual working code.]"
            )

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
        file_writer.prompt_and_write(response_text, user_message=user_input)

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
    git_manager: GitManager,
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
        from dev_cli.commands.context import _context
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

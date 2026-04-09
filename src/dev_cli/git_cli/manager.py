"""Git CLI execution manager.

Resolves placeholder templates, classifies risk, asks appropriate
confirmation, executes via the shell runner.
"""
from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm, Prompt

from dev_cli.git_cli.command_classifier import GitRisk, classify
from dev_cli.git_cli.intent_detector import detect_git_intent
from dev_cli.shell.runner import CommandResult, ShellRunner

# Placeholders that need user input before the command can run
_PLACEHOLDERS = {
    "{branch}":  ("Branch name", None),
    "{commit}":  ("Commit hash or ref", None),
    "{message}": ("Commit message", None),
    "{tag}":     ("Tag name", None),
    "{file}":    ("File path", None),
    "{remote}":  ("Remote name", "origin"),
}


def _resolve_template(template: str, console: Console) -> str | None:
    """Interactively fill in any {placeholder} values. Returns None if cancelled."""
    command = template
    for placeholder, (label, default) in _PLACEHOLDERS.items():
        if placeholder not in command:
            continue
        value = Prompt.ask(
            f"  {label}",
            console=console,
            default=default or "",
        ).strip()
        if not value:
            console.print("[yellow]Cancelled — no value provided.[/yellow]")
            return None
        command = command.replace(placeholder, value)
    return command


class GitManager:
    """Orchestrate natural-language → git command execution."""

    def __init__(
        self,
        project_path: Path,
        console: Console | None = None,
    ) -> None:
        self._cwd    = str(project_path)
        self._console = console or Console()
        self._shell  = ShellRunner(console=self._console)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def run_from_message(self, message: str) -> CommandResult | None:
        """Detect intent, resolve template, confirm, execute."""
        template = detect_git_intent(message)
        if not template:
            return None
        return await self.run(template)

    async def run(self, command_or_template: str) -> CommandResult | None:
        """Resolve any placeholders, confirm at the right level, execute."""
        # Resolve placeholders
        command = _resolve_template(command_or_template, self._console)
        if command is None:
            return None

        risk = classify(command)

        if risk == GitRisk.READ:
            confirmed = self._confirm_read(command)
        elif risk == GitRisk.MODIFY:
            confirmed = self._confirm_modify(command)
        else:
            confirmed = self._confirm_destructive(command)

        if not confirmed:
            return None

        self._console.print("[dim]Running...[/dim]")
        result = await self._shell.run_silent(command, cwd=self._cwd)

        if result.output.strip():
            self._console.print(f"\n[dim]{result.output.strip()}[/dim]\n")

        if not result.success:
            self._console.print(
                f"[yellow]git exited with code {result.returncode}[/yellow]"
            )
        return result

    # ------------------------------------------------------------------
    # Confirmation helpers
    # ------------------------------------------------------------------

    def _confirm_read(self, cmd: str) -> bool:
        self._console.print(f"\n[bold cyan]Git:[/bold cyan] [cyan]{cmd}[/cyan]")
        return Confirm.ask("Run?", console=self._console, default=True)

    def _confirm_modify(self, cmd: str) -> bool:
        self._console.print(f"\n[bold yellow]Git (modifies history/state):[/bold yellow]")
        self._console.print(f"  [yellow]{cmd}[/yellow]")
        return Confirm.ask("Confirm?", console=self._console, default=False)

    def _confirm_destructive(self, cmd: str) -> bool:
        self._console.print(f"\n[bold red]⚠ Destructive git operation — this may lose work:[/bold red]")
        self._console.print(f"  [red]{cmd}[/red]")
        first = Confirm.ask("Are you sure?", console=self._console, default=False)
        if not first:
            return False
        typed = Prompt.ask(
            "Type [bold]YES[/bold] to confirm",
            console=self._console,
        )
        return typed.strip() == "YES"

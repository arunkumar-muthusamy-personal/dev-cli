"""Cross-platform shell command runner.

Executes shell commands on Windows (cmd / PowerShell) and Mac/Linux (bash/zsh).
Always asks user confirmation before running. Returns stdout+stderr as a string
for inclusion in the LLM context.
"""
from __future__ import annotations

import asyncio
import platform
import shlex
import subprocess
from dataclasses import dataclass

from rich.console import Console
from rich.prompt import Confirm

_IS_WINDOWS = platform.system() == "Windows"
_TIMEOUT = 60  # seconds


@dataclass
class CommandResult:
    command: str
    stdout: str
    stderr: str
    returncode: int
    timed_out: bool = False

    @property
    def output(self) -> str:
        """Combined stdout + stderr, truncated to ~20k chars."""
        combined = self.stdout
        if self.stderr:
            combined += f"\n[stderr]\n{self.stderr}"
        return combined[:20_000]

    @property
    def success(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    def to_context_block(self) -> str:
        status = "success" if self.success else f"exit code {self.returncode}"
        if self.timed_out:
            status = "timed out"
        return (
            f"## Shell Command\n"
            f"```\n$ {self.command}\n```\n"
            f"**Status:** {status}\n"
            f"```\n{self.output or '(no output)'}\n```\n"
        )


class ShellRunner:
    """Run shell commands cross-platform with user confirmation."""

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()

    async def run_with_confirm(
        self,
        command: str,
        cwd: str | None = None,
        auto_confirm: bool = False,
    ) -> CommandResult | None:
        """Show the command, ask confirmation, execute. Returns None if cancelled."""
        self._console.print(f"\n[bold yellow]Run command:[/bold yellow]")
        self._console.print(f"  [cyan]$ {command}[/cyan]\n")

        if not auto_confirm:
            confirmed = Confirm.ask("Execute?", console=self._console, default=False)
            if not confirmed:
                self._console.print("[dim]Cancelled.[/dim]")
                return None

        self._console.print("[dim]Running...[/dim]")
        result = await self._execute(command, cwd=cwd)

        if result.timed_out:
            self._console.print(f"[red]Command timed out after {_TIMEOUT}s[/red]")
        elif not result.success:
            self._console.print(f"[yellow]Command exited with code {result.returncode}[/yellow]")

        return result

    async def run_silent(
        self,
        command: str,
        cwd: str | None = None,
    ) -> CommandResult:
        """Execute without confirmation (for internal use)."""
        return await self._execute(command, cwd=cwd)

    # ------------------------------------------------------------------

    async def _execute(self, command: str, cwd: str | None = None) -> CommandResult:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self._run_subprocess(command, cwd)
        )

    def _run_subprocess(self, command: str, cwd: str | None) -> CommandResult:
        if _IS_WINDOWS:
            # Use cmd.exe on Windows; supports both built-ins and PATH executables
            args = ["cmd.exe", "/c", command]
        else:
            # Use bash on Mac/Linux
            args = ["/bin/bash", "-c", command]

        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
                cwd=cwd,
                encoding="utf-8",
                errors="replace",
            )
            return CommandResult(
                command=command,
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                returncode=proc.returncode,
            )
        except subprocess.TimeoutExpired:
            return CommandResult(
                command=command,
                stdout="",
                stderr=f"Command timed out after {_TIMEOUT} seconds.",
                returncode=-1,
                timed_out=True,
            )
        except FileNotFoundError as e:
            return CommandResult(
                command=command,
                stdout="",
                stderr=f"Command not found: {e}",
                returncode=127,
            )
        except Exception as e:
            return CommandResult(
                command=command,
                stdout="",
                stderr=f"Unexpected error: {e}",
                returncode=-1,
            )


def detect_shell() -> str:
    """Return the shell being used (for display purposes)."""
    if _IS_WINDOWS:
        return "cmd.exe"
    import os
    return os.environ.get("SHELL", "/bin/bash")

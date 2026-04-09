"""Detect and execute file operation intents from natural language.

Handles: delete, rename/move files — with confirmation before any destructive action.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm, Prompt


class FileOpKind(str, Enum):
    DELETE = "delete"
    RENAME = "rename"


@dataclass
class FileOpIntent:
    kind: FileOpKind
    path: str             # primary path (file to delete or source of rename)
    dest: str | None = None  # destination path for rename/move


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

_DELETE_PATTERN = re.compile(
    r"\b(?:delete|remove|erase|get rid of|drop)\b.{0,60}?([\w./ \\-]+\.[\w]+)",
    re.I,
)

_RENAME_PATTERN = re.compile(
    r"\b(?:rename|move)\b.{0,60}?([\w./ \\-]+\.[\w]+).{0,30}(?:to|as|into)\s+([\w./ \\-]+\.[\w]+)",
    re.I,
)

# Extensions we're willing to operate on
_OPERABLE_EXTENSIONS = frozenset({
    ".py", ".ts", ".tsx", ".js", ".jsx",
    ".tf", ".tfvars", ".hcl",
    ".yaml", ".yml", ".json", ".toml", ".ini",
    ".sh", ".bash", ".ps1",
    ".sql", ".graphql",
    ".md", ".txt", ".rst",
    ".html", ".css", ".scss",
    ".dockerfile", ".gitignore",
    ".tf", ".tfvars",
})


def _is_operable(path: str) -> bool:
    return Path(path).suffix.lower() in _OPERABLE_EXTENSIONS


def detect_file_op(message: str) -> FileOpIntent | None:
    """Return a FileOpIntent if the message is asking to delete or rename a file."""
    # Check rename/move first (more specific)
    m = _RENAME_PATTERN.search(message)
    if m and _is_operable(m.group(1)):
        return FileOpIntent(kind=FileOpKind.RENAME, path=m.group(1).strip(), dest=m.group(2).strip())

    # Check delete
    m = _DELETE_PATTERN.search(message)
    if m and _is_operable(m.group(1)):
        return FileOpIntent(kind=FileOpKind.DELETE, path=m.group(1).strip())

    return None


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

class FileOpsManager:
    def __init__(self, project_path: Path, console: Console | None = None) -> None:
        self._root    = project_path
        self._console = console or Console()

    def execute(self, intent: FileOpIntent) -> str | None:
        """Confirm and execute a file operation. Returns a context string for the LLM."""
        if intent.kind == FileOpKind.DELETE:
            return self._delete(intent.path)
        if intent.kind == FileOpKind.RENAME:
            return self._rename(intent.path, intent.dest or "")
        return None

    # ------------------------------------------------------------------

    def _resolve(self, raw: str) -> Path | None:
        """Find the file relative to project root, trying a few path variants."""
        candidates = [
            self._root / raw,
            self._root / raw.replace("\\", "/"),
            self._root / Path(raw).name,  # just filename, search below
        ]
        for c in candidates[:2]:
            if c.exists():
                return c
        # Fuzzy: search for filename anywhere under project root
        name = Path(raw).name
        for found in self._root.rglob(name):
            parts = found.parts
            if not any(p.startswith(".") or p in ("node_modules", "__pycache__", "venv", ".venv")
                       for p in parts):
                return found
        return None

    def _delete(self, raw_path: str) -> str | None:
        path = self._resolve(raw_path)
        if not path:
            self._console.print(f"[yellow]File not found: {raw_path}[/yellow]")
            return None

        rel = str(path.relative_to(self._root))
        self._console.print(f"\n[bold red]Delete file:[/bold red] [red]{rel}[/red]")
        confirmed = Confirm.ask("Confirm delete?", console=self._console, default=False)
        if not confirmed:
            self._console.print("[dim]Cancelled.[/dim]")
            return None

        try:
            path.unlink(missing_ok=True)
            self._console.print(f"[green]✓[/green] Deleted {rel}")
            return f"File `{rel}` was deleted successfully."
        except Exception as e:
            self._console.print(f"[red]Failed to delete {rel}: {e}[/red]")
            return f"Failed to delete `{rel}`: {e}"

    def _rename(self, raw_src: str, raw_dest: str) -> str | None:
        src = self._resolve(raw_src)
        if not src:
            self._console.print(f"[yellow]File not found: {raw_src}[/yellow]")
            return None

        dest = self._root / raw_dest
        rel_src  = str(src.relative_to(self._root))
        rel_dest = raw_dest

        self._console.print(f"\n[bold yellow]Rename/move:[/bold yellow]")
        self._console.print(f"  [yellow]{rel_src}[/yellow] → [green]{rel_dest}[/green]")
        confirmed = Confirm.ask("Confirm?", console=self._console, default=False)
        if not confirmed:
            self._console.print("[dim]Cancelled.[/dim]")
            return None

        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            self._console.print(f"[green]✓[/green] Moved {rel_src} → {rel_dest}")
            return f"File `{rel_src}` was moved to `{rel_dest}` successfully."
        except Exception as e:
            self._console.print(f"[red]Failed: {e}[/red]")
            return f"Failed to move `{rel_src}`: {e}"

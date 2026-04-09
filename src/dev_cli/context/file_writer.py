"""Parse LLM responses for code blocks and write/patch files on disk.

Handles three scenarios:
  1. New file     — path not on disk → create it
  2. Full replace — path exists, LLM output is the complete new file → show diff, overwrite
  3. Patch/diff   — LLM output is a unified diff (--- / +++ lines) → apply the patch

Detected from these common LLM output patterns:

  Pattern 1 — filename in header above code block:
    ### `main.tf`
    ```hcl
    resource "aws_lambda_function" ...
    ```

  Pattern 2 — filename as first-line comment inside code block:
    ```python
    # src/handler.py
    import json
    ```

  Pattern 3 — filename after the language tag:
    ```hcl main.tf
    resource ...
    ```

  Pattern 4 — unified diff block:
    ```diff
    --- a/main.tf
    +++ b/main.tf
    @@ -1,4 +1,6 @@
    ...
    ```
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.syntax import Syntax
from rich.table import Table

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_CODE_BLOCK = re.compile(
    r"```(?P<lang>\w*)?(?:\s+(?P<inline_path>[\w./\\-]+\.\w+))?\n(?P<body>.*?)```",
    re.DOTALL,
)
_HEADER_PATH = re.compile(
    r"(?:#{1,4}\s+[`'\"]?)([\w./\\-]+\.[\w]+)[`'\"]?\s*\n\s*```"
)
_COMMENT_PATH = re.compile(
    r"^(?:#|//|--)\s*([\w./\\-]+\.[\w]+)\s*$"
)
# Unified diff file headers
_DIFF_FROM = re.compile(r"^---\s+(?:a/)?([\w./\\-]+)", re.MULTILINE)
_DIFF_TO   = re.compile(r"^\+\+\+\s+(?:b/)?([\w./\\-]+)", re.MULTILINE)

_WRITABLE_EXTENSIONS = frozenset({
    ".py", ".ts", ".tsx", ".js", ".jsx",
    ".tf", ".tfvars", ".hcl",
    ".yaml", ".yml", ".json", ".toml", ".ini", ".env.example",
    ".sh", ".bash", ".ps1",
    ".sql", ".graphql",
    ".md", ".txt", ".rst",
    ".html", ".css", ".scss",
    ".dockerfile", ".gitignore", ".gitattributes",
    "dockerfile",
})


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class FileAction(StrEnum):
    CREATE  = "create"
    REPLACE = "replace"
    PATCH   = "patch"


@dataclass
class DetectedFile:
    path: str
    content: str          # full new content (CREATE / REPLACE) or raw diff (PATCH)
    language: str
    action: FileAction = FileAction.CREATE
    diff_preview: str = field(default="", repr=False)  # unified diff shown to user


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _is_writable(path: str) -> bool:
    suffix = Path(path).suffix.lower()
    name = Path(path).name.lower()
    return suffix in _WRITABLE_EXTENSIONS or name in _WRITABLE_EXTENSIONS


def _is_diff_block(body: str) -> bool:
    return bool(_DIFF_FROM.search(body) and _DIFF_TO.search(body))


def _diff_target_path(body: str) -> str | None:
    m = _DIFF_TO.search(body)
    if m and _is_writable(m.group(1)):
        return m.group(1)
    m = _DIFF_FROM.search(body)
    if m and _is_writable(m.group(1)):
        return m.group(1)
    return None


def parse_files(response: str, project_root: Path | None = None) -> list[DetectedFile]:
    """Extract all writable file operations from an LLM response."""
    header_paths: dict[int, str] = {}
    for m in _HEADER_PATH.finditer(response):
        header_paths[m.end() - 3] = m.group(1)

    results: list[DetectedFile] = []
    seen: set[str] = set()

    for match in _CODE_BLOCK.finditer(response):
        lang        = (match.group("lang") or "").strip()
        inline_path = (match.group("inline_path") or "").strip()
        body        = match.group("body")
        start       = match.start()

        # --- Diff block? ---
        if lang == "diff" or _is_diff_block(body):
            path = _diff_target_path(body)
            if path and path not in seen:
                seen.add(path)
                results.append(DetectedFile(
                    path=path,
                    content=body,
                    language="diff",
                    action=FileAction.PATCH,
                ))
            continue

        # --- Full file block ---
        file_path: str | None = None
        if inline_path and _is_writable(inline_path):
            file_path = inline_path
        elif start in header_paths and _is_writable(header_paths[start]):
            file_path = header_paths[start]
        else:
            first_line = body.strip().split("\n")[0]
            cm = _COMMENT_PATH.match(first_line.strip())
            if cm and _is_writable(cm.group(1)):
                file_path = cm.group(1)
                body = "\n".join(body.strip().split("\n")[1:]).lstrip("\n")

        if not file_path or file_path in seen:
            continue
        seen.add(file_path)

        content = body.rstrip("\n") + "\n"
        action  = FileAction.CREATE

        # Check if file already exists → REPLACE, compute diff preview
        diff_preview = ""
        if project_root:
            dest = project_root / file_path
            if dest.exists():
                action = FileAction.REPLACE
                old_lines = dest.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
                new_lines = content.splitlines(keepends=True)
                diff_preview = "".join(difflib.unified_diff(
                    old_lines, new_lines,
                    fromfile=f"a/{file_path}",
                    tofile=f"b/{file_path}",
                    n=3,
                ))

        results.append(DetectedFile(
            path=file_path,
            content=content,
            language=lang,
            action=action,
            diff_preview=diff_preview,
        ))

    return results


# ---------------------------------------------------------------------------
# Patch application
# ---------------------------------------------------------------------------

def apply_patch(original: str, diff_text: str) -> str | None:
    """Apply a unified diff to *original* text. Returns patched text or None on failure."""
    hunk_re = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", re.MULTILINE)

    try:
        hunks = list(hunk_re.finditer(diff_text))
        if not hunks:
            return None

        result_lines = original.splitlines(keepends=True)
        diff_lines = diff_text.splitlines(keepends=True)
        offset = 0

        for hunk in hunks:
            orig_start = int(hunk.group(1)) - 1  # 0-based

            # Find where this hunk's body starts in diff_lines
            hunk_body_start = diff_text[: hunk.start()].count("\n") + 1

            # Walk the hunk line-by-line, maintaining a pointer into result_lines
            result_pos = orig_start + offset
            for line in diff_lines[hunk_body_start:]:
                if line.startswith("@@"):
                    break
                if not line:
                    result_pos += 1
                    continue
                ch = line[0]
                content = line[1:] if len(line) > 1 else "\n"
                if ch == " ":          # context — advance past it
                    result_pos += 1
                elif ch == "-":        # remove — delete from result, don't advance
                    del result_lines[result_pos]
                    offset -= 1
                elif ch == "+":        # add — insert before current position
                    result_lines.insert(result_pos, content)
                    result_pos += 1
                    offset += 1

        return "".join(result_lines)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# FileWriter
# ---------------------------------------------------------------------------

class FileWriter:
    """Offer to write / patch detected files after an LLM response."""

    def __init__(self, project_path: Path, console: Console | None = None) -> None:
        self._root = project_path
        self._console = console or Console()

    def prompt_and_write(self, response: str) -> list[str]:
        """Parse response, show table, write/patch confirmed files."""
        try:
            return self._prompt_and_write(response)
        except Exception as e:
            self._console.print(f"[yellow]Warning: file operation failed — {e}[/yellow]")
            return []

    def _prompt_and_write(self, response: str) -> list[str]:
        files = parse_files(response, project_root=self._root)
        if not files:
            return []

        # Summary table
        self._console.print()
        action_colors = {
            FileAction.CREATE:  "green",
            FileAction.REPLACE: "yellow",
            FileAction.PATCH:   "cyan",
        }
        table = Table(title="Files detected", show_header=True, header_style="bold cyan")
        table.add_column("#",      width=3, justify="right")
        table.add_column("Action", width=9)
        table.add_column("Path")
        table.add_column("Lines",  justify="right")

        for i, f in enumerate(files, 1):
            color  = action_colors[f.action]
            lines  = f.content.count("\n")
            table.add_row(
                str(i),
                f"[{color}]{f.action.value}[/{color}]",
                f.path,
                str(lines),
            )
        self._console.print(table)

        # Show diffs for REPLACE files
        for f in files:
            if f.action == FileAction.REPLACE and f.diff_preview:
                self._console.print(f"\n[bold]Changes to[/bold] [yellow]{f.path}[/yellow]:")
                self._console.print(Syntax(f.diff_preview, "diff", theme="monokai", line_numbers=False))

        choice = Prompt.ask(
            "\nApply? [bold]y[/bold]=all  [bold]n[/bold]=none  or numbers (e.g. 1,3)",
            console=self._console,
            default="y",
        ).strip().lower()

        if choice == "n":
            return []

        selected = files if choice == "y" else self._parse_selection(choice, files)
        if selected is None:
            return []

        written: list[str] = []
        for f in selected:
            dest = self._root / f.path

            if f.action == FileAction.PATCH:
                written += self._apply_patch_file(f, dest)
            else:
                # CREATE or REPLACE
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(f.content, encoding="utf-8")
                verb = "Created" if f.action == FileAction.CREATE else "Updated"
                self._console.print(f"[green]✓[/green] {verb} {f.path}")
                written.append(f.path)

                # Offer to delete any same-named file at a different location (move scenario)
                if f.action == FileAction.CREATE:
                    self._offer_delete_originals(f.path)

        if written:
            self._console.print(f"\n[green]Done — {len(written)} file(s) written.[/green]")
        return written

    # ------------------------------------------------------------------

    def _apply_patch_file(self, f: DetectedFile, dest: Path) -> list[str]:
        if not dest.exists():
            self._console.print(f"[yellow]Cannot patch {f.path} — file does not exist.[/yellow]")
            return []

        original = dest.read_text(encoding="utf-8", errors="replace")
        patched  = apply_patch(original, f.content)

        if patched is None:
            self._console.print(f"[red]Failed to apply patch to {f.path}.[/red]")
            return []

        # Show what will change
        old_lines    = original.splitlines(keepends=True)
        patched_lines = patched.splitlines(keepends=True)
        preview = "".join(difflib.unified_diff(
            old_lines, patched_lines,
            fromfile=f"a/{f.path}", tofile=f"b/{f.path}", n=3,
        ))
        if preview:
            self._console.print(Syntax(preview, "diff", theme="monokai"))

        confirm = Confirm.ask(f"Apply patch to [yellow]{f.path}[/yellow]?",
                              console=self._console, default=True)
        if not confirm:
            return []

        dest.write_text(patched, encoding="utf-8")
        self._console.print(f"[green]✓[/green] Patched {f.path}")
        return [f.path]

    def _offer_delete_originals(self, new_path: str) -> None:
        """After writing a file to a new location, find same-named files elsewhere and
        offer to delete them (handles file move scenarios)."""
        filename = Path(new_path).name
        new_abs  = (self._root / new_path).resolve()

        # Search project for files with the same name at a different path
        duplicates: list[Path] = []
        for candidate in self._root.rglob(filename):
            # Skip hidden dirs, .dev-cli, venv, etc.
            parts = candidate.parts
            if any(p.startswith(".") or p in ("node_modules", "__pycache__", "venv", ".venv")
                   for p in parts):
                continue
            if candidate.resolve() != new_abs and candidate.is_file():
                duplicates.append(candidate)

        for dup in duplicates:
            rel = str(dup.relative_to(self._root))
            delete = Confirm.ask(
                f"\n[yellow]{rel}[/yellow] may be the original — delete it?",
                console=self._console,
                default=False,
            )
            if delete:
                dup.unlink(missing_ok=True)
                self._console.print(f"[red]✗[/red] Deleted {rel}")

    def _parse_selection(
        self, choice: str, files: list[DetectedFile]
    ) -> list[DetectedFile] | None:
        try:
            indices = {int(x.strip()) - 1 for x in choice.split(",")}
            return [f for i, f in enumerate(files) if i in indices]
        except ValueError:
            self._console.print("[yellow]Invalid selection, skipping.[/yellow]")
            return None

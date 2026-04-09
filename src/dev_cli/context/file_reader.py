"""Intelligent file context reader.

Reads project files relevant to the user's question and injects them
into the LLM context. Respects per-file and total size limits.
"""
from __future__ import annotations

import re
from pathlib import Path

from dev_cli.detectors.utils import find_files, read_file_safe

# Match absolute paths in user messages: C:\Users\... or /home/...
# No spaces — avoids greedily consuming the rest of the sentence.
_ABS_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\\/][\w\\\/.-]+|\/[\w\/.-]{3,})"
)

# Limits
MAX_FILE_BYTES = 10 * 1024 * 1024   # 10 MB per file
MAX_TOTAL_BYTES = 50 * 1024 * 1024  # 50 MB total per request
MAX_FILES = 20                        # cap on number of files included

# Extensions considered "code" (readable text)
CODE_EXTENSIONS = frozenset({
    ".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs",
    ".java", ".go", ".rs", ".rb", ".php", ".cs", ".cpp", ".c", ".h",
    ".tf", ".tfvars", ".hcl",
    ".sql", ".graphql",
    ".yaml", ".yml", ".toml", ".json", ".env.example",
    ".sh", ".bash", ".zsh", ".ps1",
    ".md", ".txt", ".rst",
    ".html", ".css", ".scss",
    ".dockerfile", "dockerfile",
})

# Keywords that map to file patterns
_INTENT_PATTERNS: list[tuple[re.Pattern, list[str]]] = [
    (re.compile(r"\b(lambda\s+function|lambda\s+handler|lambda\s+code|handler\.py)\b", re.I), ["handler.py", "lambda*.py"]),
    (re.compile(r"\b(run\s+tests?|unit\s+tests?|write\s+tests?|test\s+file|test\s+suite|pytest|jest|spec\s+file)\b", re.I), ["test_*.py", "*.test.*", "*.spec.*"]),
    (re.compile(r"\bconfig\b|\bsetting\b", re.I),        ["config.*", "settings.*", "*.yaml", "*.toml"]),
    (re.compile(r"\bdocker\b|\bcontainer\b", re.I),      ["Dockerfile*", "docker-compose*"]),
    (re.compile(r"\bterraform\b|\binfra\b|\btf\b", re.I),["*.tf", "*.tfvars"]),
    (re.compile(r"\bschema\b|\bdatabase\b|\bdb\b", re.I),["schema.*", "models.*", "migration*"]),
    (re.compile(r"\b(api\s+route|api\s+endpoint|rest\s+api|router|routes)\b", re.I),["router*", "routes*", "api*", "views*"]),
    (re.compile(r"\bpackage\b|\bdependenc\b", re.I),     ["package.json", "requirements.txt", "pyproject.toml"]),
    (re.compile(r"\bci\b|\bpipeline\b|\bgithub\b", re.I),["*.yml", "*.yaml"]),
]


class FileContext:
    """Holds file contents selected for a single LLM request."""

    def __init__(self) -> None:
        self.files: dict[str, str] = {}  # relative_path -> content
        self._total_bytes = 0

    def add(self, rel_path: str, content: str) -> bool:
        """Add a file. Returns False if limits would be exceeded."""
        size = len(content.encode("utf-8"))
        if size > MAX_FILE_BYTES:
            content = content[: MAX_FILE_BYTES] + "\n... [truncated: file too large]"
            size = MAX_FILE_BYTES
        if self._total_bytes + size > MAX_TOTAL_BYTES:
            return False
        if len(self.files) >= MAX_FILES:
            return False
        self.files[rel_path] = content
        self._total_bytes += size
        return True

    def to_prompt_block(self) -> str:
        """Format all files as a prompt block for the LLM."""
        if not self.files:
            return ""
        parts = ["## Project Files\n"]
        for path, content in self.files.items():
            ext = Path(path).suffix.lstrip(".")
            parts.append(f"### `{path}`\n```{ext}\n{content}\n```\n")
        return "\n".join(parts)

    @property
    def summary(self) -> str:
        if not self.files:
            return "no files"
        return f"{len(self.files)} file(s): {', '.join(self.files.keys())}"


class FileContextReader:
    """Select and read project files relevant to the user's message."""

    def __init__(self, project_path: Path) -> None:
        self._root = project_path

    def scan_mentioned_dirs(self, user_message: str) -> str:
        """Return a directory listing for any absolute paths mentioned in the message."""
        parts: list[str] = []
        for match in _ABS_PATH_RE.finditer(user_message):
            raw = match.group().rstrip(".,!?\"'")
            p = Path(raw)
            if p.is_dir():
                try:
                    entries = sorted(p.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
                    lines = [f"  {'[dir] ' if e.is_dir() else '      '}{e.name}" for e in entries]
                    parts.append(
                        f"Contents of `{raw}` ({len(lines)} entries):\n" +
                        ("\n".join(lines) if lines else "  (empty directory)")
                    )
                except PermissionError:
                    parts.append(f"Cannot read directory: {raw} (permission denied)")
            elif p.is_file() and self._is_readable(p):
                content = read_file_safe(p, max_bytes=MAX_FILE_BYTES)
                if content.strip():
                    parts.append(f"File `{raw}`:\n```\n{content}\n```")
        return "\n\n".join(parts)

    def build(self, user_message: str, extra_paths: list[str] | None = None) -> FileContext:
        """Return a FileContext populated with files relevant to *user_message*."""
        ctx = FileContext()
        candidates: list[Path] = []

        # 1. Explicit file paths mentioned in the message (e.g. "look at auth.py")
        for match in re.finditer(r'[\w./\\-]+\.[\w]+', user_message):
            p = self._root / match.group()
            if p.exists() and p.is_file():
                candidates.insert(0, p)  # explicit mentions get priority

        # 2. Extra paths passed by caller
        for ep in (extra_paths or []):
            p = self._root / ep
            if p.exists() and p.is_file():
                candidates.append(p)

        # 3. Intent-based patterns
        for pattern, globs in _INTENT_PATTERNS:
            if pattern.search(user_message):
                for g in globs:
                    candidates.extend(find_files(self._root, g))

        # 4. Fallback: only include key root files if nothing else was found
        if not candidates:
            for name in ["main.py", "app.py", "index.ts", "index.js", "README.md"]:
                p = self._root / name
                if p.exists():
                    candidates.append(p)
                    break  # just one fallback file

        # Deduplicate preserving order
        seen: set[Path] = set()
        unique: list[Path] = []
        for p in candidates:
            rp = p.resolve()
            if rp not in seen:
                seen.add(rp)
                unique.append(p)

        # Read files into context
        for path in unique:
            if not self._is_readable(path):
                continue
            rel = self._rel(path)
            content = read_file_safe(path, max_bytes=MAX_FILE_BYTES)
            if content.strip():
                if not ctx.add(rel, content):
                    break  # total limit reached

        return ctx

    def read_explicit(self, paths: list[str]) -> FileContext:
        """Read specific files by path (relative to project root)."""
        ctx = FileContext()
        for p_str in paths:
            path = self._root / p_str
            if path.exists() and path.is_file() and self._is_readable(path):
                content = read_file_safe(path, max_bytes=MAX_FILE_BYTES)
                ctx.add(self._rel(path), content)
        return ctx

    # ------------------------------------------------------------------

    def _rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self._root))
        except ValueError:
            return str(path)

    @staticmethod
    def _is_readable(path: Path) -> bool:
        suffix = path.suffix.lower()
        name = path.name.lower()
        return suffix in CODE_EXTENSIONS or name in CODE_EXTENSIONS

from __future__ import annotations

import json
from pathlib import Path

_DEFAULT_EXCLUDE = frozenset(
    {
        ".git",
        ".dev-cli",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".env",
        "dist",
        "build",
        ".next",
        ".nuxt",
        "coverage",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "*.egg-info",
    }
)


def find_files(
    root: Path,
    pattern: str,
    exclude_dirs: frozenset[str] = _DEFAULT_EXCLUDE,
    max_depth: int = 6,
) -> list[Path]:
    """Recursively find files matching *pattern*, skipping excluded dirs."""
    results: list[Path] = []

    def _walk(path: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            for entry in path.iterdir():
                if entry.is_dir():
                    if entry.name not in exclude_dirs:
                        _walk(entry, depth + 1)
                elif entry.is_file() and entry.match(pattern):
                    results.append(entry)
        except PermissionError:
            pass

    _walk(root, 0)
    return results


def read_file_safe(path: Path, max_bytes: int = 512 * 1024) -> str:
    """Read a file, returning empty string on any error."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read(max_bytes)
    except OSError:
        return ""


def parse_json_file(path: Path) -> dict:
    """Parse a JSON file, returning empty dict on error."""
    content = read_file_safe(path)
    if not content:
        return {}
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {}


def count_files(root: Path, pattern: str) -> int:
    return len(find_files(root, pattern))

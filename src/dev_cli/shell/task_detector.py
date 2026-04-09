"""Detect developer task intents and map them to shell commands.

When the user says "run tests" or "build the project", we detect that intent,
resolve the correct command for the project type, and execute it — instead of
letting the LLM just describe how to do it.
"""
from __future__ import annotations

from pathlib import Path
import re

from dev_cli.storage.models import ProjectManifest


# ---------------------------------------------------------------------------
# Intent patterns → task name
# ---------------------------------------------------------------------------

_INTENT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(run|execute|start)\s+(the\s+)?(unit\s+)?tests?\b", re.I), "test"),
    (re.compile(r"\bpytest\b", re.I), "test"),
    (re.compile(r"\brun\s+jest\b", re.I), "test"),
    (re.compile(r"\btest\s+(this|the\s+code|it|them)\b", re.I), "test"),
    (re.compile(r"\b(build|compile)\s+(the\s+)?(app|project|code)?\b", re.I), "build"),
    (re.compile(r"\b(run|start)\s+(the\s+)?(app|server|dev\s+server)\b", re.I), "dev"),
    (re.compile(r"\b(lint|format|check\s+style)\b", re.I), "lint"),
    (re.compile(r"\binstall\s+(deps|dependencies|packages)\b", re.I), "install"),
    (re.compile(r"\b(type.?check|mypy|tsc)\b", re.I), "typecheck"),
]


# ---------------------------------------------------------------------------
# Command resolution per project type
# ---------------------------------------------------------------------------

# Each entry: { task_name: command_string }
_PYTHON_COMMANDS: dict[str, str] = {
    "test":      "python -m pytest",
    "lint":      "python -m ruff check . && python -m black --check .",
    "typecheck": "python -m mypy .",
    "install":   "pip install -e '.[dev]'",
}

_NODE_COMMANDS: dict[str, str] = {
    "test":    "npm test",
    "build":   "npm run build",
    "dev":     "npm run dev",
    "lint":    "npm run lint",
    "install": "npm install",
}

_YARN_COMMANDS: dict[str, str] = {
    "test":    "yarn test",
    "build":   "yarn build",
    "dev":     "yarn dev",
    "lint":    "yarn lint",
    "install": "yarn install",
}

_PNPM_COMMANDS: dict[str, str] = {
    "test":    "pnpm test",
    "build":   "pnpm build",
    "dev":     "pnpm dev",
    "lint":    "pnpm lint",
    "install": "pnpm install",
}


def detect_task(message: str) -> str | None:
    """Return a task name if the message is asking to run a dev task."""
    for pattern, task in _INTENT_PATTERNS:
        if pattern.search(message):
            return task
    return None


def resolve_command(task: str, project_path: Path, manifest: ProjectManifest) -> str | None:
    """Map a task name to the right shell command for this project."""
    lang_names = {lang.language.lower() for lang in manifest.languages}

    # Node: check for yarn.lock / pnpm-lock.yaml to pick the right package manager
    if "typescript" in lang_names or "node.js" in lang_names:
        if (project_path / "pnpm-lock.yaml").exists():
            return _PNPM_COMMANDS.get(task)
        if (project_path / "yarn.lock").exists():
            return _YARN_COMMANDS.get(task)
        if (project_path / "package.json").exists():
            return _NODE_COMMANDS.get(task)

    if "python" in lang_names:
        return _PYTHON_COMMANDS.get(task)

    return None

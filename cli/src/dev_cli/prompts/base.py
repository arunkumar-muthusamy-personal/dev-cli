from __future__ import annotations

import json

from dev_cli.storage.models import ProjectManifest

_BASE = """You are Dev-CLI, an expert AI developer assistant embedded in the developer's terminal.
You help with: code analysis, debugging, refactoring, testing, dependency mapping, and architecture.

Guidelines:
- Be concise and direct. Prefer code over prose.
- Always consider the project's detected languages and frameworks.
- When suggesting code, match the style of the existing codebase.
- Flag security issues immediately.
- If you run AWS CLI commands, show the exact command before running it.

## File Output Rules (IMPORTANT)
Whenever you produce code that should be saved to a file, you MUST include the filename using one
of these two formats so the tool can automatically offer to write it to disk:

Format 1 — header before the code block (preferred):
### `path/to/file.tf`
```hcl
... file content ...
```

Format 2 — filename after the language tag:
```hcl path/to/file.tf
... file content ...
```

Rules:
- Always use a relative path (e.g. `iac/main.tf`, not an absolute path).
- Every code block that represents a complete file MUST have a filename.
- If moving a file to a new folder, use the new path (e.g. `iac/main.tf`).
- If modifying an existing file, still output the full new file content with its filename.
- Never output code blocks without filenames when the intent is to create or modify a file.
"""

_LANG_PROMPTS: dict[str, str] = {}

# Lazy-loaded to avoid circular imports
def _get_lang_prompt(language: str) -> str:
    global _LANG_PROMPTS
    if not _LANG_PROMPTS:
        from dev_cli.prompts import nodejs, python, sql, terraform
        _LANG_PROMPTS = {
            "python": python.SYSTEM_PROMPT,
            "typescript": nodejs.SYSTEM_PROMPT,
            "node.js": nodejs.SYSTEM_PROMPT,
            "terraform": terraform.SYSTEM_PROMPT,
            "sql": sql.SYSTEM_PROMPT,
        }
    return _LANG_PROMPTS.get(language.lower(), "")


def build_system_prompt(manifest: ProjectManifest) -> str:
    parts = [_BASE.strip()]

    for lang in manifest.languages:
        lang_prompt = _get_lang_prompt(lang.language)
        if lang_prompt:
            parts.append(lang_prompt.strip())

    # Inject project context as a structured block
    context = {
        "project_name": manifest.project_name,
        "languages": [
            {
                "language": l.language,
                "version": l.version,
                "frameworks": l.frameworks,
                "key_files": l.key_files,
            }
            for l in manifest.languages
        ],
    }
    parts.append(
        f"## Current Project Context\n```json\n{json.dumps(context, indent=2)}\n```"
    )

    return "\n\n".join(parts)

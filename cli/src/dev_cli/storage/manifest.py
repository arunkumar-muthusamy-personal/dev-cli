from __future__ import annotations

import json
from pathlib import Path

from dev_cli.storage.models import ProjectManifest

_MANIFEST_FILENAME = "project_manifest.json"


class ManifestStore:
    """Read/write the project manifest from `.dev-cli/project_manifest.json`."""

    @staticmethod
    def manifest_path(project_path: Path) -> Path:
        return project_path / ".dev-cli" / _MANIFEST_FILENAME

    @classmethod
    def load(cls, project_path: Path) -> ProjectManifest | None:
        path = cls.manifest_path(project_path)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return ProjectManifest.model_validate(data)
        except (json.JSONDecodeError, ValueError):
            return None

    @classmethod
    def save(cls, project_path: Path, manifest: ProjectManifest) -> None:
        path = cls.manifest_path(project_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            manifest.model_dump_json(indent=2),
            encoding="utf-8",
        )

    @classmethod
    def is_stale(cls, project_path: Path, ttl_seconds: int = 3600) -> bool:
        """Return True if the manifest is missing or older than ttl_seconds."""
        path = cls.manifest_path(project_path)
        if not path.exists():
            return True
        import time
        age = time.time() - path.stat().st_mtime
        return age > ttl_seconds

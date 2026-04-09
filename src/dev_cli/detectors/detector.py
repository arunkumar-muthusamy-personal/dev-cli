from __future__ import annotations

from pathlib import Path

from src.dev_cli.detectors import terraform
from src.dev_cli.storage.models import ProjectManifest
from src.dev_cli.detectors import nodejs, python


class ProjectDetector:
    """Orchestrate all language detectors and produce a ProjectManifest."""

    def detect(self, project_path: Path) -> ProjectManifest:
        results = []

        for detector_module in (python, nodejs, terraform):
            result = detector_module.detect(project_path)
            if result is not None:
                results.append(result)

        return ProjectManifest(
            project_path=str(project_path.resolve()),
            project_name=project_path.resolve().name,
            languages=results,
        )

from __future__ import annotations

from pathlib import Path

import pytest

from dev_cli.detectors import terraform
from dev_cli.detectors.detector import ProjectDetector
from dev_cli.detectors import nodejs, python


def test_python_detector(python_project: Path) -> None:
    result = python.detect(python_project)
    assert result is not None
    assert result.language == "python"
    assert "fastapi" in result.frameworks
    assert result.file_count >= 1


def test_python_detector_empty(tmp_path: Path) -> None:
    result = python.detect(tmp_path)
    assert result is None


def test_nodejs_detector(node_project: Path) -> None:
    result = nodejs.detect(node_project)
    assert result is not None
    assert result.language in ("typescript", "node.js")
    assert "react" in result.frameworks
    assert "next.js" in result.frameworks


def test_nodejs_detector_empty(tmp_path: Path) -> None:
    result = nodejs.detect(tmp_path)
    assert result is None


def test_terraform_detector(terraform_project: Path) -> None:
    result = terraform.detect(terraform_project)
    assert result is not None
    assert result.language == "terraform"
    assert "aws" in result.frameworks
    assert result.version is not None


def test_terraform_detector_empty(tmp_path: Path) -> None:
    result = terraform.detect(tmp_path)
    assert result is None


def test_project_detector_polyglot(tmp_path: Path) -> None:
    # Create a mixed project
    (tmp_path / "main.py").write_text("import fastapi\n")
    (tmp_path / "requirements.txt").write_text("fastapi\n")
    (tmp_path / "package.json").write_text('{"dependencies": {"react": "^18.0.0"}}\n')

    manifest = ProjectDetector().detect(tmp_path)
    lang_names = manifest.language_names
    assert "python" in lang_names
    assert "node.js" in lang_names or "typescript" in lang_names


def test_project_detector_empty(tmp_path: Path) -> None:
    manifest = ProjectDetector().detect(tmp_path)
    assert manifest.languages == []
    assert manifest.project_name == tmp_path.name

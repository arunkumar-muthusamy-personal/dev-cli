from __future__ import annotations

import shutil
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sample_projects"


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Empty temporary project directory."""
    return tmp_path


@pytest.fixture
def python_project(tmp_path: Path) -> Path:
    """Temporary copy of the sample Python project."""
    src = FIXTURES_DIR / "python_project"
    dest = tmp_path / "python_project"
    shutil.copytree(src, dest)
    return dest


@pytest.fixture
def node_project(tmp_path: Path) -> Path:
    src = FIXTURES_DIR / "node_project"
    dest = tmp_path / "node_project"
    shutil.copytree(src, dest)
    return dest


@pytest.fixture
def terraform_project(tmp_path: Path) -> Path:
    src = FIXTURES_DIR / "terraform_project"
    dest = tmp_path / "terraform_project"
    shutil.copytree(src, dest)
    return dest

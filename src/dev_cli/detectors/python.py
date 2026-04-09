from __future__ import annotations

from pathlib import Path

from dev_cli.detectors.utils import find_files, parse_json_file, read_file_safe
from dev_cli.storage.models import LanguageDetection

_FRAMEWORK_MARKERS: dict[str, list[str]] = {
    "fastapi": ["fastapi"],
    "django": ["django", "djangorestframework"],
    "flask": ["flask"],
    "starlette": ["starlette"],
    "sqlalchemy": ["sqlalchemy"],
    "celery": ["celery"],
    "pydantic": ["pydantic"],
    "pytest": ["pytest"],
    "boto3": ["boto3"],
    "pyspark": ["pyspark"],
    "pandas": ["pandas"],
    "numpy": ["numpy"],
}


def _detect_frameworks(content: str) -> list[str]:
    content_lower = content.lower()
    return [fw for fw, markers in _FRAMEWORK_MARKERS.items() if any(m in content_lower for m in markers)]


def detect(root: Path) -> LanguageDetection | None:
    py_files = find_files(root, "*.py")
    if not py_files:
        return None

    frameworks: set[str] = set()
    key_files: list[str] = []

    for dep_file in ["requirements.txt", "requirements-dev.txt", "Pipfile"]:
        p = root / dep_file
        if p.exists():
            key_files.append(dep_file)
            frameworks.update(_detect_frameworks(read_file_safe(p)))

    for toml_path in find_files(root, "pyproject.toml"):
        key_files.append(str(toml_path.relative_to(root)))
        frameworks.update(_detect_frameworks(read_file_safe(toml_path)))

    for setup_file in ["setup.py", "setup.cfg"]:
        p = root / setup_file
        if p.exists():
            key_files.append(setup_file)

    # Detect version from common markers
    version: str | None = None
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        content = read_file_safe(pyproject)
        for line in content.splitlines():
            if "python_requires" in line or "requires-python" in line:
                import re
                m = re.search(r'["\']>=?(\d+\.\d+)', line)
                if m:
                    version = m.group(1)
                    break

    return LanguageDetection(
        language="python",
        version=version,
        file_count=len(py_files),
        frameworks=sorted(frameworks),
        key_files=key_files[:10],
    )

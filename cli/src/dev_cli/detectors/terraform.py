from __future__ import annotations

import re
from pathlib import Path

from dev_cli.detectors.utils import find_files, read_file_safe
from dev_cli.storage.models import LanguageDetection

_PROVIDER_PATTERNS = re.compile(
    r'source\s*=\s*"(?:hashicorp/)?(\w+)"', re.IGNORECASE
)

_KNOWN_PROVIDERS = {
    "aws", "azurerm", "google", "kubernetes", "helm",
    "datadog", "github", "random", "null", "local",
}


def detect(root: Path) -> LanguageDetection | None:
    tf_files = find_files(root, "*.tf")
    if not tf_files:
        return None

    providers: set[str] = set()
    key_files: list[str] = []

    for tf_file in tf_files:
        content = read_file_safe(tf_file)
        for m in _PROVIDER_PATTERNS.finditer(content):
            name = m.group(1).lower()
            if name in _KNOWN_PROVIDERS:
                providers.add(name)
        rel = str(tf_file.relative_to(root))
        if tf_file.name in ("main.tf", "variables.tf", "outputs.tf", "providers.tf"):
            key_files.insert(0, rel)
        elif len(key_files) < 10:
            key_files.append(rel)

    # Detect terraform version from .terraform-version or required_version
    version: str | None = None
    tv = root / ".terraform-version"
    if tv.exists():
        version = tv.read_text(encoding="utf-8").strip()
        key_files.append(".terraform-version")
    else:
        for tf_file in tf_files:
            m = re.search(r'required_version\s*=\s*"([^"]+)"', read_file_safe(tf_file))
            if m:
                version = m.group(1)
                break

    return LanguageDetection(
        language="terraform",
        version=version,
        file_count=len(tf_files),
        frameworks=sorted(providers),
        key_files=key_files[:10],
    )

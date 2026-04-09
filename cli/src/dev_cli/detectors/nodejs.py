from __future__ import annotations

from pathlib import Path

from dev_cli.detectors.utils import find_files, parse_json_file
from dev_cli.storage.models import LanguageDetection

_FRAMEWORK_DEPS: dict[str, list[str]] = {
    "react": ["react", "react-dom"],
    "next.js": ["next"],
    "vue": ["vue"],
    "angular": ["@angular/core"],
    "express": ["express"],
    "fastify": ["fastify"],
    "nestjs": ["@nestjs/core"],
    "tailwindcss": ["tailwindcss"],
    "prisma": ["prisma", "@prisma/client"],
    "typeorm": ["typeorm"],
    "jest": ["jest"],
    "vitest": ["vitest"],
    "eslint": ["eslint"],
    "webpack": ["webpack"],
    "vite": ["vite"],
    "esbuild": ["esbuild"],
}


def _detect_frameworks(pkg: dict) -> list[str]:
    all_deps: set[str] = set()
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        all_deps.update(pkg.get(key, {}).keys())

    return [fw for fw, markers in _FRAMEWORK_DEPS.items() if any(m in all_deps for m in markers)]


def detect(root: Path) -> LanguageDetection | None:
    pkg_files = find_files(root, "package.json")
    # Exclude node_modules (already excluded by find_files) but double check name
    pkg_files = [p for p in pkg_files if "node_modules" not in p.parts]

    if not pkg_files:
        return None

    ts_files = find_files(root, "*.ts") + find_files(root, "*.tsx")
    js_files = find_files(root, "*.js") + find_files(root, "*.jsx")
    is_typescript = bool(ts_files) or any(
        (root / f).exists() for f in ["tsconfig.json", "tsconfig.base.json"]
    )

    frameworks: set[str] = set()
    key_files: list[str] = []

    for pkg_path in pkg_files:
        pkg = parse_json_file(pkg_path)
        frameworks.update(_detect_frameworks(pkg))
        key_files.append(str(pkg_path.relative_to(root)))

    for config_file in ["tsconfig.json", ".eslintrc.js", ".eslintrc.json", "vite.config.ts", "next.config.js"]:
        if (root / config_file).exists():
            key_files.append(config_file)

    language = "typescript" if is_typescript else "node.js"
    file_count = len(ts_files) if is_typescript else len(js_files)

    # Node version from .nvmrc or .node-version
    version: str | None = None
    for vf in [".nvmrc", ".node-version"]:
        p = root / vf
        if p.exists():
            version = p.read_text(encoding="utf-8").strip().lstrip("v")
            key_files.append(vf)
            break

    return LanguageDetection(
        language=language,
        version=version,
        file_count=file_count,
        frameworks=sorted(frameworks),
        key_files=key_files[:10],
    )

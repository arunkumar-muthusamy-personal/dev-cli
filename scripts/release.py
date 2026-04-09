#!/usr/bin/env python3
"""Release helper — bumps version in pyproject.toml and creates a matching git tag.

Usage:
    python scripts/release.py 0.2.0
    python scripts/release.py 0.2.0 --push      # also push tag to origin
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
TOML = ROOT / "pyproject.toml"


def current_version() -> str:
    text = TOML.read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        raise SystemExit("❌ Could not find version in pyproject.toml")
    return m.group(1)


def set_version(new: str) -> None:
    text = TOML.read_text(encoding="utf-8")
    updated = re.sub(
        r'^(version\s*=\s*)"[^"]+"',
        f'\\g<1>"{new}"',
        text,
        flags=re.MULTILINE,
    )
    TOML.write_text(updated, encoding="utf-8")


def run(cmd: str) -> None:
    print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(f"❌ Command failed: {cmd}")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    push = "--push" in sys.argv

    if not args:
        print(f"Current version: {current_version()}")
        print("Usage: python scripts/release.py <new_version> [--push]")
        return

    new_version = args[0].lstrip("v")  # accept both "0.2.0" and "v0.2.0"
    tag = f"v{new_version}"
    old_version = current_version()

    print(f"\n  {old_version}  →  {new_version}")
    confirm = input("Continue? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    # 1. Update pyproject.toml
    set_version(new_version)
    print(f"✅ Updated pyproject.toml → {new_version}")

    # 2. Stage + commit
    run(f'git add pyproject.toml')
    run(f'git commit -m "chore: bump version to {new_version}"')

    # 3. Create annotated tag
    run(f'git tag -a {tag} -m "Release {tag}"')
    print(f"✅ Created tag {tag}")

    # 4. Optionally push
    if push:
        run("git push")
        run(f"git push origin {tag}")
        print(f"✅ Pushed {tag} — GitHub Actions release workflow triggered.")
    else:
        print(f"\nTo trigger the release, run:")
        print(f"  git push && git push origin {tag}")


if __name__ == "__main__":
    main()

"""Detect available AWS profiles from ~/.aws/config and ~/.aws/credentials."""
from __future__ import annotations

import configparser
import os
from pathlib import Path


def get_available_profiles() -> list[str]:
    """Return all named profiles from ~/.aws/config and ~/.aws/credentials."""
    profiles: set[str] = set()

    for config_path in [
        Path.home() / ".aws" / "config",
        Path.home() / ".aws" / "credentials",
    ]:
        if not config_path.exists():
            continue
        parser = configparser.ConfigParser()
        parser.read(config_path, encoding="utf-8")
        for section in parser.sections():
            # config uses [profile myname], credentials uses [myname]
            name = section.removeprefix("profile ").strip()
            profiles.add(name)

    return sorted(profiles)


def get_active_profile(explicit: str | None = None) -> str | None:
    """Resolve the active AWS profile using priority order:
    1. Explicit --aws-profile flag
    2. AWS_PROFILE env var
    3. AWS_DEFAULT_PROFILE env var
    4. 'default' if it exists
    5. None (let boto3/AWS CLI use its own defaults)
    """
    if explicit:
        return explicit
    for env_var in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE"):
        val = os.environ.get(env_var)
        if val:
            return val
    profiles = get_available_profiles()
    if "default" in profiles:
        return "default"
    return None

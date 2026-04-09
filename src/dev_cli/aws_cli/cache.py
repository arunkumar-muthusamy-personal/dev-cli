"""Simple in-memory cache for AWS CLI results with TTL."""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass


@dataclass
class _Entry:
    output: str
    stored_at: float


class CommandCache:
    """Cache AWS CLI command results for *ttl* seconds to avoid duplicate calls."""

    def __init__(self, ttl: int = 30) -> None:
        self._ttl = ttl
        self._store: dict[str, _Entry] = {}

    def _key(self, command: str, profile: str | None) -> str:
        raw = f"{command}|{profile or ''}"
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, command: str, profile: str | None = None) -> str | None:
        key = self._key(command, profile)
        entry = self._store.get(key)
        if entry and (time.time() - entry.stored_at) < self._ttl:
            return entry.output
        return None

    def set(self, command: str, output: str, profile: str | None = None) -> None:
        key = self._key(command, profile)
        self._store[key] = _Entry(output=output, stored_at=time.time())

    def clear(self) -> None:
        self._store.clear()

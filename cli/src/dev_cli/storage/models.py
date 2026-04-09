from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LanguageDetection(BaseModel):
    language: str
    version: str | None = None
    file_count: int = 0
    frameworks: list[str] = Field(default_factory=list)
    key_files: list[str] = Field(default_factory=list)


class ProjectManifest(BaseModel):
    project_path: str
    project_name: str
    languages: list[LanguageDetection] = Field(default_factory=list)
    scanned_at: datetime = Field(default_factory=datetime.utcnow)
    extra: dict[str, Any] = Field(default_factory=dict)

    @property
    def language_names(self) -> list[str]:
        return [lang.language for lang in self.languages]

    @property
    def all_frameworks(self) -> list[str]:
        frameworks: list[str] = []
        for lang in self.languages:
            frameworks.extend(lang.frameworks)
        return frameworks


class MessageRecord(BaseModel):
    id: str
    conversation_id: str
    role: str  # "user" | "assistant" | "system"
    content: str
    tokens: int | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ConversationRecord(BaseModel):
    id: str
    project_path: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    message_count: int = 0

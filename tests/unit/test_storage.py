from __future__ import annotations

from pathlib import Path

import pytest

from src.dev_cli.storage.conversation import ConversationDB
from src.dev_cli.storage.manifest import ManifestStore
from src.dev_cli.storage.models import LanguageDetection, ProjectManifest


@pytest.fixture
async def db(tmp_path: Path) -> ConversationDB:
    d = ConversationDB(tmp_path)
    await d.initialize()
    return d


async def test_create_conversation(db: ConversationDB, tmp_path: Path) -> None:
    conv = await db.get_or_create_conversation(str(tmp_path))
    assert conv.id
    assert conv.message_count == 0


async def test_get_or_create_idempotent(db: ConversationDB, tmp_path: Path) -> None:
    conv1 = await db.get_or_create_conversation(str(tmp_path))
    conv2 = await db.get_or_create_conversation(str(tmp_path))
    assert conv1.id == conv2.id


async def test_add_and_retrieve_messages(db: ConversationDB, tmp_path: Path) -> None:
    conv = await db.get_or_create_conversation(str(tmp_path))
    await db.add_message(conv.id, "user", "Hello")
    await db.add_message(conv.id, "assistant", "Hi there!")

    messages = await db.get_recent_messages(conv.id, limit=10)
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[1].role == "assistant"
    assert messages[1].content == "Hi there!"


async def test_history_limit(db: ConversationDB, tmp_path: Path) -> None:
    conv = await db.get_or_create_conversation(str(tmp_path))
    for i in range(10):
        await db.add_message(conv.id, "user", f"msg {i}")

    messages = await db.get_recent_messages(conv.id, limit=5)
    assert len(messages) == 5
    # Should return the LAST 5 in chronological order
    assert messages[-1].content == "msg 9"


async def test_clear_conversation(db: ConversationDB, tmp_path: Path) -> None:
    conv = await db.get_or_create_conversation(str(tmp_path))
    await db.add_message(conv.id, "user", "test")
    deleted = await db.clear_conversation(conv.id)
    assert deleted == 1
    messages = await db.get_recent_messages(conv.id)
    assert messages == []


def test_manifest_round_trip(tmp_path: Path) -> None:
    manifest = ProjectManifest(
        project_path=str(tmp_path),
        project_name="test",
        languages=[
            LanguageDetection(
                language="python",
                version="3.11",
                frameworks=["fastapi"],
                key_files=["requirements.txt"],
            )
        ],
    )
    ManifestStore.save(tmp_path, manifest)
    loaded = ManifestStore.load(tmp_path)
    assert loaded is not None
    assert loaded.project_name == "test"
    assert loaded.languages[0].language == "python"
    assert loaded.languages[0].frameworks == ["fastapi"]


def test_manifest_stale_when_missing(tmp_path: Path) -> None:
    assert ManifestStore.is_stale(tmp_path) is True

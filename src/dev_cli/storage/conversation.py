from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from dev_cli.storage.models import ConversationRecord, MessageRecord
from dev_cli.storage.schema import ALL_SCHEMAS

_TS_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"


def _now() -> str:
    return datetime.now(timezone.utc).strftime(_TS_FORMAT)


def _parse_ts(s: str) -> datetime:
    try:
        return datetime.strptime(s, _TS_FORMAT)
    except ValueError:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")


class ConversationDB:
    """Async SQLite-backed conversation store.

    Database lives at ``{project_path}/.dev-cli/conversation.db``.
    """

    def __init__(self, project_path: Path) -> None:
        self._db_path = project_path / ".dev-cli" / "conversation.db"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Create tables if they don't exist."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA foreign_keys=ON;")
            for statement in ALL_SCHEMAS:
                await db.execute(statement)
            await db.commit()

    # ------------------------------------------------------------------
    # Conversations
    # ------------------------------------------------------------------

    async def get_or_create_conversation(self, project_path: str) -> ConversationRecord:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys=ON;")

            row = await (
                await db.execute(
                    "SELECT * FROM conversations WHERE project_path = ?",
                    (project_path,),
                )
            ).fetchone()

            if row:
                count_row = await (
                    await db.execute(
                        "SELECT COUNT(*) AS cnt FROM messages WHERE conversation_id = ?",
                        (row["id"],),
                    )
                ).fetchone()
                return ConversationRecord(
                    id=row["id"],
                    project_path=row["project_path"],
                    created_at=_parse_ts(row["created_at"]),
                    updated_at=_parse_ts(row["updated_at"]),
                    message_count=count_row["cnt"] if count_row else 0,
                )

            conv_id = str(uuid.uuid4())
            now = _now()
            await db.execute(
                "INSERT INTO conversations(id, project_path, created_at, updated_at) VALUES (?,?,?,?)",
                (conv_id, project_path, now, now),
            )
            await db.commit()
            return ConversationRecord(
                id=conv_id,
                project_path=project_path,
                created_at=_parse_ts(now),
                updated_at=_parse_ts(now),
                message_count=0,
            )

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tokens: int | None = None,
    ) -> MessageRecord:
        msg_id = str(uuid.uuid4())
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("PRAGMA foreign_keys=ON;")
            await db.execute(
                "INSERT INTO messages(id, conversation_id, role, content, tokens, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (msg_id, conversation_id, role, content, tokens, now),
            )
            await db.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )
            await db.commit()
        return MessageRecord(
            id=msg_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            tokens=tokens,
            created_at=_parse_ts(now),
        )

    async def get_recent_messages(
        self, conversation_id: str, limit: int = 50
    ) -> list[MessageRecord]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (
                await db.execute(
                    """
                    SELECT * FROM (
                        SELECT * FROM messages
                        WHERE conversation_id = ?
                        ORDER BY created_at DESC
                        LIMIT ?
                    ) ORDER BY created_at ASC
                    """,
                    (conversation_id, limit),
                )
            ).fetchall()
        return [
            MessageRecord(
                id=r["id"],
                conversation_id=r["conversation_id"],
                role=r["role"],
                content=r["content"],
                tokens=r["tokens"],
                created_at=_parse_ts(r["created_at"]),
            )
            for r in rows
        ]

    async def clear_conversation(self, conversation_id: str) -> int:
        """Delete all messages in a conversation. Returns number of deleted rows."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("PRAGMA foreign_keys=ON;")
            cursor = await db.execute(
                "DELETE FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            )
            await db.commit()
            return cursor.rowcount

    async def get_message_count(self, conversation_id: str) -> int:
        async with aiosqlite.connect(self._db_path) as db:
            row = await (
                await db.execute(
                    "SELECT COUNT(*) AS cnt FROM messages WHERE conversation_id = ?",
                    (conversation_id,),
                )
            ).fetchone()
            return row[0] if row else 0

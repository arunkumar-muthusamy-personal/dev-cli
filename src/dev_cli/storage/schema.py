"""SQLite schema definitions — plain SQL, no ORM dependency."""

CREATE_CONVERSATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    project_path TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""

CREATE_MESSAGES_TABLE = """
CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content         TEXT NOT NULL,
    tokens          INTEGER,
    created_at      TEXT NOT NULL
);
"""

CREATE_MESSAGES_INDEX = """
CREATE INDEX IF NOT EXISTS idx_messages_conv_created
ON messages(conversation_id, created_at);
"""

ALL_SCHEMAS = [
    CREATE_CONVERSATIONS_TABLE,
    CREATE_MESSAGES_TABLE,
    CREATE_MESSAGES_INDEX,
]

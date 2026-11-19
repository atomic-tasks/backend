from sqlalchemy import Column, ForeignKey, Index, String, Table, Uuid

from atomic_tasks.infrastructure.postgres.tables.base import TIMESTAMPTZ, metadata

browser_sessions = Table(
    "browser_sessions",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("user_id", Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("created_at", TIMESTAMPTZ, nullable=False),
    Column("last_seen_at", TIMESTAMPTZ, nullable=False),
    Column("expires_at", TIMESTAMPTZ, nullable=False),
    Index("ix_browser_sessions_user_id", "user_id"),
)

# Вход до callback: пользователя ещё нет, поэтому и связи с users нет.
login_attempts = Table(
    "login_attempts",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("state_hash", String(64), nullable=False, unique=True),
    Column("code_verifier", String(128), nullable=False),
    Column("nonce", String(128), nullable=False),
    Column("return_to", String(2048), nullable=False),
    Column("expires_at", TIMESTAMPTZ, nullable=False),
)

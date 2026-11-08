from sqlalchemy import Column, ForeignKey, Index, String, Table, Uuid

from atomic_tasks.domain.entities.api_token import TokenScope
from atomic_tasks.infrastructure.postgres.tables.base import TIMESTAMPTZ, StrEnumType, metadata

api_tokens = Table(
    "api_tokens",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("user_id", Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("name", String(100), nullable=False),
    Column("prefix", String(8), nullable=False),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("scope", StrEnumType(TokenScope, 16), nullable=False),
    Column("created_at", TIMESTAMPTZ, nullable=False),
    Column("expires_at", TIMESTAMPTZ, nullable=True),
    Column("last_used_at", TIMESTAMPTZ, nullable=True),
    Column("revoked_at", TIMESTAMPTZ, nullable=True),
    Index("ix_api_tokens_user_id_revoked_at", "user_id", "revoked_at"),
)

from sqlalchemy import Column, ForeignKey, Index, String, Table, UniqueConstraint, Uuid

from atomic_tasks.infrastructure.postgres.tables.base import TIMESTAMPTZ, metadata

users = Table(
    "users",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("display_name", String(200), nullable=False),
    Column("email", String(320), nullable=True),
    Column("created_at", TIMESTAMPTZ, nullable=False),
    Column("updated_at", TIMESTAMPTZ, nullable=False),
    Column("disabled_at", TIMESTAMPTZ, nullable=True),
)

user_identities = Table(
    "user_identities",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("user_id", Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("issuer", String(500), nullable=False),
    Column("subject", String(255), nullable=False),
    Column("created_at", TIMESTAMPTZ, nullable=False),
    Column("last_login_at", TIMESTAMPTZ, nullable=True),
    UniqueConstraint("issuer", "subject", name="uq_user_identities_issuer_subject"),
    Index("ix_user_identities_user_id", "user_id"),
)

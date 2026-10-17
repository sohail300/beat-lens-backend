"""Initial schema: songs and fingerprints.

Databases created before migrations existed (by the app's old create_all on startup)
already have these tables; they are left untouched so `alembic upgrade head` works on them too.

Revision ID: 0001
Revises:
Create Date: 2026-10-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())

    if "songs" not in existing:
        op.create_table(
            "songs",
            sa.Column("id", sa.BigInteger(), primary_key=True),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("artist", sa.String(), nullable=False),
            sa.Column("ytID", sa.String(), nullable=True),
            sa.Column("key", sa.String(), nullable=False, unique=True),
        )

    if "fingerprints" not in existing:
        op.create_table(
            "fingerprints",
            sa.Column("address", sa.BigInteger(), primary_key=True),
            sa.Column("anchorTimeMs", sa.BigInteger(), primary_key=True),
            sa.Column("songID", sa.BigInteger(), primary_key=True),
        )


def downgrade() -> None:
    op.drop_table("fingerprints")
    op.drop_table("songs")

"""Track each song's fingerprint algorithm version; index fingerprints by song.

Existing songs are marked as version 1 (the original algorithm). Re-index them with
`python -m app.cli reindex --outdated`, or delete and re-add them.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("songs")}
    if "algorithm_version" not in columns:
        op.add_column(
            "songs",
            sa.Column("algorithm_version", sa.Integer(), nullable=False, server_default="1"),
        )

    # Speeds up deleting / re-indexing one song's fingerprints
    op.create_index("ix_fingerprints_songID", "fingerprints", ["songID"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("ix_fingerprints_songID", table_name="fingerprints", if_exists=True)
    with op.batch_alter_table("songs") as batch:
        batch.drop_column("algorithm_version")

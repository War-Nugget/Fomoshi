"""synced games

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-30 22:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "synced_games",
        sa.Column("event_ticker", sa.String(length=100), nullable=False),
        sa.Column("series_ticker", sa.String(length=100), nullable=False),
        sa.Column("league", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("team_a_ticker", sa.String(length=100), nullable=False),
        sa.Column("team_b_ticker", sa.String(length=100), nullable=False),
        sa.Column("tie_ticker", sa.String(length=100), nullable=False),
        sa.Column("volume_24h", sa.BigInteger(), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_ticker"),
    )
    with op.batch_alter_table("synced_games", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_synced_games_league"), ["league"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_synced_games_start_time"), ["start_time"], unique=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("synced_games", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_synced_games_start_time"))
        batch_op.drop_index(batch_op.f("ix_synced_games_league"))
    op.drop_table("synced_games")

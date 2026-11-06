"""Stable ordering for status events sharing the same timestamp."""

import sqlalchemy as sa

from alembic import op

revision = "0003_history_order"
down_revision = "0002_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "application_history", sa.Column("position", sa.BigInteger(), sa.Identity(), nullable=False)
    )
    op.create_unique_constraint("uq_history_position", "application_history", ["position"])


def downgrade() -> None:
    op.drop_constraint("uq_history_position", "application_history", type_="unique")
    op.drop_column("application_history", "position")

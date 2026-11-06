"""Remove duplicate uniqueness enforcement; unique indexes remain in place."""

from alembic import op

revision = "0004_remove_redundant_uniques"
down_revision = "0003_history_order"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table, column in [
        ("users", "email"),
        ("skills", "normalized_name"),
        ("refresh_tokens", "token_hash"),
    ]:
        op.drop_constraint(f"{table}_{column}_key", table, type_="unique")


def downgrade() -> None:
    for table, column in [
        ("users", "email"),
        ("skills", "normalized_name"),
        ("refresh_tokens", "token_hash"),
    ]:
        op.create_unique_constraint(f"{table}_{column}_key", table, [column])

"""Enforce tenant consistency and complete salary constraints."""

import sqlalchemy as sa

from alembic import op

revision = "0002_integrity"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_unique_constraint("uq_company_id_owner", "companies", ["id", "user_id"])
    op.create_unique_constraint("uq_vacancy_id_owner", "vacancies", ["id", "user_id"])
    op.create_foreign_key(
        "fk_vacancy_company_owner",
        "vacancies",
        "companies",
        ["company_id", "user_id"],
        ["id", "user_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_application_vacancy_owner",
        "applications",
        "vacancies",
        ["vacancy_id", "user_id"],
        ["id", "user_id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_salary_max_nonnegative", "vacancies", "salary_max IS NULL OR salary_max >= 0"
    )
    op.create_check_constraint(
        "ck_salary_currency",
        "vacancies",
        "(salary_min IS NULL AND salary_max IS NULL) OR currency IS NOT NULL",
    )
    op.create_index("ix_applications_applied_at", "applications", ["user_id", "applied_at"])
    op.create_index("ix_vacancies_deadline", "vacancies", ["user_id", "application_deadline"])


def downgrade() -> None:
    op.drop_index("ix_vacancies_deadline", table_name="vacancies")
    op.drop_index("ix_applications_applied_at", table_name="applications")
    op.drop_constraint("ck_salary_currency", "vacancies")
    op.drop_constraint("ck_salary_max_nonnegative", "vacancies")
    op.drop_constraint("fk_application_vacancy_owner", "applications", type_="foreignkey")
    op.drop_constraint("fk_vacancy_company_owner", "vacancies", type_="foreignkey")
    op.drop_constraint("uq_vacancy_id_owner", "vacancies", type_="unique")
    op.drop_constraint("uq_company_id_owner", "companies", type_="unique")
    op.drop_column("users", "updated_at")

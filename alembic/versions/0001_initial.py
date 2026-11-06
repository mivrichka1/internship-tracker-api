"""Initial schema."""

import sqlalchemy as sa

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)
    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("website_url", sa.String(2048)),
        sa.Column("industry", sa.String(120)),
        sa.Column("location", sa.String(160)),
        sa.Column("description", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_company_user_name"),
    )
    op.create_index("ix_companies_user_id", "companies", ["user_id"])
    op.create_table(
        "skills",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("normalized_name", sa.String(80), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_name"),
    )
    op.create_index("ix_skills_normalized_name", "skills", ["normalized_name"], unique=True)
    op.create_table(
        "vacancies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("vacancy_url", sa.String(2048)),
        sa.Column("location", sa.String(160)),
        sa.Column(
            "employment_type",
            sa.Enum("internship", "full_time", "part_time", "contract", name="employment_type"),
            nullable=False,
        ),
        sa.Column(
            "work_format", sa.Enum("remote", "hybrid", "office", name="work_format"), nullable=False
        ),
        sa.Column("salary_min", sa.Integer()),
        sa.Column("salary_max", sa.Integer()),
        sa.Column("currency", sa.String(3)),
        sa.Column("experience_level", sa.String(60)),
        sa.Column("application_deadline", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("salary_min IS NULL OR salary_min >= 0"),
        sa.CheckConstraint("salary_max IS NULL OR salary_min IS NULL OR salary_max >= salary_min"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vacancies_user_id", "vacancies", ["user_id"])
    op.create_index("ix_vacancies_company_id", "vacancies", ["company_id"])
    op.create_index("ix_vacancies_title", "vacancies", ["title"])
    op.create_index("ix_vacancies_work_format", "vacancies", ["work_format"])
    op.create_table(
        "vacancy_skills",
        sa.Column("vacancy_id", sa.Uuid(), nullable=False),
        sa.Column("skill_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vacancy_id"], ["vacancies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("vacancy_id", "skill_id"),
    )
    op.create_table(
        "applications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("vacancy_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "saved",
                "applied",
                "screening",
                "assessment",
                "interview",
                "offer",
                "rejected",
                "withdrawn",
                name="application_status",
            ),
            nullable=False,
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.Column("next_action_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vacancy_id"], ["vacancies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "vacancy_id", name="uq_application_user_vacancy"),
    )
    op.create_index("ix_applications_user_id", "applications", ["user_id"])
    op.create_index("ix_applications_vacancy_id", "applications", ["vacancy_id"])
    op.create_index("ix_applications_status", "applications", ["status"])
    op.create_table(
        "application_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column(
            "old_status",
            sa.Enum(
                "saved",
                "applied",
                "screening",
                "assessment",
                "interview",
                "offer",
                "rejected",
                "withdrawn",
                name="history_status",
            ),
        ),
        sa.Column(
            "new_status",
            sa.Enum(
                "saved",
                "applied",
                "screening",
                "assessment",
                "interview",
                "offer",
                "rejected",
                "withdrawn",
                name="history_new_status",
            ),
            nullable=False,
        ),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_application_history_application_id", "application_history", ["application_id"]
    )


def downgrade() -> None:
    op.drop_table("application_history")
    op.drop_table("applications")
    op.drop_table("vacancy_skills")
    op.drop_table("vacancies")
    op.drop_table("skills")
    op.drop_table("companies")
    op.drop_table("refresh_tokens")
    op.drop_table("users")

    for name in (
        "history_new_status",
        "history_status",
        "application_status",
        "work_format",
        "employment_type",
    ):
        sa.Enum(name=name).drop(op.get_bind(), checkfirst=True)

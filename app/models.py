import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now_utc() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(cascade="all, delete-orphan")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_company_user_name"),
        UniqueConstraint("id", "user_id", name="uq_company_id_owner"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    website_url: Mapped[str | None] = mapped_column(String(2048))
    industry: Mapped[str | None] = mapped_column(String(120))
    location: Mapped[str | None] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    vacancies: Mapped[list["Vacancy"]] = relationship(
        back_populates="company", foreign_keys="Vacancy.company_id", passive_deletes=True
    )


class WorkFormat(str, enum.Enum):
    remote = "remote"
    hybrid = "hybrid"
    office = "office"


class EmploymentType(str, enum.Enum):
    internship = "internship"
    full_time = "full_time"
    part_time = "part_time"
    contract = "contract"


class Status(str, enum.Enum):
    saved = "saved"
    applied = "applied"
    screening = "screening"
    assessment = "assessment"
    interview = "interview"
    offer = "offer"
    rejected = "rejected"
    withdrawn = "withdrawn"


vacancy_skills = Table(
    "vacancy_skills",
    Base.metadata,
    Column("vacancy_id", Uuid, ForeignKey("vacancies.id", ondelete="CASCADE"), primary_key=True),
    Column("skill_id", Uuid, ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True),
)


class Vacancy(Base):
    __tablename__ = "vacancies"
    __table_args__ = (
        Index("ix_vacancies_deadline", "user_id", "application_deadline"),
        UniqueConstraint("id", "user_id", name="uq_vacancy_id_owner"),
        ForeignKeyConstraint(
            ["company_id", "user_id"],
            ["companies.id", "companies.user_id"],
            ondelete="CASCADE",
            name="fk_vacancy_company_owner",
        ),
        CheckConstraint("salary_max IS NULL OR salary_max >= 0", name="ck_salary_max_nonnegative"),
        CheckConstraint(
            "(salary_min IS NULL AND salary_max IS NULL) OR currency IS NOT NULL",
            name="ck_salary_currency",
        ),
        CheckConstraint("salary_min IS NULL OR salary_min >= 0"),
        CheckConstraint("salary_max IS NULL OR salary_min IS NULL OR salary_max >= salary_min"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    vacancy_url: Mapped[str | None] = mapped_column(String(2048))
    location: Mapped[str | None] = mapped_column(String(160))
    employment_type: Mapped[EmploymentType] = mapped_column(
        Enum(EmploymentType, name="employment_type"), default=EmploymentType.internship
    )
    work_format: Mapped[WorkFormat] = mapped_column(
        Enum(WorkFormat, name="work_format"), default=WorkFormat.remote, index=True
    )
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str | None] = mapped_column(String(3))
    experience_level: Mapped[str | None] = mapped_column(String(60))
    application_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    company: Mapped[Company] = relationship(back_populates="vacancies", foreign_keys=[company_id])
    skills: Mapped[list["Skill"]] = relationship(
        secondary=vacancy_skills, back_populates="vacancies"
    )
    application: Mapped["Application | None"] = relationship(
        back_populates="vacancy",
        cascade="all, delete-orphan",
        uselist=False,
        foreign_keys="Application.vacancy_id",
        passive_deletes=True,
    )


class Skill(Base):
    __tablename__ = "skills"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80))
    normalized_name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    vacancies: Mapped[list[Vacancy]] = relationship(
        secondary=vacancy_skills, back_populates="skills"
    )


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        Index("ix_applications_applied_at", "user_id", "applied_at"),
        UniqueConstraint("user_id", "vacancy_id", name="uq_application_user_vacancy"),
        ForeignKeyConstraint(
            ["vacancy_id", "user_id"],
            ["vacancies.id", "vacancies.user_id"],
            ondelete="CASCADE",
            name="fk_application_vacancy_owner",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    vacancy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vacancies.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[Status] = mapped_column(
        Enum(Status, name="application_status"), default=Status.saved, index=True
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    vacancy: Mapped[Vacancy] = relationship(back_populates="application", foreign_keys=[vacancy_id])
    history: Mapped[list["ApplicationHistory"]] = relationship(
        cascade="all, delete-orphan",
        order_by="ApplicationHistory.changed_at, ApplicationHistory.position",
        passive_deletes=True,
    )


class ApplicationHistory(Base):
    __tablename__ = "application_history"
    position: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    old_status: Mapped[Status | None] = mapped_column(
        Enum(Status, name="history_status"), nullable=True
    )
    new_status: Mapped[Status] = mapped_column(Enum(Status, name="history_new_status"))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    comment: Mapped[str | None] = mapped_column(Text)

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    model_validator,
)

from app.models import EmploymentType, Status, WorkFormat

Name = Annotated[str, Field(min_length=1, max_length=160)]
Salary = Annotated[int, Field(ge=0)]


def validate_skill_name(value: str) -> str:
    name = value.strip()
    if not name or len(name.casefold()) > 80:
        raise ValueError("Normalized skill name must contain 1 to 80 characters")
    return name


SkillName = Annotated[str, Field(min_length=1, max_length=80), AfterValidator(validate_skill_name)]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, str_strip_whitespace=True)


class UserCreate(Schema):
    email: EmailStr
    password: Annotated[str, Field(min_length=10, max_length=128)]
    full_name: Annotated[str, Field(min_length=1, max_length=120)]

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class UserOut(Schema):
    id: UUID
    email: EmailStr
    full_name: str
    created_at: datetime
    updated_at: datetime


class Tokens(Schema):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshIn(Schema):
    refresh_token: Annotated[str, Field(min_length=1, max_length=4096)]


class CompanyIn(Schema):
    name: Name
    website_url: HttpUrl | None = None
    industry: Annotated[str, Field(max_length=120)] | None = None
    location: Annotated[str, Field(max_length=160)] | None = None
    description: Annotated[str, Field(max_length=20000)] | None = None


class Patch(Schema):
    @model_validator(mode="after")
    def reject_required_nulls(self):
        for name in self.model_fields_set:
            if name in self.required_nonnull() and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self

    def required_nonnull(self) -> set[str]:
        return set()


class CompanyPatch(Patch):
    name: Name | None = None
    website_url: HttpUrl | None = None
    industry: Annotated[str, Field(max_length=120)] | None = None
    location: Annotated[str, Field(max_length=160)] | None = None
    description: Annotated[str, Field(max_length=20000)] | None = None

    def required_nonnull(self) -> set[str]:
        return {"name"}


class CompanyOut(CompanyIn):
    id: UUID
    created_at: datetime


class VacancyFields(Schema):
    description: Annotated[str, Field(max_length=50000)] | None = None
    vacancy_url: HttpUrl | None = None
    location: Annotated[str, Field(max_length=160)] | None = None
    salary_min: Salary | None = None
    salary_max: Salary | None = None
    currency: Currency | None = None
    experience_level: Annotated[str, Field(max_length=60)] | None = None
    application_deadline: AwareDatetime | None = None

    @model_validator(mode="after")
    def salary_order(self):
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_max < self.salary_min
        ):
            raise ValueError("salary_max must be greater than or equal to salary_min")
        if (self.salary_min is not None or self.salary_max is not None) and self.currency is None:
            raise ValueError("currency is required for salary values")
        return self


class VacancyIn(VacancyFields):
    company_id: UUID
    title: Annotated[str, Field(min_length=1, max_length=200)]
    employment_type: EmploymentType = EmploymentType.internship
    work_format: WorkFormat = WorkFormat.remote
    skills: list[SkillName] = Field(default_factory=list, max_length=100)


class VacancyPatch(Patch):
    company_id: UUID | None = None
    title: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    description: Annotated[str, Field(max_length=50000)] | None = None
    vacancy_url: HttpUrl | None = None
    location: Annotated[str, Field(max_length=160)] | None = None
    employment_type: EmploymentType | None = None
    work_format: WorkFormat | None = None
    salary_min: Salary | None = None
    salary_max: Salary | None = None
    currency: Currency | None = None
    experience_level: Annotated[str, Field(max_length=60)] | None = None
    application_deadline: AwareDatetime | None = None
    skills: list[SkillName] | None = Field(default=None, max_length=100)

    def required_nonnull(self) -> set[str]:
        return {"company_id", "title", "employment_type", "work_format", "skills"}


class CompanyBrief(Schema):
    id: UUID
    name: str


class VacancyOut(VacancyFields):
    id: UUID
    company_id: UUID
    title: str
    employment_type: EmploymentType
    work_format: WorkFormat
    skills: list[str]
    company: CompanyBrief
    created_at: datetime
    updated_at: datetime


class ApplicationIn(Schema):
    vacancy_id: UUID
    status: Status = Status.saved
    applied_at: AwareDatetime | None = None
    next_action_at: AwareDatetime | None = None
    notes: Annotated[str, Field(max_length=20000)] | None = None

    @model_validator(mode="after")
    def sent_date(self):
        if self.status == Status.saved and self.applied_at is not None:
            raise ValueError("saved application cannot have applied_at")
        return self


class ApplicationPatch(Schema):
    next_action_at: AwareDatetime | None = None
    notes: Annotated[str, Field(max_length=20000)] | None = None


class StatusIn(Schema):
    status: Status
    comment: Annotated[str, Field(max_length=2000)] | None = None
    reopen: bool = False


class ApplicationOut(Schema):
    id: UUID
    vacancy_id: UUID
    status: Status
    applied_at: datetime | None
    next_action_at: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class HistoryOut(Schema):
    position: int
    id: UUID
    application_id: UUID
    old_status: Status | None
    new_status: Status
    changed_at: datetime
    comment: str | None


class SkillIn(Schema):
    name: SkillName


class SkillOut(Schema):
    id: UUID
    name: str
    normalized_name: str


class Pagination(Schema):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    direction: Literal["asc", "desc"] = "desc"


class CompanyFilter(Pagination):
    search: str | None = None
    location: str | None = None
    industry: str | None = None
    sort: Literal["name", "created_at"] = "created_at"


class VacancyFilter(Pagination):
    search: str | None = None
    company: str | None = None
    company_id: UUID | None = None
    skill: str | None = None
    work_format: WorkFormat | None = None
    salary_min: Salary | None = None
    salary_max: Salary | None = None
    currency: Currency | None = None
    application_deadline_before: AwareDatetime | None = None
    application_deadline_after: AwareDatetime | None = None
    status: Status | None = None
    status_filter: Status | None = None
    sort: Literal["created_at", "title", "salary_min", "application_deadline"] = "created_at"


class ApplicationFilter(Pagination):
    status: Status | None = None
    status_filter: Status | None = None
    vacancy_id: UUID | None = None
    search: str | None = None
    sort: Literal["created_at", "applied_at", "next_action_at"] = "created_at"


class Page[T](Schema):
    items: list[T]
    total: int
    page: int
    page_size: int


class OverviewOut(Schema):
    total_vacancies: int
    total_applications: int
    active_applications: int
    rejected: int
    offers: int
    response_rate: float
    offer_rate: float
    average_response_hours: float | None


class FunnelOut(Schema):
    stage: Status
    count: int
    conversion_from_applied: float
    conversion_from_previous: float
    progressed_from_previous: int


class SkillCount(Schema):
    skill: str
    vacancy_count: int


class TimelineOut(Schema):
    period: datetime
    count: int

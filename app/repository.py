"""Database queries. Every private query is scoped by owner before execution."""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Application, ApplicationHistory, Company, RefreshToken, Skill, User, Vacancy
from app.schemas import ApplicationFilter, CompanyFilter, Pagination, VacancyFilter


class Repository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def health(self) -> None:
        await self.db.execute(select(1))

    async def user_by_email(self, email: str) -> User | None:
        return await self.db.scalar(select(User).where(User.email == email.lower()))

    async def user(self, uid: UUID) -> User | None:
        return await self.db.get(User, uid)

    async def refresh(self, hashed: str, uid: UUID) -> RefreshToken | None:
        return await self.db.scalar(
            select(RefreshToken)
            .where(RefreshToken.token_hash == hashed, RefreshToken.user_id == uid)
            .with_for_update()
        )

    async def owned(self, model: Any, uid: UUID, oid: UUID, *, lock: bool = False) -> Any:
        q = select(model).where(model.id == oid, model.user_id == uid)
        if model is Vacancy:
            q = q.options(selectinload(Vacancy.company), selectinload(Vacancy.skills))
        if lock:
            q = q.with_for_update()
        return await self.db.scalar(q.execution_options(populate_existing=True))

    async def page(self, q: Any, model: Any, filters: Pagination) -> dict[str, Any]:
        total = await self.db.scalar(select(func.count()).select_from(q.order_by(None).subquery()))
        field = getattr(model, filters.sort)  # type: ignore[attr-defined]
        order = field.asc() if filters.direction == "asc" else field.desc()
        rows = (
            (
                await self.db.scalars(
                    q.order_by(order.nulls_last(), model.id)
                    .offset((filters.page - 1) * filters.page_size)
                    .limit(filters.page_size)
                )
            )
            .unique()
            .all()
        )
        return {
            "items": list(rows),
            "total": total or 0,
            "page": filters.page,
            "page_size": filters.page_size,
        }

    async def companies(self, uid: UUID, f: CompanyFilter) -> dict[str, Any]:
        q = select(Company).where(Company.user_id == uid)
        if f.search:
            q = q.where(Company.name.icontains(f.search, autoescape=True))
        if f.location:
            q = q.where(Company.location.icontains(f.location, autoescape=True))
        if f.industry:
            q = q.where(Company.industry.icontains(f.industry, autoescape=True))
        return await self.page(q, Company, f)

    async def vacancies(self, uid: UUID, f: VacancyFilter) -> dict[str, Any]:
        q = (
            select(Vacancy)
            .where(Vacancy.user_id == uid)
            .options(selectinload(Vacancy.company), selectinload(Vacancy.skills))
        )
        if f.search:
            q = q.where(Vacancy.title.icontains(f.search, autoescape=True))
        if f.company:
            q = q.where(Vacancy.company.has(Company.name.icontains(f.company, autoescape=True)))
        if f.company_id:
            q = q.where(Vacancy.company_id == f.company_id)
        if f.skill:
            q = q.where(Vacancy.skills.any(Skill.normalized_name == f.skill.strip().casefold()))
        if f.work_format:
            q = q.where(Vacancy.work_format == f.work_format)
        if f.salary_min is not None:
            q = q.where(func.coalesce(Vacancy.salary_max, Vacancy.salary_min) >= f.salary_min)
        if f.salary_max is not None:
            q = q.where(func.coalesce(Vacancy.salary_min, Vacancy.salary_max) <= f.salary_max)
        if f.currency:
            q = q.where(Vacancy.currency == f.currency)
        if f.application_deadline_before:
            q = q.where(Vacancy.application_deadline <= f.application_deadline_before)
        if f.application_deadline_after:
            q = q.where(Vacancy.application_deadline >= f.application_deadline_after)
        state = f.status or f.status_filter
        if state:
            q = q.where(Vacancy.application.has(Application.status == state))
        return await self.page(q, Vacancy, f)

    async def applications(self, uid: UUID, f: ApplicationFilter) -> dict[str, Any]:
        q = select(Application).where(Application.user_id == uid)
        if f.status or f.status_filter:
            q = q.where(Application.status == (f.status or f.status_filter))
        if f.vacancy_id:
            q = q.where(Application.vacancy_id == f.vacancy_id)
        if f.search:
            q = q.where(Application.vacancy.has(Vacancy.title.icontains(f.search, autoescape=True)))
        return await self.page(q, Application, f)

    async def history(self, aid: UUID) -> list[ApplicationHistory]:
        return list(
            (
                await self.db.scalars(
                    select(ApplicationHistory)
                    .where(ApplicationHistory.application_id == aid)
                    .order_by(ApplicationHistory.changed_at, ApplicationHistory.position)
                )
            ).all()
        )

    async def skills(self, names: list[str]) -> list[Skill]:
        normalized = {name.strip().casefold(): name.strip() for name in names}
        for key in sorted(normalized):
            await self.db.execute(
                pg_insert(Skill)
                .values(name=normalized[key], normalized_name=key)
                .on_conflict_do_nothing(index_elements=["normalized_name"])
            )
        return list(
            (
                await self.db.scalars(
                    select(Skill)
                    .where(Skill.normalized_name.in_(normalized))
                    .order_by(Skill.normalized_name)
                )
            ).all()
        )

    async def list_skills(self, uid: UUID, search: str | None, limit: int) -> list[Skill]:
        # The shared catalogue is returned only through the user's tagged vacancies.
        q = select(Skill).join(Skill.vacancies).where(Vacancy.user_id == uid).distinct()
        if search:
            q = q.where(Skill.normalized_name.icontains(search.casefold(), autoescape=True))
        return list((await self.db.scalars(q.order_by(Skill.normalized_name).limit(limit))).all())

    async def analytics(self, uid: UUID) -> tuple[int, list[Any], list[Any]]:
        vacancies = int(
            await self.db.scalar(select(func.count(Vacancy.id)).where(Vacancy.user_id == uid)) or 0
        )
        apps = list(
            (
                await self.db.execute(
                    select(Application.id, Application.status, Application.applied_at).where(
                        Application.user_id == uid
                    )
                )
            ).all()
        )
        events = list(
            (
                await self.db.execute(
                    select(
                        ApplicationHistory.application_id,
                        ApplicationHistory.new_status,
                        func.min(ApplicationHistory.changed_at),
                        func.max(ApplicationHistory.changed_at),
                    )
                    .join(Application, Application.id == ApplicationHistory.application_id)
                    .where(Application.user_id == uid)
                    .group_by(ApplicationHistory.application_id, ApplicationHistory.new_status)
                )
            ).all()
        )
        return vacancies, apps, events

    async def skill_counts(self, uid: UUID, limit: int) -> list[dict[str, Any]]:
        count = func.count(func.distinct(Vacancy.id))
        rows = (
            await self.db.execute(
                select(Skill.name, count)
                .join(Skill.vacancies)
                .where(Vacancy.user_id == uid)
                .group_by(Skill.id, Skill.name)
                .order_by(count.desc(), Skill.name)
                .limit(limit)
            )
        ).all()
        return [{"skill": name, "vacancy_count": n} for name, n in rows]

    async def timeline(self, uid: UUID, granularity: str) -> list[dict[str, Any]]:
        period = func.date_trunc(granularity, Application.applied_at)
        rows = (
            await self.db.execute(
                select(period, func.count(Application.id))
                .where(Application.user_id == uid, Application.applied_at.is_not(None))
                .group_by(period)
                .order_by(period)
            )
        ).all()
        return [{"period": p, "count": n} for p, n in rows]

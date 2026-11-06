"""Business rules and transaction boundaries, independent of HTTP handlers."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from pydantic import HttpUrl, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.core.errors import DomainError
from app.core.security import DUMMY_HASH, decode_token, digest, passwords, token_pair
from app.models import Application, ApplicationHistory, Company, RefreshToken, Status, User, Vacancy
from app.repository import Repository
from app.schemas import (
    ApplicationIn,
    ApplicationPatch,
    CompanyIn,
    CompanyPatch,
    StatusIn,
    UserCreate,
    VacancyFilter,
    VacancyIn,
    VacancyPatch,
)

TERMINAL = {Status.offer, Status.rejected, Status.withdrawn}
RESPONSES = {Status.screening, Status.assessment, Status.interview, Status.offer, Status.rejected}
STAGES = [Status.applied, Status.screening, Status.assessment, Status.interview, Status.offer]


def values(body: Any, **kwargs: Any) -> dict[str, Any]:
    return {
        k: str(v) if isinstance(v, HttpUrl) else v for k, v in body.model_dump(**kwargs).items()
    }


def vacancy_out(obj: Vacancy) -> dict[str, Any]:
    return {
        **{c.key: getattr(obj, c.key) for c in obj.__table__.columns if c.key != "user_id"},
        "company": {"id": obj.company.id, "name": obj.company.name},
        "skills": [s.name for s in obj.skills],
    }


class Service:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = Repository(db)

    async def commit(self) -> None:
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise DomainError(
                409,
                "RESOURCE_CONFLICT",
                "Resource conflicts with existing data or database constraints",
            ) from None

    async def owned(self, model: Any, uid: UUID, oid: UUID, lock: bool = False) -> Any:
        obj = await self.repo.owned(model, uid, oid, lock=lock)
        if obj is None:
            code = model.__name__.upper() + "_NOT_FOUND"
            raise DomainError(404, code, f"{model.__name__} was not found")
        return obj

    async def register(self, body: UserCreate) -> User:
        hashed = await run_in_threadpool(passwords.hash, body.password)
        obj = User(
            email=body.email.lower(), hashed_password=hashed, full_name=body.full_name.strip()
        )
        if not obj.full_name:
            raise DomainError(422, "VALIDATION_ERROR", "full_name cannot be blank")
        self.db.add(obj)
        await self.commit()
        await self.db.refresh(obj)
        return obj

    def persist_refresh(self, uid: UUID, pair: dict[str, str]) -> None:
        self.db.add(
            RefreshToken(
                user_id=uid,
                token_hash=digest(pair["refresh_token"]),
                expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
            )
        )

    async def login(self, email: str, password: str) -> dict[str, str]:
        user = await self.repo.user_by_email(email)
        valid = await run_in_threadpool(
            passwords.verify, password, user.hashed_password if user else DUMMY_HASH
        )
        if not user or not valid:
            raise DomainError(401, "INVALID_CREDENTIALS", "Incorrect email or password")
        pair = token_pair(user.id)
        self.persist_refresh(user.id, pair)
        await self.commit()
        return pair

    async def refresh(self, token: str) -> dict[str, str]:
        uid = decode_token(token, "refresh")
        row = await self.repo.refresh(digest(token), uid)
        if row is None or row.revoked or row.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC):
            raise DomainError(401, "INVALID_TOKEN", "Refresh token revoked or expired")
        row.revoked = True
        pair = token_pair(uid)
        self.persist_refresh(uid, pair)
        await self.commit()
        return pair

    async def logout(self, token: str, uid: UUID) -> None:
        row = await self.repo.refresh(digest(token), uid)
        if row is not None:
            row.revoked = True
            await self.commit()

    async def company_create(self, uid: UUID, body: CompanyIn) -> Company:
        obj = Company(user_id=uid, **values(body))
        self.db.add(obj)
        await self.commit()
        await self.db.refresh(obj)
        return obj

    async def company_patch(self, uid: UUID, oid: UUID, body: CompanyPatch) -> Company:
        obj = await self.owned(Company, uid, oid, True)
        for k, v in values(body, exclude_unset=True).items():
            setattr(obj, k, v)
        await self.commit()
        await self.db.refresh(obj)
        return obj

    async def delete(self, model: Any, uid: UUID, oid: UUID) -> None:
        obj = await self.owned(model, uid, oid, True)
        await self.db.delete(obj)
        await self.commit()

    async def vacancy_create(self, uid: UUID, body: VacancyIn) -> dict[str, Any]:
        await self.owned(Company, uid, body.company_id)
        obj = Vacancy(
            user_id=uid,
            **values(body, exclude={"skills"}),
            skills=await self.repo.skills(body.skills),
        )
        self.db.add(obj)
        await self.commit()
        return vacancy_out(await self.owned(Vacancy, uid, obj.id))

    async def vacancy_patch(self, uid: UUID, oid: UUID, body: VacancyPatch) -> dict[str, Any]:
        obj = await self.owned(Vacancy, uid, oid, True)
        changes = values(body, exclude_unset=True)
        merged = {k: getattr(obj, k) for k in VacancyIn.model_fields if k != "skills"}
        merged["skills"] = [s.name for s in obj.skills]
        try:
            checked = VacancyIn.model_validate({**merged, **changes})
        except ValidationError:
            raise DomainError(
                422,
                "INVALID_VACANCY",
                "Updated vacancy has an invalid salary range, currency, or field",
            ) from None
        if "company_id" in changes:
            await self.owned(Company, uid, checked.company_id)
        for k, v in values(checked, exclude={"skills"}).items():
            setattr(obj, k, v)
        if "skills" in changes:
            obj.skills = await self.repo.skills(checked.skills)
        await self.commit()
        return vacancy_out(await self.owned(Vacancy, uid, oid))

    async def vacancies(self, uid: UUID, f: VacancyFilter) -> dict[str, Any]:
        if (
            f.salary_min is not None or f.salary_max is not None or f.sort == "salary_min"
        ) and not f.currency:
            raise DomainError(
                400, "CURRENCY_REQUIRED", "currency is required for salary filtering or sorting"
            )
        if f.salary_min is not None and f.salary_max is not None and f.salary_max < f.salary_min:
            raise DomainError(422, "INVALID_SALARY_RANGE", "salary_max must be at least salary_min")
        if (
            f.application_deadline_before
            and f.application_deadline_after
            and f.application_deadline_before < f.application_deadline_after
        ):
            raise DomainError(422, "INVALID_DEADLINE_RANGE", "Deadline range is reversed")
        page = await self.repo.vacancies(uid, f)
        page["items"] = [vacancy_out(v) for v in page["items"]]
        return page

    def event(
        self,
        app: Application,
        old: Status | None,
        new: Status,
        at: datetime,
        comment: str | None = None,
    ) -> None:
        self.db.add(
            ApplicationHistory(
                application_id=app.id,
                old_status=old,
                new_status=new,
                changed_at=at,
                comment=comment,
            )
        )

    async def application_create(self, uid: UUID, body: ApplicationIn) -> Application:
        await self.owned(Vacancy, uid, body.vacancy_id)
        now = datetime.now(UTC)
        sent = body.status not in {Status.saved, Status.withdrawn}
        at = body.applied_at or (now if sent else None)
        if at and at > now:
            raise DomainError(422, "FUTURE_APPLICATION_DATE", "applied_at cannot be in the future")
        obj = Application(
            id=uuid4(), user_id=uid, **values(body, exclude={"applied_at"}), applied_at=at
        )
        self.db.add(obj)
        if at:
            self.event(obj, None, Status.applied, at)
        if body.status != Status.applied:
            self.event(obj, Status.applied if at else None, body.status, now)
        await self.commit()
        await self.db.refresh(obj)
        return obj

    async def application_patch(self, uid: UUID, oid: UUID, body: ApplicationPatch) -> Application:
        obj = await self.owned(Application, uid, oid, True)
        for k, v in values(body, exclude_unset=True).items():
            setattr(obj, k, v)
        await self.commit()
        await self.db.refresh(obj)
        return obj

    async def status(self, uid: UUID, oid: UUID, body: StatusIn) -> Application:
        obj = await self.owned(Application, uid, oid, True)
        if obj.status == body.status:
            return obj
        if obj.status in TERMINAL:
            if (
                not body.reopen
                or body.status in TERMINAL
                or body.status == Status.saved
                or not (body.comment or "").strip()
            ):
                raise DomainError(
                    409,
                    "REOPEN_REQUIRED",
                    "Reopening requires reopen=true, a comment, and a nonterminal sent status",
                )
        if body.status == Status.saved and obj.applied_at is not None:
            raise DomainError(409, "ALREADY_SENT", "A sent application cannot return to saved")
        now = datetime.now(UTC)
        previous = obj.status
        if obj.applied_at is None and body.status not in {Status.saved, Status.withdrawn}:
            obj.applied_at = now
            if body.status != Status.applied:
                self.event(obj, previous, Status.applied, now, "Submission recorded")
                previous = Status.applied
        self.event(obj, previous, body.status, now, body.comment)
        obj.status = body.status
        await self.commit()
        await self.db.refresh(obj)
        return obj

    async def history(self, uid: UUID, oid: UUID) -> list[ApplicationHistory]:
        await self.owned(Application, uid, oid)
        return await self.repo.history(oid)

    async def overview(self, uid: UUID) -> dict[str, Any]:
        vacancies, apps, events = await self.repo.analytics(uid)
        sent = {a.id: a.applied_at for a in apps if a.applied_at is not None}
        first_response: dict[UUID, datetime] = {}
        for aid, stage, first, _last in events:
            if aid in sent and stage in RESPONSES and first >= sent[aid]:
                first_response[aid] = min(first, first_response.get(aid, first))
        times = [(at - sent[aid]).total_seconds() / 3600 for aid, at in first_response.items()]
        offers = sum(a.status == Status.offer for a in apps if a.id in sent)
        return {
            "total_vacancies": vacancies,
            "total_applications": len(sent),
            "active_applications": sum(a.status not in TERMINAL for a in apps if a.id in sent),
            "rejected": sum(a.status == Status.rejected for a in apps if a.id in sent),
            "offers": offers,
            "response_rate": len(first_response) / len(sent) if sent else 0,
            "offer_rate": offers / len(sent) if sent else 0,
            "average_response_hours": sum(times) / len(times) if times else None,
        }

    async def funnel(self, uid: UUID) -> list[dict[str, Any]]:
        _, apps, events = await self.repo.analytics(uid)
        sent = {a.id: a.applied_at for a in apps if a.applied_at is not None}
        reached: dict[Status, dict[UUID, tuple[datetime, datetime]]] = {s: {} for s in STAGES}
        reached[Status.applied] = {aid: (at, at) for aid, at in sent.items()}
        for aid, stage, first, last in events:
            if stage in reached and aid in sent and stage != Status.applied:
                reached[stage][aid] = (first, last)
        result = []
        for i, stage in enumerate(STAGES):
            current = reached[stage]
            previous = reached[STAGES[i - 1]] if i else reached[Status.applied]
            progressed = sum(
                aid in previous and previous[aid][0] <= times[1] for aid, times in current.items()
            )
            result.append(
                {
                    "stage": stage,
                    "count": len(current),
                    "progressed_from_previous": progressed,
                    "conversion_from_applied": len(current) / len(sent) if sent else 0,
                    "conversion_from_previous": progressed / len(previous) if previous else 0,
                }
            )
        return result

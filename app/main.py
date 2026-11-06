"""HTTP boundary: validated DTOs, authentication, and service orchestration."""

import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException

from app.core.errors import DomainError
from app.core.security import decode_token
from app.db import engine, get_db
from app.models import Application, Company, User, Vacancy
from app.schemas import (
    ApplicationFilter,
    ApplicationIn,
    ApplicationOut,
    ApplicationPatch,
    CompanyFilter,
    CompanyIn,
    CompanyOut,
    CompanyPatch,
    FunnelOut,
    HistoryOut,
    OverviewOut,
    Page,
    RefreshIn,
    SkillCount,
    SkillOut,
    StatusIn,
    TimelineOut,
    Tokens,
    UserCreate,
    UserOut,
    VacancyFilter,
    VacancyIn,
    VacancyOut,
    VacancyPatch,
)
from app.services import Service, vacancy_out

logger = logging.getLogger("tracker")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await engine.dispose()


app = FastAPI(
    title="Internship Tracker API",
    version="1.0.0",
    lifespan=lifespan,
    description="Private internship tracking, hiring history, and analytics. All timestamps use UTC.",
)
router = APIRouter(prefix="/api/v1")
oauth = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def error(status: int, code: str, message: str, details: Any = None) -> JSONResponse:
    content: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details is not None:
        content["error"]["details"] = details
    return JSONResponse(
        status_code=status,
        content=content,
        headers={"WWW-Authenticate": "Bearer"} if status == 401 else None,
    )


@app.exception_handler(DomainError)
async def domain_error(_: Request, exc: DomainError) -> JSONResponse:
    return error(exc.status, exc.code, exc.message)


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
    return error(exc.status_code, f"HTTP_{exc.status_code}", str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Never echo input values: validation failures may contain passwords or tokens.
    details = [
        {"field": ".".join(str(x) for x in e["loc"]), "message": e["msg"]} for e in exc.errors()
    ]
    return error(422, "VALIDATION_ERROR", "Request validation failed", details)


@app.exception_handler(IntegrityError)
async def integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
    return error(409, "RESOURCE_CONFLICT", "Resource conflicts with database constraints")


@app.exception_handler(SQLAlchemyError)
async def database_error(_: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.error(json.dumps({"event": "database_error", "type": type(exc).__name__}))
    return error(503, "DATABASE_UNAVAILABLE", "Database operation could not be completed")


@app.exception_handler(Exception)
async def unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    logger.error(json.dumps({"event": "internal_error", "type": type(exc).__name__}))
    return error(500, "INTERNAL_ERROR", "Unexpected server error")


@app.middleware("http")
async def request_log(request: Request, call_next):
    started = time.monotonic()
    rid = uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    logger.info(
        json.dumps(
            {
                "event": "request",
                "request_id": rid,
                "method": request.method,
                "route": getattr(request.scope.get("route"), "path", "unmatched"),
                "status": response.status_code,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
            }
        )
    )
    return response


async def service(db: AsyncSession = Depends(get_db)) -> Service:
    return Service(db)


async def current_user(token: str | None = Depends(oauth), svc: Service = Depends(service)) -> User:
    if token is None:
        raise DomainError(401, "AUTHENTICATION_REQUIRED", "Bearer token is required")
    uid = decode_token(token, "access")
    user = await svc.repo.user(uid)
    if user is None:
        raise DomainError(401, "INVALID_TOKEN", "User does not exist")
    return user


Svc = Annotated[Service, Depends(service)]
Current = Annotated[User, Depends(current_user)]


@app.get("/health", tags=["Health"])
async def health(svc: Svc) -> dict[str, str]:
    await svc.repo.health()
    return {"status": "ok"}


@router.post("/auth/register", response_model=UserOut, status_code=201, tags=["Authentication"])
async def register(body: UserCreate, svc: Svc):
    return await svc.register(body)


@router.post("/auth/login", response_model=Tokens, tags=["Authentication"])
async def login(svc: Svc, form: Annotated[OAuth2PasswordRequestForm, Depends()]):
    return await svc.login(form.username, form.password)


@router.post("/auth/refresh", response_model=Tokens, tags=["Authentication"])
async def refresh(body: RefreshIn, svc: Svc):
    return await svc.refresh(body.refresh_token)


@router.post("/auth/logout", status_code=204, tags=["Authentication"])
async def logout(body: RefreshIn, user: Current, svc: Svc) -> None:
    await svc.logout(body.refresh_token, user.id)


@router.get("/users/me", response_model=UserOut, tags=["Users"])
async def me(user: Current):
    return user


@router.post("/companies", response_model=CompanyOut, status_code=201, tags=["Companies"])
async def create_company(body: CompanyIn, user: Current, svc: Svc):
    return await svc.company_create(user.id, body)


@router.get("/companies", response_model=Page[CompanyOut], tags=["Companies"])
async def list_companies(user: Current, svc: Svc, filters: Annotated[CompanyFilter, Query()]):
    return await svc.repo.companies(user.id, filters)


@router.get("/companies/{item_id}", response_model=CompanyOut, tags=["Companies"])
async def get_company(item_id: UUID, user: Current, svc: Svc):
    return await svc.owned(Company, user.id, item_id)


@router.patch("/companies/{item_id}", response_model=CompanyOut, tags=["Companies"])
async def patch_company(item_id: UUID, body: CompanyPatch, user: Current, svc: Svc):
    return await svc.company_patch(user.id, item_id, body)


@router.delete("/companies/{item_id}", status_code=204, tags=["Companies"])
async def delete_company(item_id: UUID, user: Current, svc: Svc) -> None:
    await svc.delete(Company, user.id, item_id)


@router.post("/vacancies", response_model=VacancyOut, status_code=201, tags=["Vacancies"])
async def create_vacancy(body: VacancyIn, user: Current, svc: Svc):
    return await svc.vacancy_create(user.id, body)


@router.get("/vacancies", response_model=Page[VacancyOut], tags=["Vacancies"])
async def list_vacancies(user: Current, svc: Svc, filters: Annotated[VacancyFilter, Query()]):
    return await svc.vacancies(user.id, filters)


@router.get("/vacancies/{item_id}", response_model=VacancyOut, tags=["Vacancies"])
async def get_vacancy(item_id: UUID, user: Current, svc: Svc):
    return vacancy_out(await svc.owned(Vacancy, user.id, item_id))


@router.patch("/vacancies/{item_id}", response_model=VacancyOut, tags=["Vacancies"])
async def patch_vacancy(item_id: UUID, body: VacancyPatch, user: Current, svc: Svc):
    return await svc.vacancy_patch(user.id, item_id, body)


@router.delete("/vacancies/{item_id}", status_code=204, tags=["Vacancies"])
async def delete_vacancy(item_id: UUID, user: Current, svc: Svc) -> None:
    await svc.delete(Vacancy, user.id, item_id)


@router.get("/skills", response_model=list[SkillOut], tags=["Skills"])
async def list_skills(
    user: Current, svc: Svc, search: str | None = None, limit: int = Query(100, ge=1, le=100)
):
    return await svc.repo.list_skills(user.id, search, limit)


@router.post("/applications", response_model=ApplicationOut, status_code=201, tags=["Applications"])
async def create_application(body: ApplicationIn, user: Current, svc: Svc):
    return await svc.application_create(user.id, body)


@router.get("/applications", response_model=Page[ApplicationOut], tags=["Applications"])
async def list_applications(
    user: Current, svc: Svc, filters: Annotated[ApplicationFilter, Query()]
):
    return await svc.repo.applications(user.id, filters)


@router.get("/applications/{item_id}", response_model=ApplicationOut, tags=["Applications"])
async def get_application(item_id: UUID, user: Current, svc: Svc):
    return await svc.owned(Application, user.id, item_id)


@router.patch("/applications/{item_id}", response_model=ApplicationOut, tags=["Applications"])
async def patch_application(item_id: UUID, body: ApplicationPatch, user: Current, svc: Svc):
    return await svc.application_patch(user.id, item_id, body)


@router.patch(
    "/applications/{item_id}/status", response_model=ApplicationOut, tags=["Applications"]
)
async def change_status(item_id: UUID, body: StatusIn, user: Current, svc: Svc):
    return await svc.status(user.id, item_id, body)


@router.get(
    "/applications/{item_id}/history", response_model=list[HistoryOut], tags=["Applications"]
)
async def application_history(item_id: UUID, user: Current, svc: Svc):
    return await svc.history(user.id, item_id)


@router.delete("/applications/{item_id}", status_code=204, tags=["Applications"])
async def delete_application(item_id: UUID, user: Current, svc: Svc) -> None:
    await svc.delete(Application, user.id, item_id)


@router.get("/analytics/overview", response_model=OverviewOut, tags=["Analytics"])
async def overview(user: Current, svc: Svc):
    return await svc.overview(user.id)


@router.get("/analytics/funnel", response_model=list[FunnelOut], tags=["Analytics"])
async def funnel(user: Current, svc: Svc):
    return await svc.funnel(user.id)


@router.get("/analytics/skills", response_model=list[SkillCount], tags=["Analytics"])
async def skills_analytics(user: Current, svc: Svc, limit: int = Query(20, ge=1, le=100)):
    return await svc.repo.skill_counts(user.id, limit)


@router.get("/analytics/timeline", response_model=list[TimelineOut], tags=["Analytics"])
async def timeline(user: Current, svc: Svc, granularity: Literal["day", "week", "month"] = "week"):
    return await svc.repo.timeline(user.id, granularity)


app.include_router(router)

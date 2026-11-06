import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import get_db
from app.main import app
from app.models import Base


@pytest.fixture
async def db_sessions():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        raise RuntimeError(
            "Set TEST_DATABASE_URL to a dedicated migrated PostgreSQL database ending in _test"
        )
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or not (parsed.database or "").endswith("_test"):
        raise RuntimeError("Tests require a PostgreSQL database whose name ends in _test")
    engine = create_async_engine(url, connect_args={"server_settings": {"timezone": "UTC"}})
    async with engine.begin() as conn:
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        await conn.execute(text(f"TRUNCATE {tables} CASCADE"))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest.fixture
async def client(db_sessions):
    async def test_db():
        async with db_sessions() as session:
            try:
                yield session
            except BaseException:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = test_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
        ) as c:
            yield c
    finally:
        app.dependency_overrides.clear()

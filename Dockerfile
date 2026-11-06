FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .
COPY alembic ./alembic
COPY alembic.ini ./

FROM base AS test
RUN pip install --no-cache-dir '.[dev]'
COPY tests ./tests
CMD ["sh", "-c", "alembic upgrade head && pytest --cov=app --cov-report=term-missing"]

FROM base AS runtime
RUN useradd --system --uid 10001 tracker
USER tracker
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log"]

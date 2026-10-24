# syntax=docker/dockerfile:1

# ---- 前端构建 ---------------------------------------------------------------
FROM node:22-alpine AS frontend

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- 运行时 -----------------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    IATP_DATA_DIR=/app/data \
    IATP_ARTIFACT_DIR=/app/artifacts

WORKDIR /app

RUN groupadd --system iatp && useradd --system --gid iatp --home /app iatp

COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --upgrade pip && python -m pip install .

COPY domain ./domain
COPY cases ./cases
COPY agents ./agents
COPY suites ./suites
COPY --from=frontend /build/frontend/dist ./frontend/dist

RUN mkdir -p /app/data /app/artifacts && chown -R iatp:iatp /app

USER iatp
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).read()"

CMD ["python", "-m", "uvicorn", "ia_platform.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

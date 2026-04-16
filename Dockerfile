# mcp-fda — FDA Drug Interaction Checker

FROM python:3.11-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libpq-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY schema/ ./schema/
COPY scripts/ ./scripts/

RUN pip install --no-cache-dir setuptools wheel && \
    pip install --no-cache-dir .

# ── Development stage ──────────────────────────────────────────────────────────
FROM base AS development

RUN pip install --no-cache-dir \
    pytest \
    pytest-asyncio \
    pytest-cov \
    black \
    ruff && \
    pip install --no-cache-dir -e .

RUN mkdir -p /app/logs /app/data

ENV PYTHONPATH="/app/src"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

CMD ["python", "src/main.py", "--http"]

# ── Production stage ───────────────────────────────────────────────────────────
FROM base AS production

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir -e . && \
    useradd --create-home --shell /bin/bash mcpuser && \
    mkdir -p /app/logs /app/data && \
    chown -R mcpuser:mcpuser /app

USER mcpuser

ENV PYTHONPATH="/app/src"
ENV PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["python", "src/main.py", "--http"]

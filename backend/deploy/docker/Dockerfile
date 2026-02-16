FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

COPY constraints/ constraints/
COPY requirements.txt ./

RUN python -m pip install --upgrade "pip<26" \
    && python -m pip install -r requirements.txt -c constraints/py312.txt

COPY apps/ apps/
COPY apiSystem/ apiSystem/
COPY scripts/ scripts/
COPY pytest.ini pyproject.toml mypy.ini .pre-commit-config.yaml .secrets.baseline Makefile ./

RUN useradd -m -u 10001 appuser \
    && chown -R appuser:appuser /app/backend

USER appuser

EXPOSE 8002

ENV PORT=8002 \
    DJANGO_DEBUG=0 \
    PYTHONPATH=apiSystem:.

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/api/v1/health" || exit 1

CMD ["sh", "-c", "cd apiSystem && daphne -b 0.0.0.0 -p ${PORT} apiSystem.asgi:application"]


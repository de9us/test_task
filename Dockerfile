FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY migrations/ ./migrations/
COPY alembic.ini ./
RUN pip install --no-cache-dir . && useradd --create-home appuser
USER appuser

CMD ["uvicorn", "payment_service.api:app", "--host", "0.0.0.0", "--port", "8000"]

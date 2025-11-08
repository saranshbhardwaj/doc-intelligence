# backend/Dockerfile
# Multi-stage build for FastAPI + Celery

FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Create non-root user
RUN addgroup --system app && adduser --system --ingroup app appuser

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Ensure Python can always import project packages when running CLI tools like Alembic
ENV PYTHONPATH=/app
ENV SHARED_UPLOAD_ROOT=/shared_uploads

# Install Python deps separately to leverage layer cache
COPY requirements.txt ./requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy application (exclude via .dockerignore)
COPY . .

# Adjust ownership for writable directories (logs, temp files)
RUN mkdir -p /shared_uploads /app/logs && chown -R appuser:app /shared_uploads /app/logs /app

# Default envs (override via compose / Railway)
ENV USE_CELERY=${USE_CELERY} \
    CELERY_BROKER_URL=${CELERY_BROKER_URL} \
    CELERY_RESULT_BACKEND=${CELERY_RESULT_BACKEND}

# Switch to non-root user
USER appuser

# Expose FastAPI port
EXPOSE 8000

# Health command (optional)
HEALTHCHECK --interval=120s --timeout=5s CMD curl -f http://localhost:8000/api/health || exit 1

# Run uvicorn by default
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

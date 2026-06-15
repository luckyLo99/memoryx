FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir -e . \
    && pip install --no-cache-dir "uvicorn[standard]"

COPY . .

RUN mkdir -p /app/db /app/logs /app/cache /app/data

# Security: MEMORYX_API_KEY must be set in production.
# For local development, a random key is auto-generated at startup.
# For production, TLS termination must happen at a reverse proxy (nginx/Caddy).
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD curl -f http://localhost:8080/live || exit 1

CMD ["uvicorn", "memoryx.api.rest_app:app", "--host", "0.0.0.0", "--port", "8080"]

# ---- Build stage (dependency install) ----
FROM python:3.11-slim AS deps

WORKDIR /app

# Install system dependencies for building
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- Runtime stage ----
FROM python:3.11-slim AS runtime

# Install tzdata for timezone support
RUN apt-get update && \
    apt-get install -y --no-install-recommends tzdata && \
    rm -rf /var/lib/apt/lists/*

ENV TZ=UTC

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

# Copy installed packages from deps stage
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Copy application code
COPY app/ ./app/
COPY alembic.ini .
COPY alembic/ ./alembic/
COPY entrypoint.sh .

# Create required directories
RUN mkdir -p /data /config /tmp && \
    chown -R appuser:appuser /data /config /tmp /app && \
    chmod +x entrypoint.sh

# Expose port
EXPOSE 8000

# Health check has been moved to docker-stack.yml / docker-compose.yml

ENTRYPOINT ["./entrypoint.sh"]

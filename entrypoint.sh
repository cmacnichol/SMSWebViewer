#!/bin/bash
set -e

echo "=== SMS Web Viewer ==="
echo "Initializing database..."

# Initialize database tables
python -c "
import asyncio
from app.core.database import init_db
asyncio.run(init_db())
print('Database initialized successfully.')
"

echo "Starting server on ${APP_HOST:-0.0.0.0}:${APP_PORT:-8000}..."

# Start uvicorn
exec uvicorn app.main:app \
    --host "${APP_HOST:-0.0.0.0}" \
    --port "${APP_PORT:-8000}" \
    --log-level info

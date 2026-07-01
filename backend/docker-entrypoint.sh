#!/bin/sh
set -e

if [ "${SKIP_MIGRATIONS:-0}" != "1" ]; then
  echo "Running alembic upgrade head..."
  alembic upgrade head
fi

exec uvicorn main:app --host 0.0.0.0 --port 7788

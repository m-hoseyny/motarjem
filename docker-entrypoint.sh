#!/bin/bash

# Wait for PostgreSQL to be ready

# Run database migrations
echo "Running database migrations..."
alembic upgrade head

# Start the application with uvicorn
echo "Starting application with uvicorn..."
uvicorn app:app --host 0.0.0.0 --port 8000 --reload;
exec "$@"

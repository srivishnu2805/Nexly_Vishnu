#!/usr/bin/env bash
# Exit on error
set -o errexit

# Start the Celery worker in the background
echo "Starting Celery worker..."
celery -A myproject worker -l info &

# Start the Web server (Gunicorn)
echo "Starting Gunicorn..."
gunicorn myproject.wsgi:application

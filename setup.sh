#!/bin/sh
# Точка входа контейнера: проверка зависимостей, миграции, запуск команды.
set -e

echo "Checking Tesseract OCR installation..."

tesseract --version | head -1
tesseract --list-langs 2>/dev/null | head -20 || true

echo "Applying database migrations..."

python /app/scripts/ensure_db_schema.py

echo "Starting application..."

exec "$@"
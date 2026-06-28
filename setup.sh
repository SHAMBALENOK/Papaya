#!/bin/sh
set -e

echo "Checking Tesseract OCR installation..."

tesseract --version | head -1
tesseract --list-langs

echo "Starting application..."

exec "$@"
# Стек технологий

[← Документация](README.md) · [К README проекта](../README.md) · [English](en/tech-stack.md)

- **Backend:** Python 3.11, FastAPI, Uvicorn, Gunicorn, Pydantic, PyJWT, bcrypt,
  Werkzeug.
- **База данных:** PostgreSQL 16, SQLAlchemy 2 (async), asyncpg, Alembic.
- **Импорт РСОШ:** pdfplumber, pypdfium2, pytesseract (Tesseract `rus` / `eng` /
  `osd`), OpenCV, openpyxl, NumPy.
- **Кэш и фоновые задачи:** Redis 7, Celery 5.
- **Frontend:** HTML, CSS, Vanilla JS SPA, Tailwind CSS (CDN).
- **Тестирование:** pytest, pytest-asyncio, httpx, asgi-lifespan.
- **Контейнеризация:** Docker, Docker Compose, Render (`render.yaml`).

См. также: [архитектура](architecture.md) · [запуск и настройка](getting-started.md).

# Technology stack

[← Documentation](README.md) · [Project README](../../English.md) · [Русская версия](../tech-stack.md)

- **Backend:** Python 3.11, FastAPI, Gunicorn, Uvicorn, Pydantic, PyJWT, bcrypt,
  Werkzeug
- **Frontend:** HTML, CSS, Vanilla JS SPA, Tailwind CSS
- **Database:** PostgreSQL 16, SQLAlchemy (async ORM), asyncpg, Alembic
- **Authentication:** JWT cookies, bcrypt, Pydantic validation
- **Caching and background jobs:** Redis 7, Celery
- **RSOSH import:** pdfplumber, pypdfium2, pytesseract (Tesseract `rus` / `eng` /
  `osd`), OpenCV, openpyxl, NumPy
- **Testing:** pytest, pytest-asyncio, httpx, asgi-lifespan
- **Containerization:** Docker, Docker Compose, Render (`render.yaml`)

See also: [architecture](architecture.md) · [getting started](getting-started.md).

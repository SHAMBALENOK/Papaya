# Getting started

[← Documentation](README.md) · [Project README](../../English.md) · [Русская версия](../getting-started.md)

## Prerequisites

- **Git**;
- **Docker Desktop** or Docker Engine;
- **Docker Compose v2** (the `docker compose` command);
- an internet connection for the first image build and dependency downloads.

You do not need to install Python, PostgreSQL, Redis or Tesseract separately; they
run inside Docker containers.

## Quick start

```bash
git clone https://github.com/SHAMBALENOK/Papaya.git
cd Papaya
cp .env.example .env
# replace JWT_KEY in .env with your own random secret:
python -c "import secrets; print(secrets.token_hex(32))"
docker compose up -d --build
```

> The application refuses to start with the placeholder
> `JWT_KEY=change_this_secret_key` (except with `ENVIRONMENT=test`): a publicly
> known secret lets anyone forge a JWT, including an admin token.

After startup:

- application — [http://localhost:5000](http://localhost:5000)
- interactive API documentation — [http://localhost:5000/docs](http://localhost:5000/docs)
- pgAdmin — [http://localhost:5050](http://localhost:5050)
  (`postgres@postgres.com` / `postgres`, host `postgres`, port `5432`, database
  `postgres`)

> If a host port is already taken (for example, by a local PostgreSQL on `5432`),
> set free `POSTGRES_HOST_PORT`, `REDIS_HOST_PORT`, `PGADMIN_HOST_PORT` or
> `WEB_HOST_PORT` values in `.env`. Ports inside the Docker network stay
> unchanged.

## Environment variables

Main variables (details in `.env.example`):

- `JWT_KEY` — the JWT signing secret; required, a long random string
  (`python -c "import secrets; print(secrets.token_hex(32))"`); the placeholder is
  rejected in every environment except `ENVIRONMENT=test`;
- `ENVIRONMENT` — `development` (default) or `production` (enables the `Secure`
  cookie flag and HSTS);
- `DATABASE_URL` — PostgreSQL connection (Alembic migrations are applied
  automatically on container start);
- `MAX_UPLOAD_MB` — maximum uploaded document size, `30` by default;
- `DOCS_DIR` — storage directory for uploaded source documents;
- `RSOSH_EXECUTION` — `auto` (default), `celery` or `inline`;
- `RSOSH_PDF_DPI` — PDF page rasterization DPI for OCR, `300` by default.

## Image

The image is built from `python:3.11-slim-bookworm` and installs Tesseract
(`rus`, `eng`, `osd`) and the Python dependencies from `requirements.txt`.
Packages installed solely for the build are not separated: `pip` does not use
`apt`, so there is nothing to clean up, while `apt-get purge --auto-remove`
without a package list would remove part of the runtime environment along with
the apt lists. `setup.sh` is normalized to LF inside the image, so the container
starts regardless of the developer's Git settings (a CRLF checkout otherwise
produces `exec /setup.sh: no such file or directory`).

> In development mode the `web`, `celery` and `test` services mount the working
> tree (`./app`, `./migrations`, `./scripts`), so code changes are picked up
> without rebuilding the image. Changing `requirements.txt` requires
> `docker compose build`.

## Logs and shutdown

```bash
docker compose logs -f web celery
docker compose down        # keeps volumes
docker compose down -v     # removes the database and Redis volumes
```

See also: [tests](testing.md) · [architecture](architecture.md) ·
[technology stack](tech-stack.md).

# Papaya

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)

| 🌐 Language |
|-------------|
| [🇷🇺 Russian](README.md) • [🇬🇧 English](English.md) |

## Content

- [Changelog](#changelog)
- [Coming Soon](#coming-soon)
- [Technology Stack](#technology-stack)
- [Prerequisites](#prerequisites)
- [Local Setup](#local-setup)
- [API and Routes](#api-and-routes)
- [License](#license)

Papaya is a web service for school students that brings information about nationwide and regional academic competitions together in one place. Users can register, manage their profiles, and browse educational events.

Project demo: https://papaya-bm5w.onrender.com/ (the first request after an idle period may take some time).

## Changelog

### Current version

- Authentication now uses access and refresh JWT cookies; registration and login include password hashing and data validation.
- Added the active olympiad catalog, event pages, a user's own event list, list of users and profile editing.
- Users with the `EDITOR` or `ADMIN` role can create and update events through the application interface.
- Added olympiad imports from PDF and XLSX tables. PDFs are processed with Tesseract OCR in the Celery queue, and extra table columns are preserved in the event description.
- Added the `USER`, `EDITOR`, and `ADMIN` roles, together with a dedicated administration panel for users and events.
- The welcome, login, and registration pages are available without authentication.
- Added Redis caching and a Celery queue for resource-intensive PDF processing.
- Added a containerized environment with PostgreSQL, Redis, the web application, Celery, and pgAdmin. `setup.sh` runs automatically inside the containers and verifies Tesseract OCR.

## Coming Soon

- School student, university student, teacher, and educational organization roles with different capabilities.
- Categorized olympiad tabs and improved event grouping.
- Direct import of tables from photos in addition to PDF and XLSX.
- More pages available without authentication.
- A dedicated, improved workflow for adding and editing events.
- Automated tests.
- Tabs for Olympiads that provide admission rights (BVI) for a specific educational institution.
- Search.
- Olympiad tags by category.

## Technology Stack

- **Backend:** Python 3.11, FastAPI, Gunicorn, Uvicorn
- **Frontend:** HTML, CSS, JavaScript SPA, Tailwind CSS
- **Database:** PostgreSQL 16, SQLAlchemy (async ORM), asyncpg
- **Authentication:** JWT cookies, bcrypt, Pydantic validation
- **Caching and background jobs:** Redis 7, Celery
- **Table import:** pandas, OpenPyXL, img2table, Tesseract OCR
- **Containerization:** Docker, Docker Compose

## Prerequisites

Install the following before starting:

- **Git**;
- **Docker Desktop** or Docker Engine;
- **Docker Compose v2** (the `docker compose` command);
- an internet connection for the first image build and dependency downloads.

You do not need to install Python, PostgreSQL, Redis, or Tesseract separately; they run inside Docker containers.

## Local Setup

### 1. Clone the Repository

```bash
git clone https://github.com/SHAMBALENOK/Papaya.git
cd Papaya
```

Start Docker Desktop if you use it.

### 2. Configure the Tokens

Before the first launch, open `docker-compose.yml` and fill in `JWT_KEY` and `HF_TOKEN` under the `environment` sections of both the `web` and `celery` services:

```yaml
JWT_KEY: "your_long_random_secret"
HF_TOKEN: "hf_your_Hugging_Face_token"
```

Use the same values for both services (Celery and Web):

- `JWT_KEY` is a long random secret used to sign JWTs;
- `HF_TOKEN` is a read-access Hugging Face token, available from the [token settings page](https://huggingface.co/settings/tokens).

Do not publish real tokens or commit them to a public repository.

### 3. Build and Start the Application

Run this command from the repository root:

```bash
docker compose up --build -d
```

The first build may take several minutes while Docker downloads images, Python dependencies, and OCR components. The `setup.sh` script is the container entrypoint and runs automatically; do not run it manually.

Check the service status:

```bash
docker compose ps
```

After startup, the following services are available:

- application — [http://localhost:5000](http://localhost:5000);
- interactive API documentation — [http://localhost:5000/docs](http://localhost:5000/docs);
- pgAdmin — [http://localhost:5050](http://localhost:5050).

The local pgAdmin credentials from `docker-compose.yml` are `postgres@postgres.com` / `postgres`. To connect from pgAdmin to PostgreSQL, use host `postgres`, port `5432`, database `postgres`, username `postgres`, and password `postgres`. These credentials are intended for local development only.

Follow the web application and task worker logs with:

```bash
docker compose logs -f web celery
```

Run `docker compose logs -f` to follow every service.

### 4. Stop and Clean Up

Stop the services while preserving their Docker volumes:

```bash
docker compose down
```

Stop the services and remove the PostgreSQL, Redis, pgAdmin, and model-cache volumes:

```bash
docker compose down -v
```

> [!WARNING]
> The command with `-v` permanently deletes the local database. Files uploaded to `app/tables` are stored in the project directory and are not removed by this command.

## API and Routes

Every API route uses the `/api/v1` prefix. The complete interactive schema is available at `/docs` while the application is running.

| Method | Path | Description | Access |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/welcome` | Check the session for the public page | Public |
| `GET` | `/api/v1/auth/` | Authentication page state | Public |
| `POST` | `/api/v1/auth/register` | Register a user | Public |
| `POST` | `/api/v1/auth/login` | Log in and set JWT cookies | Public |
| `GET` | `/api/v1/auth/logout` | Log out and remove JWT cookies | Authenticated |
| `GET` | `/api/v1/events/dashboard` | Active olympiad catalog | Authenticated |
| `GET` | `/api/v1/events/dashboard/my_events` | Current user's events | Authenticated |
| `GET` | `/api/v1/events/<event_id>` | Event details | Authenticated |
| `POST` | `/api/v1/events/add_event` | Create an event | `EDITOR` or `ADMIN` |
| `POST` | `/api/v1/events/edit_event/<event_id>` | Update an event | `EDITOR` or `ADMIN` |
| `POST` | `/api/v1/events/add_events_via_tables` | Import events from PDF or XLSX | `EDITOR` or `ADMIN` |
| `GET` | `/api/v1/user/users` | List active users | Authenticated |
| `GET` | `/api/v1/user/<user_id>` | User profile | Authenticated |
| `POST` | `/api/v1/user/<user_id>/edit_info` | Update the current user's profile | Profile owner |
| `GET` | `/api/v1/admin/users` | Manage users | `ADMIN` |
| `GET` | `/api/v1/admin/events` | Manage events and the archive | `ADMIN` |

## License

This project is distributed under the MIT License.
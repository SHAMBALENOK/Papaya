# Papaya

[![License: GPL](https://img.shields.io/badge/License-GPL-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)

| 🌐 Language |
|-------------|
| [🇷🇺 Russian](README.md) • [🇬🇧 English](English.md) |

## Content

- [What Papaya is](#what-papaya-is)
- [User flow](#user-flow)
- [Data model](#data-model)
- [Roles and permissions](#roles-and-permissions)
- [RSOSH document import](#rsosh-document-import)
- [Technology stack](#technology-stack)
- [Prerequisites](#prerequisites)
- [Local setup](#local-setup)
- [Tests](#tests)
- [API and routes](#api-and-routes)

## What Papaya is

Papaya answers one question: **which olympiads grant BVI (admission without entrance exams) at the university I want?**

It aggregates official RSOSH olympiad lists and links them to universities. A school student finds their university in the catalog, sees the olympiads that grant admission without entrance exams, opens an olympiad and follows the link to its official website. No more browsing university websites and orders by hand.

The whole product is described by one chain:

```text
University → olympiads that grant BVI → olympiad details → official website
```

Anything that does not support this chain is intentionally absent: no olympiad calendar, no stage schedule, no deadlines, no organizers, no recommendation algorithms. Papaya is an aggregator and a catalog, not an admissions system.

## User flow

| Role | What they do |
|------|--------------|
| **Student** (guest or registered) | Searches universities and olympiads, browses catalogs and entity pages. Registration is not required. |
| **University representative** | Manages BVI links of **their own** university: picks existing olympiads from the catalog and claims the university grants BVI for them. They never create olympiads. |
| **Papaya administrator** | Maintains the olympiad and university catalogs, uploads RSOSH documents and confirms imports, moderates BVI requests, manages users and roles. |

End-to-end flow:

```text
Open Papaya
      ↓
Find a university
      ↓
Open the university
      ↓
See the olympiads that grant BVI
      ↓
Open an olympiad
      ↓
Read its details and follow the link to the official website
```

The olympiad page also shows the reverse path: the universities that grant BVI for it.

## Data model

```text
University ──(university_olympiads)── Olympiad ──(source_doc_id)── Docs
        │                                 │
        └──── PENDING / CONFIRMED ────────┘
```

Key decisions:

- **An olympiad is a single canonical entity.** There are no "olympiad 2026" and "olympiad 2027" records: one entry per olympiad, independent of the year.
- **A university never creates a copy of an olympiad.** A link references an existing catalog entry, and a unique index on the pair makes duplicate links impossible even at the database level.
- **A request is not a public fact.** `PENDING` links are visible to the university's own representative and to the administrator; public lists contain confirmed links only.
- **Archive, not delete.** An olympiad that disappears from the RSOSH list moves to `ARCHIVED`: the record is kept and the interface states that it is no longer in the current list.
- **An archived olympiad accepts no new BVI requests.** A request means "we admit students through this olympiad right now", which cannot be true for an olympiad outside the current list: such a request gets 409. Already confirmed links are kept and flagged as historical (`is_historical`) — the archive changes relevance, not history.
- **Archive, never delete.** An olympiad carries history: confirmed links, its source document, its path through the RSOSH lists. There is no physical deletion of catalog records anywhere in the system — neither in the data layer nor in the API.
- **An archive has a reason.** The status is one, but two different mechanisms decide it, so an archived record always carries `archive_reason`: `RSOSH_ABSENT` (not in the RSOSH list — an import brings it back) or `MANUAL` (excluded by an administrator — restorable by hand). A record that vanished from the RSOSH list cannot be restored manually: only the list itself can say it is current again.
- **A skipped row is not a missing one.** If an administrator removed a row in the preview, it does not count as missing from the list: a single recognition error must not archive a real olympiad.
- **Two images per entity.** `preview_image` is used in catalog cards, `image` on the entity page; if one is missing, the interface falls back to the other.
- **Documents are data sources.** Each olympiad stores `source_doc_id`, so it is always clear where the information came from: the olympiad page shows the source via `GET /api/v1/olympiads/<id>/source`, publicly and without exposing the uploaded file itself. The internal `source_doc_id` is not part of public responses, and the source endpoint always answers `200` — a manual entry has a source too ("created by a Papaya administrator").
- **The public model is minimal.** An olympiad response carries only user-facing fields (`id`, `name`, `description`, `official_url`, `preview_image`, `image`, `source_url`, `status`). Internal `name_norm`, `source_doc_id`, `createdAt`, `updatedAt` and `archive_reason` never reach a visitor: they matter for imports and for the admin panel, and explain nothing to a reader.
- **The short name comes first.** Cards, catalogs and page headings show the short name (`MIPT`) first and the full name underneath. The full name is never hidden.
- **There is no generic "organization" entity.** Papaya models neither olympiad organizers nor schools: that would be an extra abstraction level for a single participant type.

## Roles and permissions

| Action | Student / guest | University representative | Administrator |
|--------|-----------------|---------------------------|---------------|
| Catalogs, search, university and olympiad pages | ✅ | ✅ | ✅ |
| Link own university to an existing olympiad | ❌ | ✅ (own university only) | ✅ (any university) |
| Confirm or revoke a BVI link | ❌ | ❌ | ✅ |
| Create or edit an olympiad | ❌ | ❌ | ✅ |
| Create or edit a university | ❌ | ❌ | ✅ |
| Upload RSOSH documents and run an import | ❌ | ❌ | ✅ |
| Manage users and roles | ❌ | ❌ | ✅ |
| Archive an olympiad and restore it by hand | ❌ | ❌ | ✅ |

The rules live in one place, `app/core/deps.py`, including the object-level check "is this your own university".

Role invariant: a representative is "a role plus a university binding", not a separate flag. `EDITOR` without `university_id` is therefore impossible — both the application and the database reject it (`ck_users_representative_needs_university`, migration `0006`). Role and binding change together through **one** endpoint, `POST /api/v1/admin/role/<user_id>`: a regular user cannot be bound to a university just like that, while an administrator may keep a binding so that demoting them returns a representative rather than a plain user. There is no separate "bind a university" route: two ways to grant rights means one of them bypasses the checks.

The last active administrator cannot be banned or demoted (409), because nobody would be able to sign in to the panel. With a second administrator, demotion is allowed.

The check is atomic: it runs under a lock on the administrator rows (`SELECT ... FOR UPDATE` in `id` order) inside the same transaction as the operation itself. Without it, two parallel operations (demote the first admin, ban the second) would each see "someone else remains" and together leave the system without a single active `ADMIN`.

BVI link rights: a representative creates a request for a **current** olympiad and may withdraw it while it is `PENDING`; only an administrator can revoke a confirmed link. A confirmed link is a public fact, so removing it is the administrator's decision, not the requester's.

Moderation is three explicit actions rather than "any status change":

| Action | Effect |
|--------|--------|
| `confirm` | `PENDING` → `CONFIRMED`: the link becomes public |
| `reject`  | the request is declined, the link is deleted |
| `revoke`  | the confirmation is withdrawn, the link is deleted |

There is no `CONFIRMED → PENDING` transition: that is not a request state but the withdrawal of a public fact. Such a record would be invisible in the catalog and would sit in the moderation queue as if the university had just applied again. `confirmedBy` exists only on `CONFIRMED` and points at the administrator who confirmed the link.

## RSOSH document import

An olympiad enters the catalog in exactly two ways:

1. **Import of an official RSOSH document** — the primary path;
2. **Manual creation by an administrator** — the fallback.

The old bulk table import (`POST /api/v1/events/add_events_via_tables`) is gone: no route, no code, no button in the interface.

```text
Document
    ↓ file type detection (by signature, not only by extension)
Image preprocessing + orientation detection (0/90/180/270)
    ↓
Extraction: native XLSX reading → PDF text-layer tables → OCR for scans/images
    ↓
Table detection and reconstruction (borders, merged and multi-line cells)
    ↓
Cell normalization (line breaks, quotes, "ё", mirrored RSOSH headers)
    ↓
Olympiad extraction (name column detection, boilerplate removal)
    ↓
Validation (name length, junk, recognition confidence)
    ↓
Deduplication: exact → merge, close → merge, uncertain → human review
    ↓
Import preview (nothing is written yet)
    ↓ administrator confirmation
Create/update olympiads + archive the ones missing from the list
```

What the importer accounts for:

- **XLSX** is read natively (openpyxl): multi-line cells, vertically merged ranges, several sheets;
- **PDF with a text layer** is parsed from the document structure (pdfplumber) — no needless OCR;
- **scans without a text layer** are rasterized (300 dpi) and recognized by Tesseract (`rus+eng`) with word coordinates;
- **rotated pages** (90/180/270) are detected through Tesseract OSD, with a trial-OCR comparison as a fallback;
- **skewed scans** are straightened by the estimated skew angle;
- **tables spanning several pages** are joined, repeated headers are dropped, and the first page's header defines the columns for all following pages;
- **mirrored headers** (a quirk of some RSOSH documents) are recognized and un-reversed;
- **boilerplate rows** (letterheads, order details, signatures) never reach the catalog;
- **an empty or unreadable document** is never imported silently: the run ends in `failed` with a readable reason.

Import state lives in `docs.metadata['rsosh']` (`processing` / `review` / `approved` / `rejected` / `failed`) — a separate table for runs is unnecessary because a run always belongs to a concrete document. Imports run in a Celery task by default and fall back to in-process execution when the broker is unavailable (`RSOSH_EXECUTION=auto|celery|inline`).

## Technology stack

- **Backend:** Python 3.11, FastAPI, Gunicorn, Uvicorn, Pydantic, PyJWT, bcrypt, Werkzeug
- **Frontend:** HTML, CSS, Vanilla JS SPA, Tailwind CSS
- **Database:** PostgreSQL 16, SQLAlchemy (async ORM), asyncpg, Alembic
- **Authentication:** JWT cookies, bcrypt, Pydantic validation
- **Caching and background jobs:** Redis 7, Celery
- **RSOSH import:** pdfplumber, pypdfium2, pytesseract (Tesseract `rus`/`eng`/`osd`), OpenCV, openpyxl, NumPy
- **Containerization:** Docker, Docker Compose, Render

## Prerequisites

- **Git**;
- **Docker Desktop** or Docker Engine;
- **Docker Compose v2** (the `docker compose` command);
- an internet connection for the first image build and dependency downloads.

You do not need to install Python, PostgreSQL, Redis, or Tesseract separately; they run inside Docker containers.

## Local setup

```bash
git clone https://github.com/SHAMBALENOK/Papaya.git
cd Papaya
cp .env.example .env      # optional: the defaults work as is
docker compose up -d --build
```

After startup:

- application — [http://localhost:5000](http://localhost:5000)
- interactive API documentation — [http://localhost:5000/docs](http://localhost:5000/docs)
- pgAdmin — [http://localhost:5050](http://localhost:5050) (`postgres@postgres.com` / `postgres`, host `postgres`, port `5432`, database `postgres`)

Main environment variables (details in `.env.example`):

- `JWT_KEY` — the JWT signing secret; in production use a long random string (`python -c "import secrets; print(secrets.token_hex(32))"`);
- `ENVIRONMENT` — `development` (default) or `production` (enables the `Secure` cookie flag and rejects placeholder secrets);
- `DATABASE_URL` — PostgreSQL connection (Alembic migrations are applied automatically on container start);
- `MAX_UPLOAD_MB` — maximum uploaded document size, `30` by default;
- `DOCS_DIR` — storage directory for uploaded source documents;
- `RSOSH_EXECUTION` — `auto` (default), `celery`, or `inline`;
- `RSOSH_PDF_DPI` — PDF page rasterization DPI for OCR, `300` by default.

> In development mode the `web`, `celery`, and `test` services mount the working tree (`./app`, `./migrations`, `./scripts`), so code changes are picked up without rebuilding the image. Changing `requirements.txt` requires `docker compose build`.

Logs and shutdown:

```bash
docker compose logs -f web celery
docker compose down        # keeps volumes
docker compose down -v     # removes the database and Redis volumes
```

## Tests

Tests run in an isolated container of the `testing` profile and never touch the working database: a separate `papaya_test` database is created, migrations are applied, Redis is flushed, and the catalogs are emptied before every test.

```bash
docker compose --profile testing run --rm test
```

Covered scenarios: catalogs and search, the two images per entity, the public source endpoint, manual archive and the manual-restore restriction, BVI links on both sides, moderation, role boundaries (student / representative / administrator), and the importer — XLSX, PDF with a text layer, scanned PDF, pages rotated by 90/180/270, PNG/JPEG images, multi-line and merged cells, repeated import of the same document, archiving of missing olympiads, unreadable documents, and permissions.

## API and routes

Every route uses the `/api/v1` prefix. The complete interactive schema is available at `/docs` while the application is running. Catalogs and search are public.

| Method | Path | Description | Access |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/universities?search=` | University catalog | Public |
| `GET` | `/api/v1/universities/<id>` | University page | Public |
| `GET` | `/api/v1/universities/<id>/olympiads` | Olympiads granting BVI (`?include_pending=true` for own requests) | Public / own requests |
| `POST` | `/api/v1/universities/add_university` | Create a university | `ADMIN` |
| `POST` | `/api/v1/universities/edit_university/<id>` | Update a university | `ADMIN` |
| `POST` | `/api/v1/universities/<id>/bvi` | Request a BVI link to an existing olympiad | `EDITOR` (own university) or `ADMIN` |
| `POST` | `/api/v1/universities/<id>/bvi/remove` | Remove a BVI link | `EDITOR` (own university) or `ADMIN` |
| `POST` | `/api/v1/universities/<id>/bvi/<olympiad_id>/moderation` | Confirm, reject or revoke a BVI link | `ADMIN` |
| `GET` | `/api/v1/olympiads?search=&include_archived=` | Olympiad catalog | Public |
| `GET` | `/api/v1/olympiads/<id>/source` | Where the olympiad data came from | Public |
| `GET` | `/api/v1/olympiads/<id>` | Olympiad page | Public |
| `GET` | `/api/v1/olympiads/<id>/universities` | Universities granting BVI for this olympiad | Public |
| `POST` | `/api/v1/olympiads/add_olympiad` | Create an olympiad manually | `ADMIN` |
| `POST` | `/api/v1/olympiads/edit_olympiad/<id>` | Update an olympiad | `ADMIN` |
| `GET` | `/api/v1/search?q=` | Search both catalogs | Public |
| `POST` | `/api/v1/docs/upload` | Upload a source document (RSOSH list, order, other) | `ADMIN` |
| `POST` | `/api/v1/imports/rsosh` | Start an RSOSH import | `ADMIN` |
| `GET` | `/api/v1/imports` | List of import runs | `ADMIN` |
| `GET` | `/api/v1/imports/<id>` | Import state and summary | `ADMIN` |
| `GET` | `/api/v1/imports/<id>/preview` | Import preview (candidates) | `ADMIN` |
| `POST` | `/api/v1/imports/<id>/confirm` | Apply the import | `ADMIN` |
| `POST` | `/api/v1/imports/<id>/reject` | Reject the import results | `ADMIN` |
| `POST` | `/api/v1/admin/archive_olympiad/<id>` | Archive or restore an olympiad (409 when restoring one absent in the RSOSH list) | `ADMIN` |
| `GET` | `/api/v1/admin/users` | Manage users and roles | `ADMIN` |
| `GET` | `/api/v1/admin/bvi` | BVI request moderation queue | `ADMIN` |
| `POST` | `/api/v1/auth/register` | Register a user | Public |
| `POST` | `/api/v1/auth/login` | Log in and set JWT cookies | Public |
| `POST` | `/api/v1/auth/logout` | Log out and remove JWT cookies | Authenticated |
| `GET` | `/api/v1/health`, `/api/v1/ready` | Liveness and readiness probes | Public |

Unknown paths under `/api/v1/` return a JSON 404 instead of the SPA HTML shell.

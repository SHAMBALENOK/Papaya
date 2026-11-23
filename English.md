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

Papaya answers one question: **which olympiads give a university applicant a benefit, and on what terms?**

It aggregates official RSOSH olympiad lists, university orders and the olympiad seasons and profiles those orders refer to. A school student finds their university in the catalog, sees the benefit rules published by that university, opens the olympiad of the relevant season and follows the link to its official website. No more browsing university websites and orders by hand.

The whole product is described by one chain:

```text
Olympiad → season → profile (RSOSH level)
        → university benefit rule → supporting document
```

Anything that does not support this chain is intentionally absent: no olympiad calendar, no registration or event dates, no deadlines, no recommendation algorithms. Papaya is an aggregator and a catalog, not an admissions system.

## User flow

| Role | What they do |
|------|--------------|
| **Student** (guest or registered) | Searches universities and olympiads, browses catalogs and entity pages. Registration is not required. |
| **University representative** | Manages benefit rules of **their own** university: links an existing olympiad, season and profile, states the benefit type and required result, and attaches the university order. They never create olympiads or seasons; they can request a missing one. |
| **Papaya administrator** | Maintains the olympiad and university catalogs, uploads RSOSH documents and confirms imports, verifies or rejects benefit rules, manages users, roles and entity requests. |

End-to-end flow:

```text
Open Papaya
      ↓
Find a university
      ↓
Open the university or filter the benefit catalog
      ↓
See the rules: olympiad, season, profile, RSOSH level, benefit type
      ↓
Open an olympiad and switch between actual and archived seasons
      ↓
Read the supporting document and follow the link to the official website
```

## Data model

```text
Olympiad ── Season ── Profile (RSOSH level 1/2/3 or null)
    │            │                 │
    └──────── Benefit rule ────────┘
                   │
          University order (doc)
```

Key decisions:

- **An olympiad is a single canonical entity.** There are no "olympiad 2026" and "olympiad 2027" records: one entry per olympiad, independent of the year. The year lives in a season.
- **A season is an olympiad plus a label.** It has no registration or event dates and no `availability`: those describe a university's admission campaign, not the olympiad.
- **RSOSH level belongs to a profile of a season.** Only `1`, `2` or `3` (or nothing) is valid, and a level is never copied to another season: the set of profiles and their levels change every year.
- **A benefit rule is the only place where a benefit is stated.** It references a university, an olympiad, a season and a profile, names the benefit type (`BVI`, `EGE_100`, `DVI_100`, `OTHER`) and the required result (`WINNER`, `PRIZE`, `WINNER_OR_PRIZE`), and points at a supporting university document. Admission without entrance exams is just `benefit_type: "BVI"`; there is no separate BVI entity, request or moderation queue.
- **EGE requirement is a separate optional structure.** `{"subject", "min_score"}` is attached to the rule, not to the olympiad profile.
- **A rule is consistent by construction.** The season must belong to the olympiad, the profile to the season, and the document to the same university; otherwise the API returns `422`. Archived olympiads accept no new rules, but existing rules stay readable and editable.
- **Archive, never delete.** An olympiad carries history: benefit rules, its source document, its path through the RSOSH lists. There is no physical deletion of catalog records anywhere in the system — neither in the data layer nor in the API.
- **An archive has a reason.** The status is one, but two different mechanisms decide it, so an archived record always carries `archive_reason`: `RSOSH_ABSENT` (not in the RSOSH list — an import brings it back) or `MANUAL` (excluded by an administrator — restorable by hand).
- **A skipped row is not a missing one.** If an administrator removed a row in the preview, it does not count as missing from the list: a single recognition error must not archive a real olympiad.
- **Two images per entity.** `preview_image` is used in catalog cards, `image` on the entity page; if one is missing, the interface falls back to the other.
- **Two kinds of documents.** An RSOSH list (`RSOSH_LIST`) is the import source; a university order (`UNIVERSITY_ORDER`) or other document (`OTHER`) belongs to a university and supports its benefit rules. There is no separate "Source" entity.
- **The public model is minimal.** An olympiad response carries only user-facing fields (`id`, `name`, `description`, `official_url`, `preview_image`, `image`, `organizer`, `status`). Internal `name_norm`, `source_doc_id`, `createdAt`, `updatedAt` and `archive_reason` never reach a visitor.
- **Programs are an independent reference.** `university_programs` belongs to a university; benefit rules do not reference programs.
- **The short name comes first.** Cards, catalogs and page headings show the short name (`MIPT`) first and the full name underneath. The full name is never hidden.

## Roles and permissions

| Action | Student / guest | University representative | Administrator |
|--------|-----------------|---------------------------|---------------|
| Catalogs, search, university and olympiad pages | ✅ | ✅ | ✅ |
| Create and edit own university's benefit rules | ❌ | ✅ (own university only) | ✅ (any university) |
| Publish or hide a rule | ❌ | ✅ (own university) | ✅ |
| Verify or reject a rule | ❌ | ❌ | ✅ |
| Manage own university's programs and documents | ❌ | ✅ | ✅ |
| Request a missing olympiad, season or profile | ❌ | ✅ | ✅ |
| Create or edit an olympiad, season or profile | ❌ | ❌ | ✅ |
| Create or edit a university | ❌ | ❌ | ✅ |
| Upload RSOSH documents and run an import | ❌ | ❌ | ✅ |
| Manage users and roles | ❌ | ❌ | ✅ |
| Archive an olympiad and restore it by hand | ❌ | ❌ | ✅ |

The rules live in one place, `app/core/deps.py`, including the object-level check "is this your own university".

Role invariant: a representative is "a role plus a university binding", not a separate flag. `EDITOR` without `university_id` is therefore impossible — both the application and the database reject it (`ck_users_representative_needs_university`, migration `0006`). Role and binding change together through **one** endpoint, `POST /api/v1/admin/role/<user_id>`: a regular user cannot be bound to a university just like that, while an administrator may keep a binding so that demoting them returns a representative rather than a plain user. There is no separate "bind a university" route: two ways to grant rights means one of them bypasses the checks.

The last active administrator cannot be banned or demoted (409), because nobody would be able to sign in to the panel. With a second administrator, demotion is allowed.

The check is atomic: it runs under a lock on the administrator rows (`SELECT ... FOR UPDATE` in `id` order) inside the same transaction as the operation itself. Without it, two parallel operations (demote the first admin, ban the second) would each see "someone else remains" and together leave the system without a single active `ADMIN`.

Rule verification: a representative creates and edits rules of their own university and may publish or hide them, but a rule is always created `unverified`. Only an administrator can `verify` it (the rule must have a `UNIVERSITY_ORDER` document of the same university) or `reject` it with a non-empty reason, which also unpublishes the rule.

Public catalog: a rule is visible when it is published and not rejected. An unverified rule remains visible with an honest "Not verified by Papaya" warning; a draft or rejected rule is not visible even by direct id.

Versions are optimistic: every update and rollback sends the current `version`, a stale value returns `409`. A rollback is atomic under `FOR UPDATE`, accepts both the target and the expected current version, creates a new version, marks the rule `unverified` and records the change in the status history.

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

Import state lives in `docs.metadata['rsosh']` (`processing` / `paused` / `review` / `approved` / `rejected` / `failed`) — a separate table for runs is unnecessary because a run always belongs to a concrete document. Imports run in a Celery task by default and fall back to in-process execution when the broker is unavailable (`RSOSH_EXECUTION=auto|celery|inline`).

While a run is `processing` the section carries a `progress` stage (`starting` / `extracting` / `matching`), so the panel shows what is happening instead of a bare "processing". An administrator can pause a run and resume it later: pausing takes effect at a stage boundary, and when it lands after recognition the run keeps the recognized rows, so resuming continues straight to matching without re-reading the document. The administrator's review choices (confirmed/dropped candidates, renamed names and descriptions, forced merges) are saved with the run, survive a page reload, and are applied on confirmation when the request body is omitted.

### Official list: table → plan → apply

A scan recognized as an official RSOSH list (table detected and the academic year read from the document) goes through its own pipeline; every other document keeps the legacy `preview` + `confirm` path. The mode is visible as `mode: "official_list"` in the import state.

```text
PDF stored under a UUID name
    ↓ background Celery task (RSOSH_EXECUTION=auto|celery|inline)
Recognition: page orientation, table borders, repeated headers, merged and multi-line cells
    ↓
XLSX ("Перечень <season>" + "Сводка") and an HTML rendering
    ↓ served as RSOSH_TABLE / RSOSH_HTML companion documents, server-side files only
Import plan: create / use / review / skip, with seasons, profiles, levels, missing records
    ↓ administrator corrects the plan (PATCH …/plan)
Atomic apply (POST …/apply) — one transaction, one document applied once
    ↓
ImportJob / ImportRecord rows and the decision history in docs.metadata['rsosh']
```

Rules the pipeline enforces:

- **The table exists before matching.** The XLSX is an intermediate artifact, not a report: the plan is built from it. Sheet 1 is the list, sheet 2 is the summary aggregated from sheet 1.
- **The season comes from the document**, not from the year the import was started. Profiles and levels belong to the season, so an olympiad is never duplicated across seasons; a level change is recorded in history.
- **Fuzzy matches are never applied automatically.** Only an exact normalized-name match becomes `use`; similar entries produce `review` and require an explicit administrator decision.
- **Unreadable rows are errors, not silence.** A row whose profile or level could not be recognized blocks `apply` until the administrator fills it in or explicitly skips it (`action: "skip"`).
- **Missing olympiads are not deleted.** Absence is recorded only for a complete list (`complete=true`, a season, no unresolved errors, `missing_allowed=true`) and only on request (`mark_missing=true`): profiles lose their level and olympiads are archived with the `RSOSH_ABSENT` reason.
- **Re-importing the same document creates nothing twice.** The generated table and HTML are reused; the plan is rebuilt; a second apply returns `409`.
- **Apply is atomic.** One transaction under the list-application lock; an error rolls everything back, so a partially applied list cannot exist.

The documents page shows the source PDF, the generated XLSX, the HTML table, the season, the date, the status and the author. The table itself is paged on the server (`GET …/table` with `sheet`, `offset`, `limit`, `search`): a list has 300+ rows.

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
cp .env.example .env
# replace JWT_KEY in .env with your own random secret:
python -c "import secrets; print(secrets.token_hex(32))"
docker compose up -d --build
```

> The application refuses to start with the placeholder
> `JWT_KEY=change_this_secret_key` (except with `ENVIRONMENT=test`): a
> publicly known secret lets anyone forge a JWT, including an admin token.

After startup:

- application — [http://localhost:5000](http://localhost:5000)
- interactive API documentation — [http://localhost:5000/docs](http://localhost:5000/docs)
- pgAdmin — [http://localhost:5050](http://localhost:5050) (`postgres@postgres.com` / `postgres`, host `postgres`, port `5432`, database `postgres`)

> If a host port is already taken (for example, by a local PostgreSQL on
> `5432`), set free `POSTGRES_HOST_PORT`, `REDIS_HOST_PORT`,
> `PGADMIN_HOST_PORT`, or `WEB_HOST_PORT` values in `.env`. Ports inside the
> Docker network stay unchanged.

Main environment variables (details in `.env.example`):

- `JWT_KEY` — the JWT signing secret; required, a long random string (`python -c "import secrets; print(secrets.token_hex(32))"`); the placeholder is rejected in every environment except `ENVIRONMENT=test`;
- `ENVIRONMENT` — `development` (default) or `production` (enables the `Secure` cookie flag and HSTS);
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

Covered scenarios: catalogs and search, the two images per entity, the public source endpoint, manual archive, seasons and profiles with RSOSH levels, benefit rules with EGE requirements and versions, the public catalog filters and `total`, entity requests, role boundaries (student / representative / administrator), and the importer — XLSX, PDF with a text layer, scanned PDF, pages rotated by 90/180/270, PNG/JPEG images, multi-line and merged cells, repeated import of the same document, archiving of missing olympiads, unreadable documents, and permissions.

## API and routes

Every route uses the `/api/v1` prefix. The complete interactive schema is available at `/docs` while the application is running. Catalogs and search are public.

| Method | Path | Description | Access |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/universities?search=` | University catalog | Public |
| `GET` | `/api/v1/universities/<id>` | University page | Public |
| `POST` | `/api/v1/universities/add_university` | Create a university | `ADMIN` |
| `POST` | `/api/v1/universities/edit_university/<id>` | Update a university | `ADMIN` |
| `GET` | `/api/v1/universities/<id>/programs` | University programs (independent reference) | Public |
| `POST` | `/api/v1/universities/<id>/programs` | Create a program of own university | `EDITOR` (own university) or `ADMIN` |
| `GET` | `/api/v1/universities/<id>/entity-requests` | Own requests for missing catalog entities | `EDITOR` (own university) or `ADMIN` |
| `POST` | `/api/v1/universities/<id>/entity-requests` | Request a missing olympiad, season or profile | `EDITOR` (own university) or `ADMIN` |
| `GET` | `/api/v1/olympiads?search=&include_archived=` | Olympiad catalog | Public |
| `GET` | `/api/v1/olympiads/<id>/source` | Where the olympiad data came from | Public |
| `GET` | `/api/v1/olympiads/<id>` | Olympiad page | Public |
| `GET` | `/api/v1/olympiads/<id>/universities` | Universities with published rules for this olympiad | Public |
| `GET` | `/api/v1/olympiads/<id>/seasons` | Seasons of an olympiad (`include_archived`, `profiles`) | Public |
| `POST` | `/api/v1/olympiads/<id>/seasons` | Create a season | `ADMIN` |
| `GET` | `/api/v1/seasons/<id>` | Season | Public |
| `PUT` | `/api/v1/seasons/<id>` | Update a season (requires `version`) | `ADMIN` |
| `GET` | `/api/v1/seasons/<id>/profiles` | Profiles of a season | Public |
| `POST` | `/api/v1/seasons/<id>/profiles` | Create a profile with RSOSH level | `ADMIN` |
| `POST` | `/api/v1/olympiads/add_olympiad` | Create an olympiad manually | `ADMIN` |
| `POST` | `/api/v1/olympiads/edit_olympiad/<id>` | Update an olympiad | `ADMIN` |
| `GET` | `/api/v1/search?q=` | Search both catalogs | Public |
| `GET` | `/api/v1/benefits` | Published benefit rules (`search`, `benefit_type`, `university_id`, `olympiad_id`, `season_id`, `profile_id`, `level`, `limit`, `offset`) | Public |
| `GET` | `/api/v1/benefits/<id>` | One published benefit rule | Public |
| `GET` | `/api/v1/benefits/olympiad/<id>` | Published benefit rules for an olympiad | Public |
| `GET` | `/api/v1/universities/<id>/benefits` | Published benefit rules of a university | Public |
| `POST` | `/api/v1/universities/<id>/benefits` | Create a benefit rule of own university | `EDITOR` (own university) or `ADMIN` |
| `PUT` | `/api/v1/benefits/<id>` | Update a rule (requires `version`) | `EDITOR` (own university) or `ADMIN` |
| `POST` | `/api/v1/benefits/<id>/rollback` | Restore a version atomically | `EDITOR` (own university) or `ADMIN` |
| `POST` | `/api/v1/benefits/<id>/verify` | Verify a rule against a university order | `ADMIN` |
| `POST` | `/api/v1/docs/upload` | Upload a source document (RSOSH list, order, other) | `ADMIN` |
| `POST` | `/api/v1/imports/rsosh` | Start an RSOSH import | `ADMIN` |
| `GET` | `/api/v1/imports` | List of import runs | `ADMIN` |
| `GET` | `/api/v1/imports/<id>` | Import state and summary | `ADMIN` |
| `GET` | `/api/v1/imports/<id>/preview` | Import preview (candidates) | `ADMIN` |
| `POST` | `/api/v1/imports/<id>/confirm` | Apply the import | `ADMIN` |
| `POST` | `/api/v1/imports/<id>/reject` | Reject the import results | `ADMIN` |
| `POST` | `/api/v1/imports/<id>/pause` | Pause a running import | `ADMIN` |
| `POST` | `/api/v1/imports/<id>/resume` | Resume a paused import | `ADMIN` |
| `PUT` | `/api/v1/imports/<id>/selection` | Save the administrator's review choices | `ADMIN` |
| `GET` | `/api/v1/imports/<id>/plan` | Official list import plan (nothing written yet) | `ADMIN` |
| `PATCH` | `/api/v1/imports/<id>/plan` | Correct matches, names, levels or actions in the plan | `ADMIN` |
| `POST` | `/api/v1/imports/<id>/apply` | Apply the approved plan atomically | `ADMIN` |
| `GET` | `/api/v1/imports/<id>/history` | What the document changed in the catalog | `ADMIN` |
| `GET` | `/api/v1/imports/<id>/table` | Paged view of the generated list/summary table | `ADMIN` |
| `POST` | `/api/v1/admin/archive_olympiad/<id>` | Archive or restore an olympiad (409 when restoring one absent in the RSOSH list) | `ADMIN` |
| `GET` | `/api/v1/admin/users` | Manage users and roles | `ADMIN` |
| `GET` | `/api/v1/admin/benefits` | Benefit rule moderation queue (`needs_review`, `verification_status`) | `ADMIN` |
| `GET` | `/api/v1/admin/entity-requests` | Requests for missing catalog entities (`status`, `limit`, `offset`, `total`) | `ADMIN` |
| `POST` | `/api/v1/admin/entity-requests/<id>/approve` | Approve a request and create the entity once | `ADMIN` |
| `POST` | `/api/v1/admin/entity-requests/<id>/reject` | Reject a request with a required reason | `ADMIN` |
| `GET` | `/api/v1/admin/docs` | Document list (`search`, `type`, `status`, `limit`, `offset`, `total`) | `ADMIN` |
| `GET` | `/api/v1/admin/imports` | Import run journal | `ADMIN` |
| `GET` | `/api/v1/admin/imports/<id>` | One import run with per-row records | `ADMIN` |
| `GET` | `/api/v1/admin/audit` | Audit log (`entity_type`, `entity_id`, `action`, `limit`, `offset`, `total`) | `ADMIN` |
| `POST` | `/api/v1/representative-applications` | Apply to represent a university | Authenticated |
| `GET` | `/api/v1/applications/my` | Own representative applications | Authenticated |
| `POST` | `/api/v1/auth/register` | Register a user | Public |
| `POST` | `/api/v1/auth/login` | Log in and set JWT cookies | Public |
| `POST` | `/api/v1/auth/logout` | Log out and remove JWT cookies | Authenticated |
| `GET` | `/api/v1/health`, `/api/v1/ready` | Liveness and readiness probes | Public |

Unknown paths under `/api/v1/` return a JSON 404 instead of the SPA HTML shell.

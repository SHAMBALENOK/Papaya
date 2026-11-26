# Papaya

[![License: GPL](https://img.shields.io/badge/License-GPL-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)

| 🌐 Language / Язык |
|--------|
| [🇬🇧 English](English.md) • [🇷🇺 Русский](README.md) • [📚 Documentation](docs/en/README.md) |

## What Papaya is

Papaya answers one question: **which olympiads give a university applicant a
benefit, and on what terms?**

It aggregates official RSOSH olympiad lists, university orders and the olympiad
seasons and profiles those orders refer to. A school student finds their
university in the catalog, sees the benefit rules published by that university,
opens the olympiad of the relevant season and follows the link to its official
website. No more browsing university websites and orders by hand.

The whole product is described by one chain:

```text
Olympiad → season → profile (RSOSH level)
        → university benefit rule → supporting document
```

Anything that does not support this chain is intentionally absent: no olympiad
calendar, no registration or event dates, no deadlines, no recommendation
algorithms. Papaya is an aggregator and a catalog, not an admissions system.

## How it works

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

## Quick start

You only need Docker Desktop (or Docker Engine) and Docker Compose v2 — Python,
PostgreSQL, Tesseract and the other dependencies run inside containers.

```bash
git clone https://github.com/SHAMBALENOK/Papaya.git
cd Papaya
cp .env.example .env
# replace JWT_KEY in .env with your own random secret:
python -c "import secrets; print(secrets.token_hex(32))"
docker compose up -d --build
```

After startup:

- application — [http://localhost:5000](http://localhost:5000)
- interactive API documentation — [http://localhost:5000/docs](http://localhost:5000/docs)
- pgAdmin — [http://localhost:5050](http://localhost:5050)
  (`postgres@postgres.com` / `postgres`, host `postgres`, port `5432`, database
  `postgres`)

Environment variables, ports, the image, logs and shutdown are covered in
[docs/en/getting-started.md](docs/en/getting-started.md).

## Documentation

All in-depth information lives in [docs/en](docs/en/README.md):

| Section | Document |
|---------|----------|
| Data model | [docs/en/data-model.md](docs/en/data-model.md) |
| Roles and permissions | [docs/en/roles-and-permissions.md](docs/en/roles-and-permissions.md) |
| RSOSH document import | [docs/en/rsosh-import.md](docs/en/rsosh-import.md) |
| Features | [docs/en/features.md](docs/en/features.md) |
| Architecture | [docs/en/architecture.md](docs/en/architecture.md) |
| Technology stack | [docs/en/tech-stack.md](docs/en/tech-stack.md) |
| Getting started | [docs/en/getting-started.md](docs/en/getting-started.md) |
| Tests | [docs/en/testing.md](docs/en/testing.md) |
| API | [docs/en/api.md](docs/en/api.md) |

Additional materials (currently in Russian): [MVP boundaries](docs/MVP.md),
[project status and next steps](docs/TODO.md), and
[detailed API responses](docs/responses.md).

## Status

The current stage is the canonical-model MVP: olympiad → season → profile with
an RSOSH level, a benefit rule with a supporting document and a separate EGE
requirement, representative requests for missing entities, a public catalog with
server-side filters, and olympiad pages with actual and archived seasons. The
next steps are in [docs/TODO.md](docs/TODO.md), MVP boundaries in
[docs/MVP.md](docs/MVP.md) (both in Russian).

## License

The project is distributed under the [GNU GPL 3.0](LICENSE). The full text is in
the [LICENSE](LICENSE) file.

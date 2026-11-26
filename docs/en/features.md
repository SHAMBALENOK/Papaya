# Features

[← Documentation](README.md) · [Project README](../../English.md) · [Русская версия](../features.md)

## Implemented

- public university and olympiad catalogs with search (case-insensitive,
  multi-line and partial matches);
- unified search across both catalogs, `GET /api/v1/search?q=…`;
- university and olympiad pages with a two-way BVI relationship;
- representative applications and administrator moderation;
- manual creation and editing of universities and olympiads by an administrator;
- olympiad archiving and automatic archiving of entries missing from the RSOSH
  list;
- source document upload and RSOSH import with preview and confirmation;
- official RSOSH list import: an XLSX table, a plan with seasons and profiles,
  plan corrections, atomic apply and change history;
- authentication (JWT in HttpOnly cookies), profiles, roles and object-level
  access;
- versioned profile cache in Redis; catalogs are read directly from PostgreSQL
  so a visitor never sees a stale card after an edit;
- health/readiness routes and a Docker healthcheck;
- Alembic migrations applied automatically on startup;
- automated tests: business logic, permissions, every import format (XLSX, PDF,
  scan, rotation, image), deduplication and archiving.

## Intentionally not implemented

These are next steps, not MVP: olympiad schedules and stages, deadlines,
results, seasons/editions, additional benefit types beyond `BVI`, `EGE_100`,
`DVI_100` and `OTHER`, organizers, schools, recommendations, a mobile app and
payments.

See also: [MVP.md](../MVP.md) · [TODO.md](../TODO.md) (both in Russian).

# API

[← Documentation](README.md) · [Project README](../../English.md) · [Русская версия](../api.md)

Every route uses the `/api/v1` prefix. Authentication uses JWTs in HttpOnly
cookies (`access_jwt`, `refresh_jwt`), with CSRF protection via `SameSite=Lax`
and the `Secure` flag in production. The complete interactive schema is
available at http://localhost:5000/docs; detailed responses are described in
[responses.md](../responses.md) (Russian).

## Catalogs, search and pages

| Method | Path | Description | Access |
|--------|------|-------------|--------|
| `GET` | `/api/v1/universities?search=` | University catalog | Public |
| `GET` | `/api/v1/universities/{id}` | University page | Public |
| `GET` | `/api/v1/universities/{id}/benefits` | Published benefit rules of a university | Public |
| `GET` | `/api/v1/universities/{id}/programs` | University programs | Public |
| `GET` | `/api/v1/olympiads?search=&include_archived=` | Olympiad catalog | Public |
| `GET` | `/api/v1/olympiads/{id}` | Olympiad page | Public |
| `GET` | `/api/v1/olympiads/{id}/source` | Where the olympiad data came from | Public |
| `GET` | `/api/v1/olympiads/{id}/seasons?include_archived=&profiles=` | Seasons and profiles of an olympiad | Public |
| `GET` | `/api/v1/olympiads/{id}/universities` | Universities with published rules for this olympiad | Public |
| `GET` | `/api/v1/benefits?search=&benefit_type=&university_id=&olympiad_id=&season_id=&profile_id=&level=&limit=&offset=` | Benefit catalog with filters and `total` | Public |
| `GET` | `/api/v1/benefits/{id}` | One published benefit rule | Public |
| `GET` | `/api/v1/benefits/olympiad/{id}` | Published rules for an olympiad | Public |
| `GET` | `/api/v1/search?q=` | Search both catalogs | Public |

## Catalog management

| Method | Path | Description | Access |
|--------|------|-------------|--------|
| `POST` | `/api/v1/universities/add_university` | Create a university | `ADMIN` |
| `POST` | `/api/v1/universities/edit_university/{id}` | Update a university | `ADMIN` |
| `POST` | `/api/v1/olympiads/add_olympiad` | Create an olympiad manually | `ADMIN` |
| `POST` | `/api/v1/olympiads/edit_olympiad/{id}` | Update an olympiad | `ADMIN` |
| `POST` | `/api/v1/olympiads/{id}/seasons` | Create a season | `ADMIN` |
| `PUT` | `/api/v1/seasons/{id}` | Update a season (requires `version`) | `ADMIN` |
| `POST` | `/api/v1/seasons/{id}/profiles` | Create a profile with an RSOSH level | `ADMIN` |
| `PUT` | `/api/v1/profiles/{id}` | Update a profile | `ADMIN` |
| `POST` | `/api/v1/admin/archive_olympiad/{id}` | Archive or restore an olympiad | `ADMIN` |
| `GET` | `/api/v1/admin/users` | Manage users and roles | `ADMIN` |
| `POST` | `/api/v1/admin/role/{user_id}` | Change role and university binding in one request | `ADMIN` |

## Benefit rules

| Method | Path | Description | Access |
|--------|------|-------------|--------|
| `POST` | `/api/v1/universities/{id}/benefits` | Create a benefit rule of own university | `EDITOR` (own university) or `ADMIN` |
| `PUT` / `PATCH` | `/api/v1/benefits/{id}` | Update a rule (requires `version`) | `EDITOR` (own university) or `ADMIN` |
| `POST` | `/api/v1/benefits/{id}/rollback` | Restore a version atomically | `EDITOR` (own university) or `ADMIN` |
| `POST` | `/api/v1/benefits/{id}/verify` | Verify a rule against a university order | `ADMIN` |
| `POST` | `/api/v1/benefits/{id}/reject` | Reject a rule with a required reason | `ADMIN` |
| `GET` | `/api/v1/admin/benefits` | Benefit rule moderation queue | `ADMIN` |

## Documents and imports

| Method | Path | Description | Access |
|--------|------|-------------|--------|
| `POST` | `/api/v1/docs/upload` | Upload a source document (`RSOSH_LIST`, `UNIVERSITY_ORDER`, `OTHER`) | `ADMIN` |
| `POST` | `/api/v1/imports/rsosh` | Start an RSOSH import | `ADMIN` |
| `GET` | `/api/v1/imports` | List of import runs | `ADMIN` |
| `GET` | `/api/v1/imports/{id}` | Import state and summary | `ADMIN` |
| `GET` | `/api/v1/imports/{id}/preview` | Import preview (candidates) | `ADMIN` |
| `POST` | `/api/v1/imports/{id}/confirm` | Apply the import (`skip`, `archive_missing`) | `ADMIN` |
| `POST` | `/api/v1/imports/{id}/reject` | Reject the import results | `ADMIN` |
| `POST` | `/api/v1/imports/{id}/pause` | Pause a running import | `ADMIN` |
| `POST` | `/api/v1/imports/{id}/resume` | Resume a paused import | `ADMIN` |
| `PUT` | `/api/v1/imports/{id}/selection` | Save the administrator's review choices | `ADMIN` |
| `GET` | `/api/v1/imports/{id}/plan` | Official list import plan (nothing written yet) | `ADMIN` |
| `PATCH` | `/api/v1/imports/{id}/plan` | Correct matches, names, levels or actions in the plan | `ADMIN` |
| `POST` | `/api/v1/imports/{id}/apply` | Apply the approved plan atomically | `ADMIN` |
| `GET` | `/api/v1/imports/{id}/history` | What the document changed in the catalog | `ADMIN` |
| `GET` | `/api/v1/imports/{id}/table` | Paged view of the generated list/summary table | `ADMIN` |
| `GET` | `/api/v1/admin/docs` | Document list (`search`, `type`, `status`, `limit`, `offset`, `total`) | `ADMIN` |
| `GET` | `/api/v1/admin/imports` | Import run journal | `ADMIN` |
| `GET` | `/api/v1/admin/imports/{id}` | One import run with per-row records | `ADMIN` |

## Requests and applications

| Method | Path | Description | Access |
|--------|------|-------------|--------|
| `GET` | `/api/v1/universities/{id}/entity-requests` | Own requests for missing catalog entities | `EDITOR` (own university) or `ADMIN` |
| `POST` | `/api/v1/universities/{id}/entity-requests` | Request a missing olympiad, season or profile | `EDITOR` (own university) or `ADMIN` |
| `GET` | `/api/v1/admin/admin-applications` | Applications for administrator access | `ADMIN` |
| `GET` | `/api/v1/admin/entity-requests` | Requests for missing entities (`status`, `limit`, `offset`, `total`) | `ADMIN` |
| `POST` | `/api/v1/admin/entity-requests/{id}/approve` | Approve a request and create the entity once | `ADMIN` |
| `POST` | `/api/v1/admin/entity-requests/{id}/reject` | Reject a request with a required reason | `ADMIN` |
| `POST` | `/api/v1/representative-applications` | Apply to represent a university | Authenticated |
| `GET` | `/api/v1/applications/my` | Own representative applications | Authenticated |

## Authentication and service routes

| Method | Path | Description | Access |
|--------|------|-------------|--------|
| `POST` | `/api/v1/auth/register` | Register a user | Public |
| `POST` | `/api/v1/auth/login` | Log in and set JWT cookies | Public |
| `POST` | `/api/v1/auth/logout` | Log out and remove JWT cookies | Authenticated |
| `POST` | `/api/v1/auth/refresh` | Refresh the access token | Authenticated |
| `GET` | `/api/v1/health` | Liveness probe | Public |
| `GET` | `/api/v1/ready` | Readiness probe (PostgreSQL and Redis) | Public |
| `GET` | `/api/v1/admin/audit` | Audit log (`entity_type`, `entity_id`, `action`, `limit`, `offset`, `total`) | `ADMIN` |

## API behaviour

- unknown paths under `/api/v1/` return a JSON 404 instead of the SPA HTML
  shell;
- errors use a single JSON shape, `{"detail": ...}`, without leaking internal
  details;
- versions are optimistic: a stale `version` on update or rollback returns `409`.

See also: [roles and permissions](roles-and-permissions.md) ·
[RSOSH document import](rsosh-import.md).

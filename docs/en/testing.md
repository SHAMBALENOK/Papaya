# Tests

[← Documentation](README.md) · [Project README](../../English.md) · [Русская версия](../testing.md)

Tests run in an isolated container of the `testing` profile and never touch the
working database: a separate `papaya_test` database is created, migrations are
applied, Redis is flushed, and the catalogs are emptied before every test, so
tests do not depend on execution order.

```bash
docker compose --profile testing run --rm test
```

A subset of tests:

```bash
docker compose --profile testing run --rm --entrypoint sh test -c \
  "pip install --no-cache-dir -q -r /app/requirements-dev.txt && pytest -q tests/test_rsosh_import.py"
```

## Coverage

| File | Scenarios |
|------|-----------|
| `tests/test_auth.py` | registration, login, logout, cookie flags, passwords |
| `tests/test_security_hardening.py` | security headers, JWT placeholder rejection, loopback ports, application self-checks and administrator role protection |
| `tests/test_health.py` | liveness, readiness, JSON 404 for non-API paths |
| `tests/test_catalog.py` | public catalogs, search, duplicates, archive, unified search |
| `tests/test_mvp.py` | canonical model: seasons, profiles with RSOSH levels, benefit rules, BVI as a benefit type, EGE requirements, university documents |
| `tests/test_invariants.py` | model invariants: uniqueness, referential integrity, absence of legacy entities |
| `tests/test_catalog_integrity.py` | races, row locks, versions and rollback, integrity on import errors |
| `tests/test_durability.py` | "never delete", atomic archiving, preserving rules during import |
| `tests/test_roles.py` | role boundaries: student / representative / administrator |
| `tests/test_rsosh_import.py` | XLSX, PDF with a text layer, scanned PDF, 90/180/270 rotations, PNG/JPEG, multi-line and merged cells, repeated import, archiving, errors, permissions |

See also: [getting started](getting-started.md) · [RSOSH import](rsosh-import.md).

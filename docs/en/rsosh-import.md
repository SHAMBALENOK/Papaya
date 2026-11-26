# RSOSH document import

[← Documentation](README.md) · [Project README](../../English.md) · [Русская версия](../rsosh-import.md)

An olympiad enters the catalog in exactly two ways:

1. **Import of an official RSOSH document** — the primary path;
2. **Manual creation by an administrator** — the fallback.

The old bulk table import (`POST /api/v1/events/add_events_via_tables`) is gone:
no route, no code, no button in the interface.

## Pipeline

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

- **XLSX** is read natively (openpyxl): multi-line cells, vertically merged
  ranges, several sheets;
- **PDF with a text layer** is parsed from the document structure (pdfplumber) —
  no needless OCR;
- **scans without a text layer** are rasterized (300 dpi) and recognized by
  Tesseract (`rus+eng`) with word coordinates;
- **rotated pages** (90/180/270) are detected through Tesseract OSD, with a
  trial-OCR comparison as a fallback;
- **skewed scans** are straightened by the estimated skew angle;
- **tables spanning several pages** are joined, repeated headers are dropped,
  and the first page's header defines the columns for all following pages;
- **mirrored headers** (a quirk of some RSOSH documents) are recognized and
  un-reversed;
- **boilerplate rows** (letterheads, order details, signatures) never reach the
  catalog;
- **an empty or unreadable document** is never imported silently: the run ends
  in `failed` with a readable reason.

## Run state

Import state lives in `docs.metadata['rsosh']` (`processing` / `paused` /
`review` / `approved` / `rejected` / `failed`) — a separate table for runs is
unnecessary because a run always belongs to a concrete document.

While a run is `processing` the section carries a `progress` stage (`starting` /
`extracting` / `matching`), so the panel shows what is happening instead of a
bare "processing". An administrator can pause a run and resume it later: pausing
takes effect at a stage boundary, and when it lands after recognition the run
keeps the recognized rows, so resuming continues straight to matching without
re-reading the document. The administrator's review choices (confirmed/dropped
candidates, renamed names and descriptions, forced merges) are saved with the
run, survive a page reload, and are applied on confirmation when the request
body is omitted.

Imports run in a Celery task by default (`python -m app.rsosh.worker_run
<doc_id>`) and fall back to in-process execution when the broker is unavailable
(`RSOSH_EXECUTION=auto|celery|inline`).

## Official list: table → plan → apply

A scan recognized as an official RSOSH list (table detected and the academic year
read from the document) goes through its own pipeline; every other document keeps
the legacy `preview` + `confirm` path. The mode is visible as
`mode: "official_list"` in the import state.

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

- **The table exists before matching.** The XLSX is an intermediate artifact, not
  a report: the plan is built from it. Sheet 1 is the list, sheet 2 is the
  summary aggregated from sheet 1.
- **The season comes from the document**, not from the year the import was
  started. Profiles and levels belong to the season, so an olympiad is never
  duplicated across seasons; a level change is recorded in history.
- **Fuzzy matches are never applied automatically.** Only an exact
  normalized-name match becomes `use`; similar entries produce `review` and
  require an explicit administrator decision.
- **Unreadable rows are errors, not silence.** A row whose profile or level could
  not be recognized blocks `apply` until the administrator fills it in or
  explicitly skips it (`action: "skip"`).
- **Missing olympiads are not deleted.** Absence is recorded only for a complete
  list (`complete=true`, a season, no unresolved errors, `missing_allowed=true`)
  and only on request (`mark_missing=true`): profiles lose their level and
  olympiads are archived with the `RSOSH_ABSENT` reason.
- **Re-importing the same document creates nothing twice.** The generated table
  and HTML are reused; the plan is rebuilt; a second apply returns `409`.
- **Apply is atomic.** One transaction under the list-application lock; an error
  rolls everything back, so a partially applied list cannot exist.

The documents page shows the source PDF, the generated XLSX, the HTML table, the
season, the date, the status and the author. The table itself is paged on the
server (`GET …/table` with `sheet`, `offset`, `limit`, `search`): a list has 300+
rows.

## Import API

| Route | Purpose |
|-------|---------|
| `POST /api/v1/docs/upload` | upload a source document (`RSOSH_LIST`, `UNIVERSITY_ORDER`, `OTHER`) |
| `POST /api/v1/imports/rsosh` | start an RSOSH import |
| `GET /api/v1/imports` | list of import runs |
| `GET /api/v1/imports/{id}` | run state, summary and warnings |
| `GET /api/v1/imports/{id}/preview` | candidates: what will be created, updated or needs review |
| `POST /api/v1/imports/{id}/confirm` | apply the import (`skip`, `archive_missing`) |
| `POST /api/v1/imports/{id}/reject` | reject the results without writing anything |
| `POST /api/v1/imports/{id}/pause` | pause a running import |
| `POST /api/v1/imports/{id}/resume` | resume a paused import |
| `PUT /api/v1/imports/{id}/selection` | save the administrator's review choices |
| `GET /api/v1/imports/{id}/plan` | official list import plan (nothing written yet) |
| `PATCH /api/v1/imports/{id}/plan` | correct matches, names, levels or actions |
| `POST /api/v1/imports/{id}/apply` | apply the approved plan atomically |
| `GET /api/v1/imports/{id}/history` | what the document changed in the catalog |
| `GET /api/v1/imports/{id}/table` | paged view of the generated list/summary table |

See also: [data model](data-model.md) · [API](api.md) ·
[architecture](architecture.md).

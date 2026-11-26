# Data model

[← Documentation](README.md) · [Project README](../../English.md) · [Русская версия](../data-model.md)

```text
Olympiad ── Season ── Profile (RSOSH level 1/2/3 or null)
    │            │                 │
    └──────── Benefit rule ────────┘
                   │
          University order (doc)
```

| Table | What it stores |
|-------|----------------|
| `users` | Profile, role (`USER` / `EDITOR` / `ADMIN`), a representative's university binding (`university_id`) and the `isActive` flag: a blocked administrator does not count as an administrator. |
| `universities` | University: full name, short name, description, official website, two images (`preview_image` for cards and `image` for the page), and a normalized name that protects against duplicates. |
| `olympiads` | Olympiad: name, description, official website, two images, organizer, publication status (`PUBLISHED` / `ARCHIVED`), archive reason (`RSOSH_ABSENT` / `MANUAL`), source document. The olympiad itself has no RSOSH level. |
| `olympiad_seasons` | Olympiad season: `season_label` and a version. There are no registration or event dates and no availability flag. An archived season keeps its profiles and rules. |
| `season_profiles` | Season profile: name and RSOSH level (`1` / `2` / `3` / `null`). The level belongs to a concrete profile of a concrete season and is never transferred to another season. |
| `benefit_rules` | Benefit rule: university, olympiad, season, profile, benefit type (`BVI` / `EGE_100` / `DVI_100` / `OTHER`), required result (`WINNER` / `PRIZE` / `WINNER_OR_PRIZE`), supporting document, verification status, publication and version. |
| `benefit_ege_requirements` | Optional EGE requirement of a rule: subject and minimum score. A separate structure, not a profile field. |
| `university_programs` | University degree programs — an independent reference. It is not linked to benefit rules. |
| `entity_requests` | A representative's request for a missing olympiad, season or profile: type, name, parent entity, status and rejection reason. |
| `docs` | Document: `RSOSH_LIST` (a list tied to an import) or `UNIVERSITY_ORDER` / `OTHER` (a university document supporting a rule). File, name, checksum, processing state and `metadata['rsosh']` with the run state. |

## Key decisions

- **An olympiad is a single canonical entity.** There are no "olympiad 2026" and
  "olympiad 2027" records: one entry per olympiad, independent of the year. The
  year lives in a season.
- **A season is an olympiad plus a label.** It has no registration or event
  dates and no `availability`: those describe a university's admission campaign,
  not the olympiad.
- **RSOSH level belongs to a profile of a season.** Only `1`, `2` or `3` (or
  nothing) is valid, and a level is never copied to another season: the set of
  profiles and their levels change every year.
- **A benefit rule is the only place where a benefit is stated.** It references
  a university, an olympiad, a season and a profile, names the benefit type
  (`BVI`, `EGE_100`, `DVI_100`, `OTHER`) and the required result (`WINNER`,
  `PRIZE`, `WINNER_OR_PRIZE`), and points at a supporting university document.
  Admission without entrance exams is just `benefit_type: "BVI"`; there is no
  separate BVI entity, request or moderation queue.
- **EGE requirement is a separate optional structure.**
  `{"subject", "min_score"}` is attached to the rule, not to the olympiad
  profile.
- **A rule is consistent by construction.** The season must belong to the
  olympiad, the profile to the season, and the document to the same university;
  otherwise the API returns `422`. Archived olympiads accept no new rules, but
  existing rules stay readable and editable.
- **Archive, never delete.** An olympiad carries history: benefit rules, its
  source document, its path through the RSOSH lists. There is no physical
  deletion of catalog records anywhere in the system — neither in the data layer
  nor in the API.
- **An archive has a reason.** The status is one, but two different mechanisms
  decide it, so an archived record always carries `archive_reason`:
  `RSOSH_ABSENT` (not in the RSOSH list — an import brings it back) or `MANUAL`
  (excluded by an administrator — restorable by hand).
- **A skipped row is not a missing one.** If an administrator removed a row in
  the preview, it does not count as missing from the list: a single recognition
  error must not archive a real olympiad.
- **Two images per entity.** `preview_image` is used in catalog cards, `image`
  on the entity page; if one is missing, the interface falls back to the other.
- **Two kinds of documents.** An RSOSH list (`RSOSH_LIST`) is the import source;
  a university order (`UNIVERSITY_ORDER`) or other document (`OTHER`) belongs to
  a university and supports its benefit rules. There is no separate "Source"
  entity. The olympiad keeps `source_doc_id`, so its origin is visible. The link
  to the original is a single `docs.source_url` field, not duplicated
  `source_url` columns in different tables.
- **The public model is minimal.** An olympiad response carries only user-facing
  fields (`id`, `name`, `description`, `official_url`, `preview_image`, `image`,
  `organizer`, `status`). Internal `name_norm`, `source_doc_id`, `createdAt`,
  `updatedAt` and `archive_reason` never reach a visitor.
- **The short name comes first.** Cards, catalogs and page headings show the
  short name (`MIPT`) first and the full name underneath. The full name is never
  hidden.
- **There is no separate "organization" entity.** The organizer is free text:
  the wording differs between lists, and a reference table would lose data.

MVP boundaries and the reasoning behind the model are in [MVP.md](../MVP.md)
(Russian).

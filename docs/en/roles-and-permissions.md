# Roles and permissions

[← Documentation](README.md) · [Project README](../../English.md) · [Русская версия](../roles-and-permissions.md)

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

The rules live in one place, `app/core/deps.py`, including the object-level check
"is this your own university", which is required both on writes and on reads.

## Role invariant

A representative is "a role plus a university binding", not a separate flag.
`EDITOR` without `university_id` is therefore impossible — both the application
and the database reject it (`ck_users_representative_needs_university`,
migration `0006`).

Role and binding change together through **one** endpoint,
`POST /api/v1/admin/role/{user_id}`: a regular user cannot be bound to a
university just like that, while an administrator may keep a binding so that
demoting them returns a representative rather than a plain user. There is no
separate "bind a university" route: two ways to grant rights means one of them
bypasses the checks.

The last active administrator cannot be banned or demoted (`409`), because
nobody would be able to sign in to the panel. With a second administrator,
demotion is allowed.

The check is atomic: it runs under a lock on the administrator rows
(`SELECT ... FOR UPDATE` in `id` order) inside the same transaction as the
operation itself. Without it, two parallel operations (demote the first admin,
ban the second) would each see "someone else remains" and together leave the
system without a single active `ADMIN`.

## Benefit rules

A representative creates and edits rules of their own university and may publish
or hide them, but a rule is always created `unverified`. Only an administrator
can `verify` it (the rule must have a `UNIVERSITY_ORDER` document of the same
university) or `reject` it with a non-empty reason, which also unpublishes the
rule.

Public catalog: a rule is visible when it is published and not rejected. An
unverified rule remains visible with an honest "Not verified by Papaya" warning;
a draft or rejected rule is not visible even by direct id.

Versions are optimistic: every update and rollback sends the current `version`,
and a stale value returns `409`. A rollback is atomic under `FOR UPDATE`, accepts
both the target and the expected current version, creates a new version, marks
the rule `unverified` and records the change in the status history. Seasons and
programs are protected the same way.

See also: [data model](data-model.md) · [API](api.md) ·
[RSOSH import](rsosh-import.md).

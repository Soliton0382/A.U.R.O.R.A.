# Multi-user — design and building site

Request of the owner (2026-10-02): single-user or multi-user chosen at install, changeable later. Single-user is
the admin alone; going back from multi to single leaves only the admin. Switching moves the databases cleanly,
**no scattered traces**. TOTP MFA on by default (Google / Microsoft Authenticator), a ceiling of users from the
performance check, the admin keeps the important settings and creates users, users set their basic things.

## The principle: one layout, two modes

The two modes do not have two data layouts to convert back and forth. There is **one** layout where every
personal datum lives under its user; single-user is the same layout with the admin alone.

| Switch | What happens |
|---|---|
| install (single or multi) | the admin is created; in multi the login page asks for name, password and code |
| single → multi | nothing moves: the login opens to the users the admin creates |
| multi → single | every user except the admin is **purged** (their folder, their rows, their devices, their trace lines, their push subscriptions); the purge is listed before it is done, and checked after (nothing with their id left) |
| upgrade from today's Aurora | **once**: today's personal data moves under the admin (migration `users_layout_1`, dry-run first, after a backup) |

Why not two layouts: a conversion multi → single would have to merge or drop data that someone wrote, and every
conversion is a chance of leftovers. With one layout the switch is "add a user" or "purge a user", and the purge
is the same operation that removes a single user in multi mode: one code path, tested once.

## Data map (measured on this installation, 2026-10-02)

| Data | Today | Whose | In the new layout |
|---|---|---|---|
| knowledge vault + index (2.7 GB + 1.2 GB) | `vault/knowledge`, `vault/index/knowledge` | shared | unchanged |
| memory: conversations, reflections (4.3 MB) | `vault/memory`, `vault/index/memory` | personal | `vault/memory/<uid>/`, `vault/index/memory/<uid>/` |
| uploads, documents (PDF), projects, notes, pictures | `AURORA_*_DIR` | personal | `<dir>/<uid>/` |
| routines, approvals, push subscriptions | `status/*.json` | personal | one file per user under `status/users/<uid>/` |
| devices | `status/devices.json` | personal | same file, every device with its `user` |
| trace of runs (questions, answers) | `logs/trace/*.jsonl` | personal | every event with `user`; the purge rewrites the files without the user's lines |
| settings, plugins, models, forge, incidents, backup, harvest | `.env`, `status/` | admin | unchanged |
| users | — | admin | `status/users.db` (`sys_users`, schema versioned) |

Backups: an encrypted backup already made keeps the purged user until it expires by retention. Said in the
purge listing, not hidden.

## Roles

| | admin | user |
|---|---|---|
| chat, own memory, own files, own projects, own routines | ✅ | ✅ |
| basic preferences (language, voice, theme, notifications) | ✅ | ✅ (own) |
| settings, models, plugins install, forge, backup, security, incidents, users | ✅ | ❌ |
| plugins with `external` or `code_change` effects (Facebook, …) | ✅ | ❌ unless the admin grants it |
| read another user's conversations | ❌ | ❌ |

## Login

- single-user: as today (API key once, then the device cookie).
- multi-user: name + password + 6-digit TOTP code → device cookie bound to the user. TOTP on by default
  (`AURORA_USERS_MFA=true`); a code is never accepted twice; the failed-login lock already in the API applies.
- The API key stays the admin's, for third-party clients. Personal keys for users: a later phase.

## Ceiling of users

From a measurement, not a guess (law 2): concurrent questions the LLM serves with an acceptable time to the
first word (`--parallel` slots of llama.cpp, VRAM per slot, M-number of a load test). **Not measured yet**:
phase U4.

## Plan (each phase closed with tests and a measure; one phase at a time)

### U0 — Decisions of the owner (before U3)
Answers to the open questions below; the default if no answer: dreams and reflections per user, private; the
library shared (what a user uploads to the knowledge is seen by everyone, as today); personal files private.

### U1 — Users store ✅ done (2026-10-02)
`sys_users.py`: SQLite `users.db` (600, schema versioned), one admin, scrypt passwords, TOTP RFC 6238 (±30 s,
a code never twice). Tests: `test_users.py` (RFC vectors, replay, one admin never removed). Not wired yet.

### U2 — Mode, migration, purge (the clean switch)
| Task | Where |
|---|---|
| settings `AURORA_USER_MODE` (single/multi), `AURORA_USERS_MFA` (true), `AURORA_USERS_MAX` (from U4) | settings_schema.json |
| `sys_users_layout.py`: where every personal datum of a user lives (one function per area: memory, index, uploads, documents, projects, notes, pictures, routines, approvals, push, devices, trace) | new module |
| migration `users_layout_1`: today's data → under the admin; `--dry-run` lists every move with sizes; a backup is required and checked first; a check after (counts before = counts after, the index finds the same sids) | `script/sys_users_migrate.py` |
| the reverse of the migration, for a rollback only (multi was never used): back to today's layout | same script, `--rollback` |
| purge of a user: lists files, rows, trace lines, devices, subscriptions; removes them; checks 0 left with the user's id | `sys_users_layout.purge` |
| switch `single ↔ multi` from Settings (admin only): multi → single = purge of every non-admin, after the listing and a confirmation | API + `sys_users_mode` |
Tests: migration on a copied test vault (never the real one: law 5), dry-run changes nothing, purge leaves 0
traces, rollback gives back byte-identical files. Measure: time and size of the migration on a copy of this vault.

### U3 — Data scoped by user (the long phase)
| Area | Change |
|---|---|
| auth | `request.state.user` from the device (cookie) or the API key (= admin); every route gets its user |
| memory | `VaultReader`/`VaultWriter`/index of the `memory` section rooted at the user's folder; REM (consolidation, reflections, dreams) per user |
| chat, runs, activity | runs and their trace carry `user`; lists filtered by it |
| files | uploads, documents, projects, notes, pictures under the user's folder; `doc_preview.resolve` checks the owner |
| routines, approvals, push | per user; external plugins and code changes: admin only (or granted) |
| settings | admin: all; user: a small whitelist (language, voice, theme, notifications) stored per user |
Tests: a matrix "user B asks every API route for user A's things" → 403/404 everywhere (the smoke suite of the
89 routes, ROADMAP "depth" 3, becomes this). Measure: 0 crossings; single-user mode behaves as today (pool30, tests).

### U4 — Ceiling of users
Load test: 1, 2, 4, 8 concurrent questions; time to the first word and to the answer, VRAM per llama.cpp slot.
Ceiling = concurrent users with first word ≤ a threshold chosen with the owner (calculated before set: law 2).
The installer shows it and writes `AURORA_USERS_MAX`. Measure: an M-number on this machine.

### U5 — The faces
Login page (name, password, 6-digit code); TOTP enrolment with a QR code (a vendored QR library, no CDN: CSP);
Users page for the admin (create, reset password, reset TOTP, remove with the purge listing); the installer asks
single or multi; manual tests N17+ (phone and PC, two users, switching modes both ways).

### Order and size (estimated, not measured)
U2 → U3 → U4 → U5; U3 is the largest (every module with personal data). Each phase is published on its own,
signed by the owner where it touches protected files (plg_host, sys_approvals).

## Open questions for the owner

1. Dreams and reflections: per user (private), or only on the admin's memory?
2. Shared knowledge: a document a user uploads to the library is seen by everyone (today's behaviour) or only
   by them?

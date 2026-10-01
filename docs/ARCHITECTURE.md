# Aurora — Architecture (first design draft, 2026-09-29)

> Partly superseded. The ecosystem is described in `ECOSYSTEM.md`. Later
> measurements changed two points of this draft: the index is per-shard HNSW
> over fp16 vectors (M16), and the embedder choice is open between bge-m3 and
> Qwen3-Embedding-0.6B (M18).

Design rules derived from measurements on the previous installation (see "Lessons" at the end).

## 1. One source of truth

| layer | role | rebuildable? |
|---|---|---|
| **Vault** (`sys/vault/vault.db`, SQLite, WAL) | every soliton: text + metadata | no — it *is* the truth |
| **Index** (`sys/vault/index/<domain>.f16` + `<domain>.ids` + `manifest.json`) | per-domain embedding matrices | yes, always, from the vault |

There is **no separate cache file**. In the previous installation the cache duplicated vault text and
vectors, and every duplicate drifted (14,485 solitons silently excluded, 0%
alignment of `broca_states`). The in-memory index *is* the cache.

The manifest records, per domain: encoder id, dimension, row count and the
highest vault rowid indexed. A mismatch triggers an incremental update, never a
guess.

## 2. The soliton (schema version 1)

| field | type | rule |
|---|---|---|
| `sid` | str (32 hex) | `blake2b(normalize(text), digest_size=16)`. Immutable. The **only** join key. File names are never keys. |
| `text` | str | Unicode NFC, whitespace collapsed, non-empty |
| `domain` | str | must belong to `taxonomy.json` (validated on write) |
| `kind` | enum | `knowledge` · `conversation` · `reflection` |
| `consolidated` | bool | `false` = STM, `true` = LTM |
| `consolidated_at` | ISO-8601 UTC or null | set by the REM cycle |
| `title` | str | human title of the source document (never lost at ingestion) |
| `source_id` | str | e.g. `arxiv:2401.12345`, `pmc:PMC123`, `chat:<session>` |
| `chunk_index` / `chunk_count` | int | position inside the source |
| `lang` | str | `en`, `it`, ... |
| `created_at` | ISO-8601 UTC | |
| `schema_version` | int | `1` |

No vectors inside the soliton. Changing encoder = rebuild the index; the vault
is untouched. (In the previous installation the embedded `cue` was 58% of vault bytes and was read by
nothing that produced an answer.)

Harvested knowledge is written with `consolidated=true`. Chat turns are written
as STM and promoted by the REM cycle. `kind=reflection` is excluded from
knowledge retrieval by default: in the previous installation the "philosophy" domain turned out to be
276/276 files of Aurora's own diary.

## 3. Retrieval contract (to be implemented and measured before adoption)

1. Embed the query once.
2. Score inside each domain matrix: cosine, then z-score **within** the domain.
3. Activate the domains whose best z passes a threshold (plus a quota floor).
4. Per active domain: top-k, then group resonant solitons.
5. Summarize per group → per domain → one global multi-domain synthesis.

Every change to this contract must beat the baseline on the retrieval bench
(paraphrased questions, recall@48). Previous installation's baseline: **r@48 = 20.4%** (bare
question), **23.1%** (with query expansion), pool 345,350.

## 4. Core modules (first milestone)

| module | responsibility |
|---|---|
| `aurora/vault/soliton.py` | dataclass, normalization, `sid`, validation |
| `aurora/vault/writer.py` | insert/dedup, consolidation |
| `aurora/vault/reader.py` | fetch by sid, iterate by domain/kind/memory |
| `aurora/index/builder.py` | build/update per-domain matrices, manifest |
| `aurora/index/search.py` | the retrieval contract above |
| `aurora/config.py` | the only place that reads the environment |

## 5. Services

Plain `.service` units only, no `.service.d` drop-ins. Each unit carries its
full hardening block (`Restart=on-failure`, `KillMode=mixed`, timeouts,
`Nice`/`IOSchedulingClass` where relevant) and **one** `EnvironmentFile`. Units
must not set `Environment=` values that the env file also sets: in the previous installation systemd's
precedence made such drop-in values silently dead (e.g. `BROCA_KEYS`,
`AURORA_SEM_DEVICE`).

## Lessons from the previous installation (measured 2026-09-29)

- 326 `except` blocks swallowed errors → now: no bare/silent excepts, log or raise.
- A 10-module import cycle at the core → now: layered packages, no upward imports.
- Name used as join key across 4 artefacts, 3 naming generations → now: `sid`.
- 331 live config knobs → now: typed settings in `config.py`, documented defaults.
- No version control (1 tracked file) → now: git from the first commit.

# Tests

```sh
.venv/bin/python -m pytest                    # everything (~10 s)
.venv/bin/python -m pytest -k "not gpu"       # without the real models
.venv/bin/python sys/core/script/bench_retrieval.py --suite retrieval_pool108
```

Every test runs in its own temporary root with a `.env` generated from the
settings schema: tests never touch the real vault, index or logs.

| file | covers |
|---|---|
| `test_sys_config.py` | strict `.env` parsing, types and ranges, every problem reported at once, relative/absolute paths, root check, unknown keys, the real `.env` in sync with the schema |
| `test_sys_log.py` | per-component folder, size rotation with gzip and readable content, retention purge (live file never touched), trace as JSON lines |
| `test_sol_schema.py` | normalization, identity (knowledge = text, memory = event), birth state, row round trip, every validation rule |
| `test_sol_vault.py` | write/read, dedup across calls and sources, rejection, memory apart from knowledge, resumable iteration, shard rollover, recent turns, consolidation, crash repair, memory reset |
| `test_sol_index.py` | full and incremental indexing, crash leftovers cut, encoder mismatch refused, HNSW with an exactly searched tail, memory searchable, memory index dropped on reset, language-aware re-ranking |
| `test_kno_ingest.py` | chunking keeps every word within size, short tail joins, short documents kept, hard cut; markdown/html titles and text (scripts and styles removed); unsupported format; pdftotext failure reported; import writes, indexes and is idempotent by content |
| `test_agents.py` | gate by effect and settings; approvals store; agent: reads run, external actions become requests, finish; empty/truncated turns nudged and a report always written; old tool results shortened to fit the context; the report ends with the record of calls and every false claim is flagged; change detection, services to restart, rollback |
| `test_concurrency.py` | two processes writing the same 300 solitons at once: each stored once, registry consistent (20/20 runs) |
| `test_ethics.py` | signed integrity (intact, tampered, foreign signature refused); level B holds without the owner's exemption and yields to .env with it; a forged exemption is refused; level A capabilities refused |
| `test_sentinel.py` | syslog key=value parsing; port scan and deny burst raised once per hour; slow traffic outside the window raises nothing; IPS alerts; local networks |
| `test_kno_rem.py` | closed sessions become one memory each (abstentions left out), turns go long-term, open sessions wait, nothing consolidated twice |
| `test_kno_attach.py` | image detection, conversion to upright RGB JPEG within the size, domain classification accepts only knowledge domains |
| `test_sys_devices.py` | register, check, revoke; only the token hash on disk, file mode 600 |
| `test_kno_acquire.py` | arXiv Atom parsing (id without version, title whitespace, pdf link, primary category); category → domain map (exact, prefix, default) and every mapped domain is a knowledge domain |
| `test_models_gpu.py` | real encoder and re-ranker on GPU: Italian law question → Italian article (original question), English physics → English paper (translation). Skipped without two GPUs and the models |

## Benchmarks

| suite | content | baseline |
|---|---|---|
| `retrieval_pool108` | 108 Italian paraphrased questions, 3,108 chunks (the M8/M18 pool) | 2026-09-30 (M25): doc r@1 94.4, doc r@12 96.3, chunk r@1 91.7, 7.4 s per question |

## Live checks (2026-09-30, services on GPU)

| check | result |
|---|---|
| WebUI files served by aurora-api | `/`, `/static/app.css`, `/static/js/*.js`, `/static/i18n/*.json`: 200 |
| API key | 401 without key |
| import `attention.pdf` (arXiv 1706.03762) | 12 chunks written and indexed |
| question on it (IT) | 19.4 s, 1 sentence kept, 1 dropped (A8) |
| question not in the vault (RoPE) | abstained in 4.1 s |
| arXiv acquisition on it | round 1: 3 queries, 53 candidates, 3 papers imported (54 chunks), answered with 4 verified sentences; 63.6 s total |
| routing (3 messages) | "come stai?" and "cosa sai fare…?" → self, answered from measured state in 2.5 / 2.4 s; "quante teste…?" → knowledge, gate open, 20.8 s |

A benchmark result is added to `MEASUREMENTS.md` when it decides something.

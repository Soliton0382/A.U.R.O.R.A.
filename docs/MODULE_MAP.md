# Module map — who does what, who calls whom

Updated at every change that adds, removes or rewires a module. Layers only
call downward (ECOSYSTEM §1).

## Library: `sys/core/aurora/`

| module | layer | does | uses | used by |
|---|---|---|---|---|
| `sys_config.py` | system | reads `.env`, validates it against `config/settings_schema.json`, resolves paths | — | everything |
| `sys_log.py` | system | per-component logs, trace events, rotation + gzip + retention, `purge` | sys_config | everything |
| `sol_schema.py` | memory | the soliton: normalization, `sid`, validation, taxonomy | `config/taxonomy.json` | sol_vault, sol_writer, sol_reader, harvester |
| `sol_vault.py` | memory | shard layout on disk, connections, `check` / `repair` | sol_schema, sys_config | sol_writer, sol_reader |
| `sol_writer.py` | memory | add (validate, dedup, rollover), consolidate STM→LTM, reset memory | sol_vault, sys_log | harvester, REM cycle, API; bench |
| `sol_reader.py` | memory | get by sid, iterate a domain from a position, recent turns, counts | sol_vault | sol_index, sol_search |
| `sol_index.py` | memory | per-domain vectors (exact → HNSW), incremental update, crash cut, encoder guard; `IndexSet` search | sol_reader, faiss, sys_log | sol_search, harvester; bench |
| `sol_search.py` | knowledge | recall + re-ranking, passage read in its own language, group by domain | sol_index, sol_reader, an embedder, a re-ranker | API (planned); bench |
| `mdl_embedder.py` | models | the encoder (Qwen3-Embedding-0.6B), query prompt, L2-normalized fp16 vectors | sentence-transformers | sol_index, sol_search |
| `mdl_reranker.py` | models | the cross-encoder re-ranker (bge-reranker-v2-m3) | sentence-transformers | sol_search |
| `mdl_remote.py` | models | encoder and re-ranker over HTTP (aurora-models), same interface as the local ones | httpx | svc_api |
| `mdl_llm.py` | models | client of llama-server: ChatML, thinking on/off, complete and stream | httpx | kno_answer, kno_acquire |
| `txt_lang.py` | text | Italian/English detection by stop words | — | kno_answer, kno_ingest |
| `mdl_cloud.py` | models | cloud reasoners with the local interface: Anthropic API and Claude Code CLI; `make_reasoner` (rule 9 without exemption: local) | httpx, sys_ethics | kno_answer |
| `mdl_image.py` | models | Aurora paints (dreams): SDXL-Lightning in a separate process, reasoner swapped out when the GPU is short, AI disclosure on the image | img_paint, sys_disclosure | kno_rem |
| `sys_push.py` | system | Web Push (VAPID) to the owner's browsers: key pair made locally, subscriptions, which events notify (AURORA_PUSH_EVENTS), gone subscriptions dropped | pywebpush | svc_api |
| `sys_update.py` | system | updates from the git repository: check (commits, files, protected files), changelog, apply fast-forward with pip, tests and rollback | git, sys_tests, sys_ethics | svc_api, svc_rem |
| `sns_av.py` | senses | cameras and microphones of the machine: list, photo (ffmpeg/V4L2), recording (PipeWire), Whisper transcription on CPU with a filter for inventions on silence | ffmpeg, transformers | plugin senses, svc_api |
| `kno_harvest.py` | knowledge | the owner steers the harvester: arXiv ids/links parsed, command queue and status files shared by aurora-api and aurora-harvester | — | svc_api, svc_harvester |
| `txt_compress.py` | text | SSCC salience compression of what goes to a cloud reasoner, saving measured per call | numpy | kno_answer |
| `kno_answer.py` | knowledge | the answer pipeline: route (self or knowledge), translate, search, gate, extract, synthesize, verify, remember | sol_search, sol_writer, sol_index, mdl_llm | svc_api, kno_acquire |
| `kno_ingest.py` | knowledge | documents (txt, md, html, pdf) → chunks → solitons, written and indexed | sol_writer, sol_index, pdftotext | svc_api, kno_acquire |
| `kno_attach.py` | knowledge | chat attachments: images described by the reasoner (vision) as citable passages; documents imported in the domain the reasoner picks | mdl_llm, kno_ingest, Pillow | svc_api |
| `sns_clock.py` | senses | exact local time (AURORA_TIMEZONE) for every prompt; local rendering of stored timestamps | zoneinfo | kno_answer, kno_rem, svc_rem |
| `sns_weather.py` | senses | weather at home (open-meteo or openweathermap), cached, with a `condition` word | httpx | kno_answer (self state), kno_rem, svc_rem |
| `plg_host.py` | plugins | MCP client: discovers `sys/plugins/*/plugin.json`, runs each plugin as a stdio child, lists and calls tools, effect per tool, only the declared secrets | mcp | agt_loop, svc_api |
| `sys_approvals.py` | system | the approval gate: effect → automatic or owner; pending requests with preview and action (`<status>/approvals.json`) | — | agt_loop, svc_api |
| `agt_loop.py` | agents | the agent loop: Qwen tool calls, budgets, context compaction, propose_change, honest report with the record of calls | plg_host, sys_approvals, agt_change, mdl_llm | svc_api |
| `agt_change.py` | agents | apply an approved sandbox change: tests, backup, copy, live tests, rollback, restart of the affected services | sys_tests | svc_api, agt_loop |
| `sys_tests.py` | system | run the test suite (no GPU tests) on the live code or a sandbox, with Aurora's venv, never the real .env | pytest | agt_change, plugin self |
| `sys_health.py` | system | every service (systemd + real check or heartbeat), disk, GPUs → ok / warn / down with reasons | sys_metrics, httpx, curl | svc_api (/health), WebUI dot |
| `sys_ethics.py` | system | code of conduct: signed integrity of the protected files (services refuse to start otherwise), level A forbidden plugin capabilities, owner's level-B exemption | cryptography | every service, plg_host, sys_approvals, sys_disclosure, agt_change |
| `sys_disclosure.py` | compliance | EU AI Act art. 50: disclosure line on published text, machine-readable mark and label on images, header on documents | Pillow | agt_loop, kno_social, plugin projects |
| `kno_social.py` | knowledge | social platforms from plugin manifests, drafts in Aurora's voice (no links, within length, disclosed), daily statistics report with ideas | plg_host, mdl_llm | svc_api, kno_rem |
| `sec_sentinel.py` | security | firewall syslog parsing (key=value), sliding-window detector: deny bursts, port scans, IPS alerts, failed logins | — | svc_sentinel |
| `sec_incidents.py` | security | incident store, severity by rule, investigation with public network registry data and a defensive report | plg_host (netintel), mdl_llm | svc_api |
| `doc_pdf.py` | documents | Markdown → HTML (raw HTML off) → PDF with Chrome headless; AI mark in metadata and footer | markdown-it, pypdf, Chrome | plugin documents, svc_api |
| `sys_logread.py` | system | Aurora reads her logs: inventory with the last day's problems, tail of a component, a run's events from the traces, answer statistics | sys_config | kno_answer (self state), kno_rem (self-review), svc_api (/logs) |
| `sys_metrics.py` | system | CPU, RAM, GPUs for the WebUI top bar, sampled at most every 1.5 s | /proc, nvidia-smi | svc_api |
| `kno_rem.py` | memory | autonomic work: closed sessions → session memories (STM → LTM), spontaneous thoughts, dreams | mdl_llm, sol_writer, sol_index, sns_* | svc_api (started by svc_rem) |
| `sys_devices.py` | system | registered devices: token hashes in `<status>/devices.json` (600), HttpOnly cookie for the WebUI | — | svc_api |
| `kno_acquire.py` | knowledge | iterative arXiv agent: queries, re-ranked abstracts, PDF import, answer again | kno_ingest, kno_answer, arXiv API | svc_api |

## Scripts: `sys/core/script/`

| script | does | when |
|---|---|---|
| `sys_env_sync.py` | compares `.env` with the schema; writes `.env.proposed` and `.env.example` | after the schema changes |
| `bench_retrieval.py` | permanent retrieval benchmark on a fixed suite, isolated vault; results + history | after any change to encoder, index or search |
| `svc_models.py` | service aurora-models (127.0.0.1:9710): encoder + re-ranker on GPU1 | systemd |
| `svc_llm.py` | service aurora-llm (127.0.0.1:9711): launches llama-server with the `.env` values | systemd |
| `svc_api.py` | service aurora-api (127.0.0.1:9700): OpenAI API, runs + SSE events, import, acquire, settings, WebUI | systemd |
| `sys_install_services.py` | writes `sys/https/Caddyfile` (validated) and the systemd units in `sys/deploy/systemd/` | after changing ports, domain, certificates, root |
| `kno_import.py` | imports files or folders into a domain through the API | by hand |
| `svc_sentinel.py` | service aurora-sentinel: syslog receiver (UDP, allow-listed), firewall log, incidents to the API | systemd |
| `doc_plugins.py` | writes docs/PLUGINS.md from the plugin manifests | after changing a plugin |
| `sys_ethics_sign.py` | the owner signs the code of conduct: keygen, sign, exempt, check | by the owner (sudo) |
| `svc_rem.py` | service aurora-rem: decides when to consolidate, reflect (boredom, weather) and dream (night window); the work runs in aurora-api | systemd |
| `svc_harvester.py` | service aurora-harvester: newest arXiv papers of the configured categories, through the API; the owner's commands (harvest now, batch of papers) from the WebUI; waits while a migration runs | systemd |
| `dev_license_headers.py` | Apache-2.0 SPDX header on every source file (report, --apply; protected files only with --include-protected, then sign) | before a commit |
| `sys_nvidia.sh` | NVIDIA stack: check, clean-up (Ubuntu's CUDA 12.4, mismatched cuDNN, leftovers), CUDA toolkit 13 from NVIDIA with an apt pin that forbids NVIDIA's driver packages, optional driver change with Ubuntu's signed modules in one transaction, verification kernel on every GPU, llama.cpp build for the GPUs present; prints the plan, acts with --yes | owner, sudo |
| `sys_relocate.sh` | move or rename the installation: folder from AURORA_ROOT, new one asked; venv, units, exemption | owner, sudo |
| `doc_charts.py` | benchmark charts (SVG, IT/EN) for the README from the measurements | docs |
| `dev_publish.sh` | copies what .gitignore lets through to a separate repository folder, checks paths, size, secrets, the owner's personal patterns (list kept outside the repo) and the tests, then commits and pushes there | before every publication |
| `bench_image.py` | image model benchmark (load, time per image, peak VRAM at 1:1 and 16:9 ≥ 1024 px) | before choosing the image model |
| `img_paint.py` | paints one image with SDXL-Lightning and exits (all GPU memory given back) | mdl_image, never by hand during another GPU job |
| `kno_migrate_legacy.py` | one-time migration of the previous installation's chunk store (knowledge only, owner's exclusions), resumable, through the API | once |

## Configuration: `sys/core/config/`

| file | holds |
|---|---|
| `settings_schema.json` | every `.env` variable: type, range, category, IT/EN explanation, evidence, services |
| `taxonomy.json` | domains (IT/EN names); `memory: true` for conversation and reflection |
| `arxiv_domains.json` | primary arXiv category → vault domain |

## Plugins: `sys/plugins/`

| plugin | kind | tools (effect) | needs |
|---|---|---|---|
| `self` | tool | read code/logs (read); sandbox create/replace/write, run tests (write_local) | — |
| `documents` | tool | create_pdf (write_local), list_documents (read) | — |
| `projects` | tool | projects in usr/projects: scaffold (GitHub licence and .gitignore templates, README with AI disclosure), files, local commits (write_local); publish, push (external) | AURORA_GITHUB_TOKEN for publishing |
| `netintel` | tool | public network data about an IP: RDAP registry, reverse DNS, AbuseIPDB reputation (read); refuses local addresses | AbuseIPDB key (optional) |
| `web` | tool | read a public page as text, search (read); refuses local and private addresses | Brave key for search |
| `email` | connector | unread messages, read (IMAPS); send (external, TLS only) | IMAP/SMTP settings |
| `homeassistant` | connector | device states (read); services on devices (external) | URL, token |
| `mastodon` | connector | account statistics (read); post (external) | URL, token |
| `github` | connector | official GitHub MCP server v1.12.2 (`sys/runtime/github-mcp-server`, SHA-256 verified): get_/list_/search_ read, everything else external | AURORA_GITHUB_TOKEN |
| `telegram` | connector | get_me, get_updates (read); send_message (external) | AURORA_TELEGRAM_BOT_TOKEN, owner chat id |
| `facebook` | connector | page_info, list_posts (read); publish_post (external) | AURORA_FACEBOOK_PAGE_ID/TOKEN |

## Prompts: `sys/core/prompts/`

`identity.md`: who Aurora is and how she speaks; used for messages about herself, with
her state measured at that moment (vault counts, models, services, GPU memory, uptime).
Shared by every reasoner provider (ECOSYSTEM §6.3).

## WebUI: `sys/core/webui/`

Static files served by aurora-api; no build step. The page is a showcase that composes modules:

| file | role |
|---|---|
| `index.html`, `app.css` | the shell's skeleton and styles: top bar, left drawer menu, views, slots |
| `js/main.js` | the shell: login (device registration), menu, view switching, service worker |
| `js/modules.js` | the list of modules: views (menu entries) and widgets (slots) — one line per piece |
| `js/api.js`, `js/i18n.js`, `js/dom.js`, `js/bus.js` | core: calls with the device cookie, SSE, IT/EN labels, DOM helpers, the event bus between modules |
| `js/modules/chat.js` (+ `css/chat.css`) | conversation: history on load, attachments, live answers, arXiv button |
| `js/modules/trace.js` | a run's events as words and a collapsible path in Aurora's message |
| `js/modules/approvals.js`, `js/modules/plugins.js` (+ `css/agents.css`) | Repairs: pending approvals with ✔/✘, self-reviews and repair reports, decisions; plugins (state, missing tokens, tools and effects, on/off) |
| `js/modules/{diary,social,security}.js` | diary (session memories, thoughts, dreams); social (platforms, report with ideas, drafts, publish); security (incidents, registry data, reports, close) |
| `js/modules/alerts.js` (+ `css/alerts.css`) | top-bar widget: health dot (green/yellow/red, reasons on hover), pulsing bell for pending approvals, shield for open incidents |
| `js/md.js` | safe Markdown rendering (elements only) for answers, reports, diary |
| `js/restart.js` | after a settings change: popup "restart the services now?", restart and wait for the API |
| `js/modules/{import,runs,settings,status}.js` | the other views |
| `js/modules/metrics.js` (+ `css/metrics.css`) | top-bar widget: CPU, RAM, GPU VRAM live |
| `js/modules/sky.js` | background widget: Aurora's face in a circle, twinkling stars; fireflies while she thinks (`thinking` on the bus) |

Server data is always inserted as text, never as HTML.

## Services and ports (all in `.env`)

| unit | listens | notes |
|---|---|---|
| `aurora-https` | :443 HTTPS, :80 → redirect, admin 127.0.0.1:2019 | Caddy, owner's certificate in `sys/https/cert/` |
| `aurora-api` | 127.0.0.1:9700 | the only writer of vault and index |
| `aurora-models` | 127.0.0.1:9710 | GPU1 |
| `aurora-llm` | 127.0.0.1:9711 | GPU0+GPU1, tensor split |
| `aurora-rem` | — | autonomic cycle (calls the API) |
| `aurora-harvester` | — | new papers (calls the API) |
| `aurora-sentinel` | UDP AURORA_SENTINEL_BIND (default 127.0.0.1:5514) | firewall syslog, allow-listed senders |
| `aurora.target` | — | starts them all |

## Data on disk (not in git)

| path | written by | read by |
|---|---|---|
| `sys/vault/{knowledge,memory}/registry.db`, `<domain>/NNNN.db` | sol_writer | sol_reader |
| `sys/vault/index/{knowledge,memory}/<domain>/` | sol_index.Indexer | sol_index.IndexSet |
| `sys/logs/<component>/`, `sys/logs/trace/` | sys_log | owner, WebUI (planned) |
| `sys/status/bench/<suite>/` | bench_retrieval | owner |
| `sys/models/{embedder,reranker,llm,diffusion}/` | owner | mdl_* |

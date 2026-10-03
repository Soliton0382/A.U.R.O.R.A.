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
| `mdl_router.py` | models | which model does each step: providers (local, Claude Code, Anthropic, OpenAI-compatible), roles.json, MaskedLLM, Fallback to local, list of a provider's models, cloud statistics from the traces | mdl_cloud, sec_mask, httpx | kno_answer, kno_attach, svc_api |
| `sec_mask.py` | security | reversible Pseudonymizer for what leaves for the cloud: addresses, e-mails, phones, IBANs, cards (Luhn), keys, secret settings, the owner's words; placeholders put back in the answer and in a stream | sys_config | mdl_router, agt_forge |
| `txt_ical.py` | knowledge | iCalendar: events in a window, recurrences (DAILY/WEEKLY/MONTHLY/YEARLY, COUNT, UNTIL, BYDAY, EXDATE), time zones, all-day; a VEVENT for CalDAV; complex rules said, not guessed | zoneinfo | plugin calendar |
| plugin `calendar` | services | ICS links read only (secret, never shown) + one CalDAV calendar read and written (add event = external) | txt_ical | chat, agent |
| plugin `notes` | services | a Markdown folder / Obsidian vault: list, search, read, write (append only, never overwrite); no network, writes only there | AURORA_NOTES_DIR | chat, agent |
| plugin `nextcloud` | services | any WebDAV (Nextcloud, ownCloud, NAS): list, read text, upload a document (no overwrite, no delete) | — | agent |
| plugin `dropbox` | services | Dropbox API v2 with a refresh token (authorize.py once): list, search, read text, upload (mode add) | — | agent |
| plugin `discord` | social | one channel through a bot (REST v10): read, send (external, AI line, no mentions) | — | agent |
| plugin `whatsapp` | social | WhatsApp Business Cloud API, send only to the owner (text within 24 h, templates outside) | — | agent, notifications |
| plugin `twitch` | social | Helix with an app token: favourite channels live, top streams; read only | — | chat |
| `agt_react.py` | agents | a failure met by the owner (chat, approval, routine) → an immediate repair: should_react (once per kind of error / 6 h, 6 a day), the context (error, recent warnings, installed plugins), the goal | sys_logread | api/core, api/agents, api/routines |
| `doc_preview.py` + `api/preview.py` | webui | a PDF's pages as PNG for the viewer (pdfinfo, pdftoppm, 110 dpi, cached by content); resolve() admits only documents and chat files | poppler-utils | viewer.js |
| `webui/js/viewer.js` | webui | pictures, PDFs and videos opened inside the page with a Download button (never a new window: C39, C100) | dom, i18n | chat, trace, uploads |
| agent tool `create_picture` | agents | inside agt_loop: mdl_image.paint (GPU lock, swap), the picture saved with the run (chat, Files); facebook `publish_photo` posts it | mdl_image, sys_uploads | agent |
| plugin `news` | knowledge | read only, network: headlines of official RSS feeds by topic (feeds.json), title, summary, source, link; never the article | — | chat (current events), Facebook routine |
| plugin `diary` | knowledge | read only, no network: Aurora's latest dream and thoughts (vault reflections, never conversations; owner's name replaced) and what the harvester took | vault (read only) | Facebook routine |
| plugin `instagram` | social | the IG professional account linked to the Facebook page (page token): profile, posts, publishing a picture (via an unpublished page photo: IG takes JPEG from a public URL only) | facebook settings | agent |
| plugin `tiktok` | social | Content Posting API, direct post of a local video; SELF_ONLY until the app is audited; authorize.py for the one-time OAuth | TikTok app keys | agent |
| `bench_quality.py` (script) | bench | answer quality of the live system: the API answers, the vault's passages, a blind Claude judge | api, vault | the owner |
| plugin `cloud` | models | read only: which cloud providers have a key, the models of one; its card holds the keys and the masking settings | mdl_router | Models page |
| `mdl_cloud.py` | models | cloud reasoners with the local interface: Anthropic API and Claude Code CLI; `make_reasoner` (rule 9 without exemption: local) | httpx, sys_ethics | kno_answer |
| `mdl_image.py` | models | Aurora paints (dreams): SDXL-Lightning in a separate process, reasoner swapped out when the GPU is short, AI disclosure on the image; picture jobs (img_ai); `gpu_lock`, one GPU job at a time across processes | img_paint, img_ai, sys_disclosure | kno_rem, svc_api, mdl_video |
| `mdl_video.py` | models | short videos (Wan 2.2 TI2V 5B): `plan` (does a message ask to create a video? English prompt, title), `estimate_minutes` from M57, `generate` under the GPU lock with the reasoner swapped, AI label and metadata | vid_ai, mdl_image, sys_disclosure | svc_api |
| `sys_push.py` | system | Web Push (VAPID) to the owner's browsers: key pair made locally, subscriptions, which events notify (AURORA_PUSH_EVENTS), gone subscriptions dropped | pywebpush | svc_api |
| `sys_update.py` | system | updates from the git repository: check (commits, files, protected files), changelog, apply fast-forward with pip, tests and rollback | git, sys_tests, sys_ethics | svc_api, svc_rem |
| `sns_av.py` | senses | cameras and microphones of the machine: list, photo (ffmpeg/V4L2), recording (PipeWire), Whisper transcription on CPU with a filter for inventions on silence | ffmpeg, transformers | plugin senses, svc_api |
| `sys_routines.py` | system | routines: the owner's periodic checks (tool or agent), schedules in local time, notify rules, plugins' suggestions and welcome | sns_clock | svc_api (run, tick), svc_rem (tick) |
| `prj_browse.py` | projects | Projects page, read side: list, tree, files, git log, sandboxed previews under a 10-minute token | git | svc_api |
| `agt_forge.py` | agents | the capability forge: requests, a look at the data (per-kind samples with counts), plugin written, checked, tested in the cage, judged; read-only + no network installed alone, else Approvals | plg_host, sys_ethics | agt_loop, svc_api, svc_rem |
| plugin `security` | security | read only: sentinel incidents, firewall summary over a window, night report (shares sec_sentinel.is_ips) | sec_sentinel | agent, routines |
| `img_edit.py` | images | picture edits in words: intent (edit/look/other), a checked list of operations planned by the reasoner, Pillow applies them | Pillow | svc_api |
| `sys_uploads.py` | system | files attached in the chat and Aurora's edits: kept with their turn, served safely, purged with the memory | — | svc_api, svc_rem |
| `kno_video.py` | knowledge | watching a video: probe, scene changes (peak rule), moments, frames, one vision call, timestamped transcript, passages | ffmpeg, mdl_llm.see_many, sns_av | kno_attach |
| `kno_sources.py` | knowledge | the harvester's sources per domain (config/harvest_sources.json): arXiv, Normattiva (Akoma Ntoso), Europe PMC and bioRxiv/medRxiv (JATS), Wikipedia, GitHub; cursors, the owner's domain modes (off, round, until exhausted), licence per text | kno_acquire, httpx (via svc_harvester) | svc_harvester, svc_api |
| `kno_harvest.py` | knowledge | the owner steers the harvester: arXiv ids/links parsed, command queue and status files shared by aurora-api and aurora-harvester | — | svc_api, svc_harvester |
| `txt_compress.py` | text | SSCC salience compression of what goes to a cloud reasoner, saving measured per call | numpy | kno_answer |
| `kno_answer.py` | knowledge | the answer pipeline: route (self or knowledge), translate, search, gate, extract, synthesize, verify, remember | sol_search, sol_writer, sol_index, mdl_llm | svc_api, kno_acquire |
| `kno_followup.py` | knowledge | after an answer: a typed follow-up rewritten with the whole previous answer and its sources' titles, the previous sources in focus (their passages compete on the same re-ranker score); 3-4 suggested complete questions under a knowledge answer, each with its sources (C104, A22) | kno_answer, sol_reader, sol_search | kno_answer, api/runs |
| `kno_ingest.py` | knowledge | documents (txt, md, html, pdf) → chunks → solitons, written and indexed | sol_writer, sol_index, pdftotext | svc_api, kno_acquire |
| `kno_attach.py` | knowledge | chat attachments: images described by the reasoner (vision) as citable passages; documents imported in the domain the reasoner picks | mdl_llm, kno_ingest, Pillow | svc_api |
| `sns_clock.py` | senses | exact local time (AURORA_TIMEZONE) for every prompt; local rendering of stored timestamps | zoneinfo | kno_answer, kno_rem, svc_rem |
| `sns_weather.py` | senses | weather at home (open-meteo or openweathermap), cached, with a `condition` word | httpx | kno_answer (self state), kno_rem, svc_rem |
| `plg_host.py` | plugins | MCP client: discovers `sys/plugins/*/plugin.json`, runs each plugin as a stdio child, lists and calls tools, effect per tool, only the declared secrets | mcp | agt_loop, svc_api |
| `sys_approvals.py` | system | the approval gate: effect → automatic or owner; pending requests with preview and action (`<status>/approvals.json`) | — | agt_loop, svc_api |
| `agt_loop.py` | agents | the agent loop: Qwen tool calls, budgets, context compaction, propose_change, honest report with the record of calls | plg_host, sys_approvals, agt_change, mdl_llm | svc_api |
| `agt_change.py` | agents | apply an approved sandbox change: tests, backup, copy, live tests, rollback, restart of the affected services | sys_tests | svc_api, agt_loop |
| `sys_tests.py` | system | run the test suite (no GPU tests) on the live code or a sandbox, with Aurora's venv, never the real .env | pytest | agt_change, plugin self |
| `api/core.py` | api | what every part of aurora-api shares: config, activity feed and notifications, authentication (key, devices, lockout), the pipeline, one plugin host (cached tool lists), runs (one at a time), the chat's routing (tools, pictures, videos) | aurora modules | every api module |
| `api/*.py` | api | one module per area, each with its router: oai, runs, knowledge, projects, models, forge, routines, activity, documents, incidents, social, agents, access, system (order in `api/__init__.py`) | api/core | svc_api |
| `mdl_budget.py` | models | the day's tokens per cloud provider (shared file, locked), the daily ceiling for providers paid by the token, `Metered`: every local call traced with its step | sys_config, sys_log | mdl_router, mdl_cloud, api/models, sys_health |
| `sys_backup.py` | system | the owner's data to another disk: AES-256-GCM frames, blobs named by HMAC (dedup), SQLite backup API, snapshots, retention, verify, restore into an empty folder | sys_config | svc_backup, api/backup, sys_health, sys_doctor |
| `sys_bugreport.py` | system | a bug report zip: description, environment, health, settings (secrets as set/empty), logs of N hours, problems of 7 days, plugin stderr, chosen runs; one masker for all | sec_mask, sys_logread | api/bugreport |
| `sys_features.py` | system | what this installation can do: each feature with its models (all files), setting paths, switch, programs; `need` turns a missing one into a sentence with the command; installer groups with measured hardware needs; contradicting settings | sys_config, models.json, mdl_router | svc_api, kno_attach, kno_video, kno_rem, sys_health, sys_doctor |
| `sys_health.py` | system | every service (systemd + real check or heartbeat), disk, GPUs → ok / warn / down with reasons | sys_metrics, httpx, curl | svc_api (/health), WebUI dot |
| `sys_ethics.py` | system | code of conduct: signed integrity of the protected files (services refuse to start otherwise), level A forbidden plugin capabilities, owner's level-B exemption | cryptography | every service, plg_host, sys_approvals, sys_disclosure, agt_change |
| `sys_disclosure.py` | compliance | EU AI Act art. 50: disclosure line on published text, machine-readable mark and label on images, header on documents | Pillow | agt_loop, kno_social, plugin projects |
| `kno_social.py` | knowledge | social platforms from plugin manifests, drafts in Aurora's voice (no links, within length, disclosed), daily statistics report with ideas | plg_host, mdl_llm | svc_api, kno_rem |
| `sec_sentinel.py` | security | firewall syslog parsing (key=value), sliding-window detector: deny bursts, port scans, IPS alerts, failed logins | — | svc_sentinel |
| `sec_incidents.py` | security | incident store, severity by rule, investigation with public network registry data and a defensive report | plg_host (netintel), mdl_llm | svc_api |
| `doc_pdf.py` | documents | Markdown → HTML (raw HTML off) → PDF with Chrome headless; AI mark in metadata and footer | markdown-it, pypdf, Chrome | plugin documents, svc_api |
| `doc_artifact.py` | documents | artifacts: an interactive HTML page Aurora makes (agent tool create_artifact), kept with the turn; run only under /v1/preview/ with a 10-minute token, sandboxed, no network | sys_uploads | agt_loop, api/projects, api/preview |
| `sys_logread.py` | system | Aurora reads her logs: inventory with the last day's problems, tail of a component, a run's events from the traces, answer statistics | sys_config | kno_answer (self state), kno_rem (self-review), svc_api (/logs) |
| `sys_metrics.py` | system | CPU, RAM, GPUs for the WebUI top bar, sampled at most every 1.5 s | /proc, nvidia-smi | svc_api |
| `kno_rem.py` | memory | autonomic work: closed sessions → session memories (STM → LTM), spontaneous thoughts, dreams | mdl_llm, sol_writer, sol_index, sns_* | svc_api (started by svc_rem) |
| `sys_users.py` | system | users (admin, users): `<status>/users.db` (600, schema versioned), scrypt passwords, TOTP RFC 6238 with replay refused; not wired yet (docs/MULTIUSER.md, U1) | — | — |
| `sys_devices.py` | system | registered devices: token hashes in `<status>/devices.json` (600), HttpOnly cookie for the WebUI | — | svc_api |
| `kno_acquire.py` | knowledge | iterative arXiv agent: queries, re-ranked abstracts, PDF import, answer again | kno_ingest, kno_answer, arXiv API | svc_api |

## Scripts: `sys/core/script/`

| script | does | when |
|---|---|---|
| `sys_env_sync.py` | compares `.env` with the schema; writes `.env.proposed` and `.env.example` | after the schema changes |
| `bench_retrieval.py` | permanent retrieval benchmark on a fixed suite, isolated vault; results + history | after any change to encoder, index or search |
| `svc_models.py` | service aurora-models (127.0.0.1:9710): encoder + re-ranker on GPU1 | systemd |
| `svc_llm.py` | service aurora-llm (127.0.0.1:9711): launches llama-server with the `.env` values | systemd |
| `svc_api.py` | service aurora-api (127.0.0.1:9700): builds the app from the routers of `aurora/api/` (in order), the WebUI, start (vault check, plugin tools listed in the background) | systemd |
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
| `install.sh` (root) | the installer: system, packages, NVIDIA, answers, venv, profile, .env, models, llama.cpp, tests, ethics key, services, HTTPS | a new user |
| `sys_nas_mount.py` | aurora-mount (root, oneshot): checks smb://host/share/folder, writes /etc/aurora/nas.cred, one marked fstab line (copy first), mounts /mnt/aurora-nas | API on the backup plugin's Save, install.sh |
| `svc_backup.py` | aurora-backup (oneshot, timer AURORA_BACKUP_TIME): init (key + recovery code), run, list, verify, restore, failed (the unit could not start: `aurora-backup-failed`, OnFailure) | systemd timer, the owner |
| `dev_privacy_scan.py` | before a publish: the masker's terms and the firewall's devices must not be in the published folder (file:line, kind) | dev_publish.sh |
| `sys_doctor.py` | read-only check of the installation: .env and schema, code signature, features, contradicting settings, services; `--groups` for the installer | install.sh (end), the owner |
| `sys_models_fetch.py` | models from Hugging Face per `config/models.json`: pinned revisions, sizes before, SHA-256 after, resumable | install.sh |
| `sys_profile.py` | hardware profile (GPUs, VRAM, RAM) → .env values; only the reference profile is measured | install.sh |
| `bench_image.py` | image model benchmark (load, time per image, peak VRAM at 1:1 and 16:9 ≥ 1024 px) | before choosing the image model |
| `vid_ai.py` | makes one video with Wan 2.2 TI2V 5B (from words or a picture; fp8 weights, CPU offload, VAE tiling), labels the frames, encodes H.264 with metadata, exits | mdl_video, never by hand during another GPU job |
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
| `js/md.js` | Markdown to DOM (never HTML): headings, lists, code, tables, formulas drawn by KaTeX (`vendor/katex`, loaded only when a formula is there; prices like $5 stay text) |
| `js/artifact.js` | an artifact live in the answer (sandboxed frame, full screen, download) |
| `js/share.js` | ↗ Share on dreams and thoughts: the Social page with the drafts and the dream's picture |
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

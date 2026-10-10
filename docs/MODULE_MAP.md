# Module map — who does what, who calls whom

Updated at every change that adds, removes or rewires a module. Layers only
call downward (ECOSYSTEM §1).

## Library: `sys/core/aurora/`

| module | layer | does | uses | used by |
|---|---|---|---|---|
| `sys_config.py` | system | reads `.env`, validates it against `config/settings_schema.json`, resolves paths | — | everything |
| `sys_log.py` | system | per-component logs, trace events, rotation + gzip + retention by kind (firewall, trace, the rest), `purge` | sys_config | everything |
| `sol_schema.py` | memory | the soliton: normalization, `sid`, validation, taxonomy | `config/taxonomy.json` | sol_vault, sol_writer, sol_reader, harvester |
| `sol_vault.py` | memory | shard layout on disk, connections, `check` / `repair` | sol_schema, sys_config | sol_writer, sol_reader |
| `sol_writer.py` | memory | add (validate, dedup, rollover), consolidate STM→LTM, reset memory | sol_vault, sys_log | harvester, REM cycle, API; bench |
| `sol_reader.py` | memory | get by sid, iterate a domain from a position, recent turns, counts | sol_vault | sol_index, sol_search |
| `sol_index.py` | memory | per-domain vectors (exact → HNSW), incremental update, crash cut, encoder guard; `IndexSet` search | sol_reader, faiss, sys_log | sol_search, harvester; bench |
| `sol_search.py` | knowledge | recall + re-ranking, passage read in its own language, group by domain | sol_index, sol_reader, an embedder, a re-ranker | API (planned); bench |
| `mdl_embedder.py` | models | the encoder (Qwen3-Embedding-0.6B), query prompt, L2-normalized fp16 vectors | sentence-transformers | sol_index, sol_search |
| `mdl_stt.py` | speech to text (Whisper, CPU) inside aurora-models: transcribe (a voice message), segments (a video's track); loaded at the first request — never in the API's process, where faiss is (M146) | sns_av.clear_speech, transformers | svc_models /transcribe, /transcribe/segments ← sns_av |
| `mdl_reranker.py` | models | the cross-encoder re-ranker (bge-reranker-v2-m3) | sentence-transformers | sol_search |
| `mdl_remote.py` | models | encoder and re-ranker over HTTP (aurora-models), same interface as the local ones | httpx | svc_api |
| `agt_calls.py` | agents | the tool calls read from a reply in every format (Aurora's, Claude's, Llama's, both of Mistral's, bare JSON), a reply cut where it invents a result | — | agt_loop, mdl_router |
| `mdl_llm.py` | models | client of llama-server: ChatML (Qwen) or the model's own template, the agent's tools as a list there (C245), thinking on/off, complete and stream | httpx | kno_answer, kno_acquire |
| `txt_lang.py` | text | Italian/English detection by stop words | — | kno_answer, kno_ingest |
| `mdl_router.py` | models | which model does each step: providers (local, Claude Code, Anthropic, OpenAI-compatible, custom: any OpenAI-compatible address), roles.json, native tool calling (native_turns, as_text), MaskedLLM, Fallback to local, CloudBase ("local" on a machine without a local reasoner, AURORA_LLM_BACKEND=cloud), list of a provider's models, cloud statistics from the traces | mdl_cloud, sec_mask, httpx | kno_answer, kno_attach, svc_api |
| `mdl_gguf.py` | models | a GGUF's header read without loading the model (a file, or the first megabytes of a remote one): architecture, experts, context, chat template, size | struct | mdl_formats, mdl_custom, sys_model_check |
| `mdl_formats.py` | models | each model's profile: prompt (Qwen's measured ChatML or the model's own template, --jinja), how its reasoning is switched, its tool-call format, native tools; cloud abilities kept AURORA_FORMATS_CACHE_H | mdl_gguf, httpx | mdl_llm, svc_llm |
| `mdl_custom.py` | models | a local reasoner of one's own (roadmap 73): a Hugging Face repository inspected, a file checked before download (fit, profile), downloaded with SHA-256, switched to with a trial question, the one before kept | mdl_gguf, mdl_formats, mdl_modes, huggingface_hub | api/models_custom, Models page |
| `sec_mask.py` | security | reversible Pseudonymizer for what leaves for the cloud: addresses, e-mails, phones, IBANs, cards (Luhn), keys, secret settings, the owner's words; placeholders put back in the answer and in a stream | sys_config | mdl_router, agt_forge |
| `txt_ical.py` | knowledge | iCalendar: events in a window, recurrences (DAILY/WEEKLY/MONTHLY/YEARLY, COUNT, UNTIL, BYDAY, EXDATE), time zones, all-day; a VEVENT for CalDAV; complex rules said, not guessed; a VALARM's properties not the event's (C201) | zoneinfo | plugin calendar, cal_store, cal_text, cal_external |
| plugin `calendar` | services | Aurora's own calendar always (calendar_agenda, calendar_add, calendar_remind, calendar_change, calendar_delete: write_local) + the user's ICS links and CalDAV beside, read only (calendar_add_event to CalDAV = external) | cal_store, cal_text, cal_external | chat, agent |
| `cal_store.py` | life | Aurora's calendar: items (event/reminder) sealed per user (key "calendar"), wall times in AURORA_TIMEZONE, repeats through txt_ical's rule engine, one occurrence skipped; alerts due once (late up to 12 h), pending, answered (done/snooze) in <state>/calendar_fired.json | sys_seal, txt_ical, sys_users_layout | api/calendar, plugin calendar |
| `cal_text.py` | life | the calendar in words and files: when() («domani alle 9», «venerdì 18:30», «12/10 ore 15») by the code, the agenda for the chat, an alert's words, .ics out (RRULE, EXDATE, VALARM, folded) and in | cal_store, txt_ical | api/calendar, plugin calendar |
| `cal_external.py` | life | the user's other calendars read only (ICS links kept 10 min, CalDAV REPORT), named by number, never by address | txt_ical, httpx | api/calendar, plugin calendar |
| `api/calendar.py` | life | /v1/aurora/calendar (a range, Aurora's and the others'), /calendar/items (add, read, change, delete or skip one), /calendar/pending, /calendar/answer, /calendar/export.ics, /calendar/import; watch_calendar: every 30 s, each user's alerts (notification «calendar.alert») | cal_store, cal_text, cal_external, sys_push (note) | webui calendar.js, calendar_alerts.js |
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
| `api/places.py` | interface | a town by its name (Open-Meteo's geocoding, no key): coordinates and region for the weather's card | httpx | Plugins page (weather) |
| `sec_scorecard.py` | security | the autopilot's scorecard (roadmap 81): the owner's verdicts, precision, reviewed share, blind minutes from the firewall's log, «ready» after two weeks above the bar | sec_incidents | api/incidents, Security page |
| `sys_commands.py` | system | command cards (roadmap 74): what only the owner can do from a shell (an update through the installer, a signature), the command for this system (config/commands.json, or the port's own in <STATUS>/commands.json), and its check | sys_update, sys_ethics | api/knowledge, Updates page |
| `sys_update.py` | system | updates from the git repository: check (commits, files, protected files), changelog, apply fast-forward with pip, tests and rollback | git, sys_tests, sys_ethics | svc_api, svc_rem |
| `sns_av.py` | senses | cameras and microphones of the machine: list, photo (ffmpeg/V4L2), recording (PipeWire), Whisper transcription on CPU with a filter for inventions on silence | ffmpeg, transformers | plugin senses, svc_api |
| `sys_replay.py` | system | a request repeated after a lost connection is answered once: kept by its key (X-Aurora-Request) bound to the caller, the work never stopped by a caller going away | — | svc_api (middleware) |
| `sys_routine_advice.py` | system | Aurora's advice on the agents and routines: code checks (doubles, crowded minutes, failures, plugins not ready) and her daily review, each validated; apply/dismiss | sys_routines | api/routine_advice |
| `sys_routine_templates.py` | system | sets of agents and routines by use (config/routine_templates.json) and a user's own saved as a set; applied only where missing and possible | sys_routines | api/routine_advice |
| `sys_social_guard.py` | system | a post repeating one of the last 7 days is not published (same link, same opening, mostly the same words) | sys_approvals | agt_loop, api/social, kno_story_auto |
| `kno_story_auto.py` | knowledge | Aurora's videos on a schedule: topic from the science news, public sources only, made at night; published by day through the posts' gates | kno_story, sec_privacy, sys_approvals | api/routines (kind story) |
| `sys_routines.py` | system | routines: the owner's periodic checks (tool or agent), schedules in local time, notify rules, plugins' suggestions and welcome | sns_clock | svc_api (run, tick), svc_rem (tick) |
| `prj_browse.py` | projects | Projects page, read side: list, tree, files, git log, sandboxed previews under a 10-minute token | git | svc_api |
| `agt_forge.py` | agents | the capability forge: requests, a look at the data (per-kind samples with counts), plugin written, checked, tested in the cage, judged; read-only + no network installed alone, else Approvals | plg_host, sys_ethics | agt_loop, svc_api, svc_rem |
| `agt_forge_data.py` | agents | what the forge looks at before writing (moved from agt_forge): the data a need points to (peek, never .env/vault/memory/owner's files), the time window, a log's levels and kinds, the data places | sys_config | agt_forge, api/forge |
| plugin `security` | security | read only: sentinel incidents, firewall summary over a window, night report (shares sec_sentinel.is_ips) | sec_sentinel | agent, routines |
| `img_edit.py` | images | picture edits in words: intent (edit/look/other), a checked list of operations planned by the reasoner, Pillow applies them | Pillow | svc_api |
| `sys_uploads.py` | system | files attached in the chat and Aurora's edits: kept with their turn, served safely, purged with the memory | — | svc_api, svc_rem |
| `kno_video.py` | knowledge | watching a video: probe, scene changes (peak rule), moments, frames, one vision call, timestamped transcript, passages | ffmpeg, mdl_llm.see_many, sns_av | kno_attach |
| `kno_sources.py` | knowledge | the harvester's sources per domain (config/harvest_sources.json): arXiv, Normattiva (Akoma Ntoso), Europe PMC and bioRxiv/medRxiv (JATS), Wikipedia, GitHub; cursors, the owner's domain modes (off, round, until exhausted), licence per text | kno_acquire, httpx (via svc_harvester) | svc_harvester, svc_api |
| `kno_harvest.py` | knowledge | the owner steers the harvester: arXiv ids/links parsed, command queue and status files shared by aurora-api and aurora-harvester | — | svc_api, svc_harvester |
| `txt_compress.py` | text | SSCC salience compression of what goes to a cloud reasoner, saving measured per call | numpy | kno_answer |
| `kno_answer.py` | knowledge | the answer pipeline, in order: route (self or knowledge), translate, search (or kno_split), the stages, remember | kno_stages, kno_self, kno_trail, kno_split, sol_search, sol_writer, sol_index, mdl_llm | svc_api, kno_acquire |
| `kno_stages.py` | knowledge | stages 4-7 (a mixin of Pipeline): gate, extraction per domain, synthesis, verification of every sentence (paragraphs and headings kept) | kno_split (a case's rules), kno_trail, mdl_router | kno_answer |
| `kno_self.py` | knowledge | the route «self» (a mixin of Pipeline): Aurora's state measured now and her memories, for small talk and questions about her | sns_clock, sns_weather, sys_persona | kno_answer |
| `kno_trail.py` | knowledge | a run's trail, the Answer, the synapses its cited passages strengthen (hebb) | kno_synapse | kno_answer, the API, agt_loop |
| `kno_split.py` | knowledge | a case told as a story (C183): searched by its problems (short questions, 80 candidates each) and its provisions (kno_cites), the owner's same message never a source; a case's extraction and synthesis rules, the fixed «non un parere legale» note | kno_cites, sol_search | kno_answer, kno_stages |
| `kno_cites.py` | knowledge | the provisions a lawyer would read, named by the local model and fetched by their number from the vault's Normattiva passages (codes, d.lgs., d.P.R., leggi): the text, never the model's memory | sol_reader (law_it shards) | kno_split |
| `kno_read.py` | knowledge | search, read, answer from what was read: the question's kind (FACT, EXPLAIN, CASE: the «route» model), the web's snippets or pages read (a fact), the vault's passages read (an explanation), in ONE call that cites [n]; no source answers → her own memory marked ⚠️, never silence (M130) | kno_web, mdl_router | kno_think |
| `kno_web.py` | knowledge | the web for an answer: ddgs (DuckDuckGo and the other engines when one refuses, no key); a public page as text (the address checked: never the home network); the query on the subject, written by the local model and masked — never the owner's question | ddgs, sec_mask | kno_read |
| `kno_think.py` | knowledge | how much to think (AURORA_ANSWER_MODE or the chat's 🧠): vault as before; light, medium, auto take the way of the question's kind (kno_read) — a case goes deep in auto, every question in deep; then the other source; then memory ⚠️ (event «think»: asked, used, why) | kno_read, kno_split | kno_answer |
| `kno_followup.py` | knowledge | after an answer: a typed follow-up rewritten with the whole previous answer and its sources' titles, the previous sources in focus (their passages compete on the same re-ranker score); 3-4 suggested complete questions under a knowledge answer, each with its sources (C104, A22); the message the owner replies to (↩️) read as the last turn, at any age (quoted, with_quote) | kno_answer, sol_reader, sol_search | kno_answer, api/runs |
| `kno_ingest.py` | knowledge | documents (txt, md, html, pdf) → chunks → solitons, written and indexed | sol_writer, sol_index, pdftotext | svc_api, kno_acquire |
| `kno_attach.py` | knowledge | chat attachments: images described by the reasoner (vision) as citable passages; documents imported in the domain the reasoner picks | mdl_llm, kno_ingest, Pillow | svc_api |
| `sns_clock.py` | senses | exact local time (AURORA_TIMEZONE) for every prompt; local rendering of stored timestamps | zoneinfo | kno_answer, kno_rem, svc_rem |
| `sns_weather.py` | senses | weather at home (open-meteo or openweathermap), cached, with a `condition` word | httpx | kno_answer (self state), kno_rem, svc_rem |
| `plg_host.py` | plugins | MCP client: discovers `sys/plugins/*/plugin.json`, runs each plugin as a stdio child, lists and calls tools, effect per tool, only the declared secrets | mcp | agt_loop, svc_api |
| `sys_approvals.py` | system | the approval gate: effect → automatic or owner; pending requests with preview and action (`<status>/approvals.json`) | — | agt_loop, svc_api |
| `agt_loop.py` | agents | the agent loop: Qwen tool calls, budgets, context compaction, propose_change, honest report with the record of calls | plg_host, sys_approvals, agt_change, mdl_llm | svc_api |
| `agt_loop_report.py` | agents | a mixin of Agent (moved from agt_loop): the honest record — what a report may claim only if the log of calls holds it — and the context fitted to the model's window | mdl_llm | agt_loop |
| `agt_change.py` | agents | apply an approved sandbox change: tests, backup, copy, live tests, rollback, restart of the affected services | sys_tests | svc_api, agt_loop |
| `sys_tests.py` | system | run the test suite (no GPU tests) on the live code or a sandbox, with Aurora's venv, never the real .env | pytest | agt_change, plugin self |
| `api/core.py` | api | what every part of aurora-api shares: config, activity feed and notifications, authentication (key, devices, lockout), the pipeline, one plugin host (cached tool lists), runs (one at a time), the chat's routing (in core_route, re-exported) | aurora modules | every api module |
| `api/core_route.py` | api | the chat's routing, a part of core without routes (api/core_*): a connected service to the agent, pictures edited or looked at again, a video made or the GPU's job said, the search outside offered after an abstention, a shadow's answer, else the pipeline | api/core, api/agents | api/runs, api/oai (through core) |
| `api/*.py` | api | one module per area, each with its router: oai, runs, knowledge, projects, models, forge, routines, activity, documents, incidents, social, agents, access, system, backup, bugreport, preview, users, security, dj, care, diet, autonomy, synapses (order in `api/__init__.py`) | api/core | svc_api |
| `mdl_budget.py` | models | the day's tokens per cloud provider (shared file, locked), the daily ceiling for providers paid by the token, `Metered`: every local call traced with its step | sys_config, sys_log | mdl_router, mdl_cloud, api/models, sys_health |
| `sys_backup.py` | system | the owner's data to another disk: AES-256-GCM frames, blobs named by HMAC (dedup), SQLite backup API, snapshots, retention, verify, restore into an empty folder | sys_config | svc_backup, api/backup, sys_health, sys_doctor |
| `sys_backup_crypto.py` | system | the backup's key and recovery code, sub-keys, AES-256-GCM frames with the last marked (moved from sys_backup) | cryptography | sys_backup, sys_restore |
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
| `sys_users_layout.py` | system | where each user's personal data lives (`<area>/users/<uid>/`), the migration from today's layout and its rollback, the purge of a user with its check (files, trace lines, devices, record); shared data never moves | sys_users, sys_devices | script/sys_users_migrate.py |
| `sys_user_config.py` | system | each user's settings: the keys of scope user in `usr/<name>/.env`; `for_user` = the machine's values, the user's own, their usr/ folders; split/merge at the migration | sys_config, sys_users_layout | api/core (plugin hosts), api/system (settings) |
| `sys_users_mode.py` | system | single ↔ multi (AURORA_USER_MODE): multi only on the per-user layout and with the login (U5); single only after the list of users to delete and a confirmation | sys_users_layout, sys_users | api/system |
| `sys_context.py` | system | whose work: the user of the request being served (a context variable set by the API's auth); `sys_config.get()` answers with their configuration, the trace records them, threads carry them (`start`), background work acts as a user (`acting_as`) | — | api/core, sys_config, sys_log |
| `api/users.py` | api | login (password, Authenticator code, first-login QR), my account, the admin's Users page (create, reset, delete with the purge list) | sys_users, sys_users_layout, sys_devices | WebUI |
| `sys_devices.py` | system | registered devices: token hashes in `<status>/devices.json` (600), HttpOnly cookie for the WebUI | — | svc_api |
| `kno_acquire.py` | knowledge | iterative arXiv agent: queries, re-ranked abstracts, import (HTML first, kno_arxiv), answer again | kno_ingest, kno_answer, arXiv API | svc_api |
| `aud_analysis.py` | audio | audio in and out, and what a track is: its tempo, where its beats fall, its key (the DJ) | numpy | aud_dj, aud_synth |
| `aud_synth.py` | audio | the DJ's instruments drawn with numpy (kick, clap, hats, snare, bass and pad in the track's key) and the effects of a remix (sidechain, filter, saturation, riser) | aud_analysis, numpy | aud_dj |
| `aud_dj.py` | audio | the DJ: a track remixed in a style, or several tracks mixed into one set | aud_analysis, aud_synth | api/dj |
| `hlt_store.py` | health | a user's health folder, sealed: the dietitian's plans, the trainer's programmes, medical exams; documents and notes, the index | sys_seal, kno_ingest | api/care, hlt_labs, plugin health |
| `hlt_labs.py` | health | exam values over time: read by the LOCAL model from an exam, sealed, a series per test with its range, corrected by the owner; never a diagnosis | hlt_store, sys_seal | api/care, plugin health |
| `kno_acquire_more.py` | knowledge | beyond arXiv: when Aurora does not know, the search agent also asks the harvester's sources searchable by words, the re-ranker picks the best | kno_acquire, kno_sources | kno_acquire |
| `kno_arxiv.py` | knowledge | an arXiv paper's text with readable formulas: arXiv's HTML (or ar5iv's) first, the PDF only when neither has it (C135, C137) | — | kno_acquire, kno_sources, svc_harvester |
| `kno_synapse.py` | knowledge | synapses: weighted links between passages of different domains — grown at night above 0.72 (M107), spread into a question's candidates (the re-ranker chooses), strengthened when cited together (Hebb), faded when unused | numpy, sqlite3 | sol_search, kno_answer, api/synapses |
| `kno_synapse2.py` | knowledge | synapses of synapses: level-2 links from triads A↔B↔C whose ends are similar (≥ 0.60, M108), concepts (strong groups across domains) named by the local model, run every N new links | kno_synapse, numpy | api/synapses |
| `kno_dedup.py` | knowledge | one document, one copy: same title, language and words (bottom-k signature) = already in the vault, not imported again; two official ids are two documents (C150, M109) | sys_config | kno_ingest |
| `kno_study.py` | knowledge | the questions she declined, studied at night (the search agent, not remembered as a conversation), each outcome a "study" reflection, once per question | kno_acquire, kno_rem | api/routines (rem study) |
| `kno_shadow.py` | knowledge | the shadow of a verified answer: a question close enough (cosine ≥ 0.90) whose answer the old one is (re-rank ≥ 0.5) gets it at once; rechecked in the background | sys_users_layout | api/core (answer_or_acquire) |
| `script/shadow_seed.py` | knowledge | the shadow seed published with the code: questions (every config/shadow_seed_questions*.json) asked alone through the API, export of those answered alone with public sources and nothing personal, arXiv links, import, the owner's daily timer (systemd --user) |
| `plg_shadow.py` | plugins | each plugin's small cache: a read tool it declares (manifest "cache") called again with the same arguments gets the result already obtained | sys_users_layout | agt_loop |
| `net_cloudflare.py` | network | Aurora reachable from away (Cloudflare One, WARP private network): the account's state, what is missing, `apply` («Salva»: tunnel, /32 routes, split tunnel carved, local domain fallback, the tunnel's token fetched and kept 0600, aurora-tunnel started) | httpx, systemctl (polkit) | plugins/cloudflare, api/tunnel |
| `mdl_modes.py` | models | the whole as one choice: local, mixed, cloud with privacy, all cloud; every aspect checked in each, what each mode still needs (the exemption, a key, the consent, with its shell command), apply to every role and media task, the local reasoner off/on (rule 6) | mdl_router, mdl_media, sys_cloud_consent, sys_features | api/models, webui models_mode.js |
| `sys_cloud_consent.py` | security | «Tutto cloud»: the owner's consent signed with the installation's key (sudo), verified like the exemption; revoked with no shell | sys_ethics | mdl_router.private_model, mdl_modes |
| `net_https.py` | network | the Caddyfile's one writer (the service generator, the 🔒 HTTPS page, a restart of aurora-https from the WebUI): every name of the machine as one site, Caddy's root certificate at http://<name>/aurora-ca.crt for the phones, the owner's certificate checked (key, dates, names) and put back on failure, back to Caddy's authority; reload through 50-aurora.rules | sys_config, caddy, systemctl | sys_install_services, api/https, api/agents, sys_ready |
| `api/https.py` | network | 🔒 HTTPS e dispositivi (admin): status, own certificate, back to Caddy's, the other names | net_https | webui https.js |
| `api/tunnel.py` | network | the cloudflare plugin saved or switched on: `apply` in the background, told by a notification (tunnel.done/failed); off: aurora-tunnel stopped; at the API's start: up again if it should be | net_cloudflare | api/system (settings), api/agents (plugin switch), svc_api |
| `hlt_diet.py` | health | the dietitian's plan followed day by day: the week read from the text (days × meals, foods, food groups), the frequencies and free meals, rules by the LOCAL model; what was eaten, sealed; the meal proposed with its reasons, alternatives and variety hints; reminder times; the texts the chat's model reads (meal_text, plan_text: the code's date, C179) | hlt_store, sys_seal, kno_ingest | api/diet |
| `hlt_diet_read.py` | health | a dietitian's plan read out of a document's text: the week (days × meals, foods, food groups), the frequencies, the rules by the LOCAL model; no state | — | hlt_diet |
| `api/diet.py` | health | /v1/aurora/diet (the day's meals, the week), /diet/process, /diet/choice, /diet/pending; watch_diet: each minute, the meal reminder of each user who turned it on (notification «diet.meal») | hlt_diet, sys_push (note) | webui care_diet.js, diet.js |
| `webui/js/diet.js` | interface | 🍽️ a meal's card (proposed, alternatives, «scelgo questo», free meal, something else) and the chat's reminder bubbles | api/diet | care_diet.js, chat.js |
| `webui/js/modules/care_diet.js` | interface | Health → Diet: «Elabora documenti», the day ‹ › with its meals, the week's chips against the frequencies, the plan's rules, the reminders (on/off, times) | api/diet, settings | care.js |
| `webui/js/modules/calendar.js` | interface | 📅 Calendario: two weeks as a list or the month as a grid (dots on a phone, the day's list under it), ‹ Oggi ›, the other calendars beside (dashed, read only), .ics export and import | calendar_form.js, api/calendar | the menu (✨ area) |
| `webui/js/modules/calendar_form.js` | interface | an appointment or a reminder: what, day, time, end, all day, where, notes, two alerts, repeat and until; delete all or ✂️ only this time | api/calendar | calendar.js |
| `webui/js/calendar_alerts.js` | interface | the chat's bubbles of the calendar's alerts: ✅ fatto, ⏰ 10 min, ⏰ 1 h | api/calendar | chat.js |
| `hlt_doctor.py` | health | the doctors' cards: hours of the week, phone, address, booking, notes — sealed; told to the local model with today's day | sys_seal | api/care, plugins/health (health_doctors) |
| `mdl_tts.py` | models | Aurora's own voice: natural (Qwen3-TTS cloning the owner's private clip AURORA_TTS_QWEN_REF, a worker of its own: on the CPU for videos — AURORA_VIDEO_VOICE —, on the GPU for the chat only if chosen, with room and no run going) or Piper (the chat's, tuned (separate program, GPL-3, always the fallback); spoken sentences kept | mdl_image (gpu_busy) | api/voice, webui/js/voice.js, kno_story, api/core (release at a run's start) |
| `sec_netmap.py` | security | the network as the firewall sees it: read only, sealed, compared with the last look, address → name | sec_fwapi, sys_seal | api/security, plugins/security (network_map, network_changes) |
| `mdl_media.py` | models | pictures, edits, videos from a cloud provider chosen per task; masked words, a photo only with the exemption, counted | mdl_router, sec_mask, sys_ethics | mdl_image, mdl_video, api/models |
| `sys_capabilities.py` | system | what works read live: plugins, connections, abilities | plg_host, mdl_router, sec_fwapi, sys_push, sys_backup… | api/knowledge (/features) |
| `sys_ideas.py` | system | the owner's ideas to improve Aurora, moved new → considered → planned → done | — | api/bugreport |
| `kno_review.py` | knowledge | second thoughts: drives counted (curiosity, dissatisfaction, novelty, social); past knowledge answers answered again (remember=False), judged against the old one; a better one with new sources becomes a "review" reflection in the chat and replaces the shadow; review.json per user, a pause after 12 with nothing better | kno_answer, kno_shadow, kno_rem, kno_study | api/routines (rem review, rem/state drives) |
| `kno_story.py` | knowledge | narrated videos: the pipeline's answer (not remembered) → scenes (say + picture prompt) → sentences the answer does not support cut → pictures in one GPU swap (mdl_image.paint_many) → the natural voice on the CPU (Piper if missing) → ffmpeg (zoom, subtitles, AI label and metadata, classical music by the topic's mood from config/story_music.json, credited); video, pictures, script and post in pictures/stories/ | kno_answer, mdl_image, mdl_tts, sys_disclosure | api/social (social/story) |
| `webui/js/mood.js` | interface | 💗 the face of the emotion that prevails and the rows with their causes: the top bar's face and card (alerts.js: hover on the PC, tap on the phone; GET /v1/aurora/mood each minute, the REM's last measure) and the Health page | api/routines (/mood) | alerts.js, status.js |
| `webui/js/modules/social_video.js` | interface | the Social page's 🎬 section: a topic → a video (run events as steps), the videos with player, post and one «Publish» per video platform | api/social (social/story, social/stories, social/publish with video) | social.js |
| `kno_train.py` | knowledge | the shadow trained at night: random documents → general questions → answered → shadows ("train") | kno_shadow, kno_study | api/routines (rem train) |
| `sys_formats.py` | system | the versions of the data formats; a backup records them, a restore compares and migrates | — | sys_backup, script/sys_restore.py |
| `sys_reset.py` | system | factory settings (behaviour only) and Aurora as just installed (her mind moved aside, never usr/) | sys_config | api/system, script/sys_factory_reset.py |
| `sec_intel.py` | security | public lists of attackers, downloaded daily, looked up for every incident from outside | — | api/incidents, svc_rem |
| `sec_baseline.py` | security | each device's normal (countries, ports, apps, data a day) learned for days, then what is new; new devices with their maker | — | svc_sentinel |
| `sec_hostfw.py` | security | Aurora's own firewall on this machine (nftables through the root helper aurora-nft): decoys touched, login lockouts | sec_defence, sec_fwapi | api/incidents, api/core |
| `sec_fwplan.py` | security | any firewall change asked in words: the local model plans, the code checks (allowed entities, names, wide Accept, shadowed blocks) | sec_fwconf, sec_fwdocs, sec_fwwrite, mdl_llm | api/security_ciso, plugins/security (firewall_plan_request) |
| `sec_hostaudit.py` | security | Aurora's machine: what listens and who can reach it, judged | sys_config | api/security_ciso (🔥 page) |
| `plg_trash.py` | plugins | a plugin deleted into the trash and restored; «self» never deleted | sys_config | api/agents |
| `api/security_ciso.py` | api | the CISO and Firewall pages: posture, hunt, audit, changes (plan, apply, revert), documentation | sec_* | webui ciso.js, firewall.js |
| `sec_fwdocs.py` | security | the firewall's documentation (manual, API with sample requests, syslog) downloaded and indexed on this machine (SQLite FTS5), searched by the plugin | sys_config | plugins/security (firewall_docs) |
| `sec_fwconf.py` | security | the firewall's configuration read through the API (<Get>) as dicts; services' ports; a rule's fields | sec_fwapi | sec_audit, sec_fwwrite |
| `sec_audit.py` | security | the configuration judged as a security officer: findings with why and fix | sec_fwconf, sec_fwapi | plugins/security (firewall_audit, security_posture) |
| `sec_hunt.py` | security | threat hunting in the syslog: beaconing, lateral movement, ATP judged, dubious domains, admin logins and changes | sec_profile, sec_sentinel, sec_intel, sec_netmap | plugins/security (threat_hunt, security_posture) |
| `sec_fwwrite.py` | security | changes on the firewall planned, applied with approval, read back, undone (publish, unpublish, quarantine, release, harden) | sec_fwapi, sec_fwconf | plugins/security (firewall_plan_*, firewall_apply, firewall_revert) |
| `sec_playbook.py` | security | signals joined by device, scenarios, playbooks, the register of risks | sec_sentinel | plugins/security (security_posture) |
| `sec_report.py` | security | the week: score, incidents, campaigns, what is missing | sec_incidents, sec_fwapi, sec_hostfw, sec_intel, sys_backup | plugins/security, api/security |
| `kno_mood.py` | knowledge | 💗 her emotions from measurements: GPU load and thermal margin, errors, answers, questions to study, silence, weather, incidents, health → seven values 0–1 with causes; samples of how busy the machine is (6 h) for tiredness; the last measure saved per user for her prompts | sys_logread, sec_incidents, sys_users_layout | api/routines (rem/state, /mood), api/core (facts about herself), kno_rem (thoughts), kno_morning, mdl_tts, svc_rem (waits when stressed), status.js |
| `kno_morning.py` | knowledge | the good morning: the night in counts (learned, harvested, links, attacks stopped, the dream), a "morning" reflection and a notification | kno_study, kno_synapse, sec_defence, kno_rem | api/routines (rem morning) |
| `kno_docs.py` | knowledge | programming documentation as knowledge: Python's text archive, documentation repositories on GitHub (MDN JavaScript, the Rust book) | kno_sources | kno_sources |
| `plg_access.py` | plugins | which plugins the other users may use, and which stay the admin's | sys_config | api/agents, api/core |
| `plg_sandbox.py` | plugins | what a plugin process can see (protected): its own secrets only, a bubblewrap cage over the filesystem | sys_config | plg_host |
| `prj_run.py` | projects | a command in one of the user's local projects (tests, the program) in a cage of its own, no network | sys_config | agt_loop |
| `prj_reports.py` | projects | Aurora's reports on a project, one per work done on it, for the Projects page | sys_config | agt_loop, api/projects |
| `sec_privacy.py` | security | what a public text (a post, a bug report) would give away — private names read by the local model, places, contacts, ids — and the safer text proposed | sec_mask, sys_users | agt_loop, api/social, sys_bugreport |
| `sec_profile.py` | security | what the firewall really sends, read with its official documentation, and the checks Aurora proposes from it | sec_rules | api/security |
| `sec_rules.py` | security | the owner's own checks on the firewall's syslog, proposed by Aurora, switched on in Security | sys_config | api/security, sec_profile, svc_sentinel |
| `sec_fwapi.py` | security | the firewall's API (kind sophos): an address into the blocking group and out of it; never the firewall, this machine, special addresses | sys_config, httpx | api/security, sec_defence |
| `sec_defence.py` | security | autonomous defence: the source of a serious attack blocked by herself within the owner's limits (exemption, severity, never the home network nor protected addresses, a daily maximum), lifted when its time is over | sec_fwapi, sys_ethics, sys_autonomy | api/incidents, api/security |
| `sec_outbound.py` | security | what left this machine, measured: cloud calls, masked items by kind, pictures, posts, pushes, firewall actions | mdl_router, sys_push, sys_autonomy | api/security |
| `sys_autonomy.py` | system | the Autonomy panel: areas and levels read from (and written to) the settings, profiles, the ledger of what she did alone, the statistics of her proposals | sys_config, sec_defence | api/autonomy, agt_loop, api/forge, api/knowledge, api/core, sec_defence |
| `sys_persona.py` | system | who the assistant is for each user: name, character, gender | sys_config | api/users, kno_social |
| `sys_seal.py` | system | sealed files for a user's most private data (AES-256-GCM, a key per user and purpose) | cryptography | hlt_store, hlt_labs, api/care |
| `sys_soak.py` | system | the daily soak line: memory and restarts per service, logs, GPU swaps, failed routines, free disk | sys_config | svc_rem, api/activity |
| `sys_trash.py` | system | the trash: a deleted file waits AURORA_TRASH_DAYS before going for good | sys_config | api/dj, api/documents, api/knowledge, sys_uploads |

## Scripts: `sys/core/script/`

| script | does | when |
|---|---|---|
| `sys_env_sync.py` | compares `.env` with the schema; writes `.env.proposed` and `.env.example` | after the schema changes |
| `bench_forge.py` | the forge's benchmark: 8 needs on Aurora's own data, each with its answer computed by code (M89, M100) | after a change to the forge |
| `bench_honesty.py` | honesty: questions on a false premise must be corrected, controls left alone; judged by Claude (M106) | after a change to the answer prompts |
| `bench_repair.py` | the self-repair benchmark: a realistic bug in a sandbox, the symptom to the agent, fixed if the tests turn green and the change is proposed (M104) | after a change to the repair path |
| `bench_followup.py` | follow-up questions: typed and suggested, against their sources (M72, M73) | after a change to follow-ups |
| `img_ai.py` | the picture tools the image service runs (cut-out, enlargement, edit) | called by the image pipeline |
| `sys_backup_retime.py` | moves the nightly backup timer (root helper, aurora-retime) | when the owner changes the backup time |
| `sys_users_migrate.py` | to the per-user layout: plan, migrate (with a backup first), fresh for a new install | once, at the passage to users |
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
| `dev_publish.sh` | each port (Aurora_mac, Aurora_windows, kept in the mirror) built from the code with its platform tests; copies what .gitignore lets through to a separate repository folder, checks paths, size, secrets, the owner's personal patterns (list kept outside the repo) and the tests, then commits and pushes there | before every publication |
| `publish.sh` | the one command (owner, 2026-10-08): signs the code of conduct when the code changed (sudo once), dev_publish --commit --push; `--release X.Y.Z`: dev_changelog, a signed tag verified and pushed; `--check`: checks only | sys_ethics_sign, dev_publish, dev_changelog | the owner |
| `dev_changelog.py` | a version's section of CHANGELOG.md from the mirror's history since the last tag, pyproject's version; a lower or tagged version refused | git | publish.sh |
| `sys_github_mcp_install.sh` | the GitHub plugin's program: GitHub's MCP server pinned (1.12.2), SHA-256 checked, idempotent (C203) | curl, sha256sum | install.sh, the owner (repair) |
| `.github/workflows/release.yml` | on a tag v*: the tag verified against allowed_signers, the version against pyproject, the GitHub release with the CHANGELOG section | git, gh | a tag pushed |
| `.github/workflows/ports.yml` | by hand and on a tag: each port built on a real macOS / Windows runner, requirements from PyPI, platform tests, probe.py (fails the job), the Linux suite for information | Aurora_*/build.py, probe.py | Actions |
| `install.sh` (root) | the installer: system, packages, NVIDIA, answers, venv, profile, .env, models, llama.cpp, tests, ethics key, services, HTTPS | a new user |
| `sys_nas_mount.py` | aurora-mount (root, oneshot): checks smb://host/share/folder, writes /etc/aurora/nas.cred, one marked fstab line (copy first), mounts /mnt/aurora-nas | API on the backup plugin's Save, install.sh |
| `svc_backup.py` | aurora-backup (oneshot, timer AURORA_BACKUP_TIME): init (key + recovery code), run, list, verify, restore, failed (the unit could not start: `aurora-backup-failed`, OnFailure) | systemd timer, the owner |
| `dev_privacy_scan.py` | before a publish: the masker's terms and the firewall's devices must not be in the published folder (file:line, kind) | dev_publish.sh |
| `sys_doctor.py` | read-only check of the installation: .env and schema, code signature, features, contradicting settings, services; `--groups` for the installer | install.sh (end), the owner |
| `sys_models_fetch.py` | models from Hugging Face per `config/models.json`: pinned revisions, sizes before, SHA-256 after, resumable | install.sh |
| `sys_profile.py` | hardware profile (GPUs, VRAM, RAM) → .env values; no NVIDIA GPU of 16 GB (or `--cloud`): the cloud profile, encoder and re-ranker on the CPU (M151); only the reference profile is measured | install.sh |
| `sys_ready.py` | the end of an installation: the addresses, the API key, the phone's steps (also when the services are left to do by hand) | install.sh |
| `sys_cloud_setup.py` | the installer's cloud questions: a provider's own list of models (suggested first), one call through Aurora's client to prove key and model; the key by the environment only | install.sh |
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
| `cloudflare` | connector | cloudflare_status, cloudflare_check (read: tunnel, published hostnames, routes, split tunnel, fallback, aurora-tunnel); cloudflare_activate (external, approved each time) — all in net_cloudflare. State tools written by Aurora (forge, 7 Oct) | AURORA_CLOUDFLARE_ACCOUNT_ID/API_TOKEN; `sys/deploy/cloudflared/install.sh` once |

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
| `js/modules/chat_media.js` | the chat's media and Aurora's own bubbles (moved from chat.js): a phone photo made light, this device's recorder, a dream and a good morning among the turns |
| `js/modules/chat_think.js` | 🧠 how much Aurora thinks: 🧠 the setting, 🤖 auto, ⚡ light, ⚖️ medium, 🔬 deep; this device remembers it; sent with the question («think») |
| `js/modules/chat_menu.js` | the composer's menus with their words: 📎 file or photo; ⚙️ thinking, camera and microphone of this device or Aurora's PC, answers aloud, the voice |
| `js/modules/chat_actions.js` | 📋 copy under every message, ↩️ reply under Aurora's: the quote over the box, sent as reply_to (kno_followup.quoted) |
| `js/modules/trace.js` | a run's events as words and a collapsible path in Aurora's message |
| `js/modules/approvals.js`, `js/modules/plugins.js` (+ `css/agents.css`) | Repairs: pending approvals with ✔/✘, self-reviews and repair reports, decisions; plugins (state, missing tokens, tools and effects, on/off) |
| `js/modules/{diary,social,security}.js` | diary (session memories, thoughts, dreams); social (platforms, report with ideas, drafts, publish); security (incidents, registry data, reports, close) |
| `js/modules/alerts.js` (+ `css/alerts.css`) | top-bar widget: health dot (green/yellow/red, reasons on hover), pulsing bell for pending approvals, shield for open incidents |
| `js/md.js` | Markdown to DOM (never HTML): headings, lists, code, tables, formulas drawn by KaTeX (`vendor/katex`, loaded only when a formula is there; prices like $5 stay text) |
| `js/qr.js` | a QR code as SVG elements (vendor/qrcode, MIT) for the Authenticator |
| `js/modules/users.js` | 👥 Users: my account (password, Authenticator) and the admin's users |
| `js/voice.js` | answers read aloud by the device (speech synthesis, local voices only; modes per device) |
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

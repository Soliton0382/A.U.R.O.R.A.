# Status — work in progress

Updated at every validated change (last: 2026-10-02). Details: BUGS.md (issues, 1 open / 69 closed),
MANUAL_TESTS.md (what the owner checks by hand),
TESTS.md (tests and live checks), MEASUREMENTS.md (numbers), MODULE_MAP.md (who does what),
SECURITY.md (encryption, ethics, AI Act), COMPATIBILITY.md (tested stack), ECOSYSTEM.md (design and decisions).

## Working (validated)

| area | what | proof |
|---|---|---|
| vault | solitons in SQLite shards, knowledge and memory apart, dedup by content, rowids never reused, source removal, check and repair at every start, safe with concurrent writers | tests (vault, index, concurrency 20/20) |
| index | per-domain vectors, HNSW over the exact tail, incremental, drop without re-encoding | tests |
| retrieval | Qwen3-Embedding + bge re-ranker, bilingual, grouped by domain | M25: doc r@1 94.4% |
| answers | route (self/knowledge), gate, per-domain extraction, thinking, sentence verification, sources; exact time; "sì, cerca" starts the arXiv agent from any client | live |
| memory | STM turns with their path; recent turns in context and in the chat after a refresh; session memories (LTM) written by the REM and recalled by meaning when Aurora answers about herself or the past, dates labelled by the clock | tests, live |
| autonomic cycle | aurora-rem: session memories, thoughts (boredom, weather), dreams painted with SDXL-Lightning (reasoner swapped out for ~20 s, AI-marked) and shown in the chat, daily self-review from the logs with measured evidence, self-repair on recurring problems only, daily social report, log retention | tests, live |
| agents | agent loop with budgets (60 steps / 90 min), context compaction, honest report with the record of calls, `/agente <goal>` in the chat; code changes in a sandbox, tests, owner's approval, live tests, rollback | tests, live |
| plugins (12) | self, projects, netintel, web, documents, senses: active; github (official MCP server), telegram, facebook, mastodon, email, homeassistant: ready, off until their tokens are set | live listing and calls |
| approval gate | read/write_local automatic; external actions and code changes wait for the owner (Repairs page, pulsing bell) | tests, live |
| social | platform statistics, daily ideas, drafts in Aurora's voice from any answer ("Share"), publishing by the owner's click | drafts tested live; publishing needs tokens |
| projects | GitHub-ready scaffolding in usr/projects, local commits, publish/push with approval | tested in a temporary folder |
| security | aurora-sentinel: firewall syslog, detector, incidents investigated with public network data, defensive reports; Security page and shield | end-to-end test with synthetic syslog |
| ethics | code of conduct in two levels, signed integrity (services refuse to start if changed), owner's level-B exemption | tests, live tamper check |
| compliance | EU AI Act art. 50 disclosure on published text, images and documents | tests |
| senses | clock, weather (open-meteo), machine metrics, service health (green/yellow/red) | live |
| services | api, models, llm, https (443), rem, harvester, sentinel; one install.sh; polkit for restarts; clean stop in 5 s | install checks |
| harvester | arXiv rounds by category (off by default), "harvest now" and batches of papers from the 🌾 page, each paper in its category's domain | live batch test |
| updates | Updates page: mode (notify / auto / off), what a new version changes, update now; daily check by the REM, approval in Repairs, fast-forward + tests + rollback | tests with real git repositories; live once the remote exists |
| notifications | Notifications page: push on each device and toasts in the WebUI, which events on each channel (suggested / all / none / custom), effective at once | tests; live delivery depends on the browser |
| senses | plugin `senses`: camera photo described by Aurora's vision, microphone transcribed locally (Whisper on CPU); 📷 photo and 🎙️ dictation in the chat; devices chosen from a list | live (M35) |
| knowledge sources | harvester per domain (off / a round / until exhausted) from arXiv, Normattiva (Akoma Ntoso, one passage per group of articles), Europe PMC, bioRxiv/medRxiv, Wikipedia, GitHub; licence kept with every text; certificate chains completed (AIA) | M43–M44, tests |
| chat → services | a third route "tools": requests about connected services go to the agent with the plugins | M45 |
| routines | 🔁 page: plugins' suggestions, tool or agent routines by aurora-rem, notify always / if any / if new, failures recorded and notified, documents linked | M46, M52, tests |
| projects | 📁 page: local projects and GitHub repositories, clone, tree, files, history, sandboxed page preview, ask Aurora | M46 |
| weather | plugin: now, forecast, morning report, alerts on sudden changes, MeteoAlarm warnings; coordinates never logged | M46, C65 |
| security plugin | firewall incidents, traffic summary, night report (read only); the sentinel's settings from its card | M52 |
| phone | the PWA uses the phone's camera and microphone (Android, iOS formats), transcribed by the local Whisper | M47 |
| video | attached videos watched: scene changes, frames in one vision call, timestamped transcript | M48 |
| pictures | edits in words (checked operations, Pillow), look again at the latest picture; the vision gets 32-px tiles | M50, M51 |
| files | attached files kept with their turn, 📎 Files page, Aurora's documents downloadable | M49, C66, C69 |
| forge | capability requests, plugins written, tested in the cage (no network), judged; read-only installed alone, else Approvals — safe, not yet useful with the local reasoner | M53, C70 |
| WebUI | modular showcase: chat (full width, dates, path, share), repairs, security, diary, social, plugins, import, activity, status, settings; sky with orbiting fireflies; metrics with GPU load; PWA; safe Markdown | headless Chrome checks |
| videos | «fammi un video di…», «anima questa foto»: Wan 2.2 TI2V 5B, 5 s at 1280×704 (a photo keeps its shape), ~19 min with the reasoner swapped out; immediate answer with the estimate, the chat says when it will be ready, push when done or failed; AI label and metadata; GPU lock shared with dreams and edits | M57, C74 |
| news and diary | 📰 news (14 official feeds, by topic) and 📔 diary (dream, thoughts, what she learned): current events in the chat, the Facebook routine's material | M66 |
| answer quality | 30 questions, live: 6.90 (was 6.03), 22 of 30 answered; verification no longer drops right sentences; the gate stays (measured) | M66, M67 |
| your services | calendar (ICS, CalDAV), notes (Markdown/Obsidian), Nextcloud/WebDAV, Dropbox, Discord, WhatsApp, Twitch, Home Assistant connected | M67 |
| security page | closed incidents archived with one button (kept in the file: the morning report still counts them) | M65 |
| backup | to the NAS every night at 03:30: encrypted (AES-256-GCM), deduplicated, SQLite-consistent, retention 7/4/6, checked every run; first copy 30.5 GB in 4 min 48 s, the vault restored from it intact | M60, M63 |
| bug reports | 🐞 page: description, runs, hours of logs → a zip with private data masked, the list of files and of what was masked, a GitHub issue link | M60 |
| routine PDFs | an agent routine's report is always also a PDF (C84) | M60 |
| API structure | aurora-api in modules: aurora/api/core (shared) + 14 routers, entry svc_api.py 143 lines; no public API map (C79); one plugin host with cached tool lists, warmed at start (Plugins page 0.004 s, C80) | M59 |
| install | clean install validated end to end in a new folder (10 min 55 s with 81 GB of models), rerun 7 s, missing sudo handled, doctor at the end | M59, C81 |
| log rotation | handler logs rotate and compress by size; loose logs (plugins' stderr) too, in the daily purge; 12-month retention | M59 |
| features and gates | 10 features, each with what it needs; a missing model or a contradicting setting becomes an answer with the command, never a crash mid-job (live: cut-out and dictation with the model pointed away); ⚙️ Status lists them; sys_doctor checks the whole installation; the installer offers optional groups by measured hardware | M58, C75–C77 |
| models per step | 🧠 Models page: each of 12 steps on local or a cloud provider (keys in the ☁️ cloud plugin), masked by default (C72), fallback to local, statistics of calls, cost, masked items, pictures sent, SSCC | M56 |
| guide | 📖 Guide page: first steps, cloud, phone, plugins, safety, and every page of the menu with a button | — |
| logs | one file per component, rotation, gzip, 12-month retention, traces, lifecycle lines; Aurora reads them | sys_logread |
| encryption | TLS 1.3 to clients, HTTPS everywhere outwards, secrets 0600; storage not encrypted (no LUKS) | SECURITY.md |

## In progress (2026-10-02)

| what | state |
|---|---|
| forge | written and judged by Claude Code (opus): 8 of 8 built, 7 right (M64; local 4/8). Known limit: a plugin that ignored the time window of a JSON log passed the judge; read-only plugins only install alone |
| self-repair | runs daily (4 self-reviews, 2 repairs in 2 days); 0 code changes proposed so far: no evidence yet that it fixes a real bug |
| multi-user | performance check on install, admin and users, TOTP MFA |
| depth | the gate's 3 wrong closures of 30 (vague questions): a question rewritten with the conversation's context before the gate is the next idea, to measure; then multi-user |
| social | Instagram and TikTok plugins ready, waiting for the owner's accounts (Instagram professional linked to the page; TikTok developer app). Facebook connected (page token with 8 scopes; posts, statistics, comments, page info; writes wait for approval; the Messenger welcome message is not accepted by Meta's API for this page: set by hand in Business Suite); routines: a post a day proposed when there is something new, weekly statistics. LinkedIn later |
| network finding | 11,945 denied connections to port 6667 (IRC) from one internal host, 107 ATP matches: the owner checks the device |

## Owner (2026-10-02)

| what | why |
|---|---|
| sign | code changed today (the health is yellow until then): `sudo .venv/bin/python sys/core/script/sys_ethics_sign.py sign` |
| Messenger welcome message | Meta Business Suite → Inbox → Automations → Instant reply (Meta's API refuses it for this page) |

## To do (designed)

| what | depends on |
|---|---|
| move the owner's key to root-only custody (USB) | owner (SECURITY.md) |
| firewall actions (block an address) and abuse reports as approvals | Sophos API plugin |
| full-disk encryption | owner |
| re-measure answer quality (M40) after the synthesis prompt change (M48) | a run of the benchmark |

## Open bugs (0)

None. Measurements still to take are listed in ROADMAP.md ("Still to measure").


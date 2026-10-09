# Status — work in progress

Updated at every validated change (last: 2026-10-09). Details: BUGS.md (issues, 1 open / 230 closed),
MANUAL_TESTS.md (what the owner checks by hand),
TESTS.md (tests and live checks), MEASUREMENTS.md (numbers), MODULE_MAP.md (who does what),
SECURITY.md (encryption, ethics, AI Act), COMPATIBILITY.md (tested stack), ECOSYSTEM.md (design and decisions).

## Working (validated)

| area | what | proof |
|---|---|---|
| vault | solitons in SQLite shards, knowledge and memory apart, dedup by content, rowids never reused, source removal, check and repair at every start, safe with concurrent writers | tests (vault, index, concurrency 20/20) |
| index | per-domain vectors, HNSW over the exact tail, incremental, drop without re-encoding | tests |
| retrieval | Qwen3-Embedding + bge re-ranker, bilingual, grouped by domain | M25: doc r@1 94.4% |
| answers by the question's kind | the cache (shadow) first; then FACT → the web (ddgs: DuckDuckGo and other engines, no key; a masked query on the subject; snippets, the pages when needed; Italian then English), EXPLAIN → the vault's passages, CASE → the deep path (split, provisions by number, verification); one reading with its sources; no source → memory marked ⚠️; a false premise is the answer, a myth's page no evidence; a broken source never breaks the answer | M130: 35-36/50 real questions right (vault 8/50), 7.2 s mean, 3.95 s median; false premises 6/6, true 2/2; tests |
| thinking modes | vault (the pipeline before), light, medium, deep, auto (the default: starts light, the web only for the unconfirmed, deep for a case); the chat's 🧠 button for one message; the trace says the way and why | M130, tests, headless |
| answers (deep path) | route (self/knowledge), gate, per-domain extraction, thinking, sentence verification, sources; a case told as a story split in its problems and its provisions fetched by number (kno_split, kno_cites); a fixed «not legal advice» note; exact time | M128, live |
| cache and night study | a web answer cached 30 days (AURORA_SHADOW_WEB_DAYS), a vault answer kept, a memory answer never; the explanations the vault lacked (from the web or memory) studied at night with the declined questions — no «sì, cerca» | tests |
| emotions | stress, satisfaction, curiosity, tiredness, longing, melancholy, worry from measures with their causes; a face beside the health dot and its card; in the good morning, her thoughts, her words about herself; the cycle waits from stress 0.8 | M124, tests, headless |
| guided diet | «Elabora documenti» (PDF, Word: C178) → the week, the frequencies, the rules (local model); each meal proposed and re-weighed on the week and on variety; reminders (notification + chat bubble); the chat's «cosa mangio?» from the processed plan with the code's date (C179) | M126, tests, a user's real plan |
| Aurora's calendar | appointments and reminders of each user, sealed; repeats, one time skipped, summer time; alerts by notification and chat bubble (done / snooze), late up to 12 h; page 📅 Calendario (agenda, month); in the chat (calendar plugin: add, remind, agenda, change, delete — the dates the code's); .ics export and import; Google/Outlook/CalDAV beside, read only | M139, `test_calendar.py`, the crossing test (another user sees nothing) |
| access from away | plugin cloudflare (state written by Aurora's forge): «Salva» creates the tunnel, the /32 routes, WARP's split tunnel and fallback, fetches the tunnel's token, starts aurora-tunnel; own LAN address never blocked (C180) | M127, the owner's account: tunnel healthy |
| arXiv text | papers come from arXiv's HTML (or ar5iv's), formulas in LaTeX; the PDF only when neither has it — acquisition, sources and harvester (C137); 116 garbled papers re-imported | M97, 4 tests |
| concurrent users | 2 slots of the reasoner (AURORA_LLM_PARALLEL), 8 users at once all answered | M99, M102 |
| clean install | from GitHub over HTTPS, multi-user, unattended answers, 303 tests in the clone, first login with Authenticator | M103 |
| push delivery | the devices confirm each push; the rate on the Notifications page | M101 |
| autonomy | 🧭 page: 7 areas, levels read from the settings, profiles, daily line, statistics, users | tests |
| autonomous defence | auto blocks within the owner's limits, lifted by themselves, never the home network | tests (fake firewall) |
| post privacy | 🔍 private names (local model), places, contacts; 🗑️ discard; an autonomous post naming someone waits | M105, tests |
| exam values | read by the local model from the exams, sealed, a chart over time with the range | tests |
| knowledge by language | Wikipedia in the installation's language and ticked ones; programming docs (Python, MDN, Rust) | tests |
| answer shadow | a question in the shadow of a verified answer gets it written again for itself from the same passages, verified, in 6-13 s (52-62 s through the whole pipeline); at cosine ≥ 0.97 nothing more, at 0.90-0.97 rechecked in the background and a new shadow; overlapping shadows chosen by the re-ranker; said in the chat | M111, M113, tests |
| shadow seed and plugin caches | script/shadow_seed.py asks 128 questions on 32 domains to fill the shadow; --export keeps only answers with public sources (with their attribution) for new installations; each plugin's read tools cached apart | M112, tests |
| doctors' cards | ❤️ Health → ⚕️ Medico: the hours of each day, phone, address, how to book, notes, sealed; Aurora answers "a che ora riceve oggi?" from the local model | test_doctor |
| Aurora's voice | the device's own voice, or Aurora's made on her CPU (Piper) when the device has none — waits for `sys_tts_install.sh` | M114, test_tts |
| agents and routines | a grid of icons; personal agents with a goal, chosen plugins, memory of the last report, a budget; clone | test_routines |
| network map | the firewall's hosts, groups, interfaces, zones, DHCP reservations, read only and sealed; names in the incidents; what changed | M114, test_netmap |
| security page | four tabs (incidents, defence and network, checks, what went out), each loaded when opened; the network drawn | M115 |
| media providers | pictures, edits and videos: local or a cloud provider per task (Models page) | test_media; live: N86 |
| ideas | 💡 a tidy request to improve Aurora, with its state | test_ideas |
| multi-user | a user sees and changes only what is theirs (menu and API); chats private, vault and the seed's shadow shared | M116 |
| uninstall, reset, restore | uninstall.sh (keep the data / everything), factory settings in Settings, sys_factory_reset.py, sys_restore.py from the backup card with the formats checked | dry-runs, tests |
| synapses | links between domains grown at night (99 from 990 passages, 18 min), spread in the search, Hebbian, fading | M107, tests |
| firewall undo | every block (the owner's or Aurora's) undone with one click; group and rule names shown once the API is set | live (N44), tests |
| self-update | the clean clone updated itself from GitHub: 332 tests, 19.7 s | M103 bis |
| memory | STM turns with their path; recent turns in context and in the chat after a refresh; session memories (LTM) written by the REM and recalled by meaning when Aurora answers about herself or the past, dates labelled by the clock | tests, live |
| autonomic cycle | aurora-rem: session memories, thoughts (boredom, weather), dreams painted with SDXL-Lightning (reasoner swapped out for ~20 s, AI-marked) and shown in the chat, daily self-review from the logs with measured evidence, self-repair on recurring problems only, daily social report, log retention; second thoughts (kno_review): drives counted (curiosity, dissatisfaction, novelty, social), past answers answered again in AURORA_REVIEW_HOURS, a better one with new sources told in the chat (≤ AURORA_REVIEW_MESSAGES a day) and put in the shadow, paused by itself after 12 reviews with nothing better; narrated videos (kno_story): from the vault, checked, local pictures, Aurora's natural voice and free classical music by mood, cost zero, made and published from the Social page (🎬, M123: Facebook video; Instagram Reels and TikTok need the owner's connection) | tests, live (M120, M121) |
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
| harvester | rounds by domain (on by default since 9 Oct: a new Aurora starts empty; the installer asks; a host that says «slow down» is asked again and then left alone, C214), "harvest now" and batches of papers from the 🌾 page, each paper in its category's domain | live batch test |
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
| repairs at once | a failure met by the owner is diagnosed immediately (agt_react), not the next day: code defects proposed as fixes, outside causes explained; notified | M69, C101 |
| files in place | pictures, PDFs, videos open inside the page (also in the installed app), with Download | C100 |
| pictures on request | «crea una foto per Facebook»: the agent paints it (create_picture), shows it in the chat and Files, proposes the post with the picture (facebook publish_photo) | M68, C97 |
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

## Closed on 2 October 2026

Signed and published (commit d4ce54f, 29 commits, the history clean of the firewall serial); health green; 0 open bugs;
207 tests; the Messenger welcome message set by hand. The next roadmap is decided by the owner after the weekend
(ROADMAP.md, "Next roadmap").

## Done 2026-10-05 (night), to verify by the owner (N58-N61)

The agent on Claude Code works with Aurora's tools (C133); projects given as briefs, with progress alerts; the
notification history; the side menu in areas; the top bar on two rows.

## Done 2026-10-05 (evening), to verify by the owner (N53-N57)

Masking stronger and mandatory (C132); the assistant's name, character and gender per user (install, Settings, the
admin's new user with the person's name); ❤️ Health sealed per user, local model only.

## Done 2026-10-05 (later), to verify by the owner (N49-N52)

🎧 DJ (remix and mix, 8 styles, all local, M93); the login with name, password and code also in single-user once the
admin has them; Security's checks with their state and "switch on / off / delete selected". Decided by the owner and
written in ROADMAP: the autonomy panel, users as system accounts (U6), autonomous defence.

## Done 2026-10-05, to verify by the owner (N45-N48)

Log out; Social with posts to approve and history; Approvals apart from Reports; the firewall's API generic and
working (C131: login verified live). The autonomy panel is a design to decide (ROADMAP).

## Done 2026-10-04, to verify by the owner (N31-N41)

Verified by the owner: the WebUI changes (models menu, PDFs deletable, menu by plugin) and the backup timer.
Code and tests (273 green), not yet live (aurora-api restarts after the owner's signature): dictation decoded whole
and sent by itself (C121); plugins of the admin or of everyone, switching the admin's (C124); plugin settings in their
cards with checkboxes; alerts per user, the cloud ceiling and failing providers notified; the trash (30 days);
routines with several times and groups of days; projects in two tabs, Aurora's tests in a cage of her own (M85);
the NAS backup after the mount (C123).

## In progress (2026-10-03)

| what | state |
|---|---|
| forge | written and judged by Claude Code (opus): 8 of 8 built, 7 right (M64; local 4/8). Known limit: a plugin that ignored the time window of a JSON log passed the judge; read-only plugins only install alone |
| self-repair | runs daily (4 self-reviews, 2 repairs in 2 days); 0 code changes proposed so far: no evidence yet that it fixes a real bug |
| depth | follow-ups: rewritten with the conversation and the previous answer, its sources in focus, 3-4 suggested questions under each answer (C104, C106, M73: typed follow-ups right 2 → 6 of 14, suggestions 8 of 11 ≥ 7); the gate's 3 wrong closures of 30 on complete questions remain (A18) |
| multi-user | migrated and verified (M77); several users at once (per-request user, filters, REM and routines per user: crossing test M79) and the login with Authenticator code, my account, the Users page: done, live after the owner's signature; the owner switches to multi after setting his password and code (N27) |
| social | Facebook autonomous since 2026-10-03: Aurora publishes her own posts (at most 3 a day; posts and photos only; recorded as "auto", notified); 09:30 a dream or a thought, 18:30 science; Share on dreams and thoughts with the picture (N18, N19 to verify). Instagram and TikTok plugins ready, waiting for the owner's accounts (Instagram professional linked to the page; TikTok developer app). Facebook connected (page token with 8 scopes; posts, statistics, comments, page info; writes wait for approval; the Messenger welcome message is not accepted by Meta's API for this page: set by hand in Business Suite); routines: a post a day proposed when there is something new, weekly statistics. LinkedIn later |
| network finding | 11,945 denied connections to port 6667 (IRC) from one internal host, 107 ATP matches: the owner checks the device |

## Owner (2026-10-02)

| what | why |
|---|---|
| manual tests N13–N15 | when calendar, notes and Home Assistant devices are set up (docs/MANUAL_TESTS.md) |
| Instagram, TikTok | parked by the owner: plugins ready, accounts not connected |

## To do (designed)

| what | depends on |
|---|---|
| move the owner's key to root-only custody (USB) | owner (SECURITY.md) |
| firewall actions (block an address) and abuse reports as approvals | Sophos API plugin |
| full-disk encryption | owner |
| the calendar synced both ways: CalDAV write-back; Google and Microsoft through their APIs | the owner registers an app with Google / Microsoft (OAuth) |
| Mac and Windows, phases 3–5: installers, per-system locks, models on Metal/CPU, services, the cages | the Ports workflow's first run (the real list) |
| updates by release (a channel «only versions») | the owner's choice; today the updater follows the branch |

## Open bugs (0)

None (5 October 2026): A19 closed by re-importing 107 arXiv papers from HTML (C135, M97), A18 closed by
measurement (C136, M98). Measurements still to take: ROADMAP.md ("Still to measure").


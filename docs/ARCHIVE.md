# Archive — closed lists, kept as they were written

Moved verbatim on 2026-10-28 from ROADMAP.md and STATUS.md after the audit against the code: every item here
is done, superseded, or carried into ROADMAP.md's first section.

# From ROADMAP.md

## Owner's list of 2026-10-04 — in order of priority

Quick fixes, done in the same session (each verified in STATUS when closed):
| # | request | state |
|---|---|---|
| Q1 | forge writer back on Claude Code (opus) instead of Grok; the judge was already on Claude Code (set by the owner). Grok's cost measured by the owner: 746,041 tokens = $2.27 | ✅ roles set 2026-10-04 |
| Q2 | dictation: the first attempt always fails, the second works; send automatically after dictation (hands-free), Aurora answers aloud | ✅ C121, M84; to verify N31 |
| Q3 | backup page shows the next backup at 03:31 with the time set to 23:00 | ✅ C122; needs install.sh once; to verify N32 |
| Q4 | choosing an API provider shows its list of models, to assign them easily | ✅ a real menu (the list was a datalist, hidden on phones); N33 |
| Q5 | Files: PDFs made by Aurora cannot be deleted | ✅ 🗑️ on Aurora's PDFs only (Creator: Aurora); N34 |
| Q6 | side menu: an entry only when its plugin is on (Social shows only Facebook) | ✅ Social, Security, Projects follow their plugins; Social lists only platforms on and connected; N35 |

Larger, by priority (highest first):
1. **Voice** — owner (2026-10-04): the voice is natural, a neural one is not needed; the choice works (N24).
2. **The judge on zeros (A22)** — ✅ C128, then C129: the forge **8 of 8** with Claude Code opus (M89).
3. **Plugins: admin or user** — ✅ (2026-10-04) plg_access: the machine's plugins (backup, security, netintel, self,
   senses, homeassistant, cloud) the admin's, the personal ones everyone's; a new or forged plugin the admin's until
   shared; 👥 in each card. Switching plugins is the admin's (C124). N36.
4. **Plugin settings inside the plugin's card** — ✅ the settings of a plugin are in its card only (Settings lists the
   rest and says where the others are); yes/no as checkboxes; Facebook's card carries the autonomy (posts by herself,
   posts a day, which tools). N37.
5. **Alerts per user** — ✅ each user's choice was already theirs; a user now sees only the personal kinds (the
   machine's — incidents, backup, updates, harvester, cloud — are the admin's). Missing alerts found and added: the
   cloud ceiling reached, a cloud provider failing (answers from the local model), a plugin stopped for a secret, the
   harvester waiting; once an hour each, to the admin. Then (C126): Aurora's health, new sign-ins, her posts. N38.
6. **Trash with retention** — ✅ sys_trash: a file deleted from Files (attachments, Aurora's PDFs) goes to
   usr/<user>/trash, restorable; removed after AURORA_TRASH_DAYS (30) by the nightly round; AURORA_TRASH_ENABLED. N39.
7. **Routines: several times and day groups** — ✅ "days and times": times with "+", days one by one or a group
   (every day, Monday-Friday, weekend, working days without Italian public holidays, holidays). N40.
8. **Research beyond arXiv** — ✅ (2026-10-04) kno_acquire_more: the search agent asks, with the same queries,
   Europe PMC (open-access full texts, bioRxiv/medRxiv preprints included), Wikipedia and GitHub (READMEs with an
   open licence) besides arXiv; the re-ranker orders all candidates together; a chosen document is fetched then, with
   its licence and URL, and goes to a domain of its source (the reasoner chooses among them). Normattiva is not
   searchable by words (whole collections only). AURORA_ACQUIRE_SOURCES. Live: the three answer (M86). N42.
9. **Projects per user** — ✅ per user already (usr/<user>/projects, the GitHub token a personal setting); two tabs,
   Local and GitHub; Aurora runs tests and programs in a cage of her own (run_in_project: no network, no keys, only
   the project writable, AURORA_PROJECT_RUN_S) and iterates; GitHub writes through Approvals as before. M85, N41.
10. **Configurable security** — ✅ (2026-10-04) in the security plugin's card: the syslog documentation's link and the
    firewall's API (address, user, password, the blocking group). Security page: "What to watch": Aurora reads the
    documentation with the last day's traffic (grouped by log_id: type, component, subtype, severity) and proposes
    checks, each tried on that traffic (how many incidents it would have raised) and off until the owner turns it on;
    the sentinel follows within a minute (sec_rules). Defence: ⛔ on an incident puts the address in the group
    AURORA_XG_BLOCK_GROUP through the XML API (IPHost, HostGroupList), only on the owner's click; Aurora never writes
    firewall rules and never blocks loopback, the firewall or herself. M88, N43, N44.
12. **Mathematics in PDFs** (from A19, 2026-10-04) — the text of some papers comes out of the PDF with formulas garbled
    (‖x‖ as "kxk"): Aurora re-typesets them and the verification cannot match them. Count the garbled passages of the
    vault, measure a math-aware extractor on those papers, re-import them.
11. Left from before: A18/A19 (gate and extraction quality), U4 (concurrent users measured), U6 (system accounts).

## Next roadmap (to decide with the owner, after 2 October 2026)

Candidates, each with the measure that says it worked:
1. **The gate on vague questions** — follow-ups **done** (C104, C106, M71-M73); the gate's 3 wrong closures of 30 on
   complete questions remain (A18, A19): measure `bench_quality.py --pool 30` above 6.90, wrong gate closures below 3.
1f. **Answers aloud** (owner, 2026-10-03) — **done, to verify (N24)**: the device that asked reads the answer
   (browser speech synthesis, the device's own voices only); per device: when I speak (default), always, off. A
   local voice on the server (Kokoro, Apache-2.0, Italian voices graded C by their author) if the device voices are
   not good enough.
1e. **Cinema and expenses plugins** (owner, 2026-10-03) — **done, to verify (N22, N23)**: cinema from TMDB
   (trending, in cinemas, search, details, where to watch in Italy, JustWatch data; needs the owner's free TMDB key);
   expenses on this machine only (amounts in cents, categories, monthly budgets, summary against the month before).
   Netflix and Amazon: set aside by the owner (2026-10-03). **The film source is closed: TMDB, with the owner's key** (2026-10-03). Not doable as asked: Netflix has no public API (TMDB covers "what and where"); the Amazon cart is reachable by no
   API and reading the pages breaks Amazon's terms. Price watch of chosen products: Keepa (paid) or Amazon's PA-API
   (an affiliate account with sales) — the owner decides.
1d. **Artifacts** (owner, 2026-10-03) — **done, to verify (N21)**: interactive pages Aurora makes (charts,
   simulations, calculators) live in the chat, sandboxed with no network (M74). Also: formulas (KaTeX) and tables in
   the chat, suggestions kept with the answer.
1c. **Social, more autonomous** (owner, 2026-10-03) — **done, to verify (N18, N19)**: Share on dreams and
   thoughts (with the dream's picture); Aurora publishes her own posts by herself (Facebook posts and photos,
   at most 3 a day, recorded and notified); a morning routine (09:30) for a dream or a thought, the 18:30 one for <!-- schedule -->
   science news.
1b. **Suggested follow-ups** (owner, 2026-10-03) — **done** (C106, M73) — 3-4 complete questions under each knowledge answer, drawn from
   the passages found but not used, carrying the previous answer's sources; a click starts a search that is right by
   construction. Free follow-ups: the rewrite sees the whole previous answer and its sources' titles (A22), only there,
   no redundancy in the synthesis. Measure: the 14 follow-ups of M72 (3 right today) and the suggestions judged
   against their sources; the extra time per answer. Before multi-user U2.
2. **Multi-user** — performance check on install (users the machine can serve), an admin, users, TOTP MFA on by
   default; measure: concurrent users at the measured ceiling, no data seen across users (tests). Owner
   (2026-10-02): an install option, single or multi, changeable later; single = the admin alone; switching leaves no
   traces. **Done 2026-10-03** (docs/MULTIUSER.md): per-user layout migrated, settings per user, login with
   Authenticator code, Users page, REM and routines per user; crossing test M79, live M80. Left: U4, the ceiling of
   concurrent users measured; U6, the folders protected by system accounts (to decide).
3. **The whole 108 questions** — the quality benchmark on retrieval_pool108 entire, once, as the new reference.
4. **The forge** — the judge checks time windows (C118, C120); with Grok 5 of 8 right (M83), A22 open; measure:
   `bench_forge.py --roles` 8/8.
5. **Self-repair proven or switched off** — a week of its reports; on only with one real fix.
6. **The device on port 6667** — the owner checks it (11,945 denied connections to IRC).
7. **Feedback of the company's AI team** — their install on other hardware: the profiles not measured here.

## Depth before breadth (proposed 2026-10-02, the owner decides)

The structure is complete; what is missing is proof that each part is good, not more parts. In order:

1. **Backup of the owner's data** — **done** (M60): nightly, encrypted, deduplicated, checked; the owner chooses the
   folder (second disk or NAS) and keeps the recovery code; a full restore test once a month stays his habit.
2. **The manual tests** (docs/MANUAL_TESTS.md, ~30 lines): one pass by the owner on the phone and the PC.
3. **The HTTP layer under test**: in part (2026-10-03): the crossing test drives the real API with TestClient (16
   routes, two users) and a test lists the 7 routes without authentication of 111; a smoke of every route is left.
4. **Answer quality re-measured** — **done** (M66): 5.5, the answers given 8.8; three wrong abstentions, one per
   stage. Fixed and measured on 30 questions (M67): 6.03 → 6.90; the gate kept after measuring it off.
5. **Switch off what does not work yet, or prove it**: the forge with the local reasoner (C70, 4/8) and the
   self-repair (0 code fixes so far) — on only when a benchmark says they help.
6. **A week of soak**: memory of each service, log growth, GPU swaps, failed routines, measured daily
   (the doctor and health already give the numbers); then multi-user.

## Phase 1 — close what is open (now)

| item | state |
|---|---|
| plugin guides with verified official links (24 checked), "▶ Try" for read-only tools, docs/PLUGINS.md generated | done |
| plugins page: grid of icons, green active / red off, popup with guide, links, settings, tools, icon | done |
| plugin icons: official favicons fetched, drawn icons for Aurora's own; the owner changes them (upload or https link); default by kind | done (forged plugins: phase 3) |
| settings saved → popup "restart now?" → restart from the WebUI | done |
| PDF documents (plugin, API, "⬇ PDF" on answers) | done, download tested |
| owner's key moved to root-only custody: step-by-step guide | guide done (SECURITY.md); the owner runs it |
| Facebook test | needs the owner's Page and token (guide in the Plugins page) |
| LTM check | done: 14/14 turns long-term, 3 session memories |
| docs aligned with the code | done (automatic check of MODULE_MAP against the files) |

## Phase 2 — the reasoner, the sources, the cross-domain mind

| item | notes |
|---|---|
| pluggable reasoner: local llama.cpp, Anthropic API, Claude Code (CLI, owner's subscription) | **done** (M26): roles in AURORA_CLOUD_ROLES, service calls local, rule 9 refuses the cloud without exemption; Anthropic API not tested live (no key) |
| token compression for cloud providers (owner's SSCC engine, AGI_old/Papers/Presentation_Hybrid-Offload-Engine) | **done**: −29.6% on one question (M26); quality effect not measured |
| sources by domain on abstention: arXiv (science), Europe PMC / PubMed (medicine), Normattiva (law_it), Wikipedia (general), programming docs | propose the right source, not always arXiv |
| owner's sources: URL patterns with wildcards (e.g. `KBA-*********` sequential), site crawls from a start page, each with its own domain (e.g. sophos, sophos_central); a dedicated ingest per source kind | robots.txt and rate limits respected |
| owner-defined domains in the taxonomy | from the WebUI |
| harvester control in the WebUI: start/stop, "harvest now", a batch of papers (ids, links or a list) to download, split by domain automatically, with progress | **done** 2026-10-01: page 🌾 Harvester; live: RoFormer imported in 5 s from a batch, unknown id and non-arXiv link reported |
| cross-domain deductions: inferences that connect passages of different domains, shown as Aurora's deductions (with their premises), separate from verified facts | today verification drops them |

## Phase 3 — independence and presence

| item | notes |
|---|---|
| proactive messages: Aurora writes to the owner in the chat (a finding, a finished task, an incident, a thought worth sharing) | rate-limited, the owner can mute |
| PWA push notifications (Web Push, VAPID) | **done** 2026-09-30: 🔔/🔕 in the top bar per device; incidents, approvals, dreams, self-reviews (AURORA_PUSH_EVENTS); proactive chat messages still to do |
| autonomy ledger and levels: every autonomous action, its outcome, approvals/refusals, honesty warnings; a level that rises with the evidence | shown in a page, versioned |
| routines and plugins' suggestions | **done** 2026-10-01 (M46): 🔁 page; plugins say what they can do once connected and propose periodic checks; tool or agent routines, run by aurora-rem, notify always / if any / if new |
| Projects page | **done** 2026-10-01 (M46): local projects and GitHub repositories, clone, tree, files, history, sandboxed page preview, ask Aurora |
| weather plugin | **done** 2026-10-01 (M46): now, 3-day forecast, daily report, local alerts on sudden changes, MeteoAlarm warnings |
| multimodal (owner, 2026-10-01): V1 understand videos **done** (M48); I1 classic image edits **done** (M51; background removal and AI enlargement still to do: new libraries and models); I2 edits in words **done** (M55); V2 generate short videos **done** (M57); then multi-user (auto-sizing, admin, TOTP MFA) | one at a time, measured |
| next for presence | proactive messages inside the chat (today routines notify through the activity feed and push); the ledger page; GitHub traffic (views, clones) needs its own tool |
| webcam and microphone plugin: see (vision) and hear (speech to text) | **done** 2026-10-01: plugin `senses` (devices chosen in its window), 📷 and 🎙️ in the chat, Whisper on CPU (M35) |
| notifications page: push and WebUI toasts, presets (suggested / all / none / custom), event by event | **done** 2026-10-01 |
| research workspace: projects inside usr/documents/papers; scientific scripts run in usr/test_area with its own venv (installs there, never in Aurora's) | plugin "lab" |
| Facebook Page "A.U.R.O.R.A": Aurora's own blog, autonomous publishing (per-plugin autonomy switch), AI-disclosed | owner's decision |
| Instagram (Graph API: business/creator account linked to a Page) | needs the owner's account |

## Phase 3b — plugin suite (owner, 2026-09-30)

Rule proposed for every plugin that moves hardware (mount slew, park, focuser, dome, starting a
sequence): **always the owner's confirmation**, also with the level-B exemption. Tuning that cannot
damage anything (guiding parameters within bounds) may be autonomous, measured before and after,
rolled back when worse.

| plugin | what | how (to verify on the owner's setup) |
|---|---|---|
| `astro-guiding` (PHD2) | live guiding: RA/Dec error, RMS, star lost, calibration; tuning of aggressiveness, hysteresis, min-move, exposure — one parameter at a time, A/B on the RMS over N minutes, rollback | PHD2 event server + JSON-RPC (TCP 4400): events stream in real time, `get/set_algo_param`, `set_exposure`, `dither`; reachable from the LAN or through an SSH tunnel |
| `astro-nina` (N.I.N.A.) | equipment status, current sequence and image, last HFR/stars; start/stop a sequence (confirmation); plan a session | N.I.N.A. "Advanced API" plugin (REST + WebSocket, default port 1888), installed on the mini PC |
| `astro-planner` | tonight's plan: targets above the horizon, moon, darkness, cloud cover and seeing, framing for the owner's focal length and sensor, target order | local ephemerides (astropy/skyfield), open-meteo cloud layers, 7Timer! ASTRO (seeing, transparency); output: a plan and a target list for N.I.N.A. |
| `astro-alpaca` (ASCOM Alpaca) | read-only status of mount, camera, focuser, filter wheel | Alpaca REST (default port 11111), if the drivers expose it |
| `astrometry` | plate solving and annotation of the owner's images | nova.astrometry.net API (key) or a local solver |
| `flickr` | the owner's astro photos: upload (confirmation), albums, tags, stats; Aurora writes the descriptions (AI-disclosed) | Flickr API, OAuth 1.0a |
| `mini-pc` | the capture PC itself: disk space, CPU/temperature, running programs, logs (PHD2/N.I.N.A. log folders) | small agent on the mini PC or SSH; read-only first |
| `sky-events` | ISS passes, comets, occultations, APOD of the day | JPL Horizons, Minor Planet Center, NASA APOD API |

Needed from the owner: mini PC OS and address, PHD2 and N.I.N.A. versions, whether the Advanced API
plugin is installed, telescope focal length and camera sensor, Flickr API key.

## The plan of 2026-10-01 — kept as written (reviewed 14 Oct)

Done: 2 (C43), 3 (no aurora-ouroboros left), 4-6 (M28-M32), 7 (the harvester page), 9 (Facebook connected), 10 (the repository public since 2 Oct). Open: 1 the owner's own checks (row 3 of the main table), 8 the astro plugins — they wait for the owner's data (row 23 and 79).

| # | what | done when |
|---|---|---|
| 1 | owner: dream in the chat, 🔔 on (test notification), lightbox, streaming and tok/s seen in the browser | the owner confirms |
| 2 | A16: length stated in the prompt for Claude Code | a self answer ≤ the limit, measured |
| 3 | Ouroboros cleanup: empty sys/ouroboros and AURORA_OUROBOROS_DIR removed; ECOSYSTEM.md and schema say where self-repair lives | no reference to aurora-ouroboros left |
| 4 | A7 tensor split: tok/s for 3-4 splits (one GPU job at a time) | best split in .env, M28 |
| 5 | A3 drop time on a copy of the largest domain; A5 encoder on the full vault | M29, M30 |
| 6 | A8 verification (passages' language, all extracted passages) and A9 original sources: before/after | M31, M32 |
| 7 | harvester panel in the WebUI (start/stop, harvest now, batch of papers split by domain) | tested live |
| 8 | first astro plugins with the owner's data: astro-guiding (read-only first), astro-planner | live on the mini PC |
| 9 | Facebook, when Meta sends the SMS: token, page_info, first post with approval | post online |
| 10 | clean-up for the commit: docs aligned, tests, Apache headers script, .env.example, no personal data in the repo | owner's go for the commit |

## Phase 4 — security plugin

| item | notes |
|---|---|
| firewall as a plugin (not in Settings): syslog receiver + firewall API with credentials (Sophos first): read rules, block/unblock an address (approval) | the sentinel moves inside it |
| abuse reports as approvals (email plugin) | |

## Phase 5 — GitHub-ready

| item | notes |
|---|---|
| name and acronym A.U.R.O.R.A. everywhere | owner chooses the expansion |
| Apache-2.0 header on every source file + LICENSE + NOTICE, automated by a script | copyright holder: the owner's name |
| installer (Linux): pre-checks (OS, Python, GPU, RAM, VRAM, disk), owner's name, install folder, venvs created/reset, model choice and download, .env generated with values fitted to the hardware (all in VRAM or offload), certificates (self-signed or Let's Encrypt DNS via Caddy), firewall port hint, systemd units | the owner's machine is the "recommended" profile with measured RAM/VRAM |
| owner's name as a setting (prompts stop saying the owner's name in code) | **done** 2026-10-01: AURORA_OWNER_NAME |
| updates: check the repository for new commits (automatic or button), apply, restart | **done** 2026-10-01: AURORA_UPDATE_MODE notify/auto/off, changelog from the commits, approval in Repairs, fast-forward + tests + rollback; works once the GitHub remote exists |
| .env without hardware-specific numbers (PCIe, measured placements go to docs) | |
| GitHub page (Pages): block diagrams, charts, every aspect explained, differences from other systems, benchmarks | |
| public benchmarks: retrieval, answer quality (correct / wrong / abstained), speed, memory, agent honesty | reproducible scripts |
| Claude Code history: keep the sessions when the installation folder is renamed | **done** 2026-10-01 (same path); `sys_relocate.sh` for future moves |
| README in Italian (default) and English, benchmark charts | **done** 2026-10-01: README.md / README.en.md, docs/img/{it,en} from `doc_charts.py`; technical docs stay in English |

## Installer specification (owner, 2026-10-01)

`git clone` → `./install.sh` → the owner follows the screen and gets an Aurora sized for the machine.
The installer is the sum of the scripts run by hand on the owner's machine, in this order:

| step | what | from |
|---|---|---|
| 1 pre-checks | OS (Ubuntu 26.04 recommended), CPU, RAM, disk, GPUs (count, VRAM, compute capability), Secure Boot, internet | `sys_nvidia.sh check` + new checks |
| 2 NVIDIA | clean-up, CUDA toolkit 13 (toolkit only, apt pin), optional driver change with Ubuntu's signed modules, reboot, `verify` kernel on every GPU | `sys_nvidia.sh` (COMPATIBILITY.md) |
| 3 owner | name (AURORA_OWNER_NAME), language, install folder, domain (or local only) | prompts |
| 4 Python | venv created or reset, requirements.txt | |
| 5 profile | VRAM/RAM → a profile: the owner's measured one is **recommended** (2×16 GB: Qwen3.6-35B-A3B Q4 split 4.5,3.5); other profiles marked "not measured" until someone measures them | COMPATIBILITY.md |
| 6 models | chosen by the profile, downloaded from Hugging Face at a pinned revision, sizes shown before, SHA-256 checked after, resumable; licenses shown and accepted | new `sys_models_fetch.py` (manifest) |
| 7 llama.cpp | built for the GPUs found, pinned commit | `sys_nvidia.sh llama` |
| 8 .env | generated from the schema with the profile's values and fresh secrets, 0600 | `sys_env_sync.py` + profile |
| 9 ethics | a key pair for this installation in /etc/aurora, manifest signed, level B exemption only if the owner asks | `sys_ethics_sign.py setup [--exempt]` |
| 10 HTTPS | self-signed or Let's Encrypt (DNS), Caddy, firewall port hint | `sys_install_services.py` |
| 11 services | systemd units with explicit names, polkit rule, start, health check | `sys_install_services.py` → install.sh |
| 12 first run | tests, the retrieval benchmark on an empty vault, the WebUI address and the device login | `sys_tests`, `bench_retrieval.py` |

Models are **not** put in the repository: GitHub refuses files over 100 MB (the reasoner alone is 20.6 GB),
the weights carry their own licenses (SDXL: CreativeML Open RAIL++-M, which must be passed on), and
Hugging Face already gives versioned, resumable, checksummed downloads. The repository carries a
manifest (repo, revision, files, SHA-256, size, license, profile) and the installer fetches from it.
Today's models: reasoner 20.6 GB + vision projector 0.8 GB, encoder 1.2 GB, re-ranker 2.2 GB,
SDXL-Lightning 6.9 GB. FLUX.2 klein (23 GB) and Z-Image-Turbo (31 GB) were only benchmarked (M27).

## After the first commit (owner, 2026-10-01)

| item | notes |
|---|---|
| clean-install test: `git clone` into another folder, every installation step run and checked, problems fixed | the base of `install.sh` |
| AGI test battery: reasoning, memory over time, honesty (abstention, invented facts), autonomy (goals with plugins), self-repair, senses, planning — scored, repeatable, published as benchmarks | after the install test |
| invite testers to the private repository (GitHub: Settings → Collaborators) | owner |

## Still to measure (2026-10-01)

| what | why not yet |
|---|---|
| the two non-reference hardware profiles | no such machine here |
| ~~the whole `install.sh` with its sudo steps, on another machine~~ | ✅ 9-10 Oct: CI Install green on a clean Ubuntu (sudo steps included), the colleague's Debian 13, the Ubuntu and Windows VMs (M156-M158) — before: M103: from GitHub, multi-user, 6 min 39 s, 303 tests, first configuration; the sudo steps for missing packages need a machine without them |
| ~~Web Push delivery on phones~~ | ✅ measured: 146 pushes from 30 September to 5 October, 146 accepted by the push service, 0 failed, 2 expired subscriptions dropped by themselves |
| ~~an update from the public repository~~ | ✅ the clone updated itself from GitHub: 332 tests, 19.7 s (M103) |
| ~~the nightly backup started by its timer~~ | ✅ measured: 4 October 23:00, 1,590 files, 30.89 GB in 53 s (the time moved by C122) <!-- schedule --> |

## Still to implement (2026-10-01)

| area | items |
|---|---|
| knowledge | sources by domain on abstention (PubMed, Normattiva, Wikipedia, programming docs); the owner's sources with wildcard URLs and site crawls (Sophos KBA); owner-defined domains; cross-domain deductions shown as Aurora's, with premises |
| presence | proactive messages in the chat; autonomy ledger and levels; plugin "lab" (projects in usr/documents/papers, scripts in usr/test_area with its own venv) |
| plugins | astro suite (PHD2, N.I.N.A., planner, Alpaca, astrometry, Flickr, mini PC, sky events); firewall (Sophos API, sentinel inside); Facebook Page autonomous (waits for Meta's SMS), Instagram |
| tests | AGI battery: reasoning, memory over time, honesty, autonomy, self-repair, senses, planning, scored and repeatable |
| GitHub | public page (Pages) with the charts; releases with a changelog; issue templates |
| security | see SECURITY.md, "Hardening still to do" |

## Harvester beyond arXiv (owner, 2026-10-01) — done, M44

| item | state |
|---|---|
| licence per source | ✅ every harvested text stores licence, origin and URL in its solitons |
| domains with a choice | ✅ Harvester page: off / a round / until exhausted, per domain, with sources and progress |
| Normattiva → law_it | ✅ official pre-packed collections (open data API of api.normattiva.it), Akoma Ntoso, one passage per article, text in force |
| Europe PMC open access → medicine, biomedicine, genomics | ✅ |
| bioRxiv / medRxiv | ✅ |
| GitHub → programming | ✅ READMEs of repositories with an open licence; documentation folders still to add |
| Wikipedia → philosophy, religion, history, literature, society, general | ✅ English "Vital articles"; Italian Wikipedia still to add |
| a public estimate | ✅ README, per source |
| still open | patents (EPO OPS needs a key); the Constitution itself (not in a collection: one act to fetch by URN); per-topic queries chosen by the owner |

## Self-improvement — where it really is (2026-10-02, measured)

| ability | what exists | evidence | missing |
|---|---|---|---|
| notice a fault | daily self-review from the logs | 4 self-reviews in 2 days | — |
| fix itself | repair agent: sandbox, tests, proposal, rollback | 2 repairs, both found nothing to fix; 0 changes ever proposed | a real bug fixed by it, measured |
| notice a missing capability | the agent's request_capability, and a check by code after every agent run (routines, chat, services) | M54: 12/12 on test reports | live cases over weeks |
| build the capability | forge: write, cage, judge, install read-only; the cloud (Claude) only with the owner's consent per request, masked samples | M54 benchmark: 4/8 plugins right, judge kept 2 of them, let 1 wrong through | a run-and-read loop; judge errors; re-run the benchmark (bench_forge.py) after each change, with the cloud too |
| notice it lacks knowledge | abstention → "sì, cerca" → arXiv agent; harvester | live | sources beyond arXiv in the abstention path |

## Open measurements (BUGS.md)

None open: A1-A23 all measured and closed (BUGS.md, "was A…"). What is left to measure needs another
machine or the owner ("Still to measure" above).


# From STATUS.md

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
| social | Facebook autonomous since 2026-10-03: Aurora publishes her own posts (at most 3 a day; posts and photos only; recorded as "auto", notified); 09:30 a dream or a thought, 18:30 science; Share on dreams and thoughts with the picture (N18, N19 to verify). Instagram and TikTok plugins ready, waiting for the owner's accounts (Instagram professional linked to the page; TikTok developer app). Facebook connected (page token with 8 scopes; posts, statistics, comments, page info; writes wait for approval; the Messenger welcome message is not accepted by Meta's API for this page: set by hand in Business Suite); routines: a post a day proposed when there is something new, weekly statistics. LinkedIn later <!-- schedule --> |
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
| abuse reports as approvals | the e-mail plugin set up |
| full-disk encryption | owner |
| the calendar synced both ways: CalDAV write-back; Google and Microsoft through their APIs | the owner registers an app with Google / Microsoft (OAuth) |
| Mac and Windows, phases 3–5: installers, per-system locks, models on Metal/CPU, services, the cages | the Ports workflow's first run (the real list) |
| updates by release (a channel «only versions») | the owner's choice; today the updater follows the branch |

## Open bugs (0)

None (5 October 2026): A19 closed by re-importing 107 arXiv papers from HTML (C135, M97), A18 closed by
measurement (C136, M98). Measurements still to take: ROADMAP.md ("Still to measure").



# Roadmap

Every request of the owner is recorded here as soon as it is made, so that nothing is lost between
sessions. Each item moves to STATUS.md ("Working") when it is validated. Updated 2026-09-30.

## Principles restated by the owner (2026-09-30)

- Aurora grows more independent; her autonomy is **measured and tracked** (what she did alone, how it
  went, what the owner approved or refused), and improvements ship as versioned updates.
- Capabilities are governed by the code of conduct (sys/core/ethics). Defensive and constructive
  capabilities can be as strong as useful; capabilities to attack third parties, to identify or locate
  persons, or to write malware are **not built**, locally or on GitHub (level A).
- GitHub gets everything, to the last screw, published in safe mode; the owner's installation keeps
  its exemption from level B.
- The project is signed **A.U.R.O.R.A. — Architettura Unificata Risonante per l'Orchestrazione del
  Ragionamento Autonomo** (owner, 2026-09-30): the Italian acronym marks the project's Italian origin.
- Copyright in the Apache-2.0 headers: **A.U.R.O.R.A. Project** (owner, 2026-09-30).
- Claude as reasoner: **both** ways, chosen in Settings: Anthropic API (key) and Claude Code (CLI,
  the owner's subscription) (owner, 2026-09-30).

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

## Tomorrow (2026-10-01) — close the circle, then clean up for the commit

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
| SSCC on long contexts (agent runs, wide extractions): saving and answer quality | M40: short extractions are never compressed |
| dictation with the owner's real voice | M37 used a synthetic voice |
| the two non-reference hardware profiles | no such machine here |
| the whole `install.sh` with its sudo steps, on another machine | M39 ran the steps without sudo on this one |
| Web Push delivery on phones | depends on each device and browser |
| update with a read-only deploy key | the owner's key has a passphrase |

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

A3 drop on a large domain · A4 CUDA ≥ 12.8 build · A5 encoder on the full vault · A7 tensor split ·
A8 sentence verification · A9 acquisition sources — the migration ended (2026-09-30): measurable now.

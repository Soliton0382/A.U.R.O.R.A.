# Changelog

Each version is a signed tag; its notes are the publications since the one before (newest first). Numbers and proofs: docs/MEASUREMENTS.md, docs/BUGS.md.

## v0.2.5 — 2026-10-10

1 publications since v0.2.4.

- 2026-10-10 C260 PWA top bar; roadmap 77 deductions (kno_deduce, M178); roadmap 75 phase 1 project terminal (prj_term)

## v0.2.4 — 2026-10-10

1 publications since v0.2.3.

- 2026-10-10 C246-C259; English pivot; local models contest M174-M177 (35B + pivot, Qwen3-Next ready); --fit for large models; seed asked alone, 318 answers; KV q8_0 option; M173/M175 golden rotation (did not hold)

## v0.2.3 — 2026-10-10

1 publications since v0.2.2.

- 2026-10-10 C246 C247 C249 C250, agt_calls split, native tools for local models, M168-M171; hourly sharing removed

## v0.2.2 — 2026-10-10

1 publications since v0.2.1.

- 2026-10-10 C245 local models with their own template get the tools as a list, Mistral call form; M168 English shadows; M169 Mistral switch

## v0.2.1 — 2026-10-10

39 publications since v0.2.0.

- 2026-10-10 C229 closed (M158); M166 light profile on 6 GB; M167 immediate repairs; roadmap 70-71 measured
- 2026-10-10 C243 C244 scanner knocks medium, verdict too serious, scorecard on medium/high; roadmap 78 log retention by kind; native tool calling for OpenAI-compatible APIs (Gemini thought_signature kept)
- 2026-10-10 Roadmap 81: house chatter never an incident, one incident per threat, outbound threats explained and investigated, recon-then-out correlation, autopilot scorecard
- 2026-10-10 C241 firewall plans ask the origin, keep the owner's rule, show field diffs, explain 599, audit reads NAT origin; C242 syslog silence alert
- 2026-10-10 C240 plugin card says why a plugin does not start, Retry; weather place by town name (geocoding)
- 2026-10-09 docs/GPU.md: NVIDIA drivers and CUDA on Ubuntu and Debian, GPU tiers, AMD status (roadmap 80)
- 2026-10-09 C239 update approvals closed when up to date, Caddy trusted on update, HTTPS health says why
- 2026-10-09 C238 cloud update signs the exemption; shadow seed 380 answers (it/en), 75% sources linked
- 2026-10-09 C237 bubblewrap installed (plugins' cage); roadmap 73: another local model from Hugging Face (inspect, check by range, download with SHA-256, try, revert)
- 2026-10-09 C235 Caddyfile paths quoted (Mac); C236 WebUI boot waits for the API; install.sh updates without questions; uninstall says the clean way back
- 2026-10-09 C233 tests never send real notifications; C234 updates on Windows/Mac/Docker via command cards (roadmap 74)
- 2026-10-09 Model formats: GGUF reader, per-family profiles (Qwen ChatML unchanged, others native --jinja), cloud abilities cached; sys_model_check
- 2026-10-09 Agent reads tool calls in every provider's format (Hermes, Claude, Llama, Mistral, OpenAI, JSON)
- 2026-10-09 C232: agent reads Claude-format tool calls and drops invented tool results
- 2026-10-09 Machine audit picks light/standard/strong settings; C231 Windows plugins run in the AppContainer (window station and desktop read); Windows VM on 10 cores
- 2026-10-09 Shadows by chosen areas and language (installers ask 8 areas, Docker AURORA_DOMAINS), seed with domain/lang and arXiv links; OpenAI endpoint answers at answer.final (C229)
- 2026-10-09 C229: questions first on a CPU with the harvest running (quiet window, 4-passage slices, failed plugins remembered); C230: an answer cut by Gemini's thinking is asked again
- 2026-10-09 C224 settings reconciled; C225 Italian phones masked; C226 no cage no plugin + Docker plugins container; C227-C228 ports: checked everywhere, Caddy follows, page moves; cloud voice and dictation; approvals alerts; shadow seed for every user; Mac installer; notifications history last
- 2026-10-09 C222 bug reports and ideas as masked GitHub issues with a final privacy check; C223 Windows suite green (9 real bugs fixed everywhere); M154 harvest disk cost; Docker guide
- 2026-10-09 Docker image (cloud, one volume, supervisor, guide docs/DOCKER.md); HTTPS ports from the 🔒 page, checked and put back on failure; C221 default_sni; Windows tasks restart and Caddy root
- 2026-10-09 Windows installer (install.ps1, scheduled tasks, ACL keys, Caddy root) tried on a real Windows 11; C216 CPU priority; C217 installer CR+LF; C218 claude.cmd; C219 the owner's question first in models and API; C220 test date
- 2026-10-09 C214: harvester backs off on 429/503; C215: forge refuses code naming a person, runs plugin reads its own user; harvesting on by default, asked by the installer
- 2026-10-08 Models: four modes (local, mixed, cloud with privacy, all cloud) with every aspect checked, shell popups, consent signed with sudo; service role; forge with the chosen cloud; local reasoner on/off; C213 private data never follows the cloud default
- 2026-10-08 C213: private data (health, firewall) never follows the cloud default on a machine without a local model
- 2026-10-08 Installer: reasoner asked also with a GPU, any OpenAI-compatible service, address and key at every end, the phone (home address, name.local, root certificate over HTTP); 🔒 HTTPS page with own certificate; C212 HTTPS check before caddy trust
- 2026-10-08 Cloud install from a clean clone: the trial call without a .env, C210 personal settings on a new installation, C211 sys/https made by the service generator
- 2026-10-08 Install workflow: the end of install.log as public notices on a failure
- 2026-10-08 Aurora without a GPU: cloud reasoner chosen by the installer, masked, encoder and re-ranker on the CPU (M151); C209 thinking models answered nothing on short steps; Install workflow
- 2026-10-08 C208: the models' clients ask at first use (history without aurora-models); tests never reach this machine's services; make_private's PowerShell
- 2026-10-08 Phase 3: make_private removes every entry on Windows; the probe waits for the Mac's CPU counters (M150)
- 2026-10-08 Phase 3: C206 symlinked root, C207 open files (backup descriptor, memory reset), file privacy by ACL on Windows
- 2026-10-08 Ports: both green on real machines; NAS test skipped on Windows; failure reasons public (M148)
- 2026-10-08 Ports: tzdata on Windows (time zones); the models-service test in its own process (M147)
- 2026-10-08 Speech to text in aurora-models (no torch beside faiss); ports: native factory paths per system (M146)
- 2026-10-08 Ports: platform tests and native crashes as public notices; the Mac's OpenMP clash recorded (M145)
- 2026-10-08 Windows cage: grants only, never denials; Mac: Homebrew's official ffmpeg-full (M144)
- 2026-10-08 C204: plugins' cage hides the home wherever Aurora is; C205 ffmpeg paths; cages for Mac (sandbox-exec) and Windows (AppContainer) (M143)
- 2026-10-08 C203: GitHub plugin program installed and pinned; ports: probe on real Windows, plugins scanned, crash diagnostics (M142)
- 2026-10-08 C202: Ports on Windows (repository name ending with a dot); results as public notices; the ecosystem checked (M141)

## v0.2.0 — 2026-10-08

The first tagged version: 101 publications since the first public one (0.1.0, untagged).

- 2026-10-08 Aurora's own calendar (roadmap 68, C201); releases, one-command publish, Mac and Windows ports in the repository (roadmap 69)
- 2026-10-08 C200 voice: CSP media-src; local voice chosen wins; ports kept in the mirror
- 2026-10-08 C200 voice played inside the tap; composer as a menu; copy and reply under messages
- 2026-10-08 C199: lost connections taken up everywhere (requests answered once by key, runs followed again)
- 2026-10-08 Routines reviewed: videos on a schedule, Aurora's advice with Apply, sets by use, colour themes; C197 models OOM, C198 social publish checked
- 2026-10-08 C195 security plugin sandbox (password, folder), C196 dream told as scenes, painted as its scene
- 2026-10-08 Any firewall change asked in words, planned locally and checked by the code; Aurora's own firewall as a page; plans discarded (C193, M135)
- 2026-10-08 The security officer: audit, threat hunt, posture with playbooks, firewall changes planned and approved, the SFOS manual indexed; the security area in pages, autonomy in each section, plugins deleted into a trash (C190-C192, M134)
- 2026-10-07 Web answers are remembered without a vault id; a case reads the provisions that govern it (C188-C189, M133)
- 2026-10-07 A day of use: follow-ups take auto, weather routed to its plugin, routines wait while a person uses Aurora (C185-C187, M132)
- 2026-10-07 The forge builds plugins for services: declared settings (secrets masked), actions approved each time, a setup guide; the judge skips an unconfigured tool (C184, M131)
- 2026-10-07 README, GitHub page and charts for the new Aurora: answers by the question's kind, thinking modes, emotions, diet, access from away (M129, M130)
- 2026-10-07 Answers by the question's kind: web for facts (ddgs), vault for explanations, deep for cases; read once with sources; cache and night study; thinking modes, auto by default; modules under 500 lines; MKQA battery (M129, M130)
- 2026-10-07 A case told as a story: searched by its problems and its provisions, answered problem by problem; the answer pipeline in modules (C183)
- 2026-10-07 Cloudflare: split tunnel accepted (descriptions), a public record left for Aurora's name warned of (C182)
- 2026-10-07 Cloudflare access with one Save: tunnel token fetched by Aurora, aurora-tunnel service, step-by-step guide (roadmap 56, C181)
- 2026-10-07 Diet in the chat: the processed plan recalled with the code's date, the meal's card under the answer (C179)
- 2026-10-07 Diet plan followed day by day: process documents, meals proposed and re-weighed on the week, reminders; Word documents read (roadmap 55, C178)
- 2026-10-07 Who is logged in, at the menu's foot beside the language and the logout (roadmap 54)
- 2026-10-07 Good morning aloud: the player unlocked by the tap, MP3 voice, true error messages (C177)
- 2026-10-07 Aurora's mood beside the health dot: a face per emotion, its card on hover or tap
- 2026-10-07 Emotions from measurements; Facebook videos as Reel, post or story; Security: a block closes its incident, the owner's blocks counted (C174-C176)
- 2026-10-06 Social: Aurora's videos made, previewed and published from the Social page; Facebook video, Instagram Reels, TikTok
- 2026-10-06 Two voices: Piper tuned for the chat, the natural voice for the videos; free classical music; the voice clip stays private (C172, C173)
- 2026-10-06 Second thoughts: past answers reviewed, a better one told in the chat; chat resumes after a dropped connection (C170, C171)
- 2026-10-06 Chat resumes the answer after a dropped connection (C170)
- 2026-10-06 Security: threat lists, device baseline, decoys, weekly report, Aurora's own firewall; Veo 3.1, server voice in the picker, PDF thumbnails, chat sync, video progress; C165-C169 (M119)
- 2026-10-06 Multi-user health for every user, Aurora's documents to the trash, push urgency high, 30 manual tests run by machine; C162-C164 (M118)
- 2026-10-06 Multi-user done right, known devices, free-tier limits, uninstall/reset/restore with data formats, night shadow training; C158-C161 (M116-M117)
- 2026-10-06 Security in tabs with the network drawn, settings menu in 3 levels, live capabilities, ideas, cloud media providers; C155-C157 (M115)
- 2026-10-06 Doctors' cards, Aurora's own voice, agents and routines as icons, network map; roadmap 19/33-36 (M114)
- 2026-10-06 Shadow in two bands, answers written again and verified, overlapping shadows chosen; seed 116 answers; C152-C154 (M113)
- 2026-10-05 Shadow seed script and export, per-plugin caches, follow-ups kept with the shadow; roadmap: agents, routine icons, network map (M112)
- 2026-10-05 Shadow seed script and export, per-plugin caches, follow-ups kept with the shadow (M112)
- 2026-10-05 Answer shadow: paraphrases answered at once and rechecked in the background (M111)
- 2026-10-05 Studies at night what she could not answer, good morning; fixes C151; answer timing measured
- 2026-10-05 Synapses page and level 2, vault deduplicated (C149, C150): one document, one copy
- 2026-10-05 Synapses page, synapses of synapses and named concepts, noise links removed (C149)
- 2026-10-05 Synapses between domains, psychology, firewall undo and setup names, autonomy panel fixed (C148), PWA chat layout, GitHub Pages
- 2026-10-05 Firewall unblock fixed (C146), tighter masking (C147), what left the machine, what Aurora remembers, verification line, honesty and repair benchmarks
- 2026-10-05 Autonomy panel, autonomous defence, post privacy check, exam values, Wikipedia by language and programming docs, self-repair fixed (C139-C145), first admin login
- 2026-10-05 Side menu panel, arXiv HTML first (C137), two LLM slots (M102), push delivery confirmed by devices (M101), clean install measured (M103)
- 2026-10-05 Zero open bugs: A19 re-import from arXiv HTML, A18 measured; project reports, daily soak, push history, U4 and local forge measured
- 2026-10-05 Agent on Claude Code works with Aurora's tools (C133, C134); projects as briefs with progress alerts; notification history; side menu in areas; two-row top bar
- 2026-10-05 Masking stronger and mandatory (C132); the assistant's name, character and gender per user; Health sealed per user, local model only
- 2026-10-05 DJ: remix and mix in 8 styles, all local (M93); login with password and code in single-user; security checks with batch actions; roadmap: autonomy panel, system accounts, autonomous defence
- 2026-10-05 Log out; Social posts to approve and history; Approvals apart from Reports; firewall API generic and working (C131); autonomy panel proposal
- 2026-10-04 Harvester page back (C130: import circle); forge 8/8 (C129); gate threshold measured and kept off (M90-M92); roadmap status and DJ proposal
- 2026-10-04 Forge 8/8 (C129: one clock for truth and judge); gate threshold measured and kept off (M90-M92); A19 traced to garbled PDF formulas
- 2026-10-04 Search beyond arXiv (Europe PMC, Wikipedia, GitHub); configurable security: checks from the syslog documentation tried on real traffic, XG API blocking on the owner's click; forge 6/8 with Claude Code (C127, C128)
- 2026-10-04 Notifications: Aurora's health, new sign-ins, her posts as kinds of their own (C126)
- 2026-10-04 Status page no longer hangs on a sleeping NAS: SMB check before touching its folder (C125)
- 2026-10-04 Owner's list of 4 October: plugins of the admin or of everyone, settings in plugin cards, alerts per user, trash, routines with several times and day groups, projects in two tabs with a run cage; dictation and backup fixes (C121-C124)
- 2026-10-04 Forge: time windows (A20), Grok; per-user API keys, Facebook per user, plugin cage per user; benchmark ids (A21)
- 2026-10-03 Backup: Run now in the plugin's card, admin only; docs aligned
- 2026-10-03 Multi-user complete: per-request user, login with Authenticator, Users page, REM and routines per user
- 2026-10-03 User mode in Settings, installer asks single or multi, doctor aware of per-user settings
- 2026-10-03 Multi-user layout migrated and verified, diary and sandbox fixes
- 2026-10-03 Voice picker, per-user settings and plugins (U3)
- 2026-10-03 Dictation diagnostics, per-user memory (U3)
- 2026-10-03 Answers aloud, the owner's per-user tree, papers locked
- 2026-10-03 Cinema and expenses plugins, multi-user U2 (layout, migration, purge)
- 2026-10-03 Artifacts, formulas fix (service worker), suggestions kept with the answer
- 2026-10-03 Formulas and tables in the chat, WebUI no-cache, dream share fix
- 2026-10-03 Share dreams and thoughts, autonomous posts, morning routine
- 2026-10-03 Suggested follow-ups, previous answer and sources in focus
- 2026-10-03 Follow-up questions, open-files leak, nightly backup retries, multi-user U1
- 2026-10-02 PDF preview as page pictures, every file link opens inside the page, roadmap updated
- 2026-10-02 PDF preview as page pictures (works on phones), every file link of the WebUI opens inside the page
- 2026-10-02 Files open inside the app (pictures, PDF preview), immediate repair of failed owner requests
- 2026-10-02 Pictures on request, Facebook photo posts, honest reports on pending actions, failed approvals notified
- 2026-10-02 Close of 2 October: status, next roadmap
- 2026-10-02 Answer quality 6.0 -> 6.9 (whole passages to verification), science news and posts, calendar, notes, Nextcloud, Dropbox, Discord, WhatsApp, Twitch, READMEs aligned
- 2026-10-02 News and diary plugins, Instagram and TikTok, live answer-quality benchmark, models service gives GPU memory back
- 2026-10-02 Archive closed incidents, docs aligned
- 2026-10-02 Forge on Claude, benchmark truths fixed, Facebook greeting guidance
- 2026-10-02 NAS mount button, backup memory cap, Facebook page setup
- 2026-10-02 Facebook management, NAS mount fix, service user fix, scrollable menu
- 2026-10-02 NAS backup plugin, cloud daily ceiling, placeholder fix, harvester waits for the API, SSH keys hidden from services
- 2026-10-02 Backup, bug reports, routine PDFs, privacy scan in the publish check
- 2026-10-02 Modular API (aurora/api), faster plugins page, no public API map, loose log rotation, installer fixes from a clean install
- 2026-10-02 Consolidation: feature gates, sys_doctor, installer per-group models, caged plugin logs, structure tests
- 2026-10-02 V2: videos from words or a photo (Wan 2.2 TI2V 5B), GPU lock across processes
- 2026-10-02 Models per step, cloud providers plugin, default masking, guide page
- 2026-10-02 I2: picture edits with FLUX.2 klein, Swin2SR upscale, SAM 2.1 cut-out; forge with cloud on consent (M54, M55)
- 2026-10-02 Aurora notices missing capabilities by code, forge benchmark (M54), cloud forge only with consent and masked samples, firewall settings in the security plugin
- 2026-10-01 Capability forge (caged, no network, judged), push for new kinds, downloadable documents (C69, C70)
- 2026-10-01 Security plugin; routines never fail silently, agent fits its context (C68); manual test list
- 2026-10-01 Picture edits in words, look again at the latest picture; vision gets 32-px tiles (C67, M50, M51)
- 2026-10-01 Attached files kept with the conversation, Files page (C66); video watching (M48)
- 2026-10-01 Aurora watches videos: scene changes, frames in one vision call, timestamped local transcript (M48)
- 2026-10-01 PWA: the phone's camera and microphone (Android and iOS), voice transcribed by the local Whisper
- 2026-10-01 Projects page, routines with plugins' suggestions, weather plugin with alerts; chat uses connected services; weather errors never log coordinates (C64, C65)
- 2026-10-01 Chat routes requests about connected services to the agent (C64); certificate chains and network errors in the harvester (C63)
- 2026-10-01 Harvester: complete certificate chains (AIA), network errors retried not taken for missing collections (C63), faster until-exhausted
- 2026-10-01 Harvester: open sources per domain (Normattiva, Europe PMC, bioRxiv/medRxiv, Wikipedia, GitHub) with licence per text, domain choice in the WebUI; plugin cage under confined units (C58-C62)
- 2026-10-01 Security: plugin cage, secret guard, confined services, login lockout, signed updates, hash-locked dependencies; SSCC 60% (M41)
- 2026-10-01 install.sh: plug & play installer (models from Hugging Face, profiles, .env, services); A17 closed; M37-M40
- 2026-10-01 Clean-install fixes from the clone test (C52-C56): env, llama build, .env.example, gitignore, Caddy stop
- 2026-10-01 README: architecture, formulas and SSCC; fresh .env uses the installation folder (C52)
- 2026-10-01 A.U.R.O.R.A.: first public version

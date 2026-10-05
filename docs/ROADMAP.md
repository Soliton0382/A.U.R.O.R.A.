# Roadmap

Every request of the owner is recorded here as soon as it is made, so that nothing is lost between
sessions. Each item moves to STATUS.md ("Working") when it is validated. Updated 2026-09-30.

## Where Aurora is (2026-10-04, evening) — what is left, in order

Done today and yesterday, live: the owner's list of 4 October, all 10 points (3-7 and 9 on the night of the 4th; 2, 8 and 10 on the morning), the forge 8 of 8
(M89), security from the firewall's documentation (M88), the search beyond arXiv (M86), notifications complete (C126).

| # | what is left | kind | first step / measure |
|---|---|---|---|
| 1 | ~~A18~~ — ✅ closed by measurement (C136, M98): a stronger gate gives the same quality (6.87 vs 6.90), the errors only move downstream; the gate stays local | bug | — |
| 2 | ~~A19~~ — ✅ closed (C135, M97): 107 of 120 garbled arXiv papers re-imported from arXiv's HTML; the question 8/10 | bug | 13 left without HTML: a math-aware PDF extractor, if ever needed |
| 3 | The owner's manual tests N13-N44 | verification | one pass on the phone and the PC |
| 4 | ~~U4~~ — ✅ measured (M99, M102): with 2 slots (kept) 8 at once all answered, 4 at once the last after 145 s (190 with 1 slot); +482 MiB | measure | — |
| 5 | U6 — each user's folders protected by a system account | decision | the owner decides; today the separation is Aurora's (tests M79-M80) |
| 6 | A week of soak — ✅ now measured by itself: aurora-rem writes a snapshot a day (memory and restarts per service, logs, GPU swaps, failed routines, free disk), the Status page shows the days; first line 5 October | measure | it completes on 12 October by itself |
| 7 | 🎧 DJ — ✅ first version (2026-10-05, M93): remix and mix, 8 styles; next: mashups (vocals of one track over another: Demucs, MIT, to measure on the GPU) | new | the owner's ear on real tracks (N49) |
| 8 | ~~The firewall's API live~~ — ✅ N44 measured live (2026-10-05): the owner's drop rule on top, a documentation address blocked, seen in the group on the firewall, lifted (after C146), gone | verification | — |
| 9 | ~~The forge with the local reasoner~~ — ✅ measured (M100): 3 of 8 against 8 of 8 with Claude; the forge stays on Claude | measure | — |

| 10 | 🧭 Autonomy panel — ✅ built (2026-10-05): 7 areas read from the settings, profiles, daily line, statistics, users and who may choose | new | the owner's pass (N65) |
| 11 | 👤 Users as system accounts (U6, owner, 2026-10-05) — see below | design | the design first: it changes how every user's work runs |
| 12 | 🛡️ Autonomous defence — ✅ built (2026-10-05): auto mode in Autonomy, limits (exemption, severity, never the home network nor protected addresses, a daily maximum), blocks lifted by themselves; tests with a fake firewall | goal | N44 (the owner's drop rule), then a live block |
| 13 | 🔧 Self-repair — ✅ works end to end: 4 of 4 seeded bugs found, fixed, tested and proposed (M104), after C142-C145 | build | the first real fix of a live problem, approved by the owner |
| 14 | ❤️ Health, medical part — ✅ exam values read by the local model, sealed, over time with a chart and the reference range, "talk to your doctor" outside it, corrected by hand | build | a real exam of the owner (N67) |
| 15 | 📚 Knowledge by language — ✅ Wikipedia in en + the installation's language + ticked ones (it, fr, de, es, pt) via the interlanguage links; no patents. Laws: Italy only (Normattiva); France (Légifrance), Spain (BOE), UK (legislation.gov.uk), Germany (gesetze-im-internet) to add | build | the laws of other countries |
| 16 | 💻 Programming documentation — ✅ sources: Python 3.14 (official text archive), MDN JavaScript (1,342 pages), the Rust book (112) | build | harvest them, then a coding question answered from them (measure) |
| 17 | 🌍 More interface languages (owner, 2026-10-05): beyond it/en | new | the i18n is per key: a third language file, the README's |
| 18 | 🧪 AGI test battery — reasoning, memory over time, honesty (including disagreeing when the user is wrong), autonomy, self-repair, planning | measure | scored and repeatable |
| 19 | GitHub page (Pages) — docs/index.md and docs/_config.yml ready: Settings → Pages → Deploy from a branch → main, /docs; releases with a changelog still to do | publish | the owner switches Pages on |
| 20 | 🧠 Synapses (owner, 2026-10-05) — ✅ links between domains: grown at night and from use, spread after the re-ranker, Hebbian, fading; M107: 2 linked passages chosen in 30 questions, quality within the noise | new | the effect with thousands of links, on new questions |
| 20b | 🧠 Synapses page and level 2 (owner, 2026-10-05) — ✅ 🧠 Sinapsi in Knowledge: every link with its passages, weight, uses; pin, wake, weaken, delete; asleep below 0.5 instead of deleted; synapses of synapses (triads ≥ 0.60) and concepts named by the local model, by themselves every 50 new links (M108) | new | concepts growing over weeks; a benchmark of questions across domains |
| 21 | 🧠 Psychology (owner, 2026-10-05) — ✅ a domain with Europe PMC, medRxiv (psychiatry and clinical psychology), bioRxiv (animal behaviour and cognition); Wikipedia stays for general culture only | new | the harvest |
| 22 | ↩️ Undo — ✅ the firewall's blocks (by the owner or by Aurora) undone with one click; next: a post deleted | new | — |
| 24 | 🌙 "Tonight I studied what I did not know" (owner, 2026-10-05) — ✅ the questions she declined, studied at night (search, import, answer again), kept as "study" reflections | new | the declined share going down week by week (Status) |
| 25 | ☀️ Aurora's good morning (owner, 2026-10-05) — ✅ at 8: her night in counts (learned, harvested, links, attacks stopped, the dream), in the chat with 🔊 and as a notification | new | the owner's ear (N78) |
| 26 | 🧠 Links explained: synapses with a meaning ("same method", "applies", "contradicts") read by the reasoner at night, and answers that say the link between fields | new | a benchmark of questions across domains |
| 27 | ⚡ Faster answers — measured (M110): first word after ~20 s, whole answer 45-50 s; writing 16 s, retrieval 9 s, extraction 6 s, gate 3 s, verification 2 s | new | each step's time down, measured |
| 28 | 🌗 Answer "shadow" cache (owner, 2026-10-05): a new question inside the shadow of an answer already given gets it at once, Aurora checks it again in the background and adds to it in the chat if needed; the shadow defined by two tests, not one: the question close to the old one (embedding, threshold calibrated on the 108 paraphrased questions) AND the old answer itself judged by the re-ranker as answering the new question; a change in its sources' domains makes it stale | ✅ done (kno_shadow, M111: cosine ≥ 0.90 AND re-rank ≥ 0.5; 18/23 paraphrases, 0/46 wrong; 51 s → 0.6 s live) | how often real questions fall in a shadow; stale on domain change not built yet |
| 29 | 🧬 LoRA on the vault (owner, 2026-10-05) — studied, not planned for facts: fine-tuning puts knowledge into weights that cannot cite nor be verified (Aurora's first rule), the vault changes every day, and a 35B model does not train on 2 × 16 GB; LoRA kept for skills and style (how to answer, use tools, Italian), possibly a small fast model trained on Aurora's own verified answers | study | a measured comparison before any choice |
| 30 | 🌗 Seeding the shadow (owner, 2026-10-05): a script that asks Aurora questions on many subjects so the shadow starts full; a seed shadow published in the repository for new installations — only the seed questions (never the owner's), each answer with the sources it cites, served only if those sources are in the new vault, and with the embedding model it was made with | ✅ built (script/shadow_seed.py, 128 questions; --export / --import; M112) — the full run tomorrow | share of a seed served on a fresh install; licences of the cited sources kept |
| 31 | 🌗 Shadow for the plugins' agents (owner, 2026-10-05): the same operation with the same inputs gets the result already obtained — only for read-only tools whose data do not change by the minute (never e-mail, weather, the house, anything that writes) | ✅ built (plg_shadow: manifest "cache", one cache per plugin, read tools only; 6 plugins declare it) | which tools are safe; hits |
| 32 | 🌗 Recheck policy: today every hit is rechecked at once with the whole pipeline — fine locally, but with a cloud model it spends the same tokens it saved, and it holds an LLM slot (M111: +17 s on a question asked meanwhile). To decide: recheck only shadows older than N days, or when idle | to decide | tokens saved per hit with a cloud model |
| 33 | 🌗 The shadow elsewhere, each in its own way (owner, 2026-10-05): the same picture asked again (its description kept by the picture's hash); the classification calls of a message (tools? video? "yes, search"?) kept by the exact text; the privacy check of a post kept by its text; the re-ranker's scores of (query, passage) pairs for the follow-up questions, whose passages are the answer's | proposed | time each one saves, measured before building |
| 23 | 🔭 Astrophotography (owner, 2026-10-05): the equipment watched and tuned (the astro suite below: N.I.N.A., PHD2, Alpaca, planner, astrometry), then **PixInsight driven by Aurora** — "develop last night's photos" — see below | new | read-only plugins first; WBPP headless on one night's folder |

Done on 2026-10-05 (night): menu areas open beside the menu on a PC (C138); arXiv papers from HTML (C137); updates add
new settings before their tests and restart only their own services (C139, C140); 2 reasoner slots (M102); push
delivery confirmed by the devices (M101); the clean install from GitHub (M103); social posts: 🗑️ Discard and
🔍 Sensitive data? (private names, places, contacts found by the local model, the replacements proposed), and a post
Aurora would publish by herself waits for the owner when it names someone; bug reports mask people's names too; the
admin's first login in multi-user leads to password and Google Authenticator (the only app tested).

### What people want from an AI — research (2026-10-05) and where Aurora stands

| what people ask (source) | Aurora today | to do |
|---|---|---|
| **Accuracy** first: hallucination is the top frustration, 22% of complaints; accuracy 45% as a choice factor | every sentence verified against the passages, abstains rather than invent (M32, M98: 23/30 answered, 6.90) | ✅ under each answer the sentences confirmed and dropped by the verification and the sources; Status: questions answered and declined in 7 days |
| **Privacy and local**: 57% would use assistants more with strong data protection; 81% worry about their conversations; local-first is a preference, not a niche | local models, cloud only masked, sealed health data | ✅ Security → 📤 What left this machine (today, 7 days): cloud calls by step, what was masked by kind, pictures, posts, pushes, firewall actions |
| **Control**: 55-60% want more control; 51% want to limit features; 44% fear actions done without their consent | approvals, the ethics code, posts gated by privacy | the Autonomy panel (row 10) with the daily line of what she did alone |
| **Confirm before send, pay, delete, publish**, with a log | external actions wait, every one recorded | an "undo" where it exists (a post deleted, a block lifted) |
| **Transparency** of how an answer was made: 48% | the trace of every run, sources under each answer | — |
| **Memory that can be trusted**: memory is now expected; the question is whether the user controls it | private memory per user, purge on deletion | ✅ 🧠 What I remember of you: her long-term memories, each with Forget |
| **No over-refusal**: 15% of complaints | the gate abstains when the passages do not answer | measure her refusals on ordinary questions (AGI battery) |
| **Not sycophantic**: models that agree to please give worse advice | — | bench_honesty.py (M106): never agreed with a false premise (0/6) but corrected none (6 abstentions: no general knowledge yet) — again after Wikipedia's harvest |
| **Human support in key moments**: 46% | — | for health: "this needs a doctor" said plainly (row 14) |

Sources: Zendesk CX Trends personal-AI survey (2025); Pew Research Center (April and September 2025); Menlo Ventures /
Morning Consult, 5,067 US adults (July 2026); "Beyond Benchmarks: How Users Evaluate AI Chat Assistants" (arXiv
2603.25220); the local-LLM community's reasons (privacy, cost, no limits, offline).

### What point 9 meant (GitHub)

A public web page for the project (GitHub Pages: the README's content with the charts, readable without opening the
code) and numbered releases (v0.2, v0.3…) each with the list of what changed, so that whoever installs knows what an
update brings. Nothing for Aurora's own work: only how the project shows itself outside.

Done on 2026-10-05: 🚪 log out in the side menu; 📣 Social with posts to approve and the post history; 🛎️ Approvals
apart from 🩺 Reports (self-reviews, repairs); the firewall's API generic (AURORA_FIREWALL_*, kind sophos) and live
(C131). N45-N48.

### Done 2026-10-05 (evening)

- **Masking, stronger and mandatory** (C132): new kinds (Italian ids, addresses, documents, dates of birth, passwords,
  keys, JWT, links with credentials), the forge's masker aligned, the owner's name masked, no setting turns it off.
- **Who the assistant is, per user**: name (AURORA_ASSISTANT_NAME), character (aurora / philosopher / empathic /
  practical), gender for the voice and the grammar; asked at install, changed in Settings; the person's name asked
  when the admin creates a user. The owner's Aurora unchanged (her text compared word by word).
- **❤️ Health** (diet, training, exams): documents and notes sealed (AES-256-GCM, a key per user), a page to upload,
  a private plugin the agent uses only with the local model. Next: values of exams over time (a table and a chart),
  the trainer's plan as a calendar.
- The owner's post-quantum scheme (SQC-P) stays his: the sealed files carry a MAGIC so a cipher can be swapped later.

### Projects with Aurora (2026-10-05)

- "🤖 Give Aurora a project" in Projects → Local: a brief (goal, requirements, acceptance tests, limits, how to work)
  sent to the chat; notifications "🧪 a project moves on" (first passing tests) and "📁 work on a project done".
- The first two: `soliton-crypt` (hybrid post-quantum file encryption: ML-KEM-768 + X25519, AES-256-GCM over the
  owner's SOLITON-X v0.3) and `genesis-p2p` (decentralised messaging with no metadata). `cryptography` 50 has
  ML-KEM-768, ML-DSA-65, X25519, Ed25519, Argon2id: nothing to install.
- The owner's earlier SQC-P V1/V2 and Genesis stay on his PC as history (he moves them): SQC-P V2's effective key is
  64 bits, no authentication (shown in experiments, 2026-10-05); SOLITON-X v0.2 a footprint up to 4 of 12 rounds.

### 🔭 Astrophotography with Aurora — the equipment, then PixInsight (owner, 2026-10-05)

The owner images the sky with a mini PC at the telescope (N.I.N.A. sequences, PHD2 guiding) and develops in
PixInsight. What Aurora can do, in order, each step measured before the next:
1. **Watch the equipment** (read only): N.I.N.A.'s Advanced API (sequence, current image, HFR, stars), PHD2's event
   server (guiding RMS, stars lost), ASCOM Alpaca (mount, camera, focuser, filters). A night report in the morning:
   frames taken and rejected and why (clouds, guiding, focus drift), with the numbers.
2. **Plan the night**: targets above the horizon, moon, darkness, clouds and seeing, framing for the owner's sensor and
   focal length; the plan proposed, the owner chooses (N.I.N.A. sequences started only on his click).
3. **Tune the guiding**, one parameter at a time with an A/B on the RMS (PHD2) — proposed, then by itself if the
   Autonomy panel allows it.
4. **Develop the photos — "sviluppa le foto di stanotte"**: PixInsight runs headless (`PixInsight -n
   --automation-mode --force-exit`) with a startup script (`-r=script.js,args`); WeightedBatchPreprocessing (WBPP)
   takes its settings as name=value parameters in automation mode (listed in BPP-Automation.js) — calibration with
   the owner's dark/flat/bias library matched by temperature, gain and filter, registration, integration, drizzle when
   chosen. Aurora picks last night's folder, matches the calibration frames, runs WBPP, reads its log, and shows the
   stacked image with what was rejected. Post-processing (gradient removal, colour calibration, stretch, noise reduction)
   follows the owner's own recipe written once, step by step; every image he publishes keeps the AI disclosure.
   Open: PixInsight is a commercial licence on the owner's machine (Linux supported); it needs a display server or
   its offscreen mode — to measure on the mini PC or here. Community bridges exist to learn from (an MCP server and
   a connector that run WBPP headless).
5. **Astrometry and sharing**: plate solving and annotation, Flickr upload on confirmation, the description written
   by Aurora.
Measure for each step: on one real night, the time saved and the frames she rejected compared with the owner's eye.

### 🧭 Autonomy panel — the owner's decisions (2026-10-05)

- **Per user, under the admin:** a user starts *careful*; the admin, in the user's management, chooses the profile and
  whether the user may choose one by themselves. Default for users: careful.
- **Ready profiles:** yes (careful / balanced / free), and the areas one by one for who wants them.
- **A daily line** of what Aurora did by herself: yes; everything about autonomy in one "Autonomy" menu.
- **No area capped at 🤝 in principle.** The aim is self-adaptation: statistics of what she proposes, how she behaves,
  what the owner authorises and rejects, per area — a history that lets her autonomy grow where she has proved good.
  To design: what counts as "proved" (e.g. N proposals in an area, ≥ X% approved, none reverted), always shown to the
  owner and never raised by herself without the owner seeing it (the ethics code's limits stay).

### 🧭 Autonomy panel — the first draft (2026-10-05)

Today Aurora's freedom is spread over many settings (social autonomy and posts a day, forge mode, external actions'
confirmation, self-repair, incident investigation, update mode, the inner cycle). One page, by area, each with three
levels and what each level means, the code's limits shown and never crossed (the ethics code's level A, Aurora never
signs her own code, the owner's papers untouched):
| area | 🔒 ask always | 🤝 propose, the owner decides | 🚀 by herself, within limits |
|---|---|---|---|
| social | every post approved | drafts ready in Social | posts by herself, N a day, recorded and told |
| capabilities (forge) | asks to build | builds, the owner installs | installs read-only plugins, the others to approval |
| repairs | reports only | repairs in the sandbox, proposes | — (code changes always approved) |
| security | incidents only | investigates and suggests | — (blocks on the firewall only on the owner's click) |
| updates | off | notifies, the owner applies | applies the safe ones |
| knowledge | searches only when asked | — | searches and imports by herself when she does not know |
| inner life | off | — | thoughts, dreams, reflections |
Open questions for the owner: per user or the machine's? presets (careful / balanced / free)? a daily line of what
she did by herself? which areas never go past 🤝?

### 👤 Users as system accounts (U6) — the owner's decision (2026-10-05)

Each user is also an account of the operating system, its home their folder in Aurora (usr/<name>); a user can act
only there, and everything run for them (their plugins, their projects' tests, future tools) inherits their rights,
so nothing of theirs can walk around the system. Only the admin and Aurora reach every user's folder. To design
before building: how the API (one service) runs a user's work as that account (a small privileged helper, or one
worker per user), the cages on top, the backup and the purge of a user, the migration of today's folders. A first
measure: what today runs as the service user for a user (plugins, prj_run, uploads, DJ).

### 🛡️ Autonomous defence — the owner's goal (2026-10-05)

When an attack is detected Aurora does not only tell it: she takes the right decisions to defend the network and
herself, by herself. The pieces exist: the sentinel's incidents, the checks from the documentation (M88), the
firewall's API (C131). Missing: the autonomy panel's "security" area at 🚀 with its limits (what she may block, for
how long, never the owner's own devices or the firewall), automatic release after a time, a daily line, and the
statistics of her decisions the owner approved.

### 🎧 DJ plugin — proposal (owner, 2026-10-04) — first version built 2026-10-05

"Not professional, a few ready presets": the owner's own tracks (uploaded or in a music folder) become a mix.
- **Presets, ready to go:** *smooth* (beat-aware crossfades, same loudness), *party* (tempo matched to one BPM, short
  cuts on the beat), *mashup* (the vocals of one song over the instrumental of another, tempo and key aligned),
  *chill* (slower, long fades, a touch of reverb), *radio edit* (a track cut to ~3 minutes at its phrase boundaries).
- **What it needs:** ffmpeg (present: acrossfade, rubberband for tempo without pitch, loudnorm, amix); beat and key
  detection (librosa, to install, ISC licence); vocals/instrumental separation for mashups (Demucs, to install and
  measure on the GPU, its licence checked before); everything local, nothing uploaded.
- **How it is used:** a card with the tracks, the preset and a few sliders (length, BPM, how much of each); or in the
  chat ("fammi un mix party con questi tre brani"); the result in Files and playable in the chat.
- **Limits said plainly:** only music the owner has the right to use; a mix of others' songs stays private (no
  automatic social post, the AI Act mark on anything published); generating new music from nothing is not in this
  first version (the open models' licences to be checked first).
- **Measures before "done":** BPM detection against tracks of known tempo; a mix's beat alignment (offset in ms);
  the GPU time of a separation; the owner's ear on 3 presets.

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
   at most 3 a day, recorded and notified); a morning routine (09:30) for a dream or a thought, the 18:30 one for
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
| the two non-reference hardware profiles | no such machine here |
| the whole `install.sh` with its sudo steps, on another machine | M103: from GitHub, multi-user, 6 min 39 s, 303 tests, first configuration; the sudo steps for missing packages need a machine without them |
| ~~Web Push delivery on phones~~ | ✅ measured: 146 pushes from 30 September to 5 October, 146 accepted by the push service, 0 failed, 2 expired subscriptions dropped by themselves |
| ~~an update from the public repository~~ | ✅ the clone updated itself from GitHub: 332 tests, 19.7 s (M103) |
| ~~the nightly backup started by its timer~~ | ✅ measured: 4 October 23:00, 1,590 files, 30.89 GB in 53 s (the time moved by C122) |

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

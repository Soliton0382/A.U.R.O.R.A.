# Status — work in progress

Updated at every validated change (last: 2026-10-01). Details: BUGS.md (issues, 0 open / 57 closed),
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
| WebUI | modular showcase: chat (full width, dates, path, share), repairs, security, diary, social, plugins, import, activity, status, settings; sky with orbiting fireflies; metrics with GPU load; PWA; safe Markdown | headless Chrome checks |
| logs | one file per component, rotation, gzip, 12-month retention, traces, lifecycle lines; Aurora reads them | sys_logread |
| encryption | TLS 1.3 to clients, HTTPS everywhere outwards, secrets 0600; storage not encrypted (no LUKS) | SECURITY.md |

## In progress

| what | state |
|---|---|
| migration of the previous knowledge (355,415 solitons, owner's exclusions) | **done** 20:45: 316,866 written, 37,046 duplicates, 1,474 rejected |
| harvester | waits for the migration, then starts by itself (now also cs.CR, cs.SE, cs.PL) |
| image model | benchmark done (M27): SDXL 2.9 s, klein 10.3 s, Z-Image 21.4 s per 1024² image; the owner chooses from the images |

## To do (designed)

| what | depends on |
|---|---|
| install the new unit aurora-sentinel (install.sh), point the firewall's syslog to it | owner |
| move the owner's key to root-only custody | owner (SECURITY.md) |
| firewall actions (block an address) and abuse reports as approvals | a firewall API plugin, email configured |
| plugin triggers (a Telegram message becomes a goal) and forging new agents/plugins during a run | agents (working) |
| Instagram (Graph API business account), other platforms | the owner's accounts |
| Italian law corpus (Normattiva) | harvester |
| full-disk encryption | owner (reinstall or encrypted home) |
| README for GitHub: architecture to the bit, how it works, what differs from other systems, benchmarks | these documents |

## Open bugs (0)

None open. Measurements still to take are listed in ROADMAP.md ("Still to measure").


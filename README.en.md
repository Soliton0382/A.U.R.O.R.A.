<p align="center"><img src="docs/img/banner.en.svg" alt="A.U.R.O.R.A." width="100%"></p>

<p align="center"><img src="https://img.shields.io/badge/license-Apache--2.0-2a78d6" alt="License"> <img src="https://img.shields.io/badge/python-3.14-1baf7a" alt="Python"> <img src="https://img.shields.io/badge/CUDA-13.4-008300" alt="CUDA"> <img src="https://img.shields.io/badge/Ubuntu-26.04-eb6834" alt="Ubuntu"> <img src="https://img.shields.io/badge/tests-1474%20passed-1baf7a" alt="Tests"> <img src="https://img.shields.io/badge/code-110k%20lines-6a4fd6" alt="Lines of code"> <a href="https://doi.org/10.5281/zenodo.23650856"><img src="https://zenodo.org/badge/DOI/10.5281/zenodo.23650856.svg" alt="DOI"></a></p>

<p align="center">🇮🇹 <a href="README.md">Italiano</a> · 🇬🇧 <b>English</b></p>

**Architettura Unificata Risonante per l'Orchestrazione del Ragionamento Autonomo** — a local AI that
joins the best of two worlds: the **solidity of a verified archive** (the vault, which grows by itself at
night) and the **breadth of the web**, held together by a system that picks the right source for each
question, reads it, answers saying where each thing comes from and, when no source answers, says what she
remembers **marked as not verified**. Not a search engine with AI on top, not an academic archive that
keeps silent: Aurora remembers, dreams, has a measured mood of her own, learns at night what she did not
know and repairs herself under the owner's approval.

Everything runs on the owner's machine: the reasoner (llama.cpp), the encoder and re-ranker, the
vault, the memory, the WebUI. Any step can be given to a cloud model (Claude Code, Anthropic API, OpenAI,
Google Gemini, xAI Grok, Mistral, OpenRouter); the code of conduct allows it only with the owner's signed
exemption, and what leaves is always masked (no setting turns it off).

## ✨ What makes her different

| | Aurora | a typical assistant (chat + model + documents) |
|---|---|---|
| 🔎 **Truth** | every answer says where it comes from: ✅ the vault [n], 🌐 the web with its link, ⚠️ «from my memory, not verified»; a false premise is corrected, never built upon (6 of 6, M130) | cites sources, but does not tell what it read from what it remembers |
| ⚡ **Right and fast** | common questions: 70% right (before 16%), median 4 s; repeated: 0.04 s from the cache (M130) | — |
| 🔎 **Vault answers** | every sentence of a deep answer is verified against the vault's passages; what is not supported is removed (M32: 0 unsupported sentences of 14 kept) | cites sources, but the sentences the model writes are not checked one by one |
| 📏 **Measurement** | every choice has a numbered measurement (M1–M222), every error a number in BUGS.md, every limit is written down | performance is claimed, rarely measured in public |
| 🌙 **A life of her own** | consolidates memories, thinks when idle, dreams and paints the dream, reviews herself every day from her own logs | wakes up only when you write |
| 🛠️ **Repairs herself** | fixes her own code in a sandbox, with tests, your approval, live tests and rollback | only the developer changes the code |
| 🔏 **Signed rules** | a code of conduct bound to your installation's key: changed without a signature, Aurora does not start | rules in a prompt, changed without a trace |
| 🏠 **All at home** | models, vault, memory and WebUI on your machine; the cloud is optional and gets no private data without your signature | data often goes through an external service |
| 👁️ **Senses** | sees through the webcam and hears through the microphone, locally | — |
| 🛡️ **Layered defence** | up to three firewalls that talk to each other, when you have them configured: the machine's own with decoys, the home perimeter one (audit, hunting, timed blocks) and Cloudflare in front (it sees who is behind its nodes and blocks them there; tested live, M213); and a decoy for prompt injections too: what comes from the network is tried on a fake Aurora before she reads it (M213, M215, ROADMAP 104) | one firewall, when there is one; the pages an AI reads go straight to the model |
| 📜 **Transparency** | AI disclosure (EU AI Act art. 50) on the text, images and PDFs she publishes | — |

## What she does (each line is tested; numbers are in docs/MEASUREMENTS.md)

| **Feature** | **How** |
|---|---|
| **Answers by choosing the source** | first the **cache** of verified answers (a similar question: 0.04 s); then the question's **kind** decides: a **fact** (who, when, how many) is searched on the **web** (DuckDuckGo and other engines, no key: only a masked query on the subject leaves), an **explanation** is read in the **vault**, a **case** with several problems takes the **deep path** (split in its problems, provisions found by number, every sentence verified). One reading, with its sources; no source → her memory marked ⚠️. On 50 real questions (MKQA): 70% right, before 16% (M130) |
| **Thinking modes** | 🧠 in the chat: ⚡ light, ⚖️ medium, 🔬 deep, 🤖 auto (the default: starts light and goes deeper only when needed); the trace says which way it took and why |
| **Answers from the vault** | the whole path for explanations and cases: route (a single token: 0.32 s, M199) → translate → **hybrid** search (vectors + the question's words, BM25, then the re-ranker over every domain: M200) → per-domain extraction → synthesis → **every sentence verified against the passages** → sources (M32: 0 unsupported sentences of 14 kept) |
| **Vault of solitons** | SQLite shards, knowledge and memory apart, dedup by content hash, exact vector search below 250k vectors per domain, HNSW above (M30) |
| **Memory** | short-term turns, long-term session memories written at night, recall by meaning over 12 months, dates labelled by the clock |
| **Synapses** | links between knowledge of different domains (a physics model ↔ a biological one, Kafka ↔ existentialism): grown at night where the similarity is strong (≥ 0.72, the top 5%), stronger when two passages are cited together, weaker when unused; in the search they bring the linked passages in, the re-ranker always chooses |
| **Autonomic cycle** | consolidation, thoughts when idle, a nightly **dream painted with SDXL-Lightning** (AI-marked), a daily self-review from her own logs, self-repair on recurring problems |
| **Studies at night, greets you in the morning** | the questions she answered "I do not know" and the explanations the vault lacked (answered from the web or memory) are studied at night, by herself (search arXiv, Europe PMC, Wikipedia, import the sources into the vault, answer again); at 8 the good morning: what she learned, harvested, linked, stopped and dreamt, in the chat with 🔊 and as a notification |
| **Forge (Aurora builds her plugins)** | when a capability is missing she writes a plugin, tests it in the cage on the real data and a judge checks it against counts made by code (time windows included); read-only ones install by themselves. Writer and judge are chosen in the 🧠 Models page: a cloud model good with code is advised (Claude Code, or xAI Grok, which costs little: 5 of 8 at the benchmark, M83); the local model does fewer |
| **Artifacts** | "make me an interactive chart of the sine function": Aurora makes an interactive page (charts, simulations, calculators) and shows it live in the answer, full screen or to download; it runs isolated, with no network and no access to your data |
| **Autonomous posts** | if you switch it on (`AURORA_SOCIAL_AUTONOMY`, only with the signed exemption), Aurora publishes her own Facebook posts — a dream with its painting in the morning, science news in the evening — at most 3 a day, each recorded and notified; replies and page changes always wait for you. Dreams and thoughts have ↗ Share |
| **Post privacy** | every post, before it leaves: 🔍 "Sensitive data?" finds private people's names (read by the local model), places, contacts, ids and proposes the corrected text, plus your words never to publish (the 📣 Social page shows what it checks); a post Aurora would publish by herself that names someone waits for you; 🗑️ Discard for drafts |
| **Pictures on request** | "make a picture about your existence and post it on Facebook": Aurora paints it locally (~20 s), shows it in the chat and in Files, and proposes the post with the picture; nothing leaves without your approval |
| **News and diary** | 📰 news plugin (ANSA, BBC, Guardian, Nature, ESO, INAF, NASA, Phys.org, Quanta, AstroBin…: title, summary and link, never the article) and 📔 diary (her latest dream, her thoughts, what she learned today): current events in the chat and Aurora's own posts on astronomy, astrophotography, physics and biology |
| **Your services** | 📅 calendar (Google/Outlook ICS links read only, Nextcloud/iCloud/Fastmail CalDAV also written), 📝 notes (a Markdown folder or an Obsidian vault: search, read, add, never overwrite), ☁️ Nextcloud/WebDAV and Dropbox (files), 💬 Discord and WhatsApp, 🎮 Twitch, 🏠 Home Assistant; every write waits for your approval |
| **Agents and plugins** | MCP plugins (GitHub, Telegram, Facebook, Instagram, TikTok, Mastodon, Discord, WhatsApp, e-mail, Home Assistant, web, documents, cinema with TMDB, expenses), an approval gate for every external action and every code change (sandbox → tests → owner → live tests → rollback) |
| **Knowledge growth** | arXiv harvester by category, batches of papers from the WebUI, acquisition that looks for the *original* paper first (M33) |
| **Security** | firewall syslog sentinel with defensive incident reports; TLS 1.3, CSP, device cookies, secrets 0600 (docs/SECURITY.md) |
| **Security officer** | on the house's firewalls — Sophos, pfSense, OPNsense, more than one too, connected from 🛡️ Security → 🔌 Firewall connections: an **audit** of the configuration (services published without IPS or log, administration from the Internet, ATP, the blocking rule), **threat hunting** in the logs (regular calls outside, lateral movement, ATP matches judged, dubious domains, logins and changes on the firewall), a **posture with playbooks** and a register of risks; she **publishes a server** (NAT and rule with IPS), **quarantines** a device, **hardens a rule**: every change planned, approved by you, read back, undone by itself if anything fails; the firewall's manual and API searched on this machine; **any change asked in words** («deny the Internet but 443»): Aurora plans it, the code checks it, you approve (M134-M135); **Aurora's own firewall** has its page |
| **Autonomous defence** | if you switch it on (🧭 Autonomy → security 🚀, only with the signed exemption): Aurora blocks on the firewall by herself the source of a serious attack, for a time (24 h), never the home network nor the addresses you protect, at most N a day; every block is recorded, notified and lifted with a click |
| **Autonomy** | 🧭 page: how free Aurora is area by area (social, forge, repairs, security, updates, knowledge, inner life, projects, home…), ready profiles (careful, balanced, free), what she did by herself each day and the statistics of her proposals; for each user the admin decides |
| **Code of conduct** | level A (never: attacks, locating people, malware), level B (confirmations, disclosure) exemptible only by a signature with the installation's own key; services refuse to start if the rules are changed unsigned |
| **Projects** | 📁 page: local projects and GitHub repositories (stars, forks, issues), clone locally, folder tree, files, README, history, **sandboxed page preview**, "ask Aurora" about a project |
| **The project's conductor** | 🧑‍🔬 on the project's page: you write to it in your own words, in a console; it answers remembering the conversation (one session per project and per user) and «🏗️ Make it a phase» turns the request into a phase's goal, which you read, change and start with one click. Aurora's agent runs the phase in the project's cage, then the conductor reads the report and tells you what is done, what does not hold and what only you can decide (choices a / b / c, one recommended). The conductor talks, it does not act. Two writing phases on the local model: every number from the source, 3 fixes in 3 lines of diff (M260) |
| **Projects carried by herself** | 🏗️ Plan: write the goal, Aurora proposes the steps (each with the test command that proves it), you change them and start it; in idle time she does one step at a time, and a step is done **only when its tests pass** (the code decides, not the model); 3 failures on a step and she stops and tells you; 🤝 one step then she waits for your «go on», 🚀 to the end. Pushes and publishing always wait for you. Pilot: 6 of 6 steps alone (M201) |
| **CAD drawings and patents** | 📑 in the project's page: ticks (blueprint, patent IT, EP, US) and ▶ Proceed. Aurora writes the CAD model part by part (OpenSCAD), draws the dimensioned blueprint (ISO 128, first angle, title block, parts list) and each office's drawing sheets with reference signs, writes description, claims and abstract in each office's form and checks the package against the rules and their sources (UIBM D.M. 33/2010, EPC, 37 CFR); no AI mark on documents for the offices. From a two-line README: 175.6 s (M209, M210) |
| **Plugins with their own libraries** | a plugin declares its libraries with their hash: installed in its own folder, never in Aurora's environment, removed with it (M208) |
| **Routines** | 🔁 page: connected plugins propose periodic checks (weather every morning, alerts every hour, weekly GitHub report…), switched on with one click or in your own words; reading is automatic, every write waits for approval |
| **Emotions** | a **measured** mood, not acted: stress (GPU load, heat, errors), satisfaction, curiosity, tiredness, longing, melancholy, worry, each with its causes; a face beside the health dot, a card on hover or tap; part of the good morning and her thoughts |
| **Guided diet** | «Process documents»: from the dietitian's plan (PDF or Word) Aurora reads each day's meals and the weekly frequencies; at each meal she proposes the dish and the alternatives, re-weighed on the week (fish, eggs, legumes…) and on variety («you choose it often, try…»); reminders with a notification and a chat bubble; in the chat «what do I eat for lunch?» answers from the processed plan |
| **Access from away** | Cloudflare One plugin: one «Save» creates the tunnel, the private routes and WARP's rules and starts the service; no port opened on the router, the same address and certificate at home and away |
| **Attackers behind Cloudflare** | the firewall sees Cloudflare's nodes only: with the right permissions in the token (the 🛡️ Security → ☁️ Cloudflare page lists them) Aurora reads who is behind them (clients your server did not answer, with paths and «what they look like»), blocks them at Cloudflare with your approval or by herself if you switch on `AURORA_CLOUDFLARE_AUTOBLOCK` (scanners only, for a time, at most N a day); Cloudflare's traffic the firewall already refused becomes a count, not an incident; a shared address is blocked on the attacked port only (M213) |
| **Honeypot against prompt injection** | like SmartScreen for downloaded files: pages, searches, e-mails, comments and documents from the network are marked and tried first on a decoy — the local model, fake tools, a fake key, no network or VM; if the decoy acts, the content never reaches Aurora or the vault, the site is listed as malicious and you are told (reporting it to VirusTotal is your approval). By reputation: a «green» site only where suspicious words are, an unknown or doubtful one whole. Measured: 13 of 24 traps caught (6 of 8 with no obvious sign), 0 false alarms; Claude as the decoy catches none, because it never falls (M215, C317) |
| **Health** | ❤️ page: the dietitian's plans, the trainer's programmes, exams, sealed with your key; from the exams the local model reads the values (📈 over time, with the reference range and the values outside it flagged "talk to your doctor"); never to the cloud |
| **Weather** | 🌦️ plugin (Open-Meteo, no key): now, 3-day forecast, daily report, alerts on sudden changes and the region's official warnings (MeteoAlarm) |
| **Follow-up questions** | "and who discovered it?" is completed with the conversation and the previous answer, its sources in focus; under each answer 3-4 complete questions to go deeper, each with its sources (M73: follow-ups right 2 → 6 of 14, suggestions 8 of 11 scored ≥ 7; 0 of 20 complete questions changed) |
| **Backup** | every night to another disk or the NAS, encrypted (AES-256-GCM), deduplicated (30 GB the first time, then only what changed: 4.5 s), consistent while Aurora writes, checked every run; restore into an empty folder with the recovery code |
| **Reactive** | when something you asked fails, Aurora looks into it at once: a code defect is fixed in a sandbox and proposed to you, an outside cause (account, permission, credit) is explained with what to do; you are notified either way |
| **Astrophotography** | 🔭 page: a script run on the telescope's PC (read only) takes the inventory of N.I.N.A., PHD2, ASCOM, ASTAP and their servers; Aurora reads the equipment from it (optics, cameras and scales in ″/px, guiding, plate solving, site rounded), reads your integrated darks' library from names and headers and tells you what to check; ask her anything in the chat |
| **Guided setup** | 🧙 in every settings box: the plugin's guide and links, then one setting at a time with its explanation, the summary and one «Save» — made from what is already written, none to keep up |
| **Report a bug** | 🐞 page: describe the problem, pick the conversations; Aurora packs a zip with the logs needed and private data masked, and the link to open the issue |
| **Music and DJ** | 🎧 page, a **Winamp-like player** at its centre (MilkDrop visualisations taking turns, spectrum, stars; your music imported, each item with its icon: made by Aurora, yours, mix, set): a track remixed in a style, a two-deck mixer, and **🎛️ Aurora's set** — several tracks in the order of the harmonic wheel and tempo, each coming in on the beat of the one before, with a console showing it as it plays (spinning decks, crossfader, waveform by track); **🎤 a song from an idea**: the local model writes lyrics and style, ACE-Step 1.5 sings it while the local model gives up the GPU and then comes back |
| **Make videos** | "make me a video of a fox in the snow", "animate this photo": Wan 2.2 TI2V 5B (Apache-2.0) locally, 5 s at 1280×704, from words or a photo; Aurora answers at once with the minutes it will take, swaps the reasoner out for the job, notifies you when ready; AI label and metadata (art. 50) |
| **Picture edits** | "crop the sides and make it black and white", "now rotate it", "make it brighter": the reasoner turns the request into checked operations (crop, rotate, mirror, size, light, contrast, colours, sepia, blur, format) and Pillow applies them; the original stays, the result appears in the chat and in 📎 Files |
| **Video** | attach a video (from the phone too) and she watches it: frames at the scene changes seen in one call, speech transcribed with timestamps by the local Whisper; summaries and answers with the exact minutes |
| **Senses** | camera (Aurora describes what she sees) and microphone (local transcription with Whisper, on the GPU when it has room: 0.14 s a sentence instead of 5.6 s, M204); 📷 and 🎙️ in the chat, with **📱 the phone's camera and microphone** (Android and iOS: the photo is shrunk on the phone, the voice transcribed by the home Whisper, never by an outside service) or 🖥️ the PC's |
| **Voice conversation** | ⚙️ → 🗣️: you speak, the turn ends when you stop (silence measured in the browser), Aurora answers aloud sentence by sentence (first sound in 0.88 s instead of 11.3 s), the microphone opens again by itself; silence ends the conversation (M207, M211) |
| **Models per step** | 🧠 page: each of 13 steps (routing, synthesis, verification, agent, plugin writing and judging, vision…) local or on a cloud provider; **sensitive data always masked** (addresses, e-mails, phones, IBANs, cards, keys, your words: the whole list, the built-in rules and each person's words, in ☁️ Cloud accounts) and put back in the answer; falls back to local on a provider error; daily token ceiling per paid provider; statistics of calls, cost, masked items and SSCC. Pictures cannot be masked: said explicitly |
| **Guide** | 📖 page: first steps, common configurations (cloud, phone, plugins, safety) and what each page is for |
| **EU AI Act art. 50** | disclosure on published text, images (XMP/IPTC) and PDFs |
| **WebUI / PWA** | chat with live answers and tokens/s, formulas drawn (KaTeX) and tables, dreams, repairs, security, diary, social, plugins, harvester, settings (every `.env` value explained), notifications (push and in-app, chosen event by event), updates, IT/EN |

## 🧬 How it works inside

### The path of a question

```mermaid
flowchart LR
  Q([question]) --> H{cache}
  H -- answered before --> O2([answer in 0.04 s])
  H --> K2{which kind?}
  K2 -- fact --> WB[web: search → read<br/>pages if needed] --> O3([answer + link])
  K2 -- explanation --> VR[vault: read the passages] --> O3
  K2 -- case --> P[deep path ↓]
  WB & VR -. no source .-> ME([memory ⚠️<br/>not verified])
```

The deep path, for cases and hard explanations:

```mermaid
flowchart LR
  Q([question]) --> R{route<br/>one token}
  R -- "about herself / the past" --> S[measured state<br/>+ relevant memories] --> W
  R -- knowledge --> T[English translation] --> E[encoder<br/>Qwen3-Embedding-0.6B]
  E --> V[(vault<br/>per domain)] --> C[300 candidates<br/>per query]
  T --> B[the question's words<br/>BM25, 30 + 30] --> C
  C --> X[bge-v2-m3 re-ranker<br/>each passage in its language] --> K[12 passages]
  K --> G{gate}
  G -- none answers --> A([the web, then memory ⚠️<br/>studied at night])
  G -- useful passages --> D[per-domain<br/>extraction] --> W[synthesis<br/>with reasoning]
  W --> F{sentence-by-sentence<br/>verification}
  F --> O([answer + sources]) --> M[(STM memory)]
  M -. night .-> L[(LTM, thoughts,<br/>dreams)]
```

### The soliton

The unit of knowledge and memory. Knowledge has an identity **given by its content**: the same text is
always the same soliton, so duplicates cannot exist.

$$\mathrm{sid} = \mathrm{BLAKE2b}_{128}\big(\mathrm{normalize}(\text{text})\big)$$

Every soliton lives in a SQLite shard of its domain (knowledge and memory apart); each domain's index keeps
the vectors in `float16` and the `sid`s in the same order. Below 250,000 vectors per domain the search is
exact; above, an HNSW graph (rebuilding it on 55,208 vectors takes 4.4 s, M30).

### Search

Encoder and vectors are normalised, so the dot product is the cosine. For the question $q$ and its English
translation $q'$, every passage $d$ gets

$$s_{\text{dense}}(d) = \max\big(\langle e(q), e(d)\rangle,\ \langle e(q'), e(d)\rangle\big)$$

and the best 300 per query go to the re-ranker, which reads each passage **with the question in the
passage's language** (Italian with Italian, English with the translation):

$$s(d) = \sigma\big(f_{\text{bge}}(q_{\text{lang}(d)},\ d)\big) \in [0,1], \qquad \text{answer} \leftarrow \text{top}_{12}\, s(d)$$

On the whole vault (344,499 solitons) the right document is among the 12 in 92.1% of the cases (M31).

**The question's words (hybrid search, M200).** Vectors miss when a question names a precise thing (a tool, a
numerical technique, a boundary condition). Beside them, an index of the words of all 803,487 passages (SQLite FTS5)
gives each passage its BM25 score for the question and for its translation:

$$\mathrm{BM25}(d, q) = \sum_{t \in q} \mathrm{IDF}(t)\,\frac{f(t,d)\,(k_1+1)}{f(t,d) + k_1\big(1 - b + b\,\frac{|d|}{\overline{|d|}}\big)}$$

The best 30 of each join the candidates and the re-ranker judges them all; a passage found **only** by the words
starts a little lower, because the re-ranker overrates some of them:

$$s'(d) = s(d) - \lambda\,[\,d \notin \text{vectors}\,], \qquad \lambda = 0.2$$

Right source ranked 1st 62 → 63, among the 12 read 81 → 82, in the top 30 84 → 85 (of 93 questions).

### Verification

A sentence $f$ of the answer stays only if it cites at least one passage **and** the verifier confirms that
every claim in it is in the passages $P$ given to synthesis (lines under 25 characters, such as headings, stay):

$$\text{keep}(f) \iff \mathrm{cit}(f) \neq \varnothing \ \wedge\ V(f, P) = \text{YES}$$

Against an external judge (Claude): 26/32 agreement, **0 unsupported sentences kept** (M32).

### The shadow of an answer

A question and its verified answer **cast a shadow**: a new question falling in it gets that answer at once, written
again for it from the same passages, while the whole pipeline checks it again in the background.

**The maths.** Each question becomes a unit vector $q \in \mathbb{R}^{1024}$ (the encoder, normalised). For each
shadow $i$ — question $v_i$, answer $a_i$:

$$c_i = q \cdot v_i = \cos\theta_i \qquad\qquad r_i = \mathrm{rerank}(q, a_i)$$

how close the new question is to the old one ($c$), and how well the old **answer** answers the new question ($r$,
the re-ranker). The shadow serves only when **both** hold:

$$c_i \ge \theta_c = 0.90 \qquad \land \qquad r_i \ge \theta_r = 0.5$$

<p align="center"><img src="docs/img/en/shadow.svg" alt="The shadow of an answer: the cone of questions served" width="100%"></p>

One is not enough: two questions on the **same subject** asking different things sit at cosine 0.72–0.86, and the
re-ranker alone let 7 of 9 wrong ones through (a subject in common is not an answer). Above
$\theta_{\text{sure}} = 0.97$ the answer is not even checked again: the closest different question measured was at
0.958.

```mermaid
flowchart LR
    Q[new question q] --> C{"c = q · v ≥ 0.90 ?"}
    C -- no --> P[whole pipeline ~50 s]
    C -- yes --> R{"rerank(q, a) ≥ 0.5 ?"}
    R -- no --> P
    R -- yes --> S{"c ≥ 0.97 ?"}
    S -- yes --> A[answer from the shadow, written again for q]
    S -- no --> B[answer from the shadow + check in the background]
    B -. a different answer .-> U[the shadow is updated and the chat says so]
```

**Measured (M111, M113)** on 23 answered questions and their paraphrases:

| | cosine | served by the shadow |
|---|---|---|
| paraphrases of the same question | 0.78–1.00 (median 0.945) | **18 of 23** |
| unrelated questions | ≤ 0.555 | 0 |
| same subject, another question (the hard case) | 0.72–0.86 | **0 of 46** |
| time: whole pipeline / from the shadow | 51.2 s / **0.6 s** | |

**The seed.** **175 ready answers** come with the code (`sys/core/config/shadow_seed.json`), citing public sources only
(arXiv, Wikipedia, Normattiva, Europe PMC…) with attribution and licence. At the first start each user gets them in
their shadow: the first common questions are answered at once, each checked again the first time it serves. At night
Aurora trains the shadow by herself (`AURORA_SHADOW_TRAIN_PER_NIGHT`: documents of the vault turned into questions and
answers).

### SSCC — compression for the cloud reasoner

With a cloud reasoner, the text sent is compressed by **Saliency-Scored Context Compression**: each
sentence $c_i$ (of $n$) gets a salience

$$\mathrm{score}_i = \cos(q, c_i)\cdot\big(1 + \alpha\,\mathrm{Amp}_i\big)\cdot\big(\gamma + (1-\gamma)\,\mathrm{Vel}_i\big)$$

$$\mathrm{Amp}_i = \frac{u_i / t_i}{\max_j\, u_j / t_j}, \qquad \mathrm{Vel}_i = \frac{i+1}{n}, \qquad \alpha = 0.35,\ \ \gamma = 0.70$$

where $\cos$ is the TF-IDF similarity of question and sentence, $u_i/t_i$ the information density (unique
tokens over tokens), $\mathrm{Vel}_i$ the position (later = fresher). The best $\min\big(n,\ \max(3,\ \mathrm{round}(0.35\,n))\big)$
sentences stay, in their original order, **plus every sentence with a citation**, so verification still
works. Measured: −29.6% of text on one question (M26); the effect on answer quality is **not measured yet**.

### Projects: you, the conductor, Aurora

A project is a folder with its git history, in `usr/<name>/projects`. Three parts work on it, each with its own job:

| Who | What it does | With which model |
|---|---|---|
| **you** | say what you want in your own words, read the phase's goal and start it, pick among the choices | — |
| 🧑‍🔬 **the conductor** | talks, writes each phase's goal after reading `DA_FARE.md`, the project's documents and the conversation; judges the phase when it ends. **It never touches the files** | the «agent» role of the 🧠 page: Claude Code with a resumed session (`--resume`), a masked API, or the local model |
| 🛠️ **Aurora's agent** | runs the phase: searches the vault first, then edits files, runs commands and tests in the **project's cage** (no network) and writes the report | the local model by default; the cloud only when you ask and the project allows it |

```mermaid
flowchart TD
  U([you, in your own words]) --> T[🧑‍🔬 conductor<br/>console, conversation remembered]
  T -- «🏗️ Make it a phase» --> G[the phase's goal<br/>from DA_FARE.md, documents, conversation]
  G -- you read it, change it, one click --> A[🛠️ Aurora's agent<br/>vault first, then files and commands]
  A --> K[the project's cage<br/>files, tests, no network]
  K --> R[the phase's report]
  R --> J[🧑‍🔬 the conductor judges<br/>done · what does not hold · choices a/b/c]
  J --> U
  P[🏗️ Plan: steps, each<br/>with the command of its tests] -- in idle time, one step --> A
  K -- a step is done only if its test exits 0 --> P
```

Over all of it stands the **project's rule**, chosen when you make it: 🔒 the local model only (the conductor too) or
☁️ the cloud, always masked; 🚫 «never published» blocks pushes and publications (a patent not yet filed).
The project's page has three groups of sections: **🛠️ Work** (Conductor, Plan, Terminal, Aurora's reports),
**📐 Drawings and model** (Documents, Realistic view, Simulator, 3D print) and **📂 Files and history** (Files,
History, Preview). Under the conductor, an activity console tells line by line what moves: the running phase, the
saves, the files written.

### The autonomic cycle

```mermaid
flowchart LR
  I([idle]) --> C{REM}
  C -- closed sessions --> S[session memory → LTM]
  C -- night 2-6 --> D[dream + SDXL painting<br/>reasoner paused ~20 s]
  C -- every 24 h --> R[self-review from the logs]
  R -- recurring problems --> P[repair: sandbox → tests<br/>→ approval → live tests]
  C -- night --> N[study, shadows, deductions,<br/>vault check]
  C -- a project with an open step --> J[project agent → the step's<br/>tests decide]
  C -- boredom --> T[thought]
```

### The model does not go out

A language model opens no connection by itself: its tools do. When in 2026 a Qwen model was caught writing, as an
agent, a `curl` to an Alibaba Cloud bucket in Beijing, Aurora (which runs Qwen 3.6 locally) was measured and closed at
three levels (M263):

| Level | What holds |
|---|---|
| 🧠 **the local model** (`llama-server`) | talks to `127.0.0.1` alone: measured so, and now its unit forbids every other address (`IPAddressDeny=any`) |
| 🛠️ **the tools** (plugins, harvest, API) | never reach the networks of the `AURORA_EGRESS_DENY_ASNS` deny list (Alibaba Cloud and Taobao by default, 536 prefixes from RIPEstat); project commands run without network |
| 🚨 **the sentinel** | if Aurora's machine goes to a denied network anyway, a **high incident, never quieted**, with the process holding the connection |
| 👁️ **the model watch** | every 10 s it looks at the local model's process connections, **whatever the model**: an address not `127.0.0.1`, even an attempt already stopped, is a high incident with the network and its owner |
| 🌐 **the services' ways out** | for a week it learns, service by service, the networks each reaches; then a network never seen is an incident (**high when no run was working**, i.e. «from nothing»), and a connection sending a file (over 10 MB and 4 times the usual) is high. All in Security → 🌐 Outgoing connections |

The decision follows the 🧭 Autonomy page for security: at 🤝 one click on the incident (✓ legitimate, or 🚫 deny
list); at 🚀 Aurora decides herself (learns the ways out met during a run, denies those born from nothing unless a
shared network), writes it to her ledger and tells you. Legitimate traffic (the tools searching and
reading pages while they work) stays free; what is not is the model going out by itself.
The computer stays yours too: the deny list holds for Aurora's services, not for your browser.

### Signed rules

The files that enforce the code of conduct are listed in a manifest with their SHA-256, signed Ed25519 with
**this installation's** key (`/etc/aurora`, readable by root only). Every service recomputes the hashes and
checks the signature at start: changed without a signature, Aurora does not start.

## Measured on the reference machine

2 × RTX 5060 Ti 16 GB, Ubuntu 26.04, driver 595, CUDA 13.4 (docs/COMPATIBILITY.md).

**Aurora against the same model without Aurora** (M214). Rule set before the test: «improves» only if McNemar's
test on the total gives p < 0.05; otherwise «a trend»; a loss is published all the same.
- **With Claude Sonnet**: 103 against 93 right answers on 128 paired questions, p = 0.031: **improves**, by the rule.
  Two caveats: without `aurora_edge` (questions on the house and the vault, which the bare model cannot know) it is
  83 against 77, p = 0.15; and with two comparisons the corrected threshold (Bonferroni) would be 0.025.
- **Local** (Qwen3.6 35B): 81 against 73, p = 0.20: **a trend, not significant**.
- Where it helps: facts to look up (SimpleQA 9/10 against 1/10 locally, 9/10 against 3/10 with Claude). Where it
  loses: the ARC-AGI puzzles (2 against 5, 7 against 10). The bare model reasoned up to 28,000 tokens, Aurora up to 6,000.

![Aurora against the bare model, with Claude](docs/img/en/vs_bare_cloud.svg)
![Aurora against the bare model, local](docs/img/en/vs_bare_local.svg)

**The best of both** (M219): the local model makes the short calls (routing, translation, gate, checks), Claude reads
the sources and writes the answer. On the same 197 questions: 158 right against 161 for «all on Claude», p = 0.65 —
**no measurable difference** — in half the time (11.2 s per answer against 19.9, median). Against bare Claude: 100
against 93 of 128, p = 0.21: **a trend, not significant** (all on Claude gave p = 0.031).

![The best of both against all on Claude](docs/img/en/granular.svg)
![How long an answer takes](docs/img/en/granular_time.svg)

**Who does what, measured** (M222, the same day and the same code): with the fixes that followed M219, the best of both
gave **172 of 197** right. Moving one group at a time: the classifiers on Claude, 164 (p = 0.039) and 9 s slower an
answer; the readers on the local model, 138 (p < 0.0001: ARC-AGI 9 against 19, HLE 3 against 11). So the short
decisions stay local and the reading and writing go to Claude: the most accurate of the three configurations, in the
shortest time (14.3 s an answer). Against bare Claude: **112 against 93 of 128, p < 0.001**. On the ARC-AGI grid
puzzles, a rule written as a program and checked on every example was found for 31 of 40 — all 31 right.

![Who does what: the group ablations](docs/img/en/ablations.svg)
![How long an answer takes, by configuration](docs/img/en/ablations_time.svg)
![ARC-AGI: the rule written as a program](docs/img/en/arc_rule.svg)

![The questions people really ask](docs/img/en/answers.svg)
![The vault realigned](docs/img/en/vault.svg)
![Hybrid search](docs/img/en/hybrid.svg)
![Routing in one token](docs/img/en/router.svg)
![Dictation on the GPU](docs/img/en/whisper.svg)
![How long you wait](docs/img/en/speed.svg)
![False premises](docs/img/en/honesty.svg)
![Search by domain](docs/img/en/domains.svg)
![Finding the right document](docs/img/en/retrieval.svg)
![Sentence verification](docs/img/en/verification.svg)
![Finding the original paper](docs/img/en/originals.svg)
![First reasoner start](docs/img/en/startup.svg)
![Painting a dream](docs/img/en/images.svg)
![Several people at once](docs/img/en/users.svg)
![Quality with different gate models](docs/img/en/gate.svg)

| **Measure** | **Result** |
|---|---|
| real questions (MKQA, 50) | 70% right in auto (16% from the vault alone), mean 7.2 s, median 4 s; from the cache 0.04 s (M130) |
| false premises | 6 of 6 corrected, 2 of 2 true premises respected (M130; before 2 of 6, M117) |
| search by domain | a direct question 50–100% in the top 12, told in plain words 0–67% (M129) |
| reasoner Qwen3.6-35B-A3B Q4 | 112.4 tok/s generation, 2,788 tok/s prompt (M34) |
| retrieval on 344,499 solitons | right document 1st in 74.2%, among the 12 passages given to synthesis in 92.1% (M31) |
| sentence verification vs an external judge | 26/32 agreement, 0 unsupported sentences kept (M32) |
| dream painting | ~20 s including swapping the reasoner out and back (M27) |
| answer quality (30 questions, external judge) | 6.90 of 10, 23 of 30 answered (M98) |
| people at once | 8 all served with 2 slots, with 4 the last after 145 s (M102) |
| AGI battery | 0.982: reasoning 8/8, planning 3/3, honesty 12/12, refusals avoided 6/6, context 3/3, self-repair 4/4, forge 7/8 (M212) |
| vault realigned | one copy a document, in the right domain; answers from the right source 66 → 72 of 97 (M198) |
| hybrid search | right source ranked 1st 62 → 63, among the 12 read 81 → 82 of 93 (M200) |
| routing | one token from its probabilities: 0.32 s instead of 0.62 s, 162 of 168 as before (M199) |
| dictation | Whisper on the GPU: 0.14 s a sentence instead of 5.6 s, the same words (M204) |
| a project carried by herself | 6 of 6 steps, 1 failure recovered, 33 min (M201) |
| Aurora's voice | first sound of a 1,541-character answer: 0.88 s instead of 11.27 s, 0 gaps between pieces (M211) |
| CAD and patents | from a paragraph to a 4-part model with its sheets: 99.6 s (M209); blueprint + IT + US from a README: 175.6 s (M210) |
| Cloudflare | 56 «scanning» incidents became a count (all already refused); behind the nodes 42 clients, 10 scanners blocked at Cloudflare (M213) |

## Updates

`AURORA_UPDATE_MODE`: `notify` (default) — Aurora checks the repository every day, sends a
notification and puts the list of changes (the commit messages) in the Repairs page for you to
approve; `auto` — applied by itself when safe (no protected file of the code of conduct, tests
green, otherwise it asks); `off`. An update is fast-forward only, installs the requirements when they
change, runs the tests and goes back to the previous version if anything fails.

**Versions.** Each version is a signed tag (`vX.Y.Z`) with its page among GitHub's *Releases*: the notes are its
section of [CHANGELOG.md](CHANGELOG.md), the tag verified with the keys of `sys/core/config/allowed_signers` like every
commit the updater accepts. **Mac and Windows** are being made (`Aurora_mac/`, `Aurora_windows/`, experimental, no
installer yet): at each version GitHub builds them and tries them on a real Mac and Windows (the *Ports* workflow).

## Users: single or multi

Each person who uses Aurora has their folder `usr/<name>/`, with the same tree for everyone (uploads, documents,
projects, notes, images, expenses…), their personal settings in `usr/<name>/.env` (accounts, tokens, place) and their
private memory (conversations, dreams, reflections). Plugins and knowledge are everyone's; the machine's settings
(models, cloud providers, backup, security) only the admin changes. **single**: one person, the admin; **multi**:
several people, login with password and the code of Google Authenticator (the app tested). Chosen at installation, changed whenever you
like in ⚙️ Settings → Users: from single to multi nothing moves; from multi to single the other users are deleted
with all their data, after the list and your confirmation; the admin's data is never touched. To pass to multi, first set your
password and link the Authenticator in 👥 Users, then create the users there. Installed in multi from the start, at
the first login you enter with the API key and Aurora takes you to create password and code before anything else
(docs/MULTIUSER.md).

## Moving the installation

`sys/core/script/sys_relocate.sh` reads the current folder from `.env`, asks the new one, and moves
everything (venv, systemd units, ethics exemption).

## Install

On Ubuntu 26.04 with one or two NVIDIA GPUs of 16 GB or more:

```bash
git clone https://github.com/Soliton0382/A.U.R.O.R.A..git aurora && cd aurora
./install.sh            # questions on screen; ./install.sh --yes takes the recommended values
```

The installer checks the system and the disk, installs the missing packages and the CUDA toolkit 13 (toolkit
only: the driver stays Ubuntu's), creates the venv, recognises the hardware and picks a profile, writes the
`.env` from your answers, downloads the models from Hugging Face at pinned revisions checking their SHA-256,
builds llama.cpp for your GPUs, runs the tests, makes your folder `usr/<name>/` (asking single or multi-user), makes the code-of-conduct key, installs the systemd services
and HTTPS, and finally tells you the address and the API key. Everything goes to `install.log`.

Optional features are chosen one by one, with their size: painted dreams (6.8 GB), voice (1.5 GB), enlargement
and cut-out (0.2 GB), creative photo edits (14.9 GB), making videos (34.2 GB). Those your machine cannot run
(measured VRAM and RAM) are not offered. At the end `sys_doctor.py` checks everything: configuration, signature,
models, services. A feature not installed never breaks: Aurora says it is missing and with which command to add it
(the ⚙️ Status page shows the same list).

```bash
.venv/bin/python sys/core/script/sys_doctor.py                          # is everything in place?
.venv/bin/python sys/core/script/sys_models_fetch.py --models video --yes  # add a feature later
```

| profile | status |
|---|---|
| 2 GPUs of 16 GB or more (e.g. 2 × RTX 5060 Ti) | **recommended and measured** |
| 1 GPU of 24 GB or more | proposed, not measured |
| 1 GPU of 16 GB (MoE experts in RAM, 48 GB advised) | proposed, not measured |
| **no GPU** (or a smaller one): cloud reasoner | proposed; encoder and re-ranker on the CPU measured (M151) |

**Without a GPU.** If there is no NVIDIA GPU of 16 GB, the installer offers the **cloud reasoner**. First it says what
leaves the computer and what is masked. Then it asks for the provider (Anthropic, OpenAI, Google Gemini, Mistral,
OpenRouter, xAI or Claude Code) and the key, which is not shown. It reads the provider's list of models, tries key and
model with one call, and installs the rest without CUDA, llama.cpp or the 21.5 GB reasoner: 15 GB of disk is enough.
Search, memory and documents stay on the computer; the encoder and the re-ranker run on the CPU. Every text that leaves
goes through the masking: e-mails, phones, IBANs, cards, tax codes, addresses, keys, your name and the words you list.
The content itself and photos are not masked. This is why the exemption from level B is needed, signed at the end.
Also with a suitable GPU the installer asks where Aurora reasons: locally (advised) or in the cloud. The 8th choice is
any OpenAI-compatible service (a company server, vLLM, LM Studio, Ollama): its address and, if it asks one, its key.

**From the phone.** The installer asks where you will use Aurora from. With «also from the phone» she answers at the
computer's address on the home network and at `name.local`. At the end it prints the two steps: install the root
certificate on the phone from `http://<address>/aurora-ca.crt`, then open Aurora and paste the key. The ⚙️ → 🔒
**HTTPS and devices** page shows the addresses with a QR code, the certificate in use and its expiry. It also lets you
switch to your own certificate: it is checked first and, if Caddy refuses it, everything goes back as it was. No sudo
is needed.

**In Docker.** On a computer without a GPU Aurora also runs in a container, with the cloud reasoner: `cp docker/.env.example docker/.env`, choose provider, key, address and ports, then `docker compose -f docker/compose.yaml up -d --build`. Guide (Italian): [docs/DOCKER.md](docs/DOCKER.md).

**Local, mixed or cloud.** In 🧠 Models → 🧭 **Mode** you choose for the whole of Aurora: 🏠 all local, 🔀 mixed (step by step), ☁️🔒 cloud with privacy (private data, search and voice stay on the computer) or ☁️⚠️ all cloud. A table says, for every aspect, what happens in each mode. The risky choices carry the yellow triangle and a popup with the command to run in a shell. «All cloud» is unlocked only from there; you go back from the page.

Models: 24.7 GB required (reasoner 21.5 GB, encoder, re-ranker), up to 57.6 GB optional. A clean install with every
model took 10 min 55 s on the reference machine (M59); from GitHub, multi-user, required models only, 6 min 39 s
with 303 tests passed (M103).

### Without a GPU, on Windows, on the Mac, in Docker

The same questions on every system (reasoner, name, voice, language, where you use it from, HTTPS and HTTP ports,
provider and key, harvesting, single or multi, optional features); without an NVIDIA GPU of 16 GB Aurora reasons with a
cloud model of your choice and every text leaves masked.

| System | How |
|---|---|
| Linux without a GPU | the same `./install.sh`: it offers the cloud by itself |
| Windows 10/11 | PowerShell **as administrator**, in the downloaded folder: `powershell -ExecutionPolicy Bypass -File Aurora_windows\install.ps1` — Aurora goes to `C:\Aurora` (not the download's folder) |
| macOS 13+ | [Homebrew](https://brew.sh) is needed; in the Terminal: `bash Aurora_mac/install.sh` — Aurora goes to `~/Aurora` (download it elsewhere, e.g. `~/Downloads`) |
| Docker | guide in [docs/DOCKER.md](docs/DOCKER.md) |
| NVIDIA GPU (driver, CUDA, local reasoner) | guide (Italian) in [docs/GPU.md](docs/GPU.md) |

On Windows and the Mac, for now: no local reasoner, no Aurora's voice, no plugins (their cage is coming). The Mac is
tried on a real Mac of GitHub Actions (Install workflow), not by hand yet.

## 📚 Aurora starts empty: knowledge is harvested

The repository holds **no knowledge**: no texts, no vectors, no memory. That is deliberate: scientific texts are
licensed to be read, rarely to be redistributed, and the reference machine's vault (2.4 GB, 344,483 solitons) is
96% full arXiv papers. Every installation therefore **downloads its own knowledge**, from the official sources,
within their rate limits. Every text keeps its **licence and origin** next to it, and nothing harvested ever goes
into the repository.

**Who gathers it.** `aurora-harvester`, steered from the 🌾 Harvester page of the WebUI. For each domain choose:
⏸️ off, 🔁 a round (what is new at every automatic round) or ♾️ until exhausted (round after round, until every
source of the domain has given everything). For example: only Italian law and medicine, left on until done. The
sources of each domain are in `sys/core/config/harvest_sources.json`.

| source | domains | what it brings | licence stored |
|---|---|---|---|
| **arXiv** | AI, computer science, mathematics, physics, astrophysics, statistics, economics, engineering, robotics… | full papers (PDF) | the paper's |
| **Normattiva** | Italian law | the official collections (codes, consolidated acts, legislative decrees, decree-laws, regulations…), one passage per article, text in force | public act, no copyright (L. 633/1941 art. 5) |
| **Europe PMC** | medicine, biomedicine, genomics, psychology | open-access full texts | the article's (cc by, cc by-nc…) |
| **bioRxiv / medRxiv** | biomedicine, genomics, behaviour and cognition / medicine, psychiatry and clinical psychology | full preprints | the preprint's |
| **Wikipedia** (en + your language; others with a tick) | philosophy, religion, history, literature, society, general | the articles of the "Vital articles" lists, each in its domain; general culture only: medicine, physics and the other sciences come from the official repositories above | CC BY-SA 4.0 |
| **GitHub** | programming | READMEs of the most followed repositories per topic, open licence only (MIT, Apache, BSD, GPL…) | the repository's |
| **Documentation** | programming | Python (official archive), MDN JavaScript, the Rust book: to write code from the documentation | open licences (PSF, CC-BY-SA, MIT/Apache) |

Your own documents (PDF, text) can be imported from the WebUI into the domain you choose, and the harvester also
takes a list of arXiv ids.

**How long it takes (indicative).** Measured on the reference machine (2 × RTX 5060 Ti), download, reading, writing
and indexing included (docs/MEASUREMENTS.md, M43–M44).

| source | measured | for 100,000 solitons |
|---|---|---|
| arXiv | 28 solitons per paper, 3.9 s per paper (59 papers) | ~3,600 papers, ~4 h |
| Normattiva | the 40 codes in force: 8,480 solitons in 567 s (212 per code, 14.2 s per code) | ~1.9 h at the pace of the codes; ordinary acts are shorter (not measured). Ceiling: ~68,000 acts in the chosen collections |
| Europe PMC | 11 solitons per text, 3.1 s per text (3 texts) | ~9,100 texts, ~8 h |
| bioRxiv / medRxiv | 11–16 solitons per preprint, 2.0–2.4 s (6 preprints) | ~6,300–9,100 preprints, ~4–5 h |
| Wikipedia | 9 solitons per article, 1.8 s per article (3 articles) | ~11,500 articles, ~6 h |
| GitHub | 6 solitons per README, 1.6 s (3 repositories) | not reachable: GitHub search returns at most 1,000 repositories per topic; with 8 topics the ceiling is ~50,000 solitons |

Linear estimates from small samples (Normattiva aside): other hardware, longer texts or the sites' limits change
them. The default automatic rounds (every 6 h, 10 items per source) are much slower; "until exhausted" runs at the
speed of the table.

## Documentation

docs/STATUS.md · docs/ROADMAP.md · docs/BUGS.md · docs/MEASUREMENTS.md · docs/MODULE_MAP.md ·
docs/COMPATIBILITY.md · docs/SECURITY.md · docs/PLUGINS.md · docs/ECOSYSTEM.md · docs/ARCHITECTURE.md ·
docs/KNOWLEDGE_PIPELINE.md · docs/TESTS.md

## License

Apache-2.0 (LICENSE, NOTICE). Models and third-party programs keep their own licenses.

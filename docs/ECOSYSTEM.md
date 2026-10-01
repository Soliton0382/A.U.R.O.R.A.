# Aurora — the ecosystem

Status legend: **[M]** decided by a measurement (see MEASUREMENTS.md) ·
**[P]** proposed, waiting for the owner's confirmation · **[O]** open.

## 0. The goal

Aurora is not a chatbot. It is an operating system for knowledge and action:

1. A question is a **goal**. Aurora works on it until the goal is met or it can
   prove it cannot be met with the means it has. A difficulty is a step, not
   an end: missing knowledge → search the vault → search arXiv / the web →
   download → forge solitons → retry; missing capability → forge an agent →
   test it in the sandbox → use it.
2. Aurora answers **only from verified knowledge** (the vault, or sources it
   fetched during the run), never from a model's training. When it does not
   know, it says so, and then keeps working if the goal allows it.
3. **Everything is visible.** Every step, instruction, tool call, retrieval,
   verification and decision is an event, streamed live and stored.
4. Aurora is **multi-model**: each task is done by the model that is best at
   it, orchestrated by an agentic core.
5. The knowledge grows without bound; quality is measured continuously and
   must not silently degrade.

## 1. Layers

```
 clients      native WebUI  ·  LibreChat / Chatbox / any OpenAI client
                  │  (HTTPS, SSE / WebSocket)
 interface    OpenAI-compatible API  +  Aurora event stream
                  │
 cognition    orchestrator: goal → plan → act → observe → verify → decide
                  │            agents (registry + forged)   tools
 knowledge    knowledge pipeline: recall → selection → synthesis → grounding
                  │
 memory       vault (solitons: knowledge + memory)  ·  index  ·  STM / LTM / REM
                  │
 models       reasoner · embedder · re-ranker · vision · image generation
                  │
 system       config (.env) · logs + trace · self-tests · self-repair · services
```

A layer only calls the layer below it (the previous installation had a
10-module import cycle at its core, B37).

## 2. Interface

### 2.1 OpenAI-compatible API [P]

| endpoint | purpose |
|---|---|
| `POST /v1/chat/completions` (stream / non-stream) | main entry, what third-party clients use |
| `POST /v1/responses` | current OpenAI API shape, for newer clients |
| `GET /v1/models` | exposes `aurora` (and per-mode variants if useful) |
| `POST /v1/images/generations` | image generation |
| `POST /v1/embeddings` | the vault encoder, for tools that want it |
| `POST /v1/files` | documents and images to read or ingest |

Images in chat use the standard `image_url` content parts.

### 2.2 What is streamed [P]

Two channels, same run:

- **For any OpenAI client**: the answer in `delta.content`; the live trace in
  `delta.reasoning_content` (the convention LibreChat and other clients render
  as a collapsible "thinking" panel). A third-party client therefore sees the
  work happening without knowing anything about Aurora.
- **For the native WebUI**: a typed event stream (`/v1/aurora/runs/{run_id}/events`,
  SSE or WebSocket) with every event of the run:

```
run.start · plan · step.start · step.end · model.call · tool.call · tool.result
retrieval.hits · rerank · synthesis.domain · verify.keep · verify.drop
agent.spawn · agent.test · agent.result · source.fetch · soliton.forge
answer.delta · answer.final · run.end · error
```

Each event: `run_id`, `seq`, `ts`, `layer`, `type`, `payload`, `parent`. The same
events go to the trace log, so the WebUI can replay any past run.

### 2.3 Every message is the first message [decided, owner 2026-09-29]

Aurora keeps **its own** conversational memory. The history that a client
sends is discarded: from any request only the **last user message** (with its
attachments) is taken.

- The message is a goal. Retrieval runs over the knowledge shards **and** the
  memory shards (STM + LTM); what it finds joins the per-domain synthesis like
  any other knowledge.
- Short follow-ups ("and the second one?") depend on the immediately preceding
  turns, which semantic retrieval may not bring back. The memory stage
  therefore always adds the most recent turns by time (a window set in `.env`)
  on top of the semantic hits. Aurora is single-owner, so this is one timeline
  across every client.
- The new message and Aurora's answer are written to STM at the end of the
  run; the REM cycle later consolidates them into LTM.
- A client's system prompt is ignored for the same reason: Aurora's behaviour
  is defined by Aurora.

### 2.4 Native WebUI [P]

New, modular, one component per concern (chat, run timeline, trace inspector,
vault explorer, agents, models, logs, settings), all fed by the event stream and
the API. IT/EN through `i18n/it_IT.json` and `i18n/en_US.json`; code and
comments in English.

## 3. Cognition

### 3.1 The run loop [P]

```
goal → plan → [ act → observe → verify → decide ]* → answer
```

- **act**: retrieve, call a tool, call an agent, fetch a source, forge an agent.
- **verify**: every claim is checked against the soliton or source it cites;
  unsupported claims are dropped (measured in progress, M22).
- **decide**: done (verified answer), continue (next strategy), or stop with a
  report of what is known, what is missing and what was tried.
- **Budgets** (steps, time, tokens) come from `.env`; reaching a budget is a
  reported outcome, not a silent stop.
- **Routing** (which model handles the request) is decided by what is already
  resident: attachment type (image → vision), intent (image generation, code,
  reasoning) from the resident embedder, then the reasoner. No large model is
  loaded just to decide.
- A failed strategy is not retried identically: the next step must change
  something (source, query, tool, agent).

### 3.2 Agents [P]

- A registry of agents with a declared contract (inputs, outputs, test cases).
- **Forging**: the reasoner writes a new agent when no existing one fits; it
  runs in the sandbox against its own tests; it is registered only if the
  tests pass. Every forge is an event and a log entry.
- Self-repair (Ouroboros) uses the same path: a change is accepted only if the
  self-tests still pass. Previous installation: 8.3% of self-modification
  cycles succeeded, 35.1% failed on invalid code (B30) — the gate is the tests,
  not the model's confidence.

### 3.3 Plugins [decided, owner 2026-09-29]

Aurora is extended by plugins, and can write plugins for itself.

**Plugins belong to Aurora.** They are never exposed to other systems. The only
interface Aurora exposes is the OpenAI-compatible API of §2, which lets clients
talk *to* Aurora; it does not let anyone use Aurora's tools.

**Protocol.** Internally, plugins speak **MCP** (Model Context Protocol), the
standard used across the industry to connect tools and services to models,
over local pipes (stdio) only — never on a network port. Aurora is the only MCP
client. This way existing MCP connectors (GitHub, Gmail, Google Drive and
Calendar, Slack, filesystems, databases, ...) plug in without new code, and the
plugins Aurora forges follow the same contract. Services with only an HTTP API
are wrapped from their OpenAPI description.

**Kinds of plugin.**

| kind | what it does | example |
|---|---|---|
| tool | a function the reasoner can call | search arXiv, run a calculation |
| connector | access to an external account | send an email, make a commit, publish a post |
| service | a long-running listener | a syslog receiver for the firewall |
| trigger | turns external events into goals for Aurora | "anomaly in the firewall log" → investigate → notify |

**Manifest.** Every plugin declares: name, version, description, the tools it
exposes (JSON schemas), the permissions it needs, the secrets it needs (as
`.env` key names, never values), its kind, its entrypoint, and its tests.

**Lifecycle**, the same for installed and self-forged plugins:
`install → sandbox → contract tests → permission grant → enable (hot, no
restart) → monitor → disable / roll back`. Every step is an event.

**Forging during a request.** When a goal needs a capability Aurora does not
have, it can create the agent or plugin in the middle of the run. The mode is a
setting (`AURORA_FORGE_MODE`):

- `ask` (default): Aurora stops that branch and asks, stating the purpose, what
  the new component will do and which permissions it needs. Example: *"Attack
  detected from 203.0.113.7. To geolocate the attacker I need a plugin that
  queries a geolocation database (read-only, no credentials). Proceed?"* The
  rest of the run continues while it waits.
- `auto`: Aurora forges, tests in the sandbox and enables without asking; every
  step is still an event, logged and reversible.

Forging and external actions are **separate switches**: enabling autonomous
forging does not by itself allow sending, publishing or committing without
confirmation; those follow the effect policy below.

**Actions with consequences outside the machine** (sending an email,
publishing, pushing a commit, opening a network port) are classified by effect:

| effect | default |
|---|---|
| read | automatic |
| write local | automatic, logged |
| external / irreversible | **the owner confirms**: preview in the WebUI or client, then execute |

Per plugin and per action the default is configurable in `.env` (for example:
emails to the owner's own address without confirmation). A self-forged plugin
that opens a port or holds credentials always needs the owner's approval
before it is enabled.

**Hosting.** Service and trigger plugins run as supervised subprocesses of a
single `aurora-plugins` unit, not one systemd unit each.

### 3.3b Choosing among many tools [O]

With few plugins every tool schema goes in the reasoner's prompt. With hundreds
it costs tokens and confuses the model: a fast first filter must pass only the
5-10 pertinent tools. Two candidates, to be compared on a tool-selection
benchmark built from Aurora's own traces (every step records the tool chosen and
whether it worked):

| candidate | cost | notes |
|---|---|---|
| the resident embedder: question vs tool descriptions | ~0 extra, already resident | baseline |
| CLM-v0.1-8B (Contrastive-LM): frozen Qwen3-8B encoder + state/action heads trained with InfoNCE | 4.2 GiB nf4 · 7.5 int8 · 14.9 fp16, resident | published DeepSWE 81.6%, Terminal-Bench 2.1 87.6% with heads **fine-tuned**; zero-shot uncertain per its authors; 2,048-token context; no GGUF; Apache-2.0. Its heads can be retrained on Aurora's traces |

Adopted only if it beats the embedder on that benchmark by more than its VRAM
costs.

### 3.4 Learning: skills in the weights, facts in the vault [P]

Proposal after the owner's question on training a custom model (2026-09-29).

- **Facts stay in the vault.** Knowledge in the weights cannot be cited,
  verified sentence by sentence, corrected or deleted, and is lost when the
  base model changes or a cloud provider is used. Literature: Ovadia et al.,
  *Fine-Tuning or Retrieval? Comparing Knowledge Injection in LLMs* (retrieval
  beats fine-tuning for new knowledge); Gekhman et al., *Does Fine-Tuning LLMs
  on New Knowledge Encourage Hallucinations?* (new facts are learned slowly and
  raise hallucination); Biderman et al., *LoRA Learns Less and Forgets Less*.
- **Skills go in the weights**, where the measurements show the weakness
  (M20): answering from passages, citing, ignoring distractors, abstaining only
  when the answer is absent. Method: RAFT (retrieval-augmented fine-tuning) on
  data generated from the vault in the benchmark's format. Tooling candidate:
  Soup (github.com/MakazhanAlpamys/Soup, Apache-2.0; SFT, DPO, GRPO, LoRA/QLoRA,
  RAFT).
- Also candidates: fine-tuning the embedder and the re-ranker on Italian
  questions against English passages; a style/preference LoRA learned from the
  owner's conversations, while conversational facts stay in LTM solitons.
- **Acquisition on demand** (the owner's idea): when knowledge is missing, the
  agent fetches and forges it during the run (§3.1); the harvester covers the
  domains in advance.
- Every trained adapter is adopted only if it beats the current model on the
  same benchmark, and is tied to its base model version.

**Option: learning during REM, all-local mode** [decided as an option, owner
2026-09-29]. When the reasoner provider is local, the REM cycle can, besides
consolidating STM into LTM, train a new LoRA adapter for the reasoner
(`AURORA_REM_TRAINING`, off by default; not available with cloud providers,
which cannot load adapters). Guardrails: the vault stays the source of truth
and answers still cite solitons; a new adapter replaces the current one only if
it scores at least as well on the benchmarks; adapters are versioned and can be
rolled back.

Tooling, checked on the llama.cpp source of 2026-09-29:

| step | tool | status |
|---|---|---|
| train the adapter | PyTorch stack (Soup, PEFT or similar), QLoRA on the original Hugging Face weights | **llama.cpp cannot do it**: its training is "technically functional (for FP32 models and limited hardware setups) but the code is very much WIP", tested on 1B models, no LoRA training |
| convert | `convert_lora_to_gguf.py` (llama.cpp) | available |
| serve | `llama-server --lora`, switched at run time with `POST /lora-adapters`, no restart | available |

Not measured: whether QLoRA of Qwen3.6-35B-A3B fits in 2x16 GB, and how long
one REM training cycle takes. The original weights (~70 GB) are needed in
addition to the GGUF.

## 4. Knowledge

The pipeline in `KNOWLEDGE_PIPELINE.md`: recall → selection → synthesis →
grounding, each stage with its test.

- Recall: query translated to English, dense encoder, top-300 [M: M14-M17].
- Selection: cross-encoder re-ranker [M: M12, M15, M17]; no fixed score
  threshold [M: M19].
- Synthesis: per-domain extraction, cross-domain synthesis [M: M20], plus a
  verification gate [measurement in progress].
- Grounding: answer only from passages; abstain when absent [M: M20].
- External sources: arXiv agent [measurement in progress].

### 4.1 Language-aware retrieval [P, owner request 2026-09-29]

Translating the question to English helps only because most documents are
English (M14). Italian solitons (law, conversations, Italian sources) must be
matched in Italian. Every soliton carries `lang`, so:

1. the vault is searched **twice**: with the original question and with its
   English translation (two ANN lookups, ~1 ms each, M16);
2. the candidates are merged;
3. the re-ranker scores each passage against the question **in the passage's
   language**.

The encoders in play are multilingual (M8, M18). To be measured on an Italian
benchmark (law and conversations) before adoption.

### 4.2 Italian legal corpus [P, owner request 2026-09-29]

Source: **Normattiva OpenData** — official consolidated Italian legislation,
Akoma Ntoso XML, ELI identifiers, CC BY 4.0, open API without authentication
(published figures, to verify when building the connector). Derived open
corpora exist: `dataciviclab/italia-corpus` (20,716 acts, 108,490 references
between acts, Markdown/Parquet) and converters such as `ondata/normattiva_2_md`.

Differences from scientific papers, all in the soliton metadata:

- **Unit = the article** (split by paragraph if long), not 4,000 characters:
  legal answers cite "art. N, comma M".
- **Validity in time**: consolidated law changes; each soliton records the act
  (ELI/URN, type, number, date), the article, and the interval in which that
  text is in force. An answer cites the version in force at the date asked,
  by default today.
- **References**: the act-to-act references are kept, so synthesis can follow
  a cross-reference to the article it points to.
- Domain `law_it`, with sub-domains by code (civil, criminal, procedure,
  administrative, ...); language `it`.
- Attribution as required by CC BY 4.0 travels with every citation.

Acquisition as a connector plugin (§3.3) feeding the harvester.

## 5. Memory

- **Soliton** = the unit of knowledge: full text, domain, kind, source,
  title, language, consolidated flag, immutable `sid` [decided].
- **Vault** = SQLite shards: `knowledge/` (harvested and fetched sources) and
  `memory/` (conversations: STM and LTM) [decided].
- **Index** = per-shard HNSW over fp16 vectors, rebuildable from the vault;
  ~2.3 GB RAM per million solitons, 1.1 ms per query near-exact [M: M16].
- **STM → LTM**: the REM cycle consolidates conversations and sets
  `consolidated=true` [P].
- **Growth**: the harvester fills every domain; quotas keep small domains
  growing [O: measurement of the quota effect].

## 6. Models

### 6.1 Placement: VRAM, RAM, CPU [decided, owner 2026-09-29; figures measured where marked]

Principle: only what decides who handles a request stays in VRAM; the model
that does the work is swapped in; whatever runs on CPU/RAM without hurting
performance lives warm there, with the smallest footprint that keeps it fast.

Measured host facts (2026-09-29):

| | |
|---|---|
| GPU 0 | RTX 5060 Ti 16 GB, **PCIe 5.0 x8** (~31 GB/s theoretical host→device) |
| GPU 1 | RTX 5060 Ti 16 GB, **PCIe 4.0 x4** (~7.9 GB/s theoretical; the card is x16, the slot gives x4) |
| RAM | 58 GiB |
| CPU | Ryzen 7 7700X, 8 cores / 16 threads, 32 MB L3 |

Consequences:

- A half-second swap is physically possible only for models up to ~12 GB
  loaded on **GPU 0**. A 20 GB model split over both GPUs is bound by GPU 1:
  ~1.5 s of pure copy at best. The owner accepts ~1.5 s swaps. **Swapped models go to GPU 0; resident models
  to GPU 1**, which is slow to load but loads once. (Real swap time: to be
  measured with the model runtime, M23.)
- Measured swaps (M23, warm caches): 4B model ready in **0.71 s** on GPU 0,
  14B in **1.11 s** on GPU 0 (2.12 s on GPU 1), the 35B-A3B reasoner fully in
  VRAM over both GPUs in 3.43 s.
- The MoE reasoner has two states [M: M23]:
  - **answering**: fully in VRAM (21.8 GB), 2,752 prompt tok/s, 109.5 gen tok/s;
  - **standby**: experts in RAM (`--cpu-moe`), **2.95 GB of VRAM**, ready in
    1.29 s, 519 / 52 tok/s — used while VRAM is lent to another model (image
    generation, a large vision model).
  Aurora's answers read ~19k-token contexts, so answering in standby would cost
  ~37 s of prompt reading against ~7 s in VRAM.
- Runtime: the native llama.cpp server (the Python binding does not expose
  expert offload). A CUDA toolkit >= 12.8 is needed to compile for Blackwell
  natively; without it the kernels are JIT-translated on first use.

### 6.2 Roles

| role | candidate | placement | evidence |
|---|---|---|---|
| router | the resident embedder + rules on attachments | GPU 1, resident | — |
| embedder | Qwen3-Embedding-0.6B or bge-m3 | GPU 1, resident (2.5 / 2.8 GB encoding) | M8, M18 |
| re-ranker | bge-reranker-v2-m3 | GPU 1, resident (~2.2 GB fp16 on disk) | M12-M17 |
| reasoner (thinking, tools) | Qwen3.6-35B-A3B Q4, or a cloud provider | experts in RAM or swapped | M20, M22 in progress |
| vision | the reasoner's own projector (Qwen3.6 is multimodal) or Qwen3-VL-8B | swapped, GPU 0 | not measured |
| image generation | Z-Image-Turbo or FLUX.2 Klein 4B | swapped, GPU 0 | not measured (published 13-16 GB) |

### 6.3 Reasoner providers [decided, owner 2026-09-29]

The reasoner is a provider behind one interface (`chat(messages, tools,
stream) → events`). Retrieval, embeddings, re-ranking, vision routing, the vault
and all memory stay **local and offline** whatever the provider. Adapters:

| provider | how |
|---|---|
| local | llama.cpp server (OpenAI-compatible) |
| any OpenAI-compatible endpoint | Ollama, vLLM, LM Studio, xAI and others |
| Anthropic | Messages API |
| Google | Gemini API |
| Claude Code | the Claude Agent SDK / headless `claude -p` with streamed JSON output, using the owner's subscription |

Every provider receives the same **identity prompt**: who Aurora is, how it
behaves (answer only from verified knowledge, never stop at the first
difficulty, report what is missing), what tools and plugins it has right now.
The prompt is a versioned file (`sys/core/prompts/identity.md`), and the tool
catalogue is appended at run time from the enabled plugins. Providers are not
benchmarked separately: they run inside the same pipeline and the same checks.

Two rules that come with a cloud provider:

- **Privacy**: the passages sent for synthesis leave the machine. Domains or
  sources marked private in `.env` are never sent to a cloud provider; the run
  falls back to the local reasoner for them.
- **Terms**: using a subscription plan through automation is governed by the
  provider's terms; the owner checks them for each provider.

## 7. System

- **Config**: `.env` is the only source of values; paths relative to
  `AURORA_ROOT` [decided].
- **Logs**: `sys/logs/<service>/`, global trace `sys/logs/trace/`, rotation +
  gzip + 365-day retention, values in `.env` [decided].
- **Self-tests**: retrieval, grounding, synthesis and agent benches run on a
  schedule; a drop below the recorded threshold is an event and a log entry.
- **Services** (plain `.service` units, generated from `.env`) [P]:

| unit | contains |
|---|---|
| `aurora-api` | OpenAI API, event stream, orchestrator, agents, knowledge pipeline |
| `aurora-models` | model runtime: reasoner, embedder, re-ranker, vision, image generation |
| `aurora-harvester` | vault growth |
| `aurora-rem` (+ `.timer`) | STM → LTM consolidation |
| ~~`aurora-ouroboros`~~ | not built as a service (2026-10-01): self-repair (Ouroboros) runs inside `aurora-rem` (daily self-review → `repair` on recurring problems) and `agt_change` (sandbox in `sys/sandbox`, tests, owner's approval, live tests, rollback) |
| `aurora-plugins` | host for service and trigger plugins (supervised subprocesses) |
| `aurora-https` | reverse proxy (TLS) |

The model runtime is separate so that a model crash cannot take down the API.
The WebUI is static and served by `aurora-api`.

### 7.1 Settings from the WebUI [decided, owner 2026-09-29]

Every value of `.env` is editable from a **Settings** menu of the WebUI.

- A **settings schema** (`sys/core/config/settings_schema.json`) describes each
  variable: key, type, allowed values or range, category, explanation in
  Italian and English, whether it is a secret, and which services must reload
  it. `.env` stays the only source of values; the schema only describes them.
  `.env.example` is generated from the schema.
- The page shows each variable with its current value and its explanation,
  grouped by category; secrets are masked and write-only.
- A change is validated against the schema, written to `.env` atomically
  (comments preserved), recorded as an event with old and new value (secrets
  masked), and applied by hot reload where the service supports it, otherwise
  by restarting only the services that declare that variable.
- The Settings page, like the whole WebUI, requires the owner's
  authentication.

## 8. Decisions

Decided by the owner on 2026-09-29:

1. Soliton schema with a content-hash `sid`.
2. Knowledge and conversation memory in separate shard files.
3. The live trace is streamed to third-party clients through `reasoning_content`.
4. Every message is the first message; client history is discarded (§2.3).
5. Minimal VRAM residency, swap on demand, warm CPU/RAM tier (§6.1).
6. Pluggable reasoner providers, local or cloud, with the same identity prompt; retrieval and memory stay local (§6.3).
7. ~1.5 s model swaps are acceptable (§6.1).
8. Plugins are Aurora's own: MCP over local pipes only, never exposed; self-forged through the sandbox; external actions confirmed by the owner by default (§3.3).
9. Forging agents or plugins during a run: `ask` with the purpose stated, or `auto`, chosen in `.env` (§3.3).
10. Every `.env` value is editable from the WebUI Settings menu, with its explanation (§7.1).

Settled by measurement (2026-09-30):

11. **Reasoner: Qwen3.6-35B-A3B**, fully in VRAM when answering, experts in RAM
    in standby (M20, M22, M23).
12. **Answer pipeline**: question-level answerability gate (no thinking) →
    per-domain extraction and cross-domain synthesis **with thinking** →
    sentence-level verification against the cited solitons. Measured on 40
    questions: 52% correct, 10% partial, **2% wrong**, 35% abstained (M24); the
    abstentions go to the agent loop.
13. **Sentence verification is for faithfulness, not correctness**: it brings
    citations to 98-100% supported, it does not catch a wrong answer (M22); the
    gate does that job (M24).
14. **The agent loop must iterate**: a single search pass found the missing
    source in 1 of 17 cases (M22).
15. **Embedder: Qwen3-Embedding-0.6B**, provisional: better than bge-m3 on the
    only direct comparison (M18), same size and dimension; 2.6x slower to
    embed. Re-checked on the new vault's benchmark.

Still open:

- Iterative agent strategy (more queries, better search engines, reformulation,
  citations) — first benchmark of the new code.
- Vision and image-generation models (not measured).
- Whether QLoRA of the reasoner fits 2x16 GB (only for the REM-training option).

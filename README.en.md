<p align="center"><img src="docs/img/banner.en.svg" alt="A.U.R.O.R.A." width="100%"></p>

<p align="center"><img src="https://img.shields.io/badge/license-Apache--2.0-2a78d6" alt="License"> <img src="https://img.shields.io/badge/python-3.14-1baf7a" alt="Python"> <img src="https://img.shields.io/badge/CUDA-13.4-008300" alt="CUDA"> <img src="https://img.shields.io/badge/Ubuntu-26.04-eb6834" alt="Ubuntu"> <img src="https://img.shields.io/badge/tests-117%20passed-1baf7a" alt="Tests"></p>

<p align="center">🇮🇹 <a href="README.md">Italiano</a> · 🇬🇧 <b>English</b></p>

**Architettura Unificata Risonante per l'Orchestrazione del Ragionamento Autonomo** — a local AI that
answers only from knowledge it can show, remembers, dreams, repairs herself under the owner's
approval, and says "I don't know" when the vault does not know.

Everything runs on the owner's machine: the reasoner (llama.cpp), the encoder and re-ranker, the
vault, the memory, the WebUI. A cloud reasoner (Anthropic API or Claude Code) can be chosen for the
reasoning roles; the code of conduct forbids sending private data there without the owner's signed
exemption.

## ✨ What makes her different

| | Aurora | a typical assistant (chat + model + documents) |
|---|---|---|
| 🔎 **Truth** | every sentence of an answer is verified against the vault's passages; what is not supported is removed, and with nothing found she abstains (M32: 0 unsupported sentences of 14 kept) | cites sources, but the sentences the model writes are not checked one by one |
| 📏 **Measurement** | every choice has a numbered measurement (M1–M35), every error a number in BUGS.md, every limit is written down | performance is claimed, rarely measured in public |
| 🌙 **A life of her own** | consolidates memories, thinks when idle, dreams and paints the dream, reviews herself every day from her own logs | wakes up only when you write |
| 🛠️ **Repairs herself** | fixes her own code in a sandbox, with tests, your approval, live tests and rollback | only the developer changes the code |
| 🔏 **Signed rules** | a code of conduct bound to your installation's key: changed without a signature, Aurora does not start | rules in a prompt, changed without a trace |
| 🏠 **All at home** | models, vault, memory and WebUI on your machine; the cloud is optional and gets no private data without your signature | data often goes through an external service |
| 👁️ **Senses** | sees through the webcam and hears through the microphone, locally | — |
| 📜 **Transparency** | AI disclosure (EU AI Act art. 50) on the text, images and PDFs she publishes | — |

## What she does (each line is tested; numbers are in docs/MEASUREMENTS.md)

| **Feature** | **How** |
|---|---|
| **Answers from the vault** | route → translate → search (encoder + re-ranker over every domain) → per-domain extraction → synthesis → **every sentence verified against the passages** → sources. Unsupported sentences are dropped (M32: 0 of 14 kept); with nothing found, an honest abstention and an offer to search arXiv |
| **Vault of solitons** | SQLite shards, knowledge and memory apart, dedup by content hash, exact vector search below 250k vectors per domain, HNSW above (M30) |
| **Memory** | short-term turns, long-term session memories written at night, recall by meaning over 12 months, dates labelled by the clock |
| **Autonomic cycle** | consolidation, thoughts when idle, a nightly **dream painted with SDXL-Lightning** (AI-marked), a daily self-review from her own logs, self-repair on recurring problems |
| **Agents and plugins** | MCP plugins (GitHub, Telegram, Facebook, Mastodon, e-mail, Home Assistant, web, documents…), an approval gate for every external action and every code change (sandbox → tests → owner → live tests → rollback) |
| **Knowledge growth** | arXiv harvester by category, batches of papers from the WebUI, acquisition that looks for the *original* paper first (M33) |
| **Security** | firewall syslog sentinel with defensive incident reports; TLS 1.3, CSP, device cookies, secrets 0600 (docs/SECURITY.md) |
| **Code of conduct** | level A (never: attacks, locating people, malware), level B (confirmations, disclosure) exemptible only by a signature with the installation's own key; services refuse to start if the rules are changed unsigned |
| **Senses** | camera (Aurora describes what she sees) and microphone (local transcription with Whisper); 📷 and 🎙️ in the chat; devices chosen from a list |
| **EU AI Act art. 50** | disclosure on published text, images (XMP/IPTC) and PDFs |
| **WebUI / PWA** | chat with live answers and tokens/s, dreams, repairs, security, diary, social, plugins, harvester, settings (every `.env` value explained), notifications (push and in-app, chosen event by event), updates, IT/EN |

## Measured on the reference machine

2 × RTX 5060 Ti 16 GB, Ubuntu 26.04, driver 595, CUDA 13.4 (docs/COMPATIBILITY.md).

![Finding the right document](docs/img/en/retrieval.svg)
![Sentence verification](docs/img/en/verification.svg)
![Finding the original paper](docs/img/en/originals.svg)
![First reasoner start](docs/img/en/startup.svg)
![Painting a dream](docs/img/en/images.svg)

| **Measure** | **Result** |
|---|---|
| reasoner Qwen3.6-35B-A3B Q4 | 112.4 tok/s generation, 2,788 tok/s prompt (M34) |
| retrieval on 344,499 solitons | right document 1st in 74.2%, among the 12 passages given to synthesis in 92.1% (M31) |
| sentence verification vs an external judge | 26/32 agreement, 0 unsupported sentences kept (M32) |
| dream painting | ~20 s including swapping the reasoner out and back (M27) |

## Updates

`AURORA_UPDATE_MODE`: `notify` (default) — Aurora checks the repository every day, sends a
notification and puts the list of changes (the commit messages) in the Repairs page for you to
approve; `auto` — applied by itself when safe (no protected file of the code of conduct, tests
green, otherwise it asks); `off`. An update is fast-forward only, installs the requirements when they
change, runs the tests and goes back to the previous version if anything fails.

## Moving the installation

`sys/core/script/sys_relocate.sh` reads the current folder from `.env`, asks the new one, and moves
everything (venv, systemd units, ethics exemption).

## Install

Today: the scripts below, run in order, on Ubuntu 26.04 with NVIDIA GPUs. A single `install.sh`
that asks the questions on screen is being written (docs/ROADMAP.md, "Installer specification").

```bash
git clone git@github.com:Soliton0382/A.U.R.O.R.A..git aurora && cd aurora
sys/core/script/sys_nvidia.sh check                 # then clean / toolkit / (driver) / verify / llama
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python sys/core/script/sys_env_sync.py    # .env from the schema (review .env.proposed)
sudo .venv/bin/python sys/core/script/sys_ethics_sign.py setup
.venv/bin/python sys/core/script/sys_install_services.py && sudo bash sys/deploy/systemd/install.sh
```

Models are not in the repository (the reasoner alone is 20.6 GB): they come from Hugging Face.

## Documentation

docs/STATUS.md · docs/ROADMAP.md · docs/BUGS.md · docs/MEASUREMENTS.md · docs/MODULE_MAP.md ·
docs/COMPATIBILITY.md · docs/SECURITY.md · docs/PLUGINS.md · docs/ECOSYSTEM.md · docs/ARCHITECTURE.md ·
docs/KNOWLEDGE_PIPELINE.md · docs/TESTS.md

## License

Apache-2.0 (LICENSE, NOTICE). Models and third-party programs keep their own licenses.

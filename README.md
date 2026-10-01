<p align="center"><img src="docs/img/banner.svg" alt="A.U.R.O.R.A." width="100%"></p>

<p align="center"><img src="https://img.shields.io/badge/license-Apache--2.0-2a78d6" alt="License"> <img src="https://img.shields.io/badge/python-3.14-1baf7a" alt="Python"> <img src="https://img.shields.io/badge/CUDA-13.4-008300" alt="CUDA"> <img src="https://img.shields.io/badge/Ubuntu-26.04-eb6834" alt="Ubuntu"> <img src="https://img.shields.io/badge/tests-117%20passed-1baf7a" alt="Tests"></p>

<p align="center">🇮🇹 <b>Italiano</b> · 🇬🇧 <a href="README.en.md">English</a></p>

**Architettura Unificata Risonante per l'Orchestrazione del Ragionamento Autonomo** — un'intelligenza
artificiale locale che risponde solo con conoscenza che sa mostrare, ricorda, sogna, si ripara con
l'approvazione del proprietario e dice "non lo so" quando il vault non lo sa.

Tutto gira sulla macchina del proprietario: il ragionatore (llama.cpp), l'encoder e il re-ranker, il
vault, la memoria, la WebUI. Per i ruoli di ragionamento si può scegliere un ragionatore cloud (API
Anthropic o Claude Code); il codice di condotta vieta di mandarci dati privati senza l'esenzione
firmata dal proprietario.

## ✨ Cosa la rende diversa

| | Aurora | un assistente tipico (chat + modello + documenti) |
|---|---|---|
| 🔎 **Verità** | ogni frase della risposta è verificata sui passaggi del vault; ciò che non è supportato viene tolto, e se non c'è nulla si astiene (M32: 0 frasi non supportate su 14) | cita le fonti, ma le frasi scritte dal modello non vengono controllate una per una |
| 📏 **Misura** | ogni scelta ha una misura numerata (M1–M35), ogni errore un numero in BUGS.md, ogni limite è scritto | le prestazioni si dichiarano, raramente si misurano in pubblico |
| 🌙 **Vita propria** | consolida i ricordi, pensa quando si annoia, sogna e dipinge il sogno, fa un'autodiagnosi quotidiana dai propri log | si attiva solo quando le scrivi |
| 🛠️ **Si ripara** | corregge il proprio codice in una sandbox, con test, la tua approvazione, test dal vivo e rollback | il codice lo cambia solo lo sviluppatore |
| 🔏 **Regole firmate** | codice di condotta con la chiave della tua installazione: se qualcuno lo modifica senza firma, Aurora non parte | regole nel prompt, modificabili senza traccia |
| 🏠 **Tutto in casa** | modelli, vault, memoria e WebUI sulla tua macchina; il cloud è facoltativo e non riceve dati privati senza la tua firma | spesso i dati passano da un servizio esterno |
| 👁️ **Sensi** | vede dalla webcam e sente dal microfono, in locale | — |
| 📜 **Trasparenza** | dichiarazione IA (AI Act art. 50) su testi, immagini e PDF che pubblica | — |

## Cosa fa (ogni riga è testata; i numeri sono in docs/MEASUREMENTS.md)

| **Funzione** | **Come** |
|---|---|
| **Risponde dal vault** | smistamento → traduzione → ricerca (encoder + re-ranker su tutti i domini) → estrazione per dominio → sintesi → **ogni frase verificata sui passaggi** → fonti. Le frasi non supportate vengono tolte (M32: 0 su 14 passano); se non trova nulla, si astiene onestamente e propone di cercare su arXiv |
| **Vault di solitoni** | shard SQLite, conoscenza e memoria separate, deduplica per hash del contenuto, ricerca vettoriale esatta sotto i 250k vettori per dominio, HNSW sopra (M30) |
| **Memoria** | turni a breve termine, memorie di sessione a lungo termine scritte di notte, richiamo per significato su 12 mesi, date etichettate dall'orologio |
| **Ciclo autonomo** | consolidamento, pensieri quando si annoia, un **sogno notturno dipinto con SDXL-Lightning** (marcato come IA), un'autodiagnosi quotidiana dai propri log, autoriparazione sui problemi ricorrenti |
| **Agenti e plugin** | plugin MCP (GitHub, Telegram, Facebook, Mastodon, e-mail, Home Assistant, web, documenti…), un cancello di approvazione per ogni azione esterna e ogni modifica al codice (sandbox → test → proprietario → test dal vivo → rollback) |
| **Crescita della conoscenza** | harvester arXiv per categoria, batch di paper dalla WebUI, acquisizione che cerca prima il paper *originale* (M33) |
| **Sicurezza** | sentinella del syslog del firewall con rapporti difensivi sugli incidenti; TLS 1.3, CSP, cookie per dispositivo, segreti 0600 (docs/SECURITY.md) |
| **Codice di condotta** | livello A (mai: attacchi, localizzare persone, malware), livello B (conferme, dichiarazione IA) esentabile solo con una firma con la chiave della propria installazione; i servizi non partono se le regole cambiano senza firma |
| **Sensi** | videocamera (Aurora descrive ciò che vede) e microfono (trascrizione locale con Whisper); 📷 e 🎙️ in chat; dispositivi scelti da un elenco |
| **AI Act UE, art. 50** | dichiarazione su testi pubblicati, immagini (XMP/IPTC) e PDF |
| **WebUI / PWA** | chat con risposte in diretta e token/s, sogni, riparazioni, sicurezza, diario, social, plugin, harvester, impostazioni (ogni valore del `.env` spiegato), notifiche (push e nella WebUI, scelte evento per evento), aggiornamenti, IT/EN |

## Misure sulla macchina di riferimento

2 × RTX 5060 Ti 16 GB, Ubuntu 26.04, driver 595, CUDA 13.4 (docs/COMPATIBILITY.md).

![Trovare il documento giusto](docs/img/it/retrieval.svg)
![Verifica delle frasi](docs/img/it/verification.svg)
![Trovare il paper originale](docs/img/it/originals.svg)
![Primo avvio del ragionatore](docs/img/it/startup.svg)
![Dipingere un sogno](docs/img/it/images.svg)

| **Misura** | **Risultato** |
|---|---|
| ragionatore Qwen3.6-35B-A3B Q4 | 112,4 token/s in generazione, 2.788 token/s sul prompt (M34) |
| ricerca su 344.499 solitoni | documento giusto al 1° posto nel 74,2%, tra i 12 passaggi dati alla sintesi nel 92,1% (M31) |
| verifica delle frasi contro un giudice esterno | 26/32 in accordo, 0 frasi non supportate tenute (M32) |
| sogno dipinto | ~20 s compreso lo scambio del ragionatore (M27) |

## Aggiornamenti

`AURORA_UPDATE_MODE`: `notify` (predefinito) — Aurora controlla il repository ogni giorno, manda una
notifica e mette l'elenco delle novità (i messaggi dei commit) nella pagina Riparazioni perché tu le
approvi; `auto` — le applica da sola se sono sicure (nessun file protetto del codice etico, test
verdi; altrimenti chiede); `off`. Un aggiornamento è solo fast-forward, installa i requisiti se
cambiano, esegue i test e torna alla versione precedente se qualcosa fallisce.

## Spostare l'installazione

`sys/core/script/sys_relocate.sh` legge la cartella attuale dal `.env`, chiede la nuova e sposta
tutto (venv, unit systemd, esenzione etica).

## Installazione

Oggi: gli script qui sotto, nell'ordine, su Ubuntu 26.04 con GPU NVIDIA. Un unico `install.sh` che fa
le domande a schermo è in lavorazione (docs/ROADMAP.md, "Installer specification").

```bash
git clone git@github.com:Soliton0382/A.U.R.O.R.A..git aurora && cd aurora
sys/core/script/sys_nvidia.sh check                 # poi clean / toolkit / (driver) / verify / llama
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python sys/core/script/sys_env_sync.py    # .env dallo schema (controlla .env.proposed)
sudo .venv/bin/python sys/core/script/sys_ethics_sign.py setup
.venv/bin/python sys/core/script/sys_install_services.py && sudo bash sys/deploy/systemd/install.sh
```

I modelli non sono nel repository (il solo ragionatore pesa 20,6 GB): arrivano da Hugging Face.

## Documentazione

La documentazione tecnica è in inglese: docs/STATUS.md · docs/ROADMAP.md · docs/BUGS.md ·
docs/MEASUREMENTS.md · docs/MODULE_MAP.md · docs/COMPATIBILITY.md · docs/SECURITY.md ·
docs/PLUGINS.md · docs/ECOSYSTEM.md · docs/ARCHITECTURE.md ·
docs/KNOWLEDGE_PIPELINE.md · docs/TESTS.md

## Licenza

Apache-2.0 (LICENSE, NOTICE). Modelli e programmi di terze parti mantengono le proprie licenze.

# Aurora in Docker — guida rapida

Aurora in un container, con il **ragionatore in cloud** (Anthropic, OpenAI, Google, Mistral, OpenRouter, xAI o un
servizio compatibile OpenAI). Pensata per un computer **senza GPU**: ricerca, memoria e documenti restano sul computer,
ogni testo che esce è mascherato (email, telefoni, IBAN, nomi… diventano segnaposto).

## Cosa serve

| | |
|---|---|
| Sistema | Linux con Docker e Docker Compose (`docker compose version`) |
| RAM | 12 GB consigliati; con 8 GB spegni la raccolta (vedi sotto) — misurato: encoder e re-ranker ~5–7 GB mentre lavorano (M151, M152) |
| Disco | ~10 GB: immagine + 3,3 GB di modelli scaricati al primo avvio; poi cresce con la raccolta: **~6,8 KB a passaggio, ~55 KB a documento** (M154: 743.536 passaggi = 5 GB) |
| Rete | la chiave API del provider scelto |

## 1. Configura

Dalla cartella di Aurora scaricata:

```bash
cp docker/.env.example docker/.env
nano docker/.env
```

Le voci da guardare:

| Voce | Cosa mettere |
|---|---|
| `AURORA_DOMAIN` | l'indirizzo di questo computer in casa (es. `192.168.1.20`, lo vedi con `ip -4 addr`), oppure `localhost` se la userai solo da qui |
| `AURORA_HTTPS_PORT`, `AURORA_HTTP_PORT` | `443` e `80` di solito; **se sono già occupate** (un altro web server) scegline altre, es. `8443` e `8080` |
| `AURORA_CLOUD_PROVIDER` | `anthropic`, `openai`, `google`, `mistral`, `openrouter`, `xai` o `custom` |
| la chiave di quel provider | es. `AURORA_ANTHROPIC_API_KEY=...` (le altre restano vuote) |
| `AURORA_CLOUD_MODEL` | vuoto = il primo modello dell'elenco del provider (viene provato con una chiamata) |
| `AURORA_OWNER_NAME`, `AURORA_LANG_DEFAULT` | il tuo nome, `it_IT` o `en_US` |
| `AURORA_HARVEST_ENABLED` | `1` riempie il vault vuoto con articoli aperti; su un PC piccolo tiene la CPU occupata: `0` per spegnerla |
| `AURORA_MEMORY_LIMIT` | il massimo di RAM per il container (default `10g`) |

`docker/.env` contiene la tua chiave: non condividerlo (è già escluso da git).

## 2. Avvia

```bash
docker compose -f docker/compose.yaml up -d --build
docker compose -f docker/compose.yaml logs -f
```

Il primo avvio costruisce l'immagine e scarica i modelli (alcuni minuti). Quando è pronta, nel log compaiono
**l'indirizzo da aprire e la chiave API** (`WebUI: https://...` e `API key: ...`): la chiave serve una volta per ogni
browser o telefono.

## 3. Il certificato (il lucchetto del browser)

Aurora usa un certificato suo (di Caddy). La prima volta il browser avvisa: puoi accettare l'eccezione, oppure
installare il certificato radice — da ogni dispositivo apri `http://<AURORA_DOMAIN>:<AURORA_HTTP_PORT>/aurora-ca.crt`
e segui la pagina 🔒 HTTPS di Aurora (passi per Android e iPhone).

## Cambiare qualcosa dopo

| Cosa | Dove |
|---|---|
| porte o indirizzo | in `docker/.env`, poi `docker compose -f docker/compose.yaml up -d` |
| tutto il resto (modelli, provider, modalità, utenti…) | dalla WebUI: Impostazioni, 🧠 Modelli |
| altri nomi del computer (es. `nomepc.local`) | pagina 🔒 HTTPS |

## Aggiornare

```bash
git pull
docker compose -f docker/compose.yaml up -d --build
```

I dati restano nel volume `aurora-data` (vault, memoria, impostazioni, chiavi, modelli): un'immagine nuova li ritrova.
Al primo avvio dopo l'aggiornamento Aurora firma di nuovo il proprio codice con la chiave di questa installazione.

## Comandi utili

```bash
docker compose -f docker/compose.yaml ps            # stato (healthy quando l'API risponde)
docker compose -f docker/compose.yaml logs -f       # cosa succede
docker compose -f docker/compose.yaml restart       # riavvio
docker compose -f docker/compose.yaml down          # spegne (i dati restano)
docker exec -it aurora systemctl is-active aurora-api aurora-models aurora-https
```

## Cosa non c'è in questa immagine

- il ragionatore locale (serve una GPU: installazione con `./install.sh`);
- Claude Code come provider (è un programma da installare e collegare al tuo account: usa una chiave API);
- i plugin (girano solo dentro la loro gabbia, che in un container normale non è disponibile);
- voce di Aurora, sogni dipinti, video (modelli pesanti o GPU).

Tecnicamente: un solo container; `docker/entrypoint.py` prepara dati e impostazioni e tiene vivi i servizi (API,
encoder, cicli notturni, raccolta, sentinella, Caddy), riavviandoli se si fermano; `systemctl` nel container è un
sostituto che parla con lui, così le pagine di Aurora funzionano come su Linux.

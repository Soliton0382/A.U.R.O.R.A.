# Plugins

Generated from `sys/plugins/*/plugin.json` by `sys/core/script/doc_plugins.py`: the WebUI (Plugins page) shows the same guides. Effects: **read** automatic, **write_local** automatic and logged, **external** waits for the owner (Repairs page).

| plugin | kind | tools (effect) | needs |
|---|---|---|---|
| `documents` | tool | create_pdf (write_local), list_documents (read) | — |
| `email` | connector | list_unread (read), read_message (read), send_email (external) | AURORA_EMAIL_IMAP_HOST, AURORA_EMAIL_USER, AURORA_EMAIL_PASSWORD |
| `facebook` | connector | publish_post (external), page_info (read), list_posts (read), page_stats (read) | AURORA_FACEBOOK_PAGE_ID, AURORA_FACEBOOK_PAGE_TOKEN |
| `github` | connector | get_* (read), list_* (read), search_* (read), everything else (external) | AURORA_GITHUB_TOKEN |
| `homeassistant` | connector | states (read), call_service (external) | AURORA_HA_URL, AURORA_HA_TOKEN |
| `mastodon` | connector | account_stats (read), post_status (external) | AURORA_MASTODON_URL, AURORA_MASTODON_TOKEN |
| `netintel` | tool | rdap_ip (read), reverse_dns (read), ip_reputation (read) | — |
| `projects` | tool | project_list (read), project_tree (read), project_read_file (read), project_status (read), project_create (write_local), project_write_file (write_local), project_commit (write_local), project_publish (external), project_push (external) | — |
| `self` | tool | list_files (read), read_file (read), search_code (read), logs_inventory (read), read_log (read), sandbox_read (read), sandbox_diff (read), sandbox_create (write_local), sandbox_replace (write_local), sandbox_write (write_local), run_tests (write_local) | — |
| `senses` | tool | devices (read), look (external), listen (external) | — |
| `telegram` | connector | send_message (external), get_me (read), get_updates (read) | AURORA_TELEGRAM_BOT_TOKEN |
| `web` | tool | fetch_url (read), search (read) | — |

## documents

Documents: Aurora writes a PDF from Markdown (headings, lists, tables, code), marked as AI-generated (EU AI Act); files in AURORA_DOCUMENTS_DIR, downloadable from the WebUI.

### Setup (EN)

Nothing to configure.

### Configurazione (IT)

Nessuna configurazione: usa Chrome (`AURORA_CHROME_BIN`) per stampare i PDF in `usr/documents`.

## email

The owner's mailbox over encrypted connections only (IMAPS, SMTP with TLS): read unread messages; sending waits for the owner and carries the AI disclosure.

### Setup (EN)

IMAPS/SMTP with TLS only. Gmail: app password; imap.gmail.com:993, smtp.gmail.com:465. **▶ Try** `list_unread`.

### Configurazione (IT)

Aurora usa solo connessioni cifrate (IMAP su TLS, SMTP su TLS o STARTTLS).

**Gmail**: attiva la verifica in due passaggi, poi crea una **password per le app** e usala al posto della tua password. IMAP `imap.gmail.com:993`, SMTP `smtp.gmail.com:465`.
**Altri provider**: cerca nelle impostazioni del provider i server IMAP/SMTP con SSL/TLS.

1. Aurora → **Impostazioni → Plugin**: `AURORA_EMAIL_IMAP_HOST`, `AURORA_EMAIL_SMTP_HOST`, `AURORA_EMAIL_USER` (il tuo indirizzo), `AURORA_EMAIL_PASSWORD`.
2. **▶ Prova** su `list_unread`: i messaggi restano non letti.

Inviare una mail è un'azione esterna: passa sempre dalla tua approvazione e porta la dichiarazione IA.

### Official guides

- [Gmail – password per le app](https://support.google.com/accounts/answer/185833)
- [Crea password per le app](https://myaccount.google.com/apppasswords)
- [Gmail – impostazioni IMAP](https://support.google.com/mail/answer/7126229)

## facebook

The owner's Facebook page through the Graph API: read the latest posts; publishing a post waits for the owner.

### Setup (EN)

**A Facebook Page is needed**, not the personal profile (Meta does not let apps post on profiles since 2018).

1. **Meta for Developers** → *My Apps* → *Create App*, type **Business**.
2. **Graph API Explorer**: select the app, *Get User Access Token* with `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`.
3. Paste the token into the **Access Token Debugger** and press *Extend Access Token*.
4. With the extended token run `me/accounts` in the Explorer: `id` is the page id, `access_token` the page token (it does not expire).
5. Aurora → **Settings → Plugins**: `AURORA_FACEBOOK_PAGE_ID`, `AURORA_FACEBOOK_PAGE_TOKEN`.
6. Press **▶ Try** on `page_info`.

### Configurazione (IT)

**Serve una Pagina Facebook**, non il profilo personale: dal 2018 Meta non permette alle app di pubblicare sui profili. Se non ne hai una, creane una (anche di prova).

1. Su **Meta for Developers** → *My Apps* → *Create App*: scegli un'app di tipo **Business**.
2. Apri **Graph API Explorer**, seleziona la tua app, poi *Get Token* → *Get User Access Token* e spunta i permessi `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`.
3. Il token dell'Explorer dura circa un'ora: incollalo nell'**Access Token Debugger** e premi *Extend Access Token* (diventa di lunga durata).
4. Torna nell'Explorer con il token esteso ed esegui `me/accounts`: per ogni pagina che amministri vedi `id` (l'ID della pagina) e `access_token` (il token della pagina, che così non scade).
5. In Aurora → **Impostazioni → Plugin**: `AURORA_FACEBOOK_PAGE_ID` = l'id, `AURORA_FACEBOOK_PAGE_TOKEN` = il token della pagina. Salva.
6. Qui sotto premi **▶ Prova** su `page_info`: devi vedere il nome della pagina.

Per le pagine che amministri tu, con l'app in modalità sviluppo non dovrebbe servire la revisione di Meta; se Meta la chiede, le guide ufficiali qui sotto spiegano come.

### Official guides

- [Crea una Pagina](https://www.facebook.com/pages/create)
- [Meta for Developers – App](https://developers.facebook.com/apps/)
- [Graph API Explorer](https://developers.facebook.com/tools/explorer/)
- [Access Token Debugger](https://developers.facebook.com/tools/debug/accesstoken/)
- [Pages API – guida ufficiale](https://developers.facebook.com/docs/pages-api/getting-started)
- [Token di lunga durata](https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived)
- [Pubblicare post](https://developers.facebook.com/docs/pages-api/posts)
- [Permessi](https://developers.facebook.com/docs/permissions)

## github

GitHub through the official GitHub MCP server: repositories, issues, pull requests, code search. Reading is automatic; every write (issue, comment, commit, push, merge) waits for the owner.

### Setup (EN)

Fine-grained personal access token with Contents, Issues, Pull requests (read and write), Administration only to create repositories → `AURORA_GITHUB_TOKEN`. **▶ Try** `get_me`.

### Configurazione (IT)

1. Su GitHub → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. Scadenza (ad esempio 90 giorni); *Repository access*: tutti i repository o solo quelli scelti.
3. Permessi *Repository*: **Contents**, **Issues**, **Pull requests** in *Read and write*; **Administration** in *Read and write* solo se vuoi che Aurora crei repository nuovi.
4. Genera e copia il token → Aurora **Impostazioni → Plugin**: `AURORA_GITHUB_TOKEN`. Facoltativi: `AURORA_GITHUB_OWNER` (utente od organizzazione dei nuovi repository), `AURORA_GIT_AUTHOR_NAME`/`EMAIL`.
5. **▶ Prova** su `get_me`: vedi il tuo utente GitHub.

Tutto ciò che scrive su GitHub (commit, issue, pull request, push) passa da **Riparazioni** per la tua approvazione.

### Official guides

- [Token fine-grained](https://github.com/settings/personal-access-tokens)
- [Guida ufficiale ai token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
- [GitHub MCP server (ufficiale)](https://github.com/github/github-mcp-server)

## homeassistant

The owner's Home Assistant: read the state of devices and sensors; commands to devices act on the physical world and wait for the owner.

### Setup (EN)

Profile → Security → Long-lived access tokens → `AURORA_HA_URL`, `AURORA_HA_TOKEN`. **▶ Try** `states`.

### Configurazione (IT)

1. In Home Assistant apri il tuo **profilo** (in basso a sinistra) → scheda **Sicurezza** → **Token di accesso a lunga durata** → *Crea token*.
2. Aurora → **Impostazioni → Plugin**: `AURORA_HA_URL` (es. `https://homeassistant.local:8123`, meglio in HTTPS) e `AURORA_HA_TOKEN`.
3. **▶ Prova** su `states`.

I comandi ai dispositivi agiscono sul mondo fisico: passano sempre dalla tua approvazione.

### Official guides

- [Il tuo profilo e i token](https://www.home-assistant.io/docs/authentication/#your-account-profile)
- [Token a lunga durata](https://developers.home-assistant.io/docs/auth_api/#long-lived-access-token)
- [REST API](https://developers.home-assistant.io/docs/api/rest/)

## mastodon

The owner's Mastodon account: statistics of the latest posts; posting waits for the owner.

### Setup (EN)

Preferences → Development → New application (`read`, `write:statuses`) → copy the access token → `AURORA_MASTODON_URL`, `AURORA_MASTODON_TOKEN`. **▶ Try** `account_stats`.

### Configurazione (IT)

1. Sul tuo server Mastodon: **Preferenze → Sviluppo → Nuova applicazione**; permessi `read` e `write:statuses`.
2. Salva, apri l'applicazione e copia **Il tuo token d'accesso**.
3. Aurora → **Impostazioni → Plugin**: `AURORA_MASTODON_URL` = l'indirizzo del server (es. `https://mastodon.social`), `AURORA_MASTODON_TOKEN` = il token.
4. **▶ Prova** su `account_stats`.

### Official guides

- [Ottenere un token](https://docs.joinmastodon.org/client/token/)
- [API dei post](https://docs.joinmastodon.org/methods/statuses/)

## netintel

Defensive network intelligence on an IP address, from public sources only: registry (RDAP: network, organisation, country of registration, abuse contact), reverse DNS, reputation (AbuseIPDB, with a key). Never about persons.

### Setup (EN)

RDAP and reverse DNS work at once; AbuseIPDB key for reputation → `AURORA_ABUSEIPDB_KEY`.

### Configurazione (IT)

Registro RDAP e DNS inverso funzionano subito. Per la **reputazione** degli IP: registrati su **AbuseIPDB** → *Account → API* → *Create Key* → `AURORA_ABUSEIPDB_KEY`.

### Official guides

- [AbuseIPDB – registrazione](https://www.abuseipdb.com/register)
- [AbuseIPDB – documentazione](https://docs.abuseipdb.com/)
- [Cos'è RDAP](https://about.rdap.org/)

## projects

Software projects in AURORA_PROJECTS_DIR: scaffold (README, licence, .gitignore, changelog), write files, commit locally; publishing to GitHub and pushing wait for the owner.

### Setup (EN)

Works locally at once; publishing needs `AURORA_GITHUB_TOKEN`.

### Configurazione (IT)

Funziona subito in locale (`usr/projects`). Per **pubblicare** su GitHub serve il token del plugin **github** (`AURORA_GITHUB_TOKEN`, con *Administration* per creare repository). Facoltativi: `AURORA_GITHUB_OWNER`, `AURORA_GIT_AUTHOR_NAME`, `AURORA_GIT_AUTHOR_EMAIL` (titolare della licenza e autore dei commit).

### Official guides

- [Token GitHub (serve per pubblicare)](https://github.com/settings/personal-access-tokens)

## self

Aurora works on herself: reads her code and logs, changes code only inside a sandbox copy, runs the tests there or on the live code.

### Setup (EN)

Nothing to configure.

### Configurazione (IT)

Nessuna configurazione: sono gli strumenti con cui Aurora lavora su sé stessa, nella sandbox.

## senses

Senses: Aurora sees through the camera (one photo, described by her own vision) and hears through the microphone (local transcription with Whisper). Local only: nothing leaves the machine. Choose the devices in the settings.

### Setup (EN)

Connect a webcam (a built-in microphone works too). In the plugin window choose the **camera** and the **microphone** among those found, or leave `auto` (the first). Camera and microphone touch the privacy of whoever is in the room: without the owner's exemption every use by Aurora waits for approval. In the chat: 📷 sends Aurora a photo from the camera, 🎙️ dictates the message.

### Configurazione (IT)

Collega una webcam (va bene anche con microfono integrato). Nella finestra del plugin scegli **videocamera** e **microfono** tra quelli rilevati, oppure lascia `auto` (il primo). Usare videocamera e microfono tocca la privacy di chi è nella stanza: senza l'esenzione del proprietario ogni uso da parte di Aurora aspetta l'approvazione. In chat: 📷 manda ad Aurora una foto dalla videocamera, 🎙️ detta il messaggio.

### Official guides

- [Whisper large-v3-turbo (model)](https://huggingface.co/openai/whisper-large-v3-turbo)

## telegram

Telegram through Aurora's bot: send a message (waits for the owner unless confirmation is off), read the messages the bot received.

### Setup (EN)

1. In Telegram open **@BotFather**, `/newbot`: you get the bot **token** → `AURORA_TELEGRAM_BOT_TOKEN`.
2. Send any message to your bot, then **▶ Try** `get_updates`: the number after `chat` is your chat id → `AURORA_TELEGRAM_OWNER_CHAT_ID`.

### Configurazione (IT)

1. In Telegram apri **@BotFather**, scrivi `/newbot`, scegli nome e username: ricevi il **token** del bot.
2. Aurora → **Impostazioni → Plugin**: `AURORA_TELEGRAM_BOT_TOKEN` = il token. Salva.
3. Scrivi un messaggio qualsiasi al tuo bot (serve perché il bot conosca la tua chat).
4. Qui sotto premi **▶ Prova** su `get_updates`: nel risultato, il numero dopo `chat` è il tuo **chat id** → mettilo in `AURORA_TELEGRAM_OWNER_CHAT_ID`.
5. **▶ Prova** su `get_me` deve mostrare il nome del bot.

Nota: i messaggi dei bot sono cifrati verso Telegram ma non end-to-end.

### Official guides

- [Tutorial ufficiale dei bot](https://core.telegram.org/bots/tutorial)
- [BotFather](https://core.telegram.org/bots/features#botfather)
- [Bot API – getUpdates](https://core.telegram.org/bots/api#getupdates)

## web

The web: read a public page as text; search (Brave Search API, with a key). Local and private addresses are refused.

### Setup (EN)

`fetch_url` works at once. For search: Brave Search API key → `AURORA_BRAVE_SEARCH_KEY`.

### Configurazione (IT)

`fetch_url` funziona subito (solo pagine pubbliche: la rete di casa è sempre rifiutata).
Per la **ricerca**: registrati su **Brave Search API**, scegli un piano, crea una chiave → `AURORA_BRAVE_SEARCH_KEY`. **▶ Prova** su `search` non è disponibile qui perché richiede una query: usala dalla chat con `/agente cerca …`.

### Official guides

- [Brave Search API](https://brave.com/search/api/)
- [Dashboard e chiavi](https://api-dashboard.search.brave.com/)


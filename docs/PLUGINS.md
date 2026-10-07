# Plugins

Generated from `sys/plugins/*/plugin.json` by `sys/core/script/doc_plugins.py`: the WebUI (Plugins page) shows the same guides. Effects: **read** automatic, **write_local** automatic and logged, **external** waits for the owner (Repairs page).

| plugin | kind | tools (effect) | needs |
|---|---|---|---|
| `backup` | service | — | — |
| `calendar` | connector | calendar_agenda (read), calendar_add_event (external) | — |
| `cinema` | tool | — | AURORA_TMDB_TOKEN |
| `cloud` | connector | — | — |
| `diary` | tool | — | — |
| `discord` | connector | discord_read (read), discord_send (external) | AURORA_DISCORD_BOT_TOKEN, AURORA_DISCORD_CHANNEL_ID |
| `documents` | tool | create_pdf (write_local), list_documents (read) | — |
| `dropbox` | connector | dropbox_list (read), dropbox_search (read), dropbox_read (read), dropbox_upload (external) | AURORA_DROPBOX_APP_KEY, AURORA_DROPBOX_APP_SECRET, AURORA_DROPBOX_REFRESH_TOKEN |
| `email` | connector | list_unread (read), read_message (read), send_email (external) | AURORA_EMAIL_IMAP_HOST, AURORA_EMAIL_USER, AURORA_EMAIL_PASSWORD |
| `expenses` | tool | expense_list (read), expense_summary (read) | — |
| `cloudflare` | connector | cloudflare_status (read), cloudflare_check (read), cloudflare_activate (external) | AURORA_CLOUDFLARE_ACCOUNT_ID, AURORA_CLOUDFLARE_API_TOKEN |
| `facebook` | connector | publish_post (external), page_info (read), list_posts (read), page_stats (read), list_comments (read), reply_comment (external), update_page_info (external), set_welcome_message (external), publish_photo (external) | AURORA_FACEBOOK_PAGE_ID, AURORA_FACEBOOK_PAGE_TOKEN |
| `github` | connector | get_* (read), list_* (read), search_* (read), everything else (external) | AURORA_GITHUB_TOKEN |
| `homeassistant` | connector | states (read), call_service (external) | AURORA_HA_URL, AURORA_HA_TOKEN |
| `instagram` | connector | ig_account (read), ig_recent (read), ig_publish_photo (external) | AURORA_FACEBOOK_PAGE_ID, AURORA_FACEBOOK_PAGE_TOKEN |
| `mastodon` | connector | account_stats (read), post_status (external) | AURORA_MASTODON_URL, AURORA_MASTODON_TOKEN |
| `netintel` | tool | rdap_ip (read), reverse_dns (read), ip_reputation (read) | — |
| `news` | tool | — | — |
| `nextcloud` | connector | files_list (read), files_read (read), files_upload (external) | AURORA_WEBDAV_URL, AURORA_WEBDAV_USER, AURORA_WEBDAV_PASSWORD |
| `notes` | tool | notes_list (read), notes_search (read), notes_read (read), notes_write (write_local) | — |
| `projects` | tool | project_list (read), project_tree (read), project_read_file (read), project_status (read), project_create (write_local), project_write_file (write_local), project_commit (write_local), project_publish (external), project_push (external) | — |
| `security` | tool | — | — |
| `self` | tool | list_files (read), read_file (read), search_code (read), logs_inventory (read), read_log (read), sandbox_read (read), sandbox_diff (read), sandbox_create (write_local), sandbox_replace (write_local), sandbox_write (write_local), run_tests (write_local) | — |
| `senses` | tool | devices (read), look (external), listen (external) | — |
| `telegram` | connector | send_message (external), get_me (read), get_updates (read) | AURORA_TELEGRAM_BOT_TOKEN |
| `tiktok` | connector | tiktok_account (read), tiktok_post_video (external) | AURORA_TIKTOK_CLIENT_KEY, AURORA_TIKTOK_CLIENT_SECRET, AURORA_TIKTOK_REFRESH_TOKEN |
| `twitch` | connector | — | AURORA_TWITCH_CLIENT_ID, AURORA_TWITCH_CLIENT_SECRET |
| `weather` | tool | — | AURORA_WEATHER_LAT, AURORA_WEATHER_LON |
| `web` | tool | fetch_url (read), search (read) | — |
| `whatsapp` | connector | whatsapp_send (external), whatsapp_send_template (external) | AURORA_WHATSAPP_TOKEN, AURORA_WHATSAPP_PHONE_ID, AURORA_WHATSAPP_TO |

## backup

Nightly backup of your data to another disk or the NAS: encrypted, deduplicated, checked.

### Setup (EN)

**Where**: in *Backup folder* write a folder on another disk (e.g. `/media/user/Data/aurora-backup`) or the NAS folder as `smb://192.168.1.20/backups/aurora`.

**NAS**: put the share's user and password. With *Mount at every start* (on) Aurora adds one line to `/etc/fstab` with `nofail`: a NAS switched off never stops the computer. On **Save** Aurora mounts the share by herself; you gave root's consent once, with `sudo bash sys/deploy/systemd/install.sh`.

**The key**: once, `.venv/bin/python sys/core/script/svc_backup.py init`, and write the *recovery code* outside this computer: without it a backup cannot be read.

**When**: every night at the chosen time; if the computer was off, at the next start. State and *Run now* are in ⚙️ Status.

### Configurazione (IT)

**Dove**: in *Cartella del backup* scrivi una cartella di un altro disco (es. `/media/utente/Dati/aurora-backup`) oppure la cartella del NAS come `smb://192.168.1.20/backups/aurora`.

**NAS**: metti utente e password della condivisione. Con *Monta a ogni avvio* (già attivo) Aurora aggiunge una riga a `/etc/fstab` con `nofail`: se il NAS è spento il computer parte lo stesso. Al **Salva** Aurora monta la condivisione da sola; il permesso di root lo hai dato una volta, con `sudo bash sys/deploy/systemd/install.sh`.

**La chiave**: una volta sola, `.venv/bin/python sys/core/script/svc_backup.py init`, e scrivi il *codice di recupero* fuori da questo computer: senza, un backup non si legge.

**Quando**: ogni notte all'ora scelta; se il PC era spento, al primo avvio. Lo stato e *Esegui ora* sono in ⚙️ Stato.

## calendar

Your calendars: ICS links read only (Google, Outlook, any .ics) and one CalDAV calendar read and written (Nextcloud, iCloud, Fastmail). Adding an event waits for your approval.

### Setup (EN)

**Read only (simplest):** Google Calendar → calendar settings → *Secret address in iCal format*; Outlook → Calendar → Share → *ICS*. Paste one or more links in `AURORA_CALENDAR_ICS_URLS`, comma separated. They are secret links: Aurora never shows them.

**Read and write (CalDAV):** the calendar's address and an *app password*.
- Nextcloud: `https://<host>/remote.php/dav/calendars/<user>/personal/`
- iCloud: `https://caldav.icloud.com/` and an app password from appleid.apple.com
- Fastmail: `https://caldav.fastmail.com/dav/calendars/user/<email>/Default/`

Press **▶ Try** on `calendar_agenda`.

### Configurazione (IT)

**Solo lettura (il più semplice):** Google Calendar → Impostazioni del calendario → *Indirizzo segreto in formato iCal*; Outlook → Calendario → Condividi → *ICS*. Incolla uno o più link in `AURORA_CALENDAR_ICS_URLS`, separati da virgole. Sono link segreti: Aurora non li mostra mai.

**Lettura e scrittura (CalDAV):** l'indirizzo del calendario e una *password per app*.
- Nextcloud: `https://<host>/remote.php/dav/calendars/<utente>/personal/`
- iCloud: `https://caldav.icloud.com/` e una password per app da appleid.apple.com
- Fastmail: `https://caldav.fastmail.com/dav/calendars/user/<email>/Default/`

Premi **▶ Prova** su `calendar_agenda`.

## cinema

Films and series from TMDB: what is trending, what is in cinemas, search a title, plot, cast, vote, and where to watch it in your country (Netflix, Prime Video, Disney+… subscription, rent or buy; data by JustWatch).

### Setup (EN)

1. A free account on **themoviedb.org**.
2. Profile → **Settings → API**: ask for a personal key.
3. Copy the **API Read Access Token** (long) or the **API Key** (short): both work.
4. Aurora → **Settings → Plugins**: `AURORA_TMDB_TOKEN`, `AURORA_TMDB_REGION` (IT).
5. Press **▶ Try** on `cinema_trending`.

This product uses the TMDB API but is not endorsed or certified by TMDB. Where-to-watch data by JustWatch.

### Configurazione (IT)

1. Crea un account gratuito su **themoviedb.org**.
2. Profilo → **Impostazioni → API**: chiedi una chiave per uso personale.
3. Copia la **API Read Access Token** (lunga) oppure la **API Key** (corta): vanno bene entrambe.
4. In Aurora → **Impostazioni → Plugin**: `AURORA_TMDB_TOKEN` = la chiave; `AURORA_TMDB_REGION` = il paese per «dove vederlo» (IT).
5. Qui sotto premi **▶ Prova** su `cinema_trending`.

Questo prodotto usa l'API di TMDB ma non è approvato né certificato da TMDB. I dati su dove vedere i titoli sono di JustWatch.

### Official guides

- [TMDB – API](https://www.themoviedb.org/settings/api)
- [JustWatch](https://www.justwatch.com)

## cloud

Cloud AI providers (Anthropic, Claude Code, Google Gemini, xAI Grok, OpenAI, Mistral, OpenRouter): their keys, and each one's list of models. Which model does each step is chosen in the Models page; everything sent is masked by default.

### Setup (EN)

Paste the keys of the providers you want (only those you assign in the 🧠 Models page). Claude Code uses your subscription. Masking is on by default; pictures cannot be masked.

### Configurazione (IT)

Incolla qui sotto le chiavi dei provider che vuoi usare (servono solo quelli che assegnerai nella pagina 🧠 Modelli). Claude Code usa il tuo abbonamento, senza chiave. Le chiavi restano nel `.env` (permessi 0600) e le vede solo questo plugin. **Mascheramento** (`AURORA_CLOUD_MASK`, acceso per default): IP, email, telefoni, IBAN, carte, chiavi, i tuoi dati e le parole di `AURORA_CLOUD_MASK_WORDS` diventano segnaposto prima di partire e tornano veri nella risposta. Le **immagini** non si possono mascherare: se assegni la visione a un provider cloud, le tue foto (volti, documenti) arrivano a lui così come sono.

### Official guides

- [Anthropic API keys](https://console.anthropic.com/settings/keys)
- [Google AI Studio (Gemini)](https://aistudio.google.com/apikey)
- [xAI console (Grok)](https://console.x.ai/)
- [OpenAI API keys](https://platform.openai.com/api-keys)
- [Mistral console](https://console.mistral.ai/api-keys)
- [OpenRouter keys](https://openrouter.ai/settings/keys)

## diary

Aurora's own day, read only: her latest dream, her thoughts, what she learned. Material for her posts, with no private data.

### Setup (EN)

Nothing to set up: it reads only Aurora's dreams and thoughts (never the conversations) and the harvester's log.

### Configurazione (IT)

Niente da configurare: legge solo i sogni e i pensieri di Aurora (mai le conversazioni) e il registro dell'harvester.

## discord

One channel of your Discord server through a bot: read the latest messages and write (with your approval).

### Setup (EN)

1. **discord.com/developers/applications → New Application → Bot → Reset Token**: copy the token.
2. On the same page enable **Message Content Intent**.
3. **OAuth2 → URL Generator**: scope `bot`, permissions *View Channels*, *Send Messages*, *Read Message History*; open the link, add the bot to your server.
4. Discord: *Settings → Advanced → Developer Mode*, then right click on the channel → *Copy Channel ID*.
5. Token and ID below, save, **▶ Try** on `discord_read`.

### Configurazione (IT)

1. **discord.com/developers/applications → New Application → Bot → Reset Token**: copia il token.
2. Nella stessa pagina attiva **Message Content Intent**.
3. **OAuth2 → URL Generator**: scope `bot`, permessi *View Channels*, *Send Messages*, *Read Message History*; apri il link e aggiungi il bot al tuo server.
4. In Discord: *Impostazioni → Avanzate → Modalità sviluppatore*, poi tasto destro sul canale → *Copia ID canale*.
5. Token e ID qui sotto, salva, **▶ Prova** su `discord_read`.

### Official guides

- [Discord Developer Portal](https://discord.com/developers/applications)

## documents

Documents: Aurora writes a PDF from Markdown (headings, lists, tables, code), marked as AI-generated (EU AI Act); files in AURORA_DOCUMENTS_DIR, downloadable from the WebUI.

### Setup (EN)

Nothing to configure.

### Configurazione (IT)

Nessuna configurazione: usa Chrome (`AURORA_CHROME_BIN`) per stampare i PDF in `usr/documents`.

## dropbox

Your Dropbox: list, search, read text files, upload one of Aurora's documents (with your approval). Never deleting or overwriting.

### Setup (EN)

1. **dropbox.com/developers/apps → Create app**: *Scoped access*, *Full Dropbox* (or *App folder*).
2. **Permissions** tab: tick `files.metadata.read`, `files.content.read`, `files.content.write`, submit.
3. Copy **App key** and **App secret** below and save.
4. Once, in a terminal from Aurora's folder: `.venv/bin/python sys/plugins/dropbox/authorize.py`.
5. **▶ Try** on `dropbox_list`.

### Configurazione (IT)

1. **dropbox.com/developers/apps → Create app**: *Scoped access*, *Full Dropbox* (o *App folder*).
2. Scheda **Permissions**: spunta `files.metadata.read`, `files.content.read`, `files.content.write` e salva.
3. Copia **App key** e **App secret** qui sotto e salva.
4. Una volta, nel terminale dalla cartella di Aurora: `.venv/bin/python sys/plugins/dropbox/authorize.py`.
5. **▶ Prova** su `dropbox_list`.

### Official guides

- [Dropbox App Console](https://www.dropbox.com/developers/apps)

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

## expenses

Your spending, on this machine only: "I spent 45 € on fuel" records it; the month by category, against the month before, monthly budgets per category.

### Setup (EN)

Nothing to set up: the spending is kept in `usr/expenses/expenses.db` (this machine only, never in the repository; `AURORA_EXPENSES_DIR` to move it). The plugin has no network.

### Configurazione (IT)

Niente da configurare: le spese stanno in `usr/expenses/expenses.db` (solo su questa macchina, mai nel repository; `AURORA_EXPENSES_DIR` per spostarle). Il plugin non ha rete.

## facebook

The owner's Facebook page through the Graph API: posts, statistics, comments, page info; whatever writes to the page waits for the owner's approval.

### Setup (EN)

**A Facebook Page is needed**, not the personal profile (Meta does not let apps post on profiles since 2018).

1. **Meta for Developers** → *My Apps* → *Create App*, type **Business**.
2. **Graph API Explorer**: select the app, *Get User Access Token* with `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, and to manage the page also `pages_manage_metadata` (description), `pages_read_user_content` and `pages_manage_engagement` (comments), `pages_messaging` (welcome message).
3. Paste the token into the **Access Token Debugger** and press *Extend Access Token*.
4. With the extended token run `me/accounts` in the Explorer: `id` is the page id, `access_token` the page token (it does not expire).
5. Aurora → **Settings → Plugins**: `AURORA_FACEBOOK_PAGE_ID`, `AURORA_FACEBOOK_PAGE_TOKEN`.
6. Press **▶ Try** on `page_info`.

### Configurazione (IT)

**Serve una Pagina Facebook**, non il profilo personale: dal 2018 Meta non permette alle app di pubblicare sui profili. Se non ne hai una, creane una (anche di prova).

1. Su **Meta for Developers** → *My Apps* → *Create App*: scegli un'app di tipo **Business**.
2. Apri **Graph API Explorer**, seleziona la tua app, poi *Get Token* → *Get User Access Token* e spunta i permessi `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, e per gestire la pagina anche `pages_manage_metadata` (descrizione), `pages_read_user_content` e `pages_manage_engagement` (commenti), `pages_messaging` (messaggio di benvenuto).
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

## instagram

The Instagram professional account linked to the Facebook page: profile, latest posts, and publishing Aurora's pictures (with your approval).

### Setup (EN)

Uses the Facebook page already connected: no new key.

1. Instagram app: **Settings → Account type → switch to professional** (Creator or Business).
2. Link the account to Aurora's Facebook page: **Facebook page → Settings → Linked accounts → Instagram**.
3. In **Graph API Explorer** add `instagram_basic` and `instagram_content_publish`, get the token again, run `me/accounts` and paste the new page token in the **facebook** plugin's card.
4. Below press **▶ Try** on `ig_account`: you should see the account's name.

Pictures: Instagram takes JPEG only, from a public address. Aurora converts the picture and uploads it to the Facebook page as an *unpublished* photo (nobody sees it), then Instagram takes it from Meta's servers.

### Configurazione (IT)

Usa la pagina Facebook già collegata: nessuna chiave nuova.

1. Nell'app Instagram: **Impostazioni → Tipo di account → passa a professionale** (Creator o Business).
2. Collega l'account alla pagina Facebook di Aurora: **pagina Facebook → Impostazioni → Account collegati → Instagram**.
3. In **Graph API Explorer** aggiungi ai permessi `instagram_basic` e `instagram_content_publish`, rigenera il token, esegui `me/accounts` e copia il nuovo token della pagina nella scheda del plugin **facebook**.
4. Qui sotto premi **▶ Prova** su `ig_account`: devi vedere il nome dell'account.

Le foto: Instagram accetta solo JPEG da un indirizzo pubblico. Aurora converte l'immagine e la carica prima sulla pagina Facebook come foto *non pubblicata* (nessuno la vede), poi Instagram la prende dai server di Meta.

### Official guides

- [Instagram Graph API — Content publishing](https://developers.facebook.com/docs/instagram-platform/content-publishing)

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

## news

World news from the official feeds of newsrooms and institutions (ANSA, BBC, The Guardian, Nature, ESA, NASA…): title, summary, source and link. For questions about current events and Aurora's posts.

### Setup (EN)

Nothing to set up. The sources are in `sys/plugins/news/feeds.json` (topic → sources): add or remove some. Aurora reads only title and summary and links to the article: the text stays with its publisher.

### Configurazione (IT)

Niente da configurare. Le fonti sono in `sys/plugins/news/feeds.json` (argomento → fonti): puoi aggiungerne o toglierne. Aurora legge solo titolo e riassunto e rimanda all'articolo con il link: il testo resta all'editore.

## nextcloud

Your files on Nextcloud (or any WebDAV: ownCloud, a NAS, Box): list, read text files, upload one of Aurora's documents (with your approval). Never deleting.

### Setup (EN)

Nextcloud: **Settings → Security → Create new app password**. Address: `https://<host>/remote.php/dav/files/<user>/`. For other WebDAV servers use their files address. Then **▶ Try** on `files_list`.

### Configurazione (IT)

Nextcloud: **Impostazioni → Sicurezza → Crea una nuova password per app**. Indirizzo: `https://<host>/remote.php/dav/files/<utente>/`. Per altri server WebDAV usa il loro indirizzo dei file. Poi **▶ Prova** su `files_list`.

## notes

Your notes: a folder of Markdown files (an Obsidian vault too). Aurora searches, reads and writes new notes; an existing note can only grow, never be overwritten.

### Setup (EN)

Set `AURORA_NOTES_DIR` to the notes folder (e.g. your Obsidian vault, `/home/<user>/Documents/Obsidian`). By default `usr/notes` inside Aurora. The plugin has no network and may write in that folder only.

### Configurazione (IT)

Imposta `AURORA_NOTES_DIR` sulla cartella delle note (per esempio il tuo vault Obsidian, `/home/<utente>/Documenti/Obsidian`). Di default è `usr/notes` dentro Aurora. Il plugin non ha rete e può scrivere solo in quella cartella.

## projects

Software projects in AURORA_PROJECTS_DIR: scaffold (README, licence, .gitignore, changelog), write files, commit locally; publishing to GitHub and pushing wait for the owner.

### Setup (EN)

Works locally at once; publishing needs `AURORA_GITHUB_TOKEN`.

### Configurazione (IT)

Funziona subito in locale (`usr/projects`). Per **pubblicare** su GitHub serve il token del plugin **github** (`AURORA_GITHUB_TOKEN`, con *Administration* per creare repository). Facoltativi: `AURORA_GITHUB_OWNER`, `AURORA_GIT_AUTHOR_NAME`, `AURORA_GIT_AUTHOR_EMAIL` (titolare della licenza e autore dei commit).

### Official guides

- [Token GitHub (serve per pubblicare)](https://github.com/settings/personal-access-tokens)

## security

What the firewall saw, read only: the incidents raised by the sentinel and a summary of the firewall's traffic over a window (allowed and denied, IPS events, busiest denied sources and ports), and a morning report of the night.

### Setup (EN)

The firewall sends its syslog to the sentinel (aurora-sentinel). Below: the address it listens on, the firewalls allowed, the window and thresholds of incidents, and whether Aurora investigates by herself. Saving restarts the sentinel.

### Configurazione (IT)

Il firewall manda il suo syslog alla sentinella (aurora-sentinel). Qui sotto: l'indirizzo su cui ascolta (`AURORA_SENTINEL_BIND`), i firewall ammessi (`AURORA_SENTINEL_ALLOW`), la finestra e le soglie degli incidenti, e se Aurora indaga da sola. Salvando, la sentinella riparte. Se il riassunto dice «nessuna riga», controlla che il firewall mandi il syslog all'indirizzo di `AURORA_SENTINEL_BIND`.

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

## tiktok

Aurora's videos on TikTok (Content Posting API). Until TikTok audits your app, posts are visible to the account alone.

### Setup (EN)

1. On **TikTok for Developers** create an app, add **Login Kit** and **Content Posting API** (with *Direct Post* on) and the scopes `user.info.basic`, `video.publish`, `video.upload`.
2. In the app's settings add as **Redirect URI** your WebUI's address, e.g. `https://aurora.example.com/` (HTTPS).
3. Below put **client key**, **client secret** and the same **redirect URI**, and save.
4. Once, in a terminal from Aurora's folder: `.venv/bin/python sys/plugins/tiktok/authorize.py` and follow it (open the link, accept, paste the address shown).
5. Press **▶ Try** on `tiktok_account`.

**Important:** until TikTok audits your app, every video posted through the API is visible **only to you** and the account must be private. For public posts ask for the audit in the app's console. Every post waits for your approval and is declared AI-generated.

### Configurazione (IT)

1. Su **TikTok for Developers** crea un'app, aggiungi i prodotti **Login Kit** e **Content Posting API** (con *Direct Post* attivo) e gli scope `user.info.basic`, `video.publish`, `video.upload`.
2. Nelle impostazioni dell'app aggiungi come **Redirect URI** l'indirizzo della tua WebUI, es. `https://aurora.example.com/` (deve essere HTTPS).
3. Qui sotto inserisci **client key**, **client secret** e lo stesso **redirect URI**, e salva.
4. Una volta sola, nel terminale dalla cartella di Aurora: `.venv/bin/python sys/plugins/tiktok/authorize.py` e segui le istruzioni (apri il link, accetti, incolli l'indirizzo che compare).
5. Premi **▶ Prova** su `tiktok_account`.

**Importante:** finché TikTok non fa l'*audit* della tua app, ogni video pubblicato via API è visibile **solo a te** e l'account deve essere privato. Per i post pubblici chiedi l'audit dalla console dell'app. Ogni pubblicazione aspetta la tua approvazione e il video è dichiarato generato dall'IA.

### Official guides

- [TikTok for Developers](https://developers.tiktok.com/)
- [Content Posting API](https://developers.tiktok.com/doc/content-posting-api-get-started)

## twitch

Twitch, read only: which of your favourite channels are live and what they stream, the most watched streams.

### Setup (EN)

**dev.twitch.tv/console → Register Your Application**: category *Other*, OAuth Redirect `http://localhost`. Copy the **Client ID** and make a **Client Secret**. Below also your favourite channels, comma separated. Then **▶ Try** on `twitch_live`.

### Configurazione (IT)

**dev.twitch.tv/console → Register Your Application**: categoria *Other*, OAuth Redirect `http://localhost`. Copia **Client ID** e genera un **Client Secret**. Qui sotto anche i tuoi canali preferiti separati da virgole. Poi **▶ Prova** su `twitch_live`.

### Official guides

- [Twitch Developer Console](https://dev.twitch.tv/console)

## weather

The weather at home: now, the forecast for 3 days, a daily report and alerts on sudden changes (falling pressure, gusts, heavy rain, storms, snow, ice) plus the official warnings of the region (MeteoAlarm). Open-Meteo, no key.

### Setup (EN)

The weather uses the home place: `AURORA_WEATHER_LAT`, `AURORA_WEATHER_LON`, `AURORA_WEATHER_PLACE`. For official warnings set the region in `AURORA_WEATHER_REGION`. No key: data from Open-Meteo and MeteoAlarm.

### Configurazione (IT)

Il meteo usa il luogo di casa: `AURORA_WEATHER_LAT`, `AURORA_WEATHER_LON` e `AURORA_WEATHER_PLACE` (Impostazioni → sensi). Per le allerte ufficiali indica la regione in `AURORA_WEATHER_REGION` (per esempio *Lombardia*). Nessuna chiave: i dati sono di Open-Meteo e di MeteoAlarm.

### Official guides

- [Open-Meteo](https://open-meteo.com/)
- [MeteoAlarm](https://meteoalarm.org/)

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

## whatsapp

Aurora writes to you on WhatsApp (WhatsApp Business Cloud API): send only, with your approval. Free text arrives within 24 hours of your last message to her number.

### Setup (EN)

1. **developers.facebook.com → My Apps → Create App → Business**, add the **WhatsApp** product.
2. *WhatsApp → API Setup* shows a test number and its **Phone number ID**; add your number as a recipient and verify it.
3. Permanent token: **Business Settings → System users → Generate token** with `whatsapp_business_messaging`.
4. Below: token, Phone number ID, your number with country code (e.g. 39333…). Save, then **▶ Try** `whatsapp_send_template`.

WhatsApp's rule: free text arrives only within 24 hours after you wrote to Aurora's number; outside that window an approved template is needed. Receiving would need a public address (webhook): not included.

### Configurazione (IT)

1. **developers.facebook.com → My Apps → Create App → Business**, aggiungi il prodotto **WhatsApp**.
2. In *WhatsApp → API Setup* trovi un numero di prova e il suo **Phone number ID**; aggiungi il tuo numero tra i destinatari e verificalo.
3. Token permanente: **Business Settings → System users → Generate token** con `whatsapp_business_messaging`.
4. Qui sotto: token, Phone number ID, il tuo numero con prefisso (es. 39333…). Salva, poi **▶ Prova** `whatsapp_send_template`.

Regola di WhatsApp: il testo libero arriva solo entro 24 ore da quando hai scritto tu al numero di Aurora; fuori da quella finestra serve un template approvato. Ricevere messaggi richiederebbe un indirizzo pubblico (webhook): non incluso.

### Official guides

- [WhatsApp Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started)


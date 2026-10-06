# Manual tests — what only the owner can check

What a person on a real device must see; everything here was measured by machine first. Mark ✅ / ❌ with a note.
Reload the WebUI first (the service worker caches the old pages). Tidied on 6 October 2026: done tests moved to the
end, duplicates and tests of pages that no longer exist removed (each with its reason).

| session | tests |
|---|---|
| 🌙 they come by themselves (look in the morning) | N19, N63, N77, N78, R4, R7 |
| 🔁 again after a change | N4, N5, N86, N88–N92 |
| 📱 phone, ~10 min | N16, N25, N31, N58, N59 |
| 🖥️ chat on the PC, ~15 min | I1–I5, N41, N42 |
| 🧭 pages, ~25 min | K1, K3, N3, N6, N32, N34, N35, N37, N39, N40, N43, N46, N47, N53, N57, N60, N62, N64–N66, N68, N70, N71, N73, N74, R1, R3, R10 |
| 🔑 a setup first (keys, devices, a second user) | N2, N13–N15, N18, N22, N23, N30, N33, N36, N38, N48–N51, N54–N56, N61, N67, N69, R2, R11 |

## Pages added on 2 October

| # | Test | Expected |
|---|---|---|
| N2 | 🧠 Models: choose a provider without a key | it is greyed out (— manca la chiave) and the server refuses it |
| N3 | 📖 Guide: open each «Apri →» | every page opens; the texts read well on the phone |
| N4 | ⚙️ Status → «Funzioni di questa installazione» | 10 ✅; nothing red — ❌ owner: incomplete — to be made dynamic, then again |
| N5 | ⚙️ Settings: categories | each category once (C71) — ❌ owner: on the phone the categories take half the screen — a 3-level menu, then again |
| N13 | 📅 calendar: an ICS link (Google → secret address) in the card, then «cosa ho in agenda questa settimana?» | the events, at the right local time |
| N14 | 📝 notes: AURORA_NOTES_DIR on your Obsidian vault, «cerca nelle mie note …», «aggiungi alla nota X …» | found; the addition waits for approval, the note only grows |
| N15 | 🏠 «che luci ci sono accese?» once devices are in Home Assistant | read from HA; switching asks for approval |
| N16 | In the installed app (phone): tap a picture Aurora made, then a PDF in 📎 Files | each opens inside the app; ⬇️ Download saves it; ✕ closes |
| N18 | 📔 Diary: open a dream; then a dream in the chat | its painting is shown (tap: the viewer); ↗ Condividi opens Social with the drafts and the picture; Publish posts it with the picture; a session memory has no Share |
| N19 | The morning routine (09:30) on a day with a dream | the post is published by itself with the picture, a notification «📣 Aurora ha pubblicato un post», the approvals list shows it as "auto"; a 4th post the same day waits |
| N22 | Put the TMDB key in Settings → Plugins → cinema; ask «quali film sono di tendenza questa settimana?» and «dove posso vedere Inception?» | the list with votes; where it streams in Italy (subscription, rent, buy) with the TMDB and JustWatch credit |
| N23 | «ho speso 45 € di benzina», then «quanto ho speso questo mese?», «metti un budget di 40 € per l'auto» | recorded with its #id; the month by category; ⚠️ budget passed |
| N25 | Hold 🗣️ in the chat | the device's voices, the best female one marked; ▶ plays a sample; tapping a name makes it Aurora's voice on this device |
| N30 | A second user with their own Facebook page in ⚙️ Settings (their token) | their posts go to their page, their autonomy and daily number are theirs; yours unchanged |
| N31 | On the phone, the first dictation after opening the app: 🎙️, speak 5 s, ⏹️ | the text is right the first time, it is sent by itself and the answer is read aloud |
| N32 | 💾 Backup card: the time 23:00, Save, reload the card | "next backup" says 23:0x (after `sudo bash sys/deploy/systemd/install.sh` once) |
| N33 | 🧠 Models: choose a provider in a step | a menu with its models; "other" for a name not listed |
| N34 | 📁 Files: 🗑️ on a PDF Aurora wrote | it is gone after the confirmation; a PDF of yours in that folder is refused |
| N35 | 🧩 Plugins: switch off the security plugin, then on | 🛡️ Security leaves the menu and comes back; 📣 Social lists only Facebook |
| N36 | As a second user: 🧩 Plugins; as the admin: 👥 on a plugin's card | the user sees no backup/security/senses and cannot switch plugins; a plugin shared appears for them |
| N37 | ⚙️ Settings, then 🧩 Plugins → facebook | Settings says which settings are in the cards; Facebook's card has ☑ "publishes by herself", the posts a day |
| N38 | 🔔 Notifications as a second user, then as the admin | the user has no incidents/backup/cloud; the admin has "Cloud" |
| N39 | 📎 Files: 🗑️ an attachment and a PDF, then ♻️ | both in the Trash with the day they go; restored where they were |
| N40 | 🔁 Routines: "days and times", 08:00 + 18:30, working days | saved; the line says "giorni lavorativi alle 08:00, 18:30"; it runs Monday, not on 8 December |
| N42 | Ask something not in the vault and not on arXiv (e.g. a Stoic philosopher's life), then "sì, cerca" | the search steps show Wikipedia (or Europe PMC/GitHub) candidates; the answer comes, the document in the right domain with its licence |
| N43 | 🛡️ Security → 📖 Read the documentation and propose; switch on a check with few incidents | proposals with "in the last 24 hours it would have raised N"; the next matching lines make an incident with its 💡 action |
| N46 | 📣 Social | "Posts to approve" (if any) and "Post history" with date, text, picture, a link to the post |
| N47 | 🛎️ Approvals and 🩺 Reports | approvals without posts and without self-reviews; reports with the self-reviews and repairs |
| N48 | 🧩 Plugins → security: address https://172.16.16.16:4444 style, user, password; 🛡️ Security | the firewall's API answers (C131); ⛔ on an incident appears |
| N49 | 🎧 DJ: upload a song you own (e.g. a church song), select it, style techno-trance, Create | a notification when ready; the mix plays in the page, in time and in key (or kept in its own time if it had no beat) |
| N50 | 🎧 DJ: two or three tracks, style house | one continuous mix at 124 BPM, crossfades on the beat |
| N51 | Log out, then log in again | name, password and the Authenticator's code (the API key still works from "use the key") |
| N53 | ⚙️ Settings → interface: personality "Filosofa", name "Sofia", gender female; reload | the top bar says Sofia; she answers as a philosopher; back to Aurora → your Aurora as before |
| N54 | 👥 Users → a new user with "nome della persona" | the assistant calls them by that name, not by their login |
| N55 | ❤️ Salute → Dieta: upload the dietitian's PDF; in the chat "cosa prevede la dieta per pranzo?" | the answer from the plan; on disk only sealed files |
| N56 | 🧠 Models: agent → a cloud provider; ask about the diet | "REFUSED": health data stays local; back to local |
| N57 | 🧠 Models page | "masking always on" |
| N58 | ☰ the side menu on the phone and on the PC | areas (Activity, Life, Work, Knowledge, System, Help): a tap opens one on the phone, hovering on the PC; the shown page's area stays open; an approval waiting puts a dot on its area |
| N59 | The top bar | the state dot beside the name, the bells under it; CPU/RAM and the GPUs on two rows; it fits the phone |
| N60 | 🛎️ Activity → 🔔 Notifications | "Notification history" on top: every alert with its time, 📱 or 🖥️; a click opens its page |
| N61 | 📁 Projects → 💻 Local → 🤖 Give Aurora a project | the brief goes to the chat; a 🧪 alert when its tests first pass, a 📁 alert at the end |
| N62 | PC, the side menu: pass the mouse over an area, then move up and right fast into its pages | the pages open in a panel beside the menu, nothing below moves; the panel stays while you cross; a phone still opens areas in place on tap |
| N63 | Phone: open the WebUI once (new service worker), then wait for a few alerts; 🔔 Notifications | "Last 7 days: N confirmed out of M sent" — N close to M |
| N64 | 📁 Projects → a project → 📝 Aurora's reports | her reports of every work on it, newest first |
| N65 | 🧭 Autonomy: choose "Equilibrata", then one area by hand | the levels change, "(personalizzato)" after the hand change; the daily line fills as she acts |
| N66 | 📣 Social: a draft naming a person → 🔍 Dati sensibili? → apply; 🗑️ Scarta another draft | the name replaced by "una persona a me cara"; the discarded draft gone |
| N67 | ❤️ Health → Esami: upload a real exam (PDF or photo) | after a minute 📈 shows its values; one outside the range says "parlane con il tuo medico"; correct a value |
| N68 | 📚 Harvester: tick a language; Security → 🛡️ Difesa | the language saved, the harvester restarts; the defence's mode, limits and history shown |
| N70 | 🛡️ Security → 📤 Cosa è uscito dalla macchina | today and 7 days: cloud calls, what was masked, posts, pushes, firewall actions |
| N71 | ✨ → 🧠 Cosa ricordo di te: open one, Dimentica | it disappears and does not come back after a reload |
| N73 | 🧭 Autonomy: click a few levels in a row | "✅ Salvato" every time, no "errore", the level highlighted at once |
| N74 | 🛡️ Security → an incident → ⛔ then ↩️ Annulla; Difesa → 🧱 Sul firewall → Prova la connessione | the address blocked then unblocked; the group and rule names shown, "Collegato" |
| N77 | Ask something she does not know; the next morning | the good morning says she studied it; ask again: an answer with sources — ❌ C152 — again after tonight |
| N78 | ☀️ The good morning in the chat (after 8) → 🔊 Ascolta | the night's counts, read aloud — ❌ C154 — again after the fix |
| N86 | 🧠 Models → 🎨: «Immagini nuove» to Google (or xAI), Save; ask «disegnami un faro al tramonto»; then put it back to Locale | the picture from the provider; Security → 📤 shows the call; back to local, local again |
| N88 | 🐞 → 💡 Proponi un'idea: tick two areas, write it, Save; change its state | it is in the list with its state; 📋 copies it |
| N89 | `bash uninstall.sh --dry-run 1` then `--dry-run 2` | the plan of each choice; nothing changed |
| N90 | ⚙️ Settings → ⚠️ Impostazioni di fabbrica (keys kept) | the behaviour settings back; folders, ports, NAS, firewall unchanged; the .env before saved |
| N91 | 🧩 Plugin → backup → ♻️ Ripristina un backup | the snapshots with their compatibility; 📋 the command (do not run it unless you want to restore) |
| N92 | As a user (alice): the menu | no Settings, Models, Security, Harvester, Status; 👥 My account → ⚙️ Le mie preferenze |
| N69 | Multi-user first login of an admin without password (a clean install) | after the API key, the Users page with the note: password and Google Authenticator first |
| N41 | 📁 Projects → 💻 Local: ask Aurora "crea il progetto prova-calc con una funzione somma e i suoi test, eseguili" | the project, the tests run (EXIT 0) in the run's steps, a local commit |
| N6 | 🧩 Plugins: open the page, then a card, then back | the grid appears at once; icons do not flash (C80) |

## Pictures

| # | Test | Expected |
|---|---|---|
| I1 | A real photo + "ritagliala un po' ai lati e mettila in bianco e nero" | the edited picture in Aurora's bubble, the original untouched |
| I2 | Then "ora ruotala di 90 gradi in senso orario" (no attachment) | the last edit rotated clockwise |
| I3 | Then "cosa c'è sullo sfondo?" | Aurora looks at the latest picture again |
| I4 | A very large photo (> 20 MP) and a PNG with transparency | edited without errors, the kind kept |
| I5 | 📎 Files page | thumbnails, open, delete (the conversation keeps only the name) |

## Projects, routines, plugins

| # | Test | Expected |
|---|---|---|
| R1 | 📁 Projects → a repository → 🔍 Preview on a project with an index.html | the page shows in the frame; it cannot reach Aurora |
| R2 | GitHub token with "All repositories" → 📁 Projects | the private repositories appear too |
| R3 | Routines → GitHub weekly report → ▶ Run now | a table of the repositories; a notification |
| R4 | Routines → Security "night report" (or your own routine) at 07:00 | the report arrives in the morning |
| R7 | Weather alerts on a stormy day | one notification per new alert, not one an hour |
| R10 | Plugins → 🛡️ security → settings | the sentinel's address, allowed firewalls, thresholds; saving restarts the sentinel |
| R11 | After signing: a routine asking for something no plugin does (e.g. "ogni sera dimmi quanti documenti ha raccolto l'harvester per fonte") | a forge request in the run, then "🔨 si è costruita un plugin" or "una capacità non è riuscita" — never a wrong plugin installed |

## Knowledge

| # | Test | Expected |
|---|---|---|
| K1 | Harvester page: domains and modes | your choices kept; law_it until exhausted moving on |
| K3 | Ordinary questions after the synthesis prompt changed (M48) | as good as before (M40 should be re-measured) |

## ✅ Done

| # | test | by, when |
|---|---|---|
| P1 | Chat → 📱/🖥️ button | owner, 6 Oct (the errors found: C155-C157, fixed) |
| P2 | 📷 on 📱 | owner, 6 Oct (the errors found: C155-C157, fixed) |
| P3 | 🎙️ on 📱: tap, speak ~10 s, tap | owner, 6 Oct (the errors found: C155-C157, fixed) |
| P4 | 🎙️ outdoors or with noise | owner, 6 Oct (the errors found: C155-C157, fixed) |
| P5 | 📎 a video from the gallery (30 s–2 min) + "riassumilo" | owner, 6 Oct (the errors found: C155-C157, fixed) |
| P6 | Leave the chat, come back | owner, 6 Oct (the errors found: C155-C157, fixed) |
| P7 | Push on the phone for a routine (Routines → ▶ Run now on the weather report) | owner, 6 Oct (the errors found: C155-C157, fixed) |
| P8 | Chat on 📱: «fammi un video di un gatto che gioca con la neve», then leave the app | owner, 6 Oct (the errors found: C155-C157, fixed) |
| P9 | While the video is being made, write anything | owner, 6 Oct (the errors found: C155-C157, fixed) |
| N1 | 🧠 Models: assign «sintesi» to Claude Code · sonnet, Save, ask a question | owner + machine, 5 Oct |
| N7 | ⚙️ Status → Backup → 💾 Run now (after the owner's setup) | owner, 6 Oct |
| N10 | 🛠️ Repairs after the 18:30 Facebook routine (on a day with news) | owner, 6 Oct |
| N24 | 🗣️ next to the microphone (default): dictate a question with 🎙️ and send it; then type one; tap 🗣️ to 🔊 (alway… | owner, 6 Oct |
| N44 | On the firewall: Backup & firmware → API on, Aurora's address allowed, a user; in the security card its addres… | owner, 5 Oct |
| N75 | Phone, the installed app: the chat | owner, 5 Oct |
| N76 | Status → 🧠 Sinapsi (after a night) | machine, 6 Oct (M113) |
| N79 | Ask a question, then the same in other words | owner, 5 Oct |
| N80 | `python sys/core/script/shadow_seed.py` in the day (about 2 hours, Ctrl-C and again is fine), then `--export` | owner, 6 Oct (M113) |
| N81 | «che tempo fa a Roma?» twice within 10 minutes | machine, 6 Oct (M114) |
| R6 | Chat: "che tempo farà domani?", "quante stelle ha il mio repository?", "cosa ha visto il firewall stanotte?" | machine, 6 Oct (weather and GitHub stars through the plugins) |
| K2 | "Cosa dice l'articolo 2043 del codice civile?" | machine, 6 Oct (from the shadow, 13 s) |
| N8 | 🐞 Report a bug: describe, tick a conversation, Prepare | machine, 6 Oct (M115: nothing private in the zip; not sent) |
| N11 | Chat: «che notizie ci sono oggi di tecnologia?» | machine as a user, 6 Oct (M116) |
| N17 | Ask a knowledge question (e.g. «Come funziona la fotosintesi?»), then tap one of the «Approfondisci» questions | machine as a user, 6 Oct (4 follow-ups; the tap is the owner's) |
| N20 | Ask «Mi spieghi la formula di Einstein-Cartan?» and a question whose answer is a table | machine as a user, 6 Oct (7 formulas) |
| N21 | In the chat: «fammi un grafico interattivo della funzione seno con uno slider»; then reopen the chat on anothe | machine as a user, 6 Oct |
| N72 | Ask a knowledge question | machine as a user, 6 Oct |
| R9 | An agent PDF ("/agente crea un PDF con…") | machine as a user, 6 Oct |
| R5 | A routine that cannot work (e.g. "read my e-mail" with e-mail not connected) | machine as a user, 6 Oct (then fixed: ❌ when it cannot) |
| N82 | ❤️ Salute → ⚕️ Medico: fill the hours, phone, notes, 💾 Salva; reload; then «a che ora riceve oggi il medico?» | owner, 6 Oct |
| N83 | `bash sys/core/script/sys_tts_install.sh`, then 🔊 on the good morning on the PC (Chrome on Linux) | owner, 6 Oct |
| N84 | 🤖 Agenti e routine: the icons; ➕ → 🔬 Ricerca, write the subject, plugin web, Salva; ▶ Esegui ora; then ⧉ Clona | owner, 6 Oct |
| N85 | 🛡️ Sicurezza → 🗺️ Mappa della rete: «Guarda la rete», search a device; switch on the proposed routine «Disposi | owner, 6 Oct |
| N87 | 🛡️ Security: the four tabs; Difesa e rete → 🗺️ Visualizza la mappa: zoom, drag, hover a device | owner, 6 Oct (the checks' layout: fixed after) |
| N26 | ⚙️ Settings → Users: read the explanation; set «multi», save; then (when there are other users) «single» | owner, 6 Oct (single → multi) |
| N27 | 👥 Users → My account: set your password, link the Authenticator (scan the QR, type the code); ⚙️ Settings → Us | owner, 6 Oct (user created and deleted) |
| N29 | 👥 Users → My account → 🔑 API keys: «Chatbox sul PC», Create; in Chatbox: OpenAI API, the address and model sho | owner, 6 Oct (Chatbox) |

## 🗑️ Removed

| # | why |
|---|---|
| N9 | the side menu changed (N58, N62) |
| N12 | the same as N10 |
| N28 | the same as N7 |
| N45 | inside N51 |
| N52 | inside N43 |
| R8 | the same as P7 |

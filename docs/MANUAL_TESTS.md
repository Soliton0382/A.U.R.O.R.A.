# Manual tests — what only the owner can check

What a person on a real device must see; everything here was measured by machine first. Mark ✅ / ❌ with a note.
Reload the WebUI first (the service worker caches the old pages). Tidied on 6 October 2026: done tests moved to the
end, duplicates and tests of pages that no longer exist removed (each with its reason).

| session | tests |
|---|---|
| 🌙 they come by themselves (look in the morning) | N19, N63, N77, N78 |
| 🔁 again after a change | I5, N25, N93–N100, N102–N106 |
| 📱 phone, ~10 min | N31 |
| 🖥️ chat on the PC, ~15 min | I4 |
| 🧭 pages, ~25 min | K1, N32, N35, N37, N40, N43, N46, N53, N62, N64, N66, N68, N73, N74, R1, R10 |
| 🔑 a setup first (keys, devices, a second user) | N13–N15, N18, N22, N30, N49–N51, N61, N67, N69, R2, R11 |

## Pages added on 2 October

| # | Test | Expected |
|---|---|---|
| N13 | 📅 calendar: an ICS link (Google → secret address) in the card, then «cosa ho in agenda questa settimana?» | the events, at the right local time |
| N14 | 📝 notes: AURORA_NOTES_DIR on your Obsidian vault, «cerca nelle mie note …», «aggiungi alla nota X …» | found; the addition waits for approval, the note only grows |
| N15 | 🏠 «che luci ci sono accese?» once devices are in Home Assistant | read from HA; switching asks for approval |
| N18 | 📔 Diary: open a dream; then a dream in the chat | its painting is shown (tap: the viewer); ↗ Condividi opens Social with the drafts and the picture; Publish posts it with the picture; a session memory has no Share |
| N19 | The morning routine (09:30) on a day with a dream | the post is published by itself with the picture, a notification «📣 Aurora ha pubblicato un post», the approvals list shows it as "auto"; a 4th post the same day waits |
| N22 | Put the TMDB key in Settings → Plugins → cinema; ask «quali film sono di tendenza questa settimana?» and «dove posso vedere Inception?» | the list with votes; where it streams in Italy (subscription, rent, buy) with the TMDB and JustWatch credit |
| N25 | Hold 🗣️ in the chat | the device's voices, the best female one marked; ▶ plays a sample; tapping a name makes it Aurora's voice on this device — ❌ owner: «nessuna voce»; now Aurora's voice is in the list (6 Oct): again |
| N30 | A second user with their own Facebook page in ⚙️ Settings (their token) | their posts go to their page, their autonomy and daily number are theirs; yours unchanged |
| N31 | On the phone, the first dictation after opening the app: 🎙️, speak 5 s, ⏹️ | the text is right the first time, it is sent by itself and the answer is read aloud |
| N32 | 💾 Backup card: the time 23:00, Save, reload the card | "next backup" says 23:0x (after `sudo bash sys/deploy/systemd/install.sh` once) |
| N35 | 🧩 Plugins: switch off the security plugin, then on | 🛡️ Security leaves the menu and comes back; 📣 Social lists only Facebook |
| N37 | ⚙️ Settings, then 🧩 Plugins → facebook | Settings says which settings are in the cards; Facebook's card has ☑ "publishes by herself", the posts a day |
| N40 | 🔁 Routines: "days and times", 08:00 + 18:30, working days | saved; the line says "giorni lavorativi alle 08:00, 18:30"; it runs Monday, not on 8 December |
| N43 | 🛡️ Security → 📖 Read the documentation and propose; switch on a check with few incidents | proposals with "in the last 24 hours it would have raised N"; the next matching lines make an incident with its 💡 action |
| N46 | 📣 Social | "Posts to approve" (if any) and "Post history" with date, text, picture, a link to the post |
| N49 | 🎧 DJ: upload a song you own (e.g. a church song), select it, style techno-trance, Create | a notification when ready; the mix plays in the page, in time and in key (or kept in its own time if it had no beat) |
| N50 | 🎧 DJ: two or three tracks, style house | one continuous mix at 124 BPM, crossfades on the beat |
| N51 | Log out, then log in again | name, password and the Authenticator's code (the API key still works from "use the key") |
| N53 | ⚙️ Settings → interface: personality "Filosofa", name "Sofia", gender female; reload | the top bar says Sofia; she answers as a philosopher; back to Aurora → your Aurora as before |
| N61 | 📁 Projects → 💻 Local → 🤖 Give Aurora a project | the brief goes to the chat; a 🧪 alert when its tests first pass, a 📁 alert at the end |
| N62 | PC, the side menu: pass the mouse over an area, then move up and right fast into its pages | the pages open in a panel beside the menu, nothing below moves; the panel stays while you cross; a phone still opens areas in place on tap |
| N63 | Phone: open the WebUI once (new service worker), then wait for a few alerts; 🔔 Notifications | "Last 7 days: N confirmed out of M sent" — N close to M — measured 61% (C164: urgency high since 6 Oct): look again on 13 Oct |
| N64 | 📁 Projects → a project → 📝 Aurora's reports | her reports of every work on it, newest first |
| N66 | 📣 Social: a draft naming a person → 🔍 Dati sensibili? → apply; 🗑️ Scarta another draft | the name replaced by "una persona a me cara"; the discarded draft gone |
| N67 | ❤️ Health → Esami: upload a real exam (PDF or photo) | after a minute 📈 shows its values; one outside the range says "parlane con il tuo medico"; correct a value |
| N68 | 📚 Harvester: tick a language; Security → 🛡️ Difesa | the language saved, the harvester restarts; the defence's mode, limits and history shown |
| N73 | 🧭 Autonomy: click a few levels in a row | "✅ Salvato" every time, no "errore", the level highlighted at once |
| N74 | 🛡️ Security → an incident → ⛔ then ↩️ Annulla; Difesa → 🧱 Sul firewall → Prova la connessione | the address blocked then unblocked; the group and rule names shown, "Collegato" |
| N77 | Ask something she does not know; the next morning | the good morning says she studied it; ask again: an answer with sources — ❌ C152; 7 Oct, the machine's part ✅ (M124: laser, entropy answered with sources): only the good morning at 9:30 to look at |
| N78 | ☀️ The good morning in the chat (after 8) → 🔊 Ascolta, on the phone and on the PC | the night's counts, read aloud — ❌ C154; ❌ 7 Oct «solo voci online» (C177) — again after reloading (v89); if it says «il browser ha bloccato l'audio», a second tap plays it |
| N93 | `sudo bash sys/deploy/nft/install.sh`; then 🛡️ Sicurezza → Difesa e rete → 🧱 | «Firewall di Aurora attivo»; from another PC (not the phone): `nc <aurora> 2222` → incident «Esca toccata», the PC kept off Aurora for 24 h, ↩️ lifts it |
| N94 | The chat open on the PC and on the phone (the app in the background); write on one | the other shows it by itself, also after waking up |
| N95 | «anima questa foto» with the video given to Google (Models → 🎨) | the video from Veo; while it is made, the bar «🎬 … in corso · circa N%» over the chat |
| N97 | The chat on the phone: a question, then the network cut for a few seconds (airplane mode) while she answers | «🔌 connessione persa: riprendo…», then the whole answer — no «network error» (C170) |
| N98 | Tomorrow between 9 and 22, silent for a while: the chat | at most 2 bubbles «🔁 Aurora ci ha ripensato» on an old answer, with its sources; tell whether they were worth it (M120) |
| N106 | 🍽️ As the user with the diet: Health → Diet → «Elabora documenti»; then «Scelgo questo» on a meal; turn the reminders on | the plan from the dietitian's document (28 meals, the frequencies' chips); a meal chosen shows ✅ and the week's chips move; at the next meal time a notification «🍽️ È ora di mangiare» and a bubble in the chat, answered there |
| N105 | 👤 Open the menu ☰ (PC and phone), then log in as another user | above the language and «Esci»: 🛡️ your name, «il tuo login · amministratore»; as the other user: 👤 their name and «utente» |
| N104 | 🛡️ Security: on an incident from outside, ⛔ Blocca | the card says it is blocked and closed; reload: it is among the closed ones, no new alert for that address; 🤝 Autonomy → statistics: security counts it as approved |
| N103 | Beside the green/yellow/red dot: the face (🥺 longing, 🧐 curiosity, 😣 stress…); mouse over it on the PC, tap it on the phone; then 📊 Health, in the morning and while she answers | «💗 Come si sente: prevale …» with seven rows, each with its causes; ask «come ti senti?» in the chat: she says it with the causes; the good morning ends with «💗 Stamattina prevale …» |
| N102 | 📣 Social → 🎬 a video → «come Reel» → ✔ Pubblica su Facebook | a Reel on the page (Reels tab); «come storia»: 24 h, no text; a video over 60 s as a story: refused with its length |
| N101 | ✅ owner, 7 Oct: published on Facebook. 📣 Social → 🎬 Video di Aurora: open «Perché il cielo è blu?», watch it, fix the post if needed, ✔ Pubblica su Facebook | the video on the page, with its text and «🤖 Contenuto generato…»; the post in the history below; then Instagram on (Plugins) and TikTok authorized: their buttons appear |
| N100 | The third video (black hole: natural voice, music); then 🔊 on an answer in the chat | the chat's voice is sample 3 (steadier, slower); in the video sample 5, the music low under it and fitting, the credit in the post |
| N99 | Watch the two pilot videos (laser, free will: usr/<you>/images/stories/) | the pictures fit the words, the voice is clear, subtitles readable, the label «Generato con IA» visible; tell what to change |
| N96 | 🛡️ → 📊 La settimana della sicurezza; and on Monday 08:30 the routine (switch it on in Agenti e routine) | the score, campaigns, what is missing |
| N69 | Multi-user first login of an admin without password (a clean install) | after the API key, the Users page with the note: password and Google Authenticator first |

## Pictures

| # | Test | Expected |
|---|---|---|
| I4 | A very large photo (> 20 MP) and a PNG with transparency | edited without errors, the kind kept |
| I5 | 📎 Files page | thumbnails, open, delete (the conversation keeps only the name) — owner: no PDF thumbnails; now the first page (6 Oct): again |

## Projects, routines, plugins

| # | Test | Expected |
|---|---|---|
| R1 | 📁 Projects → a repository → 🔍 Preview on a project with an index.html | the page shows in the frame; it cannot reach Aurora |
| R2 | GitHub token with "All repositories" → 📁 Projects | the private repositories appear too |
| R10 | Plugins → 🛡️ security → settings | the sentinel's address, allowed firewalls, thresholds; saving restarts the sentinel |
| R11 | After signing: a routine asking for something no plugin does (e.g. "ogni sera dimmi quanti documenti ha raccolto l'harvester per fonte") | a forge request in the run, then "🔨 si è costruita un plugin" or "una capacità non è riuscita" — never a wrong plugin installed |

## Knowledge

| # | Test | Expected |
|---|---|---|
| K1 | Harvester page: domains and modes | your choices kept; law_it until exhausted moving on |

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
| N2 | 🧠 Models: choose a provider without a key | machine, 6 Oct (M118) |
| N57 | 🧠 Models page | machine, 6 Oct (M118) |
| N60 | 🛎️ Activity → 🔔 Notifications | machine, 6 Oct (M118) |
| N70 | 🛡️ Security → 📤 Cosa è uscito dalla macchina | machine, 6 Oct (M118) |
| N91 | 🧩 Plugin → backup → ♻️ Ripristina un backup | machine, 6 Oct (M118) |
| N47 | 🛎️ Approvals and 🩺 Reports | machine, 6 Oct (M118) |
| R3 | Routines → GitHub weekly report → ▶ Run now | machine, 6 Oct (M118) |
| R4 | Routines → Security "night report" (or your own routine) at 07:00 | machine, 6 Oct (M118) |
| R7 | Weather alerts on a stormy day | machine, 6 Oct (M118) |
| N3 | 📖 Guide: open each «Apri →» | machine, 6 Oct (M118) |
| N6 | 🧩 Plugins: open the page, then a card, then back | machine, 6 Oct (M118) |
| N59 | The top bar | machine, 6 Oct (M118) |
| N92 | As a user (alice): the menu | machine, 6 Oct (M118) |
| N23 | «ho speso 45 € di benzina», then «quanto ho speso questo mese?», «metti un budget di 40 € per l'auto» | machine, 6 Oct (M118) |
| N54 | 👥 Users → a new user with "nome della persona" | machine, 6 Oct (M118) |
| N71 | ✨ → 🧠 Cosa ricordo di te: open one, Dimentica | machine, 6 Oct (M118) |
| N88 | 🐞 → 💡 Proponi un'idea: tick two areas, write it, Save; change its state | machine, 6 Oct (M118) |
| N34 | 📁 Files: 🗑️ on a PDF Aurora wrote | machine, 6 Oct (M118) |
| N39 | 📎 Files: 🗑️ an attachment and a PDF, then ♻️ | machine, 6 Oct (M118) |
| N55 | ❤️ Salute → Dieta: upload the dietitian's PDF; in the chat "cosa prevede la dieta per pranzo?" | machine, 6 Oct (M118) |
| N56 | 🧠 Models: agent → a cloud provider; ask about the diet | machine, 6 Oct (M118) |
| I1 | A real photo + "ritagliala un po' ai lati e mettila in bianco e nero" | machine, 6 Oct (M118) |
| I2 | Then "ora ruotala di 90 gradi in senso orario" (no attachment) | machine, 6 Oct (M118) |
| I3 | Then "cosa c'è sullo sfondo?" | machine, 6 Oct (M118) |
| N36 | As a second user: 🧩 Plugins; as the admin: 👥 on a plugin's card | machine, 6 Oct (M118) |
| N38 | 🔔 Notifications as a second user, then as the admin | machine, 6 Oct (M118) |
| N89 | `bash uninstall.sh --dry-run 1` then `--dry-run 2` | machine, 6 Oct (M118) |
| N58 | ☰ the side menu on the phone and on the PC | owner, 5 Oct («la ui sul cel va benissimo») |
| N48 | 🧩 Plugins → security: address https://172.16.16.16:4444 style, user, password; 🛡️ Security | owner + machine, 6 Oct (the network map reads the firewall's API; N44 blocked) |
| N33 | 🧠 Models: choose a provider in a step | machine, 6 Oct (12 steps, each with its menu of models) |
| N4 | ⚙️ Status → «Funzioni di questa installazione» | machine, 6 Oct (M119) |
| N5 | ⚙️ Settings: categories | owner, 6 Oct |
| N16 | In the installed app (phone): tap a picture Aurora made, then a PDF in 📎 Files | owner, 6 Oct |
| N41 | 📁 Projects → 💻 Local: ask Aurora "crea il progetto prova-calc con una funzione somma e i suoi test, eseguili" | machine as a user, 6 Oct |
| N42 | Ask something not in the vault and not on arXiv (e.g. a Stoic philosopher's life), then "sì, cerca" | machine as a user, 6 Oct (after C166) |
| N90 | ⚙️ Settings → ⚠️ Impostazioni di fabbrica (keys kept) | machine in the test clone, 6 Oct (M119) |
| N86 | 🧠 Models → 🎨: «Immagini nuove» to Google (or xAI), Save; ask «disegnami un faro al tramonto»; then put it back | owner, 6 Oct (the picture; the video after C168) |

## 🗑️ Removed

| # | why |
|---|---|
| N9 | the side menu changed (N58, N62) |
| N12 | the same as N10 |
| N28 | the same as N7 |
| N45 | inside N51 |
| N52 | inside N43 |
| R8 | the same as P7 |
| N65 | inside N73 (the same clicks on the autonomy levels) |
| K3 | a quality measure, not a manual test: bench_quality (M40, M110) |

# Manual tests — what only the owner can check

Everything below was measured by machine (M43–M52), but not by a person on a real device. One pass, top to bottom;
mark each line ✅ / ❌ with a note. Reload the WebUI first (the service worker caches the old pages).

## Phone (PWA)

| # | Test | Expected |
|---|---|---|
| P1 | Chat → 📱/🖥️ button | starts on 📱 on the phone, 🖥️ on the PC; the choice is remembered |
| P2 | 📷 on 📱 | the phone's camera opens; the photo appears as a chip, then Aurora describes it |
| P3 | 🎙️ on 📱: tap, speak ~10 s, tap | the first time the browser asks for the microphone; the text appears in the box (~5–10 s) |
| P4 | 🎙️ outdoors or with noise | the transcript is still usable, or Aurora says it heard nothing clear |
| P5 | 📎 a video from the gallery (30 s–2 min) + "riassumilo" | scenes in order with times, what is said; time in the run (not measured on phone footage) |
| P6 | Leave the chat, come back | the photos and videos sent are in the conversation again |
| P7 | Push on the phone for a routine (Routines → ▶ Run now on the weather report) | a notification "☀️ Il meteo di oggi" |

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
| R5 | A routine that cannot work (e.g. "read my e-mail" with e-mail not connected) | ❌ and a notification "una routine non è riuscita", never ⏳ forever |
| R6 | Chat: "che tempo farà domani?", "quante stelle ha il mio repository?", "cosa ha visto il firewall stanotte?" | answered with the plugins, not from the vault |
| R7 | Weather alerts on a stormy day | one notification per new alert, not one an hour |

## Knowledge

| # | Test | Expected |
|---|---|---|
| K1 | Harvester page: domains and modes | your choices kept; law_it until exhausted moving on |
| K2 | "Cosa dice l'articolo 2043 del codice civile?" | the article from Normattiva, cited |
| K3 | Ordinary questions after the synthesis prompt changed (M48) | as good as before (M40 should be re-measured) |

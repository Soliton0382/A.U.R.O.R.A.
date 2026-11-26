# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The chat's «/» commands (the owner, 26 Nov: «se nella chat metto / non vengono elencati gli strumenti… utile nel
caso si voglia una cosa specifica; la cosa migliore è il routing automatico»; then «aggiungere anche tutto il resto
che potrebbe essere utile nel menu /»): a way to ask for one tool by name, the automatic routing staying the default.

Each command names what does the work: «agent» (the tools' agent, told which tool or plugin to use), «arxiv» (the
arXiv agent: papers searched and imported), «lean» (kno_prove_chat's own: never handled here). A command tied to a
plugin is listed only while that plugin is available (connected, configured, no error). The WebUI's composer lists
them when a message starts with «/» (GET /v1/aurora/chat/commands); core_route.answer_or_acquire acts on them."""
from __future__ import annotations

import re

#           cmd            aliases                kind     plugin         hint for the agent (English)
_C = [
    ("/calcola", ("calc", "compute"), "agent", None, "the compute tool",
     "Calcola invece di ricordare: un programma Python nella gabbia (numpy, scipy, sympy)",
     "Compute instead of remembering: a Python program in the cage (numpy, scipy, sympy)",
     "/calcola frequenza di risonanza di un LC con 10 mH e 1 µF"),
    ("/fem", (), "agent", None, "the compute tool with fem=true (FEniCSx: first a case whose exact solution is known, "
     "then the problem)",
     "Elementi finiti con FEniCSx (Poisson, magnetostatica, correnti parassite, calore)",
     "Finite elements with FEniCSx (Poisson, magnetostatics, eddy currents, heat)",
     "/fem temperatura in una piastra quadrata con un lato a 100 °C e gli altri a 0"),
    ("/lean", (), "lean", None, "", "Dimostrazione formale con Lean 4 + Mathlib, verificata da Aurora",
     "A formal proof with Lean 4 + Mathlib, checked by Aurora", "/lean la somma di due numeri pari è pari"),
    ("/arxiv", ("paper",), "arxiv", None, "", "Cerca articoli su arXiv e li porta nel vault, con le fonti",
     "Search arXiv and bring the papers into the vault, with sources", "/arxiv magnon squeezing YIG"),
    ("/cerca", ("web",), "agent", "web", "the web plugin's search, then read the best pages",
     "Cerca sul web e leggi le pagine migliori", "Search the web and read the best pages",
     "/cerca orari del museo della scienza di Milano"),
    ("/leggi", ("url",), "agent", "web", "the web plugin's fetch_url on the address given",
     "Leggi una pagina web e riassumila", "Read a web page and sum it up", "/leggi https://esempio.it/articolo"),
    ("/immagine", ("foto", "img"), "agent", None, "the create_picture tool",
     "Disegna un'immagine nuova", "Paint a new picture", "/immagine un gatto astronauta, acquerello"),
    ("/pagina", ("grafico", "chart"), "agent", None, "an artifact (an interactive page shown in the chat)",
     "Una pagina interattiva in chat: un grafico, una simulazione, un calcolatore",
     "An interactive page in the chat: a chart, a simulation, a calculator", "/pagina grafico di sin(x)/x da -20 a 20"),
    ("/pdf", ("documento",), "agent", "documents", "the documents plugin's create_pdf",
     "Scrive un documento PDF (marcato come generato da IA)", "Write a PDF document (marked as AI-generated)",
     "/pdf riassunto di quello che ci siamo detti oggi"),
    ("/documento", ("odt", "word"), "agent", "documents", "the documents plugin's create_odt (an editable .odt)",
     "Scrive un documento modificabile (.odt, per Writer e Word)", "Write an editable document (.odt, for Writer and Word)",
     "/documento verbale della riunione di oggi con i punti decisi"),
    ("/traduci", (), "agent", None, "no tool: translate the text faithfully, keeping its layout (lists, headings)",
     "Traduce un testo mantenendone la forma", "Translate a text keeping its layout", "/traduci in inglese: Buongiorno a tutti"),
    ("/confronta", ("diff",), "agent", None, "the compute tool with Python's difflib on the two texts given, then explain "
     "what changed", "Confronta due testi: cosa è cambiato", "Compare two texts: what changed",
     "/confronta «versione A …» con «versione B …»"),
    ("/nota", ("note",), "agent", "notes", "the notes plugin (search, read or write a note)",
     "Le tue note: cerca, leggi, scrivi", "Your notes: search, read, write", "/nota scrivi: comprare il latte"),
    ("/promemoria", ("ricorda", "appuntamento"), "agent", "calendar", "the calendar plugin (an event or a reminder)",
     "Un appuntamento o un promemoria nel calendario", "An event or a reminder in the calendar",
     "/promemoria dentista giovedì alle 15"),
    ("/meteo", (), "agent", "weather", "the weather plugin", "Il meteo: adesso e i prossimi giorni",
     "The weather: now and the next days", "/meteo domani"),
    ("/notizie", ("news",), "agent", "news", "the news plugin", "Le notizie di oggi su un argomento",
     "Today's news on a topic", "/notizie fisica quantistica"),
    ("/email", ("posta",), "agent", "email", "the email plugin (list or read; sending waits for the owner's approval)",
     "La tua posta: le non lette, un messaggio", "Your mail: unread, one message", "/email non lette di oggi"),
    ("/casa", ("ha",), "agent", "homeassistant", "the homeassistant plugin", "La casa: dispositivi, stati, comandi",
     "The house: devices, states, commands", "/casa temperatura del soggiorno"),
    ("/spese", ("soldi",), "agent", "expenses", "the expenses plugin", "Entrate e uscite: registra o riassumi",
     "Income and expenses: record or sum up", "/spese quanto ho speso questo mese"),
    ("/progetto", (), "agent", "projects", "the projects plugin", "I tuoi progetti: elenca, leggi, crea",
     "Your projects: list, read, create", "/progetto elenca i file di vuoto-dinamico"),
    ("/circuito", (), "agent", "circuits", "the circuits plugin (schematic, simulation with ngspice)",
     "Un circuito: schema e simulazione", "A circuit: schematic and simulation", "/circuito filtro RC passa-basso a 1 kHz"),
    ("/cad", (), "agent", "cad", "the cad plugin", "Un pezzo in 3D: modello e disegni", "A 3-D part: model and drawings",
     "/cad staffa a L 40×40×3 mm con due fori da 5"),
    ("/cielo", ("sky",), "agent", "sky", "the sky plugin", "Il cielo di stanotte per le riprese",
     "Tonight's sky for imaging", "/cielo M31 stanotte"),
    ("/ip", (), "agent", "netintel", "the netintel plugin", "Informazioni difensive su un indirizzo IP",
     "Defensive information on an IP address", "/ip 203.0.113.7"),
    ("/link", (), "agent", "linkcheck", "the linkcheck plugin", "La reputazione di un link prima di aprirlo",
     "A link's reputation before opening it", "/link https://esempio.it"),
    ("/desktop", ("desk",), "agent", None, "the desktop_skills tool (read only: what she knows, step by step)",
     "Cosa sai fare sul desktop: le procedure imparate, passo per passo",
     "What she can do on a desktop: the procedures learned, step by step", "/desktop come salvi un file con Kate?"),
    ("/telefono", ("tel",), "agent", None, "the phone (the Aurora app on the owner's phone)",
     "Sul telefono: sveglia, timer, apri, naviga, chiama", "On the phone: alarm, timer, open, navigate, call",
     "/telefono sveglia alle 7"),
]
COMMANDS = [{"cmd": c, "aliases": a, "kind": k, "plugin": p, "hint": h, "it": it, "en": en, "example": ex}
            for c, a, k, p, h, it, en, ex in _C]
_BY = {n: c for c in COMMANDS for n in (c["cmd"][1:], *c["aliases"])}
WORD = re.compile(r"^\s*/([a-zà-ù]+)\b[\s:,.\-–]*", re.I)


def listing(lang: str = "it", available: set[str] | None = None) -> list[dict]:
    """The commands to show: those whose plugin is available (all built-in ones always)."""
    key = "en" if lang == "en" else "it"
    return [{"cmd": c["cmd"], "text": c[key], "example": c["example"]} for c in COMMANDS
            if not c["plugin"] or available is None or c["plugin"] in available]


def forced(question: str, available: set[str] | None = None) -> tuple[dict, str] | None:
    """(the command, the rest of the message) for a command this module handles; None for no command, for /lean
    (kno_prove_chat's), and for a command whose plugin is not available (the normal routing answers then)."""
    m = WORD.match(question or "")
    c = _BY.get(m.group(1).lower()) if m else None
    if c is None or c["kind"] == "lean" or (c["plugin"] and available is not None and c["plugin"] not in available):
        return None
    return c, question[m.end():].strip()


def goal(c: dict, rest: str) -> str:
    """The agent's goal: the owner asked for this tool by name."""
    return (f"The owner asked for {c['cmd']} by name: do it with {c['hint']}, then answer in the owner's language from "
            f"what the tool returned (a computation: say it was computed). The request: {rest}")

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📱 Actions on the owner's phone (N68, owner, 1 Nov: «l'app dovrebbe … aprire il browser fare ricerche aggiungere
calendar, altrimenti sarebbe solo un assistenza povero di azioni»).

The agent's phone_action is checked here and goes to the conversation as an event (phone.action); the WebUI hands it
to the Android app (AuroraApp.act → PhoneActions), which gives it to the phone's own app: the browser, the clock, the
calendar, the maps, the dialler. A call or a message is only prepared — the owner presses call or send. In a browser
without the app the page offers what it can (a link). Nothing is done on the phone from a run nobody asked for."""
from __future__ import annotations

import json
import re
import secrets
from datetime import datetime
from .sys_lang import say as _t   # each sentence in the reader's language (C526)

ACTIONS = ("open_url", "web_search", "open_app", "alarm", "timer", "calendar", "navigate", "call", "message")

TOOL = {"name": "phone_action", "description": "Do something on the owner's phone, where the Aurora app runs: open a "
        "web page, search the web in the phone's browser, open an app by its name, set an alarm or a timer, put an "
        "event in the PHONE's calendar (Aurora's own calendar has its own tools), start the navigation to a place, "
        "prepare a call or a message to a number or to a contact by name (the owner presses call or send: it is never "
        "sent alone). Only when the owner asks for it on the phone.",
        "input_schema": {"type": "object", "properties": {
            "action": {"type": "string", "enum": list(ACTIONS)},
            "url": {"type": "string", "description": "open_url: the address, https"},
            "query": {"type": "string", "description": "web_search: the words to search"},
            "app": {"type": "string", "description": "open_app: the app's name as the phone shows it"},
            "hour": {"type": "integer"}, "minute": {"type": "integer"},
            "seconds": {"type": "integer", "description": "timer: its length"},
            "label": {"type": "string", "description": "alarm, timer: a short label"},
            "title": {"type": "string"}, "start": {"type": "string", "description": "calendar: local time, "
                                                                                     "YYYY-MM-DDTHH:MM"},
            "end": {"type": "string"}, "location": {"type": "string"},
            "destination": {"type": "string", "description": "navigate: an address or a place"},
            "contact": {"type": "string", "description": "call, message: the contact's name"},
            "number": {"type": "string"}, "text": {"type": "string", "description": "message: what it says"},
            "via": {"type": "string", "enum": ["sms", "whatsapp"]}},
            "required": ["action"]}}

SAID = {"open_url": "📱 apro {url}", "web_search": "🔎 cerco «{query}»", "open_app": "📱 apro {app}",
        "alarm": "⏰ sveglia alle {hour:02d}:{minute:02d}", "timer": "⏱️ timer di {mins}",
        "calendar": "📅 «{title}» nel calendario del telefono", "navigate": "🧭 navigazione verso {destination}",
        "call": "📞 chiamata a {who} (premi chiama)", "message": "💬 messaggio a {who} (premi invia)"}
SAID_EN = {"open_url": "📱 opening {url}", "web_search": "🔎 searching «{query}»", "open_app": "📱 opening {app}",
           "alarm": "⏰ alarm at {hour:02d}:{minute:02d}", "timer": "⏱️ timer of {mins}",
           "calendar": "📅 «{title}» in the phone's calendar", "navigate": "🧭 navigation to {destination}",
           "call": "📞 call to {who} (press call)", "message": "💬 message to {who} (press send)"}


def _ms(when: str) -> int:
    return int(datetime.fromisoformat(when.strip()).timestamp() * 1000)    # a naive time: this machine's zone


def prepare(args: dict) -> dict | str:
    """The action checked and in the app's form, or "ERROR: …" for the agent to correct."""
    a = str(args.get("action", ""))
    if a not in ACTIONS:
        return f"ERROR: action is one of {', '.join(ACTIONS)}"
    out: dict = {"id": secrets.token_hex(6), "action": a}
    try:
        if a == "open_url":
            url = str(args.get("url", "")).strip()
            if not re.match(r"https?://[^\s]+$", url):
                return "ERROR: open_url needs a full address (https://…)"
            out["url"] = url
        elif a == "web_search":
            out["query"] = str(args.get("query", "")).strip()[:300]
        elif a == "open_app":
            out["app"] = str(args.get("app", "")).strip()[:60]
        elif a == "alarm":
            out["hour"], out["minute"] = int(args["hour"]), int(args.get("minute") or 0)
            if not (0 <= out["hour"] < 24 and 0 <= out["minute"] < 60):
                return "ERROR: alarm: hour 0-23, minute 0-59"
            out["label"] = str(args.get("label") or "Aurora")[:60]
        elif a == "timer":
            out["seconds"] = int(args["seconds"])
            if not 1 <= out["seconds"] <= 86400:
                return "ERROR: timer: seconds 1-86400"
            out["label"] = str(args.get("label") or "Aurora")[:60]
        elif a == "calendar":
            out["title"] = str(args.get("title", "")).strip()[:120]
            out["begin_ms"] = _ms(str(args["start"]))
            out["end_ms"] = _ms(str(args["end"])) if args.get("end") else out["begin_ms"] + 3600_000
            out["location"] = str(args.get("location") or "")[:120]
        elif a == "navigate":
            out["destination"] = str(args.get("destination", "")).strip()[:200]
        else:                                                    # call, message
            out["number"] = re.sub(r"[^\d+]", "", str(args.get("number") or ""))[:20]
            out["contact"] = str(args.get("contact") or "").strip()[:60]
            if not out["number"] and not out["contact"]:
                return f"ERROR: {a} needs a number or a contact's name"
            if a == "message":
                out["text"] = str(args.get("text") or "")[:1000]
                out["via"] = "whatsapp" if args.get("via") == "whatsapp" else "sms"
    except (KeyError, TypeError, ValueError) as e:
        return f"ERROR: {a}: {type(e).__name__} {e}"
    if any(out.get(k) == "" for k in ("query", "app", "title", "destination")):
        return f"ERROR: {a}: an empty value"
    return out


def said(act: dict) -> str:
    """The action in a few words, for the conversation."""
    s = act.get("seconds", 0)
    mins = f"{s // 60} min" + (f" {s % 60} s" if s % 60 else "") if s >= 60 else f"{s} s"
    return _t(SAID, SAID_EN)[act["action"]].format_map({**act, "mins": mins, "who": act.get("contact") or act.get("number")})


# ⚡ The plain commands, understood without a model (owner, 1 Nov: «mi serve la stessa reattività della chiamata… per
# aprire YouTube non può impiegarci un minuto» — the agent took 15–92 s to choose the tool): Italian as Whisper writes
# it; used by the call (api/call.py), the assistant's way in. Anything not matched goes to Aurora as before.
_NUM = {"un": 1, "uno": 1, "una": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5, "sei": 6, "sette": 7, "otto": 8,
        "nove": 9, "dieci": 10, "undici": 11, "dodici": 12, "quindici": 15, "venti": 20, "trenta": 30, "quaranta": 40,
        "cinquanta": 50, "sessanta": 60}
_POLITE = {"aprire": "apri", "avviare": "avvia", "lanciare": "lancia", "chiamare": "chiama", "telefonare": "telefona",
           "mettere": "metti", "mettermi": "mettimi", "impostare": "imposta", "cercare": "cerca", "cercarmi": "cercami",
           "portarmi": "portami", "svegliarmi": "svegliami", "scrivere": "scrivi", "mandare": "manda", "inviare": "invia"}
# what the house's plugin does («apri il cancello»), never taken for an app
_HOUSE = re.compile(r"\b(porta|portone|cancell|finestr|tapparell|serrand|garage|box|luc[ei]|lampad|presa|condizionator|"
                    r"riscaldament|termostat|allarme)", re.I)
_I = re.I
_TIMER = re.compile(r"^(?:metti|imposta|fai partire|avvia|fammi|parti con)?\s*(?:un |il )?timer (?:di |da |per )?(\w+)\s*"
                    r"(second|minut|or[ae])\w*(?: e (\w+)(?: second\w*)?)?$", _I)
_HALF = re.compile(r"^(?:metti|imposta|fai partire|avvia)?\s*(?:un |il )?timer (?:di |da )?mezz'?\s?ora$", _I)
_ALARM = (re.compile(r"^(?:metti(?:mi)? |imposta |punta )?(?:la |una )?sveglia (?:per )?(?:domani )?(?:mattina )?"
                     r"(?:alle |per le |a )(\w+)(?:[:.,]| e )?(\d{2}|mezza|un quarto)?$", _I),
          re.compile(r"^svegliami (?:domani )?(?:mattina )?(?:alle |a )(\w+)(?:[:.,]| e )?(\d{2}|mezza|un quarto)?$", _I))
_APP = re.compile(r"^(?:apri|avvia|lancia|fammi vedere) (?:l'app |l'applicazione |app )?(.{2,40})$", _I)
_NAV = re.compile(r"^(?:portami|naviga|navigatore|indicazioni(?: stradali)?|come arrivo|come si arriva) (?:per |verso |"
                  r"fino |a casa di )?(?:a |in |al |alla |allo |ai |alle |all')?(.{2,120})$", _I)
_SEARCH = (re.compile(r"^(?:cerca|ricerca|cercami) (?:su internet|sul web|in rete|su google|online) (.{2,200})$", _I),
           re.compile(r"^(?:cerca|cercami) (.{2,200}) (?:su internet|sul web|in rete|su google|online)$", _I))
_CALL = re.compile(r"^(?:chiama|telefona a|fai una chiamata a) (.{2,40})$", _I)
_MSG = re.compile(r"^(?:scrivi|manda un messaggio|invia un messaggio|manda un whatsapp|scrivi su whatsapp) (?:a )?"
                  r"(\S+(?: \S+)?) (?:su whatsapp )?(?:che|dicendo|:) (.{1,500})$", _I)


def _num(w: str) -> float:
    w = str(w or "").lower()
    return int(w) if w.isdigit() else _NUM.get(w, float("nan"))


def quick(text: str) -> dict | None:
    """A plain command for the phone in the app's form (with its id), or None."""
    s = re.sub(r"[.!?¿¡]+$", "", text.strip())
    s = re.sub(r"^(ehi |ok |hey )?aurora,?\s*", "", s, flags=_I)
    s = re.sub(r"\b(per favore|per piacere|grazie)\b", "", s, flags=_I)
    s = re.sub(r"\s+", " ", re.sub(r"\b(un|una)'", r"\1 ", s, flags=_I)).strip()
    s = re.sub(r"^((puoi|potresti|riesci a|mi|me) )+", "", s, flags=_I)
    s = re.sub(r"^(\w+)", lambda m: _POLITE.get(m.group(1).lower(), m.group(1)), s)
    act = _match(s)
    return {"id": secrets.token_hex(6), **act} if act else None


def _match(s: str) -> dict | None:
    if m := _TIMER.match(s):
        n = _num(m.group(1))
        if n != n:                                               # NaN: not a number said
            return None
        u = m.group(2).lower()
        secs = n if u.startswith("second") else n * 60 + (_num(m.group(3)) if m.group(3) else 0) if u.startswith("minut") \
            else n * 3600
        return None if secs != secs or not 1 <= secs <= 86400 else {"action": "timer", "seconds": int(secs), "label": "Aurora"}
    if _HALF.match(s):
        return {"action": "timer", "seconds": 1800, "label": "Aurora"}
    for rx in _ALARM:
        if m := rx.match(s):
            h, tail = _num(m.group(1)), (m.group(2) or "").lower()
            mins = 30 if "mezza" in tail else 15 if "quarto" in tail else int(tail or 0)
            return {"action": "alarm", "hour": int(h), "minute": mins, "label": "Aurora"} if 0 <= h < 24 and mins < 60 else None
    if (m := _APP.match(s)) and not _HOUSE.search(m.group(1)):
        return {"action": "open_app", "app": re.sub(r"^(il |lo |la |l')", "", m.group(1), flags=_I)}
    if m := _NAV.match(s):
        return {"action": "navigate", "destination": m.group(1)}
    for rx in _SEARCH:
        if m := rx.match(s):
            return {"action": "web_search", "query": m.group(1)}
    if m := _CALL.match(s):
        who = re.sub(r"^(il|lo|la|al|allo|alla) ", "", m.group(1).strip(), flags=_I)
        return {"action": "call", "number": who.replace(" ", "")} if re.fullmatch(r"[+\d][\d ]{5,}", who) \
            else {"action": "call", "contact": who}
    if m := _MSG.match(s):
        return {"action": "message", "contact": m.group(1), "text": m.group(2),
                "via": "whatsapp" if "whatsapp" in s.lower() else "sms"}
    return None


# 🧠 What the patterns above miss, read by the local reasoner in one short answer (owner, 2 Nov: «ho chiesto di mandare
# un messaggio whatsapp … e non ha aperto l'app»: the sentence went to the agent, 23 s, and no action). Measured on the
# reference machine with invented sentences: 0.13–0.57 s, NONE for talk and questions in 0.13–0.15 s (M273). Aurora's
# own calendar, reminders and the house are hers, not the phone's: NONE, and the whole path answers.
UNDERSTAND = """You turn what a person says to the assistant on their phone into ONE command for the phone, or NONE.
Reply with one JSON object on one line, nothing else, or the word NONE.
Commands:
{"action":"open_app","app":NAME}
{"action":"web_search","query":WORDS}
{"action":"open_url","url":"https://..."}
{"action":"alarm","hour":H,"minute":M}
{"action":"timer","seconds":S}
{"action":"navigate","destination":PLACE}
{"action":"call","contact":NAME} or {"action":"call","number":DIGITS}
{"action":"message","contact":NAME,"text":WHAT_IT_SAYS,"via":"whatsapp" or "sms"}
The text of a message is written as the person would send it, in first person, without "che" or "dicendo".
NONE for: questions, conversation, opinions, anything to look up or think about, the house (lights, gates, doors, \
heating, alarm, cameras), the calendar, reminders, notes, projects, mail."""


def understand(model, text: str) -> dict | None:
    """A command for the phone read by the model from a sentence the patterns missed, checked (prepare), or None."""
    try:
        out = model.complete(UNDERSTAND, text.strip()[:500], 90).answer.strip()
    except Exception:                                    # noqa: BLE001 - the reasoner off or failing: Aurora answers
        return None
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        return None
    try:
        args = json.loads(m.group(0))
    except ValueError:
        return None
    if not isinstance(args, dict) or args.get("action") in (None, "calendar"):
        return None
    act = prepare(args)
    return act if isinstance(act, dict) else None

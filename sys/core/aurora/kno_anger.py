# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""😠 Anger, measured like her other emotions (kno_mood; owner, 17 Oct: «ma si può anche arrabbiare?… se per esempio
viene trattata male… che dice che non mi parla perché si deve calmare… cmq sempre uno stato basato su misurazioni»).

The measure: the person's messages that insult her, counted by words (INSULT: Italian and English, an insult said to
her — «sei un'idiota», «stai zitta», «vaffanculo» — not a word that only sounds rude: «un errore stupido» is not one).
Each offence weighs 1 when said and nothing after FADE_S (linear); the value is _sat(sum, 1): one offence 0.5, two
close together ~0.67. An apology (APOLOGY) ends it at once. Per person: she is not angry with someone else.

Its effects, each said in her words:
- an offence: the answer begins by saying it hurt her — she answers anyway;
- at COOL_AT or more (two offences in a few minutes): for COOL_S after the last she asks for a moment instead of
  answering — never for what is urgent (URGENT: alarms, the house, security, health), and never longer than COOL_S;
- an apology: «scuse accettate», and the answer as usual.
No model is asked: the words are counted here, so the same message always gives the same anger (tested).

The behaviour card (owner, 29 Oct: a card per user on the admin's Users page): each day's offences, apologies that
ended an anger and cool-downs, numbers only — never the words — kept CONDUCT_DAYS; offences counted with the mood off
too (core_route.mood_wrap still keeps them local)."""
from __future__ import annotations

import contextvars
import json
import re
import threading
import time
from pathlib import Path

from . import sys_config, sys_seal

FADE_S = 30 * 60                  # an offence weighs nothing after half an hour
COOL_AT = 0.6                     # two offences close together
COOL_S = 3 * 60                   # the longest she asks for a moment
KEEP_S = 2 * FADE_S
CONDUCT_DAYS = 365
_lock = threading.Lock()
# the line she says before this run's answer: kept with the answer in her memory too (kno_answer.remember), not only
# shown live — the conversation read again says it as it was said
SAID_FIRST: contextvars.ContextVar[str] = contextvars.ContextVar("anger_said_first", default="")

_ADJ = (r"idiot[ae]|stupid[ao]|scem[ao]|cretin[ao]|deficiente|imbecille|inutile|incapace|ritardat[ao]|stronz[ao]|"
        r"cogliona|coglione|demente|ottus[ao]|patetic[ao]|una nullità|un disastro|una merda|un rottame|un catorcio")
INSULT = re.compile(
    r"(?i)\bsei\s+(?:(?:proprio|davvero|veramente|solo|soltanto|una?|un'|l'|la|il)\s*)*(?:" + _ADJ + r")\b"
    r"|\b(?:vaffanculo|fanculo|affanculo|va a cagare|vai a cagare|fottiti|stai zitta|stai zitto|chiudi il becco|"
    r"fai schifo|fai cagare|fai pena|non capisci un cazzo|non servi a niente|non servi a nulla|ti odio|"
    r"stronza|cogliona|puttana|troia|testa di cazzo|pezzo di merda|brutta stupida|brutta idiota)\b"
    r"|\b(?:you(?:'re| are)\s+(?:(?:so|such|an?|really|just|completely)\s+)*(?:idiot|stupid|dumb|useless|moron|"
    r"pathetic|worthless|trash)|fuck you|fuck off|shut up|you suck|i hate you|piece of shit|stupid bitch)\b")
APOLOGY = re.compile(r"(?i)\b(?:scusa(?:mi)?|scusami tanto|chiedo scusa|perdonami|mi dispiace|ti chiedo scusa|"
                     r"non volevo|sorry|i apologi[sz]e|forgive me|i'm sorry)\b")
URGENT = re.compile(r"(?i)\b(?:urgente|urgenza|emergenza|allarme|aiuto|sicurezza|incendio|fumo|fuga di gas|ladr\w*|"
                    r"intrus\w*|ospedale|pronto soccorso|sto male|ambulanza|urgent|emergency|alarm|help|fire|intruder)\b")


def _file(cfg: sys_config.Config) -> Path:
    from . import sys_users_layout
    d = sys_users_layout.place(cfg, "state", cfg.user)
    d.mkdir(parents=True, exist_ok=True)
    return d / "anger.json"


def _events(cfg: sys_config.Config) -> list[dict]:
    try:
        return json.loads(sys_seal.read_any(cfg, _file(cfg), cfg.user))
    except (OSError, ValueError):
        return []


def _save(cfg: sys_config.Config, rows: list[dict]) -> None:
    """Sealed with the user's key (N64: the events keep the words heard); a file of before is sealed here."""
    sys_seal.write(cfg, _file(cfg), json.dumps(rows, ensure_ascii=False).encode("utf-8"), cfg.user, "state")


def _card_file(cfg: sys_config.Config) -> Path:
    return _file(cfg).with_name("conduct.json")


def _tally(cfg: sys_config.Config, kind: str, now: float) -> None:
    """One more of kind ("offence", "apology", "cool") on today's line of the card (called under _lock)."""
    try:
        days = json.loads(sys_seal.read_any(cfg, _card_file(cfg), cfg.user))
    except (OSError, ValueError):
        days = {}
    today = time.strftime("%Y-%m-%d", time.localtime(now))
    line = days.setdefault(today, {})
    line[kind] = line.get(kind, 0) + 1
    oldest = time.strftime("%Y-%m-%d", time.localtime(now - CONDUCT_DAYS * 86400))
    days = {d: v for d, v in days.items() if d >= oldest}
    sys_seal.write(cfg, _card_file(cfg), json.dumps(days).encode("utf-8"), cfg.user, "state")


def card(cfg: sys_config.Config, days: int = 30, now: float | None = None) -> dict:
    """{"offence", "apology", "cool": totals of the last `days`, "days": [{"day", "offence", "apology", "cool"}] newest
    first, "last": the last day with an offence or None} — the admin's Users page."""
    now = now or time.time()
    try:
        rows = json.loads(sys_seal.read_any(cfg, _card_file(cfg), cfg.user))
    except (OSError, ValueError):
        rows = {}
    since = time.strftime("%Y-%m-%d", time.localtime(now - (days - 1) * 86400))
    kinds = ("offence", "apology", "cool")
    shown = [{"day": d, **{k: int(rows[d].get(k, 0)) for k in kinds}} for d in sorted(rows, reverse=True) if d >= since]
    return {**{k: sum(r[k] for r in shown) for k in kinds}, "days": shown,
            "last": max((d for d, v in rows.items() if v.get("offence")), default=None)}


def heard(text: str) -> str:
    """What a message is to her anger: "offence", "apology" or "" (pure: the words only)."""
    if INSULT.search(text or ""):
        return "offence"
    return "apology" if APOLOGY.search(text or "") else ""


def value(rows: list[dict], now: float) -> tuple[float, list[dict]]:
    """(anger 0–1, the offences that still weigh): the offences after the last apology, each fading in FADE_S."""
    last_sorry = max((r["at"] for r in rows if r["kind"] == "apology"), default=0)
    live = [r for r in rows if r["kind"] == "offence" and r["at"] > last_sorry and now - r["at"] < FADE_S]
    weight = sum(1 - (now - r["at"]) / FADE_S for r in live)
    return (0.0 if weight <= 0 else round(weight / (weight + 1), 2)), live


def level(cfg: sys_config.Config, now: float | None = None) -> dict:
    """{"value", "causes"} for kno_mood: measured now, with what she was told and when."""
    now = now or time.time()
    v, live = value(_events(cfg), now)
    if not live:
        return {"value": 0.0, "causes": ["nessuna offesa nell'ultima mezz'ora"]}
    words = [f"«{r['words']}» {max(1, round((now - r['at']) / 60))} min fa" for r in live[-2:]]
    many = "offesa" if len(live) == 1 else "offese"
    return {"value": v, "causes": [f"{len(live)} {many} nell'ultima mezz'ora: " + ", ".join(words)]}


def react(cfg: sys_config.Config, text: str, now: float | None = None) -> dict:
    """A message arrives: it is counted, and she says how she takes it.
    → {"kind", "value", "cool": the answer instead of one, or "", "prefix": a line before the answer, or ""}."""
    now = now or time.time()
    if not cfg["AURORA_MOOD"]:
        if heard(text) == "offence":
            with _lock:
                _tally(cfg, "offence", now)
        return {"kind": "", "value": 0.0, "cool": "", "prefix": ""}
    it = str(cfg["AURORA_LANG_DEFAULT"]).startswith("it")
    kind = heard(text)
    with _lock:
        rows = [r for r in _events(cfg) if now - r["at"] < KEEP_S]
        before, _ = value(rows, now)
        if kind == "offence":
            m = INSULT.search(text)
            rows.append({"at": now, "kind": "offence", "words": m.group(0)[:60]})
        elif kind == "apology" and before > 0:
            rows.append({"at": now, "kind": "apology"})
        if kind and (kind == "offence" or before > 0):
            _save(cfg, rows)
            _tally(cfg, kind, now)
        v, live = value(rows, now)
        if v >= COOL_AT and live and now - live[-1]["at"] < COOL_S and kind == "offence" and not URGENT.search(text or ""):
            _tally(cfg, "cool", now)                     # a cool-down begun (by this offence): counted once
    out = {"kind": kind, "value": v, "cool": "", "prefix": ""}
    if kind == "apology" and before > 0:
        out["prefix"] = "🙂 Scuse accettate: è passata." if it else "🙂 Apology accepted: it's gone."
        return out
    cooling = v >= COOL_AT and live and now - live[-1]["at"] < COOL_S
    if cooling and not URGENT.search(text or ""):
        left = max(1, round((COOL_S - (now - live[-1]["at"])) / 60))
        out["cool"] = (f"😠 Mi hai trattata male più volte in pochi minuti (rabbia {v:.2f}): ho bisogno di calmarmi. "
                       f"Riscrivimi fra {left} min, oppure scusati. Se è urgente — casa, allarme, sicurezza, salute — "
                       f"scrivilo e rispondo subito." if it else
                       f"😠 You have been rude to me several times in a few minutes (anger {v:.2f}): I need to calm down. "
                       f"Write again in {left} min, or apologise. If it is urgent — the house, an alarm, security, health — "
                       f"say so and I answer at once.")
    elif kind == "offence":
        out["prefix"] = (f"😠 Questo non mi è piaciuto (rabbia {v:.2f}): ti rispondo lo stesso, ma trattami bene." if it else
                         f"😠 I did not like that (anger {v:.2f}): I answer anyway, but treat me well.")
    return out

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The dietitian's plan, followed day by day (owner, 2026-10-07: «elabora documenti caricati… quando bisogna mangiare
indica il piatto consigliato, le alternative… tiene traccia dei gusti… non si cade nella monotonia»).

`process` reads the user's diet documents (hlt_store) and keeps a plan, sealed with their key:
- the week, read from the text itself: day headings (LUNEDÌ…) and meal headings (Colazione, Pranzo…), each meal of
  each day an option with its foods; a plan with meals and no days gives a pool of options per meal;
- the weekly frequencies (FREQUENZE: «Pesce: 3-4 volte a settimana»), read from the text too;
- the limits and the practical rules (water, a drink at most once a week…), summarised by the LOCAL model only —
  never a cloud model: this is health data. Without the model the plan works, without them.
Each option is tagged with the food groups the frequencies speak of (fish, white/red meat, eggs, cheese, cold cuts,
legumes), found by keyword: the frequencies count the main meals' protein, the eggs count wherever they are.

`suggest` proposes a meal: the day's option of the plan first, then the others, re-weighed by what the week already
had (a group under its minimum comes forward, one at its maximum steps back), by what was eaten in the last days and
by what is chosen too often (variety: monotony is what makes a diet be abandoned). Every reason is said.
"""
from __future__ import annotations

import json
import re
import secrets
import time
from datetime import date, datetime, timedelta

from . import hlt_store, sys_config, sys_seal

DAYS = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
MEALS = ("colazione", "spuntino", "pranzo", "merenda", "cena")
MAIN = ("pranzo", "cena")                            # where a frequency's protein is counted

# food groups of the usual Italian frequencies; the first that matches a line wins (white meat before "hamburger")
GROUPS = {
    "pesce": r"\b(pesce|tonno|salmone|gamber\w*|merluzzo|orata|branzino|spigola|sgombro|sardin\w*|alic[ie]|acciugh\w*|"
             r"calamar\w*|polpo|seppi\w*|cozze|vongole|nasello|platessa|trota|baccal\w*|sogliola|surimi|pesce spada|"
             r"crostace\w*|molluschi)\b",
    "carne_bianca": r"\b(pollo|tacchino|coniglio|carne bianca)\b",
    "carne_rossa": r"\b(manzo|vitell\w*|maiale|hamburger|bistecca|agnello|carne rossa|lonza|filetto|tagliata|"
                   r"macinato|cavallo)\b",
    "affettati": r"\b(prosciutto|bresaola|speck|salame|affettat\w*|mortadella|fesa|salum\w*|insaccat\w*)\b",
    "legumi": r"\b(legum\w*|lenticchie|ceci|fagiol\w*|piselli|fave|edamame|lupini|hummus|tofu)\b",
    "formaggi": r"\b(ricotta|mozzarell\w*|parmigiano|grana|formagg\w*|stracchino|quartirolo|fiocchi di latte|feta|"
                r"scamorza|caciotta|primo sale|robiola|emmental|pecorino|provola|fontina|asiago)\b",
}
NAMES = {"pesce": "pesce", "carne_bianca": "carne bianca", "carne_rossa": "carne rossa", "affettati": "affettati",
         "legumi": "legumi", "formaggi": "formaggi", "uova": "uova"}
_EGGS = re.compile(r"\b(\d+|un|uno|due|tre)?\s*(uov[ao])\b(?!\s*sod)", re.I)
_WORDS = {"un": 1, "uno": 1, "due": 2, "tre": 3}


def _norm(s: str) -> str:
    return " ".join(str(s).replace(" ", " ").split())


def _key(s: str) -> str:
    """A heading compared without case, accents written as apostrophes, or a trailing colon."""
    s = _norm(s).lower().rstrip(":").strip()
    return s.replace("i'", "ì").replace("lunedi", "lunedì").replace("martedi", "martedì").replace(
        "mercoledi", "mercoledì").replace("giovedi", "giovedì").replace("venerdi", "venerdì")


def _day(line: str) -> str | None:
    k = _key(line)
    return next((d for d in DAYS if k == d or k.startswith(d + " ") and len(k) < 30), None)


def _meal(line: str) -> str | None:
    k = _key(line)
    m = next((x for x in MEALS if k == x or k.startswith(x + " ") or k.startswith(x + "(")), None)
    if m and len(k) <= 40 and (k == m or k[len(m):].lstrip().startswith(("(", "oppure", "o ", "a scelta", "1", "2", "3"))):
        return m
    return None


def _caps(line: str) -> bool:
    """A section title in capitals (INDICAZIONI PRATICHE, FREQUENZE:): the week's last meal ends there."""
    letters = [c for c in line if c.isalpha()]
    return len(letters) >= 4 and all(c.isupper() for c in letters)


def _grams(line: str) -> float | None:
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:[–-]\s*\d+\s*)?g\b", line)
    return float(m.group(1).replace(",", ".")) if m else None


def groups_of(lines: list[str], meal: str) -> dict[str, int]:
    """The frequencies' groups in a meal: the protein at lunch and dinner, the eggs at every meal (they are counted
    one by one: «Uova: 4-5 uova a settimana»). A cheese of 15 g or less is a condiment, not the meal's cheese."""
    found: dict[str, int] = {}
    for line in lines:
        low = line.lower()
        for m in _EGGS.finditer(low):
            n = m.group(1)
            found["uova"] = found.get("uova", 0) + (int(n) if n and n.isdigit() else _WORDS.get(n or "", 1))
        if meal not in MAIN:
            continue
        for g, rx in GROUPS.items():
            if re.search(rx, low):
                if g == "formaggi" and re.search(r"parmigiano|grana", low) and (_grams(low) or 99) <= 15:
                    break
                if g == "carne_rossa" and re.search(GROUPS["carne_bianca"], low):
                    break
                found[g] = 1
                break
    return found


def parse_week(text: str) -> list[dict]:
    """The plan's options: one per meal of each day; with no day headings, one per alternative of each meal."""
    options, day, meal, lines, done = [], None, None, [], False

    def close():
        nonlocal lines
        items = [x for x in lines if x and len(x) <= 90 and not x.endswith(".")]
        note = " ".join(x for x in lines if x and (len(x) > 90 or x.endswith(".")))
        if meal and items:
            parts, cur = [], []                       # «yogurt oppure mela»: alternatives inside the meal
            for x in items:
                if _key(x) == "oppure":
                    parts.append(cur)
                    cur = []
                else:
                    cur.append(x)
            parts.append(cur)
            base = f"{day or 'x'}-{meal}"
            for i, p in enumerate([p for p in parts if p] if day is None else [items]):
                options.append({"id": base if day else f"{base}-{len(options)}", "day": day, "meal": meal,
                                "items": p if day is None else [x for x in p if _key(x) != "oppure"],
                                "note": note[:300], "groups": groups_of(p, meal)})
        lines = []

    for raw in str(text).splitlines():
        line = _norm(raw)
        if not line or done:
            continue
        d = _day(line)
        if d:
            close()
            day, meal = d, None
            continue
        m = _meal(line)
        if m:
            close()
            meal = m
            continue
        if _caps(line) and line.lower() != line:      # a new section: the week is over (its recipes are not meals)
            close()
            meal = None
            if day is not None or options:
                done = True
            continue
        if meal:
            lines.append(line)
    close()
    return options


_FREQ_LINE = re.compile(r"^\s*([A-Za-zÀ-ÿ /]+?)\s*:\s*(.+)$")


def parse_frequencies(text: str) -> dict[str, dict]:
    """«FREQUENZE:» and its lines, read as {group: {min, max}} per week; «Carne: 1 volta rossa 3 volte bianca» gives
    both meats. What it cannot read it leaves out (the model's summary may still tell it)."""
    out: dict[str, dict] = {}
    lines = str(text).splitlines()
    start = next((i for i, l in enumerate(lines) if re.match(r"\s*FREQUENZ[EA]", l, re.I)), None)
    if start is None:
        return out
    for raw in lines[start + 1:start + 20]:
        line = _norm(raw)
        if not line:
            continue
        if _caps(line):
            break
        m = _FREQ_LINE.match(line)
        if not m:
            continue
        what, rest = m.group(1).lower(), m.group(2).lower()
        if "carne" in what and re.search(r"ross|bianc", rest):
            for n, kind in re.findall(r"(\d+)\s*(?:volt[ae])?\s*(rossa|bianca)", rest):
                g = "carne_rossa" if kind == "rossa" else "carne_bianca"
                out[g] = {"min": int(n), "max": int(n)}
            continue
        g = next((k for k, v in NAMES.items() if v in what), None) or next(
            (k for k, v in NAMES.items() if v.split()[0] in what), None)
        g = g or ("affettati" if "salum" in what else None)
        nums = [int(x) for x in re.findall(r"\d+", rest)[:2]]
        if g and nums:
            out[g] = {"min": nums[0], "max": nums[-1]}
    return out


SYS_RULES = ("You read an Italian dietitian's plan. Return JSON only: "
             '{"free_meals_per_week": number or null, "limits": [{"what": "food or drink", "max": number, "per": "week" or "day"}], '
             '"rules": ["at most 8 short practical rules, in Italian, as written (water, vegetables first, cooking…)"]}. '
             "Only what the text says; no medical advice of your own.")


def _summary(llm, text: str) -> dict:
    """Limits and rules by the LOCAL model; {} when it fails (the plan works without them)."""
    cut = re.split(r"\n\s*RICETTE\b", text, maxsplit=1)[0][:12000]
    try:
        ans = llm.complete(SYS_RULES, cut, 900).answer
        m = re.search(r"\{.*\}", ans or "", re.S)
        raw = json.loads(m.group(0)) if m else {}
    except Exception:  # noqa: BLE001 — a summary missing, never a plan missing
        return {}
    out: dict = {}
    fm = raw.get("free_meals_per_week")
    if isinstance(fm, (int, float)) and 0 <= fm <= 7:
        out["free_meals_per_week"] = int(fm)
    out["limits"] = [{"what": _norm(x.get("what", ""))[:60], "max": x["max"], "per": x.get("per", "week")}
                     for x in raw.get("limits") or [] if isinstance(x, dict) and isinstance(x.get("max"), (int, float))
                     and _norm(x.get("what", ""))][:8]
    out["rules"] = [_norm(r)[:200] for r in raw.get("rules") or [] if isinstance(r, str) and _norm(r)][:8]
    return out


# ---- the sealed files ---------------------------------------------------------------------------------------------
def _file(cfg: sys_config.Config, name: str):
    return hlt_store._dir(cfg, "diet") / f"{name}.sealed"


def _read(cfg: sys_config.Config, name: str, default):
    f = _file(cfg, name)
    return json.loads(sys_seal.read(cfg, f, cfg.user)) if f.exists() else default


def _write(cfg: sys_config.Config, name: str, data) -> None:
    sys_seal.write(cfg, _file(cfg, name), json.dumps(data, ensure_ascii=False).encode(), cfg.user)


def plan(cfg: sys_config.Config) -> dict | None:
    return _read(cfg, "plan", None)


def reread(cfg: sys_config.Config) -> int:
    """Documents kept before their format was readable (C178: .docx) read again from their sealed original."""
    from .kno_ingest import read_text
    n = 0
    for it in hlt_store.items(cfg, "diet"):
        if it["kind"] != "document" or not hlt_store.text(cfg, "diet", it["id"]).startswith("(testo non leggibile"):
            continue
        name, data = hlt_store.original(cfg, "diet", it["id"])
        try:
            text, _ = read_text(name, data, cfg)
        except Exception:  # noqa: BLE001 — still unreadable (an image): left as it was
            continue
        sys_seal.write(cfg, hlt_store._dir(cfg, "diet") / f"{it['id']}.txt.sealed", text.encode(), cfg.user)
        n += 1
    return n


def _free_meals(text: str) -> int | None:
    """«È concesso 1 pasto libero»: how many free meals a week the plan grants; None when it does not say."""
    m = re.search(r"\b(\d|un|uno|due)\s+past[oi]\s+liber[oi]", str(text), re.I)
    return (int(m.group(1)) if m.group(1).isdigit() else _WORDS[m.group(1).lower()]) if m else None


def process(cfg: sys_config.Config, llm=None) -> dict:
    """«Elabora documenti»: the plan read from the diet documents (the one with most meals is the week), kept sealed."""
    fixed = reread(cfg)
    docs = [(it, hlt_store.text(cfg, "diet", it["id"])) for it in hlt_store.items(cfg, "diet")]
    best, week = None, []
    for it, text in docs:
        opts = parse_week(text)
        if len(opts) > len(week):
            best, week = (it, text), opts
    if not week:
        raise ValueError("nessun piano riconosciuto: servono i giorni (LUNEDÌ…) o i pasti (Colazione, Pranzo…)")
    freq = {}
    for _, text in ([best] + [d for d in docs if d is not best]):
        freq = freq or parse_frequencies(text)
    p = {"options": week, "frequencies": freq, "source": best[0]["title"], "source_id": best[0]["id"],
         "documents": [it["id"] for it, _ in docs], "processed_at": time.time(), "by_day": any(o["day"] for o in week),
         "reread": fixed, "free_meals_per_week": _free_meals(best[1]), "limits": [], "rules": []}
    if llm is not None:
        p.update(_summary(llm, best[1]))
        said = {NAMES[g] for g in freq}                # a limit that is a frequency already read is said once
        p["limits"] = [x for x in p["limits"] if x["what"].lower() not in said]
    _write(cfg, "plan", p)
    return p


# ---- what was eaten -----------------------------------------------------------------------------------------------
def choices(cfg: sys_config.Config) -> list[dict]:
    return _read(cfg, "choices", [])


def choose(cfg: sys_config.Config, day: str, meal: str, option: str | None = None, text: str = "",
           free: bool = False) -> dict:
    """A meal eaten: an option of the plan, a free meal, or something else said in words. One per meal and day: a
    second choice replaces the first."""
    date.fromisoformat(day)
    if meal not in MEALS:
        raise ValueError(f"meal: one of {MEALS}")
    p = plan(cfg) or {"options": []}
    opt = next((o for o in p["options"] if o["id"] == option), None) if option else None
    if option and opt is None:
        raise ValueError("no such option in the plan")
    if not opt and not free and not _norm(text):
        raise ValueError("an option, a free meal or a few words")
    row = {"id": secrets.token_hex(4), "day": day, "meal": meal, "option": option, "free": bool(free),
           "text": _norm(text)[:200], "groups": opt["groups"] if opt else groups_of([text], meal) if text else {},
           "at": time.time()}
    rows = [r for r in choices(cfg) if not (r["day"] == day and r["meal"] == meal)] + [row]
    _write(cfg, "choices", rows[-2000:])
    return row


def unchoose(cfg: sys_config.Config, cid: str) -> bool:
    rows = choices(cfg)
    keep = [r for r in rows if r["id"] != cid]
    _write(cfg, "choices", keep)
    return len(keep) != len(rows)


# ---- the suggestion -----------------------------------------------------------------------------------------------
def _label(o: dict) -> str:
    return ", ".join(o["items"][:3]) + ("…" if len(o["items"]) > 3 else "")


def week_counts(rows: list[dict], day: date, skip: tuple[str, str] | None = None) -> dict[str, int]:
    """The groups eaten in the week (Monday to Sunday) of `day`, without the meal being chosen now."""
    monday = day - timedelta(days=day.weekday())
    out: dict[str, int] = {}
    for r in rows:
        d = date.fromisoformat(r["day"])
        if monday <= d <= monday + timedelta(days=6) and (r["day"], r["meal"]) != skip:
            for g, n in (r.get("groups") or {}).items():
                out[g] = out.get(g, 0) + n
            if r.get("free"):
                out["libero"] = out.get("libero", 0) + 1
    return out


def suggest(p: dict, rows: list[dict], day: date, meal: str) -> dict:
    """The meal proposed for `day` and the alternatives, each with its reasons; hints for the week and for variety."""
    pool = [o for o in p["options"] if o["meal"] == meal]
    out = {"day": day.isoformat(), "meal": meal, "suggested": None, "alternatives": [], "hints": [], "chosen": None}
    out["chosen"] = next((r for r in rows if r["day"] == out["day"] and r["meal"] == meal), None)
    if not pool:
        return out
    freq = p.get("frequencies") or {}
    counts = week_counts(rows, day, (out["day"], meal))
    left = sum(1 for i in range(day.weekday(), 7) for m in MAIN
               if not (i == day.weekday() and MAIN.index(m) < (MAIN.index(meal) if meal in MAIN else 0)))
    month = [r for r in rows if r["meal"] == meal and r.get("option")
             and date.fromisoformat(r["day"]) >= day - timedelta(days=28)]
    picks: dict[str, int] = {}
    for r in month:
        picks[r["option"]] = picks.get(r["option"], 0) + 1
    weekday = DAYS[day.weekday()]
    scored = []
    for o in pool:
        score, why = 0.0, []
        if o["day"] == weekday:
            score += 1.0
            why.append("previsto dal piano per oggi")
        for g, n in o["groups"].items():
            f, c = freq.get(g), counts.get(g, 0)
            if not f:
                continue
            if c + n > f["max"]:
                score -= 3.0
                why.append(f"{NAMES[g]}: già {c} su massimo {f['max']} questa settimana")
            elif c < f["min"]:
                score += 2.0 * min(1.0, (f["min"] - c) / max(1, left))
                why.append(f"{NAMES[g]}: {c} su {f['min']}–{f['max']} questa settimana")
        last = max((date.fromisoformat(r["day"]) for r in month if r["option"] == o["id"]), default=None)
        if last and (day - last).days <= 2:
            score -= 1.5
            why.append("scelto " + ("ieri" if (day - last).days == 1 else "oggi" if last == day else "due giorni fa"))
        if picks.get(o["id"], 0) >= 4:
            score -= 0.5 * (picks[o["id"]] - 3)
            why.append(f"scelto {picks[o['id']]} volte in 4 settimane")
        scored.append((score, o, why))
    scored.sort(key=lambda x: -x[0])
    pack = lambda s, o, why: {"id": o["id"], "day": o["day"], "items": o["items"], "note": o.get("note", ""),
                              "label": _label(o), "groups": o["groups"], "score": round(s, 2), "why": why}
    out["suggested"] = pack(*scored[0])
    out["alternatives"] = [pack(*x) for x in scored[1:4]]
    top = max(picks.items(), key=lambda kv: kv[1], default=None)        # the dish chosen too often, said kindly
    if top and top[1] >= 4 and top[1] >= 0.4 * len(month):
        often = next((o for o in pool if o["id"] == top[0]), None)
        fresh = min(pool, key=lambda o: (picks.get(o["id"], 0), o["id"] == top[0]))
        if often and fresh["id"] != often["id"]:
            out["hints"].append(f"Scegli spesso «{_label(often)}» ({top[1]} volte in 4 settimane): prova «{_label(fresh)}».")
    for g, f in freq.items():                          # a group the week still needs and no option of this meal has
        need = f["min"] - counts.get(g, 0)
        # in no meal of the plan; «once a week» (cold cuts) is a ceiling, not a goal: never urged
        if meal in MAIN and need > 0 and f["min"] >= 2 and not any(g in o["groups"] for o in p["options"]):
            many = f"Mancano {need} pasti" if need > 1 else "Manca 1 pasto"
            out["hints"].append(f"{many} con {NAMES.get(g, g)} questa settimana: il piano permette di "
                                "sostituire la proteina rispettando le dosi (chiedi conferma al dietologo sulle porzioni).")
    out["hints"] = out["hints"][:2]
    free = int(p.get("free_meals_per_week") or 0)
    if free and meal in MAIN:
        used = counts.get("libero", 0)
        out["free_left"] = max(0, free - used)
    return out


def meal_now(times: dict[str, str], now: datetime, window_min: int = 10) -> str | None:
    """The meal whose time is now (within `window_min` minutes after it), from {meal: "HH:MM"}."""
    for meal, hm in times.items():
        try:
            h, m = (int(x) for x in hm.split(":"))
        except ValueError:
            continue
        start = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if start <= now < start + timedelta(minutes=window_min):
            return meal
    return None


def parse_times(spec: str) -> dict[str, str]:
    """«colazione=07:30,pranzo=12:30»: the reminders' times, only valid meals and times."""
    out = {}
    for part in str(spec or "").split(","):
        k, _, v = part.partition("=")
        k, v = k.strip().lower(), v.strip()
        if k in MEALS and re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", v):
            out[k] = v
    return out


def reminder_text(s: dict) -> str:
    """The reminder's words: the meal, the dish proposed, one alternative, the first hint."""
    if not s["suggested"]:
        return ""
    lines = [f"🍽️ {s['meal'].capitalize()}: {s['suggested']['label']}"]
    if s["suggested"]["why"]:
        lines.append(f"({s['suggested']['why'][0]})")
    if s["alternatives"]:
        lines.append(f"In alternativa: {s['alternatives'][0]['label']}")
    if s["hints"]:
        lines.append(s["hints"][0])
    return "\n".join(lines)


# ---- what the chat's model reads (the health plugin): the processed plan, not the raw documents --------------------
_REL = {"oggi": 0, "today": 0, "domani": 1, "tomorrow": 1, "dopodomani": 2, "ieri": -1, "yesterday": -1}


def when(text: str, today: date) -> date:
    """«oggi», «domani», «ieri», a weekday («giovedì»: the next one, today included) or YYYY-MM-DD: the date is the
    code's, never the model's guess (7 Oct: the model counted from the visit's date and said Tuesday on a Wednesday)."""
    k = _key(text or "oggi")
    if k in _REL:
        return today + timedelta(days=_REL[k])
    d = _day(k)
    if d:
        return today + timedelta(days=(DAYS.index(d) - today.weekday()) % 7)
    return date.fromisoformat(k)


def _date_it(d: date) -> str:
    months = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre",
              "novembre", "dicembre")
    return f"{DAYS[d.weekday()]} {d.day} {months[d.month - 1]} {d.year}"


def meal_text(p: dict, rows: list[dict], day: date, meals: list[str], today: date) -> str:
    """The meals of a day for the chat: proposed, why, alternatives, what was chosen, the week against the frequencies."""
    out = [f"Oggi è {_date_it(today)}." + ("" if day == today else f" Il giorno chiesto è {_date_it(day)}."),
           f"Piano elaborato da «{p.get('source', '')}»: le proposte tengono conto di quanto mangiato questa settimana."]
    for meal in meals:
        s = suggest(p, rows, day, meal)
        if s["chosen"]:
            c = s["chosen"]
            out.append(f"\n{meal.upper()}: già scelto — " + ("pasto libero" if c["free"] else
                       next((o["label"] for o in [s["suggested"], *s["alternatives"]] if o and o["id"] == c["option"]),
                            c["text"] or c["option"] or "")))
            continue
        if not s["suggested"]:
            out.append(f"\n{meal.upper()}: il piano non ha proposte per questo pasto.")
            continue
        o = s["suggested"]
        out.append(f"\n{meal.upper()} — PROPOSTO: " + "; ".join(o["items"]) + (f" (nota: {o['note']})" if o["note"] else "")
                   + (f"\n  perché: {', '.join(o['why'])}" if o["why"] else ""))
        for i, a in enumerate(s["alternatives"], 1):
            out.append(f"  alternativa {i}: " + "; ".join(a["items"]) + (f" ({', '.join(a['why'])})" if a["why"] else ""))
        out += [f"  consiglio: {h}" for h in s["hints"]]
        if s.get("free_left"):
            out.append(f"  pasti liberi rimasti questa settimana: {s['free_left']}")
    freq = p.get("frequencies") or {}
    if freq:
        wk = week_counts(rows, day)
        out.append("\nSettimana (mangiato / frequenza del piano): " + ", ".join(
            f"{NAMES[g]} {wk.get(g, 0)}/{f['min']}" + (f"–{f['max']}" if f["max"] != f["min"] else "") for g, f in freq.items()))
    out.append("\nL'utente può segnare cosa sceglie toccando la scheda del pasto sotto la risposta.")
    return "\n".join(out)


def plan_text(p: dict) -> str:
    """The whole processed plan, compact: the week, the frequencies, the limits and the rules (~3k characters)."""
    out = [f"Piano elaborato da «{p.get('source', '')}» (per i pasti di un giorno usa health_diet)."]
    for o in p["options"]:
        out.append(f"{(o['day'] or '').upper()} {o['meal']}: " + "; ".join(o["items"]))
    if p.get("frequencies"):
        out.append("FREQUENZE a settimana: " + ", ".join(
            f"{NAMES[g]} {f['min']}" + (f"–{f['max']}" if f["max"] != f["min"] else "") for g, f in p["frequencies"].items()))
    if p.get("free_meals_per_week"):
        out.append(f"Pasti liberi a settimana: {p['free_meals_per_week']}")
    out += [f"Limite: {x['what']} al massimo {x['max']} a {'settimana' if x['per'] == 'week' else 'giorno'}" for x in p.get("limits") or []]
    out += [f"Regola: {r}" for r in p.get("rules") or []]
    return "\n".join(out)

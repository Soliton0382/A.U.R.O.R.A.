# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A dietitian's plan read out of a document's text (moved from hlt_diet, 7 October 2026: one module per part): the
week (day and meal headings, each meal's foods and the food groups the frequencies speak of), the weekly frequencies
(«FREQUENZE:»), and the limits and rules summarised by the LOCAL model. No state: text in, data out."""
from __future__ import annotations

import json
import re

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

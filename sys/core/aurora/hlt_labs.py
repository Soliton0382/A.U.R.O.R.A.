# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Exam values over time (owner, 2026-10-05: "the health menu, especially the medical part").

When an exam's document is added, the LOCAL model reads its values — the test's name, the value, the unit, the
reference range, the day of the sample — and they are kept sealed with the user's key (exams/values.sealed), each
with the document it came from. The page shows each test's values over time, the last one, the direction, and those
outside their range. The owner corrects or deletes a value the model read wrong. Never a diagnosis: a value outside
its range is said plainly, with "talk to your doctor". Nothing here ever goes to a cloud model.
"""
from __future__ import annotations

import json
import re
import secrets
import time
import unicodedata

from . import hlt_store, sys_config, sys_seal

PROMPT = ("You read a medical laboratory report and list its measured values as JSON, nothing else: "
          '[{"test": "the test\'s name as written", "name": "a short standard name in Italian, lower case (e.g. '
          'glucosio, colesterolo totale, emoglobina, ferritina, tsh)", "value": number, "unit": "unit", '
          '"low": number or null, "high": number or null, "date": "YYYY-MM-DD of the sample, or null"}]. '
          "Only numeric results; low and high are the reference range printed on the report (null when absent; "
          "'< 200' means high 200, '> 40' means low 40). A decimal comma becomes a point. [] when there is none.")


def _file(cfg: sys_config.Config):
    return hlt_store._dir(cfg, "exams") / "values.sealed"


def values(cfg: sys_config.Config) -> list[dict]:
    f = _file(cfg)
    return json.loads(sys_seal.read(cfg, f, cfg.user)) if f.exists() else []


def _save(cfg: sys_config.Config, rows: list[dict]) -> None:
    sys_seal.write(cfg, _file(cfg), json.dumps(rows, ensure_ascii=False).encode(), cfg.user)


def key(name: str) -> str:
    """One test, however the reports write it: lower case, no accents, no punctuation."""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _num(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", ".").strip())
    except ValueError:
        return None


def parse(answer: str, fallback_day: str) -> list[dict]:
    """The model's JSON as clean rows; anything without a number is dropped."""
    m = re.search(r"\[.*\]", answer or "", re.S)
    try:
        rows = json.loads(m.group(0)) if m else []
    except ValueError:
        return []
    out = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        v = _num(r.get("value"))
        name = str(r.get("name") or r.get("test") or "").strip()
        if v is None or not name:
            continue
        day = str(r.get("date") or "")
        out.append({"test": str(r.get("test") or name)[:80], "name": name[:60], "key": key(name), "value": v,
                    "unit": str(r.get("unit") or "")[:20], "low": _num(r.get("low")), "high": _num(r.get("high")),
                    "date": day if re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) else fallback_day})
    return out


def extract(cfg: sys_config.Config, doc_id: str, llm) -> list[dict]:
    """Read an exam's values with the LOCAL model and keep them (a document read again replaces its own values)."""
    item = next(i for i in hlt_store.items(cfg, "exams") if i["id"] == doc_id)
    text = hlt_store.text(cfg, "exams", doc_id)
    day = time.strftime("%Y-%m-%d", time.localtime(item["at"]))
    found = []
    for i in range(0, min(len(text), 24000), 8000):     # a long report in pieces the model reads whole
        found += parse(llm.complete(PROMPT, text[i:i + 8000], 2000).answer, day)
    rows = [r for r in values(cfg) if r.get("doc") != doc_id]
    seen = set()
    for r in found:
        k = (r["key"], r["date"], r["value"])
        if k in seen:
            continue
        seen.add(k)
        rows.append({**r, "id": secrets.token_hex(4), "doc": doc_id, "by": "model"})
    _save(cfg, rows)
    return [r for r in rows if r.get("doc") == doc_id]


def correct(cfg: sys_config.Config, vid: str, fields: dict) -> dict:
    """The owner fixes a value the model read wrong (value, unit, range, date, name)."""
    rows = values(cfg)
    r = next((x for x in rows if x["id"] == vid), None)
    if r is None:
        raise KeyError(vid)
    for k in ("value", "low", "high"):
        if k in fields:
            r[k] = _num(fields[k])
    for k in ("unit", "date", "name"):
        if k in fields and fields[k] is not None:
            r[k] = str(fields[k])[:60]
    if r["value"] is None:
        raise ValueError("value: a number")
    r["key"], r["by"] = key(r["name"]), "owner"
    _save(cfg, rows)
    return r


def remove(cfg: sys_config.Config, vid: str = "", doc: str = "") -> int:
    rows = values(cfg)
    keep = [r for r in rows if not ((vid and r["id"] == vid) or (doc and r.get("doc") == doc))]
    _save(cfg, keep)
    return len(rows) - len(keep)


def series(cfg: sys_config.Config) -> list[dict]:
    """Each test with its values in time order, the last one, the direction, and whether it is outside its range."""
    by: dict[str, list] = {}
    for r in values(cfg):
        by.setdefault(r["key"], []).append(r)
    out = []
    for k, rows in by.items():
        rows.sort(key=lambda r: (r["date"], r["id"]))
        last = rows[-1]
        out_of = (last["low"] is not None and last["value"] < last["low"]) or \
                 (last["high"] is not None and last["value"] > last["high"])
        prev = rows[-2]["value"] if len(rows) > 1 else None
        trend = None if prev is None else "up" if last["value"] > prev else "down" if last["value"] < prev else "same"
        out.append({"key": k, "name": last["name"], "unit": last["unit"], "last": last, "trend": trend,
                    "out_of_range": bool(out_of), "points": rows})
    return sorted(out, key=lambda s: (not s["out_of_range"], s["name"]))

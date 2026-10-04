# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""What the firewall really sends, read with its official documentation, and the checks Aurora proposes from it
(owner, 2026-10-04: "the agents adapt to the documentation, the menu proposes what to check and which actions").

observe(): the syslog of the last hours grouped by log_type / log_component / log_subtype and the severity digit of
log_id (Sophos: type 2 digits, component 2, subtype 2, severity 1, message 5), with counts and the field names seen.
learn(): the documentation page at AURORA_SECURITY_SYSLOG_DOC (its text) and those groups go to the reasoner, which
proposes up to 8 checks as rules (sec_rules); each is checked by code and kept switched off until the owner turns
it on. Only categories and field names leave the machine: never an address, a device name or a serial number.
"""
from __future__ import annotations

import gzip
import json
import re
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import httpx

from . import sec_rules, sys_config
from .sec_sentinel import parse, src_of

CATEGORY = ("log_type", "log_component", "log_subtype", "status", "fw_rule_type", "priority", "severity")
SYS_LEARN = (
    "You help defend a home network. Below: the official syslog documentation of its firewall (an extract) and the "
    "groups of lines the firewall really sent in the last hours (counts, field names, category values). Propose up to "
    "8 checks worth watching, each as a JSON object: {\"id\": snake_case, \"title\": short Italian title, \"why\": one "
    "Italian sentence, \"match\": {field: [values]} using ONLY field names and values that appear in the groups (or "
    "log_id prefixes of 6 digits), \"threshold\": lines, \"window_min\": minutes, \"per_source\": true when counted "
    "per source address, \"action\": the defensive action to suggest to the owner, in Italian (never an attack)}. "
    "Choose thresholds from the counts so that normal traffic does not trip them. Reply with a JSON array only.")


def _lines(cfg: sys_config.Config, hours: float):
    d = (cfg.base or cfg).path("AURORA_LOG_DIR") / "firewall"
    since = time.time() - hours * 3600
    files = sorted(d.glob("firewall.*.log.gz")) + [d / "firewall.log"]
    for f in files:
        if not f.is_file() or f.stat().st_mtime < since:
            continue
        with (gzip.open(f, "rt", errors="replace") if f.suffix == ".gz" else open(f, errors="replace")) as h:
            for line in h:
                try:
                    if datetime.fromisoformat(line[:29]).timestamp() < since:
                        continue
                except ValueError:
                    continue
                yield line


def observe(cfg: sys_config.Config, hours: float = 24) -> list[dict]:
    """The groups, most frequent first: {"group": {...categories}, "log_id": first 6 digits, "severity", "count",
    "fields": [names]}."""
    count: Counter = Counter()
    fields: dict = defaultdict(set)
    cats: dict = {}
    for line in _lines(cfg, hours):
        f = parse(line)
        lid = str(f.get("log_id", ""))
        key = (f.get("log_type"), f.get("log_component"), f.get("log_subtype"), lid[:6], lid[6:7])
        count[key] += 1
        fields[key] |= {k for k in f if k != "_raw"}
        cats.setdefault(key, {k: f[k] for k in CATEGORY if f.get(k)})
    return [{"group": cats[k], "log_id": k[3], "severity": k[4], "count": n, "fields": sorted(fields[k])[:40]}
            for k, n in count.most_common(60)]


def doc_text(url: str, limit: int = 12000) -> str:
    """The documentation page as plain text (its headings and tables), cut to `limit` characters."""
    r = httpx.get(url, timeout=60, follow_redirects=True,
                  headers={"User-Agent": "Aurora/1.0 (https://github.com/Soliton0382/A.U.R.O.R.A.; security plugin)"})
    r.raise_for_status()
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", r.text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def proposals(llm, doc: str, groups: list[dict]) -> list[dict]:
    """The reasoner's checks, each one checked by code: a malformed one is dropped, a field never seen is dropped."""
    seen_fields = {k for g in groups for k in g["fields"]} | {"log_id"}
    out = llm.complete(SYS_LEARN, f"DOCUMENTATION (extract):\n{doc}\n\nGROUPS:\n{json.dumps(groups[:40], ensure_ascii=False)}",
                       2500).answer
    m = re.search(r"\[.*\]", out, re.S)
    try:
        items = json.loads(m.group(0)) if m else []
    except ValueError:
        items = []
    good = []
    for it in items[:8] if isinstance(items, list) else []:
        try:
            r = sec_rules.check({**it, "on": False})
        except (ValueError, TypeError, KeyError):
            continue
        if set(r["match"]) <= seen_fields and r["id"] not in {g["id"] for g in good}:
            good.append(r)
    return good


def tried(cfg: sys_config.Config, rules: list[dict], hours: float = 24) -> list[dict]:
    """Each rule played on the real traffic of the last hours: how many incidents and sources it would have raised
    (law 2: a threshold is seen against the real numbers before the owner switches it on)."""
    rs = sec_rules.RuleSet([{**r, "on": True} for r in rules])
    hits: dict[str, list] = {r["id"]: [] for r in rules}
    for line in _lines(cfg, hours):
        f = parse(line)
        for r, who, _n, _s in rs.feed(f, src_of(f), datetime.fromisoformat(line[:29]).timestamp()):
            hits[r["id"]].append(who)
    return [{**r, "tried": {"incidents": len(hits[r["id"]]), "sources": len(set(hits[r["id"]])), "hours": int(hours)}}
            for r in rules]


def learn(cfg: sys_config.Config, llm, hours: float = 24) -> dict:
    """Read the documentation and the traffic, propose checks; the owner's rules switched on are kept as they are."""
    groups = observe(cfg, hours)
    doc = doc_text(str(cfg["AURORA_SECURITY_SYSLOG_DOC"]))
    new = tried(cfg, proposals(llm, doc, groups), hours)
    old = sec_rules.load(cfg)
    keep = [r for r in old if r["on"]]
    rules = keep + [r for r in new if r["id"] not in {k["id"] for k in keep}]
    sec_rules.save(cfg, rules)
    return {"groups": len(groups), "lines": sum(g["count"] for g in groups), "proposed": len(new), "rules": rules}

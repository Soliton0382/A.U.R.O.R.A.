# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The owner's verdicts put to use (owner, 2026-10-27: «sono passate 2 settimane ma mi sembra che la situazione non sia
cambiata anche se do i feedback su quello che ricevo»): until then a verdict was only counted by the scorecard, and
over three weeks about half of the judged incidents stayed false alarms (76 of 146, 52 of 118, 13 of 21).

Each incident has a pattern: what it is AND which device — an IPS alert by direction and port, a new port by its
range, a new country, a spike of invalid traffic, each on one device (its MAC, else its address). A kind alone would
blind the house to every alert of that kind (C407, owner: «la tipologia di allarme (ad esempio ips) rende ciechi su
ogni allarme ips»): quieting a phone's DNS alerts must leave a new device's DNS alerts loud.
When the owner's verdicts on one pattern are at least PROPOSE_FA false alarms with at most PROPOSE_RIGHT of them right,
it is quieted as the Autonomy page says for security (owner, 27 Oct: «l'obiettivo è arrivare ad avere aurora che prende
decisioni in modo indipendente»): at 🚀 by Aurora herself, written to her ledger and told; at 🤝 or 🔒 proposed (a
notification, and a box on the Security page with the counts) and the owner says yes or no. A quiet pattern's
incidents are still kept and listed, as low, with no notification and no inquiry; a verdict «right» on one of them
wakes the pattern again, and so does the owner's click. Never quieted: a decoy touched, a known attacker's address, a
device of the house reaching one, a reconnaissance followed by an exit.
State: <STATUS>/incidents_quiet.json, {pattern: {"state", "at", "fa", "right", "name"}}."""
from __future__ import annotations

import json
import os
import re
import threading
import time
from collections import Counter
from pathlib import Path

from . import sys_config

PROPOSE_FA = 3            # false alarms on one device's pattern before a proposal (M262: 14 proposals, 94 of 158)
PROPOSE_RIGHT = 0.2       # at most this share of its verdicts right (M262: 7 right inside the 14)
WINDOW_DAYS = 30          # the verdicts counted
NEVER = {"honeypot", "recon_then_out", "egress_deny"}
_lock = threading.Lock()


def _file(cfg: sys_config.Config) -> Path:
    return cfg.path("AURORA_STATUS_DIR") / "incidents_quiet.json"


def load(cfg: sys_config.Config) -> dict:
    try:
        return json.loads(_file(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(cfg: sys_config.Config, st: dict) -> None:
    f = _file(cfg)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, f)


def what(incident: dict) -> str | None:
    """What the incident is, without who; None for what is never quieted."""
    kind = str(incident.get("kind", ""))
    if kind in NEVER or incident.get("intel_lists") or incident.get("destination_lists"):
        return None
    if kind == "ips_alert":
        port = next((m.group(1) for s in incident.get("samples") or [] if (m := re.search(r'dst_port="?(\d+)', s))), "")
        return f"ips_alert|{'in' if incident.get('internal') else 'out'}|{port or '?'}"
    if kind == "behaviour:new_port":
        m = re.search(r"(\d+)", str((incident.get("detail") or {}).get("title", "")))
        return f"behaviour:new_port|{'high' if m and int(m.group(1)) >= 1024 else 'low'}"
    return kind or None


def device(incident: dict) -> str:
    """Which device: its MAC (an address may change hands), else its address."""
    return str((incident.get("detail") or {}).get("mac") or incident.get("source") or "?").lower()


def pattern(incident: dict) -> str | None:
    w = what(incident)
    return f"{w}|{device(incident)}" if w else None


def label(p: str, lang: str = "it", name: str = "") -> str:
    """The pattern as the owner reads it: what, on which device."""
    parts = p.split("|")
    dev = name or parts[-1]
    parts = parts[:-1]
    it = lang != "en"
    if parts[0] == "ips_alert":
        where = ("da" if it else "from") if parts[1] == "in" else ("da Internet," if it else "from the Internet,")
        return (f"allarme IPS {where} {dev} verso la porta {parts[2]}" if it
                else f"IPS alert {where} {dev} to port {parts[2]}")
    if parts[0] == "behaviour:new_port":
        hi = parts[1] == "high"
        return (f"{dev} usa una porta nuova " + ("alta (≥ 1024)" if hi else "di servizio (< 1024)")) if it \
            else (f"{dev} uses a new " + ("high port (≥ 1024)" if hi else "service port (< 1024)"))
    names = {"behaviour:new_country": ("{d} parla con un paese nuovo", "{d} talks with a new country"),
             "behaviour:new_device": ("{d}, dispositivo nuovo in rete", "{d}, a new device on the network"),
             "rule:invalid_traffic_spike": ("picco di traffico non valido da {d}", "spike of invalid traffic from {d}")}
    return names.get(parts[0], (parts[0] + " · {d}", parts[0] + " · {d}"))[0 if it else 1].format(d=dev)


def tally(items: list[dict], now: float | None = None) -> dict[str, Counter]:
    """The owner's verdicts per pattern over WINDOW_DAYS."""
    since = (time.time() if now is None else now) - WINDOW_DAYS * 86400
    out: dict[str, Counter] = {}
    for i in items:
        p = pattern(i)
        if p and i.get("verdict") and float(i.get("verdict_at") or i.get("received_ts") or 0) >= since:
            out.setdefault(p, Counter())[i["verdict"]] += 1
    return out


def names(items: list[dict]) -> dict[str, str]:
    """Each pattern's device as the firewall names it (the newest incident's), where it has a name."""
    out: dict[str, str] = {}
    for i in items:
        p = pattern(i)
        if p and i.get("known") and p not in out:
            out[p] = str(i["known"])
    return out


def proposals(cfg: sys_config.Config, items: list[dict], lang: str = "it") -> list[dict]:
    """The patterns worth quieting that the owner has not answered yet, most false alarms first."""
    st, named = load(cfg), names(items)
    out = []
    for p, c in tally(items).items():
        judged = sum(c.values())
        if c["false_alarm"] >= PROPOSE_FA and c["right"] <= PROPOSE_RIGHT * judged \
                and st.get(p, {}).get("state") not in ("quiet", "declined"):
            out.append({"pattern": p, "label": label(p, lang, named.get(p, "")), "name": named.get(p, ""),
                        "false_alarm": c["false_alarm"], "right": c["right"], "judged": judged})
    return sorted(out, key=lambda x: -x["false_alarm"])


def quiet_list(cfg: sys_config.Config, lang: str = "it") -> list[dict]:
    return [{"pattern": p, "label": label(p, lang, v.get("name", "")), **v}
            for p, v in load(cfg).items() if v.get("state") == "quiet"]


def is_quiet(cfg: sys_config.Config, incident: dict) -> str | None:
    p = pattern(incident)
    return p if p and load(cfg).get(p, {}).get("state") == "quiet" else None


def answer(cfg: sys_config.Config, p: str, state: str, counts: Counter | None = None, name: str = "") -> dict:
    """The owner's answer: quiet, declined (not proposed again) or awake (as before)."""
    if state not in ("quiet", "declined", "awake"):
        raise ValueError("state: quiet, declined or awake")
    with _lock:
        st = load(cfg)
        c = counts or Counter()
        st[p] = {"state": state, "at": time.time(), "fa": c["false_alarm"], "right": c["right"],
                 "name": name or st.get(p, {}).get("name", "")}
        _save(cfg, st)
    return {"pattern": p, **st[p]}


def by_kind(cfg: sys_config.Config, items: list[dict]) -> list[str]:
    """C407: an answer given to a kind alone, before the device was part of the pattern, made again per device — a
    kind quieted becomes its devices that meet the rule, quieted; the rest of that kind loud again; a kind declined is
    forgotten, so its devices may be proposed. The old entries go. Returns the patterns quieted."""
    with _lock:
        st = load(cfg)
        # a kind alone has the parts of what(): ips_alert|in|53, behaviour:new_port|high, behaviour:new_country
        old = {k: v for k, v in st.items()
               if len(k.split("|")) == {"ips_alert": 3, "behaviour:new_port": 2}.get(k.split("|")[0], 1)}
        if not old:
            return []
        for k in old:
            del st[k]
        _save(cfg, st)
    done = []
    named = names(items)
    for p, c in tally(items).items():
        kind = p.rsplit("|", 1)[0]
        if old.get(kind, {}).get("state") == "quiet" and c["false_alarm"] >= PROPOSE_FA \
                and c["right"] <= PROPOSE_RIGHT * sum(c.values()):
            answer(cfg, p, "quiet", c, named.get(p, ""))
            done.append(p)
    return done


def after_verdict(cfg: sys_config.Config, items: list[dict], incident: dict, lang: str = "it") -> dict | None:
    """After a verdict: a «right» on a quiet pattern wakes it ({"woke"}); a pattern that now qualifies is proposed
    once ({"propose"}); else None."""
    p = pattern(incident)
    if not p:
        return None
    st = load(cfg).get(p, {})
    if incident.get("verdict") == "right" and st.get("state") == "quiet":
        answer(cfg, p, "awake")
        return {"woke": p, "label": label(p, lang, st.get("name", ""))}
    if st.get("proposed") or st.get("state") in ("quiet", "declined"):
        return None
    hit = next((x for x in proposals(cfg, items, lang) if x["pattern"] == p), None)
    if hit:
        with _lock:
            s = load(cfg)
            s.setdefault(p, {})["proposed"] = time.time()
            _save(cfg, s)
        return {"propose": hit}
    return None

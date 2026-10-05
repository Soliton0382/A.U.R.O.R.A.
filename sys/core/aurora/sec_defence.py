# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Autonomous defence (owner's goal, 2026-10-05): on an attack Aurora blocks the source on the firewall by herself,
within limits the owner sets, for a time, recorded and told — and lifted by herself when the time is over.

AURORA_DEFENCE_MODE: off | suggest (the incident shows the ⛔ button, the owner decides: today's behaviour) | auto.
Auto blocks an incident's source only when ALL hold:
- the installation is exempted from the ethics code's level B (rule 7: an action outside the machine waits for the
  owner otherwise) — the code's level A asks exactly this: "an attack is answered by defence";
- the incident's severity reaches AURORA_DEFENCE_MIN_SEVERITY;
- the source is a public address: an address of the local network is never blocked by herself (a device of the
  house behaving badly is told, the owner decides), nor one of AURORA_DEFENCE_PROTECTED, nor what sec_fwapi refuses
  (the firewall, this machine, special addresses);
- today's automatic blocks are fewer than AURORA_DEFENCE_MAX_PER_DAY.
Each block lasts AURORA_DEFENCE_HOURS, then release_due() lifts it. Never a rule on the firewall: only the address
in the blocking group (sec_fwapi). State: <AURORA_STATUS_DIR>/defence.json.
"""
from __future__ import annotations

import ipaddress
import json
import os
import threading
import time
from pathlib import Path

from . import sec_fwapi, sys_config, sys_log

_lock = threading.Lock()
RANK = {"low": 0, "medium": 1, "high": 2}


def _file(cfg: sys_config.Config) -> Path:
    return cfg.path("AURORA_STATUS_DIR") / "defence.json"


def _load(cfg: sys_config.Config) -> list[dict]:
    f = _file(cfg)
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    except ValueError:
        return []


def _save(cfg: sys_config.Config, items: list[dict]) -> None:
    f = _file(cfg)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(items[-2000:], indent=1), encoding="utf-8")
    os.replace(tmp, f)


def protected(cfg: sys_config.Config) -> list[ipaddress._BaseNetwork]:
    out = []
    for raw in str(cfg["AURORA_DEFENCE_PROTECTED"] or "").split(","):
        try:
            out.append(ipaddress.ip_network(raw.strip(), strict=False))
        except ValueError:
            continue
    return out


def active(cfg: sys_config.Config) -> list[dict]:
    now = time.time()
    return [b for b in _load(cfg) if not b.get("released") and b["until"] > now]


def decide(cfg: sys_config.Config, incident: dict) -> tuple[bool, str]:
    """(block now, why): every reason it does not is said, for the incident's card."""
    from . import sys_ethics
    if str(cfg["AURORA_DEFENCE_MODE"]) != "auto":
        return False, "mode"
    if not sys_ethics.exempt(cfg):
        return False, "not exempted from level B: the owner decides"
    if RANK.get(incident.get("severity", "low"), 0) < RANK.get(str(cfg["AURORA_DEFENCE_MIN_SEVERITY"]), 2):
        return False, f"severity {incident.get('severity')} below {cfg['AURORA_DEFENCE_MIN_SEVERITY']}"
    try:
        ip = ipaddress.ip_address(str(incident.get("source", "")).strip())
    except ValueError:
        return False, "no address"
    if incident.get("internal") or not ip.is_global:
        return False, "an address of the local network: told, never blocked by herself"
    if any(ip in net for net in protected(cfg)):
        return False, "a protected address"
    try:
        sec_fwapi.blockable(cfg, str(ip))
    except sec_fwapi.FirewallAPIError as e:
        return False, str(e)
    if any(b["ip"] == str(ip) for b in active(cfg)):
        return False, "already blocked"
    today = time.strftime("%Y-%m-%d")
    if sum(1 for b in _load(cfg) if b.get("auto") and b.get("day") == today) >= int(cfg["AURORA_DEFENCE_MAX_PER_DAY"]):
        return False, "today's limit of automatic blocks reached"
    if not sec_fwapi.configured(cfg):
        return False, "the firewall's API is not set"
    return True, "ok"


def act(cfg: sys_config.Config, incident: dict) -> dict:
    """Block the incident's source now, for AURORA_DEFENCE_HOURS (decide() said yes)."""
    ip = str(incident["source"]).strip()
    reason = f"auto: {incident.get('kind')} {incident.get('id')} ({incident.get('severity')})"
    out = sec_fwapi.block(cfg, ip, reason)
    now = time.time()
    rec = {"ip": ip, "at": now, "until": now + float(cfg["AURORA_DEFENCE_HOURS"]) * 3600, "day": time.strftime("%Y-%m-%d"),
           "incident": incident.get("id"), "kind": incident.get("kind"), "reason": reason, "auto": True,
           "released": None}
    with _lock:
        items = _load(cfg)
        items.append(rec)
        _save(cfg, items)
    sys_log.get_logger("security").info("audit: Aurora blocked %s by herself until %s (%s)", ip,
                                           time.strftime("%Y-%m-%d %H:%M", time.localtime(rec["until"])), reason)
    sys_log.trace("security", "defence.block", {"ip": ip, "incident": incident.get("id"), "hours": cfg["AURORA_DEFENCE_HOURS"]})
    from . import sys_autonomy
    sys_autonomy.log(cfg, "security", f"blocked {ip} for {cfg['AURORA_DEFENCE_HOURS']} h: {reason}")
    return {**out, "until": rec["until"]}


RULE = "Aurora_Block_List"      # the name suggested for the owner's drop rule on the firewall (Aurora writes no rule)


def record_manual(cfg: sys_config.Config, ip: str, reason: str) -> None:
    """A block made by the owner's click: kept here too, so the Security page can undo it (no expiry)."""
    now = time.time()
    with _lock:
        items = _load(cfg)
        items.append({"ip": ip, "at": now, "until": now + 10 * 365 * 86400, "day": time.strftime("%Y-%m-%d"),
                      "incident": None, "kind": "manual", "reason": reason, "auto": False, "released": None})
        _save(cfg, items)


def mark_released(cfg: sys_config.Config, ip: str, by: str) -> None:
    with _lock:
        items = _load(cfg)
        for b in items:
            if b["ip"] == ip and not b.get("released"):
                b["released"], b["released_by"] = time.time(), by
        _save(cfg, items)


def release(cfg: sys_config.Config, ip: str, by: str = "time") -> dict:
    out = sec_fwapi.unblock(cfg, ip)
    mark_released(cfg, ip, by)
    sys_log.get_logger("security").info("audit: block of %s lifted (%s)", ip, by)
    sys_log.trace("security", "defence.release", {"ip": ip, "by": by})
    return out


def release_due(cfg: sys_config.Config) -> list[str]:
    """Lift every automatic block whose time is over; an error leaves it for the next round."""
    now, done = time.time(), []
    for b in [b for b in _load(cfg) if not b.get("released") and b["until"] <= now and b.get("auto", True)]:
        try:
            release(cfg, b["ip"])
            done.append(b["ip"])
        except sec_fwapi.FirewallAPIError as e:
            sys_log.get_logger("security").warning("block of %s not lifted yet: %s", b["ip"], e)
    return done


def summary(cfg: sys_config.Config) -> dict:
    today = time.strftime("%Y-%m-%d")
    items = _load(cfg)
    return {"mode": str(cfg["AURORA_DEFENCE_MODE"]), "hours": cfg["AURORA_DEFENCE_HOURS"],
            "min_severity": str(cfg["AURORA_DEFENCE_MIN_SEVERITY"]), "max_per_day": cfg["AURORA_DEFENCE_MAX_PER_DAY"],
            "protected": [str(n) for n in protected(cfg)], "group": str(cfg["AURORA_FIREWALL_BLOCK_GROUP"]), "rule": RULE, "today": sum(1 for b in items if b.get("auto") and b.get("day") == today),
            "active": active(cfg), "history": items[-50:][::-1], "configured": sec_fwapi.configured(cfg)}

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The firewalls of the house, as many as the owner wants (owner, 16 Oct: «uno imposta lì i firewall, può scegliere
tutti quelli che vuole… impostare quello che serve, le guide… e una volta confermato il collegamento la suite security
comincia a funzionare»). Set in the 🛡️ Security page, the admin's alone.

The first firewall is the one of the settings (.env: AURORA_FIREWALL_API_*, id "main"): the plans, the audit and the
network map read it (they speak its dialect). The others are kept in <STATUS>/security/firewalls.json, their passwords
apart in a sealed file (sys_seal, AES-GCM, the key in the state folder: safe at rest, not against root). Each one is
«confirmed» only after a connection that worked (log in, the blocking group made, its guides indexed): a block of the
suite (an incident, the automatic defence, the owner's click) goes to every confirmed firewall that receives blocks.
"""
from __future__ import annotations

import dataclasses
import json
import re
import threading
import time
from pathlib import Path

from . import sec_fwapi, sys_config, sys_log, sys_seal
from .fw_drivers import KINDS

_lock = threading.Lock()
FIELDS = ("name", "kind", "url", "user", "verify_tls", "block_group", "manual", "api", "syslog", "blocks", "ups_off")
ENV = {"kind": "AURORA_FIREWALL_API_KIND", "url": "AURORA_FIREWALL_API_URL", "user": "AURORA_FIREWALL_API_USER",
       "verify_tls": "AURORA_FIREWALL_VERIFY_TLS", "block_group": "AURORA_FIREWALL_BLOCK_GROUP",
       "manual": "AURORA_FIREWALL_MANUAL_URL", "api": "AURORA_FIREWALL_API_DOC_URL", "syslog": "AURORA_SECURITY_SYSLOG_DOC"}


def _dir(cfg) -> Path:
    d = cfg.path("AURORA_STATUS_DIR") / "security"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load(cfg) -> dict:
    f = _dir(cfg) / "firewalls.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"items": [], "main": {}}


def _save(cfg, data: dict) -> None:
    f = _dir(cfg) / "firewalls.json"
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(f)


def _secrets(cfg) -> dict:
    f = _dir(cfg) / "firewalls.secrets"
    if not f.exists():
        return {}
    return json.loads(sys_seal.read(cfg, f, None, "firewalls").decode("utf-8"))


def _set_secret(cfg, fid: str, password: str | None) -> None:
    s = _secrets(cfg)
    if password is None:
        s.pop(fid, None)
    else:
        s[fid] = password
    sys_seal.write(cfg, _dir(cfg) / "firewalls.secrets", json.dumps(s).encode("utf-8"), None, "firewalls")


def _main(cfg, data: dict) -> dict:
    """The settings' firewall as an item (its state kept in the file's "main")."""
    base = cfg.base or cfg
    it = {k: base[e] for k, e in ENV.items()}
    it.update(id="main", name=data.get("main", {}).get("name") or "Firewall", blocks=data.get("main", {}).get("blocks", True),
              ups_off=bool(data.get("main", {}).get("ups_off")),
              confirmed=data.get("main", {}).get("confirmed"), error=data.get("main", {}).get("error", ""),
              has_password=bool(base["AURORA_FIREWALL_API_PASSWORD"]))
    return it


def items(cfg) -> list[dict]:
    """Every firewall, the settings' one first (when its address is set), never a password."""
    data = _load(cfg)
    out = [_main(cfg, data)] if sec_fwapi.base_url(cfg.base or cfg) else []
    secrets = _secrets(cfg)
    return out + [{**x, "has_password": x["id"] in secrets} for x in data["items"]]


def view(cfg, item: dict) -> sys_config.Config:
    """The configuration a driver reads, with this firewall's address, user, password, group and guides."""
    if item["id"] == "main":
        return cfg.base or cfg
    base = cfg.base or cfg
    values = dict(base.values)
    for k, e in ENV.items():
        if item.get(k) not in (None, ""):
            values[e] = item[k]
    values["AURORA_FIREWALL_API_PASSWORD"] = _secrets(cfg).get(item["id"], "")
    return dataclasses.replace(base, values=values)


def save(cfg, fid: str, fields: dict, password: str | None = None) -> dict:
    """A new firewall (fid "new") or a changed one; a change makes it unconfirmed until it connects again."""
    clean = {k: fields[k] for k in FIELDS if k in fields}
    if "kind" in clean and clean["kind"] not in KINDS:
        raise ValueError(f"kind: one of {KINDS}")
    if "url" in clean and not sec_fwapi.base_url(dataclasses.replace(cfg.base or cfg, values={
            **(cfg.base or cfg).values, "AURORA_FIREWALL_API_URL": clean["url"]})):
        raise ValueError("the address: https://address[:port]")
    with _lock:
        data = _load(cfg)
        if fid == "main":
            env = {ENV[k]: str(v).lower() if isinstance(v, bool) else str(v) for k, v in clean.items() if k in ENV}
            if password:
                env["AURORA_FIREWALL_API_PASSWORD"] = password
            base = cfg.base or cfg
            changed = {k: v for k, v in env.items() if k == "AURORA_FIREWALL_API_PASSWORD" or str(base.raw.get(k, "")) != v}
            if changed:
                sys_config.write_env(cfg.env_file, changed)
            data["main"] = {**data.get("main", {}), "name": clean.get("name", data.get("main", {}).get("name", "")),
                            "blocks": bool(clean.get("blocks", data.get("main", {}).get("blocks", True))),
                            "ups_off": bool(clean.get("ups_off", data.get("main", {}).get("ups_off", False))),
                            **({"confirmed": None} if changed else {})}
            _save(cfg, data)
            return {"id": "main", "restart": bool(changed)}
        if fid == "new":
            fid = re.sub(r"[^a-z0-9]+", "-", str(clean.get("name") or clean.get("kind") or "fw").lower()).strip("-")[:20]
            fid = f"{fid or 'fw'}-{int(time.time()) % 100000}"
            data["items"].append({"id": fid, "kind": "pfsense", "verify_tls": True, "block_group": "Aurora-Blocked",
                                  "blocks": True, "confirmed": None, "error": ""})
        it = next((x for x in data["items"] if x["id"] == fid), None)
        if it is None:
            raise KeyError(fid)
        link = ("kind", "url", "user", "verify_tls", "block_group")   # what the connection depends on
        if password or any(k in clean and clean[k] != it.get(k) for k in link):
            it["confirmed"] = None
        it.update(clean)
        _save(cfg, data)
    if password:
        _set_secret(cfg, fid, password)
    return {"id": fid, "restart": False}


def remove(cfg, fid: str) -> None:
    if fid == "main":
        raise ValueError("the settings' firewall is cleared in its card: its address emptied")
    with _lock:
        data = _load(cfg)
        data["items"] = [x for x in data["items"] if x["id"] != fid]
        _save(cfg, data)
    _set_secret(cfg, fid, None)


def _mark(cfg, fid: str, **state) -> None:
    with _lock:
        data = _load(cfg)
        if fid == "main":
            data["main"] = {**data.get("main", {}), **state}
        else:
            for x in data["items"]:
                if x["id"] == fid:
                    x.update(state)
        _save(cfg, data)


def connect(cfg, fid: str, docs: bool = True) -> dict:
    """Log in, make the blocking group, index the guides in the background: confirmed when the first two worked."""
    it = next((x for x in items(cfg) if x["id"] == fid), None)
    if it is None:
        raise KeyError(fid)
    v = view(cfg, it)
    try:
        test = sec_fwapi.test(v)
        d = sec_fwapi._driver(v)
        sec_fwapi.request(v, d.add_group(str(v["AURORA_FIREWALL_BLOCK_GROUP"])))
    except sec_fwapi.FirewallAPIError as e:
        _mark(cfg, fid, confirmed=None, error=str(e)[:300])
        return {"ok": False, "error": str(e)}
    _mark(cfg, fid, confirmed=time.time(), error="")
    if docs:
        from . import sec_fwdocs
        threading.Thread(target=lambda: sec_fwdocs.refresh(v), daemon=True, name=f"fwdocs-{fid}").start()
    sys_log.get_logger("security").info("audit: firewall %s (%s) connected", fid, it["kind"])
    return {"ok": True, "group_was_there": test.get("group_exists"), "docs": "indexing" if docs else "skipped"}


def ups_targets(cfg) -> list[dict]:
    """The firewalls to shut down with the UPS (owner, 28 Oct: a tick in each firewall's card), with the view a driver
    reads."""
    return [{**x, "cfg": view(cfg, x)} for x in items(cfg) if x.get("ups_off")]


def receivers(cfg) -> list[dict]:
    """The confirmed firewalls that receive blocks; the settings' one also never connected here, while it is set and
    its last connection did not fail (a firewall set before this page keeps working as before, whatever is added)."""
    out = []
    for x in items(cfg):
        legacy = x["id"] == "main" and sec_fwapi.configured(cfg.base or cfg) and not x.get("error")
        if x.get("blocks", True) and (x.get("confirmed") or legacy):
            out.append(x)
    return out


def _each(cfg, fn, ip: str, *args) -> dict:
    done, failed = {}, {}
    for it in receivers(cfg):
        try:
            done[it["id"]] = fn(view(cfg, it), ip, *args)
        except sec_fwapi.FirewallAPIError as e:
            failed[it["id"]] = str(e)[:300]
    if not done:
        raise sec_fwapi.FirewallAPIError("; ".join(f"{k}: {v}" for k, v in failed.items())
                                         or "no firewall connected (🛡️ Security → Firewall)")
    return {"firewalls": done, "failed": failed}


def block(cfg, ip: str, reason: str = "") -> dict:
    """The address blocked on every firewall that receives blocks; the first answer's fields kept for the callers."""
    out = _each(cfg, sec_fwapi.block, ip, reason)
    return {**next(iter(out["firewalls"].values())), **out}


def unblock(cfg, ip: str) -> dict:
    out = _each(cfg, sec_fwapi.unblock, ip)
    return {**next(iter(out["firewalls"].values())), **out}


def kinds() -> list[dict]:
    """Each dialect with its official guides and what it can do so far (for the page's form)."""
    import importlib
    out = []
    for k in KINDS:                                       # the modules alone: no configuration needed
        d = importlib.import_module(f"{__package__}.fw_drivers.{k}")
        out.append({"kind": k, "docs": getattr(d, "DOCS", {}), "user_is_key": k == "opnsense"})   # all: audit, map, plans (N8)
    return out

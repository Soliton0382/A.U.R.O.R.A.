# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Who is behind Cloudflare, and a block where they are seen (ROADMAP 103 step 2).

The firewall sees Cloudflare's nodes, never the client: the address that matters is the one Cloudflare saw. Read
from Cloudflare's own analytics (GraphQL, httpRequestsAdaptiveGroups): the clients whose requests the origin did not
answer (520–526: refused or dropped by the firewall) in the last hours, with hosts and paths — the owner judges who
is a scanner. A block is an IP Access Rule of the account (mode block, every zone), each one with the owner's
approval (the plugin's tool is "external"), recorded in <STATUS>/security/cf_blocks.json and lifted by itself after
its hours (release_due, the API's defence round) or with unblock.

The token needs, beyond the tunnel's: Account · Account Firewall Access Rules · Edit, Zone · Zone · Read and
Zone · Analytics · Read (measured 14 Oct on the owner's token: zones 0, access rules 403 — said, not guessed). The
account's own analytics are no way around the zones: there, httpRequestsAdaptiveGroups answers «not authorized for
that account» (measured with Account Analytics · Read)."""
from __future__ import annotations

import ipaddress
import json
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import net_cloudflare, sec_intel, sys_config, sys_log

_lock = threading.Lock()
QUERY = """query($zone: String!, $since: Time!, $until: Time!) { viewer { zones(filter: {zoneTag: $zone}) {
  httpRequestsAdaptiveGroups(limit: 200, orderBy: [count_DESC], filter: {datetime_geq: $since, datetime_leq: $until,
    edgeResponseStatus_geq: 520, edgeResponseStatus_leq: 526}) {
    count dimensions { clientIP clientRequestHTTPHost clientRequestPath edgeResponseStatus } } } } }"""
NEEDS = ("il token di Cloudflare non ha i permessi: aggiungi Account · Account Firewall Access Rules · Edit, "
         "Zone · Zone · Read e Zone · Analytics · Read — le ultime due scegliendo «Zone» nel PRIMO menu della riga, "
         "con Zone Resources: Include · All zones from an account (dash.cloudflare.com → il token → Edit)")


class CloudflareError(Exception):
    pass


def _file(cfg: sys_config.Config) -> Path:
    return cfg.path("AURORA_STATUS_DIR") / "security" / "cf_blocks.json"


def _load(cfg: sys_config.Config) -> list[dict]:
    try:
        return json.loads(_file(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save(cfg: sys_config.Config, items: list[dict]) -> None:
    f = _file(cfg)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(items[-1000:], ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, f)


def _conf(cfg: sys_config.Config) -> dict:
    c = net_cloudflare.conf(cfg)
    if net_cloudflare.missing(c):
        raise CloudflareError(net_cloudflare.missing(c))
    return c


def _call(cl, method: str, path: str, **kw):
    out, err = net_cloudflare._call(cl, method, path, **kw)
    if err:
        raise CloudflareError(NEEDS if ("403" in err or "10000" in err) else err)
    return out


def culprits(cfg: sys_config.Config, hours: float = 24, limit: int = 20) -> list[dict]:
    """The clients the origin did not answer in the last `hours` (≤ 24), most requests first, across the zones."""
    c = _conf(cfg)
    until = datetime.now(timezone.utc).replace(microsecond=0)
    since = until - timedelta(hours=max(1.0, min(24.0, float(hours))))
    seen: dict[str, dict] = {}
    with net_cloudflare.client(c) as cl:
        zones = _call(cl, "GET", f"/zones?account.id={c['acc']}&per_page=50") or []
        if not zones:
            raise CloudflareError(NEEDS + " — nessuna zona visibile")
        for z in zones:
            for g in _graphql(cl, z["id"], since, until):
                d = g["dimensions"]
                s = seen.setdefault(d["clientIP"], {"ip": d["clientIP"], "requests": 0, "hosts": set(), "paths": {},
                                                     "statuses": set()})
                s["requests"] += g["count"]
                s["hosts"].add(d["clientRequestHTTPHost"])
                s["paths"][d["clientRequestPath"]] = s["paths"].get(d["clientRequestPath"], 0) + g["count"]
                s["statuses"].add(d["edgeResponseStatus"])
    out = sorted(seen.values(), key=lambda s: -s["requests"])[:limit]
    return [{**s, "hosts": sorted(s["hosts"]), "statuses": sorted(s["statuses"]), "looks": looks(cfg, s),
             "paths": [p for p, _ in sorted(s["paths"].items(), key=lambda x: -x[1])[:5]]} for s in out]


SECRETS = re.compile(r"\.env|\.git|\.aws|credential|\.netrc|wp-login|xmlrpc|phpinfo|\.ya?ml$|\.bak$|keyfile|"
                     r"wp-json|config\.|/admin|\.php$", re.I)


def looks(cfg: sys_config.Config, s: dict) -> str:
    """What a client seems, for the owner's judgement — a guess from the paths, never a verdict."""
    paths = list(s["paths"])
    if any(p.startswith("/v1/aurora/") for p in paths):
        return "Aurora's own app (a device of yours away from home?): not to block"
    provider = sec_intel.shared(cfg, s["ip"])
    if any(SECRETS.search(p) for p in paths):
        return "scanner (secrets, admin pages)" + (f" from a {provider} machine" if provider else "")
    if provider == "Google" and any(p.startswith("/.well-known/") for p in paths):
        return "Google's own service (app links): not to block"
    return "unknown, few requests" if s["requests"] < 5 else "unknown, many requests"


def _graphql(cl, zone: str, since: datetime, until: datetime) -> list[dict]:
    """GraphQL answers 200 with its errors in the body: read them, never an empty list in their place."""
    import httpx
    try:
        r = cl.post(net_cloudflare.API + "/graphql", json={"query": QUERY, "variables": {
            "zone": zone, "since": since.strftime("%Y-%m-%dT%H:%M:%SZ"), "until": until.strftime("%Y-%m-%dT%H:%M:%SZ")}})
        j = r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise CloudflareError(f"analytics di Cloudflare non raggiungibili ({type(e).__name__})") from None
    if j.get("errors"):
        msg = "; ".join(str(e.get("message", "")) for e in j["errors"])[:300]
        raise CloudflareError(NEEDS if "authz" in msg.lower() or "not authorized" in msg.lower() else msg)
    zones = ((j.get("data") or {}).get("viewer") or {}).get("zones") or []
    return zones[0].get("httpRequestsAdaptiveGroups", []) if zones else []


def blockable(cfg: sys_config.Config, ip: str) -> str:
    try:
        a = ipaddress.ip_address(ip.strip())
    except ValueError:
        raise CloudflareError(f"{ip!r} non è un indirizzo") from None
    if not a.is_global:
        raise CloudflareError("su Cloudflare si bloccano solo indirizzi di Internet")
    # only Cloudflare's own node is a carrier, never the author; a cloud's machine seen BY Cloudflare is the client
    # itself (C315: a Google Cloud VM reading /.aws/credentials was refused as «shared»)
    if sec_intel.shared(cfg, str(a)) == "Cloudflare":
        raise CloudflareError(f"{a} è un nodo di Cloudflare, non l'autore")
    from . import sec_defence
    if any(a in n for n in sec_defence.protected(cfg)):
        raise CloudflareError(f"{a} è tra gli indirizzi protetti")
    return str(a)


def active(cfg: sys_config.Config) -> list[dict]:
    return [b for b in _load(cfg) if not b.get("released")]


def block(cfg: sys_config.Config, ip: str, reason: str, hours: float = 24, auto: bool = False) -> dict:
    ip = blockable(cfg, ip)
    if not 1 <= float(hours) <= 24 * 30:
        raise CloudflareError("durata: da 1 ora a 30 giorni")
    if any(b["ip"] == ip for b in active(cfg)):
        raise CloudflareError(f"{ip} è già bloccato su Cloudflare")
    c, now = _conf(cfg), time.time()
    until = now + float(hours) * 3600
    note = f"Aurora: {reason[:200]} (fino al {time.strftime('%Y-%m-%d %H:%M', time.localtime(until))})"
    with net_cloudflare.client(c) as cl:
        rule = _call(cl, "POST", f"/accounts/{c['acc']}/firewall/access_rules/rules",
                     json={"mode": "block", "notes": note, "configuration": {
                         "target": "ip6" if ipaddress.ip_address(ip).version == 6 else "ip", "value": ip}})
    rec = {"ip": ip, "id": rule["id"], "at": now, "until": until, "reason": reason[:300], "released": None,
           "auto": auto, "day": time.strftime("%Y-%m-%d", time.localtime(now))}
    with _lock:
        _save(cfg, _load(cfg) + [rec])
    sys_log.get_logger("security").info("audit: %s blocked on Cloudflare until %s (%s)", ip,
                                        time.strftime("%Y-%m-%d %H:%M", time.localtime(until)), reason)
    return rec


def unblock(cfg: sys_config.Config, ip: str, by: str = "owner") -> dict:
    rec = next((b for b in active(cfg) if b["ip"] == ip.strip()), None)
    if not rec:
        raise CloudflareError(f"{ip} non è bloccato da Aurora su Cloudflare")
    c = _conf(cfg)
    with net_cloudflare.client(c) as cl:
        out, err = net_cloudflare._call(cl, "DELETE", f"/accounts/{c['acc']}/firewall/access_rules/rules/{rec['id']}")
    if err and "404" not in err:                         # gone already (removed in the dashboard): just recorded
        raise CloudflareError(NEEDS if "403" in err else err)
    with _lock:
        items = _load(cfg)
        for b in items:
            if b["id"] == rec["id"]:
                b["released"], b["released_by"] = time.time(), by
        _save(cfg, items)
    sys_log.get_logger("security").info("audit: Cloudflare block of %s lifted (%s)", ip, by)
    return {**rec, "released_by": by}


def release_due(cfg: sys_config.Config, now: float | None = None) -> list[str]:
    now, done = now or time.time(), []
    for b in active(cfg):
        if b["until"] <= now:
            try:
                unblock(cfg, b["ip"], "time")
                done.append(b["ip"])
            except CloudflareError as e:
                sys_log.get_logger("security").warning("Cloudflare block of %s not lifted yet: %s", b["ip"], e)
    return done


def autoblock(cfg: sys_config.Config) -> list[dict]:
    """AURORA_CLOUDFLARE_AUTOBLOCK (owner, 2026-10-14: «quando ci riproviamo li blocco su cloudflare»): the last hour's
    clients that look like scanners (looks(): secrets, admin pages) blocked at Cloudflare by herself, for
    AURORA_DEFENCE_HOURS, at most AURORA_DEFENCE_MAX_PER_DAY a day — only exempted from level B, as the firewall's
    automatic defence. Aurora's own app, Google's service and the unknown are never blocked by herself."""
    from . import sys_ethics
    if not cfg["AURORA_CLOUDFLARE_AUTOBLOCK"] or not sys_ethics.exempt(cfg):
        return []
    log = sys_log.get_logger("security")
    try:
        rows = culprits(cfg, 1, limit=200)
    except CloudflareError as e:
        log.warning("Cloudflare autoblock: %s", e)
        return []
    today, done = time.strftime("%Y-%m-%d"), []
    left = int(cfg["AURORA_DEFENCE_MAX_PER_DAY"]) - sum(1 for b in _load(cfg) if b.get("auto") and b.get("day") == today)
    blocked = {b["ip"] for b in active(cfg)}
    for r in rows:
        if left <= 0:
            log.warning("Cloudflare autoblock: today's limit reached, the rest waits for the owner")
            break
        if not r["looks"].startswith("scanner") or r["ip"] in blocked:
            continue
        why = f"scanner: {r['requests']} richieste a {', '.join(r['paths'][:3])}"
        try:
            done.append(block(cfg, r["ip"], why, float(cfg["AURORA_DEFENCE_HOURS"]), auto=True))
            left -= 1
        except CloudflareError as e:
            log.warning("Cloudflare autoblock of %s: %s", r["ip"], e)
    if done:
        from . import sys_autonomy
        sys_autonomy.log(cfg, "security", f"blocked {len(done)} scanners at Cloudflare: "
                                          + ", ".join(b["ip"] for b in done))
    return done

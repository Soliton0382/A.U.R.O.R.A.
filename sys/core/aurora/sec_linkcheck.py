# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A link's reputation before Aurora opens it (owner, 2026-10-13: «per evitare che aurora nella chat sia obbligata ad
accedere a link dubbi… virus total… nel caso si rifiuta di accedere indicando il motivo»; «lo metterei
come controllo plugin attivo di default… con le spunte sui servizi da usare»).

The plugin «linkcheck» (on by default) holds the switches and the keys; this module does the check, for the pages
the answers open (kno_web.page), for every tool call of an agent that carries a link (agt_loop), and for the plugin's
own tool. The services the owner ticks — each needs its key, except the checks of the link itself:
    form        always: credentials in the link (user@host), a host in punycode (a look-alike), a raw IP
    virustotal  VirusTotal v3: the URL's last analysis by ~90 engines (malicious ≥ 2 → malicious; 1 or suspicious → suspicious)
    urlhaus     abuse.ch URLhaus: a listed malware URL or host → malicious
    abuseipdb   AbuseIPDB, for a raw IP or the host's address (the netintel key): confidence ≥ 75 malicious, ≥ 25 suspicious
Blocked: any «malicious»; with AURORA_LINKCHECK_STRICT also a «suspicious» one. A service that fails or has no key
says «not checked», never «clean». Verdicts are kept a day (<STATUS>/linkcheck.json): quotas are small (VirusTotal's
free one: 4 a minute, 500 a day)."""
from __future__ import annotations

import base64
import ipaddress
import json
import socket
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from . import sys_config, sys_log

SERVICES = ("virustotal", "urlhaus", "abuseipdb")
KEEP_S = 24 * 3600
_lock = threading.Lock()
RANK = {"clean": 0, "unknown": 0, "suspicious": 1, "malicious": 2}


def _on(cfg, key: str, default: bool = False) -> bool:
    try:
        v = cfg[key]
    except KeyError:
        return default
    return v if isinstance(v, bool) else str(v).strip().lower() in sys_config.TRUE_WORDS


def _val(cfg, key: str) -> str:
    try:
        return str(cfg[key] or "").strip()
    except KeyError:
        return ""


def enabled(cfg) -> bool:
    """The plugin «linkcheck» is on (the Plugins page): on unless switched off."""
    f = cfg.path("AURORA_STATUS_DIR") / "plugins.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("linkcheck", {}).get("enabled", True)
    except (OSError, ValueError):
        return True


def _cache_file(cfg) -> Path:
    return cfg.path("AURORA_STATUS_DIR") / "linkcheck.json"


def _cached(cfg, url: str) -> dict | None:
    try:
        d = json.loads(_cache_file(cfg).read_text(encoding="utf-8")).get(url)
    except (OSError, ValueError):
        return None
    return d if d and time.time() - d.get("at", 0) < KEEP_S else None


def _keep(cfg, url: str, verdict: dict) -> None:
    with _lock:
        f = _cache_file(cfg)
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            d = {}
        now = time.time()
        d = {k: v for k, v in d.items() if now - v.get("at", 0) < KEEP_S}
        d[url] = verdict
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        tmp.replace(f)


# ---- the link itself (no service) -------------------------------------------------------------------------------

def form(url: str) -> tuple[str, list[str]]:
    u = urlsplit(url)
    host = (u.hostname or "").lower()
    why, level = [], "clean"
    if u.username or u.password:
        why.append("il link contiene credenziali (utente@host): un trucco classico per mascherare il sito vero")
        level = "suspicious"
    if any(p.startswith("xn--") for p in host.split(".")):
        why.append(f"il nome del sito è in punycode ({host}): può imitare un altro sito con lettere simili")
        level = "suspicious"
    return level, why


def _ip_of(host: str) -> str | None:
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        try:
            return socket.gethostbyname(host)
        except OSError:
            return None


# ---- the services -----------------------------------------------------------------------------------------------

def virustotal(c: httpx.Client, cfg, url: str) -> tuple[str, str]:
    key = _val(cfg, "AURORA_LINKCHECK_VIRUSTOTAL_KEY")
    if not key:
        return "unknown", "VirusTotal: nessuna chiave"
    vid = base64.urlsafe_b64encode(url.encode()).decode().strip("=")
    r = c.get(f"https://www.virustotal.com/api/v3/urls/{vid}", headers={"x-apikey": key})
    if r.status_code == 404:
        return "unknown", "VirusTotal: link mai analizzato"
    r.raise_for_status()
    s = r.json()["data"]["attributes"].get("last_analysis_stats", {})
    bad, sus = int(s.get("malicious", 0)), int(s.get("suspicious", 0))
    level = "malicious" if bad >= 2 else "suspicious" if bad or sus else "clean"
    return level, f"VirusTotal: {bad} motori lo dicono malevolo, {sus} sospetto"


def urlhaus(c: httpx.Client, cfg, url: str) -> tuple[str, str]:
    key = _val(cfg, "AURORA_LINKCHECK_URLHAUS_KEY")
    if not key:
        return "unknown", "URLhaus: nessuna chiave (abuse.ch, gratuita)"
    r = c.post("https://urlhaus-api.abuse.ch/v1/url/", data={"url": url}, headers={"Auth-Key": key})
    r.raise_for_status()
    d = r.json()
    if d.get("query_status") == "ok":
        return "malicious", f"URLhaus: link di malware noto ({d.get('threat') or 'malware'}, {d.get('url_status', '')})"
    host = urlsplit(url).hostname or ""
    r = c.post("https://urlhaus-api.abuse.ch/v1/host/", data={"host": host}, headers={"Auth-Key": key})
    if r.is_success and r.json().get("query_status") == "ok" and int(r.json().get("url_count") or 0):
        return "suspicious", f"URLhaus: il sito {host} ha ospitato {r.json()['url_count']} link di malware"
    return "clean", "URLhaus: non presente"


def abuseipdb(c: httpx.Client, cfg, url: str) -> tuple[str, str]:
    key = _val(cfg, "AURORA_ABUSEIPDB_KEY")
    if not key:
        return "unknown", "AbuseIPDB: nessuna chiave (quella del plugin netintel)"
    ip = _ip_of(urlsplit(url).hostname or "")
    if not ip:
        return "unknown", "AbuseIPDB: indirizzo del sito non risolto"
    r = c.get("https://api.abuseipdb.com/api/v2/check", params={"ipAddress": ip, "maxAgeInDays": 90},
              headers={"Key": key, "Accept": "application/json"})
    r.raise_for_status()
    score = int(r.json()["data"].get("abuseConfidenceScore", 0))
    level = "malicious" if score >= 75 else "suspicious" if score >= 25 else "clean"
    return level, f"AbuseIPDB: {ip} segnalato con affidabilità {score}%"


CHECKS = {"virustotal": virustotal, "urlhaus": urlhaus, "abuseipdb": abuseipdb}


def check(url: str, cfg: sys_config.Config | None = None, client: httpx.Client | None = None) -> dict:
    """{"url", "blocked", "level", "reasons": [...], "checked": [services that answered], "at"}."""
    cfg = cfg or sys_config.get()
    if not enabled(cfg):
        return {"url": url, "blocked": False, "level": "unknown", "reasons": ["controllo dei link spento"], "checked": []}
    hit = _cached(cfg, url)
    if hit:
        return {**hit, "cached": True}
    level, reasons = form(url)
    checked, levels = ["form"], [level]
    own = client is None
    c = client or httpx.Client(timeout=8, headers={"User-Agent": "Aurora/1.0 (link reputation)"})
    try:
        for name in SERVICES:
            if not _on(cfg, f"AURORA_LINKCHECK_{name.upper()}", name in ("virustotal", "urlhaus")):
                continue
            try:
                lv, why = CHECKS[name](c, cfg, url)
            except Exception as e:                    # noqa: BLE001 — a service down: «not checked», never «clean»
                lv, why = "unknown", f"{name}: non risponde ({type(e).__name__})"
            reasons.append(why)
            if lv != "unknown":
                checked.append(name)
                levels.append(lv)
    finally:
        if own:
            c.close()
    worst = max(levels, key=lambda x: RANK[x])
    strict = _on(cfg, "AURORA_LINKCHECK_STRICT", False)
    blocked = worst == "malicious" or (strict and worst == "suspicious") or levels.count("suspicious") >= 2
    out = {"url": url, "blocked": blocked, "level": worst, "reasons": reasons, "checked": checked, "at": time.time()}
    _keep(cfg, url, out)
    sys_log.trace("security", "linkcheck", {k: out[k] for k in ("url", "blocked", "level", "checked")})
    return out


def refusal(v: dict) -> str:
    """The words of a refusal, in Italian, with the reasons the services gave."""
    bad = [r for r in v["reasons"] if not r.endswith(("nessuna chiave", "nessuna credenziale", "non presente",
                                                      "mai analizzato"))]
    return (f"Non apro questo link ({v['url'][:120]}): la sua reputazione è «{v['level']}». "
            + "; ".join(bad[:4]) + ". Se sei sicuro che sia innocuo, aprilo tu dal browser.")


def tool_call(cfg, plugin: str, args: dict, emit, log) -> str:
    """An agent's tool call that carries a link (agt_loop): "" to go on, or the refusal the agent gets instead of the
    call — the services' reasons, to tell the owner (owner, 2026-10-13: «si rifiuta di accedere indicando il motivo»)."""
    if plugin == "linkcheck":
        return ""
    links = [v.strip() for v in args.values() if isinstance(v, str) and v.strip().lower().startswith(("http://", "https://"))]
    for url in links[:3]:
        try:
            v = check(url, cfg)
        except Exception as e:                           # noqa: BLE001 — not checked: said in the log, the call goes on
            log.warning("link check failed for %s: %s", url[:100], e)
            continue
        if v["blocked"]:
            emit("link.refused", {"url": url[:300], "level": v["level"], "reasons": v["reasons"][:6]})
            return "REFUSED: " + refusal(v)
    return ""


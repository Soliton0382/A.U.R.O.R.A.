# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A file's reputation before Aurora reads it (owner, 2026-10-20: «verifiche sulle reputazioni su virus total… anche se
si passano file ad aurora»): the files a person attaches in the chat or uploads to the vault.

Only the file's SHA-256 leaves the machine, never the file: a person's own document is no service's business, and a
hash says nothing of what it holds. The services are the link check's (the plugin «linkcheck»: its switches, its keys):
    virustotal  VirusTotal v3 /files/<sha256>: the last analysis by ~90 engines (malicious ≥ 2 → malicious; 1 or
                suspicious → suspicious); a hash never seen is the common case for a person's own file: «unknown»
    urlhaus     abuse.ch URLhaus /payload/: a payload its malware URLs delivered → malicious
Blocked: any «malicious»; with AURORA_LINKCHECK_STRICT also a «suspicious» one. A service that fails or has no key
says «not checked», never «clean». Verdicts are kept a day with the links' (the hash as their key)."""
from __future__ import annotations

import hashlib
import time

import httpx

from . import sec_linkcheck as L
from . import sys_config, sys_log


def virustotal(c: httpx.Client, cfg, sha: str) -> tuple[str, str]:
    key = L._val(cfg, "AURORA_LINKCHECK_VIRUSTOTAL_KEY")
    if not key:
        return "unknown", "VirusTotal: nessuna chiave"
    r = c.get(f"https://www.virustotal.com/api/v3/files/{sha}", headers={"x-apikey": key})
    if r.status_code == 404:
        return "unknown", "VirusTotal: file mai analizzato"
    r.raise_for_status()
    s = r.json()["data"]["attributes"].get("last_analysis_stats", {})
    bad, sus = int(s.get("malicious", 0)), int(s.get("suspicious", 0))
    level = "malicious" if bad >= 2 else "suspicious" if bad or sus else "clean"
    return level, f"VirusTotal: {bad} motori lo dicono malevolo, {sus} sospetto"


def urlhaus(c: httpx.Client, cfg, sha: str) -> tuple[str, str]:
    key = L._val(cfg, "AURORA_LINKCHECK_URLHAUS_KEY")
    if not key:
        return "unknown", "URLhaus: nessuna chiave (abuse.ch, gratuita)"
    r = c.post("https://urlhaus-api.abuse.ch/v1/payload/", data={"sha256_hash": sha}, headers={"Auth-Key": key})
    r.raise_for_status()
    d = r.json()
    if d.get("query_status") == "ok":
        return "malicious", f"URLhaus: file di malware noto ({d.get('signature') or d.get('file_type') or 'malware'})"
    return "clean", "URLhaus: non presente"


CHECKS = {"virustotal": virustotal, "urlhaus": urlhaus}


def check(data: bytes, name: str = "", cfg: sys_config.Config | None = None, client: httpx.Client | None = None) -> dict:
    """{"sha256", "name", "blocked", "level", "reasons": [...], "checked": [services that answered], "at"}."""
    cfg = cfg or sys_config.get()
    sha = hashlib.sha256(data).hexdigest()
    if not L.enabled(cfg):
        return {"sha256": sha, "name": name, "blocked": False, "level": "unknown", "reasons": ["controllo spento"],
                "checked": []}
    hit = L._cached(cfg, "file:" + sha)
    if hit:
        return {**hit, "name": name, "cached": True}
    reasons, checked, levels = [], [], []
    own = client is None
    c = client or httpx.Client(timeout=8, headers={"User-Agent": "Aurora/1.0 (file reputation)"})
    try:
        for svc in CHECKS:
            if not L._on(cfg, f"AURORA_LINKCHECK_{svc.upper()}", True):
                continue
            try:
                lv, why = CHECKS[svc](c, cfg, sha)
            except Exception as e:                    # noqa: BLE001 — a service down: «not checked», never «clean»
                lv, why = "unknown", f"{svc}: non risponde ({type(e).__name__})"
            reasons.append(why)
            if lv != "unknown":
                checked.append(svc)
                levels.append(lv)
    finally:
        if own:
            c.close()
    worst = max(levels, key=lambda x: L.RANK[x]) if levels else "unknown"
    blocked = worst == "malicious" or (L._on(cfg, "AURORA_LINKCHECK_STRICT") and worst == "suspicious")
    out = {"sha256": sha, "name": name, "blocked": blocked, "level": worst, "reasons": reasons, "checked": checked,
           "at": time.time()}
    if checked:                                       # nothing answered: asked again next time, not kept a day
        L._keep(cfg, "file:" + sha, out)
    sys_log.trace("security", "filecheck", {k: out[k] for k in ("sha256", "blocked", "level", "checked")})
    return out


def refusal(v: dict) -> str:
    """The words of a refusal, in Italian, with the services' reasons."""
    bad = [r for r in v["reasons"] if not r.endswith(("nessuna chiave", "(abuse.ch, gratuita)", "non presente",
                                                      "mai analizzato"))]
    return (f"Non leggo {v['name'] or 'questo file'}: la sua reputazione è «{v['level']}» (SHA-256 {v['sha256'][:16]}…). "
            + "; ".join(bad[:4]) + ".")


def gate(cfg, name: str, data: bytes) -> None:
    """ValueError for a file the services call malicious (an attachment, an upload); any failure lets it in, said."""
    try:
        v = check(data, name, cfg)
    except Exception as e:                            # noqa: BLE001 — not checked: said in the log, the file goes on
        sys_log.get_logger("security").warning("file check failed for %s: %s", name[:100], e)
        return
    if v["blocked"]:
        sys_log.trace("security", "security.filecheck", {"name": name[:120], "sha256": v["sha256"],
                                                         "title": f"🦠 {name[:80]}: file malevolo rifiutato"})
        raise ValueError(refusal(v))

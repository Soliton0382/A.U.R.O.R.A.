# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Threat hunting on the firewall's syslog (owner, 2026-10-07: "understand whether someone slipped into the network,
or a device is doing what it must not — anomalous traffic towards ports or domains that are dubious").
What sec_baseline does not already do (a new device, a new country or port, an unusual upload), over a window:

  beacon     a device of the house calling the same outside address at regular intervals (the heartbeat of a
             malware's command server): ≥ BEACON_MIN connections over ≥ 1 hour, intervals of at least a minute that
             vary less than BEACON_CV; ports 53/123 and addresses that 3+ devices of the house call are left out
             (the cloud services everyone uses)
  sweep      a device of the house touching many other addresses of the house (lateral movement, or a scanner that
             should not be there): ≥ SWEEP_HOSTS distinct internal destinations in SWEEP_MIN minutes
  atp        each Advanced Threat Protection match judged, not just counted: an outside source on a published
             service (who knocks, on which port); a device of the house towards a listed destination, with the feed,
             the port, how many devices call it, the domain seen for it and the threat lists — GreyNoise (a list of
             Internet scanners) on 443 called by several devices is very likely a shared cloud address
  domain     a domain a device reached that looks made by a machine (a long random label: malware's generated
             domains), a top-level domain abused by phishing and malware, or a web category the firewall itself
             calls dangerous
  admin      the firewall's administration: logins (failed ones; any from outside the house) and every configuration
             change («NAT rule … was added by 'admin' from …»): who, what, from where
Read only; AURORA_HUNT_IGNORE names addresses that are allowed to do it (a network scanner of the owner's).
"""
from __future__ import annotations

import ipaddress
import math
import re
import statistics
import time
from collections import Counter, defaultdict
from datetime import datetime

from . import sys_config
from .sec_sentinel import is_private

BEACON_MIN, BEACON_CV, BEACON_SPAN = 10, 0.15, 3600
SWEEP_HOSTS, SWEEP_MIN = 15, 10
QUIET_PORTS = {"53", "123", "853", "5353", "1900"}
RISKY_TLD = {"zip", "mov", "top", "xyz", "tk", "ml", "ga", "cf", "gq", "click", "country", "kim", "work", "rest",
             "cam", "monster", "quest", "cyou", "lol", "surf", "buzz", "icu", "sbs", "bond"}
BAD_CATEGORY = ("malware", "phish", "spyware", "botnet", "command and control", "cryptomining", "hacking")
ODD_CATEGORY = ("anonymizer", "newly registered", "suspicious", "parked", "proxy")   # a policy question, not a threat
CHANGE = re.compile(r"(?P<what>.+?) '(?P<name>[^']*)' was (?P<verb>added|updated|deleted|modified|changed|enabled|disabled)"
                    r" by '(?P<user>[^']*)' from '(?P<ip>[^']*)'", re.I)


def _ts(f: dict) -> float | None:
    t = f.get("timestamp") or f.get("_ts")
    if not t:
        return None
    try:
        return datetime.fromisoformat(re.sub(r"([+-]\d\d)(\d\d)$", r"\1:\2", str(t))).timestamp()
    except ValueError:
        return None


def entropy(label: str) -> float:
    n = len(label)
    return -sum(c / n * math.log2(c / n) for c in Counter(label).values()) if n else 0.0


def machine_made(domain: str) -> bool:
    """A label that looks generated: long, high entropy, few vowels or many digits (not a CDN's known shape)."""
    labels = domain.lower().strip(".").split(".")
    if len(labels) < 2:
        return False
    core = labels[-2]
    if len(core) < 12:
        return False
    vowels = sum(ch in "aeiou" for ch in core) / len(core)
    digits = sum(ch.isdigit() for ch in core) / len(core)
    return entropy(core) >= 3.6 and (vowels < 0.25 or digits > 0.3)


class Hunt:
    """Feed parsed lines (sec_profile.parse) in time order, then findings()."""

    def __init__(self, ignore: set[str] | None = None, intel=None, names: dict[str, str] | None = None, shared=None):
        self.ignore = ignore or set()
        self.known = names or {}                             # address -> the name the firewall gives it (sec_netmap)
        self.shared = shared                                 # ip -> provider of a CDN or a cloud (sec_intel.shared)
        self.intel = intel                                   # ip -> [list names] (sec_intel.lookup), or None
        self.conn: dict[tuple, list[float]] = defaultdict(list)
        self.callers: dict[str, set] = defaultdict(set)
        self.inner: dict[str, list[tuple[float, str]]] = defaultdict(list)
        self.names: dict[str, str] = {}
        self.atp: list[dict] = []
        self.domains: dict[tuple, dict] = {}
        self.admin: list[dict] = []
        self.lines = 0

    def feed(self, f: dict) -> None:
        self.lines += 1
        t = _ts(f) or time.time()
        src, dst, port = f.get("src_ip", ""), f.get("dst_ip", ""), str(f.get("dst_port") or "")
        kind, comp = f.get("log_type", ""), f.get("log_component", "")
        if kind == "Content Filtering":
            name = f.get("domain") or f.get("sni") or ""
            if dst and name:
                self.names[dst] = name
            self._domain(src, name, f)
        elif kind == "ATP":
            self.atp.append({**{k: f.get(k, "") for k in ("log_subtype", "src_ip", "dst_ip", "dst_port", "malware",
                                                          "threatfeed", "src_country", "dst_country")}, "t": t})
        elif kind == "Event" and comp in ("GUI", "API", "SSH", "CLI"):
            self._admin(f, t)
        elif kind == "Firewall" and src and dst and src not in self.ignore:
            if is_private(src) and not is_private(dst) and port not in QUIET_PORTS and f.get("log_subtype") == "Allowed":
                self.conn[(src, dst, port)].append(t)
                self.callers[dst].add(src)
            elif is_private(src) and is_private(dst) and src != dst:
                self.inner[src].append((t, dst))

    def _domain(self, src: str, name: str, f: dict) -> None:
        if not name or not src or src in self.ignore:
            return
        cat = str(f.get("http_category") or f.get("category") or "")
        tld = name.lower().rsplit(".", 1)[-1]
        why, dangerous = [], any(b in cat.lower() for b in BAD_CATEGORY)
        if dangerous or any(b in cat.lower() for b in ODD_CATEGORY):
            why.append(f"categoria del firewall: {cat}")
        if tld in RISKY_TLD:
            why.append(f"dominio .{tld}, molto usato da phishing e malware")
        if machine_made(name):
            why.append("nome che sembra generato da una macchina")
        if why:
            d = self.domains.setdefault((src, name), {"src": src, "domain": name, "why": why, "count": 0,
                                                      "category": cat, "dangerous": dangerous})
            d["count"] += 1

    def _admin(self, f: dict, t: float) -> None:
        msg, ip = str(f.get("message") or ""), str(f.get("src_ip") or "")
        status = str(f.get("status") or "")
        m = CHANGE.search(msg)
        if m:
            self.admin.append({"t": t, "kind": "change", "user": m["user"], "ip": m["ip"], "what": m["what"].strip(),
                               "name": m["name"], "verb": m["verb"].lower()})
        elif "log" in msg.lower() and ("in" in msg.lower()):
            self.admin.append({"t": t, "kind": "login", "user": f.get("user_name", ""), "ip": ip,
                               "ok": status.lower().startswith("success"), "via": f.get("log_component", "")})

    # ---- findings ------------------------------------------------------------------------------------------------
    def label(self, ip: str) -> str:
        return f"{self.known[ip]} ({ip})" if ip in self.known else ip

    def beacons(self) -> list[dict]:
        out = []
        for (src, dst, port), ts in self.conn.items():
            if len(ts) < BEACON_MIN or len(self.callers[dst]) >= 3:
                continue
            ts = sorted(ts)
            if ts[-1] - ts[0] < BEACON_SPAN:
                continue
            gaps = [b - a for a, b in zip(ts, ts[1:]) if b - a > 1]
            if len(gaps) < BEACON_MIN - 1:
                continue
            mean = statistics.mean(gaps)
            cv = statistics.pstdev(gaps) / mean if mean else 9
            if mean >= 60 and cv <= BEACON_CV:
                listed = self.intel(dst) if self.intel else []
                out.append({"kind": "beacon", "severity": "high" if listed else "medium", "source": src, "device": self.label(src),
                            "title": f"Chiamate regolari verso {self.names.get(dst, dst)} ogni {mean / 60:.0f} min",
                            "why": f"{self.label(src)} ha contattato {dst}:{port} {len(ts)} volte in {(ts[-1] - ts[0]) / 3600:.1f} h a "
                                   f"intervalli quasi identici (variazione {cv:.0%}): così fanno i malware con il loro "
                                   "server di comando, ma anche alcuni programmi legittimi (aggiornamenti, telemetria)"
                                   + (f". L'indirizzo è nelle liste di attaccanti: {', '.join(listed)}" if listed else ""),
                            "fix": "verificare quale programma lo fa su quel dispositivo; se non è riconosciuto, metterlo in quarantena",
                            "detail": {"dst": dst, "port": port, "count": len(ts), "every_s": round(mean), "cv": round(cv, 3),
                                       "domain": self.names.get(dst, "")}})
        return out

    def sweeps(self) -> list[dict]:
        out = []
        for src, seen in self.inner.items():
            seen.sort()
            j, best, best_at = 0, set(), 0.0
            for i in range(len(seen)):
                while seen[i][0] - seen[j][0] > SWEEP_MIN * 60:
                    j += 1
                hosts = {d for _, d in seen[j:i + 1]}
                if len(hosts) > len(best):
                    best, best_at = hosts, seen[i][0]
            if len(best) >= SWEEP_HOSTS:
                out.append({"kind": "sweep", "severity": "medium" if src in self.known else "high", "source": src,
                            "title": f"{self.label(src)} ha toccato {len(best)} dispositivi della rete in {SWEEP_MIN} minuti",
                            "why": "È il movimento di chi esplora la rete dall'interno (un dispositivo compromesso, o "
                                   "un programma di scansione): un dispositivo normale parla con pochi altri"
                                   + (". È un dispositivo che il firewall conosce per nome" if src in self.known else
                                      ". Il firewall non lo conosce per nome"),
                            "fix": "se non è un tuo strumento di rete, metterlo in quarantena e controllarlo; se lo è, "
                                   "aggiungerlo a AURORA_HUNT_IGNORE",
                            "detail": {"hosts": sorted(best)[:20], "at": best_at}})
        return out

    def threats(self) -> list[dict]:
        out = []
        inbound = defaultdict(list)
        outbound = defaultdict(list)
        for a in self.atp:
            if "source" in a["log_subtype"].lower():               # from outside, onto a service of the house
                inbound[(a["dst_ip"], a["dst_port"])].append(a)
            else:                                                  # a device of the house towards a listed address
                outbound[a["dst_ip"]].append(a)
        for (target, port), hits in inbound.items():
            sources = sorted({f"{h['src_ip']} ({h['src_country']})" for h in hits})
            out.append({"kind": "atp_in", "severity": "medium", "source": hits[0]["src_ip"],
                        "title": f"{len(sources)} indirizzi segnalati da {hits[0]['threatfeed'] or hits[0]['malware']} "
                                 f"bussano a {self.label(target)} porta {port}",
                        "why": f"{', '.join(sources[:8])}: {len(hits)} tentativi. È un servizio raggiungibile da Internet, e "
                               "chi lo scansiona lo sta catalogando per attaccarlo poi",
                        "fix": "bloccarli (la difesa automatica lo fa da sola in modalità auto) e proteggere il servizio "
                               "con IPS e un filtro per paese (vedi l'audit)",
                        "detail": {"target": target, "port": port, "sources": [h["src_ip"] for h in hits], "count": len(hits)}})
        for dst, hits in outbound.items():
            devices = sorted({h["src_ip"] for h in hits})
            feed = hits[0]["threatfeed"] or hits[0]["malware"]
            port = hits[0]["dst_port"]
            listed = self.intel(dst) if self.intel else []
            provider = self.shared(dst) if self.shared else ""
            domain = self.names.get(dst, "") if self.names.get(dst) != dst else ""
            if listed or feed.lower() not in ("greynoise",):
                sev, verdict = "high", "da trattare come un dispositivo possibilmente compromesso"
            elif port in ("443", "80") and (len(devices) >= 2 or provider):
                sev, verdict = "low", ("molto probabilmente un falso positivo: GreyNoise elenca gli scanner di "
                                       "Internet, e un indirizzo cloud condiviso"
                                       + (f" (è di {provider})" if provider else "") + " chiamato sulla porta web è "
                                       "di solito un servizio legittimo")
            else:
                sev, verdict = "medium", "da verificare"
            out.append({"kind": "atp_out", "severity": sev, "source": devices[0],
                        "title": f"{len(devices)} dispositivo/i della casa verso un indirizzo segnalato da {feed}",
                        "why": f"{', '.join(self.label(d) for d in devices)} → {dst}:{port}" + (f" ({domain})" if domain else "")
                               + f", {len(hits)} volte. Giudizio: {verdict}"
                               + (f". Liste di attaccanti: {', '.join(listed)}" if listed else ""),
                        "fix": "se il giudizio è grave, quarantena del dispositivo; se è un falso positivo, un'eccezione "
                               "ATP sul firewall per quell'indirizzo",
                        "detail": {"dst": dst, "port": port, "devices": devices, "feed": feed, "domain": domain,
                                   "count": len(hits)}})
        return out

    def domain_findings(self) -> list[dict]:
        out = []
        by_src = defaultdict(list)
        for d in self.domains.values():
            by_src[d["src"]].append(d)
        for src, items in by_src.items():
            sev = "high" if any(d["dangerous"] for d in items) else ("medium" if any(d["category"] for d in items
                                                                                   if d["why"][0].startswith("categoria")) else "low")
            out.append({"kind": "domain", "severity": sev, "source": src,
                        "title": f"{self.label(src)}: {len(items)} domini dubbi",
                        "why": "; ".join(f"{d['domain']} ({', '.join(d['why'])}, {d['count']}×)" for d in items[:6]),
                        "fix": "controllare quale applicazione li contatta; con una categoria pericolosa, quarantena",
                        "detail": {"domains": [d["domain"] for d in items][:30]}})
        return out

    def admin_findings(self) -> list[dict]:
        out = []
        failed = Counter(a["ip"] for a in self.admin if a["kind"] == "login" and not a["ok"])
        for ip, n in failed.items():
            out.append({"kind": "admin_fail", "severity": "high" if not is_private(ip) else "medium", "source": ip,
                        "title": f"{n} login falliti all'amministrazione del firewall da {ip}",
                        "why": "Qualcuno prova le password del firewall" + ("" if is_private(ip) else ", da fuori casa"),
                        "fix": "se non sei tu: bloccare l'indirizzo e cambiare la password", "detail": {"count": n}})
        for a in self.admin:
            if a["kind"] == "login" and a["ok"] and a["ip"] and not is_private(a["ip"]):
                out.append({"kind": "admin_outside", "severity": "high", "source": a["ip"],
                            "title": f"Login all'amministrazione del firewall da fuori casa ({a['ip']}, utente {a['user']})",
                            "why": "L'amministrazione dovrebbe essere raggiungibile solo dalla rete di casa o dalla VPN",
                            "fix": "se non sei tu: cambiare subito la password, chiudere l'accesso da WAN", "detail": a})
        changes = [a for a in self.admin if a["kind"] == "change"]
        if changes:
            outside = [c for c in changes if c["ip"] and not is_private(c["ip"])]
            out.append({"kind": "admin_changes", "severity": "high" if outside else "low", "source": changes[-1]["ip"],
                        "title": f"{len(changes)} modifiche alla configurazione del firewall",
                        "why": "; ".join(f"{time.strftime('%d/%m %H:%M', time.localtime(c['t']))} {c['what']} «{c['name']}» "
                                         f"{c['verb']} da {c['user']} ({c['ip']})" for c in changes[-8:]),
                        "fix": "controllare che siano tutte tue" + (" — alcune vengono da fuori casa" if outside else ""),
                        "detail": {"changes": changes[-30:]}})
        return out

    def findings(self) -> list[dict]:
        rank = {"high": 0, "medium": 1, "low": 2}
        out = self.threats() + self.sweeps() + self.beacons() + self.domain_findings() + self.admin_findings()
        return sorted(out, key=lambda f: rank[f["severity"]])


def ignored(cfg: sys_config.Config) -> set[str]:
    out = set()
    for raw in str(cfg["AURORA_HUNT_IGNORE"] or "").split(","):
        raw = raw.strip()
        try:
            out.add(str(ipaddress.ip_address(raw)))
        except ValueError:
            continue
    return out


def run(cfg: sys_config.Config, hours: float = 6) -> dict:
    """Hunt over the last `hours` of the firewall's syslog: {"findings", "lines", "seconds"}."""
    from . import sec_intel
    from .sec_profile import _lines, parse
    t0 = time.time()

    def listed(ip: str) -> list[str]:
        try:
            return [x.get("list", "") for x in sec_intel.lookup(cfg, ip)]
        except Exception:  # noqa: BLE001 — the threat lists are a help, never a reason to stop the hunt
            return []
    from . import sec_netmap
    try:
        known = sec_netmap.names(cfg)
    except Exception:  # noqa: BLE001 — no map yet: addresses without names
        known = {}
    h = Hunt(ignored(cfg), intel=listed if cfg["AURORA_INTEL_ENABLED"] else None, names=known,
             shared=lambda ip: sec_intel.shared(cfg, ip))
    for line in _lines(cfg, hours):
        h.feed(parse(line))
    return {"findings": h.findings(), "lines": h.lines, "seconds": round(time.time() - t0, 1), "hours": hours}


ICON = {"high": "🔴", "medium": "🟠", "low": "🟡"}


def text(result: dict) -> str:
    f = result["findings"]
    head = (f"🔎 Caccia alle minacce, ultime {result['hours']:g} ore ({result['lines']} righe del firewall): "
            + (f"{len(f)} rilievi" if f else "niente di anomalo"))
    return "\n".join([head] + [f"\n{ICON[x['severity']]} **{x['title']}**\n   {x['why']}\n   ➜ {x['fix']}" for x in f])


def fresh(cfg: sys_config.Config, findings: list[dict], hours: float = 24) -> list[dict]:
    """The findings not already told in the last `hours` (same kind, same source): a routine says each once a day."""
    import json
    import os
    f = cfg.path("AURORA_STATUS_DIR") / "security" / "hunt_told.json"
    try:
        told = json.loads(f.read_text())
    except (OSError, ValueError):
        told = {}
    now = time.time()
    told = {k: t for k, t in told.items() if now - t < hours * 3600}
    out = []
    for x in findings:
        key = f"{x['kind']}|{x.get('source', '')}"
        if key not in told:
            told[key] = now
            out.append(x)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(told))
    os.replace(tmp, f)
    return out

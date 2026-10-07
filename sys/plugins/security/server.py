# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "security": what the firewall saw, read only, for the owner's questions and routines.

The incidents raised by aurora-sentinel (status/incidents.json) and the firewall's own lines kept by the sentinel
(logs/firewall/, key=value syslog, Sophos and most firewalls), summarised over a window: allowed and denied
traffic, components, intrusion-prevention events, the busiest sources and destination ports. Defensive only: no
lookup about persons, nothing done on the firewall (ethics code, level A).
"""
from __future__ import annotations

import gzip
import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from aurora import sys_config
from aurora.sec_sentinel import is_ips, is_private, parse, src_of
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

cfg = sys_config.get()
server = MCPServer("security", version="1.0")
SEV = {"high": "🔴", "medium": "🟠", "low": "🟡"}


def tool(fn):
    import functools

    @functools.wraps(fn)
    def wrapped(*a, **k):
        try:
            return fn(*a, **k)
        except ToolError:
            raise
        except Exception as e:
            raise ToolError(f"{type(e).__name__}: {e}") from e
    return server.tool()(wrapped)


def _ts(text: str) -> float | None:
    try:
        return datetime.fromisoformat(text.replace("+0200", "+02:00").replace("+0100", "+01:00")).timestamp()
    except ValueError:
        return None


def incidents_since(hours: float) -> list[dict]:
    f = cfg.path("AURORA_STATUS_DIR") / "incidents.json"
    try:
        items = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    since = time.time() - hours * 3600
    return [i for i in (items if isinstance(items, list) else []) if (_ts(str(i.get("received", ""))) or 0) >= since]


def lines_since(hours: float):
    """The firewall lines of the window, oldest file first; each line starts with the time the sentinel got it."""
    since = time.time() - hours * 3600
    files = sorted(Path(cfg.path("AURORA_LOG_DIR") / "firewall").glob("firewall*"), key=lambda p: p.stat().st_mtime)
    for f in files:
        if f.stat().st_mtime < since:
            continue
        opener = gzip.open if f.suffix == ".gz" else open
        with opener(f, "rt", errors="replace") as h:
            for line in h:
                t = _ts(line[:29])
                if t is not None and t >= since:
                    yield line


def summary(lines) -> dict:
    """Counts over firewall lines (pure: tested offline)."""
    kinds, comps, denied_src, ports, ips = Counter(), Counter(), Counter(), Counter(), Counter()
    n = 0
    for line in lines:
        f = parse(line[line.find("<"):] if "<" in line else line)
        n += 1
        status = f.get("status") or f.get("log_subtype") or "?"
        kinds[(f.get("log_type", "?"), status)] += 1
        comps[f.get("log_component", "?")] += 1
        if str(status).lower().startswith("den") or str(status).lower() == "drop":
            denied_src[src_of(f) or "?"] += 1
            if f.get("dst_port"):
                ports[f["dst_port"]] += 1
        if is_ips(f):                                     # the sentinel's own rule (IDP, IPS, ATP)
            what = f.get("signature_msg") or f.get("message") or f.get("threatname") or f.get("log_subtype") or "?"
            dest = f.get("url") or f.get("domain") or f.get("dst_domain") or f.get("dst_ip") or ""
            ips[f"{f.get('log_type', '?')} {what}{' → ' + dest if dest else ''} da {src_of(f) or '?'}"] += 1
    return {"lines": n, "kinds": kinds.most_common(8), "components": comps.most_common(6),
            "denied_sources": denied_src.most_common(5), "denied_ports": ports.most_common(5), "ips": ips.most_common(5)}


def _format_incidents(items: list[dict]) -> str:
    if not items:
        return "Nessun incidente."
    rows = []
    for i in sorted(items, key=lambda x: str(x.get("received", ""))):
        where = "interna" if str(i.get("internal")) == "True" else "esterna"
        rows.append(f"{SEV.get(i.get('severity'), '⚪')} {str(i.get('received', ''))[11:16]} {i.get('kind')} da {i.get('source')} "
                    f"({where}, {i.get('count')} eventi) — {i.get('status')}")
    return "\n".join(rows)


def _format_summary(s: dict, hours: float) -> str:
    if not s["lines"]:
        return f"Nessuna riga del firewall nelle ultime {hours:g} ore (la sentinella riceve il syslog?)."
    out = [f"{s['lines']} righe in {hours:g} ore."]
    out.append("Traffico: " + ", ".join(f"{t} {st} {n}" for (t, st), n in s["kinds"]))
    if s["denied_sources"]:
        out.append("Più negati, per sorgente: " + ", ".join(
            f"{ip}{' (interna)' if is_private(ip) else ''} {n}" for ip, n in s["denied_sources"]))
    if s["denied_ports"]:
        out.append("Porte di destinazione negate: " + ", ".join(f"{p} ({n})" for p, n in s["denied_ports"]))
    out.append("IPS/ATP: " + ("; ".join(f"{m} ({n})" for m, n in s["ips"]) if s["ips"] else "nessun evento"))
    return "\n".join(out)


@tool
def security_incidents(hours: float = 12) -> str:
    """The security incidents the sentinel raised in the last hours: time, severity, kind, source, events, status."""
    return _format_incidents(incidents_since(max(1.0, min(hours, 24 * 30))))


@tool
def firewall_summary(hours: float = 12) -> str:
    """What the firewall logged in the last hours: allowed and denied traffic, IPS events, top denied sources and ports."""
    h = max(1.0, min(hours, 72))
    return _format_summary(summary(lines_since(h)), h)


@tool
def security_night_report(hours: float = 10) -> str:
    """The morning report: incidents and firewall traffic of the night (the last `hours`)."""
    h = max(1.0, min(hours, 24))
    inc = incidents_since(h)
    return (f"🛡️ Notte del firewall (ultime {h:g} ore)\nIncidenti: {len(inc)}\n{_format_incidents(inc)}\n\n"
            + _format_summary(summary(lines_since(h)), h))


@tool
def network_map(query: str = "") -> str:
    """The network as the firewall sees it (the sealed map): with `query` (a name or an address: "NAS", "192.0.2.10")
    the matching hosts, reserved DHCP addresses and the interface whose network holds it; without, the interfaces,
    zones, DHCP servers, groups and routes."""
    from aurora import sec_netmap
    m = sec_netmap.load(cfg)
    if query.strip():
        return "\n".join(sec_netmap.find(m or {}, query)) or f"Nessun host «{query}» nella mappa di rete."
    return sec_netmap.text(m)


@tool
def network_changes() -> str:
    """Look at the network now through the firewall's API and say what changed since the last look (new devices,
    gone, another address); empty when nothing changed. The map stays sealed."""
    from aurora import sec_fwapi, sec_netmap
    try:
        return sec_netmap.changes_text(sec_netmap.refresh(cfg)["changes"])
    except sec_fwapi.FirewallAPIError as e:
        raise ToolError(f"the firewall's API: {e}") from None


@tool
def security_weekly_report(days: float = 7) -> str:
    """The week of the house's security: a score out of 100, incidents by kind, campaigns (the same kind from one
    network more than once), what the defences blocked, what is missing."""
    from aurora import sec_report
    return sec_report.text(sec_report.week(cfg, max(1.0, min(days, 31))))


# ---- the firewall's documentation, audit, hunt, the security officer's view (owner, 2026-10-07) ----------------------
@tool
def firewall_docs(query: str, kind: str = "") -> str:
    """Search the firewall's official documentation kept on this machine (Sophos Firewall 22.0: the administrator's
    manual, the XML API reference with its sample requests, the syslog reference). Use it before explaining a feature
    or planning a change. `kind`: "manual", "api", "syslog" or "" for all."""
    from aurora import sec_fwdocs
    hits = sec_fwdocs.search(cfg, query, 5, kind or None)
    if not hits:
        st = sec_fwdocs.stats(cfg)
        return ("La documentazione del firewall non è ancora indicizzata (strumento firewall_docs_refresh)."
                if not st["passages"] else f"Nulla su «{query}» nella documentazione.")
    return "\n\n".join(f"[{h['kind']}] {h['title']}\n{h['url']}\n{h['text'][:1500]}" for h in hits)


@tool
def firewall_docs_refresh() -> str:
    """Download and index again the firewall's documentation (manual, API, syslog: about 1,200 pages, some minutes)."""
    from aurora import sec_fwdocs
    out = sec_fwdocs.refresh(cfg)
    return "📚 Documentazione indicizzata: " + ", ".join(f"{k} {v['pages']} pagine ({v['failed']} non lette)" for k, v in out.items())


@tool
def firewall_audit() -> str:
    """Judge the firewall's configuration as a security officer: services published on the Internet (with or without
    IPS and log), administration reachable from outside, threat protection, login security, whether Aurora's blocking
    rule works, whether the syslog reaches Aurora, rules too wide. Read only; each finding has its fix."""
    from aurora import sec_audit, sec_fwapi
    try:
        return sec_audit.text(sec_audit.run(cfg))
    except sec_fwapi.FirewallAPIError as e:
        raise ToolError(f"the firewall's API: {e}") from None


@tool
def threat_hunt(hours: float = 6, only_new: bool = False) -> str:
    """Hunt in the firewall's logs of the last `hours`: devices calling outside at regular intervals (beaconing),
    devices touching many others (lateral movement), Advanced Threat Protection matches judged (false positive or
    not), dubious domains, logins and configuration changes on the firewall. `only_new`: only what was not told in the
    last 24 hours (the routine)."""
    from aurora import sec_hunt
    r = sec_hunt.run(cfg, max(1.0, min(hours, 72)))
    if only_new:
        r["findings"] = [f for f in sec_hunt.fresh(cfg, r["findings"]) if f["severity"] != "low"]
        if not r["findings"]:
            return ""
    return sec_hunt.text(r)


@tool
def security_posture(hours: float = 24) -> str:
    """The security officer's view: the open risks (configuration and activity), signals joined by device (two
    different signals on one device make it a suspect) and, for each scenario, the playbook: the steps in order, who
    does each (Aurora with which tool, or the owner)."""
    from aurora import sec_audit, sec_fwapi, sec_hunt, sec_netmap, sec_playbook
    try:
        audit = sec_audit.run(cfg)
    except sec_fwapi.FirewallAPIError:
        audit = None
    hunt = sec_hunt.run(cfg, max(1.0, min(hours, 72)))
    groups = sec_playbook.correlate(hunt["findings"], incidents_since(hours))
    text = sec_playbook.text(groups, sec_playbook.register(audit, groups), sec_netmap.names(cfg))
    return text + ("" if audit else "\n\n(Configurazione non letta: l'API del firewall non risponde.)")


@tool
def firewall_config(entity: str = "FirewallRule", name: str = "") -> str:
    """The firewall's configuration of one entity, read only (<Get>): FirewallRule, NATRule, Services, IPHost,
    IPHostGroup, Zone, Interface, IPSPolicy, ATP, AdminSettings, LocalServiceACL, SyslogServers, WebFilterPolicy…
    `name`: only the item with that name. Taken from the plugin «xgaudit» Aurora forged (owner, 2026-10-07)."""
    import json as _json
    import re as _re
    from aurora import sec_fwapi, sec_fwconf
    if not _re.fullmatch(r"[A-Za-z][A-Za-z0-9]{1,40}", entity):
        raise ToolError("entity: a name of the API, e.g. NATRule")
    try:
        items = sec_fwconf.get(cfg, entity)
    except (sec_fwapi.FirewallAPIError, sec_fwconf.ConfigError) as e:
        raise ToolError(str(e)) from None
    if name:
        items = [i for i in items if i.get("Name") == name]
    if not items:
        return f"Nessun {entity}" + (f" «{name}»" if name else "") + " sul firewall."
    return f"{len(items)} {entity}:\n" + "\n".join(_json.dumps(i, ensure_ascii=False)[:1500] for i in items[:40])

# ---- changes on the firewall: planned here, applied only with the owner's approval -----------------------------------
def _plan(make) -> str:
    from aurora import sec_fwapi, sec_fwwrite
    try:
        change = sec_fwwrite.propose(cfg, make())
    except (sec_fwwrite.WriteError, sec_fwapi.FirewallAPIError, ValueError) as e:
        raise ToolError(str(e)) from None
    off = "" if cfg["AURORA_FIREWALL_WRITE"] else ("\n\n⚠️ Le modifiche al firewall sono spente (AURORA_FIREWALL_WRITE): "
                                                   "il piano resta pronto.")
    return (sec_fwwrite.text(change) + f"\n\nPer applicarla: firewall_apply con change_id «{change['id']}» "
            "(chiede la tua approvazione)." + off)


@tool
def firewall_plan_publish(name: str, host: str, ports: str, sources: str = "") -> str:
    """Plan making a server of the house reachable from the Internet (not applied): its host, a service with the
    ports, a rule from WAN with intrusion prevention and log (after Aurora's blocking rule), the DNAT on the WAN
    address. `name`: a short label ("Nextcloud"); `host`: the server's private address; `ports`: "443", "443/tcp",
    "32400/tcp,32400/udp"; `sources`: countries or addresses allowed ("Italy", "203.0.113.7"), empty = everyone.
    Show the plan to the owner; firewall_apply applies it."""
    from aurora import sec_fwwrite
    return _plan(lambda: sec_fwwrite.plan_publish(cfg, name, host, ports, sources))


@tool
def firewall_plan_unpublish(name: str) -> str:
    """Plan closing a publication Aurora made (its DNAT, rule and service; not applied)."""
    from aurora import sec_fwwrite
    return _plan(lambda: sec_fwwrite.plan_unpublish(cfg, name))


@tool
def firewall_plan_quarantine(ip: str, reason: str) -> str:
    """Plan isolating a device of the house (not applied): its address in Aurora's quarantine group, whose Drop rule
    stops everything it sends through the firewall."""
    from aurora import sec_fwwrite
    return _plan(lambda: sec_fwwrite.plan_quarantine(cfg, ip, reason))


@tool
def firewall_plan_release(ip: str) -> str:
    """Plan the end of a device's quarantine (not applied)."""
    from aurora import sec_fwwrite
    return _plan(lambda: sec_fwwrite.plan_release(cfg, ip))


@tool
def firewall_plan_harden(rule: str, ips_policy: str, log: bool = True) -> str:
    """Plan putting an intrusion-prevention policy (and the log) on an existing firewall rule — the audit's fix for a
    published service (not applied). The rule as it is now is kept: firewall_revert puts it back."""
    from aurora import sec_fwwrite
    return _plan(lambda: sec_fwwrite.plan_harden(cfg, rule, ips_policy, log))


@tool
def firewall_apply(change_id: str) -> str:
    """Apply a planned firewall change (asks the owner's approval). Every step is checked; at the first failure, or
    if the firewall does not read the objects back within the confirmation time, everything done is undone."""
    from aurora import sec_fwapi, sec_fwwrite
    try:
        return sec_fwwrite.text(sec_fwwrite.apply(cfg, change_id))
    except (sec_fwwrite.WriteError, sec_fwapi.FirewallAPIError) as e:
        raise ToolError(str(e)) from None


@tool
def firewall_revert(change_id: str) -> str:
    """Undo a firewall change Aurora applied (asks the owner's approval)."""
    from aurora import sec_fwapi, sec_fwwrite
    try:
        return sec_fwwrite.text(sec_fwwrite.revert(cfg, change_id))
    except (sec_fwwrite.WriteError, sec_fwapi.FirewallAPIError) as e:
        raise ToolError(str(e)) from None


@tool
def firewall_changes(limit: int = 10) -> str:
    """The firewall changes Aurora planned or applied, newest first, with their state (planned, applied, undone,
    reverted, failed)."""
    from aurora import sec_fwwrite
    items = sec_fwwrite.history(cfg)[-max(1, min(limit, 50)):][::-1]
    return "\n\n".join(sec_fwwrite.text(c) for c in items) or "Nessuna modifica del firewall."


if __name__ == "__main__":
    server.run("stdio")

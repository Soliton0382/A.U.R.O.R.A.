# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Changes on the firewall beyond the blocking group (owner, 2026-10-07: "if I ask that this server be reachable from
outside, she creates the firewall and NAT rules, precisely"; "a device doing what it must not": quarantine).

A change is a list of steps, planned first (plan_*), shown to the owner, applied only through a tool whose effect is
"external" (the owner approves each) and only with AURORA_FIREWALL_WRITE on. Rules of the writer:
- every object Aurora creates is named "Aurora-…" (or "aurora-…" for hosts); she deletes only objects so named;
- an object of the owner's is changed only by harden() (IPS policy and log on one rule), and its XML before the change
  is kept in the change: undo puts it back;
- before applying, the objects the steps touch are read and kept; each step that fails stops the change and undoes
  the steps done; after applying, the firewall must still answer within AURORA_FIREWALL_CONFIRM_S and every object
  must read back as written, or the change is undone ("commit confirmed");
- every change is recorded in <STATUS>/security/fwchanges.json (what, why, steps, result, undo).
XML as in the API reference of SFOS 22.0 (sec_fwdocs.sample) and as the owner's own rules read back (sec_fwconf).
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from xml.sax.saxutils import escape

from . import sec_fwapi, sec_fwconf, sys_config, sys_log

_lock = threading.Lock()
PREFIX = "Aurora-"
NAME = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")


class WriteError(Exception):
    pass


# ---- the record ---------------------------------------------------------------------------------------------------
def _file(cfg: sys_config.Config) -> Path:
    return cfg.path("AURORA_STATUS_DIR") / "security" / "fwchanges.json"


def history(cfg: sys_config.Config) -> list[dict]:
    try:
        return json.loads(_file(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _keep(cfg: sys_config.Config, change: dict) -> None:
    with _lock:
        items = [c for c in history(cfg) if c["id"] != change["id"]] + [change]
        f = _file(cfg)
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(items[-500:], ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, f)


def get_change(cfg: sys_config.Config, change_id: str) -> dict:
    for c in history(cfg):
        if c["id"] == change_id:
            return c
    raise WriteError(f"no change {change_id!r}")


# ---- XML of one step ----------------------------------------------------------------------------------------------
def _x(tag: str, value) -> str:
    if isinstance(value, list):
        return "".join(_x(tag, v) for v in value)
    return f"<{tag}>{escape(str(value))}</{tag}>"


def _set(entity: str, body: str, op: str = "add") -> str:
    return f'<Set operation="{op}"><{entity}>{body}</{entity}></Set>'


def _remove(entity: str, name: str) -> str:
    return f"<Remove><{entity}><Name>{escape(name)}</Name></{entity}></Remove>"


def step(entity: str, name: str, xml: str, undo: str, why: str, owner_object: bool = False) -> dict:
    return {"entity": entity, "name": name, "xml": xml, "undo": undo, "why": why, "owner_object": owner_object}


def host_step(name: str, ip: str, groups: list[str] | None = None) -> dict:
    body = (_x("Name", name) + "<IPFamily>IPv4</IPFamily><HostType>IP</HostType>" + _x("IPAddress", ip)
            + ("<HostGroupList>" + _x("HostGroup", groups) + "</HostGroupList>" if groups else ""))
    return step("IPHost", name, _set("IPHost", body), _remove("IPHost", name), f"l'host {name} = {ip}")


def service_step(name: str, ports: list[tuple[str, str]]) -> dict:
    details = "".join(f"<ServiceDetail><SourcePort>1:65535</SourcePort>{_x('DestinationPort', p)}{_x('Protocol', proto)}"
                      "</ServiceDetail>" for proto, p in ports)
    body = _x("Name", name) + "<Type>TCPorUDP</Type><ServiceDetails>" + details + "</ServiceDetails>"
    return step("Services", name, _set("Services", body), _remove("Services", name),
                f"il servizio {name}: " + ", ".join(f"{proto} {p}" for proto, p in ports))


def rule_step(name: str, desc: str, src_zones: list[str], dst_zones: list[str], services: list[str],
              src_nets: list[str], dst_nets: list[str], action: str, ips: str, after: str | None) -> dict:
    pos = f"<Position>After</Position><After>{_x('Name', after)}</After>" if after else "<Position>Top</Position>"
    pol = (_x("Action", action) + "<LogTraffic>Enable</LogTraffic><SkipLocalDestined>Disable</SkipLocalDestined>"
           + ("<SourceZones>" + _x("Zone", src_zones) + "</SourceZones>" if src_zones else "")
           + ("<DestinationZones>" + _x("Zone", dst_zones) + "</DestinationZones>" if dst_zones else "")
           + "<Schedule>All The Time</Schedule>"
           + ("<SourceNetworks>" + _x("Network", src_nets) + "</SourceNetworks>" if src_nets else "")
           + ("<Services>" + _x("Service", services) + "</Services>" if services else "")
           + ("<DestinationNetworks>" + _x("Network", dst_nets) + "</DestinationNetworks>" if dst_nets else "")
           + _x("IntrusionPrevention", ips or "None"))
    body = (_x("Name", name) + _x("Description", desc[:250]) + "<IPFamily>IPv4</IPFamily><Status>Enable</Status>" + pos
            + "<PolicyType>Network</PolicyType><NetworkPolicy>" + pol + "</NetworkPolicy>")
    return step("FirewallRule", name, _set("FirewallRule", body), _remove("FirewallRule", name), f"la regola {name}: {desc}")


def dnat_step(name: str, desc: str, wan: str, host: str, service: str, sources: list[str]) -> dict:
    body = (_x("Name", name) + _x("Description", desc[:250]) + "<IPFamily>IPv4</IPFamily><Status>Enable</Status>"
            "<Position>Top</Position><LinkedFirewallrule>None</LinkedFirewallrule>"
            + ("<OriginalSourceNetworks>" + _x("Network", sources) + "</OriginalSourceNetworks>" if sources else "")
            + "<OriginalDestinationNetworks>" + _x("Network", wan) + "</OriginalDestinationNetworks>"
            + _x("TranslatedDestination", host) + "<OriginalServices>" + _x("Service", service) + "</OriginalServices>"
            "<TranslatedService>Original</TranslatedService><OverrideInterfaceNATPolicy>Disable</OverrideInterfaceNATPolicy>"
            "<TranslatedSource>Original</TranslatedSource>")
    return step("NATRule", name, _set("NATRule", body), _remove("NATRule", name), f"il NAT {name}: {desc}")


# ---- plans --------------------------------------------------------------------------------------------------------
def _ports(spec: str) -> list[tuple[str, str]]:
    """"443", "443/tcp", "32400/tcp,32400/udp", "8000-8010/tcp" → [("TCP", "443")…]; TCP when not said."""
    out = []
    for part in re.split(r"[,\s]+", spec.strip()):
        if not part:
            continue
        m = re.fullmatch(r"(\d{1,5})(?:[-:](\d{1,5}))?(?:/(tcp|udp))?", part.lower())
        if not m or not 1 <= int(m[1]) <= 65535 or (m[2] and not int(m[1]) < int(m[2]) <= 65535):
            raise WriteError(f"porta non valida: {part!r} (es. 443, 443/tcp, 8000-8010/udp)")
        out.append(((m[3] or "tcp").upper(), m[1] + (f":{m[2]}" if m[2] else "")))
    if not out:
        raise WriteError("nessuna porta")
    return out


def _zone_of(conf: dict, ip: str) -> str:
    a = ipaddress.ip_address(ip)
    for i in conf.get("Interface", []):
        if i.get("IPAddress") and i.get("Netmask") and a in ipaddress.ip_network(f"{i['IPAddress']}/{i['Netmask']}", strict=False):
            return str(i.get("NetworkZone") or "LAN")
    raise WriteError(f"{ip} non è in nessuna rete del firewall")


def _wan(conf: dict) -> tuple[str, str]:
    """("#Port7", "192.168.1.2"): the connected WAN interface, as the DNAT wizard names its address."""
    for i in conf.get("Interface", []):
        if i.get("NetworkZone") == "WAN" and str(i.get("Status", "")).startswith("Connected") and i.get("IPAddress"):
            return f"#{i['Name']}", str(i["IPAddress"])
    raise WriteError("nessuna interfaccia WAN collegata")


def _ips_policy(conf: dict, name: str, zone: str) -> str:
    names = [str(p.get("Name", "")) for p in conf.get("IPSPolicy", [])]
    for n in names:
        if len(n) >= 3 and n.lower() in name.lower():
            return n
    for n in (f"WAN TO {zone}", "generalpolicy"):
        if n in names:
            return n
    return names[0] if names else "None"


def _block_rule(conf: dict, group: str) -> str | None:
    for r in conf.get("FirewallRule", []):
        v = sec_fwconf.rule_view(r)
        if v["enabled"] and group in v["src_nets"] and v["action"] in ("Drop", "Reject"):
            return v["name"]
    return None


def _taken(conf: dict, entity: str, name: str) -> bool:
    return any(x.get("Name") == name for x in conf.get(entity, []))


def plan_publish(cfg: sys_config.Config, label: str, host: str, ports: str, sources: str = "",
                 conf: dict | None = None) -> dict:
    """Make a server of the house reachable from the Internet: its host, its service, the rule (with IPS and log,
    after Aurora's blocking rule) and the DNAT on the WAN address. `sources`: countries or addresses allowed (names of
    the firewall's objects, comma separated: "Italy, 203.0.113.7"); empty = everyone."""
    if not NAME.match(label):
        raise WriteError("nome: lettere, cifre, - _ . (max 40)")
    conf = conf if conf is not None else sec_fwconf.read(cfg)
    ip = str(ipaddress.ip_address(host.strip()))
    if not ipaddress.ip_address(ip).is_private:
        raise WriteError("si pubblica un server della casa: serve un indirizzo privato")
    zone = _zone_of(conf, ip)
    if zone == "WAN":
        raise WriteError(f"{ip} è nella rete WAN")
    wan, wan_ip = _wan(conf)
    plist = _ports(ports)
    n = PREFIX + label
    for entity in ("FirewallRule", "NATRule", "Services"):
        if _taken(conf, entity, n):
            raise WriteError(f"esiste già un {entity} «{n}»: scegli un altro nome o ritira la pubblicazione")
    host_obj = next((h["Name"] for h in conf.get("IPHost", []) if h.get("IPAddress") == ip and h.get("HostType") == "IP"
                     and not str(h.get("Name", "")).startswith("aurora-block-")), None)
    srcs = [s.strip() for s in sources.split(",") if s.strip()]
    for s in srcs:                                        # an address is made a host; a name must exist (a country…)
        try:
            ipaddress.ip_address(s)
        except ValueError:
            if not s or len(s) > 60:
                raise WriteError(f"origine non valida: {s!r}") from None
    steps = []
    if not host_obj:
        host_obj = f"aurora-host-{ip}"
        steps.append(host_step(host_obj, ip))
    src_objs = []
    for s in srcs:
        try:
            ipaddress.ip_address(s)
            steps.append(host_step(f"aurora-src-{s}", s))
            src_objs.append(f"aurora-src-{s}")
        except ValueError:
            src_objs.append(s)
    ips = _ips_policy(conf, label, zone)
    steps.append(service_step(n, plist))
    group = str(cfg["AURORA_FIREWALL_BLOCK_GROUP"])
    after = _block_rule(conf, group)
    desc = f"Aurora: {label} pubblicato ({', '.join(f'{p} {q}' for p, q in plist)} → {ip})"
    steps.append(rule_step(n, desc, ["WAN"], [zone], [n], src_objs, [wan], "Accept", ips, after))
    steps.append(dnat_step(n, desc, wan, host_obj, n, src_objs))
    notes = []
    if ipaddress.ip_address(wan_ip).is_private:           # a router in front (double NAT): it must forward the ports too
        notes.append(f"Il firewall è dietro un altro router (WAN {wan_ip}, indirizzo privato): quel router deve inoltrare "
                     f"{', '.join(q for _, q in plist)} a {wan_ip} (o avere il firewall in DMZ).")
    if not after:
        notes.append("Nessuna regola applica il gruppo dei blocchi: gli indirizzi bloccati da Aurora potrebbero entrare.")
    if not srcs:
        notes.append("Aperto a tutta Internet: con un filtro per paese (es. «Italy») il servizio è meno esposto.")
    return {"kind": "publish", "title": f"Pubblicare {label}: {', '.join(f'{p} {q}' for p, q in plist)} → {ip}",
            "why": f"richiesta del proprietario; zona {zone}, IPS «{ips}», log attivo" + (f", dopo «{after}»" if after else ""),
            "steps": steps, "notes": notes, "check": [("FirewallRule", n), ("NATRule", n)]}


def plan_unpublish(cfg: sys_config.Config, label: str, conf: dict | None = None) -> dict:
    conf = conf if conf is not None else sec_fwconf.read(cfg)
    n = PREFIX + label if not label.startswith(PREFIX) else label
    steps = [step(e, n, _remove(e, n), "", f"togliere {e} {n}") for e in ("NATRule", "FirewallRule", "Services")
             if _taken(conf, e, n)]
    if not steps:
        raise WriteError(f"nessuna pubblicazione «{n}» di Aurora")
    return {"kind": "unpublish", "title": f"Ritirare la pubblicazione {n}", "why": "richiesta del proprietario",
            "steps": steps, "notes": ["Chiusa da Internet: il servizio resta raggiungibile in casa."], "check": []}


def plan_quarantine(cfg: sys_config.Config, ip: str, reason: str, conf: dict | None = None) -> dict:
    """Isolate a device of the house: its host in the quarantine group; the group's Drop rule at the top is made the
    first time. The firewall stops what crosses it (Internet, other networks); two devices on the same switch still
    talk to each other — said in the plan."""
    conf = conf if conf is not None else sec_fwconf.read(cfg)
    ip = sec_fwapi.blockable(cfg, ip)
    if not ipaddress.ip_address(ip).is_private:
        raise WriteError("la quarantena è per i dispositivi della casa; un indirizzo di Internet si blocca")
    group = str(cfg["AURORA_QUARANTINE_GROUP"])
    rule = PREFIX + "Quarantine"
    steps = []
    if not _taken(conf, "IPHostGroup", group):
        body = _x("Name", group) + "<Description>Aurora: dispositivi in quarantena</Description><IPFamily>IPv4</IPFamily>"
        steps.append(step("IPHostGroup", group, _set("IPHostGroup", body), _remove("IPHostGroup", group), f"il gruppo {group}"))
    host = f"aurora-quarantine-{ip}"
    if _taken(conf, "IPHost", host):
        raise WriteError(f"{ip} è già in quarantena")
    steps.append(host_step(host, ip, [group]))
    if not _taken(conf, "FirewallRule", rule):
        steps.append(rule_step(rule, "Aurora: i dispositivi in quarantena non escono", [], [], [], [group], [], "Drop", "None", None))
    return {"kind": "quarantine", "title": f"Quarantena di {ip}", "why": reason[:300], "steps": steps,
            "notes": ["Il firewall ferma solo il traffico che lo attraversa (Internet, altre reti): due dispositivi "
                      "sullo stesso switch possono ancora parlarsi.",
                      "Se il dispositivo prende un altro indirizzo dal DHCP esce dalla quarantena: meglio una "
                      "prenotazione DHCP."], "check": [("IPHost", host)]}


def plan_release(cfg: sys_config.Config, ip: str, conf: dict | None = None) -> dict:
    conf = conf if conf is not None else sec_fwconf.read(cfg)
    host = f"aurora-quarantine-{ip.strip()}"
    if not _taken(conf, "IPHost", host):
        raise WriteError(f"{ip} non è in quarantena")
    body = (_x("Name", host) + "<IPFamily>IPv4</IPFamily><HostType>IP</HostType>" + _x("IPAddress", ip.strip())
            + "<HostGroupList></HostGroupList>")
    return {"kind": "release", "title": f"Fine della quarantena di {ip}", "why": "richiesta del proprietario",
            "steps": [step("IPHost", host, _set("IPHost", body, "update"), "", "fuori dal gruppo"),
                      step("IPHost", host, _remove("IPHost", host), "", "host rimosso")], "notes": [], "check": []}


def raw_rule(cfg: sys_config.Config, name: str) -> str:
    text = sec_fwapi.request(cfg, "<Get><FirewallRule/></Get>")
    m = re.search(rf"<FirewallRule[^>]*>(?:(?!</FirewallRule>).)*?<Name>{re.escape(escape(name))}</Name>.*?</FirewallRule>", text, re.S)
    if not m:
        raise WriteError(f"nessuna regola «{name}»")
    return re.sub(r"<FirewallRule[^>]*>", "<FirewallRule>", m.group(0), count=1)


def plan_harden(cfg: sys_config.Config, rule: str, ips: str, log: bool = True) -> dict:
    """An IPS policy (and the log) on one of the owner's rules — the fix the audit proposes for a published service.
    The rule's XML before is the undo."""
    before = raw_rule(cfg, rule)
    if "<NetworkPolicy>" not in before:
        raise WriteError("solo regole di rete")
    after = re.sub(r"<IntrusionPrevention>[^<]*</IntrusionPrevention>", f"<IntrusionPrevention>{escape(ips)}</IntrusionPrevention>", before)
    if "<IntrusionPrevention>" not in after:
        after = after.replace("</NetworkPolicy>", f"<IntrusionPrevention>{escape(ips)}</IntrusionPrevention></NetworkPolicy>")
    if log:
        after = re.sub(r"<LogTraffic>[^<]*</LogTraffic>", "<LogTraffic>Enable</LogTraffic>", after)
    if after == before:
        raise WriteError("la regola ha già questa protezione")
    inner_after = after[len("<FirewallRule>"):-len("</FirewallRule>")]
    inner_before = before[len("<FirewallRule>"):-len("</FirewallRule>")]
    return {"kind": "harden", "title": f"Proteggere la regola «{rule}»: IPS «{ips}»" + (" e log" if log else ""),
            "why": "rilievo dell'audit: servizio pubblicato senza IPS",
            "steps": [step("FirewallRule", rule, _set("FirewallRule", inner_after, "update"),
                           _set("FirewallRule", inner_before, "update"), f"IPS «{ips}» sulla regola {rule}", owner_object=True)],
            "notes": [], "check": [("FirewallRule", rule)], "expect": {"IntrusionPrevention": ips}}


# ---- apply, confirm, undo -----------------------------------------------------------------------------------------
def propose(cfg: sys_config.Config, plan: dict) -> dict:
    """A planned change recorded, not applied: the id the owner approves."""
    change = {"id": uuid.uuid4().hex[:8], "status": "planned", "created": time.time(), **plan}
    change["check"] = [list(c) for c in plan.get("check", [])]
    _keep(cfg, change)
    return change


def _status_of(text: str, entity: str) -> tuple[str, str]:
    m = re.search(rf"<{entity}[^>]*>\s*<Status code=\"(\d+)\">(.*?)</Status>", text, re.S)
    return (m.group(1), m.group(2).strip()) if m else ("", "")


def _run(cfg: sys_config.Config, xml: str, entity: str) -> str:
    code, msg = _status_of(sec_fwapi.request(cfg, xml), entity)
    if code != "200":
        raise WriteError(f"{entity}: il firewall ha risposto {code or '?'} {msg[:200]}")
    return msg


def _allowed(st: dict) -> None:
    """Only Aurora's own objects are added or removed; an owner's object only through harden (with its undo)."""
    if st["owner_object"]:
        return
    if not (st["name"].startswith(PREFIX) or st["name"].lower().startswith("aurora-")):
        raise WriteError(f"«{st['name']}» non è un oggetto di Aurora: non lo tocco")


def _undo(cfg: sys_config.Config, done: list[dict]) -> list[str]:
    errors = []
    for st in reversed(done):
        if st.get("undo"):
            try:
                _run(cfg, st["undo"], st["entity"])
            except (WriteError, sec_fwapi.FirewallAPIError) as e:
                errors.append(f"{st['entity']} {st['name']}: {e}")
    return errors


def confirm(cfg: sys_config.Config, change: dict, wait: float | None = None) -> list[str]:
    """The firewall still answers and each object reads back (and, for harden, with the expected value): [] or the
    problems found within AURORA_FIREWALL_CONFIRM_S."""
    deadline = time.time() + float(wait if wait is not None else cfg["AURORA_FIREWALL_CONFIRM_S"])
    problems = ["nessuna verifica"]
    while time.time() < deadline:
        problems = []
        try:
            for entity, name in change.get("check", []):
                items = [x for x in sec_fwconf.get(cfg, entity) if x.get("Name") == name]
                if not items:
                    problems.append(f"{entity} {name} non si rilegge")
                elif change.get("expect") and entity == "FirewallRule":
                    pol = items[0].get("NetworkPolicy") or {}
                    problems += [f"{k} = {pol.get(k)!r}" for k, v in change["expect"].items() if pol.get(k) != v]
        except (sec_fwapi.FirewallAPIError, sec_fwconf.ConfigError) as e:
            problems.append(f"il firewall non risponde: {e}")
        if not problems:
            return []
        time.sleep(3)
    return problems


def apply(cfg: sys_config.Config, change_id: str) -> dict:
    """Apply a planned change (the owner approved it): step by step, undone at the first failure or when the
    confirmation fails. Returns the change with its status: applied | undone | failed (undo incomplete)."""
    if not cfg["AURORA_FIREWALL_WRITE"]:
        raise WriteError("modifiche al firewall spente: attiva «AURORA_FIREWALL_WRITE» nella scheda Sicurezza")
    change = get_change(cfg, change_id)
    if change["status"] != "planned":
        raise WriteError(f"la modifica {change_id} è già {change['status']}")
    log = sys_log.get_logger("security")
    for st in change["steps"]:
        _allowed(st)
    done, error = [], ""
    for st in change["steps"]:
        try:
            _run(cfg, st["xml"], st["entity"])
            done.append(st)
        except (WriteError, sec_fwapi.FirewallAPIError) as e:
            error = f"{st['why']}: {e}"
            break
    problems = [error] if error else confirm(cfg, change)
    if problems:
        undo_errors = _undo(cfg, done)
        change.update(status="failed" if undo_errors else "undone", problems=problems, undo_errors=undo_errors,
                      applied=time.time())
        log.warning("audit: firewall change %s undone: %s %s", change_id, problems, undo_errors)
    else:
        change.update(status="applied", applied=time.time(), problems=[])
        log.info("audit: firewall change %s applied: %s", change_id, change["title"])
    sys_log.trace("security", "firewall.change", {"id": change_id, "status": change["status"], "title": change["title"]})
    _keep(cfg, change)
    return change


def revert(cfg: sys_config.Config, change_id: str) -> dict:
    """Undo an applied change (its steps' undo, last first)."""
    if not cfg["AURORA_FIREWALL_WRITE"]:
        raise WriteError("modifiche al firewall spente")
    change = get_change(cfg, change_id)
    if change["status"] != "applied":
        raise WriteError(f"la modifica {change_id} è {change['status']}: non c'è nulla da annullare")
    if not any(st.get("undo") for st in change["steps"]):
        raise WriteError("questa modifica non ha un annullamento (è già un ritiro)")
    errors = _undo(cfg, change["steps"])
    change.update(status="reverted" if not errors else "failed", reverted=time.time(), undo_errors=errors)
    _keep(cfg, change)
    sys_log.get_logger("security").info("audit: firewall change %s reverted %s", change_id, errors or "")
    return change


def text(change: dict) -> str:
    lines = [f"🧱 **{change['title']}** (modifica `{change['id']}`, {change['status']})", f"Perché: {change.get('why', '')}"]
    lines += [f"{i}. {st['why']}" for i, st in enumerate(change["steps"], 1)]
    lines += [f"⚠️ {n}" for n in change.get("notes", [])]
    if change.get("problems"):
        lines.append("Problemi: " + "; ".join(change["problems"]))
    if change.get("undo_errors"):
        lines.append("❌ Annullamento incompleto: " + "; ".join(change["undo_errors"]))
    return "\n".join(lines)

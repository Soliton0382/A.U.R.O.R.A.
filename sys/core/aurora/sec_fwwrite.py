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
The objects' XML is the driver's (aurora/fw_drivers, ROADMAP 108): this module plans, checks and undoes.
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

from . import sec_fwapi, sec_fwconf, sys_config, sys_log
from .fw_drivers import driver
from .sys_lang import say as _t   # each sentence in the reader's language (C526)

D = driver()                                    # the objects of a plan, in the default dialect (step 1 of ROADMAP 108)

_lock = threading.Lock()
PREFIX = "Aurora-"
NAME = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")


class WriteError(Exception):
    pass


def target(cfg: sys_config.Config, fid: str = "main") -> sys_config.Config:
    """The configuration of the firewall a change is for: «main» the settings' one, else one of 🔌 Firewall."""
    if fid in ("", "main"):
        return cfg
    from . import sec_firewalls
    item = next((x for x in sec_firewalls.items(cfg) if x["id"] == fid), None)
    if item is None:
        raise WriteError(_t(f"nessun firewall «{fid}»", f"no firewall «{fid}»"))
    return sec_firewalls.view(cfg, item)


def _neutral(cfg: sys_config.Config) -> bool:
    """A dialect whose plans are the neutral operations (sec_fwops), not the first dialect's XML."""
    return str(cfg["AURORA_FIREWALL_API_KIND"]) != "sophos"


def _ops(make):
    from . import sec_fwops
    try:
        return make(sec_fwops)
    except sec_fwops.OpsError as e:
        raise WriteError(str(e)) from None


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


# ---- one step -------------------------------------------------------------------------------------------------------
_x, _set, _remove = D.x, D.set_, D.remove


def step(entity: str, name: str, xml: str, undo: str, why: str, owner_object: bool = False) -> dict:
    return {"entity": entity, "name": name, "xml": xml, "undo": undo, "why": why, "owner_object": owner_object}


def host_step(name: str, ip: str, groups: list[str] | None = None) -> dict:
    return step("IPHost", name, _set("IPHost", D.host(name, ip, groups)), _remove("IPHost", name), f"l'host {name} = {ip}")


def service_step(name: str, ports: list[tuple[str, str]]) -> dict:
    return step("Services", name, _set("Services", D.service(name, ports)), _remove("Services", name),
                f"il servizio {name}: " + ", ".join(f"{proto} {p}" for proto, p in ports))


def rule_step(name: str, desc: str, src_zones: list[str], dst_zones: list[str], services: list[str],
              src_nets: list[str], dst_nets: list[str], action: str, ips: str, after: str | None) -> dict:
    body = D.rule(name, desc, src_zones, dst_zones, services, src_nets, dst_nets, action, ips, after)
    return step("FirewallRule", name, _set("FirewallRule", body), _remove("FirewallRule", name), f"la regola {name}: {desc}")


def dnat_step(name: str, desc: str, wan: str, host: str, service: str, sources: list[str]) -> dict:
    body = D.dnat(name, desc, wan, host, service, sources)
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
            raise WriteError(_t(f"porta non valida: {part!r} (es. 443, 443/tcp, 8000-8010/udp)", f"not a valid port: {part!r} (e.g. 443, 443/tcp, 8000-8010/udp)"))
        out.append(((m[3] or "tcp").upper(), m[1] + (f":{m[2]}" if m[2] else "")))
    if not out:
        raise WriteError(_t("nessuna porta", "no port"))
    return out


def _zone_of(conf: dict, ip: str) -> str:
    a = ipaddress.ip_address(ip)
    for i in conf.get("Interface", []):
        if i.get("IPAddress") and i.get("Netmask") and a in ipaddress.ip_network(f"{i['IPAddress']}/{i['Netmask']}", strict=False):
            return str(i.get("NetworkZone") or "LAN")
    raise WriteError(_t(f"{ip} non è in nessuna rete del firewall", f"{ip} is in none of the firewall's networks"))


def _wan(conf: dict) -> tuple[str, str]:
    """("#Port7", "192.168.1.2"): the connected WAN interface, as the DNAT wizard names its address."""
    for i in conf.get("Interface", []):
        if i.get("NetworkZone") == "WAN" and str(i.get("Status", "")).startswith("Connected") and i.get("IPAddress"):
            return f"#{i['Name']}", str(i["IPAddress"])
    raise WriteError(_t("nessuna interfaccia WAN collegata", "no WAN interface connected"))


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
    ip = str(ipaddress.ip_address(host.strip()))
    if not ipaddress.ip_address(ip).is_private:
        raise WriteError(_t("si pubblica un server della casa: serve un indirizzo privato", "a server of the house is published: a private address is needed"))
    if _neutral(cfg):
        return _ops(lambda o: o.plan_publish(cfg, label, ip, _ports(ports), [s.strip() for s in sources.split(",") if s.strip()]))
    conf = conf if conf is not None else sec_fwconf.read(cfg)
    zone = _zone_of(conf, ip)
    if zone == "WAN":
        raise WriteError(_t(f"{ip} è nella rete WAN", f"{ip} is in the WAN network"))
    wan, wan_ip = _wan(conf)
    plist = _ports(ports)
    n = PREFIX + label
    for entity in ("FirewallRule", "NATRule", "Services"):
        if _taken(conf, entity, n):
            raise WriteError(_t(f"esiste già un {entity} «{n}»: scegli un altro nome o ritira la pubblicazione", f"a {entity} «{n}» exists already: choose another name or withdraw the publication"))
    host_obj = next((h["Name"] for h in conf.get("IPHost", []) if h.get("IPAddress") == ip and h.get("HostType") == "IP"
                     and not str(h.get("Name", "")).startswith("aurora-block-")), None)
    srcs = [s.strip() for s in sources.split(",") if s.strip()]
    for s in srcs:                                        # an address is made a host; a name must exist (a country…)
        try:
            ipaddress.ip_address(s)
        except ValueError:
            if not s or len(s) > 60:
                raise WriteError(_t(f"origine non valida: {s!r}", f"not a valid source: {s!r}")) from None
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
        notes.append(_t(f"Il firewall è dietro un altro router (WAN {wan_ip}, indirizzo privato): quel router deve inoltrare "
                     f"{', '.join(q for _, q in plist)} a {wan_ip} (o avere il firewall in DMZ).", f"The firewall is behind another router (WAN {wan_ip}, a private address): that router must forward "
                     f"{', '.join(q for _, q in plist)} to {wan_ip} (or have the firewall in its DMZ)."))
    if not after:
        notes.append(_t("Nessuna regola applica il gruppo dei blocchi: gli indirizzi bloccati da Aurora potrebbero entrare.", "No rule applies the blocking group: the addresses Aurora blocked could come in."))
    if not srcs:
        notes.append(_t("Aperto a tutta Internet: con un filtro per paese (es. «Italy») il servizio è meno esposto.", "Open to the whole Internet: with a country filter (e.g. «Italy») the service is less exposed."))
    return {"kind": "publish", "title": _t(f"Pubblicare {label}: {', '.join(f'{p} {q}' for p, q in plist)} → {ip}", f"Publish {label}: {', '.join(f'{p} {q}' for p, q in plist)} → {ip}"),
            "why": _t(f"richiesta del proprietario; zona {zone}, IPS «{ips}», log attivo" + (f", dopo «{after}»" if after else ""), f"the owner's request; zone {zone}, IPS «{ips}», log on" + (f", after «{after}»" if after else "")),
            "steps": steps, "notes": notes, "check": [("FirewallRule", n), ("NATRule", n)]}


def plan_unpublish(cfg: sys_config.Config, label: str, conf: dict | None = None) -> dict:
    if _neutral(cfg):
        return _ops(lambda o: o.plan_unpublish(cfg, label))
    conf = conf if conf is not None else sec_fwconf.read(cfg)
    n = PREFIX + label if not label.startswith(PREFIX) else label
    steps = [step(e, n, _remove(e, n), "", f"togliere {e} {n}") for e in ("NATRule", "FirewallRule", "Services")
             if _taken(conf, e, n)]
    if not steps:
        raise WriteError(_t(f"nessuna pubblicazione «{n}» di Aurora", f"no publication «{n}» of Aurora's"))
    return {"kind": "unpublish", "title": _t(f"Ritirare la pubblicazione {n}", f"Withdraw the publication {n}"), "why": _t("richiesta del proprietario", "the owner's request"),
            "steps": steps, "notes": [_t("Chiusa da Internet: il servizio resta raggiungibile in casa.", "Closed from the Internet: the service can still be reached at home.")], "check": []}


def plan_quarantine(cfg: sys_config.Config, ip: str, reason: str, conf: dict | None = None) -> dict:
    """Isolate a device of the house: its host in the quarantine group; the group's Drop rule at the top is made the
    first time. The firewall stops what crosses it (Internet, other networks); two devices on the same switch still
    talk to each other — said in the plan."""
    ip = sec_fwapi.blockable(cfg, ip)
    if not ipaddress.ip_address(ip).is_private:
        raise WriteError(_t("la quarantena è per i dispositivi della casa; un indirizzo di Internet si blocca", "the quarantine is for the devices of the house; an Internet address is blocked"))
    if _neutral(cfg):
        return _ops(lambda o: o.plan_quarantine(cfg, ip, reason))
    conf = conf if conf is not None else sec_fwconf.read(cfg)
    group = str(cfg["AURORA_QUARANTINE_GROUP"])
    rule = PREFIX + "Quarantine"
    steps = []
    if not _taken(conf, "IPHostGroup", group):
        body = D.group(group, "Aurora: dispositivi in quarantena")
        steps.append(step("IPHostGroup", group, _set("IPHostGroup", body), _remove("IPHostGroup", group), f"il gruppo {group}"))
    host = f"aurora-quarantine-{ip}"
    if _taken(conf, "IPHost", host):
        raise WriteError(_t(f"{ip} è già in quarantena", f"{ip} is already in quarantine"))
    steps.append(host_step(host, ip, [group]))
    if not _taken(conf, "FirewallRule", rule):
        steps.append(rule_step(rule, "Aurora: i dispositivi in quarantena non escono", [], [], [], [group], [], "Drop", "None", None))
    return {"kind": "quarantine", "title": _t(f"Quarantena di {ip}", f"Quarantine of {ip}"), "why": reason[:300], "steps": steps,
            "notes": [_t("Il firewall ferma solo il traffico che lo attraversa (Internet, altre reti): due dispositivi "
                      "sullo stesso switch possono ancora parlarsi.", "The firewall stops only the traffic that crosses it (Internet, other networks): two devices "
                      "on the same switch can still talk to each other."),
                      _t("Se il dispositivo prende un altro indirizzo dal DHCP esce dalla quarantena: meglio una "
                      "prenotazione DHCP.", "If the device gets another address from the DHCP it leaves the quarantine: better a "
                      "DHCP reservation.")], "check": [("IPHost", host)]}


def plan_release(cfg: sys_config.Config, ip: str, conf: dict | None = None) -> dict:
    if _neutral(cfg):
        return _ops(lambda o: o.plan_release(cfg, ip.strip()))
    conf = conf if conf is not None else sec_fwconf.read(cfg)
    host = f"aurora-quarantine-{ip.strip()}"
    if not _taken(conf, "IPHost", host):
        raise WriteError(_t(f"{ip} non è in quarantena", f"{ip} is not in quarantine"))
    body = D.release(host, ip.strip())
    return {"kind": "release", "title": _t(f"Fine della quarantena di {ip}", f"End of the quarantine of {ip}"), "why": _t("richiesta del proprietario", "the owner's request"),
            "steps": [step("IPHost", host, _set("IPHost", body, "update"), "", _t("fuori dal gruppo", "out of the group")),
                      step("IPHost", host, _remove("IPHost", host), "", _t("host rimosso", "host removed"))], "notes": [], "check": []}


def raw_rule(cfg: sys_config.Config, name: str) -> str:
    found = D.find_rule(sec_fwapi.request(cfg, D.get_rules()), name)
    if not found:
        raise WriteError(_t(f"nessuna regola «{name}»", f"no rule «{name}»"))
    return found


def plan_harden(cfg: sys_config.Config, rule: str, ips: str, log: bool = True) -> dict:
    """An IPS policy (and the log) on one of the owner's rules — the fix the audit proposes for a published service.
    The rule's XML before is the undo."""
    if _neutral(cfg):
        raise WriteError(_t("su questo firewall una regola non ha una sua policy IPS: si accende l'IPS del firewall "
                         "(Suricata), e il log della regola dalla sua pagina", "on this firewall a rule has no IPS policy of its own: the firewall's IPS is turned on "
                         "(Suricata), and the rule's log from its page"))
    before = raw_rule(cfg, rule)
    if not D.network_rule(before):
        raise WriteError(_t("solo regole di rete", "network rules only"))
    after = D.harden(before, ips, log)
    if after == before:
        raise WriteError(_t("la regola ha già questa protezione", "the rule has this protection already"))
    inner_after, inner_before = D.inner(after), D.inner(before)
    return {"kind": "harden", "title": _t(f"Proteggere la regola «{rule}»: IPS «{ips}»" + (" e log" if log else ""), f"Protect the rule «{rule}»: IPS «{ips}»" + (" and log" if log else "")),
            "why": _t("rilievo dell'audit: servizio pubblicato senza IPS", "a finding of the audit: a service published without IPS"),
            "steps": [step("FirewallRule", rule, _set("FirewallRule", inner_after, "update"),
                           _set("FirewallRule", inner_before, "update"), _t(f"IPS «{ips}» sulla regola {rule}", f"IPS «{ips}» on the rule {rule}"), owner_object=True)],
            "notes": [], "check": [("FirewallRule", rule)], "expect": {"IntrusionPrevention": ips}}


# ---- apply, confirm, undo -----------------------------------------------------------------------------------------
def propose(cfg: sys_config.Config, plan: dict, fw: str = "main") -> dict:
    """A planned change recorded, not applied: the id the owner approves; `fw` the firewall it is for."""
    change = {"id": uuid.uuid4().hex[:8], "status": "planned", "created": time.time(), "fw": fw, **plan}
    change["check"] = [list(c) for c in plan.get("check", [])]
    _keep(cfg, change)
    return change


def _run(cfg: sys_config.Config, xml: str, entity: str) -> str:
    d = driver(cfg)                                    # the dialect of the firewall the change is for
    code, msg = d.step_status(sec_fwapi.request(cfg, xml), entity)
    if code != "200":
        hint = _t(d.READ_ONLY_HINT, getattr(d, "READ_ONLY_HINT_EN", d.READ_ONLY_HINT)) if d.read_only(code, msg) else ""
        raise WriteError(_t(f"{entity}: il firewall ha risposto {code or '?'} {msg[:200]}{hint}", f"{entity}: the firewall answered {code or '?'} {msg[:200]}{hint}"))
    return msg


def _allowed(st: dict) -> None:
    """Only Aurora's own objects are added or removed; an owner's object only through harden (with its undo)."""
    if st["owner_object"]:
        return
    if not (st["name"].startswith(PREFIX) or st["name"].lower().startswith(("aurora-", "aurora_"))):
        raise WriteError(_t(f"«{st['name']}» non è un oggetto di Aurora: non lo tocco", f"«{st['name']}» is not an object of Aurora's: I do not touch it"))


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
    problems = [_t("nessuna verifica", "no check")]
    while time.time() < deadline:
        problems = []
        try:
            for entity, name in change.get("check", []):
                if _neutral(cfg):
                    from . import sec_fwops
                    if not sec_fwops.exists(cfg, entity, name):
                        problems.append(_t(f"{entity} {name} non si rilegge", f"{entity} {name} does not read back"))
                    continue
                items = [x for x in sec_fwconf.get(cfg, entity) if x.get("Name") == name]
                if not items:
                    problems.append(_t(f"{entity} {name} non si rilegge", f"{entity} {name} does not read back"))
                elif change.get("expect") and entity == "FirewallRule":
                    pol = items[0].get("NetworkPolicy") or {}
                    problems += [f"{k} = {pol.get(k)!r}" for k, v in change["expect"].items() if pol.get(k) != v]
        except (sec_fwapi.FirewallAPIError, sec_fwconf.ConfigError) as e:
            problems.append(_t(f"il firewall non risponde: {e}", f"the firewall does not answer: {e}"))
        if not problems:
            return []
        time.sleep(3)
    return problems


def apply(cfg: sys_config.Config, change_id: str) -> dict:
    """Apply a planned change (the owner approved it): step by step, undone at the first failure or when the
    confirmation fails. Returns the change with its status: applied | undone | failed (undo incomplete)."""
    if not cfg["AURORA_FIREWALL_WRITE"]:
        raise WriteError(_t("modifiche al firewall spente: attiva «AURORA_FIREWALL_WRITE» nella scheda Sicurezza", "changes to the firewall are off: turn on «AURORA_FIREWALL_WRITE» in the Security card"))
    change = get_change(cfg, change_id)
    if change["status"] != "planned":
        raise WriteError(_t(f"la modifica {change_id} è già {change['status']}", f"the change {change_id} is already {change['status']}"))
    record, cfg = cfg, target(cfg, change.get("fw", "main"))   # the record stays here; the steps go to that firewall
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
    _keep(record, change)
    return change


def revert(cfg: sys_config.Config, change_id: str) -> dict:
    """Undo an applied change (its steps' undo, last first)."""
    if not cfg["AURORA_FIREWALL_WRITE"]:
        raise WriteError(_t("modifiche al firewall spente", "changes to the firewall are off"))
    change = get_change(cfg, change_id)
    if change["status"] != "applied":
        raise WriteError(_t(f"la modifica {change_id} è {change['status']}: non c'è nulla da annullare", f"the change {change_id} is {change['status']}: there is nothing to undo"))
    if not any(st.get("undo") for st in change["steps"]):
        raise WriteError(_t("questa modifica non ha un annullamento (è già un ritiro)", "this change has no undo (it is a withdrawal already)"))
    errors = _undo(target(cfg, change.get("fw", "main")), change["steps"])
    change.update(status="reverted" if not errors else "failed", reverted=time.time(), undo_errors=errors)
    _keep(cfg, change)
    sys_log.get_logger("security").info("audit: firewall change %s reverted %s", change_id, errors or "")
    return change


def discard(cfg: sys_config.Config, change_id: str) -> dict:
    """A planned change the owner does not want: kept in the record as discarded, never applied."""
    change = get_change(cfg, change_id)
    if change["status"] != "planned":
        raise WriteError(_t(f"la modifica {change_id} è {change['status']}: si scarta solo un piano", f"the change {change_id} is {change['status']}: only a plan is discarded"))
    change.update(status="discarded", discarded=time.time())
    _keep(cfg, change)
    return change


def text(change: dict) -> str:
    lines = [_t(f"🧱 **{change['title']}** (modifica `{change['id']}`, {change['status']})", f"🧱 **{change['title']}** (change `{change['id']}`, {change['status']})"), _t(f"Perché: {change.get('why', '')}", f"Why: {change.get('why', '')}")]
    lines += [f"{i}. {st['why']}" for i, st in enumerate(change["steps"], 1)]
    lines += [f"⚠️ {n}" for n in change.get("notes", [])]
    if change.get("problems"):
        lines.append(_t("Problemi: ", "Problems: ") + "; ".join(change["problems"]))
    if change.get("undo_errors"):
        lines.append(_t("❌ Annullamento incompleto: ", "❌ Undo not complete: ") + "; ".join(change["undo_errors"]))
    return "\n".join(lines)

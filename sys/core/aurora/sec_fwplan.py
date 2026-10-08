# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Any change on the firewall, asked in words (owner, 2026-10-08: «sappiamo entrambi che ora Aurora può fare tutto sulla
configurazione del firewall: un field dove uno scrive cosa vuole… tipo una regola che nega il traffico verso l'esterno
per ogni porta tranne la 443, o metti in black list tutti gli IP esteri tranne l'Italia… lei propone e io approvo»).

The local model (the configuration never leaves the machine) gets the request, the firewall's configuration in short
(the rules in their order, NAT, services, hosts, groups, zones, interfaces, IPS policies, the country names), the
passages of the SFOS manual and API that match, and writes the steps as XML of the API. The code then checks every
step before the owner sees it — a step that fails a check goes back to the model once, with the reason:
  - entities: only ALLOWED (rules, NAT, services, hosts and groups, policies); never the firewall's own access
    (administration, API, zones' appliance access, interfaces, authentication): a mistake there locks the owner out;
  - XML: one element, the entity's own, no DOCTYPE/ENTITY, a <Name> equal to the step's;
  - add: a new name starting with "Aurora-"; update: an object that exists — its XML before is read and kept as the
    undo; remove: only Aurora's objects, its XML before kept to put it back.
The change is then an ordinary sec_fwwrite change: planned, applied only by the owner, read back, undone on failure.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from . import sec_fwapi, sec_fwconf, sec_fwdocs, sec_fwwrite, sys_config

ALLOWED = ("FirewallRule", "NATRule", "Services", "ServiceGroup", "IPHost", "IPHostGroup", "FQDNHost", "FQDNHostGroup",
           "MACHost", "IPSPolicy", "WebFilterPolicy", "ApplicationFilterPolicy")
NEVER = ("AdminSettings", "LocalServiceACL", "Zone", "Interface", "APIConfiguration", "AuthenticationServer", "User",
         "AdminProfile", "VLAN", "DNS", "SyslogServers")
SYS = """You plan changes on a Sophos Firewall (SFOS 22.0) for its owner, through its XML API. Answer with ONE JSON
object and nothing else:
{"title": "<short, in Italian>", "why": "<what the change does and its effect, in Italian, 1-3 sentences>",
 "steps": [{"op": "add|update|remove", "entity": "<API entity>", "name": "<the object's Name>",
            "xml": "<the whole element, e.g. <FirewallRule>...</FirewallRule>; empty for remove>",
            "why": "<this step, in Italian>"}],
 "notes": ["<risks or things the owner must know, in Italian>"],
 "questions": ["<only if the request cannot be done without an answer: then steps is empty>"]}
Rules:
- Entities allowed: %ALLOWED%. Never touch the firewall's own access (administration, API, zones, interfaces, users,
  authentication, DNS, syslog): if the request needs it, steps empty and say so in notes.
- A new object's Name starts with "Aurora-" (hosts may be "aurora-"); max 60 characters, no comma.
- Follow the API's sample XML below and the shape of the owner's own objects; IPFamily IPv4; Status Enable.
- Firewall rules are evaluated top-down: place a new rule with <Position>top</Position>, or after/before a named
  rule (<Position>after</Position><After><Name>…</Name></After>), so that it takes effect where the request means.
  A blocking rule must come before the Accept rules it overrides; never above Aurora's own blocking rule %BLOCKRULE%
  unless asked.
- Never block this machine (%AURORA%) from reaching the firewall (%FIREWALL%), nor the owner's administration from
  the LAN: if the request would, say so in notes.
- Use the names that exist (services, hosts, zones, countries listed below); make a new Services/ServiceGroup/
  IPHost/IPHostGroup only when none fits, as an earlier step.
- "Everything except X": use the rule's <Exclusions> (services or networks) when the manual shows it, or a narrow
  Accept rule placed above a wider Drop rule.
- Countries are referenced by their name as a network (e.g. <Network>Italy</Network>).
- A network rule is <PolicyType>Network</PolicyType> with <NetworkPolicy> (like the owner's rules), never <UserPolicy>.
- "Any" is a list left out: never write <Network>any</Network>, <Service>any</Service> or <Zone>Any</Zone>.
- If the request does not say the direction (traffic coming IN from the Internet, or going OUT to it) and both make
  sense — e.g. «block foreign IPs» — ask in "questions" which one, with the effect of each.
- The house's devices are in EVERY zone of type LAN (e.g. LAN and WiFi): a rule about «the devices of the house» names
  all of them as source zones.
- A blocking rule placed below an Accept rule that matches the same traffic does nothing (it is shadowed): place it
  above every such rule.
- Blocking needs no Accept rule. Never add an Accept rule from WAN unless the request asks to open something, and then
  only for named services and destinations, with an IPS policy.
- Prefer the smallest change that does what is asked. Log the new rules (<LogTraffic>Enable</LogTraffic>)."""


def _short(conf: dict) -> str:
    rules = []
    for n, raw in enumerate(conf.get("FirewallRule", []), 1):
        r = sec_fwconf.rule_view(raw)
        rules.append(f"{n}. «{r['name']}» {'ON' if r['enabled'] else 'off'} {r['action']} "
                     f"{'/'.join(r['src_zones']) or 'any'}[{', '.join(r['src_nets']) or 'any'}] → "
                     f"{'/'.join(r['dst_zones']) or 'any'}[{', '.join(r['dst_nets']) or 'any'}] "
                     f"services[{', '.join(r['services']) or 'any'}] ips={r['ips']} log={'on' if r['log'] else 'off'}")
    nat = [f"«{n.get('Name')}» {n.get('Status')} {sec_fwconf.listed(n.get('OriginalServices'), 'Service')} → "
           f"{n.get('TranslatedDestination')}" for n in conf.get("NATRule", [])]
    services = [f"{s.get('Name')}={','.join(sec_fwconf.ports(conf, s.get('Name', '')))}" for s in conf.get("Services", [])]
    hosts = [f"{h.get('Name')}={h.get('IPAddress') or h.get('StartIPAddress') or h.get('Network') or ''}"
             for h in conf.get("IPHost", []) if not str(h.get("Name", "")).startswith("aurora-block-")]
    groups = [str(g.get("Name")) for g in conf.get("IPHostGroup", [])] + [str(g.get("Name")) for g in conf.get("ServiceGroup", [])]
    ifaces = [f"{i.get('Name')} zone={i.get('NetworkZone')} {i.get('IPAddress') or ''}/{i.get('Netmask') or ''}"
              for i in conf.get("Interface", []) if i.get("IPAddress")]
    acl = conf.get("LocalServiceACL", [])
    countries = sorted(set(sec_fwconf.listed(acl[0].get("Hosts"), "Host") if acl else []) | {"Italy"})
    return "\n".join([
        "FIREWALL RULES (in order):", *rules,
        "NAT RULES:", *nat,
        "SERVICES: " + "; ".join(services),
        "IP HOSTS: " + "; ".join(hosts[:250]),
        "GROUPS: " + ", ".join(groups),
        "INTERFACES: " + "; ".join(ifaces),
        "ZONES (name and type): " + ", ".join(f"{z.get('Name')}({z.get('Type')})" for z in conf.get("Zone", [])),
        "IPS POLICIES: " + ", ".join(str(p.get("Name")) for p in conf.get("IPSPolicy", [])),
        "COUNTRY NAMES: " + ", ".join(countries)])


def _docs(cfg: sys_config.Config, request: str) -> str:
    parts = [f"[{h['kind']}] {h['title']}\n{h['text'][:1400]}" for h in sec_fwdocs.search(cfg, request, 5)]
    for e in ("FirewallRule", "NATRule", "Services", "IPHost", "IPHostGroup"):
        for s in sec_fwdocs.sample(cfg, e)[:1]:
            parts.append(f"[API sample {e}]\n{s['xml'][:2500]}")
    return "\n\n".join(parts)


def _json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object in the answer")
    return json.loads(m.group(0))


def raw_item(cfg: sys_config.Config, entity: str, name: str) -> str | None:
    """The object's XML as the firewall has it (no transactionid), or None."""
    text = sec_fwapi.request(cfg, f"<Get><{entity}/></Get>")
    m = re.search(rf"<{entity}[^>]*>(?:(?!</{entity}>).)*?<Name>{re.escape(escape(name))}</Name>.*?</{entity}>", text, re.S)
    return re.sub(rf"<{entity}[^>]*>", f"<{entity}>", m.group(0), count=1) if m else None


def renamed(steps: list[dict], conf: dict) -> list[dict]:
    """A NEW object the model named «Aurora_X» (the local model writes it so, M135) becomes «Aurora-X», in every step
    that names it. Never an object that exists: «Aurora_Block_List» is the owner's rule, not Aurora's."""
    taken = {str(x.get("Name")) for items in conf.values() if isinstance(items, list) for x in items if isinstance(x, dict)}
    names = {str(st.get("name", "")) for st in steps if st.get("op") == "add"}
    swap = {n: "Aurora-" + n[len("Aurora_"):] for n in names if n.startswith("Aurora_") and n not in taken}
    out = []
    for st in steps:
        st = dict(st)
        for old, new in swap.items():
            if st.get("name") == old:
                st["name"] = new
            st["xml"] = re.sub(rf">\s*{re.escape(old)}\s*<", f">{new}<", str(st.get("xml") or ""))
        out.append(st)
    return out


ANY = re.compile(r"<(Network|Service|Zone)>\s*any\s*</\1>", re.I)


def tidy(entity: str, xml: str) -> str:
    """What the local model writes and the API does not take, put right (M135): a network rule's <UserPolicy> is a
    <NetworkPolicy>; «any» is a list left out, not an object."""
    if entity != "FirewallRule":
        return xml
    if re.search(r"<PolicyType>\s*Network\s*</PolicyType>", xml) and "<UserPolicy>" in xml:
        xml = xml.replace("<UserPolicy>", "<NetworkPolicy>").replace("</UserPolicy>", "</NetworkPolicy>")
    xml = ANY.sub("", xml)
    for box in ("SourceNetworks", "DestinationNetworks", "Services", "SourceZones", "DestinationZones"):
        xml = re.sub(rf"<{box}>\s*</{box}>", "", xml)
    return xml


def danger(entity: str, root: ET.Element) -> str:
    """Why a rule would open the network too wide ("" = it does not): an Accept from the Internet with no named
    service or no named destination."""
    if entity != "FirewallRule":
        return ""
    pol = root.find("NetworkPolicy")
    pol = pol if pol is not None else root.find("UserPolicy")
    if pol is None or (pol.findtext("Action") or "").strip().lower() != "accept":
        return ""
    zones = [z.text or "" for z in pol.iterfind("SourceZones/Zone")]
    if "WAN" not in zones:
        return ""
    if not pol.findall("Services/Service") or not (pol.findall("DestinationNetworks/Network")
                                                     or pol.findall("DestinationZones/Zone")):
        return ("an Accept rule from WAN with no named services or no named destination opens the network to the "
                "Internet: drop it, or name the services and the destination")
    return ""


def shadowed(root: ET.Element, conf: dict) -> list[str]:
    """The owner's enabled Accept rules, above where a new Drop/Reject rule would go, that take the same traffic
    first (zones overlapping, any source, any service): the new rule would never be reached (M135)."""
    pol = root.find("NetworkPolicy")
    if pol is None or (pol.findtext("Action") or "").strip().lower() not in ("drop", "reject"):
        return []
    rules = [sec_fwconf.rule_view(r) for r in conf.get("FirewallRule", [])]
    where = (root.findtext("Position") or "top").strip().lower()
    target = (root.findtext("After/Name") if where == "after" else root.findtext("Before/Name") if where == "before" else "") or ""
    names = [r["name"] for r in rules]
    if where in ("after", "before"):
        if target not in names:
            return []                                    # after a rule of the same plan: not judged
        at = names.index(target) + (1 if where == "after" else 0)
    else:
        at = 0 if where == "top" else len(rules)
    src = {z.text for z in pol.iterfind("SourceZones/Zone")}
    dst = {z.text for z in pol.iterfind("DestinationZones/Zone")}
    meet = (lambda a, b: not a or not b or bool(a & b))
    return [r["name"] for r in rules[:at] if r["enabled"] and r["action"] == "Accept" and not r["src_nets"]
            and not r["services"] and meet(src, set(r["src_zones"])) and meet(dst, set(r["dst_zones"]))]


def check(cfg: sys_config.Config, steps: list[dict], conf: dict, reader=raw_item) -> tuple[list[dict], list[str]]:
    """The model's steps → sec_fwwrite steps, and the problems found (empty: all good)."""
    out, problems = [], []
    made: set[tuple[str, str]] = set()
    for n, st in enumerate(steps, 1):
        op, entity, name = str(st.get("op", "")), str(st.get("entity", "")), str(st.get("name", "")).strip()
        xml, why = tidy(entity, str(st.get("xml", "") or "").strip()), str(st.get("why", "") or f"{op} {entity} {name}")[:300]
        where = f"step {n} ({op} {entity} «{name}»)"
        if entity in NEVER or entity not in ALLOWED:
            problems.append(f"{where}: entity not allowed (allowed: {', '.join(ALLOWED)})")
            continue
        if op not in ("add", "update", "remove") or not name or len(name) > 60 or "," in name:
            problems.append(f"{where}: op must be add/update/remove and the name 1-60 characters without comma")
            continue
        aurora = name.startswith("Aurora-") or name.startswith("aurora-")
        if op in ("add", "update"):
            if len(xml) > 20000 or re.search(r"<!(DOCTYPE|ENTITY)", xml, re.I):
                problems.append(f"{where}: the XML is too long or has a DOCTYPE")
                continue
            try:
                root = ET.fromstring(xml)
            except ET.ParseError as e:
                problems.append(f"{where}: the XML is not well formed: {e}")
                continue
            if root.tag != entity or (root.findtext("Name") or "").strip() != name:
                problems.append(f"{where}: the XML must be one <{entity}> whose <Name> is «{name}»")
                continue
            wide = danger(entity, root)
            if wide:
                problems.append(f"{where}: {wide}")
                continue
            above = shadowed(root, conf) if entity == "FirewallRule" and op == "add" else []
            if above:
                problems.append(f"{where}: this blocking rule would be shadowed — the Accept rule(s) "
                                f"{', '.join('«' + a + '»' for a in above[:4])} above it take the same traffic first: "
                                f"place it before «{above[0]}» (or at the top)")
                continue
        exists = any(x.get("Name") == name for x in conf.get(entity, []))
        if op == "add":
            if not aurora:
                problems.append(f"{where}: a new object's name must start with «Aurora-»")
                continue
            if exists:
                problems.append(f"{where}: «{name}» exists already: use update, or another name")
                continue
            out.append(sec_fwwrite.step(entity, name, f'<Set operation="add">{xml}</Set>',
                                        f"<Remove><{entity}><Name>{escape(name)}</Name></{entity}></Remove>", why))
            made.add((entity, name))
        elif op == "update":
            before = reader(cfg, entity, name) if exists else None
            if not before:
                problems.append(f"{where}: no «{name}» on the firewall to update")
                continue
            out.append(sec_fwwrite.step(entity, name, f'<Set operation="update">{xml}</Set>',
                                        f'<Set operation="update">{before}</Set>', why, owner_object=not aurora))
            made.add((entity, name))
        else:
            if not aurora:
                problems.append(f"{where}: Aurora removes only her own objects («Aurora-…»); the owner's she can update")
                continue
            before = reader(cfg, entity, name) if exists else None
            if not before:
                problems.append(f"{where}: no «{name}» on the firewall to remove")
                continue
            out.append(sec_fwwrite.step(entity, name, f"<Remove><{entity}><Name>{escape(name)}</Name></{entity}></Remove>",
                                        f'<Set operation="add">{before}</Set>', why))
    return out, problems


def plan(cfg: sys_config.Config, request: str, model=None, conf: dict | None = None, reader=raw_item) -> dict:
    """A change planned from the owner's words (not applied); {"questions": [...]} instead when the model needs an
    answer; WriteError when two attempts did not give valid steps."""
    request = request.strip()[:2000]
    if len(request) < 8:
        raise sec_fwwrite.WriteError("scrivi cosa vuoi che venga fatto sul firewall")
    if model is None:
        from . import mdl_router
        # local: the configuration never leaves the machine — except on a cloud-only one, masked (addresses too)
        model = mdl_router.base(cfg)
    conf = conf if conf is not None else sec_fwconf.read(cfg)
    fw = re.sub(r"^https?://|[:/].*$", "", str(cfg["AURORA_FIREWALL_API_URL"]))
    own = ", ".join(sorted(a for a in sec_fwapi._own_addresses() if "." in a and not a.startswith("127.")))
    block_rule = next((sec_fwconf.rule_view(r)["name"] for r in conf.get("FirewallRule", [])
                       if str(cfg["AURORA_FIREWALL_BLOCK_GROUP"]) in sec_fwconf.rule_view(r)["src_nets"]), "(none)")
    system = (SYS.replace("%ALLOWED%", ", ".join(ALLOWED)).replace("%AURORA%", own or "?").replace("%FIREWALL%", fw)
              .replace("%BLOCKRULE%", f"«{block_rule}»"))
    user = f"REQUEST OF THE OWNER:\n{request}\n\nCONFIGURATION NOW:\n{_short(conf)}\n\nMANUAL AND API:\n{_docs(cfg, request)}"
    feedback = ""
    for _attempt in range(2):
        answer = model.complete(system, user + feedback, 4000, think=False).answer   # thinking used all 4000 tokens (M135)
        try:
            data = _json(answer)
        except ValueError as e:
            feedback = f"\n\nYOUR LAST ANSWER WAS NOT VALID JSON ({e}). Answer with the JSON object only."
            continue
        if data.get("questions") and not data.get("steps"):
            return {"questions": [str(q) for q in data["questions"]][:5], "notes": [str(n) for n in data.get("notes", [])][:5]}
        steps, problems = check(cfg, renamed(data.get("steps") or [], conf), conf, reader)
        if not problems and steps:
            return {"kind": "request", "request": request, "title": str(data.get("title") or request[:80])[:120],
                    "why": str(data.get("why") or "")[:600], "steps": steps,
                    "notes": [str(n) for n in data.get("notes", [])][:8]
                    + ["Dopo l'applicazione Aurora rilegge ogni oggetto: se il firewall non risponde più, annulla."],
                    "check": [(s["entity"], s["name"]) for s in steps if not s["xml"].startswith("<Remove>")]}
        if not steps and not problems:
            problems = ["no steps"]
        feedback = ("\n\nYOUR LAST PLAN HAD PROBLEMS — fix them and answer the whole JSON again:\n- " + "\n- ".join(problems)
                    + f"\nYOUR LAST PLAN:\n{json.dumps(data, ensure_ascii=False)[:6000]}")
    raise sec_fwwrite.WriteError("non sono riuscita a preparare un piano valido: " + feedback.strip()[:600])

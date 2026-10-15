# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Any change asked in words, for the dialects of the neutral operations (ROADMAP N8; sec_fwplan for the first
dialect): the local model gets the request, the configuration in short (sec_fwmodel, sec_netmap) and the passages of
the firewall's own guides, and writes steps of the operations its driver knows (sec_fwops). The code checks every
step before the owner sees it, and a plan with problems goes back to the model once, with them:
  - operations: put_alias, alias_add, alias_del, drop_alias, put_rule, drop_rule, put_nat, drop_nat — never the
    firewall's own access (interfaces, administration, users, the API): there is no operation for it;
  - a new object is Aurora's by its name («Aurora-…» rules and port forwards, «Aurora_…» aliases); one that exists
    and is not Aurora's is never changed or dropped;
  - what a step names must exist (an interface, an alias) or be made by an earlier step;
  - nothing opens the firewall itself to the WAN, nothing blocks this machine.
The undo of each step is its opposite (a drop has none: what Aurora dropped is said in the change)."""
from __future__ import annotations

import ipaddress
import json
import re

from . import sec_fwapi, sec_fwdocs, sec_fwmodel, sec_fwwrite, sec_netmap, sys_config

OPS = ("put_alias", "alias_add", "alias_del", "drop_alias", "put_rule", "drop_rule", "put_nat", "drop_nat")
ENTITY = {"put_alias": "alias", "alias_add": "alias", "alias_del": "alias", "drop_alias": "alias",
          "put_rule": "rule", "drop_rule": "rule", "put_nat": "nat", "drop_nat": "nat"}
UNDO = {"put_alias": "drop_alias", "put_rule": "drop_rule", "put_nat": "drop_nat", "alias_add": "alias_del",
        "alias_del": "alias_add"}
PROTOS = ("tcp", "udp", "tcp/udp", "icmp", "any", "")
PORT = re.compile(r"^\d{1,5}(:\d{1,5})?$")
SYS = """You plan changes on a %KIND% firewall for its owner. Answer with ONE JSON object and nothing else:
{"title": "<short, in Italian>", "why": "<what the change does and its effect, in Italian, 1-3 sentences>",
 "steps": [{"op": "<one of the operations>", ...its fields, "why": "<this step, in Italian>"}],
 "notes": ["<risks or things the owner must know, in Italian>"],
 "questions": ["<only if the request cannot be done without an answer: then steps is empty>"]}
Operations and their fields:
- put_alias {name, addresses: [IP or CIDR], descr}: a new list of addresses; name "Aurora_<Word>" (letters, digits, _)
- alias_add / alias_del {name, ip}: one address into / out of an alias of Aurora's
- drop_alias {name}: an alias of Aurora's taken away
- put_rule {descr, interfaces: [interface ids], floating: true|false, action: "pass"|"block", source, destination,
  port, protocol: "tcp"|"udp"|"tcp/udp"|"icmp"|"any", log: true}; descr "Aurora-<what it does>"
  source/destination: "any", an IP, a CIDR, an alias name, or an interface's network ("lan")
  port: "443" or "8000:8010" (only with tcp/udp), "" for every port
- drop_rule {descr}: a rule of Aurora's taken away
- put_nat {descr, protocol, port, target, local_port, source}: a port forward from the WAN address to target (a house
  device); it passes nothing alone: add the put_rule that lets it in (interfaces ["wan"], destination = target)
- drop_nat {descr}
Rules:
- A block rule is floating (evaluated before every interface's rules); a pass rule names its interfaces.
- Never a rule that lets the WAN reach the firewall itself (its administration): if asked, steps empty and say so.
- Never block this machine (%AURORA%) nor the firewall (%FIREWALL%).
- Use the aliases and interfaces that exist (listed below); make a new alias only as an earlier step.
- The house's devices are on every inside interface (all but WAN): a rule about «the devices of the house» names
  them all.
- If the request does not say the direction (coming IN from the Internet, or going OUT to it) and both make sense,
  ask in "questions" which one, with the effect of each.
- When the request says «Consenti solo da: …», use exactly that list as the origin (an alias of those addresses).
- Prefer the smallest change that does what is asked. Log the new rules."""


def _short(model: dict, net: dict) -> str:
    rules = [f"{n}. «{r['name']}» {'ON' if r['enabled'] else 'off'} {r['action']} {'/'.join(r['src_zones']) or 'floating'} "
             f"[{', '.join(r['src_nets']) or 'any'}] → [{', '.join(r['dst_nets']) or ('firewall' if r['to_self'] else 'any')}] "
             f"{', '.join(r['ports']) or 'every port'} log={'on' if r['log'] else 'off'}"
             for n, r in enumerate(model["rules"], 1) if not r["system"]]
    nat = [f"«{n['name']}» {'ON' if n['enabled'] else 'off'} {', '.join(n['ports'])} → {', '.join(n['target'])}" for n in model["nat"]]
    aliases = [f"{g['name']} ({len(g['hosts'])})" for g in net.get("groups", [])]
    ifaces = [f"{i.get('id')} = {i['name']} {i['ip']}/{i['netmask']}" for i in net.get("interfaces", []) if i["ip"]]
    return "\n".join(["RULES (in order, the firewall's own left out):", *rules, "PORT FORWARDS:", *nat,
                      "ALIASES: " + ", ".join(aliases), "INTERFACES (id = name address): " + "; ".join(ifaces)])


def _addr(x: str) -> bool:
    try:
        ipaddress.ip_network(x, strict=False)
        return True
    except ValueError:
        return False


def check(fw: sys_config.Config, steps: list[dict], model: dict, net: dict) -> tuple[list[dict], list[str]]:
    """The plan's steps as change steps (sec_fwwrite's record), and the problems found."""
    aliases = {g["name"] for g in net.get("groups", [])}
    ifaces = {str(i.get("id")) for i in net.get("interfaces", [])}
    rules = {r["name"]: r for r in model["rules"]}
    nats = {n["name"] for n in model["nat"]}
    own = {a for a in sec_fwapi._own_addresses() if "." in a}
    firewall = re.sub(r"^https?://|[:/].*$", "", str(fw["AURORA_FIREWALL_API_URL"]))
    out, problems = [], []
    for i, s in enumerate(steps, 1):
        op = str(s.get("op", ""))
        where = f"step {i} ({op})"
        if op not in OPS:
            problems.append(f"{where}: not an operation; use one of {', '.join(OPS)}")
            continue
        name = str(s.get("name") or s.get("descr") or "")
        mine = name.startswith(("Aurora-", "Aurora_"))
        if ENTITY[op] == "alias":
            exists = name in aliases
            if op == "put_alias":
                if not re.fullmatch(r"Aurora_[A-Za-z0-9_]{1,24}", name):
                    problems.append(f"{where}: an alias of Aurora's is named Aurora_<Word> (letters, digits, _), not {name!r}")
                if exists and not mine:
                    problems.append(f"{where}: {name} is the owner's alias: never changed")
                bad = [a for a in s.get("addresses") or [] if not _addr(str(a))]
                if bad or not s.get("addresses"):
                    problems.append(f"{where}: addresses must be IPs or CIDRs ({bad or 'none given'})")
                aliases.add(name)
            elif not exists:
                problems.append(f"{where}: no alias {name}")
            elif not mine:
                problems.append(f"{where}: {name} is not Aurora's: never changed")
            elif op != "drop_alias" and not _addr(str(s.get("ip", ""))):
                problems.append(f"{where}: ip {s.get('ip')!r} is not an address")
        else:
            if not mine:
                problems.append(f"{where}: Aurora's objects are described «Aurora-…», not {name!r}")
            exists = name in (rules if ENTITY[op] == "rule" else nats)
            if op.startswith("drop") and not exists:
                problems.append(f"{where}: no {ENTITY[op]} «{name}»")
            if op in ("put_rule", "put_nat"):
                proto = str(s.get("protocol") or "").lower()
                port = str(s.get("port") or "")
                if proto not in PROTOS:
                    problems.append(f"{where}: protocol {proto!r}: tcp, udp, tcp/udp, icmp or any")
                if port and (not PORT.match(port) or proto not in ("tcp", "udp", "tcp/udp")):
                    problems.append(f"{where}: port {port!r}: a number or a range a:b, only with tcp/udp")
                for side in ("source", "destination", "target"):
                    v = str(s.get(side) or "any")
                    if side == "target" and op != "put_nat":
                        continue
                    if not (v == "any" or _addr(v) or v in aliases or v in ifaces or v.rstrip("!") in aliases):
                        problems.append(f"{where}: {side} {v!r}: any, an address, a CIDR, an alias or an interface")
            if op == "put_rule":
                bad = [x for x in s.get("interfaces") or [] if str(x) not in ifaces]
                if bad or (not s.get("interfaces") and not s.get("floating")):
                    problems.append(f"{where}: interfaces {bad or 'none'}: one of {', '.join(sorted(ifaces))}")
                if str(s.get("action")) not in ("pass", "block"):
                    problems.append(f"{where}: action pass or block")
                dest = str(s.get("destination") or "any")
                if s.get("action") == "pass" and "wan" in (s.get("interfaces") or []) and \
                        (sec_fwmodel.is_self(dest) or dest == firewall or dest in {i["ip"] for i in net.get("interfaces", [])}):
                    problems.append(f"{where}: never a rule that lets the WAN reach the firewall itself")
                if s.get("action") == "block" and str(s.get("source") or "") in own | {firewall}:
                    problems.append(f"{where}: never block this machine or the firewall")
            if op == "put_nat" and not (_addr(str(s.get("target", ""))) and ipaddress.ip_address(str(s["target"])).is_private):
                problems.append(f"{where}: target must be a device of the house (a private address)")
        fields = {k: v for k, v in s.items() if k not in ("op", "why")}
        body = json.dumps({"op": op, **fields})
        undo = ""
        if op in UNDO and not (op.startswith("put") and exists):
            key = "name" if ENTITY[op] == "alias" else "descr"
            undo = json.dumps({"op": UNDO[op], key: name, **({"ip": s.get("ip")} if op.startswith("alias_") else {})})
        out.append({"entity": ENTITY[op], "name": name, "xml": body, "undo": undo,
                    "why": str(s.get("why") or op)[:300], "owner_object": False})
    return out, problems


def plan(cfg: sys_config.Config, request: str, model) -> dict:
    """sec_fwplan.plan for these dialects: the same answer (a plan, {"questions"}, or WriteError after two tries)."""
    fwm, net = sec_fwmodel.read(cfg), sec_netmap.read(cfg)
    own = ", ".join(sorted(a for a in sec_fwapi._own_addresses() if "." in a and not a.startswith("127.")))
    firewall = re.sub(r"^https?://|[:/].*$", "", str(cfg["AURORA_FIREWALL_API_URL"]))
    system = SYS.replace("%KIND%", fwm["kind"]).replace("%AURORA%", own or "?").replace("%FIREWALL%", firewall)
    docs = "\n\n".join(f"[{h['kind']}] {h['title']}\n{h['text'][:1400]}" for h in sec_fwdocs.search(cfg, request, 5))
    user = f"REQUEST OF THE OWNER:\n{request}\n\nCONFIGURATION NOW:\n{_short(fwm, net)}\n\nTHE FIREWALL'S GUIDES:\n{docs}"
    feedback = ""
    for _attempt in range(2):
        answer = model.complete(system, user + feedback, 4000, think=False).answer
        m = re.search(r"\{.*\}", answer, re.S)
        try:
            data = json.loads(m.group(0)) if m else None
        except ValueError:
            data = None
        if not isinstance(data, dict):
            feedback = "\n\nYOUR LAST ANSWER WAS NOT VALID JSON. Answer with the JSON object only."
            continue
        if data.get("questions") and not data.get("steps"):
            return {"questions": [str(q) for q in data["questions"]][:5], "notes": [str(n) for n in data.get("notes", [])][:5]}
        steps, problems = check(cfg, data.get("steps") or [], fwm, net)
        if steps and not problems:
            return {"kind": "request", "request": request, "title": str(data.get("title") or request[:80])[:120],
                    "why": str(data.get("why") or "")[:600], "steps": steps,
                    "notes": [str(n) for n in data.get("notes", [])][:8]
                    + ["Dopo l'applicazione Aurora rilegge ogni oggetto: se il firewall non risponde più, annulla."],
                    "check": [(s["entity"], s["name"]) for s in steps if json.loads(s["xml"])["op"].startswith("put")]}
        problems = problems or ["no steps"]
        feedback = ("\n\nYOUR LAST PLAN HAD PROBLEMS — fix them and answer the whole JSON again:\n- " + "\n- ".join(problems)
                    + f"\nYOUR LAST PLAN:\n{json.dumps(data, ensure_ascii=False)[:6000]}")
    raise sec_fwwrite.WriteError("non sono riuscita a preparare un piano valido: " + feedback.strip()[:600])


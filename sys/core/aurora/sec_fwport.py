# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""An address blocked on one port only, for a time (ROADMAP 103 step 3; owner, 2026-10-14: «l'ideale non sarebbe
bloccare l'ip, ma l'ip accoppiato alla porta specifica di attacco»).

The blocking group (sec_defence) drops an address on every port: right for an attacker, wrong for an address of a
shared network (Cloudflare…) that also brings the owner's visitors and tunnel. Here a change of sec_fwwrite — planned,
shown, applied only with the owner's approval, undone by revert — with a host, a service with the ports and a Drop
rule at the top from WAN; lifted by itself after `hours` (due(), the API's defence round). On a port that Cloudflare
proxies (80, 443…) a Cloudflare address is refused: that is Cloudflare carrying visitors, blocked it would shut them
out — the author is blocked at Cloudflare instead (net_cfwaf)."""
from __future__ import annotations

import ipaddress
import time

from . import sec_fwapi, sec_fwconf, sec_fwwrite, sec_intel, sys_config, sys_log

# the ports Cloudflare's proxy forwards to an origin (HTTP and HTTPS), developers.cloudflare.com/fundamentals/…/ports
PROXIED = {80, 8080, 8880, 2052, 2082, 2086, 2095, 443, 2053, 2083, 2087, 2096, 8443}


def plan_port_block(cfg: sys_config.Config, ip: str, ports: str, reason: str, hours: float = 24,
                    conf: dict | None = None) -> dict:
    ip = sec_fwapi.blockable(cfg, ip)
    if not ipaddress.ip_address(ip).is_global:
        raise sec_fwwrite.WriteError("indirizzo+porta è per un indirizzo di Internet; un dispositivo di casa va in quarantena")
    plist = sec_fwwrite._ports(ports)
    numbers = {int(p) for _, q in plist for p in q.split(":")}
    provider = sec_intel.shared(cfg, ip)
    if provider == "Cloudflare" and numbers & PROXIED:
        raise sec_fwwrite.WriteError(
            f"{ip} è un nodo di Cloudflare e la porta {', '.join(map(str, sorted(numbers & PROXIED)))} è una di quelle "
            "che il proxy porta ai tuoi siti: bloccarla escluderebbe i visitatori dietro quel nodo. Il vero autore si "
            "blocca su Cloudflare (cloudflare_block).")
    if not 1 <= float(hours) <= 24 * 30:
        raise sec_fwwrite.WriteError("durata: da 1 ora a 30 giorni")
    tag = "_".join(q.replace(":", "-") for _, q in plist)[:12]
    name = f"{sec_fwwrite.PREFIX}PB-{ip}-{tag}"
    said = ", ".join(f"{p} {q}" for p, q in plist)
    desc = f"Aurora: {ip} bloccato su {said} per {hours:g} h — {reason}"
    if sec_fwwrite._neutral(cfg):                     # the dialects of the neutral operations (sec_fwops)
        steps, check = sec_fwwrite._ops(lambda o: o.port_block_steps(cfg, ip, plist, name, desc))
    else:
        conf = conf if conf is not None else sec_fwconf.read(cfg)
        if sec_fwwrite._taken(conf, "FirewallRule", name):
            raise sec_fwwrite.WriteError(f"{ip} è già bloccato su {tag} («{name}»)")
        host = name.lower()
        steps = [sec_fwwrite.host_step(host, ip), sec_fwwrite.service_step(name, plist),
                 sec_fwwrite.rule_step(name, desc, ["WAN"], [], [name], [host], [], "Drop", "None", None)]
        check = [("FirewallRule", name)]
    notes = [f"Tolto da solo dopo {hours:g} ore (o subito con «annulla»)."]
    if provider:
        notes.append(f"{ip} è di {provider}: il blocco vale solo per {said}, il resto del suo traffico passa.")
    return {"kind": "portblock", "title": f"Bloccare {ip} su {said}", "why": reason[:300], "steps": steps,
            "notes": notes, "check": check, "hours": float(hours), "ip": ip}


def due(cfg: sys_config.Config, now: float | None = None) -> list[str]:
    """Revert every applied port block whose time is over; an error leaves it for the next round."""
    now, done = now or time.time(), []
    for c in sec_fwwrite.history(cfg):
        if c.get("kind") != "portblock" or c.get("status") != "applied":
            continue
        if c.get("applied", now) + float(c.get("hours", 24)) * 3600 > now:
            continue
        try:
            if sec_fwwrite.revert(cfg, c["id"])["status"] == "reverted":
                done.append(c["title"])
        except (sec_fwwrite.WriteError, sec_fwapi.FirewallAPIError) as e:
            sys_log.get_logger("security").warning("port block %s not lifted yet: %s", c["id"], e)
    return done

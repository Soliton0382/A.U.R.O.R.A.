# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora reachable everywhere through Cloudflare One — a WARP private network (roadmap 56).

No port is opened: cloudflared, on this computer (aurora-tunnel, installed once by sys/deploy/cloudflared/install.sh),
connects out to Cloudflare; a phone with Cloudflare One (WARP) on reaches this computer's own address through it, at
home and away, with the same name and certificate as in the LAN — one PWA everywhere.

`apply` is what «Salva» does in the cloudflare plugin's card (owner, 2026-10-07: «con un semplice salva si attiva
tutto»): the tunnel created if missing, this computer's /32 (and the home DNS's) routed through it, WARP's split tunnel
carved around them, the internal domain resolved by the home DNS (local domain fallback), the tunnel's token fetched
and kept 0600 (never shown, never in a text), aurora-tunnel (re)started. Idempotent: what is there stays.
The state and the check of what is missing were written by Aurora herself (forge request 328397d269, 7 October 2026).
"""
from __future__ import annotations

import ipaddress
import os
import shutil
import socket
import subprocess
from pathlib import Path

import httpx

from . import sys_config

API = "https://api.cloudflare.com/client/v4"
NOTE = "Aurora (cloudflare plugin)"
UNIT = "aurora-tunnel.service"
KEYS = {"AURORA_CLOUDFLARE_ACCOUNT_ID", "AURORA_CLOUDFLARE_API_TOKEN", "AURORA_CLOUDFLARE_TUNNEL",
        "AURORA_CLOUDFLARE_NETWORK", "AURORA_CLOUDFLARE_DOMAIN", "AURORA_CLOUDFLARE_DNS"}


def token_file(cfg: sys_config.Config) -> Path:
    return cfg.path("AURORA_STATUS_DIR") / "cloudflare" / "tunnel.token"


def local_net() -> str:
    """This computer's address as /32 (a UDP connect sends no packet)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
        finally:
            s.close()
        return "" if ip.startswith("127.") else f"{ip}/32"
    except OSError:
        return ""


def conf(cfg: sys_config.Config) -> dict:
    v = lambda k: str(cfg.values.get(k) or "").strip()            # noqa: E731
    return {"acc": v("AURORA_CLOUDFLARE_ACCOUNT_ID"), "tok": v("AURORA_CLOUDFLARE_API_TOKEN"),
            "name": v("AURORA_CLOUDFLARE_TUNNEL") or "aurora", "net": v("AURORA_CLOUDFLARE_NETWORK") or local_net(),
            "dom": v("AURORA_CLOUDFLARE_DOMAIN").lstrip("."), "dns": v("AURORA_CLOUDFLARE_DNS"),
            "host": v("AURORA_DOMAIN")}


def missing(c: dict) -> str:
    m = [n for n, k in (("AURORA_CLOUDFLARE_ACCOUNT_ID", "acc"), ("AURORA_CLOUDFLARE_API_TOKEN", "tok")) if not c[k]]
    return ("Cloudflare non configurato: manca " + ", ".join(m) + " (la scheda del plugin cloudflare).") if m else ""


def _call(cl: httpx.Client, method: str, path: str, **kw):
    """(result, error text). The token never appears in the text."""
    try:
        r = cl.request(method, API + path, **kw)
    except httpx.HTTPError as e:
        return None, f"rete non raggiungibile ({type(e).__name__})"
    try:
        j = r.json()
    except ValueError:
        return None, f"HTTP {r.status_code}"
    if not j.get("success"):
        errs = "; ".join(f"{x.get('code')}: {x.get('message')}" for x in j.get("errors") or [])
        return None, f"HTTP {r.status_code} {errs}".strip()
    return j.get("result"), ""


def client(c: dict) -> httpx.Client:
    return httpx.Client(timeout=15, headers={"Authorization": f"Bearer {c['tok']}"})


def nets(c: dict) -> list[str]:
    """What WARP must carry: this computer, and the home DNS server when the domain is resolved by it."""
    out = [c["net"]] if c["net"] else []
    if c["dns"] and c["dom"]:
        out.append(f"{c['dns']}/32")
    return list(dict.fromkeys(out))


def collect(c: dict) -> dict:
    a, d = c["acc"], {}
    with client(c) as cl:
        r, err = _call(cl, "GET", f"/accounts/{a}/tokens/verify")
        if err:
            r, err = _call(cl, "GET", "/user/tokens/verify")
        d["token"] = (r or {}).get("status", "") if not err else "ERR " + err
        t, err = _call(cl, "GET", f"/accounts/{a}/cfd_tunnel", params={"name": c["name"], "is_deleted": "false"})
        d["tunnel_err"], d["tunnel"] = err, (t or [None])[0] if not err else None
        d["published"] = []
        if d["tunnel"]:                                 # a hostname published on the Internet through this tunnel
            g, err = _call(cl, "GET", f"/accounts/{a}/cfd_tunnel/{d['tunnel']['id']}/configurations")
            ingress = ((g or {}).get("config") or {}).get("ingress") or []
            d["published"] = [i["hostname"] for i in ingress if isinstance(i, dict) and i.get("hostname")]
        r, err = _call(cl, "GET", f"/accounts/{a}/teamnet/routes", params={"is_deleted": "false"})
        d["routes_err"], d["routes"] = err, r or []
        p, err = _call(cl, "GET", f"/accounts/{a}/devices/policy")
        d["policy_err"], d["policy"] = err, p or {}
        d["mode"] = "include" if (p or {}).get("include") else "exclude"
        s, err = _call(cl, "GET", f"/accounts/{a}/devices/policy/{d['mode']}")
        d["split_err"], d["split"] = err, s or []
        f, err = _call(cl, "GET", f"/accounts/{a}/devices/policy/fallback_domains")
        d["fb_err"], d["fallback"] = err, f or []
    d["public"] = public_answer(c["host"]) if c["host"] and c["dom"] and c["host"].endswith(c["dom"]) else []
    return d


def public_answer(host: str) -> list[str]:
    """What the public DNS says for Aurora's name (Cloudflare's DNS over HTTPS): a record left there — the CNAME of a
    deleted public route — sends a phone whose WARP misses the home DNS to Cloudflare's 1033 page (C182)."""
    try:
        r = httpx.get("https://cloudflare-dns.com/dns-query", params={"name": host, "type": "A"},
                      headers={"accept": "application/dns-json"}, timeout=8)
        return [a["data"] for a in r.json().get("Answer") or [] if a.get("type") in (1, 5)]
    except (httpx.HTTPError, ValueError, KeyError):
        return []


def net_in(net: str, entries: list) -> list:
    """The entries (split tunnel: {"address"}) that contain `net`."""
    out = []
    try:
        n = ipaddress.ip_network(net, strict=False)
    except ValueError:
        return out
    for x in entries:
        try:
            if x.get("address") and n.subnet_of(ipaddress.ip_network(x["address"], strict=False)):
                out.append(x["address"])
        except (ValueError, TypeError):
            pass
    return out


def without(entries: list[dict], net: str) -> list[dict]:
    """An exclude list with `net` carved out: 192.168.0.0/16 (WARP's default) becomes the pieces around the /32, so
    the rest of the LAN stays out of WARP and only Aurora goes in."""
    n = ipaddress.ip_network(net, strict=False)
    out = []
    for x in entries:
        try:
            big = ipaddress.ip_network(x["address"], strict=False)
        except (KeyError, ValueError, TypeError):
            out.append(x)
            continue
        if big.version == n.version and n.subnet_of(big):
            # each piece keeps the entry's own description: Cloudflare refuses a longer one (C182: «invalid
            # description length» — the split tunnel was never changed and the phone stayed outside)
            out += [{"address": str(p), **({"description": x["description"]} if x.get("description") else {})}
                    for p in big.address_exclude(n)]
        else:
            out.append(x)
    return out


def service_state() -> str:
    """aurora-tunnel on this computer: "active", "inactive", "failed", or "missing" (not installed yet)."""
    if not shutil.which("cloudflared"):
        return "missing"
    r = subprocess.run(["systemctl", "show", "-p", "LoadState,ActiveState", "--value", UNIT],
                       capture_output=True, text=True, timeout=10)
    load, _, active = r.stdout.strip().partition("\n")
    return "missing" if load.strip() != "loaded" else active.strip() or "inactive"


INSTALL = "sudo bash sys/deploy/cloudflared/install.sh (una volta sola)"


def analyse(c: dict, d: dict, service: str) -> tuple[list, list]:
    """(lines of state, things missing)."""
    lines, todo = [], []
    lines.append(f"Token API: {d['token'] or 'sconosciuto'}")
    if d["token"] != "active":
        todo.append("token API non valido o senza permessi (servono «Cloudflare Tunnel: Edit» e «Zero Trust: Edit»)")
    t = d["tunnel"]
    if d["tunnel_err"]:
        lines.append(f"Tunnel: impossibile leggere ({d['tunnel_err']})")
    elif not t:
        lines.append(f"Tunnel «{c['name']}»: non esiste")
        todo.append(f"creare il tunnel «{c['name']}» (lo fa «Salva»)")
    else:
        conns = t.get("connections") or []
        colos = ", ".join(sorted({x.get("colo_name", "?") for x in conns})) or "nessuna"
        lines.append(f"Tunnel «{c['name']}»: stato {t.get('status')}, {len(conns)} connessioni ({colos})")
        if t.get("status") != "healthy" and service == "active":
            todo.append("il servizio aurora-tunnel gira ma il tunnel non è healthy: attendi un minuto, poi «Salva» di nuovo")
    if d.get("public"):
        lines.append(f"⚠️ {c['host']}: il DNS pubblico risponde ({', '.join(d['public'][:2])}) — un record rimasto")
        todo.append(f"cancellare il record di {c['host']} in Cloudflare → DNS → Records della zona {c['dom']} "
                    "(serve solo il DNS di casa: senza, fuori casa si vede l'errore 1033)")
    for h in d.get("published") or []:
        lines.append(f"⚠️ {h}: PUBBLICATO su Internet da questo tunnel (chiunque arriva al login)")
        todo.append(f"togliere {h} dalle «Published application routes» del tunnel (la rete privata non ne ha bisogno)")
    tid = (t or {}).get("id")
    if not c["net"]:
        lines.append("Rete privata: indirizzo di questo computer non determinato")
        todo.append("impostare AURORA_CLOUDFLARE_NETWORK (IP/32)")
    for net in nets(c):
        if d["routes_err"]:
            lines.append(f"Rotte: impossibile leggere ({d['routes_err']})")
            break
        hit = [r for r in d["routes"] if net_in(net, [{"address": r.get("network")}])]
        mine = [r for r in hit if tid and r.get("tunnel_id") == tid]
        if mine:
            lines.append(f"Rotta {net}: presente sul tunnel ({mine[0].get('network')})")
        elif hit:
            lines.append(f"Rotta {net}: coperta da {hit[0].get('network')} su un altro tunnel ({hit[0].get('tunnel_name')})")
            todo.append(f"aggiungere la rotta {net} al tunnel «{c['name']}» (più specifica: vince lei)")
        else:
            lines.append(f"Rotta {net}: assente")
            todo.append(f"aggiungere la rotta privata {net} al tunnel «{c['name']}»")
        if d["split_err"]:
            lines.append(f"Split tunnel: impossibile leggere ({d['split_err']})")
            continue
        cov = net_in(net, d["split"])
        if d["mode"] == "exclude":
            lines.append(f"Split tunnel (exclude): {net} " + (f"ESCLUSO da {', '.join(cov)}" if cov else "passa in WARP"))
            if cov:
                todo.append(f"togliere {net} dagli esclusi di WARP ({', '.join(cov)})")
        else:
            lines.append(f"Split tunnel (include): {net} " + ("incluso" if cov else "NON incluso"))
            if not cov:
                todo.append(f"aggiungere {net} agli inclusi di WARP")
    dom = c["dom"]
    if dom:
        fb = [x for x in d["fallback"] if dom == x.get("suffix") or dom.endswith("." + str(x.get("suffix")))]
        lines.append(f"Dominio interno {dom}: " + (f"fallback locale presente ({fb[0].get('suffix')} → "
                                                  f"{', '.join(fb[0].get('dns_server') or []) or 'DNS del dispositivo'})"
                                                  if fb else "nessun fallback locale"))
        if not fb and not d["fb_err"]:
            todo.append(f"aggiungere {dom} al Local Domain Fallback di WARP" + (f" (DNS {c['dns']})" if c["dns"] else ""))
        if not c["dns"]:
            todo.append("impostare AURORA_CLOUDFLARE_DNS: il DNS di casa che risolve " + dom)
    else:
        lines.append("Dominio interno: non impostato (AURORA_CLOUDFLARE_DOMAIN)")
    lines.append("Servizio aurora-tunnel su questo computer: " + {"missing": "non installato", "active": "attivo"}.get(service, service))
    if service == "missing":
        todo.append("installare cloudflared e il servizio: " + INSTALL)
    return lines, todo


def status(cfg: sys_config.Config) -> str:
    c = conf(cfg)
    if m := missing(c):
        return m
    lines, _ = analyse(c, collect(c), service_state())
    return "Cloudflare Zero Trust\n" + "\n".join("- " + x for x in lines)


def check(cfg: sys_config.Config) -> str:
    c = conf(cfg)
    if m := missing(c):
        return m
    _, todo = analyse(c, collect(c), service_state())
    if not todo:
        return f"Tutto pronto: Aurora è raggiungibile via WARP su {c['net']} tramite il tunnel «{c['name']}», senza porte aperte."
    return "\n".join(["Per attivare l'accesso via WARP manca:"] + [f"{i}. {x}" for i, x in enumerate(todo, 1)])


def _keep_token(cfg: sys_config.Config, token: str) -> bool:
    """The tunnel's token in a 0600 file aurora-tunnel reads; True when it changed."""
    f = token_file(cfg)
    f.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(f.parent, 0o700)
    if f.exists() and f.read_text().strip() == token:
        return False
    tmp = f.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(token)
    os.replace(tmp, f)
    return True


def apply(cfg: sys_config.Config, systemctl=None) -> dict:
    """«Salva»: every step on the account, the token kept, aurora-tunnel (re)started. {"ok", "done", "failed", "text"}."""
    systemctl = systemctl or (lambda verb: subprocess.run(["systemctl", verb, UNIT], capture_output=True, text=True,
                                                          timeout=30))
    c = conf(cfg)
    if m := missing(c):
        return {"ok": False, "done": [], "failed": [m], "text": m}
    if not c["net"]:
        m = "indirizzo di questo computer non determinato: imposta AURORA_CLOUDFLARE_NETWORK (IP/32)"
        return {"ok": False, "done": [], "failed": [m], "text": m}
    a, done, failed, running = c["acc"], [], [], False
    d = collect(c)
    if d["token"] != "active":
        m = f"token API non accettato ({d['token']}): servono «Cloudflare Tunnel: Edit» e «Zero Trust: Edit»"
        return {"ok": False, "done": [], "failed": [m], "text": m}
    if d["tunnel_err"]:
        m = f"tunnel non leggibile ({d['tunnel_err']}): nulla modificato"
        return {"ok": False, "done": [], "failed": [m], "text": m}
    with client(c) as cl:
        t = d["tunnel"]
        if not t:
            t, err = _call(cl, "POST", f"/accounts/{a}/cfd_tunnel", json={"name": c["name"], "config_src": "cloudflare"})
            if err:
                m = f"tunnel «{c['name']}» non creato: {err}"
                return {"ok": False, "done": [], "failed": [m], "text": m}
            done.append(f"tunnel «{c['name']}» creato")
        tid = t["id"]
        for net in nets(c):
            if not any(r.get("tunnel_id") == tid and net_in(net, [{"address": r.get("network")}]) for r in d["routes"]):
                _, err = _call(cl, "POST", f"/accounts/{a}/teamnet/routes", json={"network": net, "tunnel_id": tid, "comment": NOTE})
                (failed if err else done).append(f"rotta {net} " + (f"non aggiunta: {err}" if err else "aggiunta al tunnel"))
        if not d["split_err"]:
            split = list(d["split"])
            for net in nets(c):
                if d["mode"] == "exclude" and net_in(net, split):
                    split = without(split, net)
                elif d["mode"] == "include" and not net_in(net, split):
                    split.append({"address": net, "description": "Aurora"})
            if split != d["split"]:
                _, err = _call(cl, "PUT", f"/accounts/{a}/devices/policy/{d['mode']}", json=split)
                (failed if err else done).append(f"split tunnel ({d['mode']}) " + (f"non aggiornato: {err}" if err else
                                                 "aggiornato: WARP porta " + ", ".join(nets(c))))
        if c["dom"] and c["dns"] and not d["fb_err"] and not any(c["dom"] == x.get("suffix") for x in d["fallback"]):
            _, err = _call(cl, "PUT", f"/accounts/{a}/devices/policy/fallback_domains",
                           json=d["fallback"] + [{"suffix": c["dom"], "dns_server": [c["dns"]], "description": NOTE}])
            (failed if err else done).append(f"dominio {c['dom']} " + (f"non aggiunto al fallback: {err}" if err else
                                             f"risolto da {c['dns']} anche fuori casa"))
        token, err = _call(cl, "GET", f"/accounts/{a}/cfd_tunnel/{tid}/token")
    if err or not isinstance(token, str):
        failed.append(f"token del tunnel non ottenuto: {err or 'risposta inattesa'}")
    else:
        try:
            changed = _keep_token(cfg, token)
        except OSError:                                 # the plugin's cage cannot write it: the card's «Salva» does
            changed = None
        service = service_state()
        if changed is None:
            failed.append("il tunnel lo avvia «Salva» nella scheda del plugin cloudflare (da qui non posso)")
            service = "cage"
        if service == "missing":
            failed.append("servizio aurora-tunnel non installato: " + INSTALL)
        elif service != "cage":
            r = systemctl("restart" if changed or service != "active" else "start")
            if r.returncode == 0 and (changed or service != "active"):
                done.append("aurora-tunnel avviato: tra un minuto il tunnel risulta HEALTHY")
            elif r.returncode == 0:
                running = True
            else:
                failed.append(f"aurora-tunnel non avviato: {(r.stderr or '').strip()[-200:]}")
    warn = [f"⚠️ {h} è pubblicato su Internet da questo tunnel: toglilo dalle «Published application routes»"
            for h in d.get("published") or []]
    text = "\n".join((["Fatto:"] + [f"✅ {x}" for x in done] if done else ["Account Cloudflare già a posto."])
                     + (["🟢 aurora-tunnel attivo"] if running else []) + [f"❌ {x}" for x in failed] + warn)
    return {"ok": not failed, "done": done, "failed": failed, "text": text}


def stop(systemctl=None) -> bool:
    """The plugin switched off: the tunnel stops (the account's settings stay, «Salva» starts it again)."""
    systemctl = systemctl or (lambda verb: subprocess.run(["systemctl", verb, UNIT], capture_output=True, text=True, timeout=30))
    return service_state() != "missing" and systemctl("stop").returncode == 0

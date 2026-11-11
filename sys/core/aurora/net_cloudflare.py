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
from .sys_lang import say as _t   # each sentence in the reader's language (C526)

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
    return _t(("Cloudflare non configurato: manca " + ", ".join(m) + " (la scheda del plugin cloudflare)."), ("Cloudflare is not configured: missing " + ", ".join(m) + " (the cloudflare plugin's card).")) if m else ""


def _call(cl: httpx.Client, method: str, path: str, **kw):
    """(result, error text). The token never appears in the text."""
    try:
        r = cl.request(method, API + path, **kw)
    except httpx.HTTPError as e:
        return None, _t(f"rete non raggiungibile ({type(e).__name__})", f"network not reachable ({type(e).__name__})")
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


INSTALL = "sudo aurora-root install tunnel (una volta sola)"
INSTALL_EN = "sudo aurora-root install tunnel (only once)"


def analyse(c: dict, d: dict, service: str) -> tuple[list, list]:
    """(lines of state, things missing)."""
    lines, todo = [], []
    lines.append(_t(f"Token API: {d['token'] or 'sconosciuto'}", f"API token: {d['token'] or 'unknown'}"))
    if d["token"] != "active":
        todo.append(_t("token API non valido o senza permessi (servono «Cloudflare Tunnel: Edit» e «Zero Trust: Edit»)", "API token not valid or without permissions («Cloudflare Tunnel: Edit» and «Zero Trust: Edit» are needed)"))
    t = d["tunnel"]
    if d["tunnel_err"]:
        lines.append(_t(f"Tunnel: impossibile leggere ({d['tunnel_err']})", f"Tunnel: cannot be read ({d['tunnel_err']})"))
    elif not t:
        lines.append(_t(f"Tunnel «{c['name']}»: non esiste", f"Tunnel «{c['name']}»: does not exist"))
        todo.append(_t(f"creare il tunnel «{c['name']}» (lo fa «Salva»)", f"create the tunnel «{c['name']}» («Save» does it)"))
    else:
        conns = t.get("connections") or []
        colos = ", ".join(sorted({x.get("colo_name", "?") for x in conns})) or _t("nessuna", "none")
        lines.append(_t(f"Tunnel «{c['name']}»: stato {t.get('status')}, {len(conns)} connessioni ({colos})", f"Tunnel «{c['name']}»: status {t.get('status')}, {len(conns)} connections ({colos})"))
        if t.get("status") != "healthy" and service == "active":
            todo.append(_t("il servizio aurora-tunnel gira ma il tunnel non è healthy: attendi un minuto, poi «Salva» di nuovo", "the aurora-tunnel service runs but the tunnel is not healthy: wait a minute, then «Save» again"))
    if d.get("public"):
        lines.append(_t(f"⚠️ {c['host']}: il DNS pubblico risponde ({', '.join(d['public'][:2])}) — un record rimasto", f"⚠️ {c['host']}: the public DNS answers ({', '.join(d['public'][:2])}) — a record left behind"))
        todo.append(_t(f"cancellare il record di {c['host']} in Cloudflare → DNS → Records della zona {c['dom']} "
                    "(serve solo il DNS di casa: senza, fuori casa si vede l'errore 1033)", f"delete the record of {c['host']} in Cloudflare → DNS → Records of the zone {c['dom']} "
                    "(only the home DNS is needed: without it, away from home one sees error 1033)"))
    for h in d.get("published") or []:
        lines.append(_t(f"⚠️ {h}: PUBBLICATO su Internet da questo tunnel (chiunque arriva al login)", f"⚠️ {h}: PUBLISHED on the Internet by this tunnel (anyone reaches the login)"))
        todo.append(_t(f"togliere {h} dalle «Published application routes» del tunnel (la rete privata non ne ha bisogno)", f"remove {h} from the tunnel's «Published application routes» (the private network does not need it)"))
    tid = (t or {}).get("id")
    if not c["net"]:
        lines.append(_t("Rete privata: indirizzo di questo computer non determinato", "Private network: this computer's address could not be found"))
        todo.append(_t("impostare AURORA_CLOUDFLARE_NETWORK (IP/32)", "set AURORA_CLOUDFLARE_NETWORK (IP/32)"))
    for net in nets(c):
        if d["routes_err"]:
            lines.append(_t(f"Rotte: impossibile leggere ({d['routes_err']})", f"Routes: cannot be read ({d['routes_err']})"))
            break
        hit = [r for r in d["routes"] if net_in(net, [{"address": r.get("network")}])]
        mine = [r for r in hit if tid and r.get("tunnel_id") == tid]
        if mine:
            lines.append(_t(f"Rotta {net}: presente sul tunnel ({mine[0].get('network')})", f"Route {net}: on the tunnel ({mine[0].get('network')})"))
        elif hit:
            lines.append(_t(f"Rotta {net}: coperta da {hit[0].get('network')} su un altro tunnel ({hit[0].get('tunnel_name')})", f"Route {net}: covered by {hit[0].get('network')} on another tunnel ({hit[0].get('tunnel_name')})"))
            todo.append(_t(f"aggiungere la rotta {net} al tunnel «{c['name']}» (più specifica: vince lei)", f"add the route {net} to the tunnel «{c['name']}» (more specific: it wins)"))
        else:
            lines.append(_t(f"Rotta {net}: assente", f"Route {net}: absent"))
            todo.append(_t(f"aggiungere la rotta privata {net} al tunnel «{c['name']}»", f"add the private route {net} to the tunnel «{c['name']}»"))
        if d["split_err"]:
            lines.append(_t(f"Split tunnel: impossibile leggere ({d['split_err']})", f"Split tunnel: cannot be read ({d['split_err']})"))
            continue
        cov = net_in(net, d["split"])
        if d["mode"] == "exclude":
            lines.append(f"Split tunnel (exclude): {net} " + _t((f"ESCLUSO da {', '.join(cov)}" if cov else "passa in WARP"), (f"EXCLUDED by {', '.join(cov)}" if cov else "goes through WARP")))
            if cov:
                todo.append(_t(f"togliere {net} dagli esclusi di WARP ({', '.join(cov)})", f"remove {net} from WARP's exclusions ({', '.join(cov)})"))
        else:
            lines.append(f"Split tunnel (include): {net} " + _t(("incluso" if cov else "NON incluso"), ("included" if cov else "NOT included")))
            if not cov:
                todo.append(_t(f"aggiungere {net} agli inclusi di WARP", f"add {net} to WARP's inclusions"))
    dom = c["dom"]
    if dom:
        fb = [x for x in d["fallback"] if dom == x.get("suffix") or dom.endswith("." + str(x.get("suffix")))]
        lines.append(_t(f"Dominio interno {dom}: ", f"Internal domain {dom}: ") + _t((f"fallback locale presente ({fb[0].get('suffix')} → "
                                                  f"{', '.join(fb[0].get('dns_server') or []) or 'DNS del dispositivo'})"
                                                  if fb else "nessun fallback locale"), (f"local fallback present ({fb[0].get('suffix')} → "
                                                  f"{', '.join(fb[0].get('dns_server') or []) or 'the device DNS'})"
                                                  if fb else "no local fallback")))
        if not fb and not d["fb_err"]:
            todo.append(_t(f"aggiungere {dom} al Local Domain Fallback di WARP", f"add {dom} to WARP's Local Domain Fallback") + (f" (DNS {c['dns']})" if c["dns"] else ""))
        if not c["dns"]:
            todo.append(_t("impostare AURORA_CLOUDFLARE_DNS: il DNS di casa che risolve ", "set AURORA_CLOUDFLARE_DNS: the home DNS that resolves ") + dom)
    else:
        lines.append(_t("Dominio interno: non impostato (AURORA_CLOUDFLARE_DOMAIN)", "Internal domain: not set (AURORA_CLOUDFLARE_DOMAIN)"))
    lines.append(_t("Servizio aurora-tunnel su questo computer: ", "The aurora-tunnel service on this computer: ") + _t({"missing": "non installato", "active": "attivo"}, {"missing": "not installed", "active": "active"}).get(service, service))
    if service == "missing":
        todo.append(_t("installare cloudflared e il servizio: ", "install cloudflared and the service: ") + _t(INSTALL, INSTALL_EN))
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
        return _t(f"Tutto pronto: Aurora è raggiungibile via WARP su {c['net']} tramite il tunnel «{c['name']}», senza porte aperte.", f"All set: Aurora can be reached through WARP at {c['net']} by the tunnel «{c['name']}», with no open ports.")
    return "\n".join([_t("Per attivare l'accesso via WARP manca:", "To turn on the access through WARP this is missing:")] + [f"{i}. {x}" for i, x in enumerate(todo, 1)])


def _write600(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    os.replace(tmp, path)


def _keep_token(cfg: sys_config.Config, token: str) -> bool | str:
    """The tunnel's token where aurora-tunnel reads it; True when it changed. Sealed (C463, N69 g: install.sh made it a
    systemd credential bound to this machine's TPM, tunnel.token.cred, and left only its SHA-256): the same token is
    known by its hash; a new one is put aside in tunnel.token.new and "seal" said — install.sh, run again, seals it
    (never written back in clear where the unit used to read it)."""
    import hashlib
    f = token_file(cfg)
    f.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(f.parent, 0o700)
    sha = hashlib.sha256(token.encode()).hexdigest()
    cred, mark = f.with_name(f.name + ".cred"), f.with_name(f.name + ".sha256")
    if cred.exists():
        if mark.exists() and mark.read_text().strip() == sha:
            return False
        _write600(f.with_name(f.name + ".new"), token)
        return "seal"
    if f.exists() and f.read_text().strip() == token:
        return False
    _write600(f, token)
    _write600(mark, sha)
    return True


def apply(cfg: sys_config.Config, systemctl=None) -> dict:
    """«Salva»: every step on the account, the token kept, aurora-tunnel (re)started. {"ok", "done", "failed", "text"}."""
    systemctl = systemctl or (lambda verb: subprocess.run(["systemctl", verb, UNIT], capture_output=True, text=True,
                                                          timeout=30))
    c = conf(cfg)
    if m := missing(c):
        return {"ok": False, "done": [], "failed": [m], "text": m}
    if not c["net"]:
        m = _t("indirizzo di questo computer non determinato: imposta AURORA_CLOUDFLARE_NETWORK (IP/32)", "this computer's address could not be found: set AURORA_CLOUDFLARE_NETWORK (IP/32)")
        return {"ok": False, "done": [], "failed": [m], "text": m}
    a, done, failed, running = c["acc"], [], [], False
    d = collect(c)
    if d["token"] != "active":
        m = _t(f"token API non accettato ({d['token']}): servono «Cloudflare Tunnel: Edit» e «Zero Trust: Edit»", f"API token not accepted ({d['token']}): «Cloudflare Tunnel: Edit» and «Zero Trust: Edit» are needed")
        return {"ok": False, "done": [], "failed": [m], "text": m}
    if d["tunnel_err"]:
        m = _t(f"tunnel non leggibile ({d['tunnel_err']}): nulla modificato", f"the tunnel cannot be read ({d['tunnel_err']}): nothing changed")
        return {"ok": False, "done": [], "failed": [m], "text": m}
    with client(c) as cl:
        t = d["tunnel"]
        if not t:
            t, err = _call(cl, "POST", f"/accounts/{a}/cfd_tunnel", json={"name": c["name"], "config_src": "cloudflare"})
            if err:
                m = _t(f"tunnel «{c['name']}» non creato: {err}", f"tunnel «{c['name']}» not created: {err}")
                return {"ok": False, "done": [], "failed": [m], "text": m}
            done.append(_t(f"tunnel «{c['name']}» creato", f"tunnel «{c['name']}» created"))
        tid = t["id"]
        for net in nets(c):
            if not any(r.get("tunnel_id") == tid and net_in(net, [{"address": r.get("network")}]) for r in d["routes"]):
                _, err = _call(cl, "POST", f"/accounts/{a}/teamnet/routes", json={"network": net, "tunnel_id": tid, "comment": NOTE})
                (failed if err else done).append(_t(f"rotta {net} " + (f"non aggiunta: {err}" if err else "aggiunta al tunnel"), f"route {net} " + (f"not added: {err}" if err else "added to the tunnel")))
        if not d["split_err"]:
            split = list(d["split"])
            for net in nets(c):
                if d["mode"] == "exclude" and net_in(net, split):
                    split = without(split, net)
                elif d["mode"] == "include" and not net_in(net, split):
                    split.append({"address": net, "description": "Aurora"})
            if split != d["split"]:
                _, err = _call(cl, "PUT", f"/accounts/{a}/devices/policy/{d['mode']}", json=split)
                (failed if err else done).append(_t(f"split tunnel ({d['mode']}) " + (f"non aggiornato: {err}" if err else
                                                 "aggiornato: WARP porta " + ", ".join(nets(c))), f"split tunnel ({d['mode']}) " + (f"not updated: {err}" if err else
                                                 "updated: WARP carries " + ", ".join(nets(c)))))
        if c["dom"] and c["dns"] and not d["fb_err"] and not any(c["dom"] == x.get("suffix") for x in d["fallback"]):
            _, err = _call(cl, "PUT", f"/accounts/{a}/devices/policy/fallback_domains",
                           json=d["fallback"] + [{"suffix": c["dom"], "dns_server": [c["dns"]], "description": NOTE}])
            (failed if err else done).append(_t(f"dominio {c['dom']} " + (f"non aggiunto al fallback: {err}" if err else
                                             f"risolto da {c['dns']} anche fuori casa"), f"domain {c['dom']} " + (f"not added to the fallback: {err}" if err else
                                             f"resolved by {c['dns']} away from home too")))
        token, err = _call(cl, "GET", f"/accounts/{a}/cfd_tunnel/{tid}/token")
    if err or not isinstance(token, str):
        failed.append(_t(f"token del tunnel non ottenuto: {err or 'risposta inattesa'}", f"the tunnel's token was not obtained: {err or 'unexpected answer'}"))
    else:
        try:
            changed = _keep_token(cfg, token)
        except OSError:                                 # the plugin's cage cannot write it: the card's «Salva» does
            changed = None
        service = service_state()
        if changed is None:
            failed.append(_t("il tunnel lo avvia «Salva» nella scheda del plugin cloudflare (da qui non posso)", "the tunnel is started by «Save» in the cloudflare plugin's card (from here I cannot)"))
            service = "cage"
        elif changed == "seal":                         # a new token while the old one is sealed: root seals it (C463)
            failed.append(_t("token del tunnel nuovo: per sigillarlo e usarlo, sudo aurora-root install tunnel", "new tunnel token: to seal it and use it, sudo aurora-root install tunnel"))
            service = "cage"
        if service == "missing":
            failed.append(_t("servizio aurora-tunnel non installato: ", "the aurora-tunnel service is not installed: ") + _t(INSTALL, INSTALL_EN))
        elif service != "cage":
            r = systemctl("restart" if changed or service != "active" else "start")
            if r.returncode == 0 and (changed or service != "active"):
                done.append(_t("aurora-tunnel avviato: tra un minuto il tunnel risulta HEALTHY", "aurora-tunnel started: in a minute the tunnel shows HEALTHY"))
            elif r.returncode == 0:
                running = True
            else:
                failed.append(_t(f"aurora-tunnel non avviato: {(r.stderr or '').strip()[-200:]}", f"aurora-tunnel not started: {(r.stderr or '').strip()[-200:]}"))
    warn = [_t(f"⚠️ {h} è pubblicato su Internet da questo tunnel: toglilo dalle «Published application routes»", f"⚠️ {h} is published on the Internet by this tunnel: remove it from the «Published application routes»")
            for h in d.get("published") or []]
    text = "\n".join(([_t("Fatto:", "Done:")] + [f"✅ {x}" for x in done] if done else [_t("Account Cloudflare già a posto.", "The Cloudflare account is already in order.")])
                     + ([_t("🟢 aurora-tunnel attivo", "🟢 aurora-tunnel active")] if running else []) + [f"❌ {x}" for x in failed] + warn)
    return {"ok": not failed, "done": done, "failed": failed, "text": text}


def stop(systemctl=None) -> bool:
    """The plugin switched off: the tunnel stops (the account's settings stay, «Salva» starts it again)."""
    systemctl = systemctl or (lambda verb: subprocess.run(["systemctl", verb, UNIT], capture_output=True, text=True, timeout=30))
    return service_state() != "missing" and systemctl("stop").returncode == 0

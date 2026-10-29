# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔒 Aurora's own internet through a VPN (owner, 29–30 Oct: an OpenVPN file imported from the WebUI; «se il tunnel
cade… aurora scelga altri ovpn caricati e che nel caso chieda di passare dalla connettività non protetta»; «tiene
sempre l'ultima connessione utilizzata come predefinita… una spunta per dire quale sarà la predefinita»).

Any provider that gives an .ovpn file. What passes through it: the service user only (uid), so every process of
Aurora — the API, the cycle, the harvester, the plugins and what they start — and nothing else of the machine: the
owner's desktop, the LAN, the NAS and the remote-access tunnel stay on the normal network (owner's four choices, 30 Oct).

- A profile is an .ovpn kept sealed, adapted on import: only the directives of a client's connection are kept (KEEP;
  whatever runs a command, changes the machine's routes or writes a file is dropped and said), `ns-cert-type` becomes
  `remote-cert-tls`. The user name and password are one pair for all, sealed.
- The tunnel is run by aurora-vpn (svc_vpn.py, the only unit with CAP_NET_ADMIN): the routes it pulls are ignored; a
  table of its own sends the service user's internet into the tunnel; while it is down that table says «unreachable»
  (the kill switch, for Aurora only), unless the owner chose the unprotected line until it is back.
- DNS: the services read <status>/vpn/resolv.conf (bound over /etc/resolv.conf in their units): the tunnel's servers
  while it is up, the machine's resolver otherwise.
- It fails: the next profile, the default first then the last used then the rest; all fail: the owner is asked.

The API writes what is wanted (prefs.json); the unit writes what is (state.json); neither writes the other's file."""
from __future__ import annotations

import json
import os
import re
import secrets
import time
from pathlib import Path

from . import sys_config, sys_seal

PURPOSE = "vpn"
TABLE = 711                                         # the routing table of Aurora's internet
MARK = 0x711                                        # the tunnel's own packets (and the remote-access tunnel's): never in it
PRIO = (17110, 17111, 17112)                        # the rules: the marked, the local routes, the rest into the table
DEV = "avpn0"
MAX_PROFILES = 40
MAX_OVPN = 64 * 1024
STUB = "nameserver 127.0.0.53\noptions edns0 trust-ad\n"
# what may pass through the tunnel, one service each (the finest the rules can tell apart: one process is one choice —
# the API's searches, plugins and cloud calls are one); ticked by default: RECOMMENDED (owner, 30 Oct: «sceglie cosa far
# passare nel tunnel vpn, con selezionati i nostri recommended»). What is not ticked keeps the normal line. Anything
# else the service user runs (a script by hand) always passes through.
CHOICES = {
    "aurora-api.service": {"it": "Ricerche, plugin, cloud, aggiornamenti (l'API)", "en": "Searches, plugins, cloud, updates (the API)"},
    "aurora-harvester.service": {"it": "Harvester: paper e fonti scaricati", "en": "Harvester: papers and sources downloaded"},
    "aurora-rem.service": {"it": "Ciclo notturno: meteo, pensieri, studio", "en": "Night cycle: weather, thoughts, study"},
    "aurora-sentinel.service": {"it": "Sentinella: controlli sugli indirizzi visti dal firewall", "en": "Sentinel: checks on the addresses the firewall saw"},
    "aurora-tunnel.service": {"it": "Accesso remoto (il tunnel verso la WebUI da fuori)", "en": "Remote access (the tunnel to the WebUI from outside)"},
}
RECOMMENDED = ("aurora-api.service", "aurora-harvester.service", "aurora-rem.service", "aurora-sentinel.service")
# the page's other choices (owner, 30 Oct: «configurazione completa… anche per le richieste dns… molto
# personalizzabile ma semplice… con relative recommended»), with what is recommended
OPTIONS = {"killswitch": True,        # the tunnel down: Aurora offline rather than on the normal line
           "failover": True,          # a profile fails: the next one, by itself
           "dns": "provider",         # Aurora's names: "provider" (the tunnel's, pushed) or "custom" (dns_servers)
           "dns_servers": [],         # custom: asked through the tunnel
           "reset_h": 2}              # the connection made again every so many hours, 0 never (owner, 30 Oct: «ogni 2 ore»)
KEEPALIVE = "keepalive 10 60"         # a ping every 10 s, the tunnel made again after 60 s of silence: it never falls idle
                                      # (owner, 30 Oct: «il keep alive del tunnel se no cade se non si utilizza»)

# a client's connection: nothing that runs a program, writes a file, sets routes or reads another file
KEEP = {"client", "dev-type", "proto", "remote", "remote-random", "port", "rport", "nobind", "persist-key", "persist-tun",
        "resolv-retry", "connect-retry", "connect-retry-max", "connect-timeout", "server-poll-timeout", "tls-client",
        "remote-cert-tls", "verify-x509-name", "key-direction", "cipher", "data-ciphers", "data-ciphers-fallback", "auth",
        "tls-version-min", "tls-cipher", "tls-ciphersuites", "reneg-sec", "tun-mtu", "fragment", "mssfix", "sndbuf",
        "rcvbuf", "fast-io", "ping", "ping-restart", "ping-exit", "keepalive", "explicit-exit-notify", "pull", "verb",
        "mute", "mute-replay-warnings", "auth-nocache", "float", "hand-window", "tran-window", "replay-window"}
BLOCKS = ("ca", "cert", "key", "tls-auth", "tls-crypt", "tls-crypt-v2", "extra-certs")
ADDED = ("dev {dev}", "dev-type tun", "route-nopull", "pull-filter ignore \"redirect-gateway\"",
         "pull-filter ignore \"route\"", "pull-filter ignore \"block-outside-dns\"", "mark {mark}",
         "auth-user-pass {auth}", "auth-nocache", "script-security 2", "up {hook}", "down {hook}", "up-restart",
         "status {status} 10")


# ---- where ------------------------------------------------------------------------------------------------------------
def folder(cfg: sys_config.Config) -> Path:
    d = cfg.path("AURORA_STATUS_DIR") / "vpn"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(path: Path, data) -> None:
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


# ---- an .ovpn adapted -------------------------------------------------------------------------------------------------
def adapt(text: str) -> tuple[str, list[str]]:
    """(the profile kept, the directives dropped). Raises ValueError for a file that is no client's connection."""
    if len(text) > MAX_OVPN:
        raise ValueError(f"an .ovpn of at most {MAX_OVPN // 1024} kB")
    out, dropped, block, seen = [], [], None, set()
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if block:
            out.append(raw.rstrip())
            if line == f"</{block}>":
                block = None
            continue
        if not line or line.startswith(("#", ";")):
            continue
        m = re.fullmatch(r"<([a-z0-9-]+)>", line)
        if m:
            if m.group(1) not in BLOCKS:
                raise ValueError(f"<{m.group(1)}>: not a block of a client's connection")
            block = m.group(1)
            seen.add(block)
            out.append(line)
            continue
        word = line.split()[0].lower()
        if word == "ns-cert-type":                         # gone from OpenVPN 2.6: its successor
            out.append("remote-cert-tls server")
        elif word == "comp-lzo" and line.split()[1:2] == ["no"]:
            continue                                       # no compression asked: nothing to say
        elif word in KEEP:
            if any(c in line for c in ("`", "$(", "|", ";", "&&")):
                dropped.append(line[:80])
                continue
            out.append(line)
        else:
            dropped.append(line[:80])
    if block:
        raise ValueError(f"<{block}> not closed")
    if not any(x.split()[0] == "remote" for x in out if x and not x.startswith("<")):
        raise ValueError("no «remote»: which server?")
    if "ca" not in seen:
        raise ValueError("no <ca>: the server could not be checked")
    return "\n".join(out) + "\n", dropped


def runtime_config(profile: str, run: Path, hook: str) -> str:
    """The file openvpn reads: the profile and Aurora's own lines (its device, no routes pulled, the mark, the
    password file, the hooks that tell the unit)."""
    own = [x.format(dev=DEV, mark=MARK, auth=run / "auth", hook=hook, status=run / "status") for x in ADDED]
    if not re.search(r"^(keepalive|ping|ping-restart)\s", profile, re.M):   # the profile's own, if it has one
        own.append(KEEPALIVE)
    return profile + "\n# added by Aurora\n" + "\n".join(own) + "\n"


def traffic(status_text: str) -> dict:
    """openvpn's status file → {"bytes_in", "bytes_out"} (what came and went through the tunnel's link)."""
    out = {}
    for line in status_text.splitlines():
        k, _, v = line.partition(",")
        if k == "TCP/UDP read bytes" and v.isdigit():
            out["bytes_in"] = int(v)
        elif k == "TCP/UDP write bytes" and v.isdigit():
            out["bytes_out"] = int(v)
    return out


def place_of(profile: str) -> str:
    """The server's name of a profile (its first «remote»): what the page shows beside the name given."""
    m = re.search(r"^remote\s+(\S+)", profile, re.M)
    return m.group(1) if m else ""


# ---- profiles and the account -----------------------------------------------------------------------------------------
def _prefs(cfg) -> dict:
    p = _read(folder(cfg) / "prefs.json", {})
    return {"on": bool(p.get("on")), "default": p.get("default"), "last": p.get("last"), "unprotected": bool(p.get("unprotected")),
            "profiles": p.get("profiles") or [], "account": bool(p.get("account")),
            "through": [u for u in p.get("through", RECOMMENDED) if u in CHOICES],
            "split": list(p.get("split") or []),
            **{k: p.get(k, v) for k, v in OPTIONS.items()}}


def prefs(cfg) -> dict:
    return _prefs(cfg)


def _save_prefs(cfg, p: dict) -> dict:
    _write(folder(cfg) / "prefs.json", p)
    return p


def add(cfg: sys_config.Config, name: str, text: str) -> dict:
    """An .ovpn imported: {"id", "name", "server", "dropped"}; the first one becomes the default."""
    kept, dropped = adapt(text)
    p = _prefs(cfg)
    if len(p["profiles"]) >= MAX_PROFILES:
        raise ValueError(f"at most {MAX_PROFILES} profiles")
    name = re.sub(r"\.ovpn$", "", str(name or "").strip(), flags=re.I)[:60] or place_of(kept)
    pid = "p" + secrets.token_hex(4)
    sys_seal.write(cfg, folder(cfg) / f"{pid}.sealed", kept.encode("utf-8"), None, PURPOSE)
    item = {"id": pid, "name": name, "server": place_of(kept), "added": time.time()}
    p["profiles"].append(item)
    p["default"] = p["default"] or pid
    _save_prefs(cfg, p)
    return {**item, "dropped": dropped}


def profile(cfg: sys_config.Config, pid: str) -> str:
    return sys_seal.read(cfg, folder(cfg) / f"{pid}.sealed", None, PURPOSE).decode("utf-8")


def remove(cfg: sys_config.Config, pid: str) -> dict:
    p = _prefs(cfg)
    if not any(x["id"] == pid for x in p["profiles"]):
        raise KeyError(pid)
    p["profiles"] = [x for x in p["profiles"] if x["id"] != pid]
    for k in ("default", "last"):
        if p[k] == pid:
            p[k] = p["profiles"][0]["id"] if p["profiles"] else None
    (folder(cfg) / f"{pid}.sealed").unlink(missing_ok=True)
    return _save_prefs(cfg, p)


def set_default(cfg: sys_config.Config, pid: str) -> dict:
    p = _prefs(cfg)
    if not any(x["id"] == pid for x in p["profiles"]):
        raise KeyError(pid)
    p["default"] = pid
    return _save_prefs(cfg, p)


def set_account(cfg: sys_config.Config, user: str, password: str) -> dict:
    """The provider's user name and password for the manual configuration (one pair for all its files), sealed."""
    user, password = str(user or "").strip(), str(password or "")
    if not user or not password or "\n" in user + password or len(user + password) > 512:
        raise ValueError("a user name and a password, one line each")
    sys_seal.write(cfg, folder(cfg) / "account.sealed", f"{user}\n{password}\n".encode("utf-8"), None, PURPOSE)
    p = _prefs(cfg)
    p["account"] = True
    return _save_prefs(cfg, p)


def account(cfg: sys_config.Config) -> str:
    return sys_seal.read(cfg, folder(cfg) / "account.sealed", None, PURPOSE).decode("utf-8")


def want(cfg: sys_config.Config, **changes) -> dict:
    """What the owner wants: on (bool), unprotected (bool: the normal line until the tunnel is back), or the profile
    to use now (it becomes the default: the last one used is the default — the owner may tick another)."""
    p = _prefs(cfg)
    if "on" in changes:
        p["on"] = bool(changes["on"])
        if not p["on"]:
            p["unprotected"] = False
    if "unprotected" in changes:
        p["unprotected"] = bool(changes["unprotected"])
    if changes.get("use"):
        if not any(x["id"] == changes["use"] for x in p["profiles"]):
            raise KeyError(changes["use"])
        p["use"] = changes["use"]
        p["on"] = True
    return _save_prefs(cfg, p)


def set_through(cfg: sys_config.Config, units: list[str]) -> dict:
    """The services whose traffic passes through the tunnel (CHOICES); the others keep the normal line."""
    bad = [u for u in units if u not in CHOICES]
    if bad:
        raise ValueError(f"not a choice: {', '.join(bad)}")
    p = _prefs(cfg)
    p["through"] = [u for u in CHOICES if u in units]
    return _save_prefs(cfg, p)


DOMAIN = re.compile(r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def set_split(cfg: sys_config.Config, domains: list[str]) -> dict:
    """The domains kept on the normal network (net_vpn_dns): resolved by the home's DNS, reached by the normal line;
    their subdomains too. At most 50."""
    out = []
    for d in domains:
        d = str(d).strip().lower().rstrip(".").removeprefix("*.")
        if not DOMAIN.match(d):
            raise ValueError(f"not a domain: {d}")
        if d not in out:
            out.append(d)
    p = _prefs(cfg)
    p["split"] = out[:50]
    return _save_prefs(cfg, p)


def set_options(cfg: sys_config.Config, **o) -> dict:
    """killswitch / failover (bool), dns ("provider" | "custom"), dns_servers (up to 3 addresses)."""
    import ipaddress
    p = _prefs(cfg)
    for k in ("killswitch", "failover"):
        if k in o:
            p[k] = bool(o[k])
    if "dns" in o:
        if o["dns"] not in ("provider", "custom"):
            raise ValueError("dns: provider or custom")
        p["dns"] = o["dns"]
    if "dns_servers" in o:
        servers = []
        for s in o["dns_servers"] or []:
            try:
                a = ipaddress.ip_address(str(s).strip())
            except ValueError:
                raise ValueError(f"not an address: {s}") from None
            if a.version != 4:
                raise ValueError(f"{s}: an IPv4 address (the tunnel carries IPv4)")
            servers.append(str(a))
        p["dns_servers"] = servers[:3]
    if "reset_h" in o:
        try:
            h = int(o["reset_h"])
        except (TypeError, ValueError):
            raise ValueError("reset: hours, 0 for never") from None
        if not 0 <= h <= 48:
            raise ValueError("reset: from 0 (never) to 48 hours")
        p["reset_h"] = h
    if p["dns"] == "custom" and not p["dns_servers"]:
        raise ValueError("custom DNS: at least one address")
    return _save_prefs(cfg, p)


def recommended(cfg: sys_config.Config) -> dict:
    """Every choice back to the recommended: what passes, the options, the installation's own domain kept home."""
    p = _prefs(cfg)
    p.update({"through": list(RECOMMENDED), **{k: (list(v) if isinstance(v, list) else v) for k, v in OPTIONS.items()}})
    p["split"] = list(dict.fromkeys(p["split"] + suggested_split(cfg)))
    return _save_prefs(cfg, p)


def upstream(p: dict, pushed: list[str]) -> list[str]:
    """The servers Aurora's names are asked of, through the tunnel: the custom ones, or the pushed ones."""
    return list(p.get("dns_servers") or []) if p.get("dns") == "custom" else list(pushed or [])


def suggested_split(cfg: sys_config.Config) -> list[str]:
    """The installation's own domain (its devices' panels often live under it, at private addresses)."""
    d = str(cfg.values.get("AURORA_DOMAIN") or "").lower().strip(".")
    parts = d.split(".")
    return [".".join(parts[-2:])] if len(parts) >= 2 and DOMAIN.match(d) and not d.endswith(".local") else []


def bypass(p: dict) -> list[str]:
    """The services left on the normal line: every choice not ticked."""
    return [u for u in CHOICES if u not in (p.get("through") or [])]


def order(p: dict, failed: set[str] | None = None) -> list[str]:
    """The profiles in the order they are tried: the one asked now, the default, the last used, the rest as added;
    the ones that failed in this round left out."""
    ids = [x["id"] for x in p.get("profiles") or []]
    first = [x for x in (p.get("use"), p.get("default"), p.get("last")) if x in ids]
    return [x for x in dict.fromkeys(first + ids) if x not in (failed or set())]


# ---- the state the unit writes ----------------------------------------------------------------------------------------
def state(cfg: sys_config.Config) -> dict:
    """{"phase": off|connecting|up|retrying|failed|unprotected, "profile", "since", "ip", "dns", "tried", "error"}."""
    return _read(folder(cfg) / "state.json", {"phase": "off"})


def write_state(cfg: sys_config.Config, **s) -> dict:
    s = {**s, "at": time.time()}
    _write(folder(cfg) / "state.json", s)
    return s


def resolv(cfg: sys_config.Config) -> Path:
    return folder(cfg) / "resolv.conf"


def machine_resolv() -> str:
    """The machine's own resolver file as it is (its search domains: the LAN's short names), or the stub's lines."""
    try:
        return Path("/run/systemd/resolve/stub-resolv.conf").read_text(encoding="utf-8") or STUB
    except OSError:
        return STUB


def set_dns(cfg: sys_config.Config, servers: list[str] | None) -> None:
    """The services' resolver: the tunnel's servers, or the machine's. Written in place: the units bind this file
    over /etc/resolv.conf, a new file (a new inode) would not reach them."""
    text = ("".join(f"nameserver {s}\n" for s in servers[:3]) + "options edns0\n") if servers else machine_resolv()
    f = resolv(cfg)
    if not f.exists():
        f.write_text(text, encoding="utf-8")
        f.chmod(0o664)                                 # read by every service; written by the VPN's unit (the group)
        return
    with open(f, "r+", encoding="utf-8") as h:
        h.seek(0)
        h.write(text)
        h.truncate()


# ---- the routes (the unit runs them; here as lists, so they are tested without touching the network) -----------------
def rules(uid: int, add_: bool = True) -> list[list[str]]:
    """The three rules: the marked packets (the tunnel's own, the remote access) by the main table; the service
    user's local routes (LAN, loopback) by the main table but its default; the rest of its traffic by TABLE."""
    op = "add" if add_ else "del"
    out = []
    for fam in ("-4", "-6"):
        out += [["ip", fam, "rule", op, "priority", str(PRIO[0]), "fwmark", hex(MARK), "lookup", "main"],
                ["ip", fam, "rule", op, "priority", str(PRIO[1]), "uidrange", f"{uid}-{uid}", "lookup", "main",
                 "suppress_prefixlength", "0"],
                ["ip", fam, "rule", op, "priority", str(PRIO[2]), "uidrange", f"{uid}-{uid}", "lookup", str(TABLE)]]
    return out


def table(up: bool) -> list[list[str]]:
    """The table: into the tunnel when it is up; «unreachable» when it is not (Aurora fails at once, never leaks).
    IPv6: always unreachable (the providers' .ovpn carry IPv4), so nothing of hers leaves by IPv6 around it."""
    v4 = ["ip", "-4", "route", "replace", "default", "dev", DEV, "table", str(TABLE)] if up else \
        ["ip", "-4", "route", "replace", "unreachable", "default", "table", str(TABLE)]
    return [v4, ["ip", "-6", "route", "replace", "unreachable", "default", "table", str(TABLE)]]


def nft_exclusions(units) -> str:
    """nftables: the packets of the services not ticked, and those to the public addresses of the domains kept on
    the normal network (split4/split6, filled by the resolver with their TTL), marked: the first rule keeps them on
    the normal line."""
    marks = "".join(f'    socket cgroupv2 level 2 "system.slice/{u}" meta mark set {hex(MARK)}\n' for u in units)
    return ("table inet aurora_vpn {\n"
            "  set split4 { type ipv4_addr; flags timeout; }\n  set split6 { type ipv6_addr; flags timeout; }\n"
            "  chain out {\n    type route hook output priority mangle; policy accept;\n"
            f"{marks}    ip daddr @split4 meta mark set {hex(MARK)}\n    ip6 daddr @split6 meta mark set {hex(MARK)}\n"
            "  }\n}\n")


def nft_split(found: list[tuple[str, int]]) -> list[list[str]]:
    """The commands that put the public addresses of a kept domain on the normal line, for their TTL (1 min at least)."""
    out = []
    for addr, ttl in found:
        s = "split6" if ":" in addr else "split4"
        out.append(["nft", "add", "element", "inet", "aurora_vpn", s, f"{{ {addr} timeout {max(60, min(ttl, 86400))}s }}"])
    return out

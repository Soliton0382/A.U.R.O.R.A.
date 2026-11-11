# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The network of a plugin Aurora wrote herself: never the machine's, only a proxy to the places the owner allowed
(owner, 9 Nov: «se aurora si crea un plugin "per evadere" e io firmo lei diventa indipendente e non va bene»).

A forged plugin's cage has no network of its own (--unshare-net). Its HTTP and HTTPS go to the cage's 127.0.0.1:<port>
(HTTP_PROXY, HTTPS_PROXY), carried by a unix socket to this proxy in Aurora's process, which lets a connection through
only to:
  - the host of each URL in the plugin's own settings (AURORA_<NAME>_…: the owner typed them, e.g. Home Assistant's
    address on the LAN), at that URL's port — never a link-local, multicast or reserved address (C571);
  - the public hosts the manifest lists in "hosts" (shown to the owner when he approves the plugin), port 443 or 80,
    resolved to public addresses only; so too the host of a URL the manifest only proposes for a setting (its
    «recommended»: nobody typed it, C571);
and never to Aurora's own services on this machine (the API, the models, the reasoner, HTTPS, Caddy's admin). Every
connection is written in the plugins' log, let through or refused. Each plugin gets its own socket, and the cage
sees only its own (plg_sandbox hides the others): one plugin never borrows another's way out.
"""
from __future__ import annotations

import ipaddress
import os
import re
import socket
import threading
from pathlib import Path
from urllib.parse import urlsplit

from . import sys_config, sys_log

HOST = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_served: dict[str, Path] = {}
_lock = threading.Lock()


def _urls(value: str) -> list[tuple[str, int]]:
    out = []
    for one in re.split(r"[\s,]+", value.strip()):
        u = urlsplit(one)
        if u.scheme in ("http", "https") and u.hostname:
            out.append((u.hostname.lower(), u.port or (443 if u.scheme == "https" else 80)))
    return out


def _suggested(manifest: dict | None) -> dict[str, str]:
    """setting → the value the manifest itself proposes for it (settings_spec «recommended»)."""
    return {str(s.get("key", "")): str(s.get("recommended", "") or "").strip()
            for s in (manifest or {}).get("settings_spec") or [] if isinstance(s, dict)}


def own_urls(name: str, cfg: sys_config.Config, manifest: dict | None = None) -> list[tuple[str, int]]:
    """(host, port) of every URL in the plugin's own settings, as the owner set them. A value that is only the
    manifest's own proposal was never typed by him (C571: a setting left empty reads its «recommended», and a plugin
    proposing http://<a LAN address> reached it as «the owner's»): not here — see suggested_hosts."""
    prefix, theirs, suggested = f"AURORA_{name.upper()}_", sys_config.others_keys(name), _suggested(manifest)
    out = []
    raw = dict(cfg.raw) or sys_config.parse_env(cfg.env_file.read_text(encoding="utf-8"), str(cfg.env_file))
    for k, v in raw.items():
        if not k.startswith(prefix) or k in theirs or not isinstance(v, str) or "://" not in v:
            continue
        if v.strip() == suggested.get(k):
            continue
        out += _urls(v)
    return sorted(set(out))


def suggested_hosts(manifest: dict) -> list[str]:
    """The hosts of the URLs the manifest proposes for its own settings: allowed like its «hosts» — a public name
    resolved to public addresses, port 443 or 80 — never as an address of the owner's (C571)."""
    name = str(manifest.get("name", ""))
    prefix, theirs = f"AURORA_{name.upper()}_", sys_config.others_keys(name)
    return sorted({h for k, v in _suggested(manifest).items() if k.startswith(prefix) and k not in theirs
                   for h, _ in _urls(v) if HOST.match(h)})


def declared_hosts(manifest: dict) -> list[str]:
    return sorted({str(h).lower().strip(".") for h in manifest.get("hosts") or [] if HOST.match(str(h).lower().strip("."))})


def _aurora_ports(cfg: sys_config.Config) -> set[int]:
    ports = set()
    for k in ("AURORA_API_PORT", "AURORA_LLM_PORT", "AURORA_MODELS_PORT", "AURORA_HTTPS_PORT", "AURORA_HTTP_PORT"):
        try:
            ports.add(int(cfg[k]))
        except (KeyError, TypeError, ValueError):
            pass
    return ports | {2019}                                # Caddy's admin


def _mine(addr: str) -> bool:
    """This machine's own address (loopback or one of its interfaces)."""
    ip = ipaddress.ip_address(addr)
    if ip.is_loopback or ip.is_unspecified:
        return True
    try:
        return addr in {a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None)}
    except OSError:
        return False


def _never(addr: str) -> bool:
    """Addresses no plugin's proxy reaches whoever set them (C571): link-local (the cloud metadata service lives
    there), multicast, unspecified, reserved. A LAN or loopback address stays the owner's to type (his Home Assistant)."""
    ip = ipaddress.ip_address(addr.split("%")[0])
    return ip.is_link_local or ip.is_multicast or ip.is_unspecified or (ip.is_reserved and not ip.is_loopback)


def decide(host: str, port: int, owner: list[tuple[str, int]], public: list[str], cfg: sys_config.Config) -> tuple[str, str]:
    """(address to connect to, "") when allowed, ("", why) when not."""
    host = host.lower().strip(".")
    by_owner = (host, port) in owner
    by_manifest = port in (80, 443) and host in public     # the exact name only (audit 9 Nov: «workers.dev» covered
                                                            # every subdomain, an attacker's too)
    if not (by_owner or by_manifest):
        return "", f"{host}:{port} not among the places allowed"
    try:
        addrs = sorted({a[4][0] for a in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)})
    except OSError as e:
        return "", f"{host}: {e}"
    if not addrs:
        return "", f"{host}: no address"
    if port in _aurora_ports(cfg) and any(_mine(a) for a in addrs):
        return "", f"{host}:{port} is Aurora's own service"
    if any(_never(a) for a in addrs):                    # C571: not even typed by the owner
        return "", f"{host} resolves to a link-local, multicast or reserved address: never reached"
    if not by_owner and not all(ipaddress.ip_address(a).is_global for a in addrs):
        return "", f"{host} resolves to a private address: only an address the owner set may be private"
    return addrs[0], ""


def _pipe(a: socket.socket, b: socket.socket) -> None:
    try:
        while data := a.recv(65536):
            b.sendall(data)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def _handle(client: socket.socket, name: str, owner, public, cfg) -> None:
    log = sys_log.get_logger("plugins")
    try:
        client.settimeout(30)
        head = b""
        while b"\r\n\r\n" not in head and len(head) < 65536:
            chunk = client.recv(4096)
            if not chunk:
                return client.close()
            head += chunk
        line, _, rest = head.partition(b"\r\n")
        method, target, _version = line.decode("latin-1").split(" ", 2)
        if method == "CONNECT":
            host, _, p = target.rpartition(":")
            port = int(p)
        else:
            u = urlsplit(target)
            if u.scheme != "http" or not u.hostname:
                raise ValueError("only absolute http:// requests or CONNECT")
            host, port = u.hostname, u.port or 80
        addr, why = decide(host, port, owner, public, cfg)
        if why:
            log.warning("plugin %s: network refused: %s", name, why)
            sys_log.trace("plugins", "plugin.net_refused", {"plugin": name, "host": host, "port": port, "why": why})
            client.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            return client.close()
        upstream = socket.create_connection((addr, port), timeout=20)
        client.settimeout(None)
        upstream.settimeout(None)
        log.info("plugin %s: network to %s:%d", name, host, port)
        if method == "CONNECT":
            client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            extra = rest.partition(b"\r\n\r\n")[2]
        else:                                        # one request per connection, the path only, no proxy headers
            u = urlsplit(target)
            path = (u.path or "/") + (f"?{u.query}" if u.query else "")
            headers = [h for h in rest.partition(b"\r\n\r\n")[0].split(b"\r\n")
                       if h and not h.lower().startswith((b"proxy-", b"connection:"))]
            extra = (f"{method} {path} {_version}\r\n".encode("latin-1") + b"\r\n".join(headers)
                     + b"\r\nConnection: close\r\n\r\n" + rest.partition(b"\r\n\r\n")[2])
        if extra:
            upstream.sendall(extra)
        threading.Thread(target=_pipe, args=(client, upstream), daemon=True).start()
        threading.Thread(target=_pipe, args=(upstream, client), daemon=True).start()
    except (OSError, ValueError) as e:
        log.warning("plugin %s: proxy: %s", name, e)
        try:
            client.sendall(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        except OSError:
            pass
        client.close()


def _serve(listener: socket.socket, name: str, owner, public, cfg) -> None:
    while True:
        try:
            client, _ = listener.accept()
        except OSError:
            return
        threading.Thread(target=_handle, args=(client, name, owner, public, cfg), daemon=True).start()


def folder(cfg: sys_config.Config) -> Path:
    return cfg.path("AURORA_STATUS_DIR") / "plugins" / "bridge" / str(os.getpid())


def bridge(name: str, manifest: dict, cfg: sys_config.Config) -> tuple[Path, int]:
    """This plugin's own proxy socket in this process (served from the first call on), and the cage's port for it."""
    owner = own_urls(name, cfg, manifest)
    public = sorted(set(declared_hosts(manifest)) | set(suggested_hosts(manifest)))
    import hashlib                                       # short: a unix socket's path has 108 bytes at most
    key = hashlib.sha256(repr((name, cfg.user, owner, public)).encode()).hexdigest()[:12]
    sock = folder(cfg) / f"n{key}.sock"
    with _lock:
        if str(sock) not in _served:
            sock.parent.mkdir(parents=True, exist_ok=True)
            if sock.exists():
                sock.unlink()
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            srv.bind(str(sock))
            srv.listen(16)
            threading.Thread(target=_serve, args=(srv, name, owner, public, cfg), daemon=True).start()
            _served[str(sock)] = sock
    return sock, 3128


def environment(port: int) -> list[str]:
    """bwrap's --setenv for the proxy, both spellings the HTTP libraries read."""
    url = f"http://127.0.0.1:{port}"
    out = []
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        out += ["--setenv", k, url]
    for k in ("NO_PROXY", "no_proxy"):
        out += ["--setenv", k, ""]
    return out

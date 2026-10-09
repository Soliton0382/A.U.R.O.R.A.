# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's HTTPS (Caddy, aurora-https): the Caddyfile written from the settings, the certificate in use, the owner's own
certificate installed from the WebUI, and the way back to Caddy's local authority.

  names     AURORA_DOMAIN and AURORA_DOMAIN_ALIASES (this machine's address on the home network, name.local): one
            site for all, so the phone reaches Aurora by an address it can resolve.
  internal  Caddy's local authority signs the certificate; a phone trusts it after installing its root certificate,
            served at http://<name>/aurora-ca.crt (a public certificate: nothing secret in it).
  files     the owner's certificate (fullchain + key, AURORA_TLS_CERT / AURORA_TLS_KEY), checked before use: the key
            must be the certificate's, it must be valid now and name AURORA_DOMAIN.
A change is written, validated by caddy and reloaded (systemctl reload aurora-https: allowed to the service user by
50-aurora.rules, no sudo); anything that fails puts back what was there.
"""
from __future__ import annotations

import datetime as dt
import ipaddress
import os
import pwd
import subprocess
from pathlib import Path
from string import Template

from . import sys_config, sys_log

CA_PATH = "/aurora-ca.crt"
CADDYFILE = Template("""# Generated from .env by sys/core/aurora/net_https.py — edit .env (or the 🔒 HTTPS page), not this file.
{
	admin $admin
	grace_period 5s
	auto_https disable_redirects
	default_sni $default_sni
	http_port $http_port
	https_port $https_port
	log {
		output file $log_dir/caddy.log {
			roll_size ${max_mb}MiB
			roll_keep_for ${keep_hours}h
		}
		level INFO
	}
}

$sites {
	$tls
	encode gzip zstd
	reverse_proxy $api {
		transport http {
			dial_timeout 10s
			read_timeout 900s
			write_timeout 900s
			response_header_timeout 900s
		}
		flush_interval -1
	}
	# project previews (/v1/preview/*): framed by the WebUI only, sandboxed by the API's own CSP (opaque origin)
	@app not path /v1/preview/*
	header /v1/preview/* {
		Strict-Transport-Security "max-age=31536000; includeSubDomains"
		X-Content-Type-Options nosniff
		Referrer-Policy no-referrer
		X-Frame-Options SAMEORIGIN
		-Server
	}
	header @app {
		Strict-Transport-Security "max-age=31536000; includeSubDomains"
		X-Content-Type-Options nosniff
		Referrer-Policy strict-origin-when-cross-origin
		X-Frame-Options DENY
		Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' data: blob:; connect-src 'self'; worker-src 'self'; manifest-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
		-Server
	}
}

$http_sites {
$ca	handle {
		redir https://{host}$https_suffix{uri} permanent
	}
}
""")


class HttpsError(RuntimeError):
    """A change refused or failed; what was there is back."""


def _v(cfg: sys_config.Config, over: dict, key: str):
    return over[key] if key in over else cfg[key]


def names(cfg: sys_config.Config, **over) -> list[str]:
    """The names Aurora answers to: the domain first, then the aliases, each once."""
    out = [str(_v(cfg, over, "AURORA_DOMAIN")).strip()]
    out += [n.strip() for n in str(_v(cfg, over, "AURORA_DOMAIN_ALIASES") or "").split(",")]
    return list(dict.fromkeys(n for n in out if n))


def ca_dir(cfg: sys_config.Config) -> Path:
    """Where Caddy (run as the service user, no XDG_DATA_HOME) keeps its local authority."""
    home = Path(pwd.getpwnam(sys_config.service_user(cfg)).pw_dir)
    return home / ".local" / "share" / "caddy" / "pki" / "authorities" / "local"


def render(cfg: sys_config.Config, **over) -> str:
    """The Caddyfile; `over` holds settings not yet in this process's configuration (a change being applied)."""
    https_port, http_port = int(_v(cfg, over, "AURORA_HTTPS_PORT")), int(_v(cfg, over, "AURORA_HTTP_PORT"))
    mode = str(_v(cfg, over, "AURORA_TLS_MODE"))
    hosts = names(cfg, **over)
    ca = ""
    if mode == "internal":                           # the phone's first step: the root certificate, over plain HTTP
        ca = (f"\thandle {CA_PATH} {{\n\t\troot * {ca_dir(cfg)}\n\t\trewrite * /root.crt\n"
              "\t\theader Content-Type application/x-x509-ca-cert\n\t\tfile_server\n\t}\n")
    return CADDYFILE.substitute(
        admin=cfg["AURORA_CADDY_ADMIN"], http_port=http_port, https_port=https_port,
        # a client that opens an address sends no name (SNI): this certificate then, not the one Caddy would pick by
        # the address it was reached at — behind Docker that address is the container's own (C221, «internal error»)
        default_sni=hosts[0] if hosts else "localhost",
        https_suffix="" if https_port == 443 else f":{https_port}",
        log_dir=cfg.path("AURORA_LOG_DIR") / "https", max_mb=cfg["AURORA_LOG_MAX_MB"],
        keep_hours=cfg["AURORA_LOG_RETENTION_DAYS"] * 24,
        sites=", ".join(f"{_host(h)}:{https_port}" for h in hosts),
        http_sites=", ".join(f"http://{_host(h)}:{http_port}" for h in hosts),
        ca=ca,
        tls=(f"tls {cfg.path('AURORA_TLS_CERT')} {cfg.path('AURORA_TLS_KEY')}" if mode == "files" else "tls internal"),
        api=f"{cfg['AURORA_API_HOST']}:{cfg['AURORA_API_PORT']}")


def _host(name: str) -> str:
    """An IPv6 address in brackets, as an address with a port needs."""
    try:
        return f"[{name}]" if ipaddress.ip_address(name).version == 6 else name
    except ValueError:
        return name


def caddyfile(cfg: sys_config.Config) -> Path:
    return cfg.path("AURORA_HTTPS_DIR") / "Caddyfile"


def write(cfg: sys_config.Config, **over) -> Path:
    """Write the Caddyfile and have caddy validate it; an invalid one is not left in place."""
    f = caddyfile(cfg)
    f.parent.mkdir(parents=True, exist_ok=True)      # not in a fresh clone (C211)
    (cfg.path("AURORA_LOG_DIR") / "https").mkdir(parents=True, exist_ok=True)
    before = f.read_text(encoding="utf-8") if f.exists() else None
    f.write_text(render(cfg, **over), encoding="utf-8")
    check = subprocess.run([cfg["AURORA_CADDY_BIN"], "validate", "--config", str(f), "--adapter", "caddyfile"],
                           capture_output=True, text=True, timeout=60)
    if check.returncode != 0:
        if before is not None:
            f.write_text(before, encoding="utf-8")
        raise HttpsError(f"caddy validate: {(check.stderr or check.stdout).strip()[-600:]}")
    return f


def reload(verb: str = "reload") -> None:
    """Caddy takes the new Caddyfile: reload (no interruption), or restart when the ports change — Ubuntu's Caddy 2.6
    panicked on the reload after a refused one (the test VM, 9 Oct: «missing cancel error»)."""
    r = subprocess.run(["systemctl", verb, "aurora-https"], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise HttpsError(f"systemctl {verb} aurora-https: {(r.stderr or r.stdout).strip()[-300:]}")


# ---- certificates -----------------------------------------------------------------------------------------------

def _covers(pattern: str, name: str) -> bool:
    pattern, name = pattern.lower().rstrip("."), name.lower().rstrip(".")
    if pattern.startswith("*."):                     # one label only, as browsers match it
        head, _, rest = name.partition(".")
        return bool(head) and rest == pattern[2:]
    return pattern == name


def describe(pem: bytes) -> dict:
    """The certificate a PEM file starts with (the leaf of a fullchain): who it names, who signed it, until when."""
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    cert = x509.load_pem_x509_certificates(pem)[0]
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        dns = san.get_values_for_type(x509.DNSName)
        ips = [str(i) for i in san.get_values_for_type(x509.IPAddress)]
    except x509.ExtensionNotFound:
        dns, ips = [], []
    cn = [a.value for a in cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)]
    issuer = [a.value for a in cert.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)]
    until = cert.not_valid_after_utc
    return {"names": list(dict.fromkeys(dns + ips + ([] if dns or ips else cn))), "issuer": issuer[0] if issuer else "",
            "not_before": cert.not_valid_before_utc.isoformat(), "not_after": until.isoformat(),
            "days_left": (until - dt.datetime.now(dt.UTC)).days}


def check_pair(cert_pem: bytes, key_pem: bytes, domain: str) -> dict:
    """Refuses a certificate Caddy could not serve for `domain`: not PEM, a key that is not its own, a key with a
    password, expired or not yet valid, not naming the domain. Returns describe() of it."""
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    try:
        certs = x509.load_pem_x509_certificates(cert_pem)
    except ValueError:
        raise HttpsError("the certificate is not a PEM file (fullchain.pem, -----BEGIN CERTIFICATE-----)") from None
    try:
        key = serialization.load_pem_private_key(key_pem, password=None)
    except TypeError:
        raise HttpsError("the key is protected by a password: Caddy needs it without") from None
    except ValueError:
        raise HttpsError("the key is not a PEM private key (privkey.pem, -----BEGIN ... PRIVATE KEY-----)") from None
    spki = serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    if certs[0].public_key().public_bytes(*spki) != key.public_key().public_bytes(*spki):
        raise HttpsError("the key is not this certificate's")
    info = describe(cert_pem)
    now = dt.datetime.now(dt.UTC)
    if certs[0].not_valid_after_utc <= now:
        raise HttpsError(f"the certificate expired on {info['not_after'][:10]}")
    if certs[0].not_valid_before_utc > now:
        raise HttpsError(f"the certificate is valid only from {info['not_before'][:10]}")
    if not any(_covers(n, domain) for n in info["names"]):
        raise HttpsError(f"the certificate names {', '.join(info['names']) or 'nothing'}, not {domain}")
    return info


def _write_private(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def fresh(cfg: sys_config.Config) -> sys_config.Config:
    """The machine's settings as they are in its .env now: a service keeps the ones it started with, and a second change
    computed from those would undo the first (the aliases set, then a certificate: the aliases gone)."""
    base = getattr(cfg, "base", None) or cfg
    return sys_config.load(base.env_file, check_root=False)


def _settings(cfg: sys_config.Config, changes: dict) -> None:
    sys_config.write_env(cfg.env_file, {k: str(v) for k, v in changes.items()})


def _apply(cfg: sys_config.Config, changes: dict, undo, verb: str = "reload") -> None:
    """Settings, Caddyfile, reload; any failure undoes all three. A refused reload leaves Caddy on the old file; a
    refused restart has stopped it, so it is started again on the old one."""
    before = {k: str(cfg[k]) for k in changes}
    try:
        write(cfg, **changes)
        _settings(cfg, changes)
        reload(verb)
    except Exception:
        undo()
        _settings(cfg, before)
        try:
            write(cfg, **before)
            if verb == "restart":
                reload("restart")
        except HttpsError:
            pass
        raise


def install_cert(cfg: sys_config.Config, cert_pem: bytes, key_pem: bytes) -> dict:
    """The owner's certificate in use (mode files); the previous files are put back if it does not work."""
    cfg = fresh(cfg)
    info = check_pair(cert_pem, key_pem, str(cfg["AURORA_DOMAIN"]))
    cert, key = cfg.path("AURORA_TLS_CERT"), cfg.path("AURORA_TLS_KEY")
    saved = {p: p.read_bytes() for p in (cert, key) if p.exists()}

    def undo():
        for p in (cert, key):
            if p in saved:
                _write_private(p, saved[p])
            elif p.exists():
                p.unlink()
    _write_private(cert, cert_pem)
    _write_private(key, key_pem)
    _apply(cfg, {"AURORA_TLS_MODE": "files"}, undo)
    sys_log.get_logger("api").info("audit: HTTPS certificate of the owner in use (%s, until %s)",
                                   ", ".join(info["names"][:4]), info["not_after"][:10])
    return {"mode": "files", "certificate": info,
            "not_covered": [n for n in names(cfg) if not any(_covers(p, n) for p in info["names"])]}


def use_internal(cfg: sys_config.Config) -> dict:
    """Back to Caddy's local authority (the owner's files stay where they are)."""
    cfg = fresh(cfg)
    _apply(cfg, {"AURORA_TLS_MODE": "internal"}, lambda: None)
    sys_log.get_logger("api").info("audit: HTTPS back to Caddy's local authority")
    return {"mode": "internal"}


def set_aliases(cfg: sys_config.Config, aliases: list[str]) -> dict:
    """The other names of this machine (its address on the home network, name.local)."""
    cfg = fresh(cfg)
    clean = []
    for a in aliases:
        a = a.strip().lower()
        if not a:
            continue
        try:
            ipaddress.ip_address(a)
        except ValueError:
            if not all(part and len(part) < 64 and part.replace("-", "").isalnum() for part in a.split(".")):
                raise HttpsError(f"not a name or an address: {a}") from None
        clean.append(a)
    _apply(cfg, {"AURORA_DOMAIN_ALIASES": ",".join(dict.fromkeys(clean))}, lambda: None)
    return {"names": names(cfg, AURORA_DOMAIN_ALIASES=",".join(clean))}


def _in_use(port: int) -> bool:
    """Something already listens on `port` (another web server, another service). A port below 1024 that this
    process may not bind is still found when something answers on it (sshd on 22: the test VM, 9 Oct)."""
    import socket
    with socket.socket() as probe:                     # anything that answers here (any port, no privilege needed)
        probe.settimeout(1)
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            return True
    for family, host in ((socket.AF_INET, "0.0.0.0"), (socket.AF_INET6, "::")):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as s:
                s.bind((host, port))
        except PermissionError:
            return False
        except OSError as e:
            if family == socket.AF_INET6 and e.errno in (47, 97, 10047):  # no IPv6 here (macOS, Linux, Windows)
                continue
            return True
    return False


def set_ports(cfg: sys_config.Config, https_port: int, http_port: int) -> dict:
    """Aurora on other ports (owner, 9 Oct: «magari io voglio far usare ad aurora un'altra porta perchè sulla 443 ho altri
    servizi»). Checked first — numbers, Aurora's own ports, a port already taken, the right to a port below 1024 — then
    the Caddyfile, the settings and Caddy's reload, all put back on a failure. The API restarts afterwards (the health
    check and the users' links read the port when they start)."""
    if os.environ.get("AURORA_DOCKER"):             # the ports are Docker's mapping: chosen outside the container
        raise HttpsError("in Docker the ports are chosen in docker/.env (AURORA_HTTPS_PORT, AURORA_HTTP_PORT), then: "
                         "docker compose -f docker/compose.yaml up -d")
    cfg = fresh(cfg)
    old = (int(cfg["AURORA_HTTPS_PORT"]), int(cfg["AURORA_HTTP_PORT"]))
    new = (int(https_port), int(http_port))
    if any(not 1 <= p <= 65535 for p in new) or new[0] == new[1]:
        raise HttpsError("two different ports between 1 and 65535")
    own = {int(cfg[k]) for k in ("AURORA_API_PORT", "AURORA_MODELS_PORT", "AURORA_LLM_PORT")}
    own.add(int(str(cfg["AURORA_CADDY_ADMIN"]).rsplit(":", 1)[-1]))
    if taken := sorted(set(new) & own):
        raise HttpsError(f"port {taken[0]} is one of Aurora's own services")
    unit = cfg.root / "sys" / "deploy" / "systemd" / "aurora-https.service"
    if min(new) < 1024 and unit.exists() and "CAP_NET_BIND_SERVICE" not in unit.read_text(encoding="utf-8"):
        # Caddy's unit grants the low ports only when the installer saw one (sys_install_services: low_ports)
        raise HttpsError("a port below 1024 needs the services written again: run ./install.sh (or choose 1024 or more)")
    if busy := [p for p in new if p not in old and _in_use(p)]:
        raise HttpsError(f"port {busy[0]} is already used by another program on this machine")
    if new == old:
        return {"https_port": new[0], "http_port": new[1], "urls": status(cfg)["urls"], "changed": False}
    _apply(cfg, {"AURORA_HTTPS_PORT": new[0], "AURORA_HTTP_PORT": new[1]}, lambda: None, verb="restart")
    sys_log.get_logger("api").info("audit: HTTPS on port %d (HTTP %d), was %d (%d)", *new, *old)
    restart_api_later()
    suffix = "" if new[0] == 443 else f":{new[0]}"
    return {"https_port": new[0], "http_port": new[1], "changed": True,
            "urls": [f"https://{_host(n)}{suffix}/" for n in names(cfg)]}


def restart_api_later(seconds: float = 2.0) -> None:
    """After the answer has left: the page reads the new address first."""
    import threading
    threading.Timer(seconds, lambda: subprocess.run(["systemctl", "restart", "--no-block", "aurora-api"],
                                                    capture_output=True, timeout=30)).start()


def local_addresses() -> list[str]:
    """This machine's address on its network and its name.local: what a phone at home can reach (a UDP «connect» sends
    nothing, it only picks the interface that leads out)."""
    import socket
    out = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))
            ip = s.getsockname()[0]
        if not ip.startswith("127."):
            out.append(ip)
    except OSError:
        pass
    return out + [f"{socket.gethostname().split('.')[0].lower()}.local"]


def status(cfg: sys_config.Config) -> dict:
    """What a browser meets now: the names, the mode, the certificate (the owner's, or the local authority's root)."""
    cfg = fresh(cfg)
    mode = str(cfg["AURORA_TLS_MODE"])
    port = int(cfg["AURORA_HTTPS_PORT"])
    suffix = "" if port == 443 else f":{port}"
    http = int(cfg["AURORA_HTTP_PORT"])
    out = {"mode": mode, "names": names(cfg), "urls": [f"https://{_host(n)}{suffix}/" for n in names(cfg)],
           "https_port": port, "http_port": http, "docker": bool(os.environ.get("AURORA_DOCKER")),
           "certificate": None, "ca": None, "suggest": [a for a in local_addresses() if a not in names(cfg)]}
    try:
        if mode == "files":
            out["certificate"] = describe(cfg.path("AURORA_TLS_CERT").read_bytes())
        else:
            root = ca_dir(cfg) / "root.crt"
            if root.exists():
                out["ca"] = {**describe(root.read_bytes()),
                             "urls": [f"http://{_host(n)}{'' if http == 80 else f':{http}'}{CA_PATH}"
                                      for n in names(cfg) if n != "localhost"]}
    except (OSError, ValueError, KeyError) as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out

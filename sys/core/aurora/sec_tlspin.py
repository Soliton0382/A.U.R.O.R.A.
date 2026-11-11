# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The firewall's own certificate, pinned (C567). A firewall's API usually answers with a certificate it made itself,
so the CA check is off by default (AURORA_FIREWALL_VERIFY_TLS 0) — and with it off, anyone in the middle of the LAN got
the API's password and could fake its answers. Now, with the check off, the certificate is learnt when the owner
connects the firewall (🛡️ Security, «Collega»: his click, the one moment trusted) and every later call accepts that
certificate only, before a byte of the request is sent (the TLS handshake fails: the password never leaves). A
firewall whose certificate changed (renewed, replaced) is connected again by the owner, which learns the new one.

The pins: <STATUS>/security/tls_pins.json, the services' account's (0600): not a secret, its integrity is what counts.
With the CA check on, nothing is pinned: the CA decides, as before."""
from __future__ import annotations

import hashlib
import json
import os
import ssl
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

from . import sys_config

_lock = threading.Lock()
NO_CHECK_TIME = 0x200000           # X509_V_FLAG_NO_CHECK_TIME: the exact certificate is trusted, expired or not


def _file(cfg: sys_config.Config) -> Path:
    return (cfg.base or cfg).path("AURORA_STATUS_DIR") / "security" / "tls_pins.json"


def _pins(cfg: sys_config.Config) -> dict:
    try:
        return json.loads(_file(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(cfg: sys_config.Config, pins: dict) -> None:
    f = _file(cfg)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(f".{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as h:
        json.dump(pins, h, indent=1)
    os.replace(tmp, f)


def _where(url: str) -> tuple[str, int] | None:
    u = urlparse(str(url or ""))
    if u.scheme != "https" or not u.hostname:
        return None
    return u.hostname, u.port or 443


def fingerprint(pem: str) -> str:
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()


def context(pem: str) -> ssl.SSLContext:
    """A TLS context that trusts this one certificate and nothing else (its name and dates not checked: it is the
    certificate itself that is trusted, as the owner confirmed it)."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_verify_locations(cadata=pem)
    ctx.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN | NO_CHECK_TIME
    return ctx


def learn(cfg: sys_config.Config, url: str, timeout: float = 10.0) -> str | None:
    """The owner's «Collega»: the certificate the firewall shows now becomes the pinned one. Returns its fingerprint
    (None for an http:// address)."""
    where = _where(url)
    if where is None:
        return None
    pem = ssl.get_server_certificate(where, timeout=timeout)
    with _lock:
        pins = _pins(cfg)
        pins[f"{where[0]}:{where[1]}"] = {"pem": pem, "sha256": fingerprint(pem), "at": time.time()}
        _save(cfg, pins)
    return fingerprint(pem)


def verify(cfg: sys_config.Config, url: str, ca: bool) -> bool | ssl.SSLContext:
    """What a driver passes to httpx as `verify`: True with the CA check on (or http://); the pinned certificate
    otherwise. Never pinned yet (a firewall connected before 12 Nov): learnt now, once, and said in the log."""
    where = _where(url)
    if ca or where is None:
        return True
    pin = _pins(cfg).get(f"{where[0]}:{where[1]}")
    if pin is None:
        learn(cfg, url)
        from . import sys_log
        sys_log.get_logger("security").warning("tls pin: %s:%d had none, learnt at first use (C567)", *where)
        pin = _pins(cfg).get(f"{where[0]}:{where[1]}")
    return context(pin["pem"])


def why(error: Exception) -> str:
    """A refused handshake said plainly: the owner knows what to do."""
    text = str(error)
    if "CERTIFICATE_VERIFY_FAILED" in text or "certificate verify failed" in text:
        return ("the firewall's certificate is not the one confirmed (C567): if you renewed it, connect the firewall "
                "again in 🛡️ Security; otherwise something on the network is in the middle")
    return f"the firewall does not answer: {text}"

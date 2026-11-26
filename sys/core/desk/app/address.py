# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Where the window finds Aurora (owner, 27 Nov: «se l'app viene installata sulla stessa macchina non chiede niente…
se invece non viene installata sulla stessa macchina allora utilizza il medesimo form dell'app android»).

1. Aurora on this computer (the launcher's DESK_WEB_URL, http://127.0.0.1:9700/) answers its /health: that one, asked
   nothing.
2. Else the address kept from the last time (~/.local/state/aurora-desk/address.json, 0600).
3. Else the Android app's form (connect_form.py): an IP or a name and a port, HTTPS only — the same rules as its
   Address.java, so a typed address means the same on the phone and here.
The menu's «Cambia indirizzo di Aurora» opens the form again (the launcher's --web-setup)."""
from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from desk.app import store

LOCAL = os.environ.get("DESK_WEB_URL", "http://127.0.0.1:9700/")
FILE = "address.json"


def normalize(typed: str | None) -> str | None:
    """«https://host[:port]» with no path, or None when it is not an HTTPS address with a name (Address.normalize)."""
    s = (typed or "").strip()
    if not s:
        return None
    if "://" not in s:
        s = "https://" + s
    try:
        u = urlsplit(s)
        port = u.port
    except ValueError:
        return None
    if u.scheme.lower() != "https" or not u.hostname or u.username or u.password:
        return None
    return "https://" + u.hostname.lower() + (f":{port}" if port and port != 443 else "")


def of(host: str | None, port: str | None) -> str | None:
    """The form's two fields: an IP or a name (or a whole address) and a port; an empty port is 443 (Address.of)."""
    n, p = normalize(host), (port or "").strip()
    if n is None or not p:
        return n
    if not re.fullmatch(r"[0-9]{1,5}", p) or not 1 <= int(p) <= 65535:
        return None
    h = urlsplit(n).hostname
    return "https://" + h + ("" if p == "443" else f":{int(p)}")


def local_up(url: str = LOCAL, timeout: float = 1.5) -> bool:
    """Aurora on this computer answers (its /health, no login needed)."""
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=timeout) as r:
            return r.status == 200
    except OSError:
        return False


def saved(state: Path | None = None) -> str | None:
    try:
        return normalize(json.loads((state or store.STATE).joinpath(FILE).read_text(encoding="utf-8")).get("address"))
    except (OSError, ValueError, AttributeError):
        return None


def save(address: str, state: Path | None = None) -> None:
    d = store.private_dir(state or store.STATE)
    tmp = d / (FILE + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"address": address}, f)
    tmp.replace(d / FILE)


def choose(setup: bool = False, up=local_up, state: Path | None = None) -> tuple[str | None, str]:
    """(the address, why): «local», «saved», or (None, «ask») when the form must ask; setup: the form always."""
    if setup:
        return None, "ask"
    if up(LOCAL):
        return LOCAL, "local"
    s = saved(state)
    return (s, "saved") if s else (None, "ask")

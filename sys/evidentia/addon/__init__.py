# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Evidentia's side inside Aurora, an add-on (aurora/sys_addons.py loads it only when installed): the routes that carry
the Evidentia page's requests to its own service (api_evidentia), the leads' worker run in each user's tick
(evd_worker) and the dedicated chat (evd_chat). Nothing of the archive is kept on Aurora's side: no vault, no memory,
no lessons — its agent runs with Evidentia's tools only, on the local model."""
from __future__ import annotations


def routers() -> list:
    from . import api_evidentia
    return [api_evidentia.router]


def ticks() -> list:
    from . import evd_worker
    return [evd_worker.tick]


STATUS = "/var/lib/evidentia-api/backup.json"     # written by evd_backup (root): numbers only, never a file's name
SOCK = "/var/lib/evidentia-api/evidentia.sock"


def health(cfg) -> list:
    """Aurora's 🩺 lines for Evidentia, as for her own backup (owner, 27 Nov: «c'è una routine automatica e verifica
    integrazione backup etc per evidentia come avviene anche per aurora?»): the service reachable, the last backup
    recent and good (older than 30 h, failed, or never: a warning, which Aurora's notifications carry)."""
    import json
    import os
    import time
    it = os.environ.get("AURORA_LANG", "it").startswith("it")
    out = []
    import socket                                   # C752: a socket file left by a dead service is not «up»: connect
    up = False
    try:
        with socket.socket(socket.AF_UNIX) as c:
            c.settimeout(2)
            c.connect(SOCK)
            up = True
    except OSError:
        pass
    out.append(("evidentia", "ok" if up else "warn",
                ("servizio attivo" if it else "service up") if up else ("il servizio non risponde" if it else "the service is down")))
    try:
        b = json.loads(open(STATUS, encoding="utf-8").read())
    except (OSError, ValueError):
        b = None
    if b is None:
        out.append(("backup evidentia", "warn", "nessun backup di Evidentia ancora" if it else "no Evidentia backup yet"))
    elif not b.get("ok"):
        out.append(("backup evidentia", "warn", (f"ultimo tentativo fallito: {b.get('error')}" if it else f"the last attempt failed: {b.get('error')}")))
    else:
        age = (time.time() - float(b.get("at") or 0)) / 3600
        gb = (b.get("bytes") or 0) / 1e9
        if age > 30:
            out.append(("backup evidentia", "warn", f"nessun backup riuscito da {age:.0f} ore" if it else f"no backup succeeded for {age:.0f} hours"))
        else:
            out.append(("backup evidentia", "ok", f"ultimo {age:.0f} h fa: {b.get('files')} file, {gb:.1f} GB" if it
                        else f"the last {age:.0f} h ago: {b.get('files')} files, {gb:.1f} GB"))
    return out

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora reachable from away (net_cloudflare, roadmap 56): «Salva» in the cloudflare plugin's card, or the plugin
switched on, sets everything up and starts aurora-tunnel; switched off, the tunnel stops. The outcome is a
notification (tunnel.done / tunnel.failed) and the card's state (cloudflare_status)."""
from __future__ import annotations

import threading

from fastapi import APIRouter

from .core import log, note

router = APIRouter()
_busy = threading.Lock()


def _fresh():
    """The .env as saved a moment ago: the process keeps the configuration it started with (machine settings)."""
    from aurora import sys_config
    return sys_config._view(sys_config.load())


def _enabled() -> bool:
    from .core import plugin_host
    return any(p.name == "cloudflare" and p.enabled for p in plugin_host().plugins(with_tools=False))


def start_tunnel() -> bool:
    """In the background: the steps on the Cloudflare account, the token kept, aurora-tunnel started. False when the
    plugin is off (nothing to do) or a setup is already running."""
    if not _enabled() or _busy.locked():
        return False
    from aurora import sys_context
    from .core import _admin

    def work():
        from aurora import net_cloudflare
        with _busy, sys_context.acting_as(_admin()):
            try:
                r = net_cloudflare.apply(_fresh())
            except Exception as e:  # noqa: BLE001 — told, never a crash
                r = {"ok": False, "text": f"errore: {type(e).__name__}: {e}"}
            log.info("audit: cloudflare tunnel set up: %s", "ok" if r["ok"] else r["text"].replace("\n", " | ")[:300])
            note("cloudflare", "tunnel.done" if r["ok"] else "tunnel.failed", {"text": r["text"]})
    threading.Thread(target=work, name="tunnel", daemon=True).start()
    return True


def stop_tunnel() -> bool:
    from aurora import net_cloudflare
    ok = net_cloudflare.stop()
    log.info("audit: cloudflare plugin off: aurora-tunnel %s", "stopped" if ok else "not running")
    return ok


def at_start() -> None:
    """After a restart or a reboot: the plugin on and configured but the tunnel down — set up once again."""
    from aurora import net_cloudflare
    try:
        c = net_cloudflare.conf(_fresh())
        if not net_cloudflare.missing(c) and net_cloudflare.service_state() not in ("active", "missing"):
            start_tunnel()
    except Exception as e:  # noqa: BLE001 — a start never fails for this
        log.warning("cloudflare at start: %s", type(e).__name__)

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "cloudflare": Aurora reachable everywhere through Cloudflare One (WARP private network, roadmap 56).

The work is in aurora.net_cloudflare (also what «Salva» in this plugin's card does, through the API). The state and
the check were written by Aurora herself through the forge (request 328397d269, 7 October 2026).

  cloudflare_status    read: the API token, the tunnel and its connections, a hostname published on the Internet,
                       the private routes, WARP's split tunnel, the internal domain's fallback, aurora-tunnel here
  cloudflare_check     read: what is still missing, step by step
  cloudflare_activate  changes the Cloudflare account (an approval each time, from the chat): the same as «Salva»
  cloudflare_culprits  read: who is behind Cloudflare's addresses the firewall refused (ROADMAP 103 step 2)
  cloudflare_blocks    read: Aurora's blocks at Cloudflare
  cloudflare_block     an IP Access Rule on the account, for some hours (an approval each time); _unblock lifts it
"""
from __future__ import annotations

from aurora import net_cfwaf, net_cloudflare, sys_config
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

server = MCPServer("cloudflare", version="1.0")


def _guard(fn):
    try:
        return fn(sys_config.get())                    # read when used: importable without a .env
    except Exception as e:  # noqa: BLE001 — the agent must see why
        import traceback
        return "ERRORE: " + "".join(traceback.format_exception(e))[-1500:]


@server.tool()
def cloudflare_status() -> str:
    """Stato di Cloudflare Zero Trust per Aurora: token, tunnel e connessioni, rotte private /32, split tunnel WARP,
    dominio interno, servizio aurora-tunnel su questo computer (sola lettura)."""
    return _guard(net_cloudflare.status)


@server.tool()
def cloudflare_check() -> str:
    """What is missing to reach Aurora through WARP, step by step (read only: creates or changes nothing)."""
    return _guard(net_cloudflare.check)


@server.tool()
def cloudflare_activate() -> str:
    """Attiva l'accesso via WARP (serve l'approvazione): crea il tunnel se manca, aggiunge le rotte private di questo
    computer e del DNS di casa, li fa passare in WARP, risolve il dominio interno anche fuori casa, avvia il tunnel.
    The same as «Salva» on the plugin's card. What is already there stays as it is."""
    return _guard(lambda cfg: net_cloudflare.apply(cfg)["text"])


@server.tool()
def cloudflare_culprits(hours: float = 24) -> str:
    """Who is behind Cloudflare's addresses in the firewall's log (read only): the clients whose requests your origin
    did not answer (refused or dropped: 520–526) in the last hours (≤ 24), with requests, hosts, paths. Judge which
    are scanners (paths like /wp-login.php, /.env); cloudflare_block blocks one at Cloudflare."""
    def run(cfg):
        rows = net_cfwaf.culprits(cfg, hours)
        if not rows:
            return f"Nessuna richiesta senza risposta dall'origine nelle ultime {hours:g} ore."
        return "\n".join(f"{r['ip']}: {r['requests']} richieste, {', '.join(r['hosts'])} — {', '.join(r['paths'])} "
                         f"(HTTP {', '.join(map(str, r['statuses']))}) → {r['looks']}" for r in rows)
    return _cf(run)


@server.tool()
def cloudflare_blocks() -> str:
    """The addresses Aurora blocked at Cloudflare and until when (read only)."""
    import time
    rows = _guard(net_cfwaf.active)
    if isinstance(rows, str):
        return rows
    return "\n".join(f"{b['ip']} fino al {time.strftime('%Y-%m-%d %H:%M', time.localtime(b['until']))}: {b['reason']}"
                     for b in rows) or "Nessun blocco di Aurora su Cloudflare."


@server.tool()
def cloudflare_block(ip: str, reason: str, hours: float = 24) -> str:
    """Block a client address at Cloudflare, on every zone of the account (an IP Access Rule; asks the owner's
    approval), lifted by itself after `hours` (1 h – 30 days). Never a Cloudflare node or a protected address."""
    return _cf(lambda cfg: "Bloccato su Cloudflare: {ip} fino al {u}".format(
        u=__import__("time").strftime("%Y-%m-%d %H:%M", __import__("time").localtime(
            net_cfwaf.block(cfg, ip, reason, hours)["until"])), ip=ip))


@server.tool()
def cloudflare_unblock(ip: str) -> str:
    """Lift a block Aurora put at Cloudflare (asks the owner's approval)."""
    return _cf(lambda cfg: f"Sbloccato su Cloudflare: {net_cfwaf.unblock(cfg, ip)['ip']}")


def _cf(fn):
    """The Cloudflare errors said plainly (a missing permission is the owner's to add), anything else as _guard."""
    try:
        return fn(sys_config.get())
    except net_cfwaf.CloudflareError as e:
        raise ToolError(str(e)) from None


if __name__ == "__main__":
    server.run("stdio")

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "cloudflare": Aurora reachable everywhere through Cloudflare One (WARP private network, roadmap 56).

The work is in aurora.net_cloudflare (also what «Salva» in this plugin's card does, through the API). The state and
the check were written by Aurora herself through the forge (request 328397d269, 7 October 2026).

  cloudflare_status    read: the API token, the tunnel and its connections, a hostname published on the Internet,
                       the private routes, WARP's split tunnel, the internal domain's fallback, aurora-tunnel here
  cloudflare_check     read: what is still missing, step by step
  cloudflare_activate  changes the Cloudflare account (an approval each time, from the chat): the same as «Salva»
"""
from __future__ import annotations

from aurora import net_cloudflare, sys_config
from mcp.server.mcpserver import MCPServer

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
    """Cosa manca per raggiungere Aurora via WARP, passo per passo (sola lettura: non crea né modifica nulla)."""
    return _guard(net_cloudflare.check)


@server.tool()
def cloudflare_activate() -> str:
    """Attiva l'accesso via WARP (serve l'approvazione): crea il tunnel se manca, aggiunge le rotte private di questo
    computer e del DNS di casa, li fa passare in WARP, risolve il dominio interno anche fuori casa, avvia il tunnel.
    Lo stesso che «Salva» nella scheda del plugin. Ciò che c'è già resta com'è."""
    return _guard(lambda cfg: net_cloudflare.apply(cfg)["text"])


if __name__ == "__main__":
    server.run("stdio")

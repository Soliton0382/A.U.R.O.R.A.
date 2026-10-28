# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🟢 Spotify in the DJ page (owner, 28 Oct: «lasciamolo come plugin interno alla pagina che uso se lo attiva se ha
premium… con la guida che spiega come fare»). The player and the sign-in live in the browser (dj_spotify.js: PKCE,
the Web Playback SDK); this program only says whether it is set up, for «Prova» and the agent."""
from __future__ import annotations

import os

from mcp.server.mcpserver import MCPServer

server = MCPServer("spotify", version="1.0")


@server.tool()
def spotify_status() -> str:
    """Whether Spotify's player is set up here (a Client ID), and what is needed when it is not."""
    cid = os.environ.get("AURORA_SPOTIFY_CLIENT_ID", "").strip()
    if not cid:
        return ("Spotify non è configurato: serve un account Premium e il Client ID di un'app su developer.spotify.com "
                "(la guida è nella scheda del plugin, pagina DJ).")
    return (f"Spotify configurato (Client ID …{cid[-4:]}). Il lettore è nel browser, pagina DJ → 🟢 Spotify: ognuno "
            "collega il proprio account Premium.")


if __name__ == "__main__":
    server.run()

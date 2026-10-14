# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""QR codes (ROADMAP 101's first plugin that brings its own library: segno, in <plugin>/.deps via plg_run.py)."""
from __future__ import annotations

import io

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

server = MCPServer("qr", version="1.0")


def _segno():
    try:
        import segno
    except ImportError:
        raise ToolError("the QR library is not installed: Plugins → QR → 📦 Install") from None
    return segno


def _out(qr) -> str:
    svg = io.BytesIO()
    qr.save(svg, kind="svg", scale=6, border=2)
    text = io.StringIO()
    qr.terminal(out=text, compact=True)
    return (f"QR {qr.designator}, {qr.symbol_size(border=2)[0]} moduli.\n\nA CARATTERI:\n```\n{text.getvalue()}```\n\n"
            f"SVG (per una pagina o un file):\n{svg.getvalue().decode()}")


@server.tool()
def qr_text(text: str) -> str:
    """A text or a link as a QR code."""
    if not text.strip() or len(text) > 2000:
        raise ToolError("a text of 1 to 2000 characters")
    return _out(_segno().make(text.strip(), micro=False))


@server.tool()
def qr_wifi(ssid: str, password: str = "", security: str = "WPA") -> str:
    """The Wi-Fi as a QR code: a phone that frames it joins the network. security: WPA, WEP or nopass."""
    if not ssid.strip():
        raise ToolError("the network's name (SSID)")
    _segno()                                          # the library checked first: a clear message if missing
    from segno import helpers as h
    qr = h.make_wifi(ssid=ssid.strip(), password=password or None, security=None if security == "nopass" else security)
    return _out(qr)


if __name__ == "__main__":
    server.run()

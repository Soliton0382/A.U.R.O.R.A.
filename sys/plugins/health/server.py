# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "health": the user's diet, training and medical exams, sealed (aurora.hlt_store), for the local model only.

The documents are uploaded in the Health page (the API seals them and makes the user's key); here Aurora reads an
area's texts to answer, and records a note (a workout, a weight, a value). No network; private (agt_loop refuses it
to a cloud model).
"""
from __future__ import annotations

from aurora import hlt_store, sys_config
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

cfg = sys_config.get()
server = MCPServer("health", version="1.0")
NAMES = {"diet": "dieta", "training": "allenamento", "exams": "esami"}


def _area(area: str) -> str:
    area = {v: k for k, v in NAMES.items()}.get(area, area)
    if area not in hlt_store.AREAS:
        raise ToolError("area: diet (dieta), training (allenamento) or exams (esami)")
    return area


@server.tool()
def health_list(area: str) -> str:
    """What is in an area: diet, training or exams (documents and notes, newest first)."""
    a = _area(area)
    its = hlt_store.items(cfg, a)
    return "\n".join(f"- {i['title']} ({i['kind']})" for i in its) or f"Nessun documento in {NAMES[a]}: caricali nella pagina ❤️ Salute."


@server.tool()
def health_read(area: str) -> str:
    """The texts of an area (diet, training, exams), newest first: to answer about the plan, the programme, the values.
    Not medical advice: for any doubt the reference is the user's doctor."""
    a = _area(area)
    return hlt_store.everything(cfg, a) or f"Nessun documento in {NAMES[a]}."


@server.tool()
def health_note(area: str, text: str, title: str = "") -> str:
    """Record a note in an area: a workout done, a weight, a meal, a value of an exam (with its day)."""
    try:
        it = hlt_store.add_note(cfg, _area(area), title, text)
    except (ValueError, OSError) as e:
        raise ToolError(f"not recorded: {e} (open the ❤️ Health page once: it makes the user's key)") from None
    return f"Annotato in {NAMES[_area(area)]}: {it['title']}."


if __name__ == "__main__":
    server.run("stdio")

#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The agents' cards: the active ones, the proposals a client made, and the owner's decision on each proposal
(owner, 10 Nov: Aurora may propose a new agent; it becomes active only with his yes).

    .venv/bin/python sys/evidentia/script/evd_agents.py list
    .venv/bin/python sys/evidentia/script/evd_agents.py show <name>        # a proposal's whole card, to read before deciding
    .venv/bin/python sys/evidentia/script/evd_agents.py approve <name>     # moved into sys/evidentia/agents: served from the next start
    .venv/bin/python sys/evidentia/script/evd_agents.py reject <name>
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evidentia import agents, config  # noqa: E402

ACTIVE = config.ROOT / "sys" / "evidentia" / "agents"
PROPOSED = config.load().path("EVD_DATA_DIR") / "agents" / "proposed"


def main(argv: list[str]) -> int:
    cmd, name = (argv + ["", ""])[:2]
    if cmd == "list":
        for label, folder in (("active", ACTIVE), ("proposed", PROPOSED)):
            for c in agents.load(folder):
                print(f"{label:9} {c['profile']:13} {c['name']:24} {c['description']}")
        return 0
    f = PROPOSED / f"{name}.md"
    if cmd not in ("show", "approve", "reject") or not agents.NAME.match(name) or not f.is_file():
        print(__doc__)
        return 2
    card = agents.parse(f.read_text(encoding="utf-8"), f.name)       # checked again: the file may have been changed
    if cmd == "show":
        print(agents.card_text(card))
    elif cmd == "approve":
        if (ACTIVE / f.name).exists():
            print(f"an active agent is already named {name}")
            return 1
        (ACTIVE / f.name).write_text(agents.card_text(card), encoding="utf-8")
        f.unlink()
        print(f"{name}: active (the MCP server serves it from its next start)")
    else:
        f.unlink()
        print(f"{name}: rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

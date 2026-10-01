# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Write docs/PLUGINS.md from the plugin manifests (the WebUI shows the same guides).

    python sys/core/script/doc_plugins.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    out = ["# Plugins", "", "Generated from `sys/plugins/*/plugin.json` by `sys/core/script/doc_plugins.py`: the WebUI "
           "(Plugins page) shows the same guides. Effects: **read** automatic, **write_local** automatic and logged, "
           "**external** waits for the owner (Repairs page).", ""]
    rows = ["| plugin | kind | tools (effect) | needs |", "|---|---|---|---|"]
    manifests = [json.loads(p.read_text()) for p in sorted((ROOT / "sys/plugins").glob("*/plugin.json"))]
    for m in manifests:
        eff = m.get("effects", {})
        tools = ", ".join([f"{k} ({v})" for k, v in eff.items() if k != "*"]
                          + [f"{k}* ({v})" for k, v in m.get("effect_prefixes", {}).items()]
                          + ([f"everything else ({eff['*']})"] if m.get("effect_prefixes") else [])) or "—"
        rows.append(f"| `{m['name']}` | {m.get('kind', '')} | {tools} | {', '.join(m.get('requires', [])) or '—'} |")
    out += rows + [""]
    for m in manifests:
        s = m.get("setup", {})
        out += [f"## {m['name']}", "", m.get("description", {}).get("en", ""), ""]
        if s.get("en"):
            out += ["### Setup (EN)", "", s["en"], ""]
        if s.get("it"):
            out += ["### Configurazione (IT)", "", s["it"], ""]
        if s.get("links"):
            out += ["### Official guides", ""] + [f"- [{l['label']}]({l['url']})" for l in s["links"]] + [""]
    (ROOT / "docs/PLUGINS.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"docs/PLUGINS.md: {len(manifests)} plugins")
    return 0


if __name__ == "__main__":
    sys.exit(main())

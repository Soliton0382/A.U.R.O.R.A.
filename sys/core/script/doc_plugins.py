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
sys.path.insert(0, str(ROOT / "sys" / "core"))


def main() -> int:
    out = ["# Plugins", "", "Generated from `sys/plugins/*/plugin.json` by `sys/core/script/doc_plugins.py`: the WebUI "
           "(Plugins page) shows the same guides. Effects: **read** automatic, **write_local** automatic and logged, "
           "**external** waits for the owner (Repairs page).", "",
           "A plugin may bring its own program (`\"install\"`: Python libraries pinned with `--hash=sha256:`, programs with "
           "their `sha256`): installed into the plugin's own folder when it is switched on or with 📦 on its card, never into "
           "Aurora's environment, removed whole with 🧹; its command is "
           "`[\"{python}\", \"{root}/sys/core/script/plg_run.py\", \"server.py\"]` (aurora/plg_deps.py; the `qr` plugin).", ""]
    from aurora.plg_contract import FIELDS
    out += ["## The contract", "", "Every plugin.json follows it (aurora/plg_contract.py: the tests check every plugin, the "
            "forge every plugin it builds; a field not listed here is refused).", "", "| field | required | what it is |",
            "|---|---|---|"]
    out += [f"| `{k}` | {'yes' if req else '—'} | {what} |" for k, (_, req, what) in FIELDS.items()] + [""]
    rows = ["| plugin | kind | tools (effect) | needs |", "|---|---|---|---|"]
    # the owner's private plugins (local_*, never published: .gitignore) are never in a public page (C308)
    manifests = [json.loads(p.read_text()) for p in sorted((ROOT / "sys/plugins").glob("*/plugin.json"))
                 if not p.parent.name.startswith("local_")]
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

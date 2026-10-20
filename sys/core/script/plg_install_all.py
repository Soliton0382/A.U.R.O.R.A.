# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The libraries and programs of every plugin that declares them (plg_deps), each into its own folder — what the
installer runs (owner, 2026-10-21: «aggiorniamo anche l'installer così chi installa installa tutti i pacchetti
necessari… senza sporcare il sistema operativo»). One that fails is said and the others go on; already installed: left.

    python sys/core/script/plg_install_all.py [--again]     # --again: installed ones fetched again
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aurora import plg_deps  # noqa: E402

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"


def main(again: bool = False) -> int:
    failed = 0
    for manifest in sorted(PLUGINS.glob("*/plugin.json")):
        folder = manifest.parent
        m = json.loads(manifest.read_text(encoding="utf-8"))
        st = plg_deps.state(folder, m)
        if not st["wanted"]:
            continue
        if st["installed"] and not again:
            print(f"  ✓ {folder.name}: already installed ({st['bytes'] // 2**20} MB)")
            continue
        try:
            st = plg_deps.install(folder, m, log=lambda msg, n=folder.name: print(f"    {n}: {msg}"))
            print(f"  ✓ {folder.name}: {st['bytes'] // 2**20} MB in its own folder")
        except Exception as e:                           # noqa: BLE001 — one plugin's failure is not the others'
            failed += 1
            print(f"  ⚠ {folder.name}: not installed — {str(e)[:300]}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main("--again" in sys.argv[1:]))

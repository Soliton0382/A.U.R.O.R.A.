# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora as just installed (owner, 2026-10-06): her memory and state moved aside, the settings to the factory's.

    python sys/core/script/sys_factory_reset.py                    # the plan (changes nothing)
    python sys/core/script/sys_factory_reset.py --apply            # asks to type AZZERA
    python sys/core/script/sys_factory_reset.py --apply --with-knowledge   # the knowledge vault too
    python sys/core/script/sys_factory_reset.py --apply --reset-keys       # keys and tokens to empty too

Never touched: usr/ (documents, papers, projects, health), the users and their keys. Nothing is deleted: what is
moved goes into <root>-before-reset-<time>; to go back, stop Aurora and move it back. See aurora/sys_reset.py.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aurora import sys_config, sys_reset  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--with-knowledge", action="store_true")
    ap.add_argument("--reset-keys", action="store_true")
    a = ap.parse_args()
    cfg = sys_config.get()
    plan = sys_reset.mind_plan(cfg, a.with_knowledge)
    print("Messi da parte (non cancellati):\n  " + "\n  ".join(plan["places"]) + f"\n→ {plan['aside']}")
    print("Impostazioni: ai valori consigliati" + (", chiavi e token compresi" if a.reset_keys else " (chiavi e token restano)"))
    print("Non toccati: usr/ (documenti, papers, progetti, salute), utenti e chiavi" + ("" if a.with_knowledge else ", il vault della conoscenza"))
    if not a.apply:
        return 0
    if input("Riportare Aurora come appena installata? Scrivi AZZERA: ").strip() != "AZZERA":
        print("annullato")
        return 1
    subprocess.run(["systemctl", "stop", "aurora.target"], check=False, timeout=300)
    sys_reset.mind(cfg, plan)
    out = sys_reset.settings(cfg, keep_keys=not a.reset_keys)
    print(f"impostazioni cambiate: {len(out['changed'])} (la .env di prima: {out['backup']})")
    subprocess.run(["systemctl", "start", "aurora.target"], check=False, timeout=300)
    print(f"✅ fatto. Quello che c'era è in {plan['aside']}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

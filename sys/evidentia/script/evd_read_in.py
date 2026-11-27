# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A folder read in from the WebUI (evidentia/sources): the inventory, then 💰 follow the money again over the whole
archive (owner, 27 Nov: «una cosa automatica che caccia, trova e correla»). The same arguments as evd_inventory.py."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    rc = subprocess.run([sys.executable, "-I", "-B", str(HERE / "evd_inventory.py"), *sys.argv[1:]]).returncode
    print("💰 following the money again…", flush=True)
    rc2 = subprocess.run([sys.executable, "-I", "-B", str(HERE / "evd_money.py")]).returncode
    return rc or rc2


if __name__ == "__main__":
    sys.exit(main())

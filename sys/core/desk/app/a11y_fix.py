# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora Desktop: put the accessibility switch back after an interrupted demonstration (bozza 8 §2). Run by the
app's transient unit (ExecStopPost, also after a kill), by the user service at login, and by `aurora-root uninstall
desk` as the owner. Does nothing when no demonstration left a record; never touches a value changed meanwhile."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from desk.app import store  # noqa: E402


def main() -> int:
    try:
        print(store.a11y_restore())
    except Exception as e:                              # noqa: BLE001 — no session bus (logout): the login unit retries
        print(f"not put back now: {e}")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

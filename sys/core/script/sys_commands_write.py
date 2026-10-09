# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A port's installer gives Aurora its own commands for the command cards (sys_commands, roadmap 74) and the clone it
built Aurora from (where updates are checked):

    python sys/core/script/sys_commands_write.py --from Aurora_windows/commands.json --source C:/path/to/clone

Writes <STATUS>/commands.json ({"source", "by_hand": true, "update", "sign", "restart"}); nothing else.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aurora import sys_config  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from", dest="src", type=Path, required=True)
    ap.add_argument("--source", default="")
    a = ap.parse_args()
    data = {k: v for k, v in json.loads(a.src.read_text(encoding="utf-8")).items() if k != "about"}
    data["by_hand"] = True
    if a.source:
        data["source"] = str(Path(a.source).resolve())
    out = sys_config.get().path("AURORA_STATUS_DIR") / "commands.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"commands for this system: {', '.join(k for k in data if k not in ('source', 'by_hand'))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

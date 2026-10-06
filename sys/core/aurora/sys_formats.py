# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The versions of Aurora's data formats, so that a backup made by one version can be restored by another (owner,
2026-10-06: "if updates change things, a restore must stay compatible, or it ruins the installation").

Each format has a number; a backup snapshot records them (sys_backup); a restore compares (compare): the same numbers
restore as they are; older ones are brought up by the migrations listed here, one step at a time; a newer one is
refused — Aurora must be updated first. A change of a format = its number + 1 AND a migration from the number before
(tests/test_formats.py checks that no step is missing).
"""
from __future__ import annotations

import json
from pathlib import Path

from . import sys_config

FORMATS = {
    "settings": 1,     # config/settings_schema.json ("version"); new keys come by themselves (sys_env_sync)
    "layout": 1,       # <STATUS>/users_layout.json: the per-user folders (U3)
    "soliton": 1,      # the vault's rows (sol_schema.schema_version)
    "backup": 1,       # the snapshot itself (sys_backup)
}
# (format, from version) -> what the migration does; the function is in MIGRATE, the text is said in the plan
MIGRATIONS: dict[tuple[str, int], str] = {}
MIGRATE: dict[tuple[str, int], object] = {}


def current(cfg: sys_config.Config) -> dict:
    """The formats of this installation as its files say (a missing file: the code's number)."""
    out = dict(FORMATS)
    try:
        out["settings"] = int(json.loads((Path(__file__).resolve().parents[1] / "config" / "settings_schema.json")
                                         .read_text(encoding="utf-8")).get("version", FORMATS["settings"]))
    except (OSError, ValueError):
        pass
    try:
        out["layout"] = int(json.loads((cfg.path("AURORA_STATUS_DIR") / "users_layout.json").read_text()).get("layout", 1))
    except (OSError, ValueError):
        pass
    return out


def compare(theirs: dict | None, ours: dict | None = None) -> dict:
    """{"verdict": "same"|"migrate"|"newer"|"unknown", "steps": [texts], "why": str} for restoring `theirs` here."""
    ours = ours or FORMATS
    if not theirs:
        return {"verdict": "unknown", "steps": [], "why": "the backup was made before the formats were recorded "
                "(6 October 2026): it is restored as it is, every format was 1 then"}
    newer = [k for k, v in theirs.items() if k in ours and int(v) > int(ours[k])]
    if newer:
        return {"verdict": "newer", "steps": [], "why": f"made by a newer Aurora ({', '.join(newer)}): update Aurora first"}
    missing = [f"{k} {n}→{n + 1}" for k, v in theirs.items() if k in ours for n in range(int(v), int(ours[k]))
               if (k, n) not in MIGRATIONS]
    if missing:
        return {"verdict": "newer", "steps": [], "why": f"no migration for {', '.join(missing)}: not restorable here"}
    steps = [MIGRATIONS[(k, n)] for k, v in theirs.items() if k in ours for n in range(int(v), int(ours[k]))]
    return {"verdict": "migrate" if steps else "same", "steps": steps, "why": ""}

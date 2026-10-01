# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Compare .env with the settings schema and write an updated copy.

Keeps every value already in .env, adds the missing keys with their
recommended value, lists the keys that the schema no longer declares, and
writes the result next to .env as .env.proposed (never over .env itself).
It also writes .env.example with the recommended values.

    python sys/core/script/sys_env_sync.py            # report + write the two files
    python sys/core/script/sys_env_sync.py --check    # report only, exit 1 if not in sync
"""
from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aurora import sys_config as C  # noqa: E402


def render(schema: dict, values: dict[str, str], lang: str = "en") -> str:
    """One commented block per category, in schema order."""
    lines = ["# Aurora environment. Generated from sys/core/config/settings_schema.json;",
             "# edit the values here or from the WebUI Settings page.", ""]
    current = None
    for spec in schema["settings"]:
        if spec["category"] != current:
            current = spec["category"]
            title = schema["categories"][current][lang]
            lines += ["", f"# ---- {title} " + "-" * max(4, 72 - len(title)), ""]
        lines.append(f"# {spec[lang]}")
        lines.append(f"# [{spec['type']}{', ' + '/'.join(spec['choices']) if 'choices' in spec else ''}]"
                     f"  recommended: {spec['recommended']}  evidence: {spec['evidence']}")
        lines.append(f"{spec['key']}={values[spec['key']]}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="report only; exit 1 if .env is not in sync")
    ap.add_argument("--adopt", default="", help="comma-separated keys to set to their recommended value")
    args = ap.parse_args()
    schema = C.load_schema()
    env_file = C.env_file_path()
    current = C.parse_env(env_file.read_text(encoding="utf-8"), str(env_file)) if env_file.is_file() else {}
    declared = [s["key"] for s in schema["settings"]]
    missing = [k for k in declared if k not in current]
    obsolete = sorted(set(current) - set(declared))
    kept = {k: current[k] for k in declared if k in current}
    recommended = {s["key"]: s["recommended"] for s in schema["settings"]}
    print(f"{env_file}: {len(kept)} kept, {len(missing)} missing, {len(obsolete)} not in the schema")
    for k in missing:
        print(f"  + {k}={recommended[k]}")
    for k in obsolete:
        print(f"  - {k}  (not declared in the schema, dropped from the proposal)")
    secret = {s["key"] for s in schema["settings"] if s.get("secret")}
    for k in declared:
        if k in kept and kept[k] != recommended[k]:
            shown = "(secret, set)" if k in secret else kept[k]
            print(f"  ~ {k}={shown}  (kept; recommended {recommended[k]})")
    if args.check:
        return 1 if (missing or obsolete) else 0
    adopt = [k.strip() for k in args.adopt.split(",") if k.strip()]
    unknown = [k for k in adopt if k not in recommended]
    if unknown:
        print(f"--adopt: keys not in the schema: {unknown}")
        return 2
    proposed = {**recommended, **kept, **{k: recommended[k] for k in adopt}}
    for spec in schema["settings"]:                  # secrets are generated, never recommended
        if spec.get("generate") == "token" and not proposed[spec["key"]]:
            proposed[spec["key"]] = secrets.token_urlsafe(32)
            print(f"  * {spec['key']} generated (secret)")
    for k in adopt:
        print(f"  = {k}={recommended[k]}  (adopted the recommended value)")
    proposed_file = env_file.parent / ".env.proposed"
    proposed_file.write_text(render(schema, proposed), encoding="utf-8")
    proposed_file.chmod(0o600)                       # it holds the secrets: owner only
    (env_file.parent / ".env.example").write_text(render(schema, recommended), encoding="utf-8")
    print(f"written {env_file.parent / '.env.proposed'} and {env_file.parent / '.env.example'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

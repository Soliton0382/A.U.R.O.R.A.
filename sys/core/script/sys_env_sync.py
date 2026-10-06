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
import json
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
        if spec["key"] not in values:            # a personal setting on the per-user layout lives in usr/<name>/.env (C165)
            continue
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


def migrated(current: dict[str, str], schema: dict) -> bool:
    """Is this installation on the per-user layout? (status/users_layout.json, written by the migration)"""
    rec = {s["key"]: s["recommended"] for s in schema["settings"]}
    root = Path(current.get("AURORA_ROOT") or C.CODE_ROOT)
    status = root / (current.get("AURORA_STATUS_DIR") or rec["AURORA_STATUS_DIR"])
    try:
        return json.loads((status / "users_layout.json").read_text(encoding="utf-8")).get("layout") == 1
    except (OSError, ValueError):
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="report only; exit 1 if .env is not in sync")
    ap.add_argument("--adopt", default="", help="comma-separated keys to set to their recommended value")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="a value for the proposal (installer: the owner's answers, the hardware profile); checked by the schema")
    ap.add_argument("--example", action="store_true",
                    help="write only .env.example from the schema (for publishing; an installation never rewrites it)")
    args = ap.parse_args()
    schema = C.load_schema()
    if args.example:
        recommended = {s["key"]: s["recommended"] for s in schema["settings"]}
        (C.CODE_ROOT / ".env.example").write_text(render(schema, recommended), encoding="utf-8")
        print(f"written {C.CODE_ROOT / '.env.example'}")
        return 0
    env_file = C.env_file_path()
    current = C.parse_env(env_file.read_text(encoding="utf-8"), str(env_file)) if env_file.is_file() else {}
    declared = [s["key"] for s in schema["settings"]]
    if migrated(current, schema):          # per-user layout: the personal settings live in usr/<name>/.env (C116)
        declared = [s["key"] for s in schema["settings"] if s.get("scope") != "user"]
        print("per-user layout: the personal settings are in each user's usr/<name>/.env, not here")
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
    proposed = {**{k: recommended[k] for k in declared}, **kept, **{k: recommended[k] for k in adopt}}
    if "AURORA_ROOT" not in kept:                 # a new installation lives where its code is
        proposed["AURORA_ROOT"] = str(C.CODE_ROOT)
        print(f"  * AURORA_ROOT={C.CODE_ROOT} (this folder)")
    specs = {sp["key"]: sp for sp in schema["settings"]}
    for item in args.set:
        key, _, value = item.partition("=")
        if key not in specs:
            print(f"--set: {key} is not in the schema")
            return 2
        try:
            C.convert(specs[key], value)
        except ValueError as e:
            print(f"--set: {key}: {e}")
            return 2
        proposed[key] = value
        print(f"  = {key}={'(secret)' if specs[key].get('secret') else value}")
    for spec in schema["settings"]:                  # secrets are generated, never recommended
        if spec.get("generate") == "token" and not proposed[spec["key"]]:
            proposed[spec["key"]] = secrets.token_urlsafe(32)
            print(f"  * {spec['key']} generated (secret)")
    for k in adopt:
        print(f"  = {k}={recommended[k]}  (adopted the recommended value)")
    proposed_file = env_file.parent / ".env.proposed"
    proposed_file.write_text(render(schema, proposed), encoding="utf-8")
    proposed_file.chmod(0o600)                       # it holds the secrets: owner only
    print(f"written {proposed_file} (review it, then: mv .env.proposed .env)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

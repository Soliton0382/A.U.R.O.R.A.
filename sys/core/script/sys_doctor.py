# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Is this installation whole? Configuration, signatures, models, features, contradicting settings, services.

    python sys/core/script/sys_doctor.py                        # the report; exit 1 when something required is wrong
    python sys/core/script/sys_doctor.py --groups profile.json  # for the installer: the optional model groups,
                                                                #   name|GB|fits|default|why|label_it|label_en|models
Read only: it changes nothing. The installer runs it at the end; the Status page shows the same features.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
ROOT = Path(__file__).resolve().parents[3]
UNITS = ("aurora-api", "aurora-models", "aurora-llm", "aurora-https", "aurora-rem", "aurora-harvester", "aurora-sentinel")


def groups(profile_file: Path) -> int:
    from aurora import sys_features as F
    profile = json.loads(profile_file.read_text(encoding="utf-8"))
    for name, g in F.GROUPS.items():
        ok, why = F.fits(profile, name)
        print("|".join([name, f"{F.group_size_gb(name):.1f}", "1" if ok else "0", "1" if g["default"] else "0", why,
                        g["label"]["it"], g["label"]["en"], ",".join(g["models"])]))
    return 0


def report(lang: str) -> int:
    bad = 0

    def line(mark: str, text: str, hint: str = "") -> None:
        print(f"  {mark} {text}" + (f"\n      → {hint}" if hint else ""))

    print("== configurazione" if lang == "it" else "== configuration")
    from aurora import sys_config
    try:
        cfg = sys_config.get()
        line("✅", ".env")
    except sys_config.ConfigError as e:
        line("⛔", str(e).splitlines()[0], "python sys/core/script/sys_env_sync.py")
        return 1
    sync = subprocess.run([sys.executable, str(ROOT / "sys/core/script/sys_env_sync.py"), "--check"], capture_output=True, text=True)
    summary = next((s for s in sync.stdout.splitlines() if "not in the schema" in s), "")
    stale = [s.split()[1] for s in sync.stdout.splitlines() if "dropped from the proposal" in s]
    line("✅" if sync.returncode == 0 else "⚠️", "schema ↔ .env" + ("" if sync.returncode == 0 else ": " + summary.split(": ")[-1]
         + (f" ({', '.join(stale)})" if stale else "")),
         "" if sync.returncode == 0 else ".venv/bin/python sys/core/script/sys_env_sync.py && mv .env.proposed .env && chmod 600 .env")
    from aurora import sys_features as F
    for p in F.config_problems(cfg):
        line("⚠️", p)

    print("== firma del codice" if lang == "it" else "== code signature")
    eth = subprocess.run([sys.executable, str(ROOT / "sys/core/script/sys_ethics_sign.py"), "check"], capture_output=True, text=True)
    out = (eth.stdout + eth.stderr).strip().splitlines()
    drift = any("differ" in o for o in out)           # code tier: a warning until the owner signs again
    line("⛔" if eth.returncode else "⚠️" if drift else "✅", out[-1][:160] if out else "?",
         "sudo .venv/bin/python sys/core/script/sys_ethics_sign.py sign" if drift or eth.returncode else "")
    bad += eth.returncode != 0

    print("== funzioni" if lang == "it" else "== features")
    for name, c in F.report(cfg).items():
        mark = "✅" if c["ok"] else "⛔" if c["required"] else "⚪"
        line(mark, c["label"][lang] + ("" if c["ok"] else f" — {', '.join(c['missing'])}"), " | ".join(c["fix"]))
        bad += c["required"] and not c["ok"]

    print("== servizi" if lang == "it" else "== services")
    for u in UNITS:
        st = subprocess.run(["systemctl", "is-active", u], capture_output=True, text=True).stdout.strip() or "?"
        line("✅" if st == "active" else "⚪" if st in ("inactive", "unknown") else "⛔", f"{u}: {st}")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--groups", type=Path, metavar="PROFILE_JSON")
    ap.add_argument("--lang", default="")
    a = ap.parse_args()
    if a.groups:
        return groups(a.groups)
    lang = a.lang
    if not lang:
        try:
            from aurora import sys_config
            lang = str(sys_config.get()["AURORA_LANG_DEFAULT"])
        except Exception:  # noqa: BLE001
            lang = "en"
    return report("it" if lang.lower().startswith("it") else "en")


if __name__ == "__main__":
    sys.exit(main())

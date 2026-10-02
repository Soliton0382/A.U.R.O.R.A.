# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Is this installation whole? Configuration, signatures, models, features, contradicting settings, services.

    python sys/core/script/sys_doctor.py                        # the report; exit 1 when something required is wrong
    python sys/core/script/sys_doctor.py --groups profile.json  # for the installer: the optional model groups,
                                                                #   name|GB|fits|default|why|label_it|label_en|models|GB to download
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
    from aurora import sys_config
    from aurora import sys_features as F
    profile = json.loads(profile_file.read_text(encoding="utf-8"))
    try:
        cfg = sys_config.get()
    except sys_config.ConfigError:                   # a first install: no .env yet, nothing downloaded
        cfg = None
    man = F.manifest()
    for name, g in F.GROUPS.items():
        ok, why = F.fits(profile, name)
        todo = g["models"] if cfg is None else [m for m in g["models"] if F._model_missing(cfg, m, man[m])]
        print("|".join([name, f"{F.group_size_gb(name):.1f}", "1" if ok else "0", "1" if g["default"] else "0", why,
                        g["label"]["it"], g["label"]["en"], ",".join(g["models"]),
                        f"{sum(man[m]['size_gb'] for m in todo):.1f}"]))
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
    first = any("missing" in o for o in out)        # never signed: setup makes the key (or reuses it) and signs
    line("⛔" if eth.returncode else "⚠️" if drift else "✅", out[-1][:160] if out else "?",
         f"sudo .venv/bin/python sys/core/script/sys_ethics_sign.py {'setup' if first else 'sign'}"
         if drift or eth.returncode else "")
    bad += eth.returncode != 0

    print("== funzioni" if lang == "it" else "== features")
    for name, c in F.report(cfg).items():
        mark = "✅" if c["ok"] else "⛔" if c["required"] else "⚪"
        line(mark, c["label"][lang] + ("" if c["ok"] else f" — {', '.join(c['missing'])}"), " | ".join(c["fix"]))
        bad += c["required"] and not c["ok"]

    print("== backup")
    from aurora import sys_backup
    b = sys_backup.status(cfg)
    last = b.get("last") or {}
    if not b["configured"]:
        line("⚠️", b["problem"], "AURORA_BACKUP_DIR (Impostazioni) + .venv/bin/python sys/core/script/svc_backup.py init")
    else:
        line("✅" if last else "⚠️", f"{b['dest']}: {len(b['snapshots'])} " + ("copie" if lang == "it" else "snapshots")
             + (f", {last.get('files')} file, {last.get('bytes', 0) / 1e9:.1f} GB" if last else ""))

    print("== provider cloud" if lang == "it" else "== cloud providers")
    from aurora import mdl_router
    for name, spec in mdl_router.PROVIDERS.items():
        if not spec.get("key") or not str(cfg.values.get(spec["key"]) or "").strip():
            continue                                    # not configured: nothing to check
        try:
            n = len(mdl_router.list_models(name, cfg))
            line("✅", f"{spec['label']}: " + (f"chiave valida, {n} modelli" if lang == "it" else f"key valid, {n} models"))
        except Exception as e:                          # noqa: BLE001 - a wrong key, a network error: said, not raised
            msg = str(e).split("\n")[0][:120]
            try:                                        # the provider's own words: no credit, wrong key...
                body = e.response.json()
                msg = f"{e.response.status_code}: {body.get('error') or body.get('message') or body}"[:220]
            except Exception:                           # noqa: BLE001 - no response body: the plain error
                pass
            line("⛔", f"{spec['label']}: {msg}", (f"{spec['key']}: controlla la chiave nella scheda del plugin ☁️ cloud"
                                                    if lang == "it" else f"{spec['key']}: check the key in the cloud plugin's card"))

    print("== servizi" if lang == "it" else "== services")
    for u in UNITS:
        st = subprocess.run(["systemctl", "is-active", u], capture_output=True, text=True).stdout.strip() or "?"
        cmd = subprocess.run(["systemctl", "show", "-p", "ExecStart", u], capture_output=True, text=True).stdout
        if st == "active" and str(ROOT) + "/" not in cmd:  # the unit names are the machine's: another folder may own it
            line("⚪", f"{u}: {'di un' + chr(39) + 'altra installazione' if lang == 'it' else 'another installation'}")
            continue
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

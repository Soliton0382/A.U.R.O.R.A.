# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""macOS: Aurora's services as launchd agents of the owner (~/Library/LaunchAgents/com.aurora.<name>.plist, domain
gui/<uid>) — what sys_install_services writes as systemd units on Linux and sys_install_tasks as scheduled tasks on
Windows. Run by install.sh as the owner (no root: launchd starts the owner's own agents).

    .venv/bin/python sys/core/script/sys_install_agents.py [--no-start]

Each agent: started at login (RunAtLoad), started again 5 s after it ends badly (KeepAlive on an unsuccessful exit,
ThrottleInterval), its output in Aurora's log folder. The encoder and the harvest run as background work (C216: the
Mac is the owner's desktop too). The Caddyfile comes from net_https, the one writer, as on Linux.
"""
from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx  # noqa: E402

from aurora import net_https, sys_config, sys_platform  # noqa: E402

LOW = {"aurora-models", "aurora-harvester", "aurora-rem"}


def agents(cfg: sys_config.Config) -> dict[str, list[str]]:
    root = cfg.root
    py = str(sys_platform.current().venv_python(root / cfg["AURORA_VENV_DIR"]))
    script = cfg.path("AURORA_CORE_DIR") / "script"
    out = {f"aurora-{n}": [py, str(script / f"svc_{n}.py")] for n in ("models", "api", "rem", "harvester", "sentinel")}
    out["aurora-https"] = [str(cfg["AURORA_CADDY_BIN"]), "run", "--config", str(net_https.caddyfile(cfg)),
                           "--adapter", "caddyfile"]
    return out


def path_env() -> str:
    """Homebrew's programs first; ffmpeg-full is keg-only (its own bin), the plain ffmpeg has no drawtext (mac.py)."""
    brew = shutil.which("brew")
    prefix = subprocess.run([brew, "--prefix"], capture_output=True, text=True).stdout.strip() if brew else "/opt/homebrew"
    full = subprocess.run([brew, "--prefix", "ffmpeg-full"], capture_output=True, text=True).stdout.strip() if brew else ""
    return ":".join(p for p in (f"{full}/bin" if full else "", f"{prefix}/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin") if p)


def write(cfg: sys_config.Config, unit: str, args: list[str]) -> Path:
    plat = sys_platform.current()
    logs = cfg.path("AURORA_LOG_DIR") / unit.removeprefix("aurora-")
    logs.mkdir(parents=True, exist_ok=True)
    plist = {"Label": plat.label(unit), "ProgramArguments": args, "WorkingDirectory": str(cfg.root),
             "RunAtLoad": True, "KeepAlive": {"SuccessfulExit": False}, "ThrottleInterval": 5,
             "EnvironmentVariables": {"PATH": path_env(), "PYTHONUNBUFFERED": "1"},
             "StandardOutPath": str(logs / "launchd.out.log"), "StandardErrorPath": str(logs / "launchd.err.log")}
    if unit in LOW and str(cfg["AURORA_LLM_BACKEND"]) == "cloud":
        plist.update(ProcessType="Background", Nice=10)
    f = plat.plist(unit)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(plistlib.dumps(plist))
    return f


def wait_for(url: str, seconds: float) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        try:
            if httpx.get(url, timeout=5, verify=False).status_code < 500:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(3)
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-start", action="store_true")
    a = ap.parse_args()
    if os.geteuid() == 0:
        ap.error("run as the owner, not with sudo: launchd agents are the owner's")
    cfg = sys_config.get()
    try:
        print(f"{net_https.write(cfg)}: valid")
    except net_https.HttpsError as e:
        print(f"{net_https.caddyfile(cfg)}: INVALID\n{e}")
        return 1
    if str(cfg["AURORA_LLM_BACKEND"]) != "cloud":
        print("! the local reasoner (llama.cpp on Metal) is not installed on the Mac yet: Aurora reasons in the cloud")
    plat = sys_platform.current()
    units = agents(cfg)
    for unit, args in units.items():
        print(f"  agent {write(cfg, unit, args)}")
    if a.no_start:
        return 0
    for unit in units:                     # loaded again from the new plist: the old code and options leave
        subprocess.run(["launchctl", "bootout", f"gui/{plat.uid}/{plat.label(unit)}"], capture_output=True)
    r = plat.service_action("start", list(units))
    if r.code != 0:
        print(f"start: {(r.out + r.err).strip()[-300:]}")
        return 1
    checks = {"aurora-models": (f"http://{cfg['AURORA_MODELS_HOST']}:{cfg['AURORA_MODELS_PORT']}/health", 300),
              "aurora-api": (f"http://{cfg['AURORA_API_HOST']}:{cfg['AURORA_API_PORT']}/health", 300),
              "aurora-https": (f"https://{cfg['AURORA_DOMAIN']}:{cfg['AURORA_HTTPS_PORT']}/", 120)}
    bad = 0
    for unit, (url, seconds) in checks.items():
        ok = wait_for(url, seconds)
        bad += not ok
        print(f"  {'ok  ' if ok else 'FAIL'}  {unit}  {url}  ({plat.service_state(unit)})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Windows: Aurora's services as scheduled tasks in the folder \\Aurora\\ — what sys_install_services writes as systemd
units on Linux, this system's way. Run by install.ps1 as the administrator, for the user who owns Aurora.

    .venv\\Scripts\\python.exe -X utf8 sys\\core\\script\\sys_install_tasks.py --user <DOMAIN\\name> [--no-start]

Each task: at startup, as that user without a password kept anywhere (S4U: no network share, the internet yes),
started again within a minute when it ends (a minute's trigger: Task Scheduler itself restarts only a start
that failed), never stopped for running long. Python always in UTF-8 (-X utf8: Windows
would read Aurora's texts as cp1252). The encoder and the harvest below normal priority (C216: the CPU is the owner's
desktop too); the API and HTTPS at normal priority. The Caddyfile comes from net_https, the one writer, as on Linux.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx  # noqa: E402

from aurora import net_https, sys_config, sys_platform  # noqa: E402
from aurora.sys_platform.windows import TASKS, _ps_quote  # noqa: E402

# Task Scheduler priorities (0 highest - 10 lowest): 4-6 normal, 7-8 below normal (Microsoft Learn,
# «TaskSettings.Priority property»)
NORMAL, LOW = 5, 7


def tasks(cfg: sys_config.Config) -> dict[str, tuple[str, str, int]]:
    """name -> (program, arguments, priority)."""
    root = cfg.root
    py = sys_platform.current().venv_python(root / cfg["AURORA_VENV_DIR"])
    script = cfg.path("AURORA_CORE_DIR") / "script"
    run = {"models": ("svc_models.py", LOW), "api": ("svc_api.py", NORMAL), "rem": ("svc_rem.py", LOW),
           "harvester": ("svc_harvester.py", LOW), "sentinel": ("svc_sentinel.py", NORMAL)}
    out = {name: (str(py), f'-X utf8 "{script / f}"', prio) for name, (f, prio) in run.items()}
    caddyfile = net_https.caddyfile(cfg)
    out["https"] = (str(cfg["AURORA_CADDY_BIN"]), f'run --config "{caddyfile}" --adapter caddyfile', NORMAL)
    return out


def register(cfg: sys_config.Config, user: str, name: str, program: str, args: str, priority: int) -> None:
    script = (
        f"$a = New-ScheduledTaskAction -Execute {_ps_quote(program)} -Argument {_ps_quote(args)} "
        f"-WorkingDirectory {_ps_quote(str(cfg.root))}; "
        # at startup, and again every minute: Task Scheduler restarts a task only when it fails to START, never when
        # its program ends badly (a real Windows, 9 Oct: the encoder stopped on its first check and stayed down);
        # a running task ignores the minute's start (IgnoreNew), a fallen one is back within 60 s
        "$t = @((New-ScheduledTaskTrigger -AtStartup), "
        "(New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1))); "
        f"$p = New-ScheduledTaskPrincipal -UserId {_ps_quote(user)} -LogonType S4U -RunLevel Limited; "
        "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable "
        "-RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) "
        f"-MultipleInstances IgnoreNew -Priority {priority}; "
        f"Register-ScheduledTask -TaskPath '{TASKS}' -TaskName {_ps_quote(name)} -Action $a -Trigger $t -Principal $p "
        f"-Settings $s -Description {_ps_quote(f'Aurora — {name} (written by sys_install_tasks.py)')} -Force | Out-Null")
    r = sys_platform.current()._ps(script, 120)
    if r.code != 0:
        raise SystemExit(f"task {name}: {(r.out + r.err).strip()[-400:]}")


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
    ap.add_argument("--user", required=True, help="DOMAIN\\name of the user who owns Aurora")
    ap.add_argument("--no-start", action="store_true")
    a = ap.parse_args()
    plat = sys_platform.current()
    if not plat.is_admin():
        ap.error("run as the administrator (install.ps1 does)")
    cfg = sys_config.get()
    try:
        caddyfile = net_https.write(cfg)
    except net_https.HttpsError as e:
        print(f"{net_https.caddyfile(cfg)}: INVALID\n{e}")
        return 1
    print(f"{caddyfile}: valid")
    if str(cfg["AURORA_LLM_BACKEND"]) != "cloud":
        print("! the local reasoner (llama.cpp) is not installed on Windows yet: Aurora reasons in the cloud")
    for name, (program, args, prio) in tasks(cfg).items():
        register(cfg, a.user, name, program, args, prio)
        print(f"  task {TASKS}{name}: {Path(program).name} {args}")
    if a.no_start:
        return 0
    # restart, not start: on an update the tasks are running the old code, and a running task ignores a start
    # (IgnoreNew — a real Windows, 9 Oct: the encoder kept the code from before the update)
    r = plat.service_action("restart", [f"aurora-{n}" for n in tasks(cfg)])
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

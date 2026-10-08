#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The port on a REAL machine (owner, 2026-10-08: «non ho né un Mac né un Windows»): every read of the platform backend
called for real and, where a right answer is known, checked against the machine itself — a socket opened here must be
in listening(), a lock held by one process must stop another, a system folder is the administrators' and a temporary
one is not, a file replaced while another reads it, text with accents through run().

    python probe.py BUILT_TREE [--json FILE]        (build.py --probe calls it on the tree it built)

Prints one line per check (ok / FAIL / info) and exits 1 when a check fails. Services are not started here: the
installer (phase 3) registers them. The same file in both ports."""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

ROWS: list[dict] = []


def check(name: str, fn, expect=None):
    """fn() -> value; expect(value) -> True | str (why not). No expectation: recorded as info."""
    t0 = time.time()
    try:
        v = fn()
        why = True if expect is None else expect(v)
        status = "info" if expect is None else ("ok" if why is True else "FAIL")
        row = {"check": name, "status": status, "value": _short(v), "seconds": round(time.time() - t0, 3)}
        if why is not True and expect is not None:
            row["why"] = str(why)
    except Exception as e:  # noqa: BLE001 — a probe records, never stops
        row = {"check": name, "status": "FAIL", "error": f"{type(e).__name__}: {e}"[:400],
               "trace": traceback.format_exc()[-800:], "seconds": round(time.time() - t0, 3)}
    ROWS.append(row)
    print(f"{row['status']:4} {name:34} {row.get('why') or row.get('error') or row['value']}"[:220], flush=True)
    return row


def _short(v):
    try:
        s = json.dumps(v, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        s = repr(v)
    return s if len(s) <= 300 else s[:297] + "..."


def _lock_holder(core: str, path: str, ready: str, release: str) -> list[str]:
    code = ("import sys,time,pathlib; sys.path.insert(0, %r)\nfrom aurora import sys_platform\np = sys_platform.current()\n"
            "fh = open(%r, 'a+', encoding='utf-8')\np.lock(fh)\npathlib.Path(%r).write_text('1')\n"
            "while not pathlib.Path(%r).exists(): time.sleep(0.05)\np.unlock(fh)\nfh.close()\n") % (core, path, ready, release)
    return [sys.executable, "-c", code]


CHILD = r"""
import json, os, socket, sys
from pathlib import Path
root, home_secret = Path(sys.argv[1]), Path(sys.argv[2])
def read(p):
    try:
        return Path(p).read_text(encoding="utf-8")
    except Exception as e:
        return f"denied:{type(e).__name__}"
def write(p):
    try:
        Path(p).write_text("x", encoding="utf-8")
        return "written"
    except Exception as e:
        return f"denied:{type(e).__name__}"
def net():
    try:
        socket.create_connection(("1.1.1.1", 443), 5).close()
        return "connected"
    except Exception as e:
        return f"denied:{type(e).__name__}"
print(json.dumps({"code": read(root / "sys" / "core" / "code.py"), "env": read(root / ".env"),
                  "push": read(root / "sys" / "status" / "push" / "vapid.pem"),
                  "own_env": read(os.environ.get("AURORA_ENV_FILE", "")), "home": read(home_secret),
                  "write_own": write(root / "usr" / "notes" / "n.txt"), "write_code": write(root / "sys" / "core" / "w.py"),
                  "net": net()}))
"""


class _Cfg:
    """The least of a Config cage_plan and the Linux cage read: a fake installation under the probe's temp folder."""
    def __init__(self, root: Path):
        self.root, self.env_file, self.user, self.base = root, root / ".env", None, None
        self._p = {"AURORA_STATUS_DIR": root / "sys" / "status", "AURORA_NOTES_DIR": root / "usr" / "notes"}

    def path(self, key):
        return self._p[key]


def cage_check(p, tmp: Path, core: str, network: bool):
    """A process in this system's real cage (bubblewrap, sandbox-exec, an AppContainer) against secrets it must not
    see: the same criterion everywhere — the secret's text never comes out."""
    root = tmp / f"inst-{int(network)}"
    for d in ("sys/core", "sys/status/push", "sys/status/plugins/env", "usr/notes", "plugins/forged"):
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / "sys/core/code.py").write_text("CODE_OK", encoding="utf-8")
    (root / ".env").write_text("TOKEN=SECRET_ENV_1234", encoding="utf-8")
    (root / "sys/status/push/vapid.pem").write_text("SECRET_PUSH_5678", encoding="utf-8")
    filtered = root / "sys/status/plugins/env/forged.env"
    filtered.write_text("TOKEN=redacted OWN_ENV_OK", encoding="utf-8")
    home_secret = Path.home() / f".aurora-probe-secret-{os.getpid()}"
    home_secret.write_text("SECRET_HOME_9012", encoding="utf-8")
    try:
        manifest = {"sandbox": {"write": ["AURORA_NOTES_DIR"], **({} if network else {"network": False})}}
        cmd = [sys.executable, "-c", CHILD, str(root), str(home_secret)]
        caged = p.cage(cmd, root / "plugins/forged", manifest, filtered, _Cfg(root))
        if not caged:
            return "no cage on this system"
        ccmd, env = caged
        r = subprocess.run(ccmd, capture_output=True, text=True, timeout=600, cwd=root / "plugins/forged",
                           env={**os.environ, "PYTHONPATH": core, "AURORA_ENV_FILE": str(root / ".env"), **env})
        out = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {"stderr": r.stderr[-600:]}
        return out
    finally:
        home_secret.unlink(missing_ok=True)


def cage_ok(v, network: bool):
    if isinstance(v, str):
        return v
    if "stderr" in v:
        return f"the caged process did not answer: {v['stderr']}"
    bad = [k for k, secret in (("env", "SECRET_ENV"), ("push", "SECRET_PUSH"), ("home", "SECRET_HOME")) if secret in v[k]]
    bad += [k for k, want in (("code", "CODE_OK"), ("own_env", "OWN_ENV_OK")) if want not in v[k]]
    bad += ["write_own"] if v["write_own"] != "written" else []
    bad += ["write_code"] if v["write_code"] == "written" else []
    bad += ["net"] if (v["net"] == "connected") != network else []
    return True if not bad else f"wrong: {bad} in {v}"


def main() -> int:
    tree = Path(sys.argv[1]).resolve()
    out_json = Path(sys.argv[sys.argv.index("--json") + 1]) if "--json" in sys.argv else None
    core = str(tree / "sys" / "core")
    sys.path.insert(0, core)
    from aurora import sys_platform
    p = sys_platform.current()
    tmp = Path(tempfile.mkdtemp(prefix="aurora-probe-"))
    print(f"== {p.name} backend on {sys.platform}, Python {sys.version.split()[0]}, {tree}")

    # ---- the machine
    def zone():
        """Aurora's clock, calendar and .ics read their time zone by name (AURORA_TIMEZONE): it must exist here."""
        from datetime import datetime
        from zoneinfo import ZoneInfo
        rome = datetime(2026, 7, 1, 12, tzinfo=ZoneInfo("Europe/Rome")).utcoffset().total_seconds() / 3600
        winter = datetime(2026, 12, 1, 12, tzinfo=ZoneInfo("Europe/Rome")).utcoffset().total_seconds() / 3600
        return {"summer": rome, "winter": winter}
    check("time zone Europe/Rome", zone, lambda v: v == {"summer": 2.0, "winter": 1.0} or str(v))
    check("os_info", p.os_info, lambda v: isinstance(v, dict) and bool(v) or "empty")
    check("machine_id stable", lambda: (p.machine_id(), p.machine_id()), lambda v: v[0] == v[1] and len(v[0]) >= 8 or "unstable or short")
    check("is_admin", p.is_admin, lambda v: isinstance(v, bool) or "not a bool")
    check("memory", p.memory, lambda v: 0 < v.get("used_mib", -1) <= v.get("total_mib", 0) or str(v))

    def cpu_twice():
        a = p.cpu_times()
        sum(i * i for i in range(2_000_000))
        return a, p.cpu_times()
    check("cpu_times grow", cpu_twice, lambda v: v[1][1] > v[0][1] or "total did not grow")
    check("gpus", p.gpus, lambda v: isinstance(v, list) or "not a list")
    check("accelerator", p.accelerator, lambda v: v in ("cuda", "metal", "cpu") or f"unknown {v}")
    check("gpu_free_mib(0)", lambda: p.gpu_free_mib(0), lambda v: v is None or v >= 0 or "negative")

    # ---- the network: a socket of ours must be seen listening
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen()
    port = srv.getsockname()[1]
    check("listening sees our socket", p.listening,
          lambda v: any(str(x.get("port")) == str(port) and x.get("proto") == "tcp" for x in v) or f"port {port} not among {len(v)}")
    srv.close()
    check("own_addresses", p.own_addresses, lambda v: bool(v) and all(isinstance(a, str) for a in v) or "empty")
    if sys.platform == "win32":                     # no mounts on Windows by design: the NAS is \\host\share (PORTING.md)
        check("is_mount (none on Windows)", lambda: (p.is_mount(Path("C:/")), p.is_mount(tmp)),
              lambda v: v == (False, False) or str(v))
    else:
        check("is_mount(root)", lambda: p.is_mount(Path("/")), lambda v: v is True or "root not a mount")
        check("is_mount(temp folder)", lambda: p.is_mount(tmp), lambda v: v is False or "a temp folder seen as a mount")

    # ---- files: trust, locks, replace, text
    check("key_dir absolute", p.key_dir, lambda v: Path(v).is_absolute() or "relative")
    check("temp folder NOT admin-only", lambda: p.trusted_by_admin_only(tmp), lambda v: v[0] is False or f"trusted: {v[1]}")
    sysdir = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" if sys.platform == "win32" else Path("/usr/bin")
    check("system folder admin-only", lambda: p.trusted_by_admin_only(sysdir), lambda v: v[0] is True or f"not trusted: {v[1]}")

    lockf, ready, release = tmp / "budget.json", tmp / "ready", tmp / "release"
    lockf.write_text("{}", encoding="utf-8")

    def contention():
        holder = subprocess.Popen(_lock_holder(core, str(lockf), str(ready), str(release)))
        for _ in range(200):
            if ready.exists():
                break
            time.sleep(0.05)
        with open(lockf, "a+", encoding="utf-8") as fh:
            while_held = p.lock(fh, wait=False)
            release.write_text("1")
            holder.wait(timeout=30)
            after = p.lock(fh, wait=False)
            if after:
                p.unlock(fh)
        return {"while_held": while_held, "after_release": after, "content": lockf.read_text(encoding="utf-8")}
    check("lock stops another process", contention,
          lambda v: (v["while_held"] is False and v["after_release"] is True and v["content"] == "{}") or str(v))

    def replace_while_read():
        dst, src = tmp / "state.json", tmp / "state.json.tmp"
        dst.write_text("old", encoding="utf-8")
        src.write_text("new è", encoding="utf-8")
        reader = open(dst, encoding="utf-8")
        threading.Timer(0.3, reader.close).start()          # a reader that lets go a moment later (Windows: busy)
        p.replace(src, dst)
        return dst.read_text(encoding="utf-8")
    check("replace while read", replace_while_read, lambda v: v == "new è" or repr(v))
    check("run: text with accents", lambda: p.run([sys.executable, "-c", "print('àèìòù €')"], 30).out.strip(),
          lambda v: v == "àèìòù €" or repr(v))
    check("process_env", p.process_env, lambda v: (sys.platform != "win32" or v.get("PYTHONUTF8") == "1") or "no PYTHONUTF8")

    def venv():
        v = tmp / "venv"
        subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(v)], check=True, timeout=120)
        return str(p.venv_python(v)), p.venv_python(v).exists()
    check("venv_python of a real venv", venv, lambda v: v[1] or f"{v[0]} missing")
    check("runtime_dir", p.runtime_dir, None)
    check("bold_font", p.bold_font, lambda v: v is None or Path(v).exists() or f"{v} missing")
    check("fonts", p.fonts, None)
    def drawtext():
        """ffmpeg draws a letter with the system's bold font, its path written by ffmpeg_path: a wrong escape (C:,
        backslashes, a quote) makes ffmpeg fail — the real test of what videos and pictures do with fonts."""
        import shutil as sh
        font = p.bold_font()
        if not sh.which("ffmpeg") or not font:
            return "skipped: no ffmpeg or no bold font"
        out = tmp / "drawtext.png"
        r = p.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x32",
                   "-vf", f"drawtext=fontfile={p.ffmpeg_path(Path(font))}:text=A:fontcolor=white", "-frames:v", "1",
                   str(out)], 60)
        return {"code": r.code, "png": out.exists() and out.stat().st_size > 0, "err": r.err.strip()[-200:],
                "path": p.ffmpeg_path(Path(font))}
    def ffmpeg_parts():
        """Every filter and encoder Aurora's code asks of ffmpeg (kno_story's videos, aud_analysis's DJ, kno_video's
        scenes): the one this machine has lacks none (v0.2.0+'s Mac: Homebrew's ffmpeg had no drawtext)."""
        import shutil as sh
        if not sh.which("ffmpeg"):
            return "skipped: no ffmpeg"
        filters = set(re.findall(r"^\s*[.A-Z|]{2,3}\s+(\w+)\s", p.run(["ffmpeg", "-hide_banner", "-filters"], 60).out, re.M))
        encoders = set(re.findall(r"^\s*[VAS.][.A-Z]{5}\s+(\w+)\s", p.run(["ffmpeg", "-hide_banner", "-encoders"], 60).out, re.M))
        need_f = {"scale", "crop", "zoompan", "fade", "format", "apad", "subtitles", "drawtext", "volume", "afade",
                  "amix", "loudnorm", "rubberband", "select", "metadata"}
        need_e = {"libx264", "aac", "mjpeg"}
        return {"missing_filters": sorted(need_f - filters), "missing_encoders": sorted(need_e - encoders),
                "version": p.run(["ffmpeg", "-hide_banner", "-version"], 30).out.splitlines()[0][:80]}
    check("ffmpeg has Aurora's filters", ffmpeg_parts,
          lambda v: (isinstance(v, str)) or (not v["missing_filters"] and not v["missing_encoders"]) or str(v))
    check("ffmpeg drawtext with ffmpeg_path", drawtext,
          lambda v: (isinstance(v, str) and v.startswith("skipped")) or (v["code"] == 0 and v["png"]) or str(v))
    check("dictionaries", p.dictionaries, None)

    # ---- devices (a runner has none: no error is the check)
    check("cameras", p.cameras, lambda v: isinstance(v, list) or "not a list")
    check("microphones", p.microphones, lambda v: isinstance(v, list) or "not a list")

    # ---- services: read only (none is installed on a fresh machine)
    for name in ("service_state", "service_info", "service_next_run", "service_command"):
        check(f"{name}(not installed)", lambda n=name: getattr(p, n)("aurora-api"), None)
    check("service_action refuses others'", lambda: _refused(p), lambda v: v is True or "a foreign unit was accepted")

    # ---- what the owner reads
    check("sandbox", p.sandbox, None)
    check("cage: secrets hidden, own files only, network", lambda: cage_check(p, tmp, core, True),
          lambda v: cage_ok(v, True))
    check("cage without network", lambda: cage_check(p, tmp, core, False), lambda v: cage_ok(v, False))
    check("host_firewall", p.host_firewall, None)
    check("install_hint(ffmpeg)", lambda: p.install_hint("ffmpeg"), lambda v: bool(v) or "empty")
    check("as_admin", lambda: p.as_admin("python x.py"), lambda v: bool(v) or "empty")
    check("in_folder", lambda: p.in_folder(tmp, "python x.py"), lambda v: str(tmp) in v or "folder missing")

    failed = [r for r in ROWS if r["status"] == "FAIL"]
    print(f"== {len(ROWS)} checks: {sum(r['status'] == 'ok' for r in ROWS)} ok, {len(failed)} failed, "
          f"{sum(r['status'] == 'info' for r in ROWS)} info")
    if out_json:
        out_json.write_text(json.dumps({"platform": sys.platform, "python": sys.version, "backend": p.name, "rows": ROWS},
                                       ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if failed else 0


def _refused(p) -> bool:
    try:
        p.service_action("restart", ["sshd"])
    except (ValueError, PermissionError, RuntimeError):
        return True
    return False


if __name__ == "__main__":
    sys.exit(main())

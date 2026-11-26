# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N152 version 1: what the preview needs — the program behind a window (package and version from dpkg, the
launch line from /proc) and each step said in plain Italian."""
import os
import subprocess


def program_meta(pid: int) -> dict:
    """{"name", "exe", "package", "version", "args"}; version '' when dpkg does not know the binary (Flatpak, AppImage,
    interpreters: the draft then says «sconosciuta», bozza 8 §4)."""
    exe = os.path.realpath(f"/proc/{pid}/exe")
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            argv = [a.decode(errors="replace") for a in f.read().split(b"\0") if a]
    except OSError:
        argv = [exe]
    pkg = ver = ""
    try:
        r = subprocess.run(["/usr/bin/dpkg-query", "-S", exe], capture_output=True, text=True, timeout=10,
                           env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
        if r.returncode == 0 and ":" in r.stdout:
            pkg = r.stdout.split(":", 1)[0].split(",")[0].strip()
            v = subprocess.run(["/usr/bin/dpkg-query", "-W", "-f=${Version}", pkg], capture_output=True, text=True,
                               timeout=10, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
            ver = v.stdout.strip() if v.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        pass
    name = os.path.basename(argv[0]) if argv else os.path.basename(exe)
    return {"name": name, "exe": exe if exe.startswith("/usr/") else (argv[0] if argv else exe), "package": pkg or name,
            "version": ver, "args": argv[1:]}


def _anchor(t: dict, loc: str) -> str:
    if not t:
        return ""
    nm = (t.get("name") or {}).get(loc) or (t.get("name_re") or {}).get(loc)
    if nm:
        return f"«{nm}»"
    e = t.get("id_end") or ""
    return f"«{e.rsplit('.', 1)[-1]}»" if e else f"un elemento «{t.get('role', '?')}»"


ROLE_IT = {"text": "il campo", "menu item": "la voce di menu", "push button": "il bottone", "button": "il bottone",
           "push button menu": "il bottone di menu", "button menu": "il bottone di menu", "check box": "la casella",
           "list item": "l'elemento"}


def _in(what: str) -> str:
    """«in» + article as Italian joins them: nel campo, nella casella, nell'elemento, in un elemento."""
    for art, joined in (("il ", "nel "), ("la ", "nella "), ("l'", "nell'"), ("lo ", "nello ")):
        if what.startswith(art):
            return joined + what[len(art):]
    return "in " + what


def describe(step: dict, loc: str = "it") -> str:
    t = step.get("target") or {}
    what = f"{ROLE_IT.get(t.get('role'), t.get('role', ''))} {_anchor(t, loc)}".strip()
    do = step["do"]
    if do == "type":
        return f"scrivi {step.get('text')} {_in(what)}"
    if do == "press":
        return f"premi {what}"
    if do == "open_menu":
        return f"apri {what}"
    if do == "key":
        return f"tasto {step.get('keys')}"
    if do == "read":
        return f"leggi {what} → {step.get('into')}"
    if do == "press_each":
        return f"premi i tasti di {step.get('text')}"
    return do

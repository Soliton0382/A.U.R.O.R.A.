# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Nothing left behind (owner, 2026-10-08: «cerchiamo di non lasciare niente alle spalle»). Two nets over the built
tree, outside sys_platform:

 words      Linux-only names in the modules Aurora runs (systemctl, fcntl, /proc, pwd, bwrap...)
 programs   EVERY external program started (subprocess, read from the code's syntax tree), in the modules and in the
            scripts: each one listed here, cross-platform or with its phase in PORTING.md

A new call in the Linux code fails here as soon as the port is built. The same file in both ports."""
import ast
import re
from pathlib import Path

CORE = Path(__file__).resolve().parents[1]
AURORA, SCRIPT = CORE / "aurora", CORE / "script"
PLUGINS = CORE.parent / "plugins"
LINUX_ONLY = re.compile(r'"systemctl"|\bfcntl\b|/proc/|"nvidia-smi"|import pwd|os\.getuid|os\.geteuid|"bwrap"|"pactl"|'
                        r'v4l2|/dev/video|\.venv/bin|journalctl|"sudo"|/usr/share/dict|/dev/null')
WORDS_ALLOWED = {
    ("sys_config.py", "import pwd"): "guarded: Windows takes getpass (FILES)",
    ("sys_bugreport.py", '"nvidia-smi"'): "the driver's version in a bug report; not found = «not measured» everywhere",
    ("mdl_custom.py", '"nvidia-smi"'): "the GPU memory others hold, for the Models page's fit; not found = 0 (C252)",
    ("prj_run.py", '"bwrap"'): "phase 4: without bwrap a project does not run («no cage, nothing is run»)",
    ("plg_sandbox.py", '"bwrap"'): "phase 4: without a cage plugins do not run on the Mac or Windows (GUARDS)",
    ("plg_sandbox.py", "/dev/null"): "phase 4: bwrap's own arguments, Linux only",
    ("sec_hostfw.py", '"sudo"'): "phase 4: the host firewall (nft) — not installed elsewhere, it says so",
}
# programs every system has, or that Aurora installs everywhere (phase 3 installs them on the Mac and Windows)
EVERYWHERE = {"ffmpeg", "ffprobe", "git", "curl", "pdfinfo", "pdftoppm", "sys.executable"}
# (file, program): why it may stay — the modules
PROGRAMS_ALLOWED = {
    ("sec_hostaudit.py", "ss"): "the Linux branch only; netstat (Mac) and psutil (Windows) otherwise (NETWORK)",
    ("sys_bugreport.py", "nvidia-smi"): "a bug report's driver version: «not measured» where missing",
    ("mdl_custom.py", "nvidia-smi"): "the GPU memory others hold (C252): 0 where missing, llama.cpp's --fit decides",
    ("sec_hostfw.py", "sudo"): "phase 4: the host firewall",
}
# the scripts the owner or the installer runs: all of phase 3 (installers and admin scripts per system)
SCRIPTS_PHASE_3 = {"systemctl", "journalctl", "runuser", "systemd-escape", "systemd-mount", "systemd-umount",
                   "nvidia-smi", "cfg['AURORA_CADDY_BIN']"}
# each port's own installer scripts start their system's own programs (phase 3, 9 Oct): the Mac's launchd agents
PORT_SCRIPTS = {("sys_install_agents.py", "launchctl"), ("sys_install_agents.py", "brew")}


def _programs(f: Path) -> set[str]:
    out = set()
    for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
        if not (isinstance(n, ast.Call) and n.args and isinstance(n.func, ast.Attribute)):
            continue
        if not (getattr(n.func.value, "id", "") == "subprocess" and n.func.attr in ("run", "Popen", "check_output", "call", "check_call")):
            continue
        a = n.args[0]
        if isinstance(a, ast.List) and a.elts and isinstance(a.elts[0], ast.Constant):
            out.add(str(a.elts[0].value))
        elif isinstance(a, ast.List) and a.elts:
            out.add(ast.unparse(a.elts[0]))
    return out


# the plugins (owner, 2026-10-08: «verifica che anche i vari plugin funzionino… vedi cloudflare»): their own code, beside
# the core's — (plugin, word or program): why it may stay
PLUGIN_WORDS_ALLOWED = {
    ("dropbox", ".venv/bin"): "the docstring of authorize.py, a command the owner reads (phase 3: per system)",
    ("tiktok", ".venv/bin"): "the docstring of authorize.py, a command the owner reads (phase 3: per system)",
}
PLUGIN_PROGRAMS_ALLOWED = {("facebook", "ffprobe"), ("projects", "git")}       # both in EVERYWHERE's installers
# a plugin started by a program of its own (not Python): it must exist for each system (phase 3, PORTING.md)
PLUGIN_COMMANDS = {"github": "{root}/sys/runtime/github-mcp-server/github-mcp-server"}


def _modules():
    return [f for f in sorted(AURORA.rglob("*.py")) if "sys_platform" not in f.parts]


def test_no_linux_only_word_left_in_the_modules_but_the_listed_ones():
    found = set()
    for f in _modules():
        for line in f.read_text(encoding="utf-8").splitlines():
            code = line.split("#", 1)[0]
            if (m := LINUX_ONLY.search(code)) and not code.strip().startswith(('"', "'")):
                found.add((f.name, m.group(0)))
    assert not found - set(WORDS_ALLOWED), f"Linux-only words not in PORTING.md: {sorted(found - set(WORDS_ALLOWED))}"


def test_every_program_the_modules_start_is_cross_platform_or_listed():
    unexpected = set()
    for f in _modules():
        for prog in _programs(f):
            if prog in EVERYWHERE or (f.name, prog) in PROGRAMS_ALLOWED or prog.startswith(("str(", "cfg[", "self.", "*")):
                continue                                   # a path from the settings: written by the installer (phase 3)
            unexpected.add((f.name, prog))
    assert not unexpected, f"programs not cross-platform and not in PORTING.md: {sorted(unexpected)}"


def test_every_program_the_scripts_start_is_known_and_left_to_phase_3():
    unexpected = set()
    for f in sorted(SCRIPT.glob("*.py")):
        for prog in _programs(f):
            if prog in EVERYWHERE or prog in SCRIPTS_PHASE_3 or (f.name, prog) in PORT_SCRIPTS \
                    or prog.startswith(("str(", "self.", "*")):
                continue
            unexpected.add((f.name, prog))
    assert not unexpected, f"programs of the scripts not in PORTING.md: {sorted(unexpected)}"


def test_the_plugins_code_has_no_linux_only_word_or_program_but_the_listed_ones():
    import json
    words, progs, cmds = set(), set(), {}
    for d in sorted(x for x in PLUGINS.iterdir() if (x / "plugin.json").is_file()):
        m = json.loads((d / "plugin.json").read_text(encoding="utf-8"))
        if (m.get("command") or ["{python}"])[0] != "{python}":
            cmds[d.name] = m["command"][0]
        for f in d.rglob("*.py"):
            for line in f.read_text(encoding="utf-8").splitlines():
                if (w := LINUX_ONLY.search(line.split("#", 1)[0])):
                    words.add((d.name, w.group(0)))
            progs |= {(d.name, prog) for prog in _programs(f)}
    assert not words - set(PLUGIN_WORDS_ALLOWED), f"Linux-only words in plugins: {sorted(words - set(PLUGIN_WORDS_ALLOWED))}"
    assert not progs - PLUGIN_PROGRAMS_ALLOWED, f"programs started by plugins: {sorted(progs - PLUGIN_PROGRAMS_ALLOWED)}"
    assert cmds == PLUGIN_COMMANDS, f"plugins started by their own program: {cmds}"


def test_every_absolute_path_by_default_is_absolute_on_this_port_s_system():
    """Found on a real Windows (8 Oct): «/usr/bin/caddy» is no absolute path there, the configuration refused to load
    with the factory settings. Each port's defaults.json gives its own (build.py applies it)."""
    import json
    import ntpath
    import posixpath
    port = json.loads((CORE.parents[1] / "BUILD.json").read_text(encoding="utf-8"))["port"]
    isabs = ntpath.isabs if port == "Aurora_windows" else posixpath.isabs
    schema = json.loads((CORE / "config" / "settings_schema.json").read_text(encoding="utf-8"))
    bad = [(x["key"], x["recommended"]) for x in schema["settings"] if x["type"] == "path_abs"
           and not (isabs(x["recommended"]) and (port != "Aurora_windows" or ntpath.splitdrive(x["recommended"])[0]))]
    assert not bad, f"factory paths not absolute on {port}: {bad}"

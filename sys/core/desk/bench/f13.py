# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""F13: no library from the home (U3), with a ScreenCast capture through GStreamer (pipewiresrc).

Baits, built here with gcc: a .so whose constructor writes a marker (pid, ppid, executable) if it is ever loaded.
    e1  ~/.local/share/gstreamer-1.0/plugins/libgstn152bait.so
    e2  ~/.local/share/vulkan/implicit_layer.d/n152.json -> an absolute path to the bait
    e3  ~/.config/pipewire/client.conf.d/n152.conf -> context.modules with the bait's absolute path
all inside a bench «owner home». New environment (§4.2 point 3): the «root» folders are bench folders made read-only
(0555) and a GStreamer registry written once with the system plugins only, then 0444. Positive control: the same
start with only HOME = a fresh copy of the bait home (the GStreamer cache is per home: a used one would skip e1).
"""
import json
import shutil
import subprocess
import time
from pathlib import Path

from .guard import descendants

HERE = Path(__file__).resolve().parent
CODE_DIR = HERE.parents[3]                              # the repository: the «code folder» of the rule
GST_SYS = "/usr/lib/x86_64-linux-gnu/gstreamer-1.0"
GST_SCANNER = "/usr/lib/x86_64-linux-gnu/gstreamer1.0/gstreamer-1.0/gst-plugin-scanner"
BAIT_C = r"""
#include <stdio.h>
#include <unistd.h>
#include <limits.h>
__attribute__((constructor)) static void n152_bait(void) {
    char exe[PATH_MAX] = {0}, path[PATH_MAX];
    readlink("/proc/self/exe", exe, sizeof exe - 1);
    snprintf(path, sizeof path, "%s/%s-%d.mark", MARKDIR, BAIT, (int)getpid());
    FILE *f = fopen(path, "w");
    if (f) { fprintf(f, "{\"bait\":\"%s\",\"pid\":%d,\"ppid\":%d,\"exe\":\"%s\"}\n", BAIT, (int)getpid(),
                     (int)getppid(), exe); fclose(f); }
}
int pipewire__module_init(void *m, const char *a) { (void)m; (void)a; return 0; }
"""


def build_baits(wd: Path) -> dict:
    src, lib, marks = wd / "src", wd / "lib", wd / "markers"
    for d in (src, lib, marks):
        d.mkdir(parents=True, exist_ok=True)
    (src / "bait.c").write_text(BAIT_C)
    out = {}
    for name in ("e1", "e2", "e3"):
        so = lib / f"n152bait_{name}.so"
        subprocess.run(["/usr/bin/gcc", "-shared", "-fPIC", "-O1", f'-DMARKDIR="{marks}"', f'-DBAIT="{name}"',
                        "-o", str(so), str(src / "bait.c")], check=True, env={"PATH": "/usr/bin:/bin"})
        out[name] = so
    return {"libs": out, "markers": marks}


def plant(home: Path, baits: dict) -> None:
    gst = home / ".local/share/gstreamer-1.0/plugins"
    vk = home / ".local/share/vulkan/implicit_layer.d"
    pw = home / ".config/pipewire/client.conf.d"
    for d in (gst, vk, pw):
        d.mkdir(parents=True, exist_ok=True)
    shutil.copy(baits["libs"]["e1"], gst / "libgstn152bait.so")
    (vk / "n152.json").write_text(json.dumps({"file_format_version": "1.0.0", "layer": {
        "name": "VK_LAYER_N152_bait", "type": "GLOBAL", "library_path": str(baits["libs"]["e2"]),
        "api_version": "1.3.0", "implementation_version": "1", "description": "bench bait",
        "disable_environment": {"N152_NO_BAIT": "1"}}}))
    (pw / "n152.conf").write_text("context.modules = [\n  { name = %s flags = [ nofail ] }\n]\n"
                                  % baits["libs"]["e3"])


def desk_env_dirs(wd: Path, bench_env: dict) -> dict:
    """The «root» folders of §4.2 simulated: created, the registry written once, then everything read-only."""
    root = wd / "desk-env"
    dirs = {k: root / k for k in ("home", "config", "data", "state", "cache")}
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    reg = root / "gst-registry.bin"
    env = dict(bench_env, HOME=str(dirs["home"]), XDG_CONFIG_HOME=str(dirs["config"]),
               XDG_DATA_HOME=str(dirs["data"]), XDG_CACHE_HOME=str(dirs["cache"]),
               XDG_STATE_HOME=str(dirs["state"]), GST_PLUGIN_SYSTEM_PATH=GST_SYS, GST_PLUGIN_PATH="",
               GST_PLUGIN_SCANNER=GST_SCANNER, GST_REGISTRY=str(reg))
    code = ("import gi; gi.require_version('Gst','1.0'); from gi.repository import Gst; Gst.init(None); "
            "print(Gst.ElementFactory.find('pipewiresrc') is not None)")
    r = subprocess.run(["/usr/bin/python3", "-I", "-B", "-c", code], env=env, capture_output=True, text=True,
                       timeout=120)
    reg.chmod(0o444)
    for d in list(dirs.values()) + [root]:
        d.chmod(0o555)
    return {"dirs": dirs, "registry": reg, "registry_has_pipewiresrc": r.stdout.strip() == "True"}


def new_env(base: dict, de: dict) -> dict:
    d = de["dirs"]
    e = dict(base)
    e.update({"HOME": str(d["home"]), "XDG_CONFIG_HOME": str(d["config"]), "XDG_DATA_HOME": str(d["data"]),
              "XDG_STATE_HOME": str(d["state"]), "XDG_CACHE_HOME": str(d["cache"]),
              "XDG_DATA_DIRS": "/usr/local/share:/usr/share", "XDG_CONFIG_DIRS": "/etc/xdg",
              "GST_PLUGIN_SYSTEM_PATH": GST_SYS, "GST_PLUGIN_PATH": "", "GST_PLUGIN_SCANNER": GST_SCANNER,
              "GST_REGISTRY": str(de["registry"]), "GST_REGISTRY_UPDATE": "no",
              "VK_LOADER_LAYERS_DISABLE": "~implicit~",
              "SPA_PLUGIN_DIR": "/usr/lib/x86_64-linux-gnu/spa-0.2",
              "PIPEWIRE_MODULE_DIR": "/usr/lib/x86_64-linux-gnu/pipewire-0.3",
              "MESA_SHADER_CACHE_DISABLE": "true"})
    return e


def control_env(base: dict, home: Path) -> dict:
    e = dict(base)
    for k in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"):
        e.pop(k, None)
    e["HOME"] = str(home)
    return e


def read_maps(pid: int, homes: list) -> dict:
    """Executable file mappings outside /usr and the code folder; any mapping from a bench home."""
    try:
        lines = Path(f"/proc/{pid}/maps").read_text().splitlines()
    except OSError as e:
        return {"error": str(e)}
    exe_out, home_any, files = set(), set(), set()
    for ln in lines:
        parts = ln.split(None, 5)
        if len(parts) < 6 or not parts[5].startswith("/"):
            continue
        path, perms = parts[5], parts[1]
        if path.startswith("/memfd:"):
            continue
        files.add(path)
        if any(path.startswith(str(h)) for h in homes):
            home_any.add(path)
        if "x" in perms and not (path.startswith("/usr/") or path.startswith(str(CODE_DIR) + "/")):
            exe_out.add(path)
    return {"exec_outside": sorted(exe_out), "from_home": sorted(home_any), "n_files": len(files),
            "non_usr": sorted(p for p in files if not p.startswith("/usr/"))}


def markers(marks: Path, tree: set) -> dict:
    out = {"all": [], "in_client_tree": []}
    for m in sorted(marks.glob("*.mark")):
        try:
            d = json.loads(m.read_text())
        except (OSError, ValueError):
            continue
        out["all"].append(d)
        if d["pid"] in tree or d["ppid"] in tree:
            out["in_client_tree"].append(d)
    return out


def session(bench, env: dict, tag: str, homes: list, marks: Path) -> dict:
    out = bench.base / "f13" / f"{tag}.json"
    before = {m.name for m in marks.glob("*.mark")}
    p = bench.procs.start(f"f13-{tag}", ["/usr/bin/python3", "-I", "-B", str(HERE / "probe_capture.py"),
                                         "--out", str(out), "--hold", "1.5", "--timeout", "20"],
                          env, stdout=bench.out("f13"), stderr=subprocess.STDOUT)
    tree = {p.pid}
    maps = None
    t0 = time.monotonic()
    while p.poll() is None and time.monotonic() - t0 < 60:
        tree |= set(descendants(p.pid))
        if out.exists() is False:
            m = read_maps(p.pid, homes)
            if "error" not in m:
                maps = m                                 # the last view before the client ends
        time.sleep(0.1)
    p.wait()
    try:
        res = json.loads(out.read_text())
    except (OSError, ValueError):
        res = {"error": "no result"}
    new = [m for m in marks.glob("*.mark") if m.name not in before]
    mk = markers(marks, tree)
    return {"tag": tag, "frames": (res.get("capture") or {}).get("frames", 0), "error": res.get("error"),
            "maps": maps, "new_markers": [m.name for m in new],
            "markers_in_tree": [d for d in mk["in_client_tree"] if any(n.name.endswith(f"-{d['pid']}.mark")
                                                                         for n in new)]}


def run(bench, n_new: int, n_control: int, log) -> dict:
    wd = bench.base / "f13"
    wd.mkdir(exist_ok=True)
    baits = build_baits(wd)
    owner_home = wd / "owner-home"                      # the «HOME del banco» with the baits
    plant(owner_home, baits)
    base = bench.wenv()
    de = desk_env_dirs(wd, base)
    res = {"registry_has_pipewiresrc": de["registry_has_pipewiresrc"], "new": [], "control": []}
    homes = [owner_home, de["dirs"]["home"]]
    for i in range(n_new):
        r = session(bench, new_env(base, de), f"new{i}", homes, baits["markers"])
        res["new"].append(r)
        log(f"F13 new={i} frames={r['frames']} marks={len(r['new_markers'])} "
            f"exec_out={len((r['maps'] or {}).get('exec_outside', []))}")
    # «se fallisce» decided before (frozen file): every culprit library put in the environment and the test run again.
    # Measured on the first runs: liborc's JIT maps an executable orcexec.* file from $XDG_RUNTIME_DIR (writable by
    # every process of the owner's uid); ORC_CODE=backup keeps it to its C fallbacks.
    res["new_fix"], res["fix_env"] = [], {"ORC_CODE": "backup"}
    for i in range(n_new):
        r = session(bench, dict(new_env(base, de), **res["fix_env"]), f"fix{i}", homes, baits["markers"])
        res["new_fix"].append(r)
        log(f"F13 fix={i} frames={r['frames']} marks={len(r['new_markers'])} "
            f"exec_out={len((r['maps'] or {}).get('exec_outside', []))}")
    for i in range(n_control):
        h = wd / f"control-home-{i}"
        shutil.copytree(owner_home, h, symlinks=True)
        r = session(bench, control_env(base, h), f"control{i}", homes + [h], baits["markers"])
        r["e1"] = any(d["bait"] == "e1" for d in r["markers_in_tree"])
        r["e2"] = any(d["bait"] == "e2" for d in r["markers_in_tree"])
        r["e3"] = any(d["bait"] == "e3" for d in r["markers_in_tree"])
        res["control"].append(r)
        log(f"F13 control={i} frames={r['frames']} e1={r['e1']} e2={r['e2']} e3={r['e3']}")
    return res

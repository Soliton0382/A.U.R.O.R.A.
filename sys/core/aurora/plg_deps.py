# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugins that bring their program (ROADMAP 101; owner, 2026-10-13: «attivo il plugin e lei scarica e installa»).

A plugin's manifest may declare what it needs beyond Aurora:

    "install": {"python": ["segno==1.6.6 --hash=sha256:28c7…"],                  # pinned, with their hashes
                "no_deps": false,                                                   # true: what Aurora has is not fetched
                "programs": [{"name": "tool", "url": "https://…", "sha256": "…"},   # a program and its checksum
                             {"name": "ngspice", "apt": "ngspice", "bin": "usr/bin/ngspice",
                              "relocate": "usr/share/ngspice"}]}      # or the system's own package, not installed

On the owner's «install» Aurora fetches them into the plugin's OWN folder — the libraries in <plugin>/.deps
(pip --target, every hash required when the manifest gives them), the programs in <plugin>/.bin, each checked
against its SHA-256 — never into Aurora's environment: a plugin's library cannot break Aurora. The plugin runs them
through script/plg_run.py ("command": ["{python}", "{root}/sys/core/script/plg_run.py", "server.py"]), which puts
.deps and .bin first in that process only. «Uninstall» removes the two folders: nothing else was written.

A program a system already packages (owner, 2026-10-21: «speravo si potesse fare qualcosa nell'env però senza sporcare
il sistema operativo») is taken from its package without installing it: apt-get download (no root; apt checks the
package against the repository's signed lists) and dpkg-deb -x into <plugin>/.bin/<name>/; the absolute /usr/ paths of
its own files under "relocate" are pointed at that folder; the program is run once to show it starts. Where there is
no apt (a Mac, Windows) nothing is fetched: the plugin says how to get it.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DEPS, BIN = ".deps", ".bin"
STATE = "installed.json"


def needs(manifest: dict) -> dict:
    inst = manifest.get("install") or {}
    return {"python": [str(x) for x in inst.get("python", [])], "programs": list(inst.get("programs", [])),
            "no_deps": bool(inst.get("no_deps"))}


def _size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.exists() else 0


def state(folder: Path, manifest: dict) -> dict:
    """What the plugin needs and whether it is installed, with the room it takes."""
    n = needs(manifest)
    wanted = bool(n["python"] or n["programs"])
    try:
        done = json.loads((folder / DEPS / STATE).read_text(encoding="utf-8")) if wanted else {}
    except (OSError, ValueError):
        done = {}
    if n["programs"] and not (folder / BIN).is_dir():
        done = {}
    return {"needs": n, "wanted": wanted, "installed": bool(done) or not wanted, "at": done.get("at"),
            "bytes": _size(folder / DEPS) + _size(folder / BIN)}


def install(folder: Path, manifest: dict, log=print, timeout: int = 900, cfg=None) -> dict:
    """Fetch and check what the manifest declares, into the plugin's folder; RuntimeError on any refusal (a wrong hash,
    a failed download): then nothing is left behind."""
    n = needs(manifest)
    deps_tmp, bin_tmp = folder / (DEPS + ".tmp"), folder / (BIN + ".tmp")
    for p in (deps_tmp, bin_tmp):
        shutil.rmtree(p, ignore_errors=True)
    try:
        if n["python"]:
            hashed = all("--hash=" in r for r in n["python"])
            with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
                f.write("\n".join(n["python"]) + "\n")
            cmd = [sys.executable, "-m", "pip", "install", "--target", str(deps_tmp), "--no-input",
                   "--disable-pip-version-check", "--no-warn-script-location", "-r", f.name]
            if hashed:
                cmd.insert(4, "--require-hashes")
            if n["no_deps"]:                                 # the rest is Aurora's already (e.g. Pillow): listed, not fetched
                cmd.insert(4, "--no-deps")
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            os.unlink(f.name)
            if r.returncode:
                raise RuntimeError(f"pip refused: {(r.stderr or r.stdout).strip()[-600:]}")
            log(f"libraries: {', '.join(x.split()[0] for x in n['python'])}" + (" (hashes checked)" if hashed else ""))
        if n["programs"]:
            import httpx
            bin_tmp.mkdir(parents=True)
            for prog in n["programs"]:
                name = str(prog["name"])
                if "/" in name or name.startswith("."):
                    raise RuntimeError(f"a program's name: {name!r}")
                if prog.get("apt"):
                    _from_package(prog, bin_tmp, folder / BIN, log)
                    continue
                url, want = str(prog["url"]), str(prog["sha256"]).lower()
                h, dest = hashlib.sha256(), bin_tmp / name
                with httpx.stream("GET", url, follow_redirects=True, timeout=120) as resp, open(dest, "wb") as out:
                    resp.raise_for_status()
                    for chunk in resp.iter_bytes(1 << 20):
                        h.update(chunk)
                        out.write(chunk)
                if h.hexdigest() != want:
                    raise RuntimeError(f"{name}: SHA-256 {h.hexdigest()} is not the declared {want}")
                dest.chmod(0o755)
                log(f"program {name}: {dest.stat().st_size} bytes, checksum right")
        deps_tmp.mkdir(parents=True, exist_ok=True)
        (deps_tmp / STATE).write_text(json.dumps({"at": time.time(), "python": n["python"],
                                                  "programs": [p["name"] for p in n["programs"]]}), encoding="utf-8")
        uninstall(folder)                                    # an older install replaced as a whole
        deps_tmp.rename(folder / DEPS)
        if bin_tmp.exists():
            bin_tmp.rename(folder / BIN)
        if cfg is not None:
            record(cfg, folder)                              # C579: checked again at every start
    except Exception:
        for p in (deps_tmp, bin_tmp):
            shutil.rmtree(p, ignore_errors=True)
        raise
    return state(folder, manifest)


def _from_package(prog: dict, bin_tmp: Path, final: Path, log) -> None:
    """The system's package of a program, unpacked into the plugin's folder (see above); nothing where there is no apt."""
    name, pkg = str(prog["name"]), str(prog["apt"])
    if not shutil.which("apt-get") or not shutil.which("dpkg-deb"):
        log(f"program {name}: no apt on this system — install it with the system's own way (e.g. brew install {pkg})")
        return
    if not pkg.replace("-", "").replace(".", "").isalnum():
        raise RuntimeError(f"a package's name: {pkg!r}")
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run(["apt-get", "download", pkg], cwd=tmp, capture_output=True, text=True, timeout=300)
        debs = sorted(Path(tmp).glob("*.deb"))
        if r.returncode or not debs:
            raise RuntimeError(f"apt-get download {pkg}: {(r.stderr or r.stdout).strip()[-400:]}")
        root = bin_tmp / name
        r = subprocess.run(["dpkg-deb", "-x", str(debs[0]), str(root)], capture_output=True, text=True, timeout=300)
        if r.returncode:
            raise RuntimeError(f"dpkg-deb {debs[0].name}: {r.stderr.strip()[-400:]}")
        log(f"program {name}: {debs[0].name} unpacked into the plugin's folder (nothing installed in the system)")
    if prog.get("relocate"):
        for f in (root / str(prog["relocate"])).rglob("*"):
            try:
                text = f.read_text(encoding="utf-8") if f.is_file() else None
            except UnicodeDecodeError:
                continue
            if text and "/usr/" in text:
                f.write_text(text.replace("/usr/", f"{final / name}/usr/"), encoding="utf-8")
    exe = root / str(prog.get("bin", f"usr/bin/{name}"))
    try:
        r = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=20)
    except OSError as e:
        raise RuntimeError(f"{name} does not start: {e}") from None
    if r.returncode:
        raise RuntimeError(f"{name} does not start (a library of the system missing?): {(r.stderr or r.stdout).strip()[-300:]}")
    said = [ln.strip(" *") for ln in (r.stdout or r.stderr).splitlines() if name.lower() in ln.lower()]
    log(f"program {name}: {said[0][:80] if said else 'starts'}")


# ---- C579: what was fetched, checked again at every start ----------------------------------------------------------
TREE = "tree.sealed"
_checked: dict[str, tuple] = {}


def _listing(folder: Path) -> list[tuple]:
    out = []
    for top in (DEPS, BIN):
        base = folder / top
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            for name in sorted(dirnames + filenames):
                p = Path(dirpath) / name
                rel = p.relative_to(folder).as_posix()
                if rel == f"{DEPS}/{TREE}" or "__pycache__" in rel.split("/"):
                    continue
                st = os.lstat(p)
                if os.path.islink(p):
                    out.append((rel, "link", os.readlink(p)))
                elif p.is_file():
                    out.append((rel, st.st_size, st.st_mtime_ns))
    return sorted(out)


def tree_digest(folder: Path) -> str:
    """Every file of .deps and .bin with its bytes, every link with its target (Python's caches left out)."""
    h = hashlib.sha256()
    for rel, kind, _ in _listing(folder):
        h.update(rel.encode() + b"\0")
        if kind == "link":
            h.update(b"link:" + os.readlink(folder / rel).encode())
        else:
            with open(folder / rel, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
        h.update(b"\0")
    return h.hexdigest()


def record(cfg, folder: Path) -> None:
    """At install: the tree's digest sealed with Aurora's key (a copy made without the key does not open)."""
    from . import sys_seal
    if (folder / DEPS).is_dir():
        sys_seal.write(cfg, folder / DEPS / TREE, tree_digest(folder).encode(), None, "plugins")
    _checked.pop(str(folder), None)


def verify(cfg, folder: Path, manifest: dict, log=None) -> None:
    """C579: before a plugin starts, what it fetched is what was fetched — the programs downloaded by address against
    the SHA-256 its signed manifest pins, the whole tree (libraries, packages unpacked) against the digest sealed at
    install. RuntimeError when something changed: the plugin is not run. A plugin installed before 12 Nov has no
    sealed digest: recorded now, once, and said. Hashed again only when a file's size or time changed."""
    n = needs(manifest)
    if not (n["python"] or n["programs"]) or not (folder / DEPS).is_dir():
        return
    seen = tuple(_listing(folder))
    if _checked.get(str(folder)) == seen:
        return
    for prog in n["programs"]:
        if prog.get("apt") or not prog.get("sha256"):
            continue
        f = folder / BIN / str(prog["name"])
        if not f.is_file() or f.is_symlink() or hashlib.sha256(f.read_bytes()).hexdigest() != str(prog["sha256"]).lower():
            raise RuntimeError(f"{folder.name}: {prog['name']} is not the program its manifest pins: not run (install it again)")
    from . import sys_seal
    sealed = folder / DEPS / TREE
    if not sealed.exists():
        record(cfg, folder)
        if log:
            log(f"plugin {folder.name}: its fetched files had no sealed digest (installed before C579): recorded now")
    else:
        try:
            want = sys_seal.read(cfg, sealed, None, "plugins").decode()
        except ValueError:
            raise RuntimeError(f"{folder.name}: the digest of its fetched files does not open: not run (install it again)") from None
        if tree_digest(folder) != want:
            raise RuntimeError(f"{folder.name}: its fetched libraries or programs changed since they were installed: "
                               "not run (install it again)")
    _checked[str(folder)] = seen


def uninstall(folder: Path) -> int:
    """The plugin's own libraries and programs removed; returns the bytes freed."""
    freed = _size(folder / DEPS) + _size(folder / BIN)
    for name in (DEPS, BIN):
        shutil.rmtree(folder / name, ignore_errors=True)
    return freed

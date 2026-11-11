# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Apply an approved code change from a sandbox to the live installation, safely.

 1. the sandbox tests must pass (again, now);
 2. the live files that change are copied into <sandbox>/.backup/ (new files are noted);
 3. the sandbox files are copied over the live ones;
 4. the live tests must pass (in the cage, the code read only: C562), otherwise everything is put back (rollback);
 5. the services that use the changed files are restarted (systemctl, allowed by the polkit rule).
Only sys/core is ever changed. Every step is an event, a log line and a trace.
"""
from __future__ import annotations

import filecmp
import json
import shutil
import subprocess
import threading
import time
from pathlib import Path

from . import sys_config, sys_log, sys_tests


def fingerprint(box: Path, files: list[str]) -> dict[str, str]:
    """Each changed file's SHA-256 as proposed: the approval keeps it, apply() takes nothing else (C541, 9 Nov: the
    sandbox stayed writable after the proposal, and the owner approved one diff while another could be applied)."""
    import hashlib
    return {rel: hashlib.sha256((box / rel).read_bytes()).hexdigest() for rel in files}


def changed_files(box: Path, root: Path) -> list[str]:
    """The files the change touches: those that differ from the sandbox's own starting copy (.base, kept since
    2026-10-05) — not from the live code, which may have moved on since the sandbox was made (C145); an older sandbox
    without .base is compared with the live code as before."""
    out, base = [], box / ".base"
    for f in sorted((box / "sys" / "core").rglob("*")):
        if not f.is_file() or "__pycache__" in f.parts or f.suffix == ".pyc":
            continue
        rel = f.relative_to(box).as_posix()
        ref = base / rel if base.is_dir() else root / rel
        if not ref.exists() or not filecmp.cmp(f, ref, shallow=False):
            out.append(rel)
    return out


# files that steer a test run from outside the tests' own folder: pytest and Python load them by their name
STEERING = {"conftest.py", "pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml", "sitecustomize.py",
            "usercustomize.py"}


def strays(box: Path, root: Path) -> list[str]:
    """Files of the sandbox OUTSIDE sys/core that would steer its tests and are not the live code's own (C590, 12 Nov:
    only sys/core is in the diff and the fingerprint — a conftest.py at the sandbox's root was in neither, and pytest
    loaded it). A sandbox that has one is refused: its tests say nothing."""
    out = []
    for f in sorted(box.rglob("*")):
        rel = f.relative_to(box)
        if rel.parts[0] in (".base", ".backup") or rel.parts[:2] == ("sys", "core") or "__pycache__" in rel.parts:
            continue
        if (f.name in STEERING or f.suffix == ".pth") and (f.is_file() or f.is_symlink()):
            ref = root / rel
            if f.is_symlink() or not ref.is_file() or not filecmp.cmp(f, ref, shallow=False):
                out.append(rel.as_posix())
    return out


def conflicts(box: Path, root: Path, files: list[str]) -> list[str]:
    """Files the change touches that changed in the live code too since the sandbox was made: never overwritten."""
    base = box / ".base"
    if not base.is_dir():
        return []
    return [rel for rel in files if (base / rel).exists() != (root / rel).exists()
            or ((root / rel).exists() and not filecmp.cmp(base / rel, root / rel, shallow=False))]


def services_for(files: list[str]) -> list[str]:
    """Which services load these files."""
    svc = set()
    for rel in files:
        name = Path(rel).name
        if rel.startswith("sys/core/webui/") or rel.startswith("sys/core/tests/") or rel.startswith("sys/core/prompts/"):
            continue                                   # served from disk / not loaded / read at each use
        if rel.startswith("sys/core/script/"):
            svc |= {"svc_api.py": {"aurora-api"}, "svc_models.py": {"aurora-models"}, "svc_llm.py": {"aurora-llm"},
                    "svc_rem.py": {"aurora-rem"}, "svc_harvester.py": {"aurora-harvester"}}.get(name, set())
        elif name in ("mdl_embedder.py", "mdl_reranker.py"):
            svc |= {"aurora-models"}
        elif rel.startswith("sys/core/aurora/") or rel.startswith("sys/core/config/"):
            svc |= {"aurora-api", "aurora-rem", "aurora-harvester"}
    return sorted(svc)


def _put(src: Path, dst: Path, data: bytes | None = None) -> None:
    """The file's content in place, its mode where allowed: the live code belongs to the owner's account, not to the
    service, so copying the times (shutil.copy2) is refused with EPERM after the content is already written (C518).
    `data`: the bytes to write, already read and checked (C590) — src gives only the mode then."""
    if data is None:
        shutil.copyfile(src, dst)
    else:
        dst.write_bytes(data)
    try:
        shutil.copymode(src, dst)
    except PermissionError:
        pass


def apply(sandbox_id: str, emit, cfg: sys_config.Config | None = None, restart: bool = True,
          expect: dict | None = None) -> dict:
    cfg = cfg or sys_config.get()
    log = sys_log.get_logger("changes")
    root, box = cfg.root, cfg.path("AURORA_SANDBOX_DIR") / sandbox_id
    if not box.is_dir():
        raise ValueError(f"no sandbox {sandbox_id}")
    files = changed_files(box, root)
    if not files:
        return {"applied": False, "reason": "no differences"}
    if expect is not None and fingerprint(box, files) != expect:   # C541: what the owner approved, byte for byte
        return {"applied": False, "reason": "the sandbox changed after the proposal: what the owner approved is not "
                                            "what is there now — propose it again"}
    from . import sys_ethics
    protected = [f for f in files if f in sys_ethics.PROTECTED or f == sys_ethics.MANIFEST]
    if protected:                                     # the rules change only with the owner's own signature
        return {"applied": False, "reason": f"protected by the ethics code, owner only: {', '.join(protected)}"}
    from . import sys_rootcmd
    owners = [f for f in files if sys_rootcmd.owner_only(f)]
    if owners:                                        # C556: what the owner runs (publish…) is never the services'
        return {"applied": False, "reason": f"the owner's own scripts, never changed by Aurora: {', '.join(owners)}"}
    clash = conflicts(box, root, files)
    if clash:                                         # the live code moved on under these files: redo the change on it
        return {"applied": False, "reason": f"changed in the live code since the sandbox was made: {', '.join(clash)}"}
    stray = strays(box, root)
    if stray:                                         # C590: outside the diff, yet loaded by the tests
        return {"applied": False, "reason": "files outside sys/core that steer the tests and are not the live "
                                            f"code's: {', '.join(stray[:10])} — make a new sandbox"}
    emit("change.check", {"files": files})
    before = fingerprint(box, files)
    t = sys_tests.run_suite(box, caged=True)           # the sandbox's code: in the cage (C420)
    emit("change.tests.sandbox", {"ok": t["ok"], "summary": t["summary"]})
    if not t["ok"]:
        return {"applied": False, "reason": "sandbox tests fail", "tests": t["summary"]}
    # C590: the test run is code too. What is copied is read ONCE, here, after it, and must be the approved bytes —
    # the same files, the same content; the copy below writes these bytes, never the sandbox's files read again
    import hashlib
    data = {rel: (box / rel).read_bytes() for rel in files} if changed_files(box, root) == files else {}
    if {rel: hashlib.sha256(b).hexdigest() for rel, b in data.items()} != (expect if expect is not None else before):
        return {"applied": False, "reason": "the sandbox changed while its tests ran: what the owner approved is not "
                                            "what is there now — propose it again"}
    backup, new = box / ".backup", []
    for rel in files:
        live = root / rel
        if live.exists():
            (backup / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(live, backup / rel)
        else:
            new.append(rel)
    (backup / "NEW_FILES.json").parent.mkdir(parents=True, exist_ok=True)
    (backup / "NEW_FILES.json").write_text(json.dumps(new))
    try:
        for rel in files:
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            _put(box / rel, root / rel, data[rel])
    except OSError as e:                              # C518: never a change left half in, untested and unsaid
        rollback(sandbox_id, cfg)
        emit("change.rollback", {"reason": repr(e)})
        return {"applied": False, "reason": f"could not write the change: {e!r}: rolled back"}
    log.info("audit: change %s applied: %s", sandbox_id, ", ".join(files))
    emit("change.applied", {"files": files})
    live_t = sys_tests.run_suite(root, caged=True, live=True)   # C562: caged too — the code read only, nothing else
    emit("change.tests.live", {"ok": live_t["ok"], "summary": live_t["summary"]})
    if not live_t["ok"]:
        rollback(sandbox_id, cfg)
        emit("change.rollback", {"reason": live_t["summary"]})
        return {"applied": False, "reason": "live tests fail: rolled back", "tests": live_t["summary"],
                "output": live_t["output"][-2000:]}
    services = services_for(files)
    if services and restart:
        # after this run has reported: restarting aurora-api ends the process that is running this code
        threading.Timer(3, lambda: subprocess.run(["systemctl", "restart", "--no-block", *services],
                                                  capture_output=True, timeout=30)).start()
        emit("change.restart", {"services": services})
    sys_log.trace("changes", "change.applied", {"sandbox": sandbox_id, "files": files, "services": services})
    return {"applied": True, "files": files, "tests": live_t["summary"], "restart": services}


def rollback(sandbox_id: str, cfg: sys_config.Config | None = None) -> list[str]:
    """Put back the live files saved before a change; remove the files it added."""
    cfg = cfg or sys_config.get()
    root, backup = cfg.root, cfg.path("AURORA_SANDBOX_DIR") / sandbox_id / ".backup"
    restored = []
    for f in sorted(p for p in backup.rglob("*") if p.is_file() and p.name != "NEW_FILES.json"):
        rel = f.relative_to(backup).as_posix()
        _put(f, root / rel)
        restored.append(rel)
    for rel in json.loads((backup / "NEW_FILES.json").read_text()) if (backup / "NEW_FILES.json").exists() else []:
        (root / rel).unlink(missing_ok=True)
        restored.append(f"-{rel}")
    sys_log.get_logger("changes").warning("rollback of %s: %s", sandbox_id, ", ".join(restored))
    sys_log.trace("changes", "change.rollback", {"sandbox": sandbox_id, "files": restored})
    return restored

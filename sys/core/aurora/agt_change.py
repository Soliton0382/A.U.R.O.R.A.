# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Apply an approved code change from a sandbox to the live installation, safely.

 1. the sandbox tests must pass (again, now);
 2. the live files that change are copied into <sandbox>/.backup/ (new files are noted);
 3. the sandbox files are copied over the live ones;
 4. the live tests must pass, otherwise everything is put back as it was (rollback);
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


def apply(sandbox_id: str, emit, cfg: sys_config.Config | None = None, restart: bool = True) -> dict:
    cfg = cfg or sys_config.get()
    log = sys_log.get_logger("changes")
    root, box = cfg.root, cfg.path("AURORA_SANDBOX_DIR") / sandbox_id
    if not box.is_dir():
        raise ValueError(f"no sandbox {sandbox_id}")
    files = changed_files(box, root)
    if not files:
        return {"applied": False, "reason": "no differences"}
    from . import sys_ethics
    protected = [f for f in files if f in sys_ethics.PROTECTED or f == sys_ethics.MANIFEST]
    if protected:                                     # the rules change only with the owner's own signature
        return {"applied": False, "reason": f"protected by the ethics code, owner only: {', '.join(protected)}"}
    clash = conflicts(box, root, files)
    if clash:                                         # the live code moved on under these files: redo the change on it
        return {"applied": False, "reason": f"changed in the live code since the sandbox was made: {', '.join(clash)}"}
    emit("change.check", {"files": files})
    t = sys_tests.run_suite(box)
    emit("change.tests.sandbox", {"ok": t["ok"], "summary": t["summary"]})
    if not t["ok"]:
        return {"applied": False, "reason": "sandbox tests fail", "tests": t["summary"]}
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
    for rel in files:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(box / rel, root / rel)
    log.info("audit: change %s applied: %s", sandbox_id, ", ".join(files))
    emit("change.applied", {"files": files})
    live_t = sys_tests.run_suite(root)
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
        shutil.copy2(f, root / rel)
        restored.append(rel)
    for rel in json.loads((backup / "NEW_FILES.json").read_text()) if (backup / "NEW_FILES.json").exists() else []:
        (root / rel).unlink(missing_ok=True)
        restored.append(f"-{rel}")
    sys_log.get_logger("changes").warning("rollback of %s: %s", sandbox_id, ", ".join(restored))
    sys_log.trace("changes", "change.rollback", {"sandbox": sandbox_id, "files": restored})
    return restored

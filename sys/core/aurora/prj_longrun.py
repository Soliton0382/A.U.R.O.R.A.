# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""⏳ Long experiments in the projects (ROADMAP N145; owner, 19 Nov: Aurora's projects need runs of hours — a
simulation, a scan, a fit — without a model call kept open).

start(cfg, project, command, limits, …) → a run id; the run goes on in the background, in prj_run's cage:
  1. the limits are declared FIRST and checked against the machine's ceilings: wall time (all attempts together), CPU
     seconds and memory of the WHOLE run (prj_longrun_meter, C654: a cgroup of its own when the unit delegates one,
     else the service's cgroup counter; the shell's ulimit stays a hard stop per process), TASKS_MAX processes, the cage's
     /tmp a tmpfs of the memory declared, the disk the project may grow by (every folder counted, every DISK_EVERY_S,
     and between those the filesystem's free space every 2 ms, measured exactly when it falls by more than what is
     left — C688; the machine's free space never under a floor; a single file never larger than it), the GPU (law 6, one job: refused when another GPU job holds the lock, the
     lock held for the whole run, the local reasoner moved off the GPU and back, the GPU's device files the only
     addition to the cage); at most AURORA_LONGRUN_MAX_ACTIVE runs of a user at once;
  2. with frozen predictions on (N142) the run is frozen as a prediction R1 «it ends by itself with exit 0 within its
     limits», with the code files it runs (required then) and the command hashed, before it starts; the entry's origin
     is «longrun»: Aurora closes it, never the agent (C630);
  3. its state and its log are Aurora's, in the user's state folder (the cage cannot reach them; the log copied from
     the run's output by Aurora, never more than LOG_MAX); the run may write its progress line to
     $LONGRUN_CHECKPOINT/PROGRESS and its checkpoints in that folder (checkpoints/<id>/, in the project), read by Aurora
     without following a link (C625);
  4. stop(): asked, the process group ended (TERM, then KILL); a run cut by an API restart or by the night (Aurora off,
     N139) is resumed by Aurora when she is back (watch(), sweep()) with the time it has left, at most MAX_ATTEMPTS
     attempts, LONGRUN_RESUMED=1 and LONGRUN_ATTEMPT telling it to continue from its checkpoints — only when its frozen
     code and its command are unchanged (C628); the morning restart waits while a run is alive (sys_fresh.why_not);
  5. when it ends, its outputs (the declared patterns, else the files it wrote) are hashed without following links: the
     list in longrun/<id>.MANIFEST.txt and in the report longrun/<id>.json (Aurora's, like prereg/), both created
     exclusively, and the frozen R1 is closed with the manifest's SHA-256 (the evidence: the manifest). The data tables
     among the outputs are kept in prj_provenance with the frozen entry and its integrity.
"""
from __future__ import annotations

import json
import logging
import signal
import subprocess
import threading
import time
from pathlib import Path

from . import prj_prereg, prj_run, prj_safeio, sys_config
from . import prj_longrun_cage as C
from . import prj_longrun_meter as M
from . import sys_users_layout as L
from .prj_longrun_cage import _patterns, limits, outputs  # noqa: F401  (re-exported: the tool, the tests)

NAME = "long_run"
DIR = "longrun"                  # the reports and manifests (written by Aurora only: prj_prereg.LOCKED)
WORK = "checkpoints"             # the run's own folder in the project (writable by it)
ORIGIN = "longrun"               # the frozen entries' origin: closed by this engine only (C630)
MAX_ATTEMPTS = 3
LOG_MAX = 5 * 1024 * 1024
TAIL = 4000
POLL_S = 1.0
DISK_EVERY_S = 15.0              # the project's size measured this often
SAVE_EVERY_S = 30.0              # the time used written this often (what a resume has left)
STARTING_S = 120.0               # a run «starting» this recently is its starter's, never a sweep's (C631)
GONE = ("ended", "failed", "stopped", "interrupted", "refused")
LOG = logging.getLogger("aurora.longrun")

TOOL = {"name": NAME, "description": "Long experiments in the project (hours): «start» a command in the cage in the "
        "background with its limits declared first (wall_s, mem_mb, disk_mb; cpu_s, gpu optional) and the code files "
        "it runs, «status» (its state, its progress line and the log's end, without waiting), «stop», «list». The run "
        "may write one progress line to $LONGRUN_CHECKPOINT/PROGRESS and its checkpoints there; after an interruption "
        "Aurora starts it again with LONGRUN_RESUMED=1, unless its code changed. Its outputs are hashed when it ends.",
        "inputSchema": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["start", "status", "stop", "list"]},
            "run": {"type": "string", "description": "the run's id (status, stop)"},
            "command": {"type": "string"}, "title": {"type": "string"},
            "wall_s": {"type": "integer", "description": "wall-clock seconds, all attempts together"},
            "cpu_s": {"type": "integer", "description": "CPU seconds of the whole run, every process it ever started "
                      "counted, even those the system reaps by itself (C654); each process is also stopped at it"},
            "mem_mb": {"type": "integer", "description": "memory of the run's processes (each one and their sum); "
                       "its /tmp, a RAM disk of the same size, is in it only when the run has a cgroup of its own"},
            "disk_mb": {"type": "integer", "description": "how much the project may grow"},
            "gpu": {"type": "boolean"},
            "outputs": {"type": "array", "items": {"type": "string"}, "description": "patterns of the files to hash"},
            "code_files": {"type": "array", "items": {"type": "string"}, "description": "the code the command runs, "
                           "frozen with it and hashed again before a resume (required with frozen predictions on; at most "
                           "64 files, 64 MB); a module it imports and you do not name is not checked"}},
            "required": ["action"]}}
RULE = ("Long runs (Aurora's rule): an experiment longer than a command's limit is started with long_run (limits "
        "declared first, its code files named) and followed with its status; never wait for it in a loop, and report "
        "its outcome only from long_run's status once it has ended.")

_live: dict[tuple, threading.Thread] = {}
_lock = threading.RLock()        # the state's writes, and start / sweep deciding together (C631)


def enabled(cfg: sys_config.Config) -> bool:
    return bool(cfg["AURORA_LONGRUN_ENABLED"])


def rule(cfg: sys_config.Config) -> str:
    return RULE if enabled(cfg) else ""


# ---- the state (the user's: outside the cage) --------------------------------------------------------------------
def _dir(cfg: sys_config.Config, project: str) -> Path:
    if not prj_run.NAME.fullmatch(project or ""):     # C629: «p/../q» stopped another project's (or user's) run
        raise ValueError("project names: lowercase letters, digits, . _ - (max 64)")
    return L.place(cfg, "state", cfg.user) / "projects" / project / "longrun"


def _state_file(cfg, project, rid) -> Path:
    if not rid or not str(rid).isdigit():
        raise ValueError("a run id (digits)")
    return _dir(cfg, project) / f"{rid}.json"


def load(cfg: sys_config.Config, project: str, rid: str) -> dict:
    f = _state_file(cfg, project, rid)
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValueError(f"no long run {rid} in {project}") from None


def _save(cfg, project, st: dict) -> None:
    f = _state_file(cfg, project, st["id"])
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(f)


def _update(cfg, project, rid, **kv) -> dict:
    with _lock:
        st = load(cfg, project, rid)
        st.update(kv)
        _save(cfg, project, st)
        return st


def runs(cfg: sys_config.Config, project: str) -> list[dict]:
    out = []
    for f in sorted(_dir(cfg, project).glob("*.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


def _key(cfg, project, rid) -> tuple:
    return (str(_dir(cfg, project)), str(rid))     # the state's own folder: a user, a project, one machine


def alive(cfg, project, rid) -> bool:
    t = _live.get(_key(cfg, project, rid))
    return bool(t and t.is_alive())


def busy(cfg: sys_config.Config, project: str) -> bool:
    """A run of this project is starting, going or not yet finished (C643: the project's file tools wait for it to
    end; O1 of C709: its finish() sets a .git aside after the status is already gone). C667: whether the engine is on
    or not — switching it off left its runs going and the tools no longer waited."""
    try:
        return any(r.get("status") not in GONE or not r.get("finished") for r in runs(cfg, project))
    except ValueError:
        return False


def unfinished_since(cfg: sys_config.Config, project: str) -> float | None:
    """The start of the earliest run of this project not finished yet (its outputs not hashed and registered): a table
    changed since then may be its work (C660). None: none."""
    try:
        ts = [float(r.get("t") or 0) for r in runs(cfg, project) if not r.get("finished")]
    except ValueError:
        return None
    return min(ts) if ts else None


def any_alive() -> int:
    """How many runs this process is supervising now (sys_fresh: the morning restart waits for them, C631)."""
    return sum(1 for t in list(_live.values()) if t.is_alive())


def gpu_holder(cfg: sys_config.Config) -> str:
    """Who holds the GPU now ("" for nobody): the lock of mdl_image.gpu_lock (law 6, one GPU job)."""
    from . import sys_health
    return sys_health.gpu_job(cfg)


# ---- start / stop / status ---------------------------------------------------------------------------------------
def start(cfg: sys_config.Config, project: str, command: str, lim: dict, title: str = "", outputs=None,
          code_files=None) -> dict:
    """The run's state once launched; ValueError for a bad request, RuntimeError when it cannot start now."""
    if not enabled(cfg):
        raise RuntimeError("long runs are off (AURORA_LONGRUN_ENABLED)")
    command = str(command or "").strip()
    if not command or len(command) > 2000:
        raise ValueError("a command of 1 to 2000 characters")
    root = prj_run.project_dir(cfg, project).resolve()
    _dir(cfg, project)
    pats = _patterns(outputs)
    freeze = prj_prereg.mode(cfg) != "off"
    if freeze and not code_files:
        raise ValueError("name the code files the command runs (code_files): they are frozen with it and checked "
                         "again before any resume")
    code = C.code_state(root, code_files or [], command)
    if not shutil_which("bwrap"):
        raise RuntimeError("bubblewrap (bwrap) is not installed: no cage, nothing is run")
    prj_run.guard_dirs(root)
    with _lock:                                       # C631: the count, the id and the launch together
        mine = sum(1 for p in _dir(cfg, project).parent.parent.glob("*/longrun")
                   for r in runs(cfg, p.parent.name) if r.get("status") not in GONE)
        from . import prj_term                        # C701: never while the user's terminal is open on it
        if (n_term := prj_term.open_on(root)):
            raise RuntimeError(f"the owner has {n_term} terminal(s) open on this project: a long run starts once "
                               "they are closed (its end sets aside a .git it did not find, C701)")
        from . import prj_package                     # C713: nor while the owner's «Salva» or package is being made
        if prj_package.making(root):
            raise RuntimeError("the owner is saving this project (its package, a commit): start the long run again "
                               "in a moment (its end would set the new .git aside, C713)")
        if mine >= int(cfg["AURORA_LONGRUN_MAX_ACTIVE"]):
            raise RuntimeError(f"{mine} long run(s) going already (AURORA_LONGRUN_MAX_ACTIVE): stop one or wait")
        if lim["gpu"] and (who := gpu_holder(cfg)):
            raise RuntimeError(f"the GPU is busy ({who}): one GPU job at a time (law 6)")
        if lim["gpu"] and any(r.get("limits", {}).get("gpu") and r.get("status") not in GONE
                              for p in _dir(cfg, project).parent.parent.glob("*/longrun")
                              for r in runs(cfg, p.parent.name)):
            raise RuntimeError("a GPU long run is starting or going already: one GPU job at a time (law 6, C648)")
        n = len(runs(cfg, project)) + 1
        while _state_file(cfg, project, f"{n:03d}").exists():
            n += 1
        rid = f"{n:03d}"
        title = " ".join(str(title or command).split())[:120]
        st = {"id": rid, "project": project, "title": title, "command": command, "limits": lim, "outputs": pats,
              "status": "starting", "attempts": 0, "used_s": 0.0, "cpu_used_s": 0.0, "created": _now(),
              "t": time.time(), "frozen": "", "exit": None, "why": "", **code,
              "git_mark": list(prj_run.git_mark(root) or []),       # C658: a .git it makes is set aside at the end
              "log": str(_dir(cfg, project) / f"{rid}.log")}
        if freeze:
            e = prj_prereg.freeze(cfg, project, f"Long run {rid}: {title}", [
                {"id": "R1", "text": f"The run «{title}» ends by itself with exit 0 within its declared limits (wall "
                                     f"{lim['wall_s']} s, CPU {lim['cpu_s']} s and memory {lim['mem_mb']} MB as Aurora sums "
                                     f"them over its processes, disk {lim['disk_mb']} MB{', the GPU' if lim['gpu'] else ''}); its "
                                     f"command SHA-256 {code['command_sha256']}; its outputs are hashed when it ends."}],
                list(code["code"]), origin=ORIGIN)
            st["frozen"] = e["id"]
        try:                                          # C644: exclusive, non-blocking, a regular file (a FIFO hung)
            prj_safeio.create_exclusive(root, f"{WORK}/{rid}/.keep")
        except FileExistsError:
            pass
        except (OSError, ValueError) as e:
            raise RuntimeError(f"the run's checkpoint folder is not usable ({e})") from None
        _save(cfg, project, st)
        launch(cfg, project, rid)
    LOG.info("audit: long run %s started in %s (%s)", rid, project, title[:80])
    return st


def shutil_which(x: str):
    import shutil
    return shutil.which(x)


def launch(cfg, project, rid, target=None) -> threading.Thread:
    """The run's supervisor in a thread of this process (`target`: the tests' own), registered before it starts."""
    t = threading.Thread(target=target or supervise, args=(cfg, project, rid), name=f"longrun-{project}-{rid}",
                         daemon=True)
    with _lock:
        _live[_key(cfg, project, rid)] = t
    t.start()
    return t


def stop(cfg: sys_config.Config, project: str, rid: str) -> dict:
    st = load(cfg, project, rid)
    if st.get("status") in GONE:
        return st
    st = _update(cfg, project, rid, stop=True)
    if not alive(cfg, project, rid):                  # nobody to stop it: said stopped at once
        st = _update(cfg, project, rid, status="stopped", why="stopped by request")
        finish(cfg, project, rid)
        st = load(cfg, project, rid)
    return st


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def status(cfg: sys_config.Config, project: str, rid: str) -> dict:
    """The state, the run's own progress line (never through a link, C625) and the log's end (read here: no model
    call kept open)."""
    st = load(cfg, project, rid)
    root = prj_run.project_dir(cfg, project).resolve()
    st["progress"] = C.read_small(root, f"{WORK}/{rid}/PROGRESS", 500).strip()
    try:
        with open(st["log"], "rb") as fh:
            fh.seek(0, 2)
            n = fh.tell()
            fh.seek(max(0, n - TAIL))
            st["log_tail"] = fh.read().decode(errors="replace")
    except OSError:
        st["log_tail"] = ""
    st["alive"] = alive(cfg, project, rid)
    return st


# ---- the supervisor ------------------------------------------------------------------------------------------------
def supervise(cfg: sys_config.Config, project: str, rid: str) -> None:
    """One attempt: the cage started, watched (stop asked, wall time, CPU, memory, processes, disk, log), then
    finish(). With the GPU: the lock, and the local reasoner off the GPU for the run (law 6)."""
    try:
        if load(cfg, project, rid).get("limits", {}).get("gpu"):
            from . import mdl_image
            with mdl_image.gpu_lock(cfg, 0, f"long run {project}/{rid}"):
                mdl_image.reasoner_out(cfg)
                try:
                    _attempt(cfg, project, rid)
                finally:
                    mdl_image.reasoner_back(cfg, 300)
        else:
            _attempt(cfg, project, rid)
    except Exception as e:  # noqa: BLE001 — the run is said failed, never left «running»
        try:
            _update(cfg, project, rid, status="failed", why=f"{type(e).__name__}: {str(e)[:300]}")
        except (OSError, ValueError):
            pass
    try:
        finish(cfg, project, rid)
    except Exception as e:  # noqa: BLE001
        LOG.warning("long run %s/%s not finished: %s", project, rid, e)


def _attempt(cfg, project, rid) -> None:
    root = prj_run.project_dir(cfg, project).resolve()
    st = load(cfg, project, rid)
    st = _update(cfg, project, rid, attempts=st["attempts"] + 1, status="running", why="")
    lim, used0, cpu0 = st["limits"], float(st["used_s"]), float(st.get("cpu_used_s") or 0)
    base = C.disk_bytes(root) if st["attempts"] == 1 else int(st.get("base_bytes") or C.disk_bytes(root))
    if st["attempts"] == 1:
        _update(cfg, project, rid, base_bytes=base)
    log = Path(st["log"])
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "ab") as fh:
        fh.write(f"\n== attempt {st['attempts']} ({_now()})\n".encode())
    meter = M.Meter(lim, f"{project}.{rid}.{st['attempts']}", C.TASKS_MAX)   # C654: from before it starts
    try:
        disk = C.DiskWatch(root, int(lim["disk_mb"]), base)                    # C688: between the looks too
        proc = subprocess.Popen(meter.argv(C.argv(cfg, root, st, WORK)), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    except BaseException:
        meter.close()
        raise
    disk.proc, disk.meter = proc, meter
    disk.start()
    over = threading.Event()
    pump = threading.Thread(target=C.pump, args=(proc.stdout, log, over, LOG_MAX), daemon=True)
    pump.start()
    _update(cfg, project, rid, pid=proc.pid, meter=meter.mode)
    t0 = last_disk = last_save = time.time()
    why, cpu = "", cpu0
    while proc.poll() is None:
        time.sleep(M.pause(POLL_S, lim["cpu_s"] - cpu))
        now = time.time()
        used = used0 + (now - t0)
        try:
            u = meter.read(proc.pid)
        except Exception:                            # noqa: BLE001 — a run never left going unmeasured
            disk.done.set()
            meter.kill(proc)
            meter.close()
            raise
        cpu = max(cpu, cpu0 + u["cpu_s"])
        disk.pids = u.get("pids", [])
        cur = load(cfg, project, rid)
        if disk.why:
            why = disk.why
        elif cur.get("stop"):
            why = "stopped by request"
        elif used > lim["wall_s"]:
            why = f"stopped: wall time {lim['wall_s']} s used"
        elif cpu > lim["cpu_s"]:
            why = f"stopped: CPU time {lim['cpu_s']} s of the whole run used ({cpu:.1f} s)"
        elif u["rss_mb"] > lim["mem_mb"]:
            why = f"stopped: the run's memory {u['rss_mb']:.0f} MB > {lim['mem_mb']} MB"
        elif u["tasks"] > C.TASKS_MAX:
            why = f"stopped: {u['tasks']} processes > {C.TASKS_MAX}"
        elif over.is_set():
            why = f"stopped: its log passed {LOG_MAX // (1024 * 1024)} MB"
        elif now - last_disk >= DISK_EVERY_S:
            last_disk = now
            try:
                grown = (C.disk_bytes(root) + C.deleted_open_bytes(u.get("pids", []), root) - base) / (1024 * 1024)
            except C.Unmeasurable as e:               # C645: a folder hidden by chmod 000 is no way around the limit
                grown, why = 0.0, f"stopped: the project's size cannot be measured ({e})"
            if grown > lim["disk_mb"]:
                why = f"stopped: the project grew by {grown:.1f} MB > {lim['disk_mb']} MB"
        if why:
            meter.kill(proc)
            break
        if now - last_save >= SAVE_EVERY_S:
            last_save = now
            _update(cfg, project, rid, used_s=round(used, 1), cpu_used_s=round(cpu, 1))
    code = proc.wait()
    disk.done.set()
    why = why or disk.why
    pump.join(timeout=10)
    end = meter.close()                              # with a cgroup: the exact CPU of all it ran, the kernel's OOM
    cpu = max(cpu, cpu0 + end["cpu_s"])
    used = round(used0 + (time.time() - t0), 1)
    if not why and end.get("oom"):
        why = f"stopped: the run's memory passed {lim['mem_mb']} MB (the kernel's limit, its cgroup)"
    if not why and code == M.JOIN_FAILED and meter.mode == "cgroup":
        why = "the run's cgroup could not be joined"
    if not why and code in (-signal.SIGXCPU, 128 + signal.SIGXCPU):
        why = f"stopped: CPU time {lim['cpu_s']} s used by one process"
    if not why and code in (-signal.SIGXFSZ, 128 + signal.SIGXFSZ):
        why = f"stopped: a file passed the disk declared ({lim['disk_mb']} MB)"
    if not why and code in (-signal.SIGKILL, 128 + signal.SIGKILL):
        why = f"stopped: killed by the system (CPU {lim['cpu_s']} s or memory {lim['mem_mb']} MB passed)"
    if not why and code == 97:
        why = "the limits could not be set (ulimit)"
    status_ = "stopped" if why.startswith("stopped") else "ended" if code == 0 else "failed"
    _update(cfg, project, rid, status=status_, exit=code, used_s=used, cpu_used_s=round(cpu, 1), why=why, pid=None,
            ended=_now())


# ---- the end: outputs hashed, the frozen prediction closed -------------------------------------------------------
def finish(cfg: sys_config.Config, project: str, rid: str) -> dict:
    """Once, after the run ended (or was stopped, or could not be resumed): the manifest, the report, the close."""
    with _lock:                                       # C648: once, even when sweep and the supervisor race
        st = load(cfg, project, rid)
        if st.get("finished") or st.get("finishing") or st.get("status") not in GONE:
            return st
        st = _update(cfg, project, rid, finishing=_now())
    try:
        return _close(cfg, project, rid, st)
    except Exception:
        _update(cfg, project, rid, finishing=None)    # C689: never left «finishing»; the next sweep tries again
        raise


def _close(cfg, project, rid, st: dict) -> dict:
    import hashlib
    root = prj_run.project_dir(cfg, project).resolve()
    gnote = prj_run.set_aside_git(root, tuple(st["git_mark"]) if st.get("git_mark") else None)
    if gnote:
        LOG.warning("long run %s in %s: %s", rid, project, gnote)
    hashed, skipped = outputs(root, st)
    lines = [f"{h}  {f}" for f, h in hashed.items()] + ([f"# {skipped} names skipped (a link, or a line break in the "
                                                         "name)"] if skipped else [])
    lines += [f"# pattern refused (a link or a file on its fixed folders): {x}" for x in st.get("outputs_refused") or []]
    lines += [f"# more than {C.MAX_VISIT} entries in the project: the patterns matched within those only"] \
        if st.get("outputs_capped") else []
    blob = ("\n".join(lines) + ("\n" if lines else "")).encode()
    man = C.write_new(root, f"{DIR}/{rid}.MANIFEST.txt", blob)   # in the locked folder, created exclusively (C625)
    msha = hashlib.sha256(blob).hexdigest()
    report = f"{DIR}/{rid}.json"
    closed = {}
    if st.get("frozen"):
        ok = st["status"] == "ended" and st.get("exit") == 0
        why = st.get("why") or f"exit {st.get('exit')}"
        try:
            closed = prj_prereg.close(cfg, project, st["frozen"], [{
                "id": "R1", "outcome": "passed" if ok else "failed" if st["status"] != "interrupted" else "void",
                "value": f"{st['status']}, exit {st.get('exit')}, {st.get('used_s')} s, CPU {st.get('cpu_used_s')} s, "
                         f"{st.get('attempts')} attempt(s); outputs manifest SHA-256 {msha} ({len(hashed)} files)",
                "note": (f"{why}; report {report}" if not ok else f"report {report}")}], man)
        except ValueError as e:
            closed = {"error": str(e)}
    body = {**{k: v for k, v in st.items() if k not in ("pid",)}, "outputs_sha256": hashed, "manifest": man,
            "manifest_sha256": msha, "names_skipped": skipped, "integrity": closed.get("integrity", ""),
            "finished": _now()}
    report = C.write_new(root, report, json.dumps(body, ensure_ascii=False, indent=1).encode())
    from . import prj_provenance                      # C632: the data tables it made, with its frozen entry
    prj_provenance.record(cfg, project, root, list(hashed), "longrun", run=rid, frozen=st.get("frozen") or "",
                          intact=closed.get("integrity") == "intact")
    t0 = float(st.get("t") or 0)                      # C649: every other table it made (not declared, or its mtime
    others = [rel for rel, v in prj_run.snapshot(root).items()   # set back) is the agent's, never evidence
              if rel.lower().endswith(prj_run.TABLES) and rel not in hashed and v[2] / 1e9 >= t0]
    prj_provenance.record(cfg, project, root, others, "run", run=rid)
    return _update(cfg, project, rid, finished=body["finished"], manifest=man, manifest_sha256=msha,
                   outputs_count=len(hashed), report=report, integrity=closed.get("integrity", ""))


# ---- after a restart, after the night ----------------------------------------------------------------------------
def sweep(cfg: sys_config.Config, project: str | None = None) -> list[str]:
    """Runs left «running» with nobody watching them (the API restarted, Aurora switched off at night): resumed with
    the time they have left when AURORA_LONGRUN_RESUME is on (at most MAX_ATTEMPTS) and their frozen code and command
    are unchanged (C628), else said interrupted; a run that ended without its finish, finished. The ids touched."""
    names = [project] if project else [p.parent.name for p in _dir(cfg, "x").parent.parent.glob("*/longrun")]
    done = []
    for name in names:
        try:
            root = prj_run.project_dir(cfg, name).resolve()
        except ValueError:
            continue
        for st in runs(cfg, name):
            rid = st["id"]
            with _lock:                               # C631: never decided while start() is launching it
                st = load(cfg, name, rid)
                if not enabled(cfg) and st.get("status") not in GONE:     # C667: switched off, its runs stop
                    if alive(cfg, name, rid):
                        _update(cfg, name, rid, stop=True)                # its supervisor kills it and finishes
                        continue
                    _update(cfg, name, rid, status="stopped", why="stopped: long runs were switched off")
                elif st.get("status") in GONE:
                    if st.get("finished") or st.get("finishing") or alive(cfg, name, rid):
                        continue
                elif alive(cfg, name, rid) or (st.get("status") == "starting"
                                               and time.time() - float(st.get("t") or 0) < STARTING_S):
                    continue
                else:
                    left = st["limits"]["wall_s"] - float(st.get("used_s") or 0)
                    changed = C.code_changed(root, st)
                    if st.get("stop"):
                        _update(cfg, name, rid, status="stopped", why="stopped by request")
                    elif changed:
                        _update(cfg, name, rid, status="interrupted",
                                why=f"interrupted; not resumed: its frozen code changed ({', '.join(changed)[:200]})")
                    elif bool(cfg["AURORA_LONGRUN_RESUME"]) and st["attempts"] < MAX_ATTEMPTS and left > 0:
                        if st["limits"].get("gpu") and gpu_holder(cfg):
                            continue                 # the GPU is someone else's now: tried again at the next sweep
                        _update(cfg, name, rid, status="resuming", why="interrupted; resumed by Aurora", finished=None)
                        launch(cfg, name, rid)
                        LOG.info("audit: long run %s resumed in %s (attempt %s)", rid, name, st["attempts"] + 1)
                        done.append(rid)
                        continue
                    else:
                        _update(cfg, name, rid, status="interrupted",
                                why="interrupted and not resumed" + ("" if left > 0 else ": no time left"))
            finish(cfg, name, rid)                    # C689: outside the lock (finish claims the run under it itself)
            done.append(rid)
    return done


def watch(every_s: int = 60) -> None:
    """At start and then each minute, for each user: sweep() (svc_api starts it)."""
    from . import sys_context
    from .api.core import _admin
    from .api.users import _users
    first = True
    while True:
        if not first:
            time.sleep(every_s)
        first = False
        try:
            names = [u["name"] for u in _users().list()] if _admin() else [None]
        except Exception:  # noqa: BLE001 — the watcher never dies
            continue
        for name in names:
            try:
                with sys_context.acting_as(name):
                    c = sys_config.get()
                    if enabled(c):
                        sweep(c)
            except Exception as e:  # noqa: BLE001 — one user's problem never stops the others'
                LOG.warning("long runs: %s", type(e).__name__)


# ---- the tool: prj_longrun_tool (text, act, offered, agent_call), here under the same names -------------------------
from .prj_longrun_tool import act, agent_call, offered, text  # noqa: E402,F401  (its own import of this module is done)

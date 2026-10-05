# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Updates from the project's git repository (GitHub): check, show what changes, apply with a way back.

check()  fetches AURORA_UPDATE_REMOTE/AURORA_UPDATE_BRANCH and lists the commits not yet here, with
         their messages (the changelog the owner reads) and what they touch: requirements, settings
         schema, protected files of the code of conduct.
apply()  only on a clean working tree; fast-forward only (never a merge that rewrites local work);
         pip when requirements.txt changed; the test suite; if anything fails, back to the previous
         commit (and its requirements). An update that changes protected files is never applied here:
         those files need the owner's signature (sys_ethics_sign.py), so the owner applies it by hand.

AURORA_UPDATE_MODE: off | notify (the owner approves from the Repairs page) | auto (applied when safe:
no protected file touched, tests green; otherwise it falls back to asking).
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from . import sys_config, sys_ethics, sys_log, sys_tests


def _git(root: Path, *args: str, timeout: int = 120) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:2])}: {(r.stderr or r.stdout).strip()[:300]}")
    return r.stdout


def _state_file(cfg: sys_config.Config) -> Path:
    d = cfg.path("AURORA_STATUS_DIR") / "update"
    d.mkdir(parents=True, exist_ok=True)
    return d / "last_check.json"


def _signed(root: Path, commit: str) -> bool:
    """A commit signed (SSH) by a key of the LOCAL allowed_signers: an update cannot bring its own signer."""
    signers = root / "sys" / "core" / "config" / "allowed_signers"
    if not signers.exists():
        return False
    r = subprocess.run(["git", "-C", str(root), "-c", f"gpg.ssh.allowedSignersFile={signers}", "verify-commit", commit],
                       capture_output=True, text=True, timeout=60)
    return r.returncode == 0


def last(cfg: sys_config.Config) -> dict:
    try:
        return json.loads(_state_file(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def dirty(root: Path) -> list[str]:
    """Tracked files changed or untracked files not ignored: an update must not mix with local work."""
    return [l[3:] for l in _git(root, "status", "--porcelain").splitlines() if l.strip()]


def check(cfg: sys_config.Config, root: Path | None = None, fetch: bool = True) -> dict:
    root = root or cfg.root
    remote, branch = cfg["AURORA_UPDATE_REMOTE"], cfg["AURORA_UPDATE_BRANCH"]
    out = {"checked": time.time(), "remote": remote, "branch": branch}
    try:
        if not _git(root, "remote").split():
            return {**out, "error": "no remote configured (the repository is not connected to GitHub yet)"}
        if fetch:
            _git(root, "fetch", "--quiet", remote, branch, timeout=300)
        here = _git(root, "rev-parse", "HEAD").strip()
        there = _git(root, "rev-parse", f"{remote}/{branch}").strip()
        log = _git(root, "log", "--reverse", "--format=%H%x1f%cI%x1f%s%x1f%b%x1e", f"HEAD..{remote}/{branch}")
        commits = []
        for rec in filter(str.strip, log.split("\x1e")):
            h, date, subject, body = (rec.strip("\n").split("\x1f") + ["", "", "", ""])[:4]
            commits.append({"hash": h[:10], "date": date, "subject": subject, "body": body.strip()[:2000]})
        files = _git(root, "diff", "--name-only", f"HEAD...{remote}/{branch}").split() if commits else []
        behind_ahead = _git(root, "rev-list", "--left-right", "--count", f"HEAD...{remote}/{branch}").split()
        out.update(here=here[:10], there=there[:10], behind=len(commits), ahead=int(behind_ahead[0]),
                   commits=commits, files=files,
                   requirements="requirements.txt" in files,
                   schema="sys/core/config/settings_schema.json" in files,
                   protected=sorted(set(files) & set(sys_ethics.PROTECTED)))
        out["unsigned"] = [c["hash"] for c in commits if not _signed(root, c["hash"])]
        out["safe"] = bool(commits) and not out["protected"] and out["ahead"] == 0 and not out["unsigned"]
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        out["error"] = str(e)
    _state_file(cfg).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def changelog(info: dict, lang: str = "it") -> str:
    """The list the owner reads before deciding: one line per commit, then what the update touches."""
    if not info.get("commits"):
        return "Nessun aggiornamento." if lang == "it" else "No update."
    lines = [f"- {c['date'][:10]} {c['subject']}" + (f"\n  {c['body'][:400]}" if c["body"] else "") for c in info["commits"]]
    notes = []
    if info.get("requirements"):
        notes.append("installa nuove dipendenze Python" if lang == "it" else "installs new Python dependencies")
    if info.get("schema"):
        notes.append("nuove impostazioni nel .env" if lang == "it" else "new settings in .env")
    if info.get("unsigned"):
        notes.append(("commit NON firmati da una chiave autorizzata: " if lang == "it" else "commits NOT signed by an allowed key: ")
                     + ", ".join(info["unsigned"]))
    if info.get("protected"):
        notes.append(("tocca file protetti del codice etico: va applicato a mano e firmato" if lang == "it"
                      else "touches protected files of the code of conduct: apply by hand and sign")
                     + f" ({', '.join(info['protected'])})")
    return "\n".join(lines) + ("\n\n" + "; ".join(notes) if notes else "")


def apply(cfg: sys_config.Config, emit=None, root: Path | None = None, run_tests=None) -> dict:
    """Fast-forward to the remote, install, test; back to the previous commit on any failure."""
    root = root or cfg.root
    ev = emit or (lambda e, d: None)
    log = sys_log.get_logger("update")
    info = check(cfg, root)
    if info.get("error"):
        return {"applied": False, "reason": info["error"]}
    if not info.get("commits"):
        return {"applied": False, "reason": "already up to date"}
    if info["protected"]:
        return {"applied": False, "reason": f"protected files change: {', '.join(info['protected'])} (apply by hand, then sign)"}
    if info["ahead"]:
        return {"applied": False, "reason": f"{info['ahead']} local commits not on the remote: merge by hand"}
    if info["unsigned"] and cfg["AURORA_UPDATE_REQUIRE_SIGNED"]:
        return {"applied": False, "reason": f"commits not signed by an allowed key: {', '.join(info['unsigned'])}"}
    local = dirty(root)
    if local:
        return {"applied": False, "reason": f"local changes not committed: {', '.join(local[:8])}"}
    before = _git(root, "rev-parse", "HEAD").strip()
    ev("update.start", {"from": before[:10], "to": info["there"], "commits": info["behind"]})
    log.info("audit: update %s -> %s (%d commits)", before[:10], info["there"], info["behind"])

    added: list[str] = []

    def back(reason: str) -> dict:
        _git(root, "reset", "--hard", before)
        if added:                                    # the settings the update brought go with it
            sys_config.write_env(env, {}, drop=set(added))
        if info["requirements"]:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(root / "requirements.txt")],
                           capture_output=True, text=True, timeout=3600)
        log.warning("update rolled back to %s: %s", before[:10], reason)
        ev("update.rollback", {"to": before[:10], "reason": reason})
        return {"applied": False, "rolled_back": True, "reason": reason}

    try:
        _git(root, "merge", "--ff-only", f"{info['remote']}/{info['branch']}")
    except RuntimeError as e:
        return {"applied": False, "reason": str(e)}
    if info["requirements"]:
        r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(root / "requirements.txt")],
                           capture_output=True, text=True, timeout=3600)
        if r.returncode != 0:
            return back(f"pip failed: {r.stderr.strip()[-300:]}")
    # the new schema's settings before the tests: the suite loads the real .env (C139)
    env = sys_config.env_file_path() if root == cfg.root else root / ".env"
    if env.exists():
        schema = root / "sys" / "core" / "config" / "settings_schema.json"
        added += sys_config.add_missing(env, schema if schema.exists() else sys_config.SCHEMA_FILE)
        if added:
            log.info("audit: update added settings with their recommended value: %s", ", ".join(added))
    tests = (run_tests or (lambda: sys_tests.run_suite(root)))()
    ev("update.tests", {"ok": tests["ok"], "passed": tests.get("passed"), "failed": tests.get("failed")})
    if not tests["ok"]:
        return back(f"tests failed: {tests.get('summary', '')[:300]}")
    log.info("update applied: %s, tests %s passed", info["there"], tests.get("passed"))
    ev("update.applied", {"to": info["there"], "passed": tests.get("passed")})
    return {"applied": True, "from": before[:10], "to": info["there"], "commits": info["behind"],
            "tests_passed": tests.get("passed"), "schema_changed": info["schema"]}

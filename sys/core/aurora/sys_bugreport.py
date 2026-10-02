# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A bug report the owner can send: his description and what is needed to find the cause, with nothing private.

    <AURORA_BUGREPORT_DIR>/aurora-bug-<time>.zip   (0600)
      report.md          the description, the steps, what was expected, environment, health, features
      environment.json   system, GPUs and driver, Python and the main libraries, Aurora's version and commit
      health.json        every service, disk, GPUs, backup, features (what the Status page shows)
      settings.txt       every setting; secrets only as "(set)" / "(empty)"
      logs/<c>.log       each component's lines of the last N hours (at most 2 MB each)
      logs/problems.log  warnings and errors of the last 7 days, every component
      logs/plugins/*     the last 300 lines of each plugin's stderr
      runs/<id>.jsonl    every traced event of the runs the owner chose (what Aurora did, step by step)

Everything written goes through one Pseudonymizer (sec_mask: addresses, e-mails, phones, IBANs, cards, keys, the value
of every secret setting, the owner's name, domain, place and home folder, device serials...): the same value gets the
same placeholder in every file, so the report still reads coherently. The owner sees the list of files and what was
masked before sending; the GitHub issue link carries the description only, the zip is attached by hand.
"""
from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from . import sys_config, sys_logread
from .sec_mask import Pseudonymizer

MAX_LOG = 2 * 2**20
LIBS = ("torch", "transformers", "diffusers", "fastapi", "httpx", "numpy", "mcp", "cryptography")


def _environment(cfg: sys_config.Config) -> dict:
    env = {"python": platform.python_version(), "kernel": platform.release(), "machine": platform.machine()}
    try:
        env["os"] = next(l.split("=", 1)[1].strip().strip('"') for l in open("/etc/os-release")
                         if l.startswith("PRETTY_NAME="))
    except (OSError, StopIteration):
        env["os"] = "?"
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
        env["gpus"] = out.splitlines()
    except (OSError, subprocess.SubprocessError):
        env["gpus"] = "not measured"
    from importlib.metadata import PackageNotFoundError, version
    libs = {}
    for name in LIBS:
        try:
            libs[name] = version(name)
        except PackageNotFoundError:
            libs[name] = None
    env["libraries"] = libs
    try:
        import tomllib
        env["aurora"] = tomllib.loads((cfg.root / "pyproject.toml").read_text())["project"]["version"]
    except (OSError, KeyError, ValueError):
        env["aurora"] = "?"
    try:
        env["commit"] = subprocess.run(["git", "-C", str(cfg.root), "rev-parse", "--short", "HEAD"], capture_output=True,
                                       text=True, timeout=10).stdout.strip() or "no git (installed from a copy)"
    except (OSError, subprocess.SubprocessError):
        env["commit"] = "?"
    return env


def _settings(cfg: sys_config.Config) -> str:
    lines = []
    for s in sys_config.load_schema()["settings"]:
        v = cfg.values.get(s["key"], "")
        if s.get("secret"):
            v = "(set)" if str(v or "").strip() else "(empty)"
        lines.append(f"{s['key']}={v}")
    return "\n".join(lines) + "\n"


def _recent_lines(f: Path, since: datetime) -> str:
    """The lines of a log written after `since` (a line without a time belongs to the one before), at most MAX_LOG."""
    out, keep = [], False
    with open(f, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = sys_logread.LINE.match(line)
            if m:
                try:
                    keep = datetime.fromisoformat(m.group(1)) >= since
                except ValueError:
                    pass
            if keep:
                out.append(line)
    text = "".join(out)
    return text[-MAX_LOG:]


def _problems(cfg: sys_config.Config, days: int = 7) -> str:
    since = datetime.now().astimezone() - timedelta(days=days)
    rows = []
    for f in sorted(cfg.path("AURORA_LOG_DIR").glob("*/*.log")):
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = sys_logread.LINE.match(line)
                if m and m.group(2) in ("WARNING", "ERROR", "CRITICAL"):
                    try:
                        if datetime.fromisoformat(m.group(1)) >= since:
                            rows.append(line if line.endswith("\n") else line + "\n")
                    except ValueError:
                        continue
    rows.sort()
    return "".join(rows)[-MAX_LOG:]


def repository(cfg: sys_config.Config) -> str:
    """The project's repository: AURORA_UPDATE_REMOTE when it is an address, else the address of that git remote
    (an installation cloned from GitHub), else the one in pyproject.toml (an installation without git)."""
    remote = str(cfg["AURORA_UPDATE_REMOTE"] or "")
    if "/" in remote:
        return remote
    try:
        url = subprocess.run(["git", "-C", str(cfg.root), "remote", "get-url", remote or "origin"], capture_output=True,
                             text=True, timeout=10).stdout.strip()
        if url:
            return url
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        import tomllib
        return tomllib.loads((cfg.root / "pyproject.toml").read_text())["project"]["urls"]["Repository"]
    except (OSError, KeyError, ValueError):
        return ""


def issue_url(cfg: sys_config.Config, title: str, body: str) -> str:
    """A prefilled GitHub issue on the project's repository, or "" if it is not on GitHub."""
    m = re.search(r"github\.com[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", repository(cfg))
    if not m:
        return ""
    return (f"https://github.com/{m.group(1)}/{m.group(2)}/issues/new?title={quote(title[:120])}"
            f"&body={quote(body[:6000])}&labels=bug")


def build(cfg: sys_config.Config, description: str, steps: str = "", expected: str = "", run_ids: list[str] | None = None,
          hours: float = 6, health: dict | None = None, features: dict | None = None) -> dict:
    """Write the zip; returns its name, size, files, what was masked, and the issue link."""
    description = description.strip()
    if len(description) < 10:
        raise ValueError("describe the bug in a few words (at least 10 characters)")
    hours = max(1.0, min(float(hours), 72.0))
    mask = Pseudonymizer(cfg)
    since = datetime.now().astimezone() - timedelta(hours=hours)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = cfg.path("AURORA_BUGREPORT_DIR")
    out_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    env = _environment(cfg)
    entries: dict[str, str] = {}
    if health is not None:
        entries["health.json"] = json.dumps(health, indent=1, ensure_ascii=False)
    if features is not None:
        entries["features.json"] = json.dumps(features, indent=1, ensure_ascii=False)
    entries["environment.json"] = json.dumps(env, indent=1, ensure_ascii=False)
    entries["settings.txt"] = _settings(cfg)
    log_dir = cfg.path("AURORA_LOG_DIR")
    for f in sorted(log_dir.glob("*/*.log")):
        if f.parent.name == "plugins":
            continue
        text = _recent_lines(f, since)
        if text:
            entries[f"logs/{f.parent.name}.log"] = text
    entries["logs/problems.log"] = _problems(cfg)
    for f in sorted((log_dir / "plugins").glob("*.stderr.log")):
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()[-300:]
        if lines:
            entries[f"logs/plugins/{f.name}"] = "\n".join(lines) + "\n"
    for rid in (run_ids or [])[:10]:
        if re.fullmatch(r"[0-9a-f]{6,32}", rid):
            ev = sys_logread.run_events(rid, cfg)
            if ev:
                entries[f"runs/{rid}.jsonl"] = "".join(json.dumps(e, ensure_ascii=False, default=str) + "\n" for e in ev)
    problems = (health or {}).get("problems", [])
    report = (f"# Bug report — {stamp}\n\n## What happened\n{description}\n\n"
              + (f"## Steps\n{steps.strip()}\n\n" if steps.strip() else "")
              + (f"## Expected\n{expected.strip()}\n\n" if expected.strip() else "")
              + f"## Environment\nAurora {env['aurora']} ({env['commit']}) · {env['os']} · kernel {env['kernel']} · "
                f"Python {env['python']} · GPUs: {', '.join(env['gpus']) if isinstance(env['gpus'], list) else env['gpus']}\n\n"
              + "## Health\n" + ("\n".join(f"- {p}" for p in problems) or "- every check ok") + "\n\n"
              + f"## Attached\nLogs of the last {hours:g} h, warnings and errors of 7 days, plugin errors"
              + (f", the runs {', '.join(run_ids)}" if run_ids else "") + ". Private data replaced by placeholders.\n")
    entries = {"report.md": report, **entries}
    masked = {name: mask.mask(text) for name, text in entries.items()}   # one masker: the same value, the same name
    zpath = out_dir / f"aurora-bug-{stamp}.zip"
    fd = os.open(zpath, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh, zipfile.ZipFile(fh, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in masked.items():
            z.writestr(name, text)
    title = description.splitlines()[0][:100]
    return {"name": zpath.name, "bytes": zpath.stat().st_size, "files": sorted(masked), "masked": dict(mask.counts),
            "issue_url": issue_url(cfg, mask.mask(title), masked["report.md"] + "\n\n_(attach the zip: "
                                                         f"{zpath.name})_"), "created": time.time()}


def listing(cfg: sys_config.Config) -> list[dict]:
    d = cfg.path("AURORA_BUGREPORT_DIR")
    return [{"name": f.name, "bytes": f.stat().st_size, "created": f.stat().st_mtime}
            for f in sorted(d.glob("aurora-bug-*.zip"), reverse=True)] if d.is_dir() else []

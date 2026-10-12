#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora on the public test sets the labs report their models on (owner, 2026-10-12: «non sarebbe male avere i test
free di quelle batterie… testare aurora con tutte le sue capacità attive indicando nei test la configurazione usata:
solo locale, mista e con cosa, solo cloud e con cosa… tieni claude code come destinazione cloud»).

Aurora is asked as a person asks her — the whole pipeline through the API (/v1/aurora/ask, remember: false), with
everything she has on — never the bare model. Each run says its configuration: who does each step (local model, or
Claude Code with which model), the local model's file, the English pivot, the thinking. Three configurations:
  local   every step on the local model
  mixed   the owner's own choice, as it is (the Models page)
  cloud   every step to Claude Code (--cloud-model; pictures stay local: the CLI sees none)
The owner's choice is saved before and put back after, also when the run is stopped (or by hand: --restore).
The sets and their scoring: bench_public_data. Results: <STATUS>/bench/public/<date>-<config>.json, saved after every
set. Claude Code is the cloud and the judge (the owner's subscription); a cloud run makes several calls a question.

    python sys/core/script/bench_public.py --config local --n 20
    python sys/core/script/bench_public.py --config all --sets mmlu_pro,aime --n 10
    python sys/core/script/bench_public.py --fetch            # download the sets only
    python sys/core/script/bench_public.py --restore          # put the owner's choice back after a crash
"""
from __future__ import annotations

import argparse
import json
import shutil
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bench_public_data as D  # noqa: E402
from bench_agi import ask  # noqa: E402
from bench_quality import cfg  # noqa: E402

from aurora import mdl_router  # noqa: E402
from aurora.mdl_cloud import ClaudeCodeLLM  # noqa: E402

OUT = cfg.path("AURORA_STATUS_DIR") / "bench" / "public"
CACHE = OUT / "cache"
SAVED = OUT / "owner_roles.json"            # the owner's choice while a run changes it
DEFAULT_SETS = ["mmlu_pro", "gpqa_diamond", "aime", "math500", "simpleqa", "truthfulqa", "arc_agi_1"]


def roles_file() -> Path:
    return cfg.path("AURORA_STATUS_DIR") / "models" / "roles.json"


def save_owner() -> None:
    if not SAVED.exists():                  # a run stopped before: the owner's choice is the one saved then
        OUT.mkdir(parents=True, exist_ok=True)
        SAVED.write_text(json.dumps(mdl_router.assignments(cfg), indent=1), encoding="utf-8")


def restore() -> bool:
    if not SAVED.exists():
        return False
    shutil.copyfile(SAVED, roles_file())
    SAVED.unlink()
    print("the owner's choice of models is back", flush=True)
    return True


def configure(name: str, cloud_model: str) -> dict:
    """The roles of a configuration, written where the API reads them at every call."""
    owner = json.loads(SAVED.read_text(encoding="utf-8"))
    if name == "local":
        roles = {r: {"provider": "local", "model": ""} for r in mdl_router.ROLES}
    elif name == "cloud":
        roles = {r: {"provider": "claude_code", "model": cloud_model} for r in mdl_router.ROLES}
        roles["vision"] = {"provider": "local", "model": ""}
    else:
        roles = owner
    mdl_router.set_assignments(cfg, roles)
    return roles


def described(name: str, roles: dict) -> dict:
    used = sorted({f"{a['provider']}{':' + a['model'] if a['model'] else ''}" for a in roles.values()})
    return {"config": name, "uses": used, "roles": roles, "local_model": Path(str(cfg["AURORA_LLM_MODEL"])).name,
            "pivot_en": bool(cfg["AURORA_PIPELINE_PIVOT_EN"]), "thinking": str(cfg["AURORA_PIPELINE_THINKING"]),
            "think_tokens": cfg["AURORA_PIPELINE_THINK_TOKENS"]}


def run(name: str, sets: list[str], n: int, cloud_model: str, judge) -> Path:
    roles = configure(name, cloud_model)
    info = described(name, roles)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    path = OUT / f"{stamp}-{name}.json"
    report = {"at": time.time(), **info, "n": n, "sets": {}}
    print(f"\n=== {name}: {', '.join(info['uses'])} (local model {info['local_model']}, pivot {info['pivot_en']})",
          flush=True)
    for s in sets:
        try:
            items = D.sample(D.SETS[s](CACHE), n)
        except Exception as e:                           # noqa: BLE001 — a set that cannot be read is said, not fatal
            why = "gated: HF_TOKEN needed" if s in D.GATED else str(e)[:200]
            report["sets"][s] = {"skipped": why}
            print(f"-- {s}: skipped ({why})", flush=True)
            continue
        rows, t0 = [], time.time()
        for it in items:
            res = ask(it["prompt"])
            sc = D.score(it, res["answer"], judge)
            rows.append({"id": it["id"], "expected": it["answer"][:200], **sc, "declined": res["abstained"],
                         "seconds": res["seconds"], "answer": res["answer"][-1500:]})
            print(f"{'✓' if sc['right'] else '✗'} {s} {it['id']} {res['seconds']} s got {str(sc['got'])[:40]!r} "
                  f"want {it['answer'][:40]!r}{' (declined)' if res['abstained'] else ''}", flush=True)
        right = sum(r["right"] for r in rows)
        secs = sorted(r["seconds"] for r in rows)
        report["sets"][s] = {"right": right, "total": len(rows), "accuracy": round(right / len(rows), 3) if rows else None,
                             "declined": sum(r["declined"] for r in rows), "median_s": secs[len(secs) // 2] if secs else None,
                             "minutes": round((time.time() - t0) / 60, 1), "rows": rows}
        if s == "simpleqa":                              # its own measures: attempted, and correct of attempted
            att = [r for r in rows if r.get("grade") != "NOT_ATTEMPTED"]
            report["sets"][s].update(attempted=len(att), correct_of_attempted=round(right / len(att), 3) if att else None)
        print(f"== {s}: {right}/{len(rows)}", flush=True)
        OUT.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="mixed", choices=("local", "mixed", "cloud", "all"))
    ap.add_argument("--sets", default=",".join(DEFAULT_SETS), help=f"of: {', '.join(D.SETS)}")
    ap.add_argument("--n", type=int, default=20, help="questions a set (a fixed sample; 0 = all)")
    ap.add_argument("--cloud-model", default="sonnet", help="Claude Code's model for the cloud configuration")
    ap.add_argument("--judge", default="sonnet", help="Claude Code's model that judges MATH and SimpleQA")
    ap.add_argument("--fetch", action="store_true", help="download the sets and stop")
    ap.add_argument("--restore", action="store_true", help="put the owner's choice of models back")
    a = ap.parse_args()
    if a.restore:
        print("restored" if restore() else "nothing to restore")
        return 0
    sets = [s for s in a.sets.split(",") if s]
    if bad := [s for s in sets if s not in D.SETS]:
        ap.error(f"unknown set: {', '.join(bad)}")
    if a.fetch:
        for s in sets:
            try:
                print(s, len(D.SETS[s](CACHE)))
            except Exception as e:                       # noqa: BLE001
                print(s, "not fetched:", str(e)[:160])
        return 0
    save_owner()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))     # stopped: the finally below still restores
    judge = ClaudeCodeLLM(cfg, a.judge)
    try:
        for name in (("local", "mixed", "cloud") if a.config == "all" else (a.config,)):
            print("→", run(name, sets, a.n, a.cloud_model, judge), flush=True)
    finally:
        restore()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

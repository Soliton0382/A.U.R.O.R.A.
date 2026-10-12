#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora against the bare models, on the public test sets the labs report on and on what only Aurora has (owner,
2026-10-12: «testare aurora con tutte le sue capacità attive indicando la configurazione usata: solo locale, mista,
solo cloud… un benchmark che dica con aurora si ottengono tot risultati, senza questi… tieni claude code come
destinazione cloud»).

Targets — the same questions to each:
  aurora-local   Aurora whole (the API, /v1/aurora/ask, remember: false), every step on the local model
  aurora-mixed   Aurora whole with the owner's own choice of models, as it is
  aurora-cloud   Aurora whole, every step to Claude Code (--cloud-model; pictures stay local)
  bare-local     the local model alone: the question, nothing else (thinking on)
  bare-claude    Claude through the owner's subscription alone (the CLI with no tools, no MCP)
Each run says who did each step. The owner's choice of models is saved before an aurora-* target changes it and put
back after, also when the run is stopped (or by hand: --restore).
The sets: bench_public_data (MMLU-Pro, GPQA, AIME, MATH-500, SimpleQA, TruthfulQA, ARC-AGI) and «aurora_edge»
(bench_edge: her vault, this machine and house now, honesty). Results: <STATUS>/bench/public/<date>-<target>.json,
saved after every set; --report puts the latest of each target side by side (report.md).

    python sys/core/script/bench_public.py --targets aurora-mixed,bare-local,bare-claude --n 10
    python sys/core/script/bench_public.py --report
    python sys/core/script/bench_public.py --restore
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
import bench_edge as E  # noqa: E402
import bench_public_data as D  # noqa: E402
from bench_agi import ask  # noqa: E402
from bench_quality import cfg  # noqa: E402

from aurora import mdl_router  # noqa: E402
from aurora.mdl_cloud import ClaudeCodeLLM  # noqa: E402
from aurora.mdl_llm import LLM  # noqa: E402

OUT = cfg.path("AURORA_STATUS_DIR") / "bench" / "public"
CACHE = OUT / "cache"
SAVED = OUT / "owner_roles.json"            # the owner's choice while a run changes it
TARGETS = ("aurora-local", "aurora-mixed", "aurora-cloud", "bare-local", "bare-claude")
DEFAULT_SETS = ["aurora_edge", "mmlu_pro", "gpqa_diamond", "aime", "math500", "simpleqa", "truthfulqa", "arc_agi_1"]
BARE_SYSTEM = "You are a helpful assistant. Answer in the language of the question."


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


def prepare(target: str, cloud_model: str, bare_tokens: int = 28000):
    """(who answers: a function question → {"answer", "abstained", "seconds"}, what the run says about itself)."""
    local = Path(str(cfg["AURORA_LLM_MODEL"])).name
    if target.startswith("aurora-"):
        save_owner()
        owner = json.loads(SAVED.read_text(encoding="utf-8"))
        name = target.split("-", 1)[1]
        if name == "local":
            roles = {r: {"provider": "local", "model": ""} for r in mdl_router.ROLES}
        elif name == "cloud":
            roles = {r: {"provider": "claude_code", "model": cloud_model} for r in mdl_router.ROLES}
            roles["vision"] = {"provider": "local", "model": ""}
        else:
            roles = owner
        mdl_router.set_assignments(cfg, roles)
        used = sorted({f"{a['provider']}{':' + a['model'] if a['model'] else ''}" for a in roles.values()})
        return ask, {"target": target, "uses": used, "roles": roles, "local_model": local,
                     "pivot_en": bool(cfg["AURORA_PIPELINE_PIVOT_EN"]),
                     "thinking": f"{cfg['AURORA_PIPELINE_THINKING']}, up to {cfg['AURORA_PIPELINE_THINK_TOKENS']} tokens"}
    llm = LLM(cfg) if target == "bare-local" else ClaudeCodeLLM(cfg, cloud_model)

    def bare(q: str) -> dict:
        t0 = time.time()
        try:
            text = llm.complete(BARE_SYSTEM, q, bare_tokens, think=True).answer
        except Exception as e:                           # noqa: BLE001 — an error is a wrong answer, said
            text = f"(error: {e})"
        return {"answer": text, "abstained": False, "seconds": round(time.time() - t0, 1)}
    return bare, {"target": target, "uses": [local if target == "bare-local" else f"claude_code:{cloud_model}"],
                  "thinking": f"on, up to {bare_tokens} tokens", "tools": "none"}


def questions(s: str, n: int) -> list[dict]:
    if s == "aurora_edge":
        return E.items(cfg, n or 10)
    return D.sample(D.SETS[s](CACHE), n)


def grade(it: dict, answer: str, judge) -> dict:
    if callable(it.get("truth")):                        # the truth of now, computed at the answer
        it["answer"] = it["truth"]()
    if it["kind"] in ("numbers", "onoff", "source", "judge"):
        return E.score(it, answer, judge)
    return D.score(it, answer, judge)


def run(target: str, sets: list[str], n: int, cloud_model: str, judge, bare_tokens: int = 28000) -> Path:
    answer, info = prepare(target, cloud_model, bare_tokens)
    path = OUT / f"{datetime.now():%Y%m%d-%H%M}-{target}.json"
    report = {"at": time.time(), **info, "n": n, "sets": {}}
    print(f"\n=== {target}: {', '.join(info['uses'])}", flush=True)
    for s in sets:
        try:
            items = questions(s, n)
        except Exception as e:                           # noqa: BLE001 — a set that cannot be read is said, not fatal
            why = "gated: HF_TOKEN needed" if s in D.GATED else str(e)[:200]
            report["sets"][s] = {"skipped": why}
            print(f"-- {s}: skipped ({why})", flush=True)
            continue
        rows, t0 = [], time.time()
        for it in items:
            res = answer(it["prompt"])
            sc = grade(it, res["answer"], judge)
            rows.append({"id": it["id"], "group": it.get("group", ""), "expected": str(it.get("answer"))[:200], **sc,
                         "declined": res["abstained"], "seconds": res["seconds"], "answer": res["answer"][-1500:]})
            print(f"{'✓' if sc['right'] else '✗'} {s} {it['id']} {res['seconds']} s {str(sc['got'])[:50]!r}"
                  f"{' (declined)' if res['abstained'] else ''}", flush=True)
        right, secs = sum(r["right"] for r in rows), sorted(r["seconds"] for r in rows)
        entry = {"right": right, "total": len(rows), "accuracy": round(right / len(rows), 3) if rows else None,
                 "declined": sum(r["declined"] for r in rows), "median_s": secs[len(secs) // 2] if secs else None,
                 "minutes": round((time.time() - t0) / 60, 1), "rows": rows}
        if s == "simpleqa":                              # its own measures: attempted, and correct of attempted
            att = [r for r in rows if r.get("grade") != "NOT_ATTEMPTED"]
            entry.update(attempted=len(att), correct_of_attempted=round(right / len(att), 3) if att else None)
        if s == "aurora_edge":
            entry["groups"] = {g: f"{sum(r['right'] for r in rows if r['group'] == g)}/{sum(r['group'] == g for r in rows)}"
                               for g in sorted({r["group"] for r in rows})}
        report["sets"][s] = entry
        print(f"== {s}: {right}/{len(rows)}", flush=True)
        OUT.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def side_by_side() -> str:
    """The latest run of each target, a set a row (Markdown), with the self-repair and forge results beside."""
    latest = {}
    for f in sorted(OUT.glob("*-*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if d.get("target") in TARGETS:
            latest[d["target"]] = d
    order = [t for t in TARGETS if t in latest]
    sets = [s for s in [*DEFAULT_SETS, "arc_agi_2"] if any(s in latest[t]["sets"] for t in order)]
    lines = ["| set | " + " | ".join(order) + " |", "|---" * (len(order) + 1) + "|"]
    for s in sets:
        cells = []
        for t in order:
            e = latest[t]["sets"].get(s)
            cells.append("—" if not e else "skipped" if "skipped" in e else
                         f"{e['right']}/{e['total']}" + (f" ({', '.join(f'{g} {v}' for g, v in e['groups'].items())})"
                                                         if e.get("groups") else ""))
        lines.append(f"| {s} | " + " | ".join(cells) + " |")
    lines.append("| configuration | " + " | ".join(", ".join(latest[t]["uses"]) for t in order) + " |")
    bench = cfg.path("AURORA_STATUS_DIR") / "bench"
    extra = []
    for name, file in (("self-repair", "repair.json"), ("forge", "forge_roles.json")):
        try:
            rows = json.loads((bench / file).read_text(encoding="utf-8"))["rows"]
            extra.append(f"- {name} (Aurora only; a bare model has no sandbox): {sum(bool(r.get('right')) for r in rows)}/{len(rows)}")
        except (OSError, ValueError, KeyError):
            extra.append(f"- {name}: not run")
    extra.append("- memory over days: no test yet")
    return "\n".join(lines + [""] + extra) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--targets", default="aurora-mixed,bare-local,bare-claude", help=f"of: {', '.join(TARGETS)}")
    ap.add_argument("--sets", default=",".join(DEFAULT_SETS), help=f"of: aurora_edge, {', '.join(D.SETS)}")
    ap.add_argument("--n", type=int, default=10, help="questions a set (a fixed sample; 0 = all)")
    ap.add_argument("--cloud-model", default="sonnet", help="Claude Code's model for aurora-cloud and bare-claude")
    ap.add_argument("--judge", default="sonnet", help="Claude Code's model that judges")
    ap.add_argument("--bare-tokens", type=int, default=28000,
                    help="a bare model's room to think and answer (8000 cut the local model's AIME inside its reasoning)")
    ap.add_argument("--fetch", action="store_true", help="download the public sets and stop")
    ap.add_argument("--report", action="store_true", help="the latest of each target side by side")
    ap.add_argument("--restore", action="store_true", help="put the owner's choice of models back")
    a = ap.parse_args()
    if a.restore:
        print("restored" if restore() else "nothing to restore")
        return 0
    if a.report:
        text = side_by_side()
        (OUT / "report.md").write_text(text, encoding="utf-8")
        print(text)
        return 0
    sets = [s for s in a.sets.split(",") if s]
    targets = [t for t in a.targets.split(",") if t]
    if bad := [s for s in sets if s not in D.SETS and s != "aurora_edge"] + [t for t in targets if t not in TARGETS]:
        ap.error(f"unknown: {', '.join(bad)}")
    if a.fetch:
        for s in [s for s in sets if s in D.SETS]:
            try:
                print(s, len(D.SETS[s](CACHE)))
            except Exception as e:                       # noqa: BLE001
                print(s, "not fetched:", str(e)[:160])
        return 0
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))     # stopped: the finally below still restores
    judge = ClaudeCodeLLM(cfg, a.judge)
    try:
        for t in targets:
            print("→", run(t, sets, a.n, a.cloud_model, judge, a.bare_tokens), flush=True)
            restore()                                    # between targets too: the owner's Aurora as it was
    finally:
        restore()
    print("\n" + side_by_side())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

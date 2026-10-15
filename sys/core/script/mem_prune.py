#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The same question asked again and again (probes, benchmarks by hand) taken out of a user's memory.

Owner, 15 Oct: «se inondano il vault è un problema… è come se l'avessimo addestrata». C326: a week of session memories
about repeated test questions pushed a real conversation out of what she recalls. This reads the user's conversation
(read only), groups the questions asked at least --min times, and lists them. With --apply 1,3 the groups chosen are
forgotten through the API — the exchanges (question and answer, with their index rows) and the session memories made
only of them — the same routes as «forget» in the 🧠 memory page. The dreams, thoughts and reviews they inspired stay.

    python sys/core/script/mem_prune.py                 # what would go, numbered
    python sys/core/script/mem_prune.py --apply 1,2     # forget groups 1 and 2
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aurora import sys_config, sys_user_config  # noqa: E402
from aurora.sol_reader import VaultReader  # noqa: E402


def norm(text: str) -> str:
    return " ".join(text.split()).lower()[:160]


def groups(reader: VaultReader, least: int) -> list[dict]:
    """[{"question", "runs": [source_id…]}], most asked first: a user's questions asked at least `least` times."""
    runs = defaultdict(set)
    for _, _, s in reader.iter_domain("conversation"):
        if s.extra.get("role") == "user" and s.source_id.startswith("run:"):
            runs[norm(s.text)].add(s.source_id)
    out = [{"question": q, "runs": sorted(r)} for q, r in runs.items() if len(r) >= least]
    return sorted(out, key=lambda g: -len(g["runs"]))


def memories_of(reader: VaultReader, runs: set[str]) -> list[str]:
    """The session memories whose every turn belongs to the runs going away (a mixed session stays)."""
    turn_run = {s.sid: s.source_id for _, _, s in reader.iter_domain("conversation")}
    out = []
    for _, _, s in reader.iter_domain("reflection"):
        turns = s.extra.get("turns") or []
        if s.extra.get("type") == "session_memory" and turns and all(turn_run.get(t) in runs for t in turns):
            out.append(s.source_id)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--user", default="", help="whose memory (default: the admin's)")
    ap.add_argument("--min", type=int, default=3, help="asked at least this many times")
    ap.add_argument("--apply", default="", help="the groups to forget, by number (1,3)")
    a = ap.parse_args()
    cfg = sys_config.load()
    import httpx
    base = f"http://{cfg['AURORA_API_HOST']}:{cfg['AURORA_API_PORT']}"
    head = {"Authorization": f"Bearer {cfg['AURORA_API_KEY']}"}
    from aurora.sys_users import Users
    user = a.user or Users(cfg.base or cfg).admin_name() or ""
    reader = VaultReader(sys_user_config.for_user(cfg, user) if user else cfg, user=user or None)
    found = groups(reader, a.min)
    for n, g in enumerate(found, 1):
        print(f"{n:3d}. {len(g['runs']):3d}×  {g['question'][:110]}")
    if not a.apply:
        print("\nnothing forgotten: --apply 1,2,… forgets the groups chosen")
        return 0
    chosen = [found[int(x) - 1] for x in a.apply.split(",") if x.strip()]
    runs = {r for g in chosen for r in g["runs"]}
    mems = memories_of(reader, runs)
    reader.close()
    gone = 0
    for r in sorted(runs):
        res = httpx.delete(f"{base}/v1/aurora/memory/conversation", params={"source_id": r}, headers=head, timeout=60)
        gone += res.json().get("forgotten", 0) if res.status_code == 200 else 0
    for m in mems:
        httpx.delete(f"{base}/v1/aurora/memory/about-me", params={"source_id": m}, headers=head, timeout=60)
    print(f"\nforgotten: {len(runs)} exchanges ({gone} turns), {len(mems)} session memories")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The same question asked again and again (probes, benchmarks by hand) taken out of a user's memory.

Owner, 15 Oct: «se inondano il vault è un problema… è come se l'avessimo addestrata». C326: a week of session memories
about repeated test questions pushed a real conversation out of what she recalls. This reads the user's conversation
(read only), groups the questions asked at least --min times, and lists them. With --apply 1,3 the groups chosen are
thinned through the API: the best --keep exchanges of each stay (owner: «lascia almeno una domanda e una risposta…
sono le mille mila ripetizioni che non vanno bene… teniamo il meglio») — the latest answer that is no refusal, in the
question's language, with no leaked reasoning, one citing its sources first; a group with none such goes whole (a bad
answer kept is read back as «how I answered last time») — the exchanges (question and answer, with their index rows) and the session memories made
only of them — the same routes as «forget» in the 🧠 memory page. The dreams, thoughts and reviews they inspired stay.

    python sys/core/script/mem_prune.py                 # what would go, numbered
    python sys/core/script/mem_prune.py --apply 1,2     # groups 1 and 2: the best exchange stays, the rest goes
    python sys/core/script/mem_prune.py --plan p.json --apply all   # a reviewed list: {"conversation": [run:…],
                                                                    #  "reflection": [dream:…, study:…, …]}
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import re  # noqa: E402

from aurora import sys_config, sys_user_config, txt_lang  # noqa: E402
from aurora.sol_reader import VaultReader  # noqa: E402

# a refusal (nothing in the vault or on the web) or the model's reasoning left in the answer: never the one kept
BAD = re.compile(r"(?i)non ho trovato (conoscenza verificata|una risposta)|i found no verified knowledge|"
                 r"let's craft|use the same citations|just answer\.")


def norm(text: str) -> str:
    return " ".join(text.split()).lower()[:160]


def groups(reader: VaultReader, least: int) -> list[dict]:
    """[{"question", "runs": [source_id…] oldest first}], most asked first: the questions asked at least `least` times."""
    runs = defaultdict(dict)
    for _, _, s in reader.iter_domain("conversation"):
        if s.extra.get("role") == "user" and s.source_id.startswith("run:"):
            runs[norm(s.text)].setdefault(s.source_id, s.created_at)
    out = [{"question": q, "runs": sorted(r, key=r.get)} for q, r in runs.items() if len(r) >= least]
    return sorted(out, key=lambda g: -len(g["runs"]))


def good(question: str, answer) -> bool:
    # not answer.extra["abstained"]: «it does not exist, I will not invent it» is abstained too, and the one to keep
    return (answer is not None and not BAD.search(answer.text)
            and txt_lang.detect(answer.text) == txt_lang.detect(question))


def best(g: dict, answers: dict, keep: int) -> list[str]:
    """The runs of a group that stay: the good answers, the ones citing [n] first, the latest first."""
    ok = [r for r in g["runs"] if good(g["question"], answers.get(r))]
    ok.sort(key=lambda r: (bool(re.search(r"\[\d+\]", answers[r].text)), answers[r].created_at), reverse=True)
    return ok[:max(0, keep)]


def memories_of(reader: VaultReader, runs: set[str]) -> list[str]:
    """The session memories whose every turn belongs to the runs going away (a mixed session stays)."""
    turn_run = {s.sid: s.source_id for _, _, s in reader.iter_domain("conversation")}
    out = []
    for _, _, s in reader.iter_domain("reflection"):
        turns = s.extra.get("turns") or []
        if s.extra.get("type") == "session_memory" and turns and all(turn_run.get(t) in runs for t in turns):
            out.append(s.source_id)
    return out


def plan(reader: VaultReader, todo: dict, go: bool, base: str, head: dict) -> int:
    """A list reviewed by hand: the exchanges, the session memories made only of them, the other reflections."""
    import httpx
    runs = set(todo.get("conversation") or [])
    mems = memories_of(reader, runs)
    others = [x for x in todo.get("reflection") or [] if x not in mems]
    reader.close()
    print(f"{len(runs)} exchanges, {len(mems)} session memories made only of them, {len(others)} other reflections")
    if not go:
        print("nothing forgotten: --apply all forgets them")
        return 0
    done = Counter()
    for r in sorted(runs):
        done["exchanges"] += httpx.delete(f"{base}/v1/aurora/memory/conversation", params={"source_id": r},
                                          headers=head, timeout=60).status_code == 200
    for m in mems:
        done["session memories"] += httpx.delete(f"{base}/v1/aurora/memory/about-me", params={"source_id": m},
                                                 headers=head, timeout=60).status_code == 200
    for x in others:
        done["reflections"] += httpx.delete(f"{base}/v1/aurora/memory/reflection", params={"source_id": x},
                                            headers=head, timeout=60).status_code == 200
    print("forgotten:", dict(done))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--user", default="", help="whose memory (default: the admin's)")
    ap.add_argument("--min", type=int, default=3, help="asked at least this many times")
    ap.add_argument("--apply", default="", help="the groups to thin, by number (1,3)")
    ap.add_argument("--keep", type=int, default=1, help="the best exchanges of each group that stay")
    ap.add_argument("--plan", default="", help="a reviewed list to forget instead of the groups (JSON)")
    a = ap.parse_args()
    cfg = sys_config.load()
    import httpx
    base = f"http://{cfg['AURORA_API_HOST']}:{cfg['AURORA_API_PORT']}"
    head = {"Authorization": f"Bearer {cfg['AURORA_API_KEY']}"}
    from aurora.sys_users import Users
    user = a.user or Users(cfg.base or cfg).admin_name() or ""
    reader = VaultReader(sys_user_config.for_user(cfg, user) if user else cfg, user=user or None)
    if a.plan:
        return plan(reader, json.loads(Path(a.plan).read_text(encoding="utf-8")), a.apply == "all", base, head)
    found = groups(reader, a.min)
    answers = {s.source_id: s for _, _, s in reader.iter_domain("conversation") if s.extra.get("role") == "assistant"}
    for n, g in enumerate(found, 1):
        g["keep"] = best(g, answers, a.keep)
        print(f"{n:3d}. {len(g['runs']):3d}×  {g['question'][:110]}")
        for r in g["keep"]:
            print(f"        stays ({answers[r].created_at[:10]}): {' '.join(answers[r].text.split())[:120]}")
        if not g["keep"]:
            print("        stays: nothing (no good answer among them)")
    if not a.apply:
        print(f"\nnothing forgotten: --apply 1,2,… thins the groups chosen (the best {a.keep} of each stays)")
        return 0
    chosen = [found[int(x) - 1] for x in a.apply.split(",") if x.strip()]
    runs = {r for g in chosen for r in g["runs"] if r not in g["keep"]}
    mems = memories_of(reader, runs)
    reader.close()
    gone = 0
    for r in sorted(runs):
        res = httpx.delete(f"{base}/v1/aurora/memory/conversation", params={"source_id": r}, headers=head, timeout=60)
        gone += res.json().get("forgotten", 0) if res.status_code == 200 else 0
    for m in mems:
        httpx.delete(f"{base}/v1/aurora/memory/about-me", params={"source_id": m}, headers=head, timeout=60)
    print(f"\nforgotten: {len(runs)} exchanges ({gone} turns), {len(mems)} session memories; "
          f"kept: {sum(len(g['keep']) for g in chosen)} (the best of each group)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""How many passages this CPU can re-rank for one question (C229, 9 Oct: on 2 cores the fixed 30 candidates of the
cloud profile took ~43 s a re-ranking — 57 s for 40, measured — and a question re-ranks several times: 5.5 minutes
before the first word). Law 2: the ceiling first. One re-ranking may take BUDGET_S; the candidates are what fits,
between the settings' minimum and the profile's 30.

    .venv/bin/python sys/core/script/sys_calibrate.py            # measures and says
    .venv/bin/python sys/core/script/sys_calibrate.py --write    # and writes AURORA_SEARCH_CANDIDATES

On a GPU nothing is measured: the reference machine re-ranks 300 candidates in a second or two (M31).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aurora import sys_config  # noqa: E402

BUDGET_S = 15.0          # one re-ranking: a question re-ranks its own words, the translation and the pages it read
CEILING = 30             # the cloud profile's (M151); the floor is the schema's minimum (floor())
PAIRS = 8
# a passage as long as a real one (the re-ranker reads up to AURORA_RERANKER_MAX_TOKENS of it)
PASSAGE = ("A soliton is a self-reinforcing wave packet that keeps its shape while it travels at a constant speed; it "
           "arises from a balance between nonlinear and dispersive effects in the medium. ") * 12


def floor(cfg: sys_config.Config) -> int:
    """The fewest candidates the settings accept (a number of its own here wrote 8 under the schema's 10 and the
    configuration no longer loaded: C229, the test VM)."""
    return int(cfg.specs["AURORA_SEARCH_CANDIDATES"].get("min", 1))


def measure(cfg: sys_config.Config) -> dict:
    from aurora.mdl_reranker import Reranker
    r = Reranker(cfg)
    r.score([("what is a soliton?", PASSAGE)] * 2)                      # warm: the first call pays the loading
    t0 = time.time()
    r.score([("what is a soliton?", PASSAGE)] * PAIRS)
    per = (time.time() - t0) / PAIRS
    return {"seconds_per_passage": round(per, 3), "candidates": max(floor(cfg), min(CEILING, int(BUDGET_S / per))),
            "budget_s": BUDGET_S, "device": str(cfg["AURORA_RERANKER_DEVICE"]), "dtype": str(cfg["AURORA_RERANKER_DTYPE"])}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    cfg = sys_config.get()
    if not str(cfg["AURORA_RERANKER_DEVICE"]).startswith("cpu"):
        print(json.dumps({"skipped": "the re-ranker is on a GPU"}))
        return 0
    out = measure(cfg)
    if a.write:
        sys_config.write_env(sys_config.env_file_path(), {"AURORA_SEARCH_CANDIDATES": str(out["candidates"])})
        out["written"] = "AURORA_SEARCH_CANDIDATES"
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())

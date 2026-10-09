# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The audit of this machine (owner, 9 Oct: «un audit fatto dall'installer per determinare i giusti parametri per le
performance»): what it can do on its CPU, measured, and the settings that fit it. Run by every installer and by
Docker at the first start; again whenever the machine changes.

    .venv/bin/python sys/core/script/sys_calibrate.py            # measures and says
    .venv/bin/python sys/core/script/sys_calibrate.py --write    # and writes the settings

Law 2: the ceiling first. What it measures and what follows (C229, 9 Oct: on 2 cores the fixed 30 candidates of the
cloud profile took ~43 s a re-ranking, and the harvest kept both cores busy for hours):
- the re-ranker's seconds a passage → AURORA_SEARCH_CANDIDATES: what fits in BUDGET_S, between the settings'
  minimum and the profile's 30;
- the encoder's seconds a passage → AURORA_HARVEST_PER_CATEGORY: a round's indexing within HARVEST_SHARE of the time
  between two rounds (a round brings up to DOCS_PER_UNIT documents for each unit of the setting, C214's 362 at 10, of
  PASSAGES_PER_DOC passages, M154), never more than the recommended 10;
- the cores and the memory → the tier: light, standard, strong; a light machine encodes in batches of 4.
On a GPU nothing is measured: the reference machine re-ranks 300 candidates in a second or two (M31).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from aurora import sys_config  # noqa: E402

BUDGET_S = 15.0          # one re-ranking: a question re-ranks its own words, the translation and the pages it read
CEILING = 30             # the cloud profile's (M151); the floor is the schema's minimum (floor())
PAIRS = 8
# a passage as long as a real one (the re-ranker reads up to AURORA_RERANKER_MAX_TOKENS of it)
PASSAGE = ("A soliton is a self-reinforcing wave packet that keeps its shape while it travels at a constant speed; it "
           "arises from a balance between nonlinear and dispersive effects in the medium. ") * 12
DOCS_PER_UNIT = 36.2     # C214: up to 362 documents in a round with AURORA_HARVEST_PER_CATEGORY=10, every domain on
PASSAGES_PER_DOC = 8.1   # M154: ~55 KB a document, ~6.8 KB a passage
HARVEST_SHARE = {"light": 0.25, "standard": 0.4, "strong": 0.6}   # of the time between two rounds, at most
PER_CATEGORY_MAX = 10    # the recommended value: the audit only lowers it


def floor(cfg: sys_config.Config) -> int:
    """The fewest candidates the settings accept (a number of its own here wrote 8 under the schema's 10 and the
    configuration no longer loaded: C229, the test VM)."""
    return int(cfg.specs["AURORA_SEARCH_CANDIDATES"].get("min", 1))


def measure(cfg: sys_config.Config) -> dict:
    """The re-ranker's speed and the candidates that fit BUDGET_S."""
    from aurora.mdl_reranker import Reranker
    r = Reranker(cfg)
    r.score([("what is a soliton?", PASSAGE)] * 2)                      # warm: the first call pays the loading
    t0 = time.time()
    r.score([("what is a soliton?", PASSAGE)] * PAIRS)
    per = (time.time() - t0) / PAIRS
    return {"seconds_per_passage": round(per, 3), "candidates": max(floor(cfg), min(CEILING, int(BUDGET_S / per))),
            "budget_s": BUDGET_S, "device": str(cfg["AURORA_RERANKER_DEVICE"]), "dtype": str(cfg["AURORA_RERANKER_DTYPE"])}


def measure_encoder(cfg: sys_config.Config) -> float:
    """The encoder's seconds for one harvested passage."""
    from aurora.mdl_embedder import Embedder
    e = Embedder(cfg)
    e.encode_documents([PASSAGE] * 2)                                    # warm
    t0 = time.time()
    e.encode_documents([PASSAGE] * PAIRS)
    return (time.time() - t0) / PAIRS


def tier(cores: int, ram_gb: float) -> str:
    """light: 4 cores or fewer, or under 10 GB (M151: models 5.0 GB at peak + API 2.0 + harvester 0.5); strong: 12
    cores and 24 GB or more; standard in between."""
    if cores <= 4 or ram_gb < 10:
        return "light"
    return "strong" if cores >= 12 and ram_gb >= 24 else "standard"


def active_share(cfg: sys_config.Config) -> float:
    """The share of the harvest's sources this installation collects (its chosen areas)."""
    from aurora import kno_sources
    cat = kno_sources.catalogue()["domains"]
    on = {d for d, m in kno_sources.modes(cfg).items() if m != "off"}

    def units(ds) -> int:
        return sum(len(s.get("categories", [])) if s["source"] == "arxiv" else 1 for d in ds for s in cat.get(d, []))
    return units(on) / max(1, units(cat))


def per_category(cfg: sys_config.Config, encode_s: float, kind: str) -> int:
    """The newest items a source gives in a round, so that indexing them takes at most HARVEST_SHARE of the interval."""
    room = HARVEST_SHARE[kind] * float(cfg["AURORA_HARVEST_INTERVAL_H"]) * 3600
    per_unit = DOCS_PER_UNIT * PASSAGES_PER_DOC * max(active_share(cfg), 0.01) * encode_s
    return max(1, min(PER_CATEGORY_MAX, int(room / per_unit)))


def audit(cfg: sys_config.Config) -> dict:
    import sys_profile
    cores, ram = os.cpu_count() or 1, sys_profile.ram_gb()
    kind = tier(cores, ram)
    rr = measure(cfg)
    enc = measure_encoder(cfg)
    env = {"AURORA_SEARCH_CANDIDATES": str(rr["candidates"]),
           "AURORA_HARVEST_PER_CATEGORY": str(per_category(cfg, enc, kind))}
    if kind == "light":
        env["AURORA_EMBEDDER_BATCH"] = "4"                               # smaller peaks of memory
    return {"tier": kind, "cores": cores, "ram_gb": ram, "rerank_s_per_passage": rr["seconds_per_passage"],
            "encode_s_per_passage": round(enc, 3), "env": env,
            # the same keys as before for the installers' summaries
            "seconds_per_passage": rr["seconds_per_passage"], "candidates": rr["candidates"]}


TIER_NAME = {"it": {"light": "leggero", "standard": "standard", "strong": "potente"},
             "en": {"light": "light", "standard": "standard", "strong": "strong"}}


def summary(out: dict, lang: str) -> str:
    """One line for the installers."""
    e, it = out["env"], lang == "it"
    line = (f"{'profilo' if it else 'profile'} {TIER_NAME[lang][out['tier']]}: {out['cores']} core, {out['ram_gb']} GB; "
            f"{'ricerca' if it else 'search'} {e['AURORA_SEARCH_CANDIDATES']} {'candidati' if it else 'candidates'} "
            f"({out['rerank_s_per_passage']} s/{'passaggio' if it else 'passage'}), "
            f"{'raccolta' if it else 'harvest'} {e['AURORA_HARVEST_PER_CATEGORY']} {'per fonte a giro' if it else 'a source a round'} "
            f"({out['encode_s_per_passage']} s/{'passaggio' if it else 'passage'})")
    return line + (f", batch {e['AURORA_EMBEDDER_BATCH']}" if "AURORA_EMBEDDER_BATCH" in e else "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--say", choices=("it", "en"), help="one readable line instead of the JSON (the installers)")
    a = ap.parse_args()
    cfg = sys_config.get()
    if not str(cfg["AURORA_RERANKER_DEVICE"]).startswith("cpu"):
        print({"it": "GPU: nulla da tarare"}.get(a.say, "GPU: nothing to tune") if a.say else
              json.dumps({"skipped": "the re-ranker is on a GPU"}))
        return 0
    out = audit(cfg)
    if a.write:
        sys_config.write_env(sys_config.env_file_path(), out["env"])
        out["written"] = sorted(out["env"])
    print(summary(out, a.say) if a.say else json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())

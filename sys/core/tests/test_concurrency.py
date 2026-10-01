# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Two writer processes at the same time (BUGS A2): every soliton stored once, registry consistent."""
import multiprocessing as mp

from aurora import sol_schema as S
from aurora import sol_vault, sys_config
from aurora.sol_writer import VaultWriter

FILLER = " The measured quantity follows the model within the stated uncertainty." * 6


def sols(n):
    return [S.Soliton.new(f"Concurrent write test number {i}.{FILLER}", "physics", "knowledge", "en", f"src:{i}")
            for i in range(n)]


def writer(env_file, start, n, barrier, out):
    cfg = sys_config.load(env_file, check_root=False)
    from aurora import sys_log
    sys_log.configure(cfg)
    items = sols(n)
    order = items[start:] + items[:start]               # the two processes start from different points
    barrier.wait()
    rep = VaultWriter(cfg).add_many(order)
    out.put((len(rep.written), len(rep.duplicates), len(rep.rejected)))


def test_two_processes_writing_the_same_solitons(cfg):
    n = 300
    ctx = mp.get_context("spawn")
    barrier, out = ctx.Barrier(2), ctx.Queue()
    procs = [ctx.Process(target=writer, args=(cfg.env_file, k * n // 2, n, barrier, out)) for k in (0, 1)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(120)
        assert p.exitcode == 0
    results = [out.get(timeout=5) for _ in procs]
    assert sum(w for w, _, _ in results) == n                 # each soliton written exactly once
    assert all(w + d == n for w, d, _ in results)            # the rest recognised as duplicates
    layout = sol_vault.Layout.from_config(cfg)
    report = sol_vault.check(layout)["knowledge"]
    assert not (report["unregistered"] or report["dangling"] or report["misplaced"])
    rows = 0
    for shard in layout.shards("knowledge", "physics"):
        with sol_vault.db(shard, readonly=True) as con:
            rows += con.execute("SELECT count(*) FROM solitons").fetchone()[0]
    assert rows == n

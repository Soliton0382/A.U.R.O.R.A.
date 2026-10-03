# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C103: a job thread closes its vault connections when it ends, instead of waiting for the garbage collector."""
import gc
import os
import threading

from aurora import sol_reader, sol_vault


class FakeReader(sol_reader.VaultReader):
    def __init__(self):                                   # no config: only the per-thread cache is under test
        self._local = threading.local()
        sol_reader._readers.add(self)


def fds() -> int:
    return len(os.listdir("/proc/self/fd"))


def test_release_closes_thread_connections(tmp_path):
    p = tmp_path / "x.db"
    con = sol_vault.connect(p)
    con.execute("CREATE TABLE t (a)")
    con.commit()
    con.close()
    r = FakeReader()

    def job():
        r._con(p).execute("SELECT * FROM t").fetchall()
        sol_reader.release()

    gc.collect()
    gc.disable()                                          # as in the API, where the collector rarely passes
    try:
        start = fds()
        for _ in range(5):
            t = threading.Thread(target=job)
            t.start()
            t.join()
        assert fds() == start
    finally:
        gc.enable()

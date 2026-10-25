# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔁 The coverage walk (sys_cycle): every index once per round, a slice per call, one integer kept between calls."""
from aurora import sys_cycle


def test_the_step_is_a_single_cycle_for_every_width():
    for m in range(2, 12):
        M, A = sys_cycle.constants(m)
        assert M % 2 == 1 and A % 4 == 3
        seen, T = set(), 0
        for _ in range(1 << m):
            T = ((T ^ M) * A) % (1 << m)
            seen.add(T)
        assert len(seen) == 1 << m


def test_slices_kept_between_calls_cover_everything_once_per_round():
    n, k, state, got = 1000, 37, 0, []
    while len(got) < n:
        part, state = sys_cycle.walk(n, k, state)
        got += part
    assert sorted(got[:n]) == list(range(n))                      # each index once before any comes back
    assert sys_cycle.walk(0, 5, 7) == ([], 7) and sys_cycle.walk(3, 10)[0] and len(sys_cycle.walk(3, 10)[0]) == 3

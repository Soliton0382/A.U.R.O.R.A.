# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A walk that visits every index of a collection once per round, a slice at a time, keeping one integer between calls
(owner, 25 Oct: «dove potremmo usare la formula» in Aurora). Drawing a slice at random each night sees 63 % of 10,000
items after 67 nights of 150 and needs about 655 nights for all of them; this walk sees them all in 67.

The step is T -> ((T xor M) * A) mod 2^m. It runs through all 2^m values in a single cycle when M is odd and
A = 3 (mod 4), for every m >= 2 (a lifting argument on the bits, as for T-functions); values >= n are skipped. It is
not a hash and not random: bit k of T depends only on bits <= k, and the low bits repeat with short periods. Use it
to order a coverage, never for anything that must be unpredictable or spread keys over buckets.
"""
from __future__ import annotations

M_SEED, A_SEED = 0x9E3779B97F4A7C15, 0xD1342543DE82EF95


def constants(m: int) -> tuple[int, int]:
    """(M, A) on m bits: M odd, A = 3 mod 4, so one single cycle."""
    mask = (1 << m) - 1
    return (M_SEED & mask) | 1, (A_SEED & mask & ~3) | 3


def walk(n: int, k: int, state: int = 0) -> tuple[list[int], int]:
    """The next k indices in [0, n) (all n at most) and the state to keep for the next call."""
    if n <= 0 or k <= 0:
        return [], state
    m = max(2, (n - 1).bit_length())
    M, A, V = *constants(m), 1 << m
    T, out = int(state) % V, []
    while len(out) < min(k, n):
        T = ((T ^ M) * A) % V
        if T < n:
            out.append(T)
    return out, T

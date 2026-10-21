# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Where a schematic's parts and wires may go (C375: a circuit written as a netlist was drawn with parts on top of
each other and a wire along the supply's line, as if joined to it).

The board keeps what is drawn — each part's body (a rectangle), the lines (a part's span or a wire, with its node),
the points of the nodes — and says whether a new part or wire would collide: a body over another, a line running
along a line of another node or of a part, a line through a body, a node's point on another node's line. Crossing at
right angles is allowed (the schematic's convention: no dot, no joint). Pure geometry: no drawing library."""
from __future__ import annotations

EPS = 1e-6
HALF = 0.35                                       # half the width of a two-terminal part's body
LEAD = 0.4                                        # a part's leads at each end: not its body
OFFSETS = (0,) + tuple(o for k in range(1, 11) for o in (3 * k, -3 * k))   # sideways, until there is room


def _same(a, b) -> bool:
    return abs(a[0] - b[0]) < EPS and abs(a[1] - b[1]) < EPS


def _overlap(lo1, hi1, lo2, hi2) -> float:
    return min(hi1, hi2) - max(lo1, lo2)


def collinear(s, t) -> bool:
    """Two axis-aligned lines lying on each other for more than a point."""
    (ax, ay, bx, by), (cx, cy, dx, dy) = s[:4], t[:4]
    if abs(ay - by) < EPS and abs(cy - dy) < EPS and abs(ay - cy) < EPS:
        return _overlap(min(ax, bx), max(ax, bx), min(cx, dx), max(cx, dx)) > EPS
    if abs(ax - bx) < EPS and abs(cx - dx) < EPS and abs(ax - cx) < EPS:
        return _overlap(min(ay, by), max(ay, by), min(cy, dy), max(cy, dy)) > EPS
    return False


def crosses(s, t) -> bool:
    """A vertical and a horizontal line meeting inside both (a crossing, not a touch at an end)."""
    v, h = (s, t) if abs(s[0] - s[2]) < EPS else (t, s)
    if abs(v[0] - v[2]) > EPS or abs(h[1] - h[3]) > EPS:
        return False
    return (min(h[0], h[2]) + EPS < v[0] < max(h[0], h[2]) - EPS
            and min(v[1], v[3]) + EPS < h[1] < max(v[1], v[3]) - EPS)


def on_line(p, s, ends: bool = True) -> bool:
    (ax, ay, bx, by) = s[:4]
    if not (min(ax, bx) - EPS <= p[0] <= max(ax, bx) + EPS and min(ay, by) - EPS <= p[1] <= max(ay, by) + EPS):
        return False
    if (abs(ax - bx) > EPS and abs(ay - by) > EPS) or not (abs(p[0] - ax) < EPS or abs(p[1] - ay) < EPS):
        return False
    return ends or not (_same(p, (ax, ay)) or _same(p, (bx, by)))


def through(s, r) -> bool:
    """A line entering a rectangle's inside (its border is not inside)."""
    (ax, ay, bx, by), (x0, y0, x1, y1) = s[:4], r[:4]
    x0, y0, x1, y1 = x0 + 0.05, y0 + 0.05, x1 - 0.05, y1 - 0.05
    if abs(ay - by) < EPS:
        return y0 < ay < y1 and _overlap(min(ax, bx), max(ax, bx), x0, x1) > EPS
    return x0 < ax < x1 and _overlap(min(ay, by), max(ay, by), y0, y1) > EPS


def body(a, b) -> tuple:
    """A two-terminal part's rectangle: its span without the leads, widened sideways (two parts meeting at a node
    touch by their leads, not their bodies)."""
    if abs(a[1] - b[1]) < EPS:
        x0, x1 = min(a[0], b[0]) + LEAD, max(a[0], b[0]) - LEAD
        return (x0, a[1] - HALF, max(x0, x1), a[1] + HALF)
    y0, y1 = min(a[1], b[1]) + LEAD, max(a[1], b[1]) - LEAD
    return (a[0] - HALF, y0, a[0] + HALF, max(y0, y1))


class Board:
    def __init__(self):
        self.lines: list[tuple] = []               # (x1, y1, x2, y2, node or None for a part's span)
        self.rects: list[tuple] = []               # (x0, y0, x1, y1)
        self.points: dict[tuple, str] = {}         # a node's drawn point -> its node

    def right(self) -> float:
        xs = [r[2] for r in self.rects] + [max(s[0], s[2]) for s in self.lines] + [p[0] for p in self.points]
        return max(xs) if xs else -3.0

    def wire_cost(self, path: list, net: str) -> int:
        """How many things a wire would run over: lines of others, bodies, other nodes' points; 0 = clean."""
        bad = 0
        for p, q in zip(path, path[1:]):
            s = (*p, *q)
            bad += sum(collinear(s, t) and t[4] != net for t in self.lines)
            bad += sum(through(s, r) for r in self.rects)
            bad += sum(n != net and on_line(pt, s) for pt, n in self.points.items())
        return bad

    def wire_ok(self, path: list, net: str) -> bool:
        return self.wire_cost(path, net) == 0

    def best(self, a, b, net: str) -> list:
        """The cleanest way from a to b (the shortest of the clean ones' order; the least bad when none is clean)."""
        ways = self.routes(a, b)
        costs = [self.wire_cost(w, net) for w in ways]
        return ways[costs.index(min(costs))]

    def part_cost(self, a, b, net_a: str, net_b: str) -> int:
        """How many things a two-terminal part from a to b would lie on; 0 = room for it."""
        s, r = (*a, *b), body(a, b)
        bad = sum(collinear(s, t) for t in self.lines)
        bad += sum(_overlap(r[0], r[2], q[0], q[2]) > EPS and _overlap(r[1], r[3], q[1], q[3]) > EPS for q in self.rects)
        bad += sum(through(t, r) for t in self.lines)
        for pt, n in self.points.items():
            bad += (_same(pt, a) and n != net_a) or (_same(pt, b) and n != net_b)
            bad += not _same(pt, a) and not _same(pt, b) and r[0] < pt[0] < r[2] and r[1] < pt[1] < r[3]
        return bad + sum(on_line(b, t) and t[4] != net_b for t in self.lines)

    def part_ok(self, a, b, net_a: str, net_b: str) -> bool:
        return self.part_cost(a, b, net_a, net_b) == 0

    def rect_ok(self, r: tuple, mine: set) -> bool:
        """A three-terminal part's box: on no other body, no line through it but its own nodes' at its border."""
        if any(_overlap(r[0], r[2], q[0], q[2]) > EPS and _overlap(r[1], r[3], q[1], q[3]) > EPS for q in self.rects):
            return False
        return not any(through(t, r) for t in self.lines) and not any(
            r[0] < pt[0] < r[2] and r[1] < pt[1] < r[3] for pt in self.points)

    def routes(self, a, b) -> list[list]:
        """Ways from a to b at right angles: straight, one corner, then around at growing distances."""
        out = [[a, b]] if abs(a[0] - b[0]) < EPS or abs(a[1] - b[1]) < EPS else []
        out += [[a, (b[0], a[1]), b], [a, (a[0], b[1]), b]]
        far = (1.5, -1.5, 3, -3, 4.5, -4.5, 6, -6)
        for o in far:
            out += [[a, (a[0], a[1] + o), (b[0], a[1] + o), b], [a, (a[0] + o, a[1]), (a[0] + o, b[1]), b]]
        for o in far[:4]:                          # out of a, across, and into b from its side
            for o2 in far[:4]:
                out += [[a, (a[0], a[1] + o), (b[0] + o2, a[1] + o), (b[0] + o2, b[1]), b],
                        [a, (a[0] + o, a[1]), (a[0] + o, b[1] + o2), (b[0], b[1] + o2), b]]
        return [[p for i, p in enumerate(r) if i == 0 or not _same(p, r[i - 1])] for r in out]

    def add_line(self, a, b, net) -> None:
        if not _same(a, b):
            self.lines.append((*a, *b, net))

    def add_part(self, a, b) -> None:
        self.add_line(a, b, None)
        self.rects.append(body(a, b))

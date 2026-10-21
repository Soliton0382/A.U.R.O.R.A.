# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The schematic of a circuit (schemdraw, no display): each part drawn from a point already drawn, in the order
written — a two-terminal part from its first node (a source from its − node) in its direction; a transistor or an
op-amp with the terminal that touches a drawn point there. A terminal that lands where its node is not yet drawn
marks the node there; one that lands elsewhere is joined to it by a wire at right angles. The ground is a symbol at
each terminal on it; a node where three or more meet has its dot; the named nodes (not n1, n2…) are written.
Nothing is drawn on anything else (circ_layout, C375): a part that would lie on another is moved sideways with a wire
to it, a wire takes the first way that runs along no line of another node."""
from __future__ import annotations

import os
import re
import tempfile

os.environ.setdefault("MPLCONFIGDIR", tempfile.mkdtemp(prefix="mpl-"))    # the sandbox's home is not writable
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import schemdraw  # noqa: E402
import schemdraw.elements as elm  # noqa: E402

import circ_layout  # noqa: E402
import circ_net  # noqa: E402

schemdraw.use("matplotlib")
TWO = {"resistor": elm.Resistor, "capacitor": elm.Capacitor, "polarized_capacitor": lambda: elm.Capacitor(polar=True),
       "inductor": elm.Inductor2, "diode": elm.Diode, "led": elm.LED, "zener": elm.Zener,
       "voltage_source": elm.SourceV, "sine_source": elm.SourceSin, "pulse_source": elm.SourcePulse,
       "battery": elm.Battery, "current_source": elm.SourceI, "wire": elm.Line}
# a three-terminal part: its drawing and its anchors in the SPICE order of its nodes
THREE = {"npn": (elm.BjtNpn, ("collector", "base", "emitter")), "pnp": (elm.BjtPnp, ("collector", "base", "emitter")),
         "nmos": (elm.NFet, ("drain", "gate", "source")), "pmos": (elm.PFet, ("drain", "gate", "source")),
         "opamp": (elm.Opamp, ("in2", "in1", "out"))}
ANGLE = {"right": 0, "up": 90, "left": 180, "down": 270}
UNIT = {"resistor": "Ω", "capacitor": "F", "polarized_capacitor": "F", "inductor": "H"}
PLAIN = re.compile(r"n?\d+")


def _value(p: dict) -> str:
    v = p["value"]
    m = re.fullmatch(r"([0-9.]+)(meg|[fpnumkgt])?", v, re.I)
    if p["kind"] in UNIT and m:                         # 4.7k -> 4.7 kΩ, 100n -> 100 nF
        prefix = {"meg": "M", "u": "µ", "k": "k"}.get((m.group(2) or "").lower(), m.group(2) or "")
        v = f"{m.group(1)} {prefix}{UNIT[p['kind']]}"
    return v


def _near(a, b) -> bool:
    return abs(a[0] - b[0]) < 1e-6 and abs(a[1] - b[1]) < 1e-6


STEP = {"right": (1, 0), "left": (-1, 0), "up": (0, 1), "down": (0, -1)}
BACK = {"right": "left", "left": "right", "up": "down", "down": "up"}


def _r(p) -> tuple:
    return (round(float(p[0]), 4), round(float(p[1]), 4))


def draw(parts: list[dict], title: str = "") -> schemdraw.Drawing:
    d = schemdraw.Drawing(show=False, fontsize=11, unit=3)
    board, net = circ_layout.Board(), circ_net.nets(parts)
    pos: dict[str, tuple] = {}                         # a name as written -> where it is drawn
    seen: dict[str, int] = {}                          # how many terminals touch it

    def wire(path, name) -> None:
        for a, b in zip(path, path[1:]):
            d.add(elm.Line().at(a).to(b))
            board.add_line(a, b, net[name])

    def route(a, b, name) -> None:                     # the first way that runs along nothing of another node
        wire(board.best(a, b, net[name]), name)

    def land(name: str, at, stub: bool = False) -> None:
        at = _r(at)
        seen[name] = seen.get(name, 0) + 1
        if circ_net.ground(name):
            if stub:                                   # a transistor's or op-amp's lead: the symbol off its body,
                def free(dx, dy):                      # where its lead and symbol cross nothing
                    end = (at[0] + dx, at[1] + dy)
                    lead, drop = (*at, *end), (end[0], end[1], end[0], end[1] - 0.9)
                    return (board.wire_ok([at, end], "0") and board.rect_ok(
                        (end[0] - 0.5, end[1] - 0.9, end[0] + 0.5, end[1] - 0.05), set())
                        and not any(circ_layout.crosses(lead, t) or circ_layout.crosses(drop, t) for t in board.lines))
                ways = [(0, -k) for k in (1, 2, 3)] + [(s * k, 0) for k in (1.5, 3) for s in (-1, 1)]
                dx, dy = next((w for w in ways if free(*w)), (0, -1))
                end = _r((at[0] + dx, at[1] + dy))
                d.add(elm.Line().at(at).to(end))
                board.add_line(at, end, "0")
                at = end
            d.add(elm.Ground().at(at).theta(0))
            board.rects.append((at[0] - 0.5, at[1] - 0.9, at[0] + 0.5, at[1] - 0.05))
            board.points.setdefault(at, "0")          # nothing of another node lands on a ground
        elif name not in pos:
            pos[name] = at
            board.points[at] = net[name]
        elif not _near(pos[name], at):
            route(at, pos[name], name)

    def labelled(e, p, text):
        return e.label(text, loc="bottom" if p.get("label_side") == "other" else "top") if text else e

    for p in parts:
        kind, nodes = p["kind"], p["nodes"]
        # the label in place of the id, the value always under it (C374: a label «R1» hid the 1.6 kΩ)
        text = p["label"] if kind == "wire" else "\n".join(x for x in (p["label"] or p["id"], _value(p)) if x)
        if kind in THREE:
            make, anchors = THREE[kind]
            theta = ANGLE[p["dir"] or "right"]         # never the way the part before went
            k = next((i for i, x in enumerate(nodes) if x in pos), None)
            home = pos[nodes[k]] if k is not None else (board.right() + 3, 0.0)
            anchor = anchors[k] if k is not None else anchors[0]

            def shape(flip: bool):
                e = make().anchor(anchor).theta(theta)
                return e.flip() if flip else e

            def terminals(at, flip=False):             # where its terminals fall, and the box it takes
                probe = schemdraw.Drawing(show=False)
                e = probe.add(shape(flip).at(at))
                b = e.get_bbox(transform=True)
                return {a: _r(e.absanchors[a]) for a in anchors}, (b.xmin, b.ymin, b.xmax, b.ymax)

            def others(ends) -> dict:                  # its other terminals as points (a wire must not run over them)
                return {ends[a]: ("0" if circ_net.ground(n) else net[n]) for n, a in zip(nodes, anchors)
                        if a != anchor or k is None}
            chosen = None
            flips = (False, True) if kind == "opamp" else (False,)    # an op-amp's inputs either way up
            for (dx, dy), flip in ((o, f) for o in ((0, 0), (3, 0), (-3, 0), (0, 3), (0, -3), (6, 0), (0, 6), (0, -6))
                                   for f in flips):
                at = (home[0] + dx, home[1] + dy)
                ends, box = terminals(at, flip)
                if not board.rect_ok(box, set()) or any(board.points.get(pt, n) != n for pt, n in others(ends).items()):
                    continue
                near = ends[anchor]                    # another terminal between its node and it: the wire would
                if any(min(home[0], near[0]) - 0.3 <= pt[0] <= max(home[0], near[0]) + 0.3   # pass it (C375)
                       and min(home[1], near[1]) - 0.3 <= pt[1] <= max(home[1], near[1]) + 0.3 for pt in others(ends)):
                    continue
                if (dx, dy) != (0, 0) and k is not None:
                    saved = dict(board.points)
                    board.points.update(others(ends))
                    board.rects.append(box)                # as it will be: the wire goes round it too
                    clean = board.wire_ok(board.best(home, at, net[nodes[k]]), net[nodes[k]])
                    board.rects.pop()
                    board.points = saved
                    if not clean:
                        continue
                chosen = (at, ends, box, flip)
                break
            at, ends, box, flip = chosen or ((home,) + terminals(home) + (False,))
            e = shape(flip).at(at)
            d.add(labelled(e, p, text))
            board.rects.append(box)
            for pt, n in others(ends).items():         # before the wire to it, so it goes round them
                board.points.setdefault(pt, n)
            for name, a in sorted(zip(nodes, anchors), key=lambda x: x[1] != anchor):   # its own node's wire first
                if k is not None and a == anchor and not _near(at, home):
                    route(home, at, name)              # moved: one wire from its node, no other
                    seen[name] = seen.get(name, 0) + 1
                elif k is not None and a == anchor:
                    seen[name] = seen.get(name, 0) + 1
                else:
                    land(name, ends[a], stub=True)
            continue
        first, second = (nodes[1], nodes[0]) if kind in circ_net.SOURCES else (nodes[0], nodes[1])
        if kind == "wire" and first in pos and second in pos:     # down/up first, or across first
            wire(board.best(pos[first], pos[second], net[first]), first)
            seen[first], seen[second] = seen.get(first, 0) + 1, seen.get(second, 0) + 1
            continue
        how = p["dir"] or ("up" if kind in circ_net.SOURCES else "right")
        a, b = pos.get(first), pos.get(second)
        e = TWO[kind]()
        if a and b and not _near(a, b) and (abs(a[0] - b[0]) < 1e-6 or abs(a[1] - b[1]) < 1e-6) \
                and board.part_ok(a, b, net[first], net[second]):
            e = e.endpoints(a, b)                       # both ends drawn, in line, room between: there
            d.add(labelled(e, p, text))
            board.add_part(a, b)
            land(first, a)
            land(second, b)
            continue
        reverse = first not in pos and second in pos   # drawn back from the other end, the same way round
        if reverse:
            how, first, second = BACK[how], second, first
        start = pos[first] if first in pos else (board.right() + 3, 0.0)
        step, side = STEP[how], STEP["up" if how in ("right", "left") else "right"]
        place, least = None, None
        target = net[second] if second not in pos else net[first] + "\0"    # a node drawn elsewhere: joined by a wire
        for o in circ_layout.OFFSETS:                  # in place, or moved sideways with a wire to it (C375)
            s = _r((start[0] + o * side[0], start[1] + o * side[1]))
            end = _r((s[0] + p["length"] * step[0], s[1] + p["length"] * step[1]))
            if second in pos and _near(pos[second], end):
                target = net[second]
            if kind == "wire":                         # a wire has no body: only what it runs over
                cost = board.wire_cost([s, end], net[first])
            else:
                cost = board.part_cost(s, end, net[first], "0" if circ_net.ground(second) else target)
            way = []
            if o and first in pos:                     # the wire to it, not along the part itself
                board.add_line(s, end, None)
                way = board.best(start, s, net[first])
                cost += board.wire_cost(way, net[first])
                board.lines.pop()
            cost += abs(o) / 100                       # the nearest of equals
            if least is None or cost < least:
                place, least = (s, end, way), cost
            if cost < 1:
                break
        s, end, way = place
        moved = bool(way)
        if moved:
            wire(way, first)
        e = getattr(e.at(s).reverse() if reverse else e.at(s), how)(p["length"])
        d.add(labelled(e, p, text))
        if kind == "wire":
            board.add_line(s, end, net[first])
        else:
            board.add_part(s, end)
        if moved:                                      # joined to its node by the wire just drawn
            seen[first] = seen.get(first, 0) + 1
        else:
            land(first, s)
        land(second, end)
    for name, at in pos.items():
        if seen.get(name, 0) >= 3:
            d.add(elm.Dot().at(at))
        if not PLAIN.fullmatch(name):
            d.add(elm.Label().at((at[0], at[1] + 0.35)).label(name, fontsize=9, color="#555555"))
    if title:
        b = d.get_bbox()
        d.add(elm.Label().at((b.xmin, b.ymax + 1.2)).label(title, fontsize=14, halign="left"))
    return d


def save(d: schemdraw.Drawing, folder, stem: str = "schematic") -> list[str]:
    out = []
    for ext, kw in (("svg", {}), ("pdf", {}), ("png", {"dpi": 200})):
        f = folder / f"{stem}.{ext}"
        d.save(str(f), **kw)
        out.append(f.name)
    return out

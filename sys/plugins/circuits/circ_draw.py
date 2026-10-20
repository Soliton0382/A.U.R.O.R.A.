# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The schematic of a circuit (schemdraw, no display): each part drawn from a point already drawn, in the order
written — a two-terminal part from its first node (a source from its − node) in its direction; a transistor or an
op-amp with the terminal that touches a drawn point there. A terminal that lands where its node is not yet drawn
marks the node there; one that lands elsewhere is joined to it by a wire at right angles. The ground is a symbol at
each terminal on it; a node where three or more meet has its dot; the named nodes (not n1, n2…) are written."""
from __future__ import annotations

import os
import re
import tempfile

os.environ.setdefault("MPLCONFIGDIR", tempfile.mkdtemp(prefix="mpl-"))    # the sandbox's home is not writable
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import schemdraw  # noqa: E402
import schemdraw.elements as elm  # noqa: E402

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


def draw(parts: list[dict], title: str = "") -> schemdraw.Drawing:
    d = schemdraw.Drawing(show=False, fontsize=11, unit=3)
    pos: dict[str, tuple] = {}                         # a name as written -> where it is drawn
    seen: dict[str, int] = {}                          # how many terminals touch it

    def fresh():
        if not pos and not d.elements:
            return (0.0, 0.0)
        b = d.get_bbox()
        return (b.xmax + 3, 0.0)

    def land(name: str, at, stub: bool = False) -> None:
        at = (float(at[0]), float(at[1]))
        seen[name] = seen.get(name, 0) + 1
        if circ_net.ground(name):
            if stub:                                   # a transistor's or op-amp's lead: the symbol off its body
                d.add(elm.Line().at(at).theta(270).length(1))
                at = (at[0], at[1] - 1)
            d.add(elm.Ground().at(at).theta(0))
        elif name not in pos:
            pos[name] = at
        elif not _near(pos[name], at):
            d.add(elm.Wire("-|").at(at).to(pos[name]))

    def labelled(e, p, text):
        return e.label(text, loc="bottom" if p.get("label_side") == "other" else "top") if text else e

    for p in parts:
        kind, nodes = p["kind"], p["nodes"]
        # the label in place of the id, the value always under it (C374: a label «R1» hid the 1.6 kΩ)
        text = p["label"] if kind == "wire" else "\n".join(x for x in (p["label"] or p["id"], _value(p)) if x)
        if kind in THREE:
            make, anchors = THREE[kind]
            e = make()
            k = next((i for i, x in enumerate(nodes) if x in pos), None)
            e = e.anchor(anchors[k]).at(pos[nodes[k]]) if k is not None else e.at(fresh())
            e = e.theta(ANGLE[p["dir"] or "right"])     # never the way the part before went
            d.add(labelled(e, p, text))
            for name, a in zip(nodes, anchors):
                land(name, e.absanchors[a], stub=True)
            continue
        first, second = (nodes[1], nodes[0]) if kind in circ_net.SOURCES else (nodes[0], nodes[1])
        if kind == "wire" and first in pos and second in pos:     # down/up first, or across first
            d.add(elm.Wire("|-" if p["dir"] in ("up", "down") else "-|").at(pos[first]).to(pos[second]))
            seen[first], seen[second] = seen.get(first, 0) + 1, seen.get(second, 0) + 1
            continue
        e = TWO[kind]()
        how = p["dir"] or ("up" if kind in circ_net.SOURCES else "right")
        a, b = pos.get(first), pos.get(second)
        if a and b and not _near(a, b) and (abs(a[0] - b[0]) < 1e-6 or abs(a[1] - b[1]) < 1e-6):
            e = e.endpoints(a, b)                       # both ends drawn, in line: between them
            d.add(labelled(e, p, text))
            land(first, a)
            land(second, b)
            continue
        if first in pos:
            e = e.at(pos[first])
        elif second in pos:                            # drawn back from the other end, the same way round
            e = e.at(pos[second]).reverse()
            how = {"right": "left", "left": "right", "up": "down", "down": "up"}[how]
            first, second = second, first
        else:
            e = e.at(fresh())
        e = getattr(e, how)(p["length"])
        d.add(labelled(e, p, text))
        land(first, e.absanchors["start"])
        land(second, e.absanchors["end"])
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

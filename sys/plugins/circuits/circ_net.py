# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A circuit as Aurora writes it, checked and turned into a SPICE netlist.

A part is {"id": "R1", "kind": "resistor", "value": "10k", "nodes": ["in", "out"], "dir": "right"}: its nodes in the
SPICE order (a source: + then −; a diode: anode then cathode; a transistor: collector base emitter / drain gate
source; an op-amp: + input, − input, output). "0" or "gnd" is the ground. A «wire» joins two names into one node (a
drawing needs two points of the same node). Values and models are SPICE's own words, checked character by character:
no line of the netlist can be written from a value (no control command reaches the simulator).
"""
from __future__ import annotations

import re

GROUND = {"0", "gnd", "GND", "ground"}
NODE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,30}|0")
ID = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,15}")
SAFE = re.compile(r"[A-Za-z0-9 .,+\-*/()=_{}^]{0,160}")
MAX_PARTS = 120

# kind: (SPICE letter, terminals, default model)
KINDS = {
    "resistor": ("R", 2, None), "capacitor": ("C", 2, None), "polarized_capacitor": ("C", 2, None),
    "inductor": ("L", 2, None),
    "diode": ("D", 2, "diode"), "led": ("D", 2, "led"), "zener": ("D", 2, "zener"),
    "voltage_source": ("V", 2, None), "sine_source": ("V", 2, None), "pulse_source": ("V", 2, None),
    "battery": ("V", 2, None), "current_source": ("I", 2, None),
    "npn": ("Q", 3, "npn"), "pnp": ("Q", 3, "pnp"), "nmos": ("M", 3, "nmos"), "pmos": ("M", 3, "pmos"),
    "opamp": ("E", 3, None), "wire": (None, 2, None),
}
SOURCES = {"voltage_source", "sine_source", "pulse_source", "battery", "current_source"}

# generic models, named as such (a datasheet's own goes in the part's "model")
MODELS = {
    "diode": "DGEN D(Is=2.52n Rs=0.568 N=1.752 Cjo=4p M=0.4 tt=20n)",          # small-signal silicon (1N4148-like)
    "led": "DLED D(Is=1e-20 N=1.6 Rs=3 Cjo=10p)",                              # red: about 1.75 V at 10 mA
    "zener": "DZEN D(Is=1e-14 Rs=5 BV=5.1 IBV=1m)",                           # 5.1 V
    "npn": "QNPN NPN(Is=6.734f Bf=416.4 Vaf=74.03 Br=0.7371 Rb=10 Cjc=3.638p Cje=4.493p Tf=301.2p Tr=239.5n)",
    "pnp": "QPNP PNP(Is=1.41f Bf=180.7 Vaf=18.7 Br=4.977 Rb=10 Cjc=4.5p Cje=8p Tf=397p Tr=33n)",
    "nmos": "MNGEN NMOS(Level=1 Vto=1 Kp=50m Lambda=0.01)",
    "pmos": "MPGEN PMOS(Level=1 Vto=-1 Kp=20m Lambda=0.01)",
}
OPAMP_GAIN = "1e5"                                     # an ideal op-amp: open-loop gain, no rails


class CircuitError(ValueError):
    pass


def _safe(text, what: str) -> str:
    s = str(text if text is not None else "").replace("µ", "u").strip()
    if not SAFE.fullmatch(s) or s.startswith("."):
        raise CircuitError(f"{what}: only letters, digits and + - * / ( ) = , . _ (one line, max 160): {s[:40]!r}")
    return s


def ground(name: str) -> bool:
    return name in GROUND


def check(parts: list[dict]) -> list[dict]:
    """The parts, each with id, kind, nodes (as written) and its value and model checked."""
    if not parts or len(parts) > MAX_PARTS:
        raise CircuitError(f"1 to {MAX_PARTS} parts")
    out, ids = [], set()
    for i, p in enumerate(parts):
        kind = str(p.get("kind", "")).lower()
        if kind not in KINDS:
            raise CircuitError(f"part {i + 1}: kind one of {', '.join(KINDS)}")
        letter, n, _ = KINDS[kind]
        nodes = p.get("nodes") or []
        if isinstance(nodes, dict):
            nodes = list(nodes.values())
        nodes = [str(x) for x in nodes]
        if len(nodes) != n or not all(NODE.fullmatch(x) for x in nodes):
            raise CircuitError(f"part {i + 1} ({kind}): {n} nodes, names of letters, digits and _ (or 0 for ground)")
        pid = str(p.get("id") or f"W{i + 1}")
        if not ID.fullmatch(pid) or pid.lower() in ids:
            raise CircuitError(f"part {i + 1}: an id of its own (letters and digits, e.g. R1), not {pid!r}")
        ids.add(pid.lower())
        value = _safe(p.get("value", ""), f"{pid} value")
        if letter in ("R", "C", "L", "V", "I") and not value:
            raise CircuitError(f"{pid}: a value (e.g. 10k, 100n, «DC 5», «SIN(0 1 1k)»)")
        model = _safe(p.get("model", ""), f"{pid} model")
        if model and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,20} (D|NPN|PNP|NMOS|PMOS)\(.*\)", model):
            raise CircuitError(f"{pid} model: «NAME TYPE(params)», e.g. «Q2N2222 NPN(Bf=200 Is=14f)»")
        d = str(p.get("dir", "")).lower()
        out.append({"id": pid, "kind": kind, "nodes": nodes, "value": value, "model": model,
                    "dir": d if d in ("right", "left", "up", "down") else "", "label": _safe(p.get("label", ""), f"{pid} label"),
                    "label_side": "other" if str(p.get("label_side", "")).lower() == "other" else "",
                    "length": max(1.0, min(12.0, float(p.get("length") or 3)))})
    return out


def nets(parts: list[dict]) -> dict[str, str]:
    """Every name to its node: the wires join names, the ground is 0; a node is called by its first name."""
    parent: dict[str, str] = {}

    def find(x):
        x = "0" if ground(x) else x
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for p in parts:
        for x in p["nodes"]:
            find(x)
        if p["kind"] == "wire":
            a, b = find(p["nodes"][0]), find(p["nodes"][1])
            if a != b:
                keep, other = (a, b) if a == "0" or b != "0" else (b, a)
                parent[other] = keep
    names = {x for p in parts for x in p["nodes"]} | set(parent)
    return {x: find(x) for x in names}


def spice_name(p: dict) -> str:
    """The part's name in the netlist: its id, after its SPICE letter when it does not start with it."""
    letter = KINDS[p["kind"]][0]
    return p["id"] if p["id"][0].upper() == letter else f"{letter}{p['id']}"


def netlist(parts: list[dict], title: str = "circuit") -> tuple[str, list[str]]:
    """The SPICE netlist (no analysis: the simulation adds its own) and the nodes, ground first."""
    net, lines, models = nets(parts), [f"* {_safe(title, 'title') or 'circuit'}"], {}
    for p in parts:
        letter, _, default = KINDS[p["kind"]]
        if letter is None:
            continue
        n = [net[x] for x in p["nodes"]]
        name = spice_name(p)
        mline = p["model"] or (MODELS[default] if default else "")
        mname = mline.split(" ", 1)[0] if mline else ""
        if mline:
            models[mname] = mline
        if letter in ("R", "C", "L", "V", "I"):
            lines.append(f"{name} {n[0]} {n[1]} {p['value']}")
        elif letter == "D":
            lines.append(f"{name} {n[0]} {n[1]} {mname}")
        elif letter == "Q":
            lines.append(f"{name} {n[0]} {n[1]} {n[2]} {mname}")
        elif letter == "M":
            lines.append(f"{name} {n[0]} {n[1]} {n[2]} {n[2]} {mname} {p['value']}".rstrip())
        elif letter == "E":                            # + input, − input, output: an ideal op-amp
            lines.append(f"{name} {n[2]} 0 {n[0]} {n[1]} {OPAMP_GAIN}")
    lines += [f".model {m}" for m in models.values()]
    if not any(v == "0" for v in net.values()):
        raise CircuitError("no ground: one node must be 0 (or gnd)")
    used = sorted(set(net.values()), key=lambda x: (x != "0", x))
    return "\n".join(lines) + "\n", used

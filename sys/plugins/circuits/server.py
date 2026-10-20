# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Electric circuits for Aurora's projects (owner, 2026-10-21: «oltre ai disegni cad, vorrei che aurora fosse capace di
disegnare progettare circuiti elettrici e circuiti integrati»; phases 1 and 2: schematics and simulation).

The circuit is a list of parts written by Aurora (circ_net: kinds, nodes, values, models). The plugin draws its
schematic (circ_draw: schemdraw, no display) and simulates it (circ_sim: ngspice in batch, its graphs). Everything
is written in the project: <project>/circuits/<name>/ — circuit.json, netlist.cir, schematic.svg/.pdf/.png, and the
simulation's simulation.cir, results.json, a CSV and a graph per analysis.
"""
from __future__ import annotations

import csv
import json
import re
import time
from pathlib import Path

from aurora import sys_config
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

import circ_net
import circ_sim

cfg = sys_config.get()
BASE = cfg.path("AURORA_PROJECTS_DIR")
HERE = Path(__file__).resolve().parent
server = MCPServer("circuits", version="1.0")
NAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")


def _folder(project: str, name: str) -> Path:
    if not NAME.fullmatch(project or "") or not NAME.fullmatch(name or ""):
        raise ToolError("project and circuit names: lowercase letters, digits, . _ - (max 64)")
    p = BASE / project
    if not p.is_dir():
        raise ToolError(f"no project {project}: create it first (projects.project_create)")
    return p / "circuits" / name


@server.tool()
def circuit_schematic(project: str, name: str, parts: list[dict], title: str = "") -> str:
    """Draw a circuit and write its SPICE netlist. parts, in drawing order (each from a node already drawn):
    {"id": "R1", "kind": "resistor", "value": "10k", "nodes": ["in", "out"], "dir": "right"} — kinds: resistor,
    capacitor, polarized_capacitor, inductor, diode, led, zener, voltage_source («DC 5», «DC 0 AC 1»), sine_source
    («SIN(0 1 1k)»), pulse_source («PULSE(0 5 0 1n 1n 1m 2m)»), battery, current_source, npn, pnp, nmos, pmos,
    opamp (ideal), wire. nodes in SPICE order: a source + then −; a diode anode then cathode; npn/pnp collector,
    base, emitter; nmos/pmos drain, gate, source; opamp + input, − input, output. "0" (or "gnd") is ground: a
    ground symbol is drawn at each terminal on it. dir: right, left, up, down (a source goes from − to +, up by
    default); length in units (3). A wire joins two names into one node (to draw a corner or close a loop).
    Draw it as by hand: the main path first, each branch from a node already drawn, corners with wires; a
    transistor or op-amp sits with its terminal on the node already drawn, the others a little off: go on from them.
    Optional: model «NAME TYPE(params)» for diodes and transistors (generic ones otherwise), label, label_side
    "other" (the label on the other side, when two parts sit close), a wire's dir (up/down: it goes that way first). Writes
    <project>/circuits/<name>/: schematic.svg/.pdf/.png, netlist.cir, circuit.json."""
    import circ_draw
    out = _folder(project, name)
    try:
        checked = circ_net.check(parts)
        net, nodes = circ_net.netlist(checked, title or name)
        t0 = time.time()
        d = circ_draw.draw(checked, title)
    except circ_net.CircuitError as e:
        raise ToolError(str(e)) from None
    out.mkdir(parents=True, exist_ok=True)
    files = circ_draw.save(d, out)
    (out / "netlist.cir").write_text(net, encoding="utf-8")
    (out / "circuit.json").write_text(json.dumps({"title": title or name, "parts": checked}, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    real = [p for p in checked if p["kind"] != "wire"]
    return (f"Circuit {name}: {len(real)} parts, nodes {', '.join(nodes)}; drawn in {time.time() - t0:.1f} s "
            f"({', '.join(files)} in {out}).\nNetlist:\n{net}")


@server.tool()
def circuit_simulate(project: str, name: str, analyses: list[dict] | None = None, probes: list[str] | None = None,
                     measures: list[dict] | None = None) -> str:
    """Simulate a circuit drawn with circuit_schematic (ngspice). analyses: [{"type": "op"} (every node's voltage,
    every source's current), {"type": "tran", "step": "10u", "stop": "5m"}, {"type": "ac", "points": 20 (per
    decade), "start": 1, "stop": "1meg"} (magnitude dB and phase °), {"type": "dc", "source": "V1", "start": 0,
    "stop": 5, "step": 0.1}]; probes: nodes («out») or a source's current («I(V1)»), at most 6 (the named nodes when
    none; a source's current is the one it gives out); measures: [{"name": "f3db", "analysis": "ac", "expr": "WHEN vdb(out)=-3.0103"}, {"name": "peak",
    "analysis": "tran", "expr": "MAX v(out)"}]. Writes results.json, a CSV and a graph (PNG) per analysis."""
    out = _folder(project, name)
    meta = out / "circuit.json"
    if not meta.is_file():
        raise ToolError(f"no circuit {name}: draw it first with circuit_schematic")
    parts = json.loads(meta.read_text(encoding="utf-8"))["parts"]
    try:
        exe, env = circ_sim.ngspice(HERE)
        net, nodes = circ_net.netlist(parts)
        vecs = circ_sim.vectors(list(probes or []), nodes, parts)
        sources = {p["id"].lower(): circ_net.spice_name(p) for p in parts if p["kind"] in circ_net.SOURCES}
        asked = [dict(a, source=sources.get(str(a.get("source", "")).lower(), a.get("source", "")))
                 for a in (analyses or [{"type": "op"}])]
        deck, plan = circ_sim.control(asked, vecs, list(measures or []))
        t0 = time.time()
        text = circ_sim.run(exe, out, net + deck, env=env)
    except (circ_sim.SimError, circ_net.CircuitError) as e:
        raise ToolError(str(e)) from None
    results, lines = {"probes": [v[0] for v in vecs], "analyses": []}, []
    for a, how in zip(plan, asked):
        a = {**a, "source": how.get("source", "")}
        if a["type"] == "op":
            values = circ_sim.op_values(text, list(measures or []))
            results["analyses"].append({"type": "op", "values": values})
            lines.append("op: " + ", ".join(f"{k} = {circ_sim.fmt(v)}" for k, v in values.items()))
            continue
        head, cols = circ_sim.read_table(out / a["file"])
        if not cols:
            raise ToolError(f"{a['type']}: ngspice wrote no data")
        x = cols[0]
        if a["type"] == "ac":
            mag = [(f"|{n}| dB", cols[1 + 2 * j]) for j, (n, _) in enumerate(vecs)]
            ph = [(f"∠{n} °", cols[2 + 2 * j]) for j, (n, _) in enumerate(vecs)]
            groups, series = [(mag, "dB"), (ph, "°")], mag + ph
        else:
            series = [(n, cols[1 + j]) for j, (n, _) in enumerate(vecs)]
            groups = [([s for s in series if s[0].startswith("V(")], "V"), ([s for s in series if s[0].startswith("I(")], "A")]
        with open(out / f"{a['type']}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([head[0]] + [n for n, _ in series])
            w.writerows(zip(x, *[y for _, y in series]))
        swept = f"{a.get('source', '')} (V or A)" if a["type"] == "dc" else ""
        circ_sim.plot(a["type"], x, groups, out / f"{a['type']}.png", swept)
        stats = {n: circ_sim.summary(x, y) for n, y in series}
        results["analyses"].append({"type": a["type"], "points": len(x), "from": x[0], "to": x[-1], "series": stats})
        lines.append(f"{a['type']} ({len(x)} points, {circ_sim.fmt(x[0])} → {circ_sim.fmt(x[-1])}): " + "; ".join(
            f"{n} min {circ_sim.fmt(s['min'])} max {circ_sim.fmt(s['max'])} last {circ_sim.fmt(s['last'])}"
            for n, s in stats.items()))
    results["measures"] = circ_sim.measured(text, list(measures or []))
    if results["measures"]:
        lines.append("measures: " + ", ".join(f"{k} = {circ_sim.fmt(v)}" for k, v in results["measures"].items()))
    (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    return f"Simulated {name} in {time.time() - t0:.1f} s ({out}):\n" + "\n".join(lines)


if __name__ == "__main__":
    server.run()

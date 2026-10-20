# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A circuit's simulation: ngspice in batch, its numbers read back, its graphs drawn.

The analyses are SPICE's: op (the operating point: every node's voltage and every source's current), tran (in
time), ac (in frequency: magnitude in dB and phase in degrees, two graphs — never one with two scales) and dc (a
source swept). The probes are nodes («out») or a source's current («I(V1)»); the measures are ngspice's own
(«WHEN v(out)=2.5», «MAX v(out)»). Every word is checked (circ_net.SAFE): no line of the control block comes from
a value. ngspice runs in the circuit's folder with a time limit; nothing else is written."""
from __future__ import annotations

import math
import re
import shutil
import subprocess
from pathlib import Path

import circ_net

ANALYSES = ("op", "tran", "ac", "dc")
NUM = re.compile(r"[0-9.]+(e[+-]?\d+)?(meg|[fpnumkgt])?", re.I)
PROBE = re.compile(r"(?:[vV]\(([A-Za-z0-9_]{1,31})\)|([A-Za-z0-9_]{1,31})|[iI]\(([A-Za-z][A-Za-z0-9_]{0,31})\))")
MEAS = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,20}")
# Okabe-Ito, in this order: told apart with every colour vision
COLOURS = ("#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9")
MAX_PROBES = 6


class SimError(ValueError):
    pass


def ngspice(here: Path) -> tuple[str, dict]:
    """The simulator and its environment: the plugin's own (unpacked from the system's package, plg_deps) or the
    system's."""
    import os
    own = here / ".bin" / "ngspice" / "usr" / "bin" / "ngspice"
    if own.is_file():
        return str(own), {**os.environ, "SPICE_LIB_DIR": str(here / ".bin" / "ngspice" / "usr" / "share" / "ngspice")}
    found = shutil.which("ngspice")
    if not found:
        raise SimError("ngspice is not there: install the plugin's programs (🔌 Plugin → circuits → Installa) or the "
                       "system's (brew install ngspice · Windows: ngspice.sourceforge.io)")
    return found, dict(os.environ)


def _num(x, what: str) -> str:
    s = str(x).strip()
    if not NUM.fullmatch(s):
        raise SimError(f"{what}: a number, with SPICE's suffixes if wanted (10u, 1meg): {s[:20]!r}")
    return s


def vectors(probes: list[str], nodes: list[str], parts: list[dict]) -> list[tuple[str, str]]:
    """(the probe as shown, the vector ngspice gives) — the named nodes when none are asked."""
    net = circ_net.nets(parts)
    names = {p["id"].lower(): circ_net.spice_name(p).lower() for p in parts if p["kind"] in circ_net.SOURCES}
    if not probes:
        probes = [n for n in nodes if n != "0" and not re.fullmatch(r"n?\d+", n)][:MAX_PROBES] or [n for n in nodes if n != "0"][:MAX_PROBES]
    out = []
    for p in probes[:MAX_PROBES]:
        m = PROBE.fullmatch(str(p).strip())
        if not m:
            raise SimError(f"probe: a node («out», «v(out)») or a source's current («I(V1)»): {str(p)[:30]!r}")
        node, source = m.group(1) or m.group(2), m.group(3)
        if source:
            if source.lower() not in names:
                raise SimError(f"probe I({source}): a current is read through a source (sources: {', '.join(names) or 'none'})")
            out.append((f"I({source})", f"-i({names[source.lower()]})"))     # what it gives, not SPICE's sign
        elif node in net:
            out.append((f"V({node})", f"v({net[node]})"))
        else:
            raise SimError(f"probe {node}: no such node (nodes: {', '.join(n for n in nodes if n != '0')})")
    return out


def control(analyses: list[dict], vecs: list[tuple[str, str]], measures: list[dict]) -> tuple[str, list[dict]]:
    """The control block, and what each analysis writes."""
    lines, plan = [".control", "set filetype=ascii", "set wr_singlescale", "set wr_vecnames"], []
    for k, a in enumerate(analyses or [{"type": "op"}]):
        t = str(a.get("type", "")).lower()
        if t not in ANALYSES:
            raise SimError(f"analysis: one of {', '.join(ANALYSES)}")
        f = f"a{k}_{t}.txt"
        if t == "op":
            lines += ["op", "print all"]
            plan.append({"type": t})
            continue
        if t == "tran":
            lines.append(f"tran {_num(a.get('step', '10u'), 'step')} {_num(a.get('stop', '10m'), 'stop')}")
        elif t == "ac":
            lines.append(f"ac dec {int(a.get('points', 20))} {_num(a.get('start', 1), 'start')} {_num(a.get('stop', '1meg'), 'stop')}")
        else:
            src = str(a.get("source", ""))
            if not re.fullmatch(r"[VvIi][A-Za-z0-9_]{0,15}", src):
                raise SimError("dc: the source swept, e.g. «V1»")
            lines.append(f"dc {src} {_num(a.get('start', 0), 'start')} {_num(a.get('stop', 5), 'stop')} {_num(a.get('step', 0.1), 'step')}")
        lines += [f"let s{j} = {v}" for j, (_, v) in enumerate(vecs)]
        if t == "ac":
            names = []
            for j in range(len(vecs)):
                lines += [f"let m{j} = db(s{j})", f"let p{j} = 180/pi*cph(s{j})"]
                names += [f"m{j}", f"p{j}"]
            lines.append(f"wrdata {f} {' '.join(names)}")
        else:
            lines.append(f"wrdata {f} {' '.join(f's{j}' for j in range(len(vecs)))}")
        for m in measures or []:
            if str(m.get("analysis", "")).lower() == t:
                if not MEAS.fullmatch(str(m.get("name", ""))):
                    raise SimError("measure: a name of letters and digits")
                lines.append(f"meas {t} {m['name']} {circ_net._safe(m.get('expr', ''), 'measure')}")
        plan.append({"type": t, "file": f})
    lines += ["quit", ".endc", ".end"]
    return "\n".join(lines) + "\n", plan


def run(exe: str, folder: Path, deck: str, timeout: int = 120, env: dict | None = None) -> str:
    (folder / "simulation.cir").write_text(deck, encoding="utf-8")
    try:
        r = subprocess.run([exe, "-b", "simulation.cir"], cwd=folder, capture_output=True, text=True, timeout=timeout,
                           env=env)
    except subprocess.TimeoutExpired:
        raise SimError(f"ngspice took more than {timeout} s: a shorter time or a larger step")
    text = (r.stdout or "") + "\n" + (r.stderr or "")
    bad = [ln for ln in text.splitlines() if re.search(r"\berror\b|singular|timestep too small|no such vector", ln, re.I)
           and "code model" not in ln and ".cm" not in ln]
    if r.returncode or bad:
        raise SimError("ngspice refused the circuit: " + " | ".join(bad or text.strip().splitlines()[-4:])[:800])
    return text


def read_table(f: Path) -> tuple[list[str], list[list[float]]]:
    rows = [ln.split() for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]
    head, data = rows[0], [[float(x) for x in r] for r in rows[1:]]
    return head, [list(c) for c in zip(*data)] if data else []


def op_values(text: str, measures: list[dict] | None = None) -> dict[str, float]:
    """The operating point's «name = value» lines (the measures, printed the same way, left out)."""
    skip, out = {str(m.get("name", "")).lower() for m in measures or []}, {}
    for m in re.finditer(r"^\s*([A-Za-z0-9_#()]+)\s*=\s*([-+0-9.eE]+)\s*$", text, re.M):
        if m.group(1).lower() not in skip:
            out[m.group(1)] = float(m.group(2))
    return out


def measured(text: str, measures: list[dict]) -> dict[str, float | None]:
    out = {}
    for m in measures or []:
        hit = re.search(rf"^\s*{re.escape(str(m['name']).lower())}\s*=\s*([-+0-9.eE]+)", text, re.M | re.I)
        out[str(m["name"])] = float(hit.group(1)) if hit else None
    return out


def plot(kind: str, x: list[float], groups: list[tuple[list[tuple[str, list[float]]], str]], f: Path,
         xlabel: str = "") -> None:
    """One graph per unit, stacked on the same x: volts and amperes, or dB and degrees — never two scales on one."""
    import matplotlib.pyplot as plt
    groups = [g for g in groups if g[0]]
    fig, axes = plt.subplots(len(groups), 1, figsize=(8, 3.2 * len(groups)), sharex=True, squeeze=False)
    sets = [(axes[i][0], ss, unit) for i, (ss, unit) in enumerate(groups)]
    for ax, ss, unit in sets:
        for (name, y), c in zip(ss, COLOURS):
            ax.plot(x, y, color=c, linewidth=2, label=name)
        ax.set_ylabel(unit)
        ax.grid(True, color="#dddddd", linewidth=0.8)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        if kind == "ac":
            ax.set_xscale("log")
        if len(ss) > 1:
            ax.legend(frameon=False, fontsize=9)
    axes[-1][0].set_xlabel(xlabel or {"tran": "time (s)", "ac": "frequency (Hz)", "dc": "swept source"}[kind])
    fig.tight_layout()
    fig.savefig(f, dpi=150)
    plt.close(fig)


def summary(x: list[float], y: list[float]) -> dict:
    return {"min": min(y), "max": max(y), "last": y[-1], "at_max": x[y.index(max(y))]} if y else {}


def fmt(v: float | None) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return f"{v:.4g}"

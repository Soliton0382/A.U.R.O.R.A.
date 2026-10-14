#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Explanatory figures for the README (not charts of a measure: drawings of how a part works), Italian and English,
static SVG with light and dark following the viewer, the palette of doc_charts.

    shadow   the shadow of an answer: every question a direction; an answered one casts a cone (cos ≥ 0.90), an inner
             one (cos ≥ 0.97) served without a second look; the re-ranker the second gate (M111, M113)

    python sys/core/script/doc_figures.py      # writes docs/img/{it,en}/shadow.svg
"""
from __future__ import annotations

import math
from pathlib import Path
from xml.sax.saxutils import escape

from doc_charts import OUT, STYLE

W, H = 720, 480
OX, OY, R = 60, 370, 240                  # the origin of the directions and the arc's radius
AXIS = 55                                  # the answered question's direction, degrees above the horizontal

TEXT = {
    "it": dict(
        title="L'ombra di una risposta", sub="ogni domanda è una direzione (un vettore unitario) · M111, M113",
        v="v: già risposta, verificata", outer="ombra: cos ≥ 0,90", inner="cos ≥ 0,97",
        pts=[("parafrasi stretta", "cos 0,99 → subito, 0,6 s"),
             ("parafrasi", "cos 0,93 → subito + ricontrollo"),
             ("stesso argomento, altra domanda", "cos 0,80 → pipeline completa"),
             ("domanda non collegata", "cos 0,50 → pipeline completa")],
        gate="Secondo cancello: il re-ranker deve dire che la vecchia RISPOSTA risponde alla nuova domanda (≥ 0,5).",
        res="Misurato: 18 parafrasi su 23 servite dall'ombra, 0 su 46 domande dello stesso argomento ma diverse.",
        time="51,2 s la pipeline · 0,6 s dall'ombra"),
    "en": dict(
        title="The shadow of an answer", sub="every question is a direction (a unit vector) · M111, M113",
        v="v: answered, verified", outer="shadow: cos ≥ 0.90", inner="cos ≥ 0.97",
        pts=[("close paraphrase", "cos 0.99 → at once, 0.6 s"),
             ("paraphrase", "cos 0.93 → at once + checked again"),
             ("same topic, another question", "cos 0.80 → full pipeline"),
             ("unrelated question", "cos 0.50 → full pipeline")],
        gate="Second gate: the re-ranker must find that the old ANSWER answers the new question (≥ 0.5).",
        res="Measured: 18 of 23 paraphrases served from the shadow, 0 of 46 same-topic different questions.",
        time="51.2 s the pipeline · 0.6 s from the shadow"),
}
EXTRA = """<style>
.cone{fill:#2a78d6;fill-opacity:.14}.core{fill:#1baf7a;fill-opacity:.22}.ray{stroke:#0b0b0b;stroke-width:2.5}
.edge{stroke:#2a78d6;stroke-width:1.5;stroke-dasharray:4 4}.arc{stroke:#bdbcb6;fill:none}.ptin{fill:#1baf7a}
.ptmid{fill:#2a78d6}.ptout{fill:#eb6834}.ring{stroke:#fcfcfb;stroke-width:2}
@media (prefers-color-scheme: dark){.cone{fill:#3987e5}.core{fill:#199e70}.ray{stroke:#ffffff}.edge{stroke:#3987e5}
.arc{stroke:#5c5b57}.ptin{fill:#199e70}.ptmid{fill:#3987e5}.ptout{fill:#d95926}.ring{stroke:#1a1a19}}
</style>"""


def _at(deg: float, r: float = R) -> tuple[float, float]:
    a = math.radians(deg)
    return OX + r * math.cos(a), OY - r * math.sin(a)


def _wedge(half: float, cls: str) -> str:
    (x1, y1), (x2, y2) = _at(AXIS - half), _at(AXIS + half)
    return f'<path class="{cls}" d="M{OX},{OY} L{x1:.1f},{y1:.1f} A{R},{R} 0 0 0 {x2:.1f},{y2:.1f} Z"/>'


def shadow(lang: str) -> str:
    t = TEXT[lang]
    outer, inner = math.degrees(math.acos(0.90)), math.degrees(math.acos(0.97))
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
           f'aria-label="{escape(t["title"])}">', STYLE, EXTRA, f'<rect class="bg" width="{W}" height="{H}" rx="8"/>',
           f'<text class="t1" x="24" y="34" font-size="20" font-weight="700">{escape(t["title"])}</text>',
           f'<text class="t2" x="24" y="56" font-size="13">{escape(t["sub"])}</text>']
    a0, a1 = _at(AXIS - 70), _at(AXIS + 38)
    out.append(f'<path class="arc" d="M{a0[0]:.1f},{a0[1]:.1f} A{R},{R} 0 0 0 {a1[0]:.1f},{a1[1]:.1f}"/>')
    out += [_wedge(outer, "cone"), _wedge(inner, "core")]
    for side in (-outer, outer):
        x, y = _at(AXIS + side)
        out.append(f'<line class="edge" x1="{OX}" y1="{OY}" x2="{x:.1f}" y2="{y:.1f}"/>')
    vx, vy = _at(AXIS, R + 6)
    out.append(f'<line class="ray" x1="{OX}" y1="{OY}" x2="{vx:.1f}" y2="{vy:.1f}"/>')
    lx, ly = _at(AXIS + outer, R + 16)
    out.append(f'<text class="t2" x="{lx:.1f}" y="{ly:.1f}" font-size="12" text-anchor="middle">{escape(t["outer"])}</text>')
    ix, iy = _at(AXIS, R * 0.55)
    out.append(f'<text class="t1" x="{ix + 14:.1f}" y="{iy:.1f}" font-size="12" font-weight="600">{escape(t["inner"])}</text>')
    tx, ty = _at(AXIS, R + 14)
    out.append(f'<text class="t1" x="{tx + 4:.1f}" y="{ty:.1f}" font-size="12" font-weight="600">'
               f'{escape(t["v"])}</text>')
    # the example questions, each at its measured cosine from v, on the arc
    for (name, what), cos, cls, k in zip(t["pts"], (0.99, 0.93, 0.80, 0.50), ("ptin", "ptmid", "ptout", "ptout"),
                                         range(4)):
        px, py = _at(AXIS - math.degrees(math.acos(cos)))
        out.append(f'<circle class="{cls} ring" cx="{px:.1f}" cy="{py:.1f}" r="7"/>')
        out.append(f'<text class="t1" x="{px + 12:.1f}" y="{py - 2:.1f}" font-size="12" font-weight="600">{k + 1}</text>')
        ly = 108 + k * 46
        out.append(f'<circle class="{cls}" cx="430" cy="{ly - 4}" r="6"/>')
        out.append(f'<text class="t1" x="444" y="{ly}" font-size="13" font-weight="600">{k + 1}. {escape(name)}</text>')
        out.append(f'<text class="t2" x="444" y="{ly + 17}" font-size="12">{escape(what)}</text>')
    for i, line in enumerate((t["gate"], t["res"], t["time"])):
        out.append(f'<text class="t2" x="24" y="{H - 56 + i * 18}" font-size="12">{escape(line)}</text>')
    out.append("</svg>")
    return "\n".join(out)


def main() -> int:
    for lang in TEXT:
        (OUT / lang).mkdir(parents=True, exist_ok=True)
        (OUT / lang / "shadow.svg").write_text(shadow(lang), encoding="utf-8")
    print(f"{len(TEXT)} figures in {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Benchmark charts for the README and the GitHub page: static SVG, Italian and English.

Every value comes from a measurement in docs/MEASUREMENTS.md, named in the chart's subtitle; the
tables there are the charts' table view. Static on purpose (GitHub shows SVG as images, without
scripts), so every bar carries its value as a label. Light and dark follow the viewer's setting
(prefers-color-scheme inside the SVG). Palette: the validated reference instance, slots 1-3.

    python sys/core/script/doc_charts.py      # writes docs/img/{it,en}/*.svg
"""
from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parents[3] / "docs" / "img"
W, H = 720, 380
PAD_L, PAD_R, PAD_T, PAD_B = 56, 24, 104, 64

STYLE = """<style>
.bg{fill:#fcfcfb}.t1{fill:#0b0b0b}.t2{fill:#52514e}.grid{stroke:#e4e3df}.axis{stroke:#bdbcb6}
.s1{fill:#2a78d6}.s2{fill:#eb6834}.s3{fill:#1baf7a}.ref{stroke:#52514e}
@media (prefers-color-scheme: dark){.bg{fill:#1a1a19}.t1{fill:#ffffff}.t2{fill:#c3c2b7}.grid{stroke:#383835}
.axis{stroke:#5c5b57}.s1{fill:#3987e5}.s2{fill:#d95926}.s3{fill:#199e70}.ref{stroke:#c3c2b7}}
text{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
</style>"""


def bar(x: float, y: float, w: float, h: float, cls: str) -> str:
    """A bar anchored to the baseline with a 4 px rounded data end."""
    r = min(4.0, w / 2, h)
    return (f'<path class="{cls}" d="M{x:.1f},{y + h:.1f} V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} '
            f'H{x + w - r:.1f} Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} V{y + h:.1f} Z"/>')


def chart(name: str, title: str, subtitle: str, cats: list[str], series: list[tuple[str, list[float]]],
          ymax: float, fmt, note: str = "", ref: tuple[float, str] | None = None) -> str:
    pw, ph = W - PAD_L - PAD_R, H - PAD_T - PAD_B
    y0 = PAD_T + ph
    sy = lambda v: y0 - v / ymax * ph
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
             f'aria-labelledby="t d">', f"<title id=\"t\">{escape(title)}</title>",
             f"<desc id=\"d\">{escape(subtitle)}. " + "; ".join(
                 f"{s}: " + ", ".join(f"{c} {fmt(v)}" for c, v in zip(cats, vals)) for s, vals in series) + "</desc>",
             STYLE, f'<rect class="bg" width="{W}" height="{H}" rx="8"/>',
             f'<text class="t1" x="{PAD_L}" y="30" font-size="17" font-weight="600">{escape(title)}</text>',
             f'<text class="t2" x="{PAD_L}" y="52" font-size="12.5">{escape(subtitle)}</text>']
    if len(series) > 1:                                   # legend for two or more series
        lx = PAD_L
        for i, (s, _) in enumerate(series, 1):
            parts.append(f'<rect class="s{i}" x="{lx}" y="68" width="12" height="12" rx="3"/>'
                         f'<text class="t2" x="{lx + 18}" y="78.5" font-size="12.5">{escape(s)}</text>')
            lx += 30 + 7.0 * len(s)
    for k in range(5):                                    # recessive grid, one axis
        v = ymax * k / 4
        parts.append(f'<line class="grid" x1="{PAD_L}" x2="{W - PAD_R}" y1="{sy(v):.1f}" y2="{sy(v):.1f}" stroke-width="1"/>'
                     f'<text class="t2" x="{PAD_L - 8}" y="{sy(v) + 4:.1f}" font-size="11" text-anchor="end">{fmt(v)}</text>')
    group = pw / len(cats)
    n = len(series)
    bw = min(64.0, (group * 0.62 - 2 * (n - 1)) / n)
    for ci, c in enumerate(cats):
        gx = PAD_L + ci * group + (group - (n * bw + 2 * (n - 1))) / 2
        for si, (_, vals) in enumerate(series, 1):
            v = vals[ci]
            x = gx + (si - 1) * (bw + 2)
            if v > 0:
                parts.append(bar(x, sy(v), bw, y0 - sy(v), f"s{si}"))
            parts.append(f'<text class="t1" x="{x + bw / 2:.1f}" y="{sy(v) - 6:.1f}" font-size="12" '
                         f'text-anchor="middle" font-weight="600">{fmt(v)}</text>')
        for li, line in enumerate(c.split("\n")):
            parts.append(f'<text class="t2" x="{PAD_L + ci * group + group / 2:.1f}" y="{y0 + 18 + 14 * li:.1f}" '
                         f'font-size="12" text-anchor="middle">{escape(line)}</text>')
    parts.append(f'<line class="axis" x1="{PAD_L}" x2="{W - PAD_R}" y1="{y0}" y2="{y0}" stroke-width="1"/>')
    if ref:
        v, label = ref
        parts.append(f'<line class="ref" x1="{PAD_L}" x2="{W - PAD_R}" y1="{sy(v):.1f}" y2="{sy(v):.1f}" '
                     f'stroke-width="1.5" stroke-dasharray="5 4"/>'
                     f'<line class="ref" x1="{PAD_L}" x2="{PAD_L + 22}" y1="{H - 16}" y2="{H - 16}" stroke-width="1.5" stroke-dasharray="5 4"/>'
                     f'<text class="t2" x="{PAD_L + 28}" y="{H - 12}" font-size="11">{escape(label)}</text>')
    if note:
        parts.append(f'<text class="t2" x="{PAD_L}" y="{H - 12}" font-size="11">{escape(note)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def _dec(v: float, lang: str) -> str:
    t = f"{v:.0f}" if v == int(v) else f"{v:.1f}"
    return t.replace(".", ",") if lang == "it" else t


pct = {lang: (lambda v, lang=lang: _dec(v, lang) + "%") for lang in ("it", "en")}
num = {lang: (lambda v: f"{v:.0f}") for lang in ("it", "en")}
sec = {lang: (lambda v, lang=lang: _dec(round(v, 1), lang) + " s" if v else "0") for lang in ("it", "en")}

CHARTS = {
    "retrieval": {
        "it": dict(title="Trovare il documento giusto", subtitle="108 domande parafrasate · M25 (pool) e M31 (vault intero)",
                   cats=["al 1° posto", "tra i primi 5", "tra i 12 dati\nalla sintesi"],
                   series=[("pool 3.108 passaggi", [94.4, 95.4, 96.3]), ("vault intero, 344.499 solitoni", [74.2, 87.6, 92.1])],
                   ymax=100, fmt=pct["it"], ref=(68.5, "installazione precedente, archivio intero (M17): 68,5% al 1° posto")),
        "en": dict(title="Finding the right document", subtitle="108 paraphrased questions · M25 (pool) and M31 (whole vault)",
                   cats=["ranked 1st", "in the top 5", "among the 12 given\nto synthesis"],
                   series=[("3,108-passage pool", [94.4, 95.4, 96.3]), ("whole vault, 344,499 solitons", [74.2, 87.6, 92.1])],
                   ymax=100, fmt=pct["en"], ref=(68.5, "previous installation, whole store (M17): 68.5% ranked 1st")),
    },
    "verification": {
        "it": dict(title="Verifica delle frasi: chi sbaglia e come", subtitle="32 frasi reali giudicate da Claude (opus) · M32",
                   cats=["passaggi citati\n(prima)", "citati,\nfrase in inglese", "tutti i passaggi\n(ora)",
                         "tutti,\nin inglese", "tutti,\nitaliano o inglese"],
                   series=[("frasi corrette scartate (su 18)", [4, 2, 6, 2, 1]), ("frasi non supportate tenute (su 14)", [8, 12, 0, 4, 4])],
                   ymax=16, fmt=num["it"], note="Scelta: «tutti i passaggi», l'unica regola che non lascia passare frasi non supportate."),
        "en": dict(title="Sentence verification: who errs, and how", subtitle="32 real sentences judged by Claude (opus) · M32",
                   cats=["cited passages\n(before)", "cited,\nEnglish sentence", "all passages\n(now)",
                         "all,\nin English", "all,\nItalian or English"],
                   series=[("correct sentences dropped (of 18)", [4, 2, 6, 2, 1]), ("unsupported sentences kept (of 14)", [8, 12, 0, 4, 4])],
                   ymax=16, fmt=num["en"], note="Chosen: “all passages”, the only rule that lets no unsupported sentence through."),
    },
    "startup": {
        "it": dict(title="Primo avvio del ragionatore dopo un cambio di binario", subtitle="llama.cpp 7fee178 su 2 × RTX 5060 Ti · M23, M34",
                   cats=["nvcc 12.4\n(kernel tradotti al volo)", "nvcc 13.4\n(sm_120 nativo)"],
                   series=[("secondi", [15.8, 3.6])], ymax=20, fmt=sec["it"],
                   note="Generazione: 110,6 → 112,4 token/s (M28, M34). Misure: M23 primo caricamento, M34 avvio fino a /health."),
        "en": dict(title="First reasoner start after a binary change", subtitle="llama.cpp 7fee178 on 2 × RTX 5060 Ti · M23, M34",
                   cats=["nvcc 12.4\n(kernels JIT-translated)", "nvcc 13.4\n(native sm_120)"],
                   series=[("seconds", [15.8, 3.6])], ymax=20, fmt=sec["en"],
                   note="Generation: 110.6 → 112.4 tokens/s (M28, M34). Measures: M23 first load, M34 start to /health."),
    },
    "images": {
        "it": dict(title="Dipingere un sogno: secondi per immagine 1024×1024", subtitle="mediana a caldo, offload su CPU, una GPU da 16 GB · M27",
                   cats=["SDXL-Lightning\n(scelto)", "FLUX.2 klein 4B", "Z-Image-Turbo"],
                   series=[("secondi", [2.91, 10.34, 21.38])], ymax=24, fmt=sec["it"],
                   note="Più lo swap del ragionatore: un sogno dipinto richiede ~20 s in tutto (M27)."),
        "en": dict(title="Painting a dream: seconds per 1024×1024 image", subtitle="warm median, CPU offload, one 16 GB GPU · M27",
                   cats=["SDXL-Lightning\n(chosen)", "FLUX.2 klein 4B", "Z-Image-Turbo"],
                   series=[("seconds", [2.91, 10.34, 21.38])], ymax=24, fmt=sec["en"],
                   note="Plus swapping the reasoner out and back: ~20 s per painted dream in all (M27)."),
    },
    "originals": {
        "it": dict(title="Trovare il paper originale, non i derivati", subtitle="12 metodi noti (RoPE, Transformer, Adam, …) · M33",
                   cats=["query per parole chiave\n(prima)", "+ titolo dell'originale\n(ora)"],
                   series=[("originali raggiungibili su 12", [4, 8])], ymax=12, fmt=num["it"],
                   note="Il titolo proposto dal modello è accettato solo se arXiv ha lo stesso titolo: 0 import sbagliati."),
        "en": dict(title="Finding the original paper, not its derivatives", subtitle="12 named methods (RoPE, Transformer, Adam, …) · M33",
                   cats=["keyword queries\n(before)", "+ title of the original\n(now)"],
                   series=[("originals reachable, of 12", [4, 8])], ymax=12, fmt=num["en"],
                   note="The model's proposed title is accepted only if arXiv has the same title: 0 wrong imports."),
    },
}


def main() -> int:
    for lang in ("it", "en"):
        (OUT / lang).mkdir(parents=True, exist_ok=True)
        for name, spec in CHARTS.items():
            (OUT / lang / f"{name}.svg").write_text(chart(name, **spec[lang]), encoding="utf-8")
    print(f"{len(CHARTS) * 2} charts in {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

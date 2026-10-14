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


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """The 95% interval of a share k/n (Wilson), in percent: what one run of n questions can tell."""
    if not n:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return round(100 * max(0.0, c - h), 1), round(100 * min(1.0, c + h), 1)


def chart(name: str, title: str, subtitle: str, cats: list[str], series: list[tuple[str, list[float]]],
          ymax: float, fmt, note: str = "", ref: tuple[float, str] | None = None,
          errors: list[list[tuple[float, float]]] | None = None) -> str:
    """errors: per series, per category, (low, high) — a 95% interval drawn as a whisker over the bar."""
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
            top = v
            if errors:                                    # the 95% interval: a whisker with caps
                lo, hi = errors[si - 1][ci]
                cx, cap = x + bw / 2, min(6.0, bw / 3)
                parts.append(f'<line class="ref" x1="{cx:.1f}" x2="{cx:.1f}" y1="{sy(lo):.1f}" y2="{sy(hi):.1f}" stroke-width="1.5"/>'
                             f'<line class="ref" x1="{cx - cap:.1f}" x2="{cx + cap:.1f}" y1="{sy(hi):.1f}" y2="{sy(hi):.1f}" stroke-width="1.5"/>'
                             f'<line class="ref" x1="{cx - cap:.1f}" x2="{cx + cap:.1f}" y1="{sy(lo):.1f}" y2="{sy(lo):.1f}" stroke-width="1.5"/>')
                top = max(v, hi)
            fs = 12 if bw >= 30 else 9.5                  # narrow bars (8 groups × 2): the labels must not touch
            parts.append(f'<text class="t1" x="{x + bw / 2:.1f}" y="{sy(top) - 6:.1f}" font-size="{fs}" '
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
score = {lang: (lambda v, lang=lang: (f"{v:.2f}".rstrip("0").rstrip(".")).replace(".", "," if lang == "it" else ".")) for lang in ("it", "en")}
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
    "users": {
        "it": dict(title="Più persone insieme: attesa dell'ultima risposta", subtitle="domande da 4 client in parallelo, pipeline completa · M99, M102",
                   cats=["2 insieme", "4 insieme"],
                   series=[("1 slot del ragionatore", [70.2, 190.1]), ("2 slot (scelto)", [53.7, 145.3])], ymax=200, fmt=sec["it"],
                   note="Con 2 slot: 8 persone insieme tutte servite, l'ultima dopo 231,5 s; +482 MiB di memoria GPU."),
        "en": dict(title="Several people at once: wait for the last answer", subtitle="questions from parallel clients, full pipeline · M99, M102",
                   cats=["2 at once", "4 at once"],
                   series=[("1 reasoner slot", [70.2, 190.1]), ("2 slots (chosen)", [53.7, 145.3])], ymax=200, fmt=sec["en"],
                   note="With 2 slots: 8 people at once all served, the last after 231.5 s; +482 MiB of GPU memory."),
    },
    "answers": {
        "it": dict(title="Le domande che la gente fa davvero", subtitle="50 domande reali (MKQA, da Google), risposta controllata · M130",
                   cats=["vault\n(prima)", "auto\n(ora)"],
                   series=[("giuste", [16, 70]), ("sbagliate", [2, 28]), ("astenute", [82, 2])], ymax=100, fmt=pct["it"],
                   note="Delle «sbagliate» di auto ~8 su 14 sono giuste ma non riconosciute o fatti cambiati dal 2018."),
        "en": dict(title="The questions people really ask", subtitle="50 real questions (MKQA, from Google), answer checked · M130",
                   cats=["vault\n(before)", "auto\n(now)"],
                   series=[("right", [16, 70]), ("wrong", [2, 28]), ("abstained", [82, 2])], ymax=100, fmt=pct["en"],
                   note="Of auto's «wrong», ~8 of 14 are right answers the score misses or facts changed since 2018."),
    },
    "speed": {
        "it": dict(title="Quanto aspetti una risposta", subtitle="stesse 50 domande · M130",
                   cats=["vault\n(prima, media)", "auto\n(media)", "auto\n(mediana)", "dalla cache\n(domanda ripetuta)"],
                   series=[("secondi", [17.9, 7.2, 3.95, 0.04])], ymax=20, fmt=sec["it"],
                   note="Un caso con più problemi va nel percorso profondo: ~100 s, ogni frase verificata sulle norme."),
        "en": dict(title="How long you wait for an answer", subtitle="the same 50 questions · M130",
                   cats=["vault\n(before, mean)", "auto\n(mean)", "auto\n(median)", "from the cache\n(a repeated question)"],
                   series=[("seconds", [17.9, 7.2, 3.95, 0.04])], ymax=20, fmt=sec["en"],
                   note="A case with several problems takes the deep path: ~100 s, every sentence checked on the law."),
    },
    "honesty": {
        "it": dict(title="Premesse false: le corregge o ci costruisce sopra?", subtitle="6 premesse false, 2 vere, giudice Claude · M117, M130",
                   cats=["vault (prima)", "auto (ora)"],
                   series=[("premesse false corrette (su 6)", [2, 6]), ("premesse vere rispettate (su 2)", [2, 2])],
                   ymax=6, fmt=num["it"], note="Prima si asteneva per mancanza di fonti; ora dice che la premessa è sbagliata e perché."),
        "en": dict(title="False premises: corrected or built upon?", subtitle="6 false premises, 2 true, Claude as judge · M117, M130",
                   cats=["vault (before)", "auto (now)"],
                   series=[("false premises corrected (of 6)", [2, 6]), ("true premises respected (of 2)", [2, 2])],
                   ymax=6, fmt=num["en"], note="Before, it declined for lack of sources; now it says the premise is wrong and why."),
    },
    "domains": {
        "it": dict(title="Ricerca nel vault: domanda diretta o raccontata", subtitle="passaggio giusto tra i 12 · 6 per dominio · M129",
                   cats=["legge", "fisica", "matem.", "filosofia", "società", "medicina", "storia", "informat."],
                   series=[("domanda diretta", [83, 83, 83, 100, 100, 50, 83, 100]),
                           ("raccontata a parole", [17, 33, 17, 33, 67, 50, 50, 0])], ymax=100, fmt=pct["it"],
                   note="Il limite sono le parole, non la materia: per questo un fatto si cerca sul web e un caso si divide."),
        "en": dict(title="Vault search: a direct question or a story", subtitle="the right passage in the top 12 · 6 per domain · M129",
                   cats=["law", "physics", "maths", "philos.", "society", "medicine", "history", "comp. sci."],
                   series=[("direct question", [83, 83, 83, 100, 100, 50, 83, 100]),
                           ("told in plain words", [17, 33, 17, 33, 67, 50, 50, 0])], ymax=100, fmt=pct["en"],
                   note="The limit is the words, not the subject: so a fact is searched on the web and a case is split."),
    },
    "gate": {
        "it": dict(title="Qualità delle risposte con modelli diversi al cancello", subtitle="30 domande, giudice Claude opus, stesso vault · M98",
                   cats=["locale\n(Qwen 35B, scelto)", "Claude Sonnet", "Claude Opus"],
                   series=[("voto medio su 10", [6.90, 6.87, 6.87])], ymax=10, fmt=score["it"],
                   note="Differenze dentro il rumore (±0,75): il cancello non è il limite, resta locale."),
        "en": dict(title="Answer quality with different models at the gate", subtitle="30 questions, Claude opus as judge, same vault · M98",
                   cats=["local\n(Qwen 35B, chosen)", "Claude Sonnet", "Claude Opus"],
                   series=[("mean score of 10", [6.90, 6.87, 6.87])], ymax=10, fmt=score["en"],
                   note="Differences within the noise (±0.75): the gate is not the limit, it stays local."),
    },
    "hybrid": {
        "it": dict(title="Ricerca ibrida: le parole della domanda accanto ai vettori", subtitle="93 domande con la fonte nel vault · M200",
                   cats=["fonte giusta\nal 1° posto", "tra le 12\nlette dalla chat", "tra le prime 30"],
                   series=[("solo vettori", [62, 81, 84]), ("ibrida (BM25 + vettori)", [63, 82, 85])], ymax=93, fmt=num["it"],
                   note="Le risposte dalla fonte giusta restano 72 su 93: la ricerca guadagna, la lettura non ancora."),
        "en": dict(title="Hybrid search: the question's words beside the vectors", subtitle="93 questions with their source in the vault · M200",
                   cats=["right source\nranked 1st", "among the 12\nthe chat reads", "in the top 30"],
                   series=[("vectors only", [62, 81, 84]), ("hybrid (BM25 + vectors)", [63, 82, 85])], ymax=93, fmt=num["en"],
                   note="Answers from the right source stay 72 of 93: the search gains, the reading not yet."),
    },
    "router": {
        "it": dict(title="Lo smistamento: una parola o un solo token", subtitle="168 messaggi con riferimento, secondi per messaggio · M199",
                   cats=["una parola scritta\n(prima)", "un token, dalle\nprobabilità (ora)", "ragionando\nogni volta"],
                   series=[("secondi", [0.62, 0.32, 7.88])], ymax=8, fmt=sec["it"],
                   note="Giusti: 162, 162 e 154 su 168. Ragionare peggiora e rallenta: non adottato."),
        "en": dict(title="Routing: a written word or a single token", subtitle="168 messages with a reference, seconds a message · M199",
                   cats=["a written word\n(before)", "one token, from its\nprobabilities (now)", "reasoning\nevery time"],
                   series=[("seconds", [0.62, 0.32, 7.88])], ymax=8, fmt=sec["en"],
                   note="Right: 162, 162 and 154 of 168. Reasoning is worse and slower: not adopted."),
    },
    "whisper": {
        "it": dict(title="Dettatura: secondi per frase", subtitle="20 frasi italiane, Whisper large-v3-turbo, stesse parole · M204",
                   cats=["CPU (prima)", "GPU (ora, se ha 3 GB liberi)"],
                   series=[("mediana", [5.58, 0.14]), ("la più lenta", [8.55, 0.20])], ymax=9, fmt=sec["it"],
                   note="Trascrizioni identiche; 6 parole sbagliate su 168, più 11 numeri scritti in cifre."),
        "en": dict(title="Dictation: seconds a sentence", subtitle="20 Italian sentences, Whisper large-v3-turbo, the same words · M204",
                   cats=["CPU (before)", "GPU (now, when it has 3 GB free)"],
                   series=[("median", [5.58, 0.14]), ("slowest", [8.55, 0.20])], ymax=9, fmt=sec["en"],
                   note="Identical transcripts; 6 words wrong of 168, plus 11 numbers written as digits."),
    },
    "vault": {
        "it": dict(title="Il vault riallineato: una copia, nel dominio giusto", subtitle="97 domande, fonte giusta letta · M193, M198",
                   cats=["risposta dalla\nfonte giusta", "fonte assente\ndal vault"],
                   series=[("prima (13 ott, 16:01)", [66, 8]), ("dopo il riallineamento", [72, 4])], ymax=97, fmt=num["it"],
                   note="Wikipedia: 4.545 voci, 0 copie; arXiv: 6.700 paper, 6.264 in HTML (formule leggibili)."),
        "en": dict(title="The vault realigned: one copy, in the right domain", subtitle="97 questions, right source read · M193, M198",
                   cats=["answer from the\nright source", "source missing\nfrom the vault"],
                   series=[("before (13 Oct, 16:01)", [66, 8]), ("after the realignment", [72, 4])], ymax=97, fmt=num["en"],
                   note="Wikipedia: 4,545 articles, 0 copies; arXiv: 6,700 papers, 6,264 as HTML (readable formulas)."),
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

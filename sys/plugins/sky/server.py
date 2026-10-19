# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "sky" (ROADMAP N30): the whole deep sky to choose from for the person's equipment — tonight's targets
ranked (ast_skyplan), one object's night, the catalogue searched. Network: the public catalogues once (OpenNGC,
VizieR) and the sky's forecast (Open-Meteo, 7Timer!) with the site rounded to a tenth of a degree. The equipment is
read from the astro folder (the «astro» plugin's, which stays offline)."""
from __future__ import annotations

from aurora import ast_catalog, ast_donut, ast_inventory, ast_rotate, ast_seqwrite, ast_skyplan, sys_config
from mcp.server.mcpserver import MCPServer

server = MCPServer("sky", version="1.0")
KINDS = ("", "narrowband", "broadband", "hdr", "galaxy")


@server.tool()
def sky_tonight(date: str = "", kind: str = "", min_alt: float = 30, limit: int = 10) -> str:
    """Cosa riprendere stanotte (o la notte di date, AAAA-MM-GG) con l'attrezzatura della persona: buio astronomico,
    Luna, nuvole/seeing/trasparenza previsti, e gli oggetti di tutto il catalogo (NGC, IC, Messier, Sharpless, Barnard,
    Lynds) in ordine di ore riprendibili, con altezza massima, distanza dalla Luna, quanto riempiono il campo (o il
    mosaico) e le impostazioni della camera. kind: narrowband, broadband, hdr, galaxy o vuoto; min_alt in gradi."""
    if kind not in KINDS:
        return f"kind: uno di {', '.join(k for k in KINDS if k)}, o vuoto"
    cfg = sys_config.get()
    return ast_skyplan.text(ast_skyplan.tonight(cfg, date.strip(), float(min_alt), kind, int(limit)))


@server.tool()
def sky_target(object: str, date: str = "", min_alt: float = 30) -> str:
    """Un oggetto preciso (M31, NGC 7000, Sh2-129, IC 1805, o un nome comune come Rosetta, Cuore, Pac-Man) nella notte
    di stanotte o di date: ora per ora l'altezza e le nuvole, le ore utili, la Luna, se entra nel campo o quanti
    pannelli di mosaico servono, e le impostazioni della camera per il suo tipo."""
    cfg = sys_config.get()
    return ast_skyplan.text(ast_skyplan.tonight(cfg, date.strip(), float(min_alt), "", 1, object.strip()[:80]))


@server.tool()
def sky_catalog(search: str, limit: int = 15) -> str:
    """Cerca nel catalogo del cielo profondo per nome, sigla o nome comune (anche una parte: «velo», «Sh2-1», «NGC 70»):
    tipo, coordinate J2000, dimensione, magnitudine, altri nomi."""
    cat = ast_catalog.load(ast_inventory.folder(sys_config.get()))
    objs = cat["objects"]
    want = search.strip().lower().replace(" ", "")
    if not want:
        return f"Catalogo: {len(objs)} oggetti ({', '.join(f'{k} {v}' for k, v in cat['sources'].items())})."
    hit = [o for o in objs if any(want in x.lower().replace(" ", "")
                                  for x in [o["name"]] + o["aliases"] + o["common"] + ast_catalog.named(o))]
    rows = [f"- {o['name']} ({', '.join(ast_catalog.named(o) + o['common'] + o['aliases']) or '—'}): "
            f"{ast_catalog.WORDS.get(o['type'], o['type'])}, RA {o['ra'] / 15:.2f} h, Dec {o['dec']:+.2f}°, "
            f"{o['maj'] or '?'}′" + (f", mag {o['mag']}" if o.get("mag") else "") for o in hit[:max(1, min(int(limit), 50))]]
    return "\n".join(rows) or f"Nessun oggetto per «{search}» fra {len(objs)}."


@server.tool()
def sky_sequence(object: str, date: str = "", kind: str = "", count: int = 0, exposure_s: float = 0) -> str:
    """Scrive la sequenza avanzata di N.I.N.A. per un oggetto e una notte (stanotte o date, AAAA-MM-GG), partendo dal
    modello della persona per quel tipo (banda stretta o larga, scelti in astro_setup.json): coordinate J2000 dal
    catalogo, gain/offset/posa misurati sui suoi frame e con i suoi dark, numero di pose che riempie le ore utili
    (o count), il resto del modello com'è; senza rotatore toglie le sue istruzioni e riduce un mosaico al primo
    pannello. Il file va in sequences/ della cartella astro: la persona lo apre in N.I.N.A., Aurora non lo avvia."""
    if kind not in ("", "narrowband", "broadband"):
        return "kind: narrowband, broadband o vuoto (dal tipo dell'oggetto)"
    try:
        r = ast_seqwrite.for_tonight(sys_config.get(), object.strip()[:80], date.strip(), kind, int(count), float(exposure_s))
    except ValueError as e:
        return f"Sequenza non scritta: {e}"
    return ast_seqwrite.text(r)


@server.tool()
def sky_rotation(angle: str = "") -> str:
    """Aiuta a ruotare la camera a mano nel focheggiatore fino all'angolo dell'inquadratura (senza rotatore): N.I.N.A.
    scatta e risolve un frame, Aurora confronta l'angolo con quello voluto (angle in gradi come in N.I.N.A., o vuoto
    per quello dell'assistente di inquadratura aperto) e dice di quanti gradi girare e in che verso; si ripete finché
    è entro ±0,3°. Non muove la montatura né altro: solo uno scatto di plate solving."""
    want = None
    if angle.strip():
        try:
            want = float(angle.replace(",", ".").replace("°", ""))
        except ValueError:
            return "angle: un numero di gradi (es. 125 o 37,5), o vuoto"
    r = ast_rotate.run(sys_config.get(), want)
    if "error" in r:
        return f"Non misurata: {r['error']}"
    return "\n".join(x for x in (f"Angolo ora {r['pa']}°, voluto {r['want']}°.", r.get("learned") and f"Imparato: {r['learned']}.",
                                  r["say"]) if x)


@server.tool()
def sky_collimation(exposure_s: float = 3, learned_screw: str = "", turned: str = "") -> str:
    """Il test della stella sfocata: con una stella luminosa al centro del campo, sfocata finché si vede l'ombra del
    secondario, N.I.N.A. scatta e Aurora misura quanto l'ombra è fuori dal centro dell'anello; dice se il primario è
    collimato o quale vite girare, di quanto e in che verso. Le viti si imparano una volta: gira una vite (per esempio
    di 1/8 in senso orario) e chiama con learned_screw il suo nome («in basso a destra») e turned quanto
    («1/8 orario», «1/4 antiorario»). Muove solo l'otturatore: uno scatto."""
    learn = None
    if learned_screw.strip():
        eighths = ast_donut.parse_turn(turned)
        if eighths is None:
            return "turned: quanto hai girato, per esempio «1/8 orario» o «1/4 antiorario»"
        learn = (learned_screw.strip()[:40], eighths)
    r = ast_donut.run(sys_config.get(), float(exposure_s), learn)
    return "\n".join(x for x in (r.get("learned") and f"Imparato: {r['learned']}.", r["say"]) if x)


if __name__ == "__main__":
    server.run("stdio")

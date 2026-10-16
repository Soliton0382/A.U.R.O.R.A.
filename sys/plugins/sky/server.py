# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "sky" (ROADMAP N30): the whole deep sky to choose from for the person's equipment — tonight's targets
ranked (ast_skyplan), one object's night, the catalogue searched. Network: the public catalogues once (OpenNGC,
VizieR) and the sky's forecast (Open-Meteo, 7Timer!) with the site rounded to a tenth of a degree. The equipment is
read from the astro folder (the «astro» plugin's, which stays offline)."""
from __future__ import annotations

from aurora import ast_catalog, ast_inventory, ast_skyplan, sys_config
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


if __name__ == "__main__":
    server.run("stdio")

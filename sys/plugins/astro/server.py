# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "astro" (ROADMAP 79 step 0): the person's astrophotography equipment, read only — the profile of the latest
inventory (ast_inventory), the integrated darks' library of this machine, the files of the astro folder. No network."""
from __future__ import annotations

from aurora import ast_advice, ast_guidelog, ast_inventory, sys_config
from mcp.server.mcpserver import MCPServer

server = MCPServer("astro", version="1.0")


@server.tool()
def astro_profile() -> str:
    """L'attrezzatura per l'astrofotografia (telescopio, montatura, camere con la scala in "/px, guida PHD2, focheggiatore,
    filtri, plate solving, sito arrotondato, software, integrated dark) e cosa conviene controllare."""
    cfg = sys_config.get()
    p = ast_inventory.profile(cfg)
    if p and ast_guidelog.logs(ast_inventory.folder(cfg)):     # the guide logs added in the folder count
        p = {**p, "checks": [c for c in p["checks"] if c["what"] != ast_inventory.NO_GUIDE_LOG]}
    return ast_inventory.text(p)


@server.tool()
def astro_darks() -> str:
    """The integrated darks of this machine: exposure, gain, offset, frames, date of each; which exposures match the camera
    as N.I.N.A. sets it."""
    cfg = sys_config.get()
    lib = ast_inventory.darks_library(cfg)
    if not lib["darks"]:
        return lib["error"] or "Nessuna cartella di dark integrati indicata (AURORA_ASTRO_DARKS_DIR, pagina 🔭 Astro)."
    p = ast_inventory.profile(cfg)
    lines = [f"Integrated dark in {lib['folder']}: {len(lib['darks'])}"]
    for d in lib["darks"]:
        lines.append(f"- {d['file']}: {d.get('exposure_s', '?'):g} s, gain {d.get('gain', '?')}, offset {d.get('offset', '?')}, "
                     f"{d.get('frames') or '?'} pose, {d.get('date') or '?'}" + (" (vecchio)" if d["old"] else ""))
    if p:
        m = ast_inventory.darks_for(lib, p["rig"])
        lines.append(f"Per gain {m['gain']} e offset {m['offset']} (N.I.N.A.): {', '.join(f'{x:g} s' for x in m['match']) or 'nessuno'}")
    return "\n".join(lines)


OWN = ("darks.json", "astro_setup.json", "autoguide.jsonl", "sensor.json", "frames.json", "sky_catalog.json")   # Aurora's own files
NOTES = (".md", ".txt")
NOTE_MAX = 12000                                  # characters of one note given to the model


@server.tool()
def astro_files() -> str:
    """The files of the astro folder, each with the day it was last changed: the inventories and the manuals and
    notes added in the 🔭 Astro page (a note is read with astro_note)."""
    import time
    cfg = sys_config.get()
    d = ast_inventory.folder(cfg)
    inv = {f.name for f in ast_inventory.inventories(cfg)}
    rows = [f"- {f.name} ({f.stat().st_size // 1024} KB, cambiato il {time.strftime('%Y-%m-%d', time.localtime(f.stat().st_mtime))})"
            + (" — inventario" if f.name in inv else " — nota: leggibile con astro_note" if f.suffix.lower() in NOTES else "")
            for f in sorted(d.iterdir()) if f.is_file() and f.name not in OWN]
    return "\n".join(rows) or "La cartella astro è vuota."


@server.tool()
def astro_note(name: str) -> str:
    """Una nota della persona nella cartella astro (.md o .txt: la scheda dell'attrezzatura, il treno ottico e il back
    focus, la collimazione, i manuali scritti a mano), letta per intero. name: il nome del file come in astro_files, o
    una sua parte. Le note sono i dati che la persona ha scritto: l'inventario del PC non le contiene (C351)."""
    import time
    d = ast_inventory.folder(sys_config.get())
    notes = [f for f in sorted(d.iterdir()) if f.is_file() and f.suffix.lower() in NOTES and f.name not in OWN]
    want = name.strip().lower()
    hit = ([f for f in notes if f.name.lower() == want] or [f for f in notes if want and f.name.lower().startswith(want)]
           or [f for f in notes if want and want in f.name.lower()])
    if len(hit) != 1:
        return (("Più note con quel nome: " if hit else "Nessuna nota con quel nome. Note: ")
                + ", ".join(f.name for f in (hit or notes)) if (hit or notes) else "Nessuna nota nella cartella astro.")
    f = hit[0]
    text = f.read_text(encoding="utf-8-sig", errors="replace")
    cut = len(text) > NOTE_MAX
    return (f"{f.name} (cambiata il {time.strftime('%Y-%m-%d %H:%M', time.localtime(f.stat().st_mtime))}):\n\n"
            + text[:NOTE_MAX] + (f"\n\n[… tagliata: {len(text)} caratteri, i primi {NOTE_MAX}]" if cut else ""))


@server.tool()
def astro_nights() -> str:
    """Le notti già guidate: i log di guida di PHD2 della cartella astro, l'RMS di ogni sessione, e cosa ci legge Aurora
    (montatura ferma al meridiano, stella persa, allineamento polare, backlash, minimo movimento)."""
    cfg = sys_config.get()
    rig = (ast_inventory.profile(cfg) or {}).get("rig") or {}
    got = ast_guidelog.nights(ast_inventory.folder(cfg), rig.get("scale_arcsec_px"), rig.get("meridian_flip"))
    if not got:
        return "Nessun log di guida di PHD2 (PHD2_GuideLog_*.txt) nella cartella astro: si aggiungono dalla pagina 🔭 Astro."
    lines = []
    for n in got:
        lines.append(f"Notte {n['night']} ({n['file']}):")
        for s in n["sessions"]:
            r = s["rms"]
            lines.append(f"- {s['start'][11:16]}, {s['minutes']:g} min{' (Guiding Assistant)' if s['assistant'] else ''}: "
                         f"RMS RA {r['ra']}″ DEC {r['dec']}″ totale {r['total']}″, SNR {s['snr']}, stelle perse {s['lost']}")
        lines += [f"  ⚠ {f['code']}: " + ", ".join(f"{k}={v}" for k, v in f.items() if k not in ("code", "level")) for f in n["findings"]]
    return "\n".join(lines)


@server.tool()
def astro_advice() -> str:
    """I valori consigliati per l'attrezzatura (campionamento, rapporto guida/ripresa, posa di guida, minimo movimento,
    passo di calibrazione, durata massima, dither e assestamento, flip al meridiano, carico, coppia e contrappeso,
    gain/offset contro i dark, passo dell'autofocus): impostato ora, consigliato, perché; e le sequenze controllate."""
    r = ast_advice.report(sys_config.get())
    if not r["inventory"]:
        return "Nessun inventario: si scarica lo script dalla pagina 🔭 Astro e si carica il file che scrive."
    mark = {"ok": "✅", "warn": "⚠️", "bad": "❌", "unknown": "❓", "info": "ℹ️"}
    lines = [f"{mark.get(x['status'], '•')} {x['key']}: ora {x['current']} {x['unit']}, consigliato {x['advised']}"
             + (f", scelto {x['choice']}" if x.get("choice") else "") + f" — {x['why']} {x['n']}" for x in r["rows"]]
    for q in r["sequences"]:
        if q.get("findings"):
            lines.append(f"Sequenza {q['name']}: " + "; ".join(f"{f['code']} {f}" for f in q["findings"]))
    unknown = [f["key"] for f in r["facts_spec"] if r["facts"].get(f["key"]) is None]
    if unknown:
        lines.append("Dati che solo la persona conosce, ancora da dare (pagina 🔭 Astro → 🎛️): " + ", ".join(unknown))
    return "\n".join(lines)


@server.tool()
def astro_imaging(object: str = "") -> str:
    """Le impostazioni di ripresa migliori (gain, offset, posa) per un oggetto o per ogni tipo di oggetto (banda stretta,
    banda larga, HDR), calcolate dal sensore e dal cielo misurati sulle pose della persona, e il meglio con i suoi dark."""
    from aurora import ast_sensor
    cfg = sys_config.get()
    m = ast_sensor.measure(cfg, str(cfg["AURORA_ASTRO_FRAMES_DIR"] or "").strip())
    p = ast_sensor.plan(m, ast_inventory.darks_library(cfg)["darks"], ast_inventory.profile(cfg), 3, object.strip()[:120])
    def one(name, k):
        if name == "hdr":
            return f"HDR: gain {k['gain']:g}, offset {k['offset']:g}, pose {', '.join(f'{x:g} s' for x in k['exposures'])}, 30–40 light ciascuna"
        if not k["best"]:
            return f"{name}: non calcolabile ({'cielo non misurato' if not k['rate'] else 'sensore non misurato'})"
        b, w = k["best"], k["with_darks"]
        return (f"{name}: ottimale gain {b['gain']:g} offset {b['offset']:g} posa {b['exposure_s']} s (minima {b['t_min']} s)"
                + (f"; con i dark che ha: {w['exposure_s']:g} s" if w else "; nessun dark adatto"))
    lines = [one(n, k) for n, k in p["kinds"].items()]
    if p.get("object"):
        o = p["object"]
        lines.insert(0, f"Oggetto {o['name']}: tipo {o['kind']}{' (dal nome)' if o['guessed'] else ''} → " + one(o["kind"], p["kinds"][o["kind"]]))
    for s in m.get("sensors", []):
        lines.append(f"Sensore a gain {s['gain']:g}/offset {s['offset']:g}: {s['gain_e_adu']} e-/ADU, rumore {s['read_noise_e']} e-, "
                     f"full well {s['full_well_e']} e- (SubframeSelector: camera gain {s['gain_e_adu']}, 16-bit)")
    return "\n".join(lines)


if __name__ == "__main__":
    server.run("stdio")

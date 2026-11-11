# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 The words of the astro inventory (ast_inventory reads and measures; this one says): what is worth a look, each
with its code and its why, and the profile in words for the model and the plugin — in the reader's language (C526).
Moved here as they were from ast_inventory. A check is told from another by its code, never by its sentence."""
from __future__ import annotations

import re

from .ast_inventory import NO_GUIDE_LOG, OPTIONAL_ASCOM
from .sys_lang import say as _t


def _checks(p: dict) -> list[dict]:
    """What is worth a look, each with why (never a verdict on the owner's choices)."""
    out = []
    rig = p["rig"]
    if not p["darks"]:
        where = ", ".join(p.get("darks_looked_in") or []) or "Documenti, D:, E:"
        out.append({"code": "no_darks_folder", "what": _t("Nessuna cartella di dark trovata", "No folder of darks found"), "why": _t(f"cercata in {where}"
                    + ("" if p["script"] == 2 else "; lo script 1 non guardava la cartella delle immagini di N.I.N.A.: "
                       "rigenera l'inventario con lo script nuovo"), f"looked for in {where}"
                    + ("" if p["script"] == 2 else "; script 1 did not look in N.I.N.A.'s images folder: "
                       "make the inventory again with the new script"))})
    if not p["phd2"]["logs"] or p["phd2"]["latest_log"].endswith("(0 KB)"):
        out.append({"code": "no_guide_log", "what": _t(NO_GUIDE_LOG, "No useful PHD2 guide log"), "why": _t("senza log non si giudica la guida (RMS, stelle perse)", "without a log the guiding cannot be judged (RMS, lost stars)")})
    for e in p["nina_errors"]:
        m = re.search(r"GET of (\w+)\.(\w+)", e["text"])
        if m and m.group(2) in OPTIONAL_ASCOM:            # N.I.N.A. asks every property on connecting; some are optional
            continue
        if e["times"] >= 3:
            out.append({"code": "nina_error", "what": _t(f"N.I.N.A. ripete un errore ({e['times']} volte)", f"N.I.N.A. repeats an error ({e['times']} times)"), "why": e["text"]})
    g = rig.get("guiding") or {}
    if g.get("ratio") and g["ratio"] > 5:
        out.append({"code": "guide_scale", "what": _t(f"La scala di guida è {g['ratio']}× quella di ripresa", f"The guiding scale is {g['ratio']}× the imaging one"),
                    "why": _t("oltre circa 5× la guida fatica a vedere gli errori che la camera di ripresa registra", "beyond about 5× the guiding struggles to see the errors the imaging camera records")})
    links = p.get("links") or {}
    if p["script"] >= 3:
        for s in links.get("servers", []):
            if not s["ok"] and s["name"].startswith(("PHD2", "N.I.N.A.")):
                out.append({"code": "server_silent", "what": _t(f"{s['name']}: non risponde", f"{s['name']}: does not answer"), "why": _t("per seguire la guida e la sequenza dal vivo Aurora ne ha bisogno: "
                            + ("in PHD2, Strumenti → Abilita server" if s["name"].startswith("PHD2")
                               else "installa il plugin Advanced API di N.I.N.A. (Plugins → Available) e attivalo"), "to follow the guiding and the sequence live Aurora needs it: "
                            + ("in PHD2, Tools → Enable server" if s["name"].startswith("PHD2")
                               else "install N.I.N.A.'s Advanced API plugin (Plugins → Available) and turn it on"))})
        wf = links.get("windows_firewall") or {}
        # a «Public» network blocks what comes in only while Windows' firewall is on for it (unknown before script 4)
        if any("Public" in x for x in links.get("profiles", [])) and wf.get("Public", True):
            out.append({"code": "public_network", "what": _t("La rete del PC è «Pubblica» per Windows", "The PC's network is «Public» for Windows"),
                        "why": _t("Windows blocca le connessioni in entrata: per Aurora va messa su «Privata»", "Windows blocks incoming connections: for Aurora it is to be set to «Private»")})
        if links.get("listening") and not any(x["network"] for x in links["listening"]):
            out.append({"code": "local_only", "what": _t("I server ascoltano solo il PC stesso", "The servers listen to the PC itself only"), "why": _t("da un'altra macchina non si raggiungono: "
                        "nelle loro impostazioni va permesso l'accesso dalla rete di casa", "they cannot be reached from another machine: "
                        "their settings must allow the access from the home network")})
    elif p["script"] < 3:
        out.append({"code": "links_unread", "what": _t("Collegamenti ai programmi non letti", "The links to the programs were not read"), "why": _t("lo script 3, lanciato con N.I.N.A. e PHD2 aperti, "
                    "dice quali server offrono e come raggiungerli", "script 3, run with N.I.N.A. and PHD2 open, "
                    "tells which servers they offer and how to reach them")})
    if not rig.get("scale_arcsec_px"):
        out.append({"code": "no_scale", "what": _t("Scala di ripresa non calcolata", "Imaging scale not worked out"), "why": _t("mancano la focale o la dimensione dei pixel nel profilo di N.I.N.A.", "the focal length or the pixel size is missing in N.I.N.A.'s profile")})
    return out


def text(p: dict | None) -> str:
    """The profile in words, for the model and the plugin."""
    if not p:
        return _t("Nessun inventario dell'attrezzatura astro: caricalo nella pagina 🔭 Astro.", "No inventory of the astro equipment: load it in the page 🔭 Astro.")
    r = p["rig"]
    lines = [_t(f"Inventario del {p['written']} (script {p['script']}). PC: {p['system']}", f"Inventory of {p['written']} (script {p['script']}). PC: {p['system']}")]
    if r.get("telescope") or r.get("mount"):
        lines.append(_t(f"- Telescopio: {r['telescope']} {r.get('focal_mm') or '?'} mm f/{r.get('focal_ratio') or '?'}; montatura: {r['mount']} ({r['mount_driver']})", f"- Telescope: {r['telescope']} {r.get('focal_mm') or '?'} mm f/{r.get('focal_ratio') or '?'}; mount: {r['mount']} ({r['mount_driver']})"))
    if r.get("camera"):
        lines.append(_t(f"- Camera di ripresa: {r['camera']}, pixel {r.get('pixel_um')} µm, gain {r.get('gain')}, offset {r.get('offset')}, "
                     f"raffreddata a {r.get('cooling_c')} °C; scala {r.get('scale_arcsec_px', '?')}\"/px", f"- Imaging camera: {r['camera']}, pixel {r.get('pixel_um')} µm, gain {r.get('gain')}, offset {r.get('offset')}, "
                     f"cooled to {r.get('cooling_c')} °C; scale {r.get('scale_arcsec_px', '?')}\"/px"))
    g = r.get("guiding")
    if g:
        lines.append(_t(f"- Guida (PHD2, profilo «{g['profile']}»): {g.get('camera')}, focale {g.get('focal_mm')} mm, scala "
                     f"{g.get('scale_arcsec_px', '?')}\"/px ({g.get('ratio', '?')}× la ripresa); esposizione {g.get('exposure_ms')} ms; "
                     f"RA {g.get('ra_algorithm')}, DEC {g.get('dec_algorithm')}", f"- Guiding (PHD2, profile «{g['profile']}»): {g.get('camera')}, focal length {g.get('focal_mm')} mm, scale "
                     f"{g.get('scale_arcsec_px', '?')}\"/px ({g.get('ratio', '?')}× the imaging); exposure {g.get('exposure_ms')} ms; "
                     f"RA {g.get('ra_algorithm')}, DEC {g.get('dec_algorithm')}"))
    lines.append(_t(f"- Focheggiatore: {r.get('focuser') or '—'}; ruota portafiltri: {r.get('filter_wheel') or '—'}", f"- Focuser: {r.get('focuser') or '—'}; filter wheel: {r.get('filter_wheel') or '—'}")
                 + (f" ({', '.join(r['filters'])})" if r.get("filters") else ""))
    lines.append(_t(f"- Plate solving: {r.get('solver') or '—'}, cataloghi ASTAP {' '.join(p['astap']['databases']) or '—'}; "
                 f"immagini in {r.get('images') or '—'} ({r.get('file_type') or '?'})", f"- Plate solving: {r.get('solver') or '—'}, ASTAP catalogues {' '.join(p['astap']['databases']) or '—'}; "
                 f"images in {r.get('images') or '—'} ({r.get('file_type') or '?'})"))
    if r.get("site"):
        lines.append(_t(f"- Sito (arrotondato): lat {r['site']['lat']}, lon {r['site']['lon']}, {r['site']['elevation_m']:.0f} m", f"- Site (rounded): lat {r['site']['lat']}, lon {r['site']['lon']}, {r['site']['elevation_m']:.0f} m"))
    lines.append("- Software: " + ", ".join(f"{s['name']} {s['version']}".strip() for s in p["software"]))
    if p["darks"]:
        lines.append(_t("- Dark sul PC astro: ", "- Darks on the astro PC: ") + "; ".join(f"{d['folder']} ({d['files']})" for d in p["darks"][:8]))
    lib = p.get("library")
    if lib:
        lines.append(_t(f"- Dark integrati su questa macchina ({len(lib['darks'])}): per gain {lib['gain']} e offset {lib['offset']} "
                     f"le esposizioni {', '.join(f'{x:g} s' for x in lib['match']) or 'nessuna'}"
                     + (f"; per altre impostazioni {', '.join(f'{x:g} s' for x in lib['other'])}" if lib["other"] else ""), f"- Integrated darks on this machine ({len(lib['darks'])}): for gain {lib['gain']} and offset {lib['offset']} "
                     f"the exposures {', '.join(f'{x:g} s' for x in lib['match']) or 'none'}"
                     + (f"; for other settings {', '.join(f'{x:g} s' for x in lib['other'])}" if lib["other"] else "")))
    lines += [f"⚠️ {c['what']}: {c['why']}" for c in p["checks"]]
    return "\n".join(lines)

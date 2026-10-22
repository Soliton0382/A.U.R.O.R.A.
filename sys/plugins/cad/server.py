# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""CAD for Aurora's projects (ROADMAP 100; owner, 2026-10-14: «quando genera un progetto in autonomia può crearsi i
blueprint, gli esplosi CAD, generare tutti i PDF come da linee guida dell'ufficio brevetti»).

The model is OpenSCAD code written by Aurora, part by part — each with its reference sign, its name and the way it
moves in the exploded view. The plugin makes the geometry (OpenSCAD, STL: no screen needed), the line drawings
(cad_draw: its own renderer, no display, no GPU) and the patent sheets (cad_sheets: A4, EPO Rule 46). Everything
is written in the project: <project>/cad/<name>/ — model, parts, STL, figures, drawings.pdf, reference_signs.md.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path

from aurora import sys_config
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

import cad_draw
import cad_sheets

cfg = sys_config.get()
BASE = cfg.path("AURORA_PROJECTS_DIR")
server = MCPServer("cad", version="1.0")
NAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")


def _folder(project: str, name: str) -> Path:
    if not NAME.fullmatch(project or "") or not NAME.fullmatch(name or ""):
        raise ToolError("project and drawing names: lowercase letters, digits, . _ - (max 64)")
    p = BASE / project
    if not p.is_dir():
        raise ToolError(f"no project {project}: create it first (projects.project_create)")
    return p / "cad" / name


def _openscad() -> str:
    here = Path(__file__).resolve().parent / ".bin" / "openscad"
    found = str(here) if here.is_file() else shutil.which("openscad")
    if not found:
        raise ToolError("OpenSCAD is not installed on this machine (apt install openscad · brew install openscad)")
    return found


def _stl(scad: Path, stl: Path) -> None:
    r = subprocess.run([_openscad(), "-o", str(stl), str(scad)], capture_output=True, text=True, timeout=600)
    errors = [ln for ln in (r.stderr or "").splitlines() if "ERROR" in ln]
    if r.returncode or not stl.is_file() or stl.stat().st_size < 100 or errors:
        raise ToolError(f"OpenSCAD refused {scad.name}: {' | '.join(errors or (r.stderr or '').splitlines()[-3:])[:800]}")


@server.tool()
def cad_build(project: str, name: str, parts: list[dict], library: str = "") -> str:
    """Build a model from its parts. parts: [{"sign": 10, "name": "base plate", "code": "base();",
    "explode": [0, 0, 0], "material": "copper"}, …] — `code` is OpenSCAD that draws the part where it sits in the
    assembly (it may use the modules of `library`: shared OpenSCAD code, e.g. module definitions and $fn = 64);
    `explode` moves it in the exploded view (mm); `material` (optional) is how the project page's realistic view
    paints it: copper, magnet, steel, aluminium, brass, plastic, plastic_light, pcb, carbon, rubber, glass or wood
    (else guessed from the name).
    Reference signs: integers, distinct (10, 20, 30… leaves room). Writes the STL of the assembly and of each part
    into <project>/cad/<name>/."""
    out = _folder(project, name)
    if not parts or len(parts) > 60:
        raise ToolError("1 to 60 parts")
    signs = [int(p.get("sign", 0)) for p in parts]
    if len(set(signs)) != len(signs) or min(signs) <= 0:
        raise ToolError("each part needs its own positive reference sign")
    out.mkdir(parents=True, exist_ok=True)
    t0, sizes = time.time(), []
    for k, p in enumerate(parts):
        ex = [float(v) for v in (p.get("explode") or [0, 0, 0])][:3]
        for kind, code in (("part", p["code"]), ("exploded", f"translate({ex}) {{ {p['code']} }}")):
            scad = out / f"{kind}_{k}.scad"
            scad.write_text(f"// {p.get('name', '')} ({signs[k]})\n{library}\n{code}\n", encoding="utf-8")
            _stl(scad, out / f"{kind}_{k}.stl")
        tri = cad_draw.load_stl(out / f"part_{k}.stl").reshape(-1, 3)
        sizes.append((tri.max(0) - tri.min(0)).round(1).tolist())
    assembly = "\n".join(f"// {p.get('name', '')} ({signs[k]})\n{p['code']}" for k, p in enumerate(parts))
    (out / "model.scad").write_text(f"{library}\n{assembly}\n", encoding="utf-8")
    mat = [{"material": str(p["material"])[:20]} if p.get("material") else {} for p in parts]
    (out / "parts.json").write_text(json.dumps({"parts": [{"sign": s, "name": p.get("name", ""), "size_mm": z, **m}
                                                          for s, p, z, m in zip(signs, parts, sizes, mat)]},
                                               ensure_ascii=False, indent=1), encoding="utf-8")
    lines = "\n".join(f"- {s} {p.get('name', '')}: {z[0]} × {z[1]} × {z[2]} mm" for s, p, z in zip(signs, parts, sizes))
    return f"Model {name}: {len(parts)} parts built in {time.time() - t0:.1f} s ({out}).\n{lines}"


@server.tool()
def cad_drawings(project: str, name: str, office: str = "EP", figures: list[dict] | None = None) -> str:
    """The patent drawing sheets of a model built with cad_build, for an office (EP, IT or US): Fig. 1 the assembly
    (isometric), Fig. 2 the exploded view with the reference signs, Fig. 3–5 front, top and side views;
    drawings_<office>.pdf in that office's form (its margins and paper, «Fig. N» — «FIG. N» for the US —, sheets
    «1/3», black lines only) and reference_signs.md (the list for the description), with the figures.
    figures (optional, in place of those five): the figures the invention needs, in order, e.g.
    [{"parts": [41, 42, 21, 22], "view": "top", "title": "rotor seen from above: the two lobes and the sub-poles"},
     {"parts": [110, 121, 122, 123, 124], "view": "top", "title": "stator 100 seen from above"},
     {"view": "iso", "exploded": true, "title": "exploded view"}] — parts: reference signs (all when omitted); view:
    iso, top, front or side; exploded: the exploded positions; signs: false for a figure without reference signs
    (C377: the assembly's views hid the rotor's faces, the heart of the invention)."""
    if figures:
        return _figures(project, name, office, figures)
    office = (office or "EP").upper()
    if office not in cad_sheets.OFFICES:
        raise ToolError(f"office: one of {', '.join(cad_sheets.OFFICES)}")
    fig = "FIG." if office == "US" else "Fig."
    out = _folder(project, name)
    meta = out / "parts.json"
    if not meta.is_file():
        raise ToolError(f"no model {name}: build it first with cad_build")
    parts = json.loads(meta.read_text(encoding="utf-8"))["parts"]
    t0 = time.time()
    load = lambda kind: [cad_draw.load_stl(out / f"{kind}_{k}.stl") for k in range(len(parts))]   # noqa: E731
    assembled, exploded = load("part"), load("exploded")
    figs = out / "figures"
    figs.mkdir(exist_ok=True)

    def drawing(tris, view, signs=None):
        r = cad_draw.render(tris, view, 1800)
        img, (x0, y0) = cad_sheets.crop(r["lines"])
        if signs is None:
            return cad_sheets.Image.fromarray(img)
        anchors = [(a[0] - x0, a[1] - y0) if a else None for a in cad_draw.anchors(r["part"], len(tris))]
        return cad_sheets.label(img, anchors, signs)

    signs = [p["sign"] for p in parts]
    f1, f2 = drawing(assembled, "iso"), drawing(exploded, "iso", signs)
    f3, f4, f5 = (drawing(assembled, v) for v in ("front", "top", "side"))
    for i, f in enumerate((f1, f2, f3, f4, f5), 1):
        f.save(figs / f"fig{i}.png")
    sheets = [[(f1, f"{fig} 1")], [(f2, f"{fig} 2")], [(f3, f"{fig} 3"), (f4, f"{fig} 4"), (f5, f"{fig} 5")]]
    pages = [cad_sheets.sheet(s, n, len(sheets), office) for n, s in enumerate(sheets, 1)]
    cad_sheets.pdf(pages, out / f"drawings_{office}.pdf")
    signs_md = "\n".join(f"{p['sign']}  {p['name']}" for p in parts)
    (out / "reference_signs.md").write_text(
        "Reference signs (for the description)\n\n" + signs_md + "\n\nFig. 1 isometric view of the assembly; Fig. 2 "
        "exploded isometric view; Fig. 3 front view; Fig. 4 top view; Fig. 5 side view.\n", encoding="utf-8")
    return (f"drawings_{office}.pdf: {len(pages)} sheets, 5 figures, {len(parts)} reference signs, in "
            f"{time.time() - t0:.1f} s ({out / f'drawings_{office}.pdf'}). Reference signs:\n{signs_md}")


def _figures(project: str, name: str, office: str, figures: list[dict]) -> str:
    """cad_drawings with the figures asked: each one some parts, in a view, one figure a sheet."""
    office = (office or "EP").upper()
    if office not in cad_sheets.OFFICES:
        raise ToolError(f"office: one of {', '.join(cad_sheets.OFFICES)}")
    if not 1 <= len(figures) <= 20:
        raise ToolError("1 to 20 figures")
    fig = "FIG." if office == "US" else "Fig."
    out = _folder(project, name)
    meta = out / "parts.json"
    if not meta.is_file():
        raise ToolError(f"no model {name}: build it first with cad_build")
    parts = json.loads(meta.read_text(encoding="utf-8"))["parts"]
    signs = [p["sign"] for p in parts]
    t0 = time.time()
    load = lambda kind: [cad_draw.load_stl(out / f"{kind}_{k}.stl") for k in range(len(parts))]   # noqa: E731
    assembled, exploded = load("part"), load("exploded")
    figs = out / "figures"
    figs.mkdir(exist_ok=True)
    images, lines = [], []
    for n, f in enumerate(figures, 1):
        view = str(f.get("view", "iso"))
        if view not in cad_draw.VIEWS:
            raise ToolError(f"figure {n}: view one of {', '.join(cad_draw.VIEWS)}")
        wanted = [int(s) for s in (f.get("parts") or signs)]
        unknown = [s for s in wanted if s not in signs]
        if unknown:
            raise ToolError(f"figure {n}: no part with sign {unknown} (signs: {signs})")
        idx = [k for k, s in enumerate(signs) if s in wanted]
        tris = [(exploded if f.get("exploded") else assembled)[k] for k in idx]
        r = cad_draw.render(tris, view, 1800)
        img, (x0, y0) = cad_sheets.crop(r["lines"])
        if f.get("signs", True):
            anchors = [(a[0] - x0, a[1] - y0) if a else None for a in cad_draw.anchors(r["part"], len(tris))]
            picture = cad_sheets.label(img, anchors, [signs[k] for k in idx])
        else:
            picture = cad_sheets.Image.fromarray(img)
        picture.save(figs / f"fig{n}.png")
        images.append((picture, f"{fig} {n}"))
        lines.append(f"{fig} {n}: {str(f.get('title', '')).strip() or view} ({', '.join(str(signs[k]) for k in idx)})")
    pages = [cad_sheets.sheet([im], i, len(images), office) for i, im in enumerate(images, 1)]
    cad_sheets.pdf(pages, out / f"drawings_{office}.pdf")
    signs_md = "\n".join(f"{p['sign']}  {p['name']}" for p in parts)
    (out / "reference_signs.md").write_text("Reference signs (for the description)\n\n" + signs_md + "\n\n"
                                            + "\n".join(lines) + "\n", encoding="utf-8")
    return (f"drawings_{office}.pdf: {len(pages)} sheets, {len(images)} figures, in {time.time() - t0:.1f} s "
            f"({out / f'drawings_{office}.pdf'}); the figures one by one in {figs}/fig<n>.png.\n" + "\n".join(lines))


@server.tool()
def cad_blueprint(project: str, name: str, title: str = "", parts: list[int] | None = None) -> str:
    """A dimensioned technical drawing of a model built with cad_build (not a patent sheet): A4 landscape, front, top
    and side views in one standard scale (first-angle projection, ISO 128-30), overall dimensions in mm (ISO 129-1),
    an isometric view, the title block and the parts list with their sizes; blueprint.pdf in <project>/cad/<name>/.
    parts (optional): only these reference signs — a part's own drawing (e.g. the rotor), blueprint_<signs>.pdf."""
    import cad_blueprint
    out = _folder(project, name)
    meta = out / "parts.json"
    if not meta.is_file():
        raise ToolError(f"no model {name}: build it first with cad_build")
    every = json.loads(meta.read_text(encoding="utf-8"))["parts"]
    wanted = set(int(s) for s in parts) if parts else {p["sign"] for p in every}
    idx = [k for k, p in enumerate(every) if p["sign"] in wanted]
    if not idx:
        raise ToolError(f"no part with signs {sorted(wanted)} (signs: {[p['sign'] for p in every]})")
    t0 = time.time()
    assembled = [cad_draw.load_stl(out / f"part_{k}.stl") for k in idx]
    page = cad_blueprint.sheet(assembled, [every[k] for k in idx], title or name, project)
    file = "blueprint.pdf" if not parts else f"blueprint_{'_'.join(str(every[k]['sign']) for k in idx)}.pdf"
    cad_sheets.pdf([page], out / file)
    return f"{file}: A4 landscape, 3 dimensioned views, {len(idx)} parts listed, in {time.time() - t0:.1f} s ({out / file})"


if __name__ == "__main__":
    server.run()

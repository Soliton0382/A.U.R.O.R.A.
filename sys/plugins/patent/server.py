# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Patent filings for Aurora's projects (ROADMAP 100; owner, 2026-10-14: «delle spunte per compatibilità brevetto,
blueprint… sia prima che durante che alla fine posso sempre renderlo compatibile»): the texts in each office's form
(IT, EP, US), the CAD drawings added, the whole package checked. Written into <project>/patent/<name>/<office>/;
the owner's own folders are only read (a check). No AI notice on a filing: it goes to a public office, signed by
its inventor."""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from aurora import sys_config
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

import check
import rules

cfg = sys_config.get()
PROJECTS, DOCUMENTS = cfg.path("AURORA_PROJECTS_DIR"), cfg.path("AURORA_DOCUMENTS_DIR")
server = MCPServer("patent", version="1.0")


def _rule(office: str) -> dict:
    try:
        return rules.office(office)
    except ValueError as e:
        raise ToolError(str(e)) from None


def _package(project: str, name: str, office: str) -> Path:
    import re
    for v in (project, name):
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", v or ""):
            raise ToolError("project and package names: lowercase letters, digits, . _ - (max 64)")
    if not (PROJECTS / project).is_dir():
        raise ToolError(f"no project {project}")
    return PROJECTS / project / "patent" / name / office.upper()


@server.tool()
def patent_offices() -> str:
    """The offices Aurora prepares filings for, with their rules of form and the sources."""
    lines = []
    for code, r in rules.OFFICES.items():
        t, d = r["text_margins"], r["drawing_margins"]
        lines.append(f"{code} — {r['name']} ({r['source']}): page {r['page']}; text margins {t['top']}/{t['left']}/"
                     f"{t['right']}/{t['bottom']} mm; drawings {d['top']}/{d['left']}/{d['right']}/{d['bottom']} mm; "
                     f"spacing {r['spacing']}; abstract ≤ {r['abstract_words'] or '—'} words; figures «{r['fig']} n»"
                     + ("; paragraphs [0001]" if r["paragraph_numbers"] else "")
                     + ("" if r["claims_required"] else "; claims not required (provisional)"))
    return "\n".join(lines)


@server.tool()
def patent_document(project: str, name: str, office: str, title: str, description: list[dict], abstract: str,
                    claims: list[str] | None = None, drawings: str = "") -> str:
    """The texts of a patent application in an office's form (office: IT, EP or US). description: [{"heading":
    "Background", "text": "paragraph\\n\\nparagraph"}, …] — recall every reference sign of the drawings (10, 20…);
    claims: one string each, in order; abstract: ≤ 150 words (EP, US). drawings: the name of a cad model of this
    project: its drawing sheets for this office (cad_drawings with this office) are added with its reference signs.
    Writes <project>/patent/<name>/<office>/ and checks it."""
    rule = _rule(office)
    out = _package(project, name, rule["code"])
    if not description or not abstract.strip():
        raise ToolError("a description and an abstract")
    import writer
    t0 = time.time()
    files = writer.write(out, rule["code"], rule, title, description, list(claims or []), abstract)
    if drawings:
        cad = PROJECTS / project / "cad" / drawings
        sheet = cad / f"drawings_{rule['code']}.pdf"
        if not sheet.is_file():
            raise ToolError(f"no drawings for {rule['code']} in cad/{drawings}: cad_drawings(project, '{drawings}', "
                            f"office='{rule['code']}') first")
        shutil.copy2(sheet, out / "04_drawings.pdf")
        shutil.copy2(cad / "reference_signs.md", out / "reference_signs.md")
        files.append(out / "04_drawings.pdf")
    report = check.check(out, rule)
    written = check._text(files[0])[0]                      # the text as the PDF holds it: what an examiner reads
    return (f"{rule['code']} package in {time.time() - t0:.1f} s: {out}\n" + "\n".join(f.name for f in files)
            + "\n\nCHECK:\n" + "\n".join(f"{m} {w}" for m, w in report)
            + f"\n\nTHE DESCRIPTION AS WRITTEN (from the PDF, first 1500 characters):\n{written[:1500]}")


@server.tool()
def patent_check(office: str, project: str = "", name: str = "", folder: str = "") -> str:
    """Check a filing package against an office's rules of form: a project's (project + name) or a folder of the
    owner's documents (folder, relative to their documents: read only, nothing is changed)."""
    rule = _rule(office)
    if folder:
        target = (DOCUMENTS / folder).resolve()
        if DOCUMENTS.resolve() not in target.parents or not target.is_dir():
            raise ToolError("a folder inside the documents")
    else:
        target = _package(project, name, rule["code"])
        if not target.is_dir():
            raise ToolError(f"no package {name} for {rule['code']} in {project}: patent_document first")
    report = check.check(target, rule)
    bad = sum(m == check.BAD for m, _ in report)
    return (f"{rule['code']} ({rule['source']}) — {target.name}: {bad} problems\n"
            + "\n".join(f"{m} {w}" for m, w in report))


if __name__ == "__main__":
    server.run()

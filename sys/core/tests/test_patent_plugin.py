# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Patent filings (ROADMAP 100): each office's rules with their source; the checker finds what a filing must not have;
the project's ticks and the goal of «Procedi»."""
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

PATENT = Path(__file__).resolve().parents[2] / "plugins" / "patent"
sys.path.insert(0, str(PATENT))
import check  # noqa: E402
import rules  # noqa: E402


def test_each_office_has_its_rules_and_source():
    it, ep, us = (rules.office(c) for c in ("IT", "EP", "us"))
    assert set(it["text_margins"].values()) == {25} and "art. 22" in it["source"]          # D.M. 33/2010
    assert ep["drawing_margins"] == {"top": 25, "left": 25, "right": 15, "bottom": 10} and ep["abstract_words"] == 150
    assert us["fig"] == "FIG." and us["paragraph_numbers"] and not us["claims_required"] and us["page"] == "letter"
    with pytest.raises(ValueError):
        rules.office("JP")


def _pdf(path: Path, pages, size=(2480, 3508)):
    imgs = []
    for draw in pages:
        im = Image.new("RGB", size, "white")
        draw(ImageDraw.Draw(im))
        imgs.append(im)
    imgs[0].save(path, "PDF", resolution=300, save_all=True, append_images=imgs[1:])


def test_the_checker_finds_colours_margins_and_an_ai_notice(tmp_path):
    # a drawing in colour, text running into the right margin
    _pdf(tmp_path / "04_drawings.pdf", [lambda d: d.rectangle([600, 600, 1800, 1800], outline="red", width=12)])
    _pdf(tmp_path / "01_description.pdf", [lambda d: d.rectangle([400, 600, 2470, 640], fill="black")])
    rep = check.check(tmp_path, rules.office("EP"))
    bad = [w for m, w in rep if m == check.BAD]
    assert any("colours" in w for w in bad) and any("right" in w and "margins" in w for w in bad)


def test_a_line_that_is_not_the_abstract_and_claims_out_of_order(tmp_path, monkeypatch):
    texts = {"03_abstract.pdf": "ABSTRACT\nA stand for a phone with a base and a lip.\nWord count: approximately 12 words.",
             "02_claims.pdf": "CLAIMS\n1. A stand.\n3. The stand of claim 1.", "01_description.pdf": "base 10 and lip 20"}
    for n in texts:
        _pdf(tmp_path / n, [lambda d: None])
    (tmp_path / "reference_signs.md").write_text("10  base\n20  lip\n30  foot\n")
    monkeypatch.setattr(check, "_text", lambda f: (texts[f.name], {"Producer": "fpdf2"}, [(210.0, 297.0)]))
    rep = dict((w, m) for m, w in check.check(tmp_path, rules.office("EP")))
    assert rep["abstract: 11 words (≤ 150)"] == check.OK                       # the counting line left out
    assert any("not the abstract" in w for w in rep)
    assert any(w.startswith("claims: 2, numbered [1, 3]") for w in rep)
    assert any("not recalled in the description: 30" in w for w in rep)        # D.M. 33/2010 art. 22.3


def test_an_ai_notice_in_the_metadata_is_found(tmp_path, monkeypatch):
    _pdf(tmp_path / "01_description.pdf", [lambda d: None])
    monkeypatch.setattr(check, "_text", lambda f: ("A stand.", {"Creator": "Content generated with artificial intelligence"},
                                                   [(210.0, 297.0)]))
    assert any(m == check.BAD and "AI notice" in w for m, w in check.check(tmp_path, rules.office("IT")))


def test_the_ticks_and_the_goal_of_procedi(cfg):
    from aurora import prj_docs
    d = prj_docs.save(cfg, "demo", ["patent_US", "blueprint", "nonsense"], run_id="r1")
    assert d["targets"] == ["patent_US", "blueprint"] and d["runs"][-1]["run_id"] == "r1"
    g = prj_docs.goal("demo", d["targets"])
    assert "cad_blueprint" in g and "office='US'" in g and "patent_check" in g and "AI made them" in g
    assert "Brevetto USA" in prj_docs.plan_note(cfg, "demo") and prj_docs.plan_note(cfg, "other") == ""
    g = prj_docs.goal("demo", ["render", "simulator"])                      # N42: the two new ticks
    assert "`material`" in g and "sim/<name>.json" in g and "project_write_file" in g


def test_signs_written_as_a_table_are_checked_too(tmp_path, monkeypatch):
    # C382: a Markdown table of signs was read as none — «0 reference signs recalled» passed while one was missing
    texts = {"02_claims.pdf": "CLAIMS\n1. A stand.", "01_description.pdf": "base 10 and lip 20"}
    for n in texts:
        _pdf(tmp_path / n, [lambda d: None])
    (tmp_path / "reference_signs.md").write_text("| segno | elemento |\n|---|---|\n| 10 | base |\n| 20 | lip |\n| 30 | foot |\n")
    monkeypatch.setattr(check, "_text", lambda f: (texts[f.name], {"Producer": "fpdf2"}, [(210.0, 297.0)]))
    rep = [w for _, w in check.check(tmp_path, rules.office("EP"))]
    assert any("not recalled in the description: 30" in w for w in rep)
    (tmp_path / "reference_signs.md").write_text("# signs\n")
    assert any("lists no sign" in w for _, w in check.check(tmp_path, rules.office("EP")))

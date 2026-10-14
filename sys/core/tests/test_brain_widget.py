# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""ROADMAP 110: the brain widget — registered, in the offline shell, every area and step it names said in both
languages, and the events of a run reaching an area (read from the code: no browser here)."""
import json
import re
from pathlib import Path

W = Path(__file__).resolve().parents[1] / "webui"
JS = (W / "js" / "modules" / "brain.js").read_text(encoding="utf-8")


def test_registered_and_in_the_offline_shell():
    assert re.search(r"widgets = \[[^\]]*\bbrain\b", (W / "js" / "modules.js").read_text(encoding="utf-8"))
    sw = (W / "sw.js").read_text(encoding="utf-8")
    assert "/static/js/modules/brain.js" in sw and "/static/css/brain.css" in sw


def test_every_area_and_step_is_said_in_both_languages():
    areas = re.findall(r"^  (\w+): \{ x:", JS, re.M)
    assert len(areas) == 8
    for lang in ("it_IT", "en_US"):
        table = json.loads((W / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
        assert all(f"brain.a.{a}" in table for a in areas), lang
        steps = [k for k in table if k.startswith("brain.e.")]
        assert len(steps) >= 25, lang


def test_the_pipelines_steps_reach_an_area():
    rules = re.findall(r'\[/\^\((.+?)\)/, "(\w+)"\]', JS)
    assert rules
    def area(name):
        return next((a for rx, a in rules if re.match(f"^({rx})", name)), None)
    for name, want in (("route", "frontal"), ("translate", "language"), ("retrieval.hits", "temporal"),
                       ("verify.keep", "parietal"), ("grid.rule", "parietal"), ("image.plan", "occipital"),
                       ("tool.call", "cerebellum"), ("agent.start", "motor"), ("rem.start", "stem")):
        assert area(name) == want, name


def test_the_brain_is_grays_figure_with_its_six_parts():
    """Traced from Gray's Anatomy Fig. 728 (public domain): the six parts the areas live in, the gyri, the fissures;
    the data file in the offline shell; the credit in NOTICE."""
    data = (W / "js" / "modules" / "brain_gray.js").read_text(encoding="utf-8")
    lobes = json.loads(re.search(r"export const LOBES = (\{.*?\});", data, re.S).group(1))
    assert set(lobes) == {"frontal", "parietal", "temporal", "occipital", "cerebellum", "stem"}
    assert len(json.loads(re.search(r"export const GYRI = (\[.*?\]);", data, re.S).group(1))) > 50
    assert "/static/js/modules/brain_gray.js" in (W / "sw.js").read_text(encoding="utf-8")
    assert "Gray" in (W.parents[2] / "NOTICE").read_text(encoding="utf-8")
    assert "<text" not in data                                     # the figure's labels left out


def test_a_run_still_open_is_never_at_rest_and_each_step_has_its_own_words():
    """C324: a model on the cloud answers in one call (route, then nothing for ~30 s, then the rest at once): the
    widget said «at rest» while the run was open. And «pivot» showed pivot.back's words."""
    assert "if (followed.size) { this.quiet = setTimeout(rest" in JS
    assert 'brain.working' in JS
    table = json.loads((W / "i18n" / "it_IT.json").read_text(encoding="utf-8"))
    assert table["brain.e.pivot"] != table["brain.e.pivot.back"]
    assert "`brain.e.${name}`" in JS                               # the whole name first

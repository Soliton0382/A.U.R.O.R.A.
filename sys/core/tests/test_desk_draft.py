# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N152 version 1: from recorded demonstrations to drafts (desk/app/draft.py). The events are three real
recordings on the virtual bench with invented text (M336): Kate saved with Ctrl+S, Kate saved from the File menu,
KCalc computing 12+30 with Enter."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desk import library_check  # noqa: E402
from desk.app import draft  # noqa: E402

FX = json.loads((Path(__file__).parent / "data" / "desk_demo_events.json").read_text(encoding="utf-8"))
KATE = {"name": "kate", "package": "kate", "exe": "/usr/bin/kate", "version": "4:25.12", "args": ["/x/nota.txt"]}
KCALC = {"name": "kcalc", "package": "kcalc", "exe": "/usr/bin/kcalc", "version": "4:25.12"}


def _steps(d):
    return [(s["do"], s.get("keys") or s.get("target", {}).get("id_end", "")) for s in d["procedure"]["steps"]]


def test_shortcut_save_is_a_flagged_key_step():
    d = draft.build(FX["A"], KATE, network=False)
    assert [s[0] for s in _steps(d)] == ["type", "key"]
    assert _steps(d)[1][1] == "Ctrl+S"
    assert d["examples"] == {"p1": "Ciao mondo"}
    assert any("scorciatoia" in f for f in d["flags"])


def test_menu_save_is_the_last_item_with_an_effect_and_no_double_step():
    d = draft.build(FX["B"], KATE, network=False)
    st = _steps(d)
    assert [s[0] for s in st] == ["type", "open_menu", "press"]
    assert st[1][1].endswith(".QMenuBar.file") and st[2][1].endswith(".file_save")
    assert d["flags"] == [] and d["examples"] == {"p1": "Riga B"}


def test_calculator_keeps_what_was_typed_not_the_result():
    d = draft.build(FX["C"], KCALC, network=False)
    assert [s[0] for s in _steps(d)] == ["type", "key", "read"]
    assert d["examples"] == {"p1": "12+30"}
    assert any("tasto" in f for f in d["flags"])


def test_launch_paths_become_parameters_never_stored():
    d = draft.build(FX["A"], KATE, network=False)
    la = d["procedure"]["program"]["launch"]
    assert la["args"] == ["{f1}"] and d["procedure"]["params"]["f1"] == {"kind": "path"}
    assert "/x/nota.txt" not in json.dumps(d)


def test_with_a_network_every_write_leaves():
    d = draft.build(FX["B"], KATE, network=True)
    assert {s["class"] for s in d["procedure"]["steps"] if s["do"] != "open_menu"} == {"esce"}


@pytest.mark.parametrize("key,prog", [("A", KATE), ("B", KATE), ("C", KCALC)])
def test_drafts_are_valid_personal_procedures(tmp_path, key, prog):
    d = draft.build(FX[key], prog, network=False)
    proc = dict(d["procedure"], id=f"per:linux/{prog['name']}/prova")
    f = tmp_path / "linux" / prog["name"] / "prova.json"
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps(proc, ensure_ascii=False))
    assert library_check.check(f, tmp_path, ns="per") == []
    assert library_check.check(f, tmp_path, ns="gen") != []           # never valid as a general procedure


def test_an_unknown_version_only_in_personal(tmp_path):
    d = draft.build(FX["C"], dict(KCALC, version=""), network=False)
    assert d["procedure"]["program"]["versions"]["min"] == "sconosciuta"
    proc = dict(d["procedure"], id="gen:linux/kcalc/prova")
    f = tmp_path / "linux" / "kcalc" / "prova.json"
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps(proc, ensure_ascii=False))
    assert any("unknown version" in e for e in library_check.check(f, tmp_path, ns="gen"))


def test_a_long_text_is_never_an_example():
    ev = [dict(e) for e in FX["A"]]
    long = "x" * 300
    for e in ev:
        if e["kind"] == "Object:TextChanged" and e.get("text_after"):
            e["text_after"] = long
    d = draft.build(ev, KATE, network=False)
    assert d["examples"] == {} and any("testo lungo" in f for f in d["flags"])


def test_a_file_name_as_anchor_is_flagged():
    t, flags = draft.target({"role": "push button", "name": "relazione-2026.pdf", "id": ""}, "it")
    assert t == {"role": "push button", "name": {"it": "relazione-2026.pdf"}} and flags


def test_qml_ids_are_not_anchors():
    assert draft.id_end("QApplication.MainWindow#1.PageRow_QMLTYPE_8_QML_144.Foo") == ""
    assert draft.id_end("QApplication.MainWindow#1.KCalculator.pbEqual") == ".KCalculator.pbEqual"

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N152: the general library's format check (design §7, V1-b, V1-h) — every shipped procedure is valid, and the
check refuses what would widen Aurora's reach or lower a step's class."""
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desk import library_check as lc  # noqa: E402

KATE = lc.LIBRARY / "linux" / "kate" / "scrivi-e-salva.json"


def test_every_shipped_procedure_is_valid():
    res = lc.check_tree()
    assert res, "the library is empty"
    assert {k: v for k, v in res.items() if v} == {}


def test_only_json_files_in_the_library():
    assert [p.name for p in lc.LIBRARY.rglob("*") if p.is_file() and p.suffix != ".json"] == []


def _write(tmp_path: Path, d: dict, rel: str = "linux/kate/scrivi-e-salva.json") -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False))
    return p


@pytest.fixture
def base() -> dict:
    return json.loads(KATE.read_text(encoding="utf-8"))


def test_a_copy_of_a_valid_procedure_stays_valid(tmp_path, base):
    assert lc.check(_write(tmp_path, base), tmp_path) == []


@pytest.mark.parametrize("field", ["trusted", "sites", "folders", "programs", "exclusions", "class_override"])
def test_a_widening_field_makes_it_invalid(tmp_path, base, field):
    d = copy.deepcopy(base)
    d[field] = ["anything"]
    errs = lc.check(_write(tmp_path, d), tmp_path)
    assert any("widen" in e for e in errs)


def test_a_widening_field_inside_a_step_too(tmp_path, base):
    d = copy.deepcopy(base)
    d["steps"][0]["trusted"] = True
    assert any("widen" in e for e in lc.check(_write(tmp_path, d), tmp_path))


def test_an_unknown_field_is_not_ignored(tmp_path, base):
    d = copy.deepcopy(base)
    d["steps"][1]["shortcut"] = "x"
    assert any("unknown field 'shortcut'" in e for e in lc.check(_write(tmp_path, d), tmp_path))


def test_a_write_cannot_be_declared_read_only(tmp_path, base):
    d = copy.deepcopy(base)
    d["steps"][0]["class"] = "legge"                       # a «type» step
    assert any("lower than 'scrive in locale'" in e for e in lc.check(_write(tmp_path, d), tmp_path))


def test_with_a_network_every_click_may_leave(tmp_path, base):
    d = copy.deepcopy(base)
    d["program"]["network"] = True
    errs = lc.check(_write(tmp_path, d), tmp_path)
    assert any("lower than 'esce'" in e for e in errs)


def test_a_delete_button_is_always_irreversible(tmp_path, base):
    d = copy.deepcopy(base)
    d["steps"][2]["target"]["name"] = {"it": "Elimina", "en": "Delete"}
    assert any("lower than 'irreversibile'" in e for e in lc.check(_write(tmp_path, d), tmp_path))


def test_a_send_button_leaves(tmp_path, base):
    d = copy.deepcopy(base)
    d["steps"][2]["target"]["name"] = {"it": "Invia", "en": "Send"}
    assert any("lower than 'esce'" in e for e in lc.check(_write(tmp_path, d), tmp_path))


def test_the_id_follows_the_folder(tmp_path, base):
    d = copy.deepcopy(base)
    d["id"] = "per:linux/kate/scrivi-e-salva"
    assert any("id must be" in e for e in lc.check(_write(tmp_path, d), tmp_path))


def test_an_undeclared_parameter_is_refused(tmp_path, base):
    d = copy.deepcopy(base)
    d["steps"][0]["text"] = "{segreto}"
    assert any("not a declared parameter" in e for e in lc.check(_write(tmp_path, d), tmp_path))


def test_network_must_be_declared(tmp_path, base):
    d = copy.deepcopy(base)
    del d["program"]["network"]
    assert any("network must be" in e for e in lc.check(_write(tmp_path, d), tmp_path))


def test_an_image_in_the_library_is_refused(tmp_path):
    p = tmp_path / "linux" / "kate" / "ritaglio.png"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"\x89PNG")
    assert any("only .json" in e for e in lc.check(p, tmp_path))

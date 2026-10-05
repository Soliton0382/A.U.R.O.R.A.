# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Exam values over time (owner, 2026-10-05): read by the local model, sealed, a series per test, corrected by hand."""
from types import SimpleNamespace

from aurora import hlt_labs, hlt_store

MARCH = ('[{"test": "GLUCOSIO", "name": "glucosio", "value": "98", "unit": "mg/dL", "low": 70, "high": 100, '
         '"date": "2026-03-02"}, {"test": "Colesterolo totale", "name": "colesterolo totale", "value": "215,5", '
         '"unit": "mg/dL", "low": null, "high": 200, "date": "2026-03-02"}, {"test": "Note", "name": "nota", "value": "n.d."}]')
SEPTEMBER = ('[{"test": "Glucosio", "name": "Glucosio", "value": 104, "unit": "mg/dL", "low": 70, "high": 100, '
             '"date": "2026-09-14"}]')


class Reader:
    def __init__(self, answer):
        self.answer, self.read = answer, []

    def complete(self, system, user, max_tokens, think=False):
        self.read.append(user)
        return SimpleNamespace(answer=self.answer)


def test_values_are_read_kept_sealed_and_shown_over_time(cfg):
    a = hlt_store.add_document(cfg, "exams", "marzo.txt", b"GLUCOSIO 98 mg/dL (70-100)\nCOLESTEROLO 215,5")
    b = hlt_store.add_document(cfg, "exams", "settembre.txt", b"Glucosio 104 mg/dL (70-100)")
    assert len(hlt_labs.extract(cfg, a["id"], Reader(MARCH))) == 2            # the row without a number is dropped
    hlt_labs.extract(cfg, b["id"], Reader(SEPTEMBER))
    raw = (hlt_store._dir(cfg, "exams") / "values.sealed").read_bytes()
    assert b"glucosio" not in raw.lower()                                    # sealed, not readable on disk
    s = {x["key"]: x for x in hlt_labs.series(cfg)}
    glu = s["glucosio"]
    assert [p["value"] for p in glu["points"]] == [98.0, 104.0] and glu["trend"] == "up" and glu["out_of_range"]
    assert s["colesterolo totale"]["last"]["value"] == 215.5 and s["colesterolo totale"]["out_of_range"]
    assert hlt_labs.series(cfg)[0]["out_of_range"]                           # those outside their range first


def test_the_owner_corrects_a_value_and_a_deleted_exam_takes_its_values_away(cfg):
    a = hlt_store.add_document(cfg, "exams", "marzo.txt", b"GLUCOSIO 98")
    rows = hlt_labs.extract(cfg, a["id"], Reader(MARCH))
    glu = next(r for r in rows if r["key"] == "glucosio")
    fixed = hlt_labs.correct(cfg, glu["id"], {"value": "89", "high": "99"})
    assert fixed["value"] == 89.0 and fixed["high"] == 99.0 and fixed["by"] == "owner"
    hlt_labs.extract(cfg, a["id"], Reader(MARCH))                            # read again: its own values replaced
    assert len([r for r in hlt_labs.values(cfg) if r["doc"] == a["id"]]) == 2
    assert hlt_labs.remove(cfg, doc=a["id"]) == 2 and hlt_labs.series(cfg) == []

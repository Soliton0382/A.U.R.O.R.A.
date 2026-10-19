# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""BFCL's AST checker written again (owner, 19 Oct: «parti con il set BFCL»): the calls read from the answer and never
run; the name, the arguments required and allowed, the values compared as BFCL does; no call is right when nothing
fits. Invented functions."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "script"))
import bench_bfcl as B  # noqa: E402

FUNCS = [{"name": "garden.water", "description": "Water a garden bed.",
          "parameters": {"type": "dict", "properties": {"bed": {"type": "string"}, "litres": {"type": "float"},
                                                         "plants": {"type": "array"}, "when": {"type": "string"}},
                         "required": ["bed", "litres"]}},
         {"name": "garden.prune", "description": "Prune a plant.",
          "parameters": {"type": "dict", "properties": {"plant": {"type": "string"}}, "required": ["plant"]}}]
GOLD = [{"garden.water": {"bed": ["North bed", "north"], "litres": [5.0], "plants": [["tomato", "basil"]], "when": ["", "now"]}}]
ITEM = {"category": "multiple", "functions": FUNCS, "gold": GOLD}


def right(text):
    return B.score(ITEM, text)


def test_the_call_is_read_however_it_is_wrapped():
    assert right('[garden.water(bed="North bed", litres=5.0, plants=["tomato", "basil"])]')["right"]
    assert right('```python\ngarden.water(bed="north", litres=5, plants=["Tomato", "basil"])\n```')["right"]
    assert right('<think>first the bed</think> [garden.water(bed="North Bed", litres=5.0, plants=["tomato","basil"], when="now")]')["right"]


def test_what_bfcl_refuses_is_refused():
    assert "garden.prune" in right('[garden.prune(plant="rose")]')["got"]
    assert "missing" in right('[garden.water(bed="north", plants=["tomato", "basil"])]')["got"]
    assert "has not got" in right('[garden.water(bed="north", litres=5.0, plants=["tomato", "basil"], soil="clay")]')["got"]
    assert "not among" in right('[garden.water(bed="south", litres=5.0, plants=["tomato", "basil"])]')["got"]
    assert "not among" in right('[garden.water(bed="north", litres=5.0, plants=["basil", "tomato"])]')["got"]   # order kept
    assert not right("I would water the north bed with five litres.")["right"]
    assert "2 calls" in right('[garden.water(bed="north", litres=5.0, plants=["tomato", "basil"]), garden.prune(plant="x")]')["got"]


def test_the_values_compared_as_bfcl_does():
    assert B.same("New-York, NY", "new york ny") and B.same(5, 5.0) and not B.same(True, 1)
    assert B.same({"a": 1, "b": "x"}, {"a": [1], "b": ["X", ""]}) and B.same({"a": 1}, {"a": [1], "b": [""]})
    assert not B.same({"a": 1, "c": 2}, {"a": [1]})


def test_an_empty_answer_is_never_right():
    # C358: a thinking cut by the token or time limit leaves no text — not an abstention
    item = {"category": "irrelevance", "functions": FUNCS, "gold": []}
    assert B.score(item, "") == {"right": False, "got": "no answer"}
    assert B.score(item, "  \n")["right"] is False


def test_irrelevance_is_right_only_without_a_call():
    item = {"category": "irrelevance", "functions": FUNCS, "gold": []}
    assert B.score(item, "None of these functions can tell the weather.")["right"]
    assert not B.score(item, '[garden.prune(plant="rose")]')["right"]


def test_the_items_carry_bfcls_own_prompt():
    rows = [{"id": "x_1", "question": [[{"role": "user", "content": "Water the north bed."}]], "function": FUNCS,
             "ground_truth": GOLD}]
    it = B.items(rows, "multiple")[0]
    assert it["prompt"].startswith(B.SYSTEM) and it["prompt"].endswith("Water the north bed.") and it["kind"] == "bfcl"

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A grid puzzle solved as a verified program (ROADMAP 105): only a rule that reproduces every example answers."""
import shutil
from types import SimpleNamespace

import pytest

from aurora import kno_grid

PUZZLE = """Puzzle: trova la regola.

Esempio 1
INPUT:
1 0
0 0
OUTPUT:
0 1
0 0

Esempio 2
INPUT:
2 3 0
OUTPUT:
0 3 2

TEST
INPUT:
4 0 5
6 0 0

Alla fine scrivi «Risposta:» e sotto la griglia."""

MIRROR = "```python\ndef transform(grid):\n    return [row[::-1] for row in grid]\n```"
SAME = "```python\ndef transform(grid):\n    return grid\n```"


def in_process(code, inputs):
    ns = {}
    exec(code, ns)
    return [ns["transform"]([r[:] for r in g]) for g in inputs]


def scripted(*replies):
    asked = []
    it = iter(replies)
    model = SimpleNamespace(complete=lambda system, text, n, think=False: asked.append(text) or
                            SimpleNamespace(answer=next(it)))
    return SimpleNamespace(_for=lambda role: model), asked


def test_the_grids_of_a_puzzle_are_its_examples_and_its_test():
    examples, test = kno_grid.puzzle(PUZZLE)
    assert examples == [([[1, 0], [0, 0]], [[0, 1], [0, 0]]), ([[2, 3, 0]], [[0, 3, 2]])]
    assert test == [[4, 0, 5], [6, 0, 0]]
    assert kno_grid.puzzle("Quanto fa 2 + 2?") is None
    assert kno_grid.puzzle("1 2\n\n3 4\n\n5 6\n\n7 8") is None               # an even number: no test alone


def test_a_rule_is_given_only_after_it_reproduces_every_example(monkeypatch):
    monkeypatch.setattr(kno_grid, "run", in_process)
    p, asked = scripted(SAME, MIRROR)
    seen = []
    out = kno_grid.solve(p, PUZZLE, lambda e, d: seen.append(d))
    assert out["text"].endswith("Risposta:\n5 0 4\n0 0 6")
    assert [d["ok"] for d in seen] == [False, True] and seen[0]["wrong"] == [1, 2]
    assert "fails on example 1" in asked[1]                                    # the second try sees why


def test_a_rule_that_never_fits_leaves_the_puzzle_to_the_reasoning(monkeypatch):
    monkeypatch.setattr(kno_grid, "run", in_process)
    p, _ = scripted(SAME, "no code at all")
    assert kno_grid.solve(p, PUZZLE, lambda e, d: None) is None
    p, asked = scripted("", MIRROR)                                          # no answer: no second try
    assert kno_grid.solve(p, PUZZLE, lambda e, d: None) is None and len(asked) == 1
    monkeypatch.setattr(kno_grid, "run", lambda code, inputs: None)            # no cage: nothing is run
    p, _ = scripted(MIRROR)
    assert kno_grid.solve(p, PUZZLE, lambda e, d: None) is None


@pytest.mark.skipif(not shutil.which("bwrap"), reason="no bubblewrap: no cage")
def test_the_rule_runs_in_a_cage_without_network_or_home():
    assert kno_grid.run("def transform(g):\n    return [r[::-1] for r in g]\n", [[[1, 2]]]) == [[[2, 1]]]
    out = kno_grid.run("import urllib.request\ndef transform(g):\n    urllib.request.urlopen('http://1.1.1.1', "
                       "timeout=3)\n    return g\n", [[[1]]])
    assert "error" in out[0]
    assert kno_grid.run("def transform(g):\n    while True: pass\n", [[[1]]]) is None


def test_the_program_is_tried_only_with_a_cloud_model_writing_it(monkeypatch):
    """M221: the local model wrote a rule for 1 puzzle of 6; the other 5 cost about 300 s each for nothing."""
    from aurora import mdl_router
    p = SimpleNamespace(cfg={})
    monkeypatch.setattr(mdl_router, "assignments", lambda cfg: {"synthesis": {"provider": "local", "model": ""}})
    assert not kno_grid.worth(p)
    monkeypatch.setattr(mdl_router, "assignments", lambda cfg: {"synthesis": {"provider": "claude_code", "model": "sonnet"}})
    assert kno_grid.worth(p)

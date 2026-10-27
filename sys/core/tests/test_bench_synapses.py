# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The synapses' comparison (bench_synapses.py): its judge reads the reasoner's real answer (C408: it asked .text)."""
import sys
from pathlib import Path

from aurora.mdl_llm import Completion

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "script"))
import bench_synapses as B  # noqa: E402


class LLM:
    def __init__(self, answer):
        self.answer = answer

    def complete(self, system, user, max_tokens):
        return Completion(self.answer, "", 1, 0.1, False)


def test_the_judge_reads_a_digit_from_the_reasoner():
    assert B.judge(LLM("2"), "q", "p") == 2
    assert B.judge(LLM(" 1."), "q", "p") == 1
    assert B.judge(LLM("not relevant"), "q", "p") == 0

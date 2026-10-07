# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""What a run of the answer pipeline leaves: its trail (the events, the reasoning apart), the answer, and the
synapses its cited passages strengthen (moved from kno_answer, 7 October 2026: one module per part)."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import sys_config


class Trail:
    """The path of a run, kept with the answer: every event but the streamed text; the reasoning apart."""
    MAX_TEXT = 2000          # characters per string field of an event
    MAX_THOUGHT = 30000      # characters of reasoning kept

    def __init__(self):
        self.steps: list[list] = []
        self.thought = ""

    def add(self, event: str, payload: dict) -> None:
        if event == "synthesis.delta":
            if payload.get("kind") == "thought" and len(self.thought) < self.MAX_THOUGHT:
                self.thought += payload.get("text", "")
            return
        self.steps.append([event, self._cut(payload)])

    def _cut(self, v):
        if isinstance(v, str):
            return v if len(v) <= self.MAX_TEXT else v[:self.MAX_TEXT] + "…"
        if isinstance(v, dict):
            return {k: self._cut(x) for k, x in v.items()}
        if isinstance(v, list):
            return [self._cut(x) for x in v]
        return v

    def export(self) -> dict:
        return {"trace": self.steps, "thought": self.thought[:self.MAX_THOUGHT]}


def hebb(cfg: sys_config.Config, sources: list[dict]) -> int:
    """The knowledge passages cited together after the verification wire (kno_synapse.strengthen); returns the pairs.
    A function of its own since C151: the line inside _answer crashed every cited answer for 50 minutes untested."""
    known = [(x["sid"], x["domain"], x["source"]) for x in sources if x["domain"] not in ("conversation", "reflection")]
    if len({k[1] for k in known}) < 2:
        return 0
    from . import kno_synapse
    return kno_synapse.strengthen(cfg, known)


@dataclass
class Answer:
    run_id: str
    question: str
    text: str
    abstained: bool
    sources: list[dict] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    seconds: float = 0.0
    mode: str = "knowledge"                        # knowledge | self
    speed: dict | None = None                      # {"tokens", "per_second"} of the writing call, as measured
    suggestions: list = field(default_factory=list)  # follow-up questions with their sources (kno_followup.suggest)
    came_from: str = ""                            # kno_think: vault | web | memory | deep ("" for the vault pipeline)
    learn: bool = False                            # an explanation the vault lacked: studied at night (kno_study)

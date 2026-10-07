# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The agent's honest record and its context window (moved from agt_loop, 7 October 2026: one module per part).
A mixin of agt_loop.Agent: what a report may claim only if the log of calls holds it, written by the code; and the
conversation shortened, oldest tool results first, so that it fits the model's window with room for the answer."""
from __future__ import annotations

import re

from .mdl_llm import chatml_turns

SEP = "__"                                               # plugin__tool: a function name the model can write


class AgentReport:
    # ---- what was really done: written by the code, not by the model ----------------------------
    # What a report may claim only if the log of calls contains it.
    CLAIMS = {
        "sandbox": (re.compile(r"(?i)ho creato (?:una )?sandbox|created a sandbox"), ("sandbox_create",)),
        "edit": (re.compile(r"(?i)\b(?:ho (?:applicato|corretto|modificato|sostituito|cambiato)|sostituit[oa] l|"
                            r"fix applicat|i fixed|i changed)"), ("sandbox_replace", "sandbox_write", "project_write_file")),
        # a project's files and tests count too (C134: a project's report was flagged as false)
        "tests": (re.compile(r"(?i)test (?:passano|superati|verdi)|ho eseguito i test|tests? pass"),
                  ("run_tests", "run_in_project")),
        "proposal": (re.compile(r"(?i)ho proposto|proposta inviata|in attesa (?:della tua )?approvazione|i proposed"),
                     ("propose_change",)),
    }
    DONE = re.compile(r"(?i)\b(?:ho|è stat[oa]|sono stat[ie]) (?:pubblicat|caricat|inviat|postat|condivis)|"
                      r"\bi (?:posted|published|sent|uploaded)")

    def _count(self, *suffixes: str) -> int:
        return sum(1 for name, ok in self.ledger if ok and name.split(SEP)[-1] in suffixes)

    def _record(self) -> str:
        own = ("list_files", "read_file", "search_code", "logs_inventory", "read_log", "sandbox_read", "sandbox_diff")
        reads = self._count(*own) + sum(1 for name, ok in self.ledger if ok and name.split(SEP)[-1] not in own
                                        and getattr(self, "effects", {}).get(name) == "read")   # the plugins' reads too
        failed = sum(1 for _, ok in self.ledger if not ok)
        return (f"— Azioni eseguite (dal registro delle chiamate): {len(self.ledger)} chiamate; {reads} letture; "
                f"{self._count('sandbox_create')} sandbox create; {self._count('sandbox_replace', 'sandbox_write')} "
                f"modifiche in sandbox; {self._count('run_tests')} esecuzioni di test; "
                f"{self._count('propose_change')} proposte di modifica; "
                f"{self._count('project_write_file')} file scritti nei progetti; {self._count('run_in_project')} "
                f"esecuzioni nei progetti; {failed} chiamate non riuscite.")

    # "Non ho creato sandbox e non ho proposto modifiche" is not a claim (C155: a weather report was flagged for it)
    NEG = re.compile(r"(?i)\b(?:non|nessun\w*|senza|né|not|never|no|didn't|did not|without)\b[^.!?\n]{0,40}$")

    def _claims(self, rx: re.Pattern, text: str) -> bool:
        """A match of a claim that is not denied in the words just before it."""
        return any(not self.NEG.search(text[max(0, m.start() - 60):m.start()]) for m in rx.finditer(text))

    def _honest(self, summary: str) -> str:
        """Every claim the log of calls does not support gets a warning at the top of the report; actions still
        waiting for the owner are listed at the end, whatever the model wrote."""
        pending = getattr(self, "pending", [])
        false = [what for what, (rx, tools) in self.CLAIMS.items() if self._claims(rx, summary) and not self._count(*tools)
                 and not (what == "proposal" and pending)]       # "waiting for your approval" is true for a post
        if pending:
            head = ("⏳ Proposto, non ancora fatto — aspetta la tua approvazione (🛠️ Riparazioni): "
                    + ", ".join(dict.fromkeys(pending)) + ".")
            if self.DONE.search(summary):
                head = "⚠️ Niente è stato ancora pubblicato o inviato.\n" + head
            summary = head + "\n\n" + summary
        if false:
            self.log.warning("agent report claims actions that were not performed: %s", ", ".join(false))
            names = {"sandbox": "sandbox create", "edit": "modifiche al codice", "tests": "test eseguiti",
                     "proposal": "proposte di modifica"}
            return ("⚠️ Attenzione: il resoconto dichiara " + ", ".join(names[f] for f in false)
                    + " che il registro delle chiamate NON contiene: fa fede il registro in fondo.\n\n" + summary)
        return summary

    # ---- context: the conversation must fit the model's window with room for the answer --------
    KEEP_FULL = 4                                       # the latest tool results stay whole

    def _tokens(self, messages: list[dict]) -> int:
        prompt = chatml_turns(messages, True)
        try:
            return self._model().count_tokens(prompt)
        except Exception:                               # no tokenizer at hand: a safe estimate
            return len(prompt) // 3

    def _fit(self, messages: list[dict], want: int, emit) -> int:
        """Shorten the oldest tool results until `want` tokens fit; returns the tokens left for the answer."""
        ctx = getattr(self._model(), "context_tokens", 0) or self.cfg["AURORA_LLM_CTX"]
        used = self._tokens(messages)
        tools = [i for i, m in enumerate(messages) if m["role"] == "tool"]
        cut = 0
        for i in tools[:-self.KEEP_FULL] if len(tools) > self.KEEP_FULL else []:
            if ctx - used >= want + 256:
                break
            if len(messages[i]["content"]) > 500:
                messages[i]["content"] = messages[i]["content"][:400] + "\n[shortened: an older result]"
                cut += 1
                used = self._tokens(messages)
        dropped = 0
        while ctx - used < want + 256 and len(messages) > 2 + 2 * self.KEEP_FULL:
            # shortening was not enough (a long run, C68): the oldest steps go, the goal and the latest stay
            del messages[2]
            dropped += 1
            if dropped % 4 == 0 or ctx - used < want + 256:
                used = self._tokens(messages)
        if dropped:
            note = f"[{dropped} earlier messages of this run were removed to fit the context]"
            if not messages[2]["content"].startswith("[") or "removed to fit" not in messages[2]["content"]:
                messages.insert(2, {"role": "user", "content": note})
            used = self._tokens(messages)
        if cut or dropped:
            emit("agent.compact", {"shortened": cut, "removed": dropped, "prompt_tokens": used})
        return max(256, ctx - used - 256)

    # ---- the loop ----------------------------------------------------------------------------

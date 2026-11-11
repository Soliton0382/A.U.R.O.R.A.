# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""12 Nov: a usage limit reached came back from the CLI's stream as an error «result» with no text; the chat answered
nothing. Now the stream raises, and the router's fallback answers with the local model."""
import io
import json
from contextlib import contextmanager

import pytest

from aurora import mdl_cloud


class _P:
    def __init__(self, lines, code=0):
        self.stdin, self.stdout, self.stderr, self.returncode = io.StringIO(), iter(lines), io.StringIO(""), code

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        pass


def _llm(monkeypatch, lines, code=0):
    llm = mdl_cloud.ClaudeCodeLLM.__new__(mdl_cloud.ClaudeCodeLLM)
    llm.cwd, llm.log = None, None

    @contextmanager
    def command(*a):
        yield ["claude"]
    monkeypatch.setattr(llm, "_command", command, raising=False)
    monkeypatch.setattr(llm, "_env", lambda n: {}, raising=False)
    monkeypatch.setattr(llm, "_account", lambda d, s: None, raising=False)
    monkeypatch.setattr(mdl_cloud.subprocess, "Popen", lambda *a, **k: _P(lines, code))
    return llm


def test_a_limit_reached_in_the_stream_is_an_error_not_an_empty_answer(monkeypatch):
    llm = _llm(monkeypatch, [json.dumps({"type": "result", "is_error": True, "result": "You've hit your limit"}) + "\n"])
    with pytest.raises(RuntimeError, match="limit"):
        list(llm.stream("s", "u", 100))


def test_a_cli_that_dies_saying_nothing_is_an_error(monkeypatch):
    with pytest.raises(RuntimeError):
        list(_llm(monkeypatch, [], code=1).stream("s", "u", 100))


def test_a_normal_stream_still_passes(monkeypatch):
    ev = {"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "ciao"}}}
    out = list(_llm(monkeypatch, [json.dumps(ev) + "\n", json.dumps({"type": "result", "usage": {}}) + "\n"]).stream("s", "u", 9))
    assert out == [("answer", "ciao")]

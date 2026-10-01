# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import unicodedata
from dataclasses import replace

import pytest

from aurora import sol_schema as S

TAX = S.load_taxonomy()
TEXT = "The soliton keeps its shape while it travels, because dispersion and nonlinearity balance. " * 5


def knowledge(text=TEXT, **kw):
    args = dict(domain="physics", kind="knowledge", lang="en", source_id="arxiv:2401.00001", title="A paper")
    args.update(kw)
    return S.Soliton.new(text, **args)


def test_normalize_is_canonical():
    composed = unicodedata.normalize("NFC", "perché")
    decomposed = unicodedata.normalize("NFD", "perché")
    assert S.normalize(decomposed) == composed
    assert S.normalize("  a \t b\r\n\r\n\r\n\nc  ") == "a b\n\nc"


def test_knowledge_identity_is_the_text():
    a = knowledge(source_id="arxiv:1")
    b = knowledge(source_id="arxiv:2", title="another title")
    assert a.sid == b.sid and len(a.sid) == 32
    assert knowledge(TEXT + " More.").sid != a.sid


def test_memory_identity_is_the_event():
    a = S.Soliton.new("ok", "conversation", "conversation", "it", "session:1", created_at="2026-09-30T10:00:00.000+00:00")
    b = S.Soliton.new("ok", "conversation", "conversation", "it", "session:1", created_at="2026-09-30T10:05:00.000+00:00")
    assert a.sid != b.sid


def test_birth_state():
    assert knowledge().consolidated and knowledge().consolidated_at
    stm = S.Soliton.new("ciao", "conversation", "conversation", "it", "session:1")
    assert not stm.consolidated and stm.consolidated_at is None


def test_row_round_trip():
    s = knowledge(extra={"url": "https://arxiv.org/abs/2401.00001", "authors": ["A", "B"]})
    assert S.Soliton.from_row(s.to_row()) == s


def test_valid_solitons_pass():
    assert S.validate(knowledge(), TAX, min_chars=300) == []
    assert S.validate(S.Soliton.new("ok", "conversation", "conversation", "it", "session:1"), TAX, 300) == []


@pytest.mark.parametrize("change, expected", [
    (dict(domain="astrology"), "not in the taxonomy"),
    (dict(domain="conversation"), "does not belong"),
    (dict(lang="ita"), "ISO 639-1"),
    (dict(source_id=""), "source_id"),
    (dict(chunk_index=3, chunk_count=3), "out of range"),
    (dict(sid="0" * 32), "sid does not match"),
    (dict(consolidated_at=None), "consolidated without"),
    (dict(created_at="yesterday"), "ISO timestamp"),
    (dict(text="  spaced  "), "not normalized"),
])
def test_invalid_solitons_are_refused_with_the_reason(change, expected):
    problems = S.validate(replace(knowledge(), **change), TAX)
    assert any(expected in p for p in problems), problems


def test_short_tail_is_refused_short_complete_document_and_memory_are_not():
    tail = knowledge("Too short.", chunk_index=3, chunk_count=4)
    assert any("shorter" in p for p in S.validate(tail, TAX, min_chars=300))
    article = S.Soliton.new("Art. 1571. La locazione è il contratto col quale una parte si obbliga a far godere "
                            "all'altra una cosa mobile o immobile per un dato tempo.", "law_it", "knowledge",
                            "it", "normattiva:cc:1571")
    assert S.validate(article, TAX, min_chars=300) == []
    turn = S.Soliton.new("sì", "conversation", "conversation", "it", "session:1")
    assert S.validate(turn, TAX, min_chars=300) == []


def test_reflection_must_live_in_reflection():
    s = S.Soliton.new("A thought.", "conversation", "reflection", "en", "aurora")
    assert any("belongs in domain 'reflection'" in p for p in S.validate(s, TAX))

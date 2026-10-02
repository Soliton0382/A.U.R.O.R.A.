# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
from aurora import mdl_cloud, txt_compress
from aurora.kno_answer import Pipeline

TEXT = ("Il sole è una stella. La Terra orbita attorno al sole in un anno. I gatti amano dormire. "
        "La luce del sole impiega 8 minuti a raggiungere la Terra [2]. Il pane si fa con farina. "
        "Le orbite sono ellittiche secondo Keplero. Oggi piove a Milano. Il caffè è amaro.")


def test_compression_keeps_the_relevant_and_the_cited_sentences():
    out, stats = txt_compress.compress("quanto impiega la luce del sole ad arrivare sulla Terra?", TEXT, 35)
    assert "8 minuti" in out and "[2]" in out
    assert "gatti" not in out and "caffè" not in out
    assert stats["chars_out"] < stats["chars_in"] and stats["sentences_out"] == 3


def test_short_text_is_left_whole():
    out, stats = txt_compress.compress("sole", "Una frase. Due frasi.", 35)
    assert out == "Una frase. Due frasi." and stats["chars_out"] == stats["chars_in"]


def test_reasoner_choice_and_rule_nine(cfg, monkeypatch):
    local = object()
    assert mdl_cloud.make_reasoner(cfg, local) is local                       # default: local
    cfg.values["AURORA_REASONER_PROVIDER"] = "claude_code"
    monkeypatch.setattr(mdl_cloud.sys_ethics, "exempt", lambda c: False)
    assert mdl_cloud.make_reasoner(cfg, local) is local                       # rule 9: refused
    monkeypatch.setattr(mdl_cloud.sys_ethics, "exempt", lambda c: True)
    assert isinstance(mdl_cloud.make_reasoner(cfg, local), mdl_cloud.ClaudeCodeLLM)
    cfg.values["AURORA_REASONER_PROVIDER"] = "anthropic"
    assert isinstance(mdl_cloud.make_reasoner(cfg, local), mdl_cloud.AnthropicLLM)


def test_turns_are_flattened_for_a_single_prompt_provider():
    system, text = mdl_cloud._flatten([{"role": "system", "content": "S"}, {"role": "user", "content": "a"},
                                       {"role": "assistant", "content": "b"}, {"role": "tool", "content": "r"}])
    assert system == "S" and text.index("USER:\na") < text.index("ASSISTANT:\nb") < text.index("<tool_response>\nr")


def test_anthropic_turns_merge_consecutive_roles():
    system, msgs = mdl_cloud.AnthropicLLM._turns([{"role": "system", "content": "S"}, {"role": "user", "content": "a"},
                                                  {"role": "assistant", "content": "b"}, {"role": "tool", "content": "r"},
                                                  {"role": "user", "content": "c"}])
    assert system == "S" and [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert "<tool_response>\nr" in msgs[2]["content"] and msgs[2]["content"].endswith("c")

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


def test_every_cloud_provider_is_masked_and_nothing_turns_it_off(cfg, monkeypatch):
    """Owner, 2026-10-05: every call that leaves for a cloud model is masked; no setting, no provider escapes it."""
    from aurora import mdl_router
    monkeypatch.setattr(mdl_router.sys_ethics, "exempt", lambda c: True)
    local = object()
    for provider in [p for p, spec in mdl_router.PROVIDERS.items() if spec["kind"] != "local"]:
        monkeypatch.setattr(mdl_router, "assignments", lambda c, p=provider: {"agent": {"provider": p, "model": "m"}})
        m = mdl_router.model_for("agent", local, cfg)
        assert isinstance(m.primary, mdl_router.MaskedLLM), provider
    assert not hasattr(mdl_cloud, "make_reasoner")           # the old unmasked reasoner is gone


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


def test_claude_code_runs_with_no_tool_and_no_mcp_server(cfg):
    """C133: without --strict-mcp-config the CLI loaded the account's claude.ai connectors; the agent's model saw
    them, failed on Aurora's tools and could have acted on the owner's account."""
    cmd = mdl_cloud.ClaudeCodeLLM(cfg, "opus")._cmd("sys", False, 100)
    assert "--strict-mcp-config" in cmd and "--mcp-config" not in cmd
    assert cmd[cmd.index("--tools") + 1] == "" and cmd[cmd.index("--setting-sources") + 1] == ""


def test_claude_code_gets_an_output_ceiling_and_a_runaway_turn_comes_back_truncated(cfg, monkeypatch):
    # C313: the CLI ignores max_tokens; one agent turn wrote 128,159 tokens in 10 minutes
    import json as _json
    import subprocess as _sp
    from aurora import mdl_cloud
    seen = {}

    def run(cmd, **k):
        seen["env"] = k.get("env") or {}
        return _sp.CompletedProcess(cmd, 1, _json.dumps({"is_error": True, "usage": {"output_tokens": 4096},
                                                         "result": "Claude's response exceeded the 4096 output token maximum."}), "")
    monkeypatch.setattr(mdl_cloud.subprocess, "run", run)
    monkeypatch.setattr(mdl_cloud.ClaudeCodeLLM, "_account", lambda self, d, s: None)
    llm = mdl_cloud.ClaudeCodeLLM.__new__(mdl_cloud.ClaudeCodeLLM)
    llm.cfg, llm.bin, llm.model, llm.cwd = cfg, "claude", "haiku", None
    out = llm.complete("system", "user", 1500)
    assert seen["env"]["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "4096" and out.truncated and out.answer == ""
    assert mdl_cloud.ClaudeCodeLLM._cap(28000)["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "56000"
    assert mdl_cloud.ClaudeCodeLLM._cap(10 ** 6)["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "64000"

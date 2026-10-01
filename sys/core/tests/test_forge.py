# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import pytest

from aurora import agt_forge as F

GOOD = {"name": "harvest_stats", "version": "1.0", "kind": "tool", "command": ["{python}", "server.py"], "env": [],
        "requires": [], "effects": {"*": "read"}, "sandbox": {"network": False}, "tests": [{"tool": "x", "args": {}}]}
CODE = 'from mcp.server.mcpserver import MCPServer\nserver = MCPServer("x")\nif __name__ == "__main__":\n    server.run("stdio")\n'


def test_the_reply_needs_both_blocks():
    m, code = F.parse_reply('ok\n```json\n{"name": "a"}\n```\n```python\nprint(1)\n```')
    assert m == {"name": "a"} and code == "print(1)\n"
    with pytest.raises(ValueError):
        F.parse_reply("```python\nprint(1)\n```")


def test_checks_name_command_tests_secrets_and_code():
    assert F.check(GOOD, CODE, set()) == []
    errs = F.check({**GOOD, "name": "Bad-Name", "command": ["bash", "x.sh"], "tests": [], "requires": ["AURORA_API_KEY"]},
                   "def (:", {"harvest_stats"})
    assert len(errs) == 6
    assert any("exists already" in e for e in F.check(GOOD, CODE, {"harvest_stats"}))


def test_only_read_without_writes_or_network_is_installed_alone():
    assert F.read_only(GOOD)
    assert not F.read_only({**GOOD, "sandbox": {"network": True}})
    assert not F.read_only({**GOOD, "sandbox": {}})                                 # network must be said false
    assert not F.read_only({**GOOD, "sandbox": {"network": False, "write": ["AURORA_PROJECTS_DIR"]}})
    assert not F.read_only({**GOOD, "effects": {"*": "read", "send": "external"}})
    assert not F.read_only({**GOOD, "effects": {}})


def test_the_forge_never_looks_at_secrets_memory_or_the_owners_files(cfg):
    (cfg.root / ".env").write_text("AURORA_API_KEY=secret\n") if not (cfg.root / ".env").exists() else None
    out = F.peek(cfg, [".env", "sys/vault", "usr/uploads/x.jpg", "../../etc/passwd"])
    assert out.count("(not allowed)") == 3 and "secret" not in out
    assert "(not allowed)" in F.peek(cfg, ["../../etc/passwd"]) or "(not found)" in F.peek(cfg, ["../../etc/passwd"])


def test_a_need_is_queued_once(cfg):
    a = F.request(cfg, "Leggere le mail di ieri", "routine mail", "run1", "r1")
    b = F.request(cfg, "leggere le mail di ieri", "again", "run2")
    assert a["id"] == b["id"] and len(F.requests(cfg)) == 1
    assert F.next_pending(cfg)["id"] == a["id"]
    F.update(cfg, a["id"], status="building", started=__import__("time").time())
    assert F.next_pending(cfg) is None                                              # one build at a time


def test_the_sample_shows_each_kind_of_line_with_counts_and_the_line_untouched():
    lines = [f"2026-10-01T10:00:0{i}.000+02:00 INFO aurora.harvester normattiva:urn:nir:stato:legge:199{i}-01-01;{i} -> law_it: x"
             for i in range(5)] + ["2026-10-01T10:00:09.000+02:00 INFO aurora.harvester 2609.39022 -> programming: y"]
    out = F.kinds_of(lines, hours=24 * 3650)
    assert len(out) == 2 and out[0].startswith("# kind: 5 lines") and out[1].startswith("# kind: 1 lines")
    assert out[1].split("\n", 1)[1] == lines[-1]                                   # the example is the real line

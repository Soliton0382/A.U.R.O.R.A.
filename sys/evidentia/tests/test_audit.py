# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The case file's audit trail (27 Nov): appended, chained by SHA-256, verified from its first line; a line removed,
changed or moved is found; protected names masked before they are written; a bad case id refused."""
import json

import pytest

from evidentia import audit


def _steps(n):
    return [{"event": "agent.tool", "payload": {"tool": "find_passages", "args": {"q": f"volo {i}"}}} for i in range(n)]


def test_the_trail_is_chained_and_verifies(tmp_path):
    assert audit.append(tmp_path, "c1", _steps(3), "chat") == 3
    assert audit.append(tmp_path, "c1", _steps(2), "lead worker #4") == 2
    v = audit.verify(tmp_path, "c1")
    assert v == {"ok": True, "lines": 5, "broken_at": None, "why": ""}
    rows = audit.read(tmp_path, "c1")
    assert [r["n"] for r in rows] == [1, 2, 3, 4, 5] and rows[0]["prev"] == audit.GENESIS
    assert rows[3]["who"] == "lead worker #4" and rows[1]["prev"] == rows[0]["hash"]


@pytest.mark.parametrize("tamper", ["change", "remove", "swap"])
def test_a_tampered_line_is_found(tmp_path, tamper):
    audit.append(tmp_path, "c1", _steps(4), "chat")
    f = tmp_path / "audit" / "c1.jsonl"
    lines = f.read_text().splitlines()
    if tamper == "change":
        row = json.loads(lines[1]); row["payload"] = row["payload"].replace("volo 1", "volo 9"); lines[1] = json.dumps(row)
    elif tamper == "remove":
        del lines[2]
    else:
        lines[1], lines[2] = lines[2], lines[1]
    f.write_text("\n".join(lines) + "\n")
    v = audit.verify(tmp_path, "c1")
    assert not v["ok"] and v["broken_at"] in (2, 3)


def test_protected_names_are_masked_and_big_payloads_cut(tmp_path):
    audit.append(tmp_path, "c2", [{"event": "x", "payload": "Mario Rossi " + "a" * 9000}], "chat",
                 mask=lambda s: s.replace("Mario Rossi", "[protetto]"))
    row = audit.read(tmp_path, "c2")[0]
    assert "Mario Rossi" not in row["payload"] and "[protetto]" in row["payload"] and "[cut:" in row["payload"]
    assert audit.verify(tmp_path, "c2")["ok"]


@pytest.mark.parametrize("bad", ["../x", "a/b", "", "x" * 65])
def test_a_bad_case_id_is_refused(tmp_path, bad):
    with pytest.raises(ValueError):
        audit.append(tmp_path, bad, _steps(1), "chat")


def test_entries_must_be_steps(tmp_path):
    with pytest.raises(ValueError):
        audit.append(tmp_path, "c3", ["not a step"], "chat")

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Models → Come ragiona (ROADMAP 109): which of the four choices the roles describe, and «il meglio dei due» as roles."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
JS = HERE.parent / "webui" / "js" / "modules" / "models_presets.js"
IDS = ["route", "translate", "gate", "extract", "synthesis", "verify", "self", "agent", "rem", "forge_write", "forge_judge",
       "vision", "service"]
CLOUD = {"extract", "synthesis", "self", "agent"}


def roles(cloud: dict) -> list[dict]:
    return [{"id": i, "provider": cloud.get(i, ("local", ""))[0], "model": cloud.get(i, ("local", ""))[1]} for i in IDS]


def run(cases: dict) -> dict:
    return json.loads(subprocess.run(["node", str(HERE / "js" / "models_presets.mjs"), JS.as_uri(), json.dumps(cases)],
                                     capture_output=True, text=True, check=True).stdout)


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_the_choice_the_roles_describe():
    cc = ("claude_code", "sonnet")
    out = run({"local": {"roles": roles({}), "mode": "local"},
               "best": {"roles": roles({r: cc for r in CLOUD}), "mode": "mixed"},
               # the owner's own: the forge on Opus does not change the choice
               "best_forge": {"roles": roles({**{r: cc for r in CLOUD}, "forge_write": ("claude_code", "opus"),
                                              "forge_judge": ("claude_code", "opus")}), "mode": "mixed"},
               "two_providers": {"roles": roles({"extract": cc, "synthesis": ("openai", "x"), "self": cc, "agent": cc}), "mode": "mixed"},
               "cloud": {"roles": roles({r: cc for r in IDS if r != "vision"}), "mode": "cloud_private"},
               "one_more": {"roles": roles({**{r: cc for r in CLOUD}, "gate": cc}), "mode": "mixed"}})
    assert out == {"local": "local", "best": "best", "best_forge": "best", "two_providers": "custom", "cloud": "cloud",
                   "one_more": "custom"}


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_the_best_of_both_keeps_the_forge_and_puts_four_steps_in_the_cloud():
    start = roles({"gate": ("claude_code", "sonnet"), "forge_write": ("claude_code", "opus")})
    out = run({"b": {"best": True, "roles": start, "provider": "claude_code", "model": "sonnet"}})["b"]
    assert {r for r, a in out.items() if a["provider"] != "local"} == CLOUD | {"forge_write"}
    assert out["forge_write"] == {"provider": "claude_code", "model": "opus"}
    assert out["gate"] == {"provider": "local", "model": ""} and out["synthesis"] == {"provider": "claude_code", "model": "sonnet"}

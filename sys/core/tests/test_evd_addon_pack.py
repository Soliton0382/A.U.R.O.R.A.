# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📦 the web handed to the investigation (owner, 12 Nov): the public people of the drawing, opened first, become
network-mapper leads; a private person never goes in, nor is named as a tie (local: never published)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

PACK = Path(__file__).resolve().parents[2] / "evidentia" / "addon" / "webui" / "evidentia_pack.js"
WEB = Path(__file__).resolve().parents[1] / "webui" / "js"
SCRIPT = """
const m = await import(process.argv[1]);
const a = {name: "Ann Example", public: true, open: true}, b = {name: "Bob Example", public: true};
const c = {name: "Cid Example", public: true}, p = {name: "", public: false, label: "private 1a2b3c"};
const nodes = new Map([["a", a], ["b", b], ["c", c], ["p", p]]);
const links = new Map([["a|b", {a, b, n: 5}], ["a|p", {a, b: p, n: 9}], ["b|c", {a: b, b: c, n: 30}]]);
const got = m.candidates(nodes, links);
console.log(JSON.stringify({got: got.map((x) => [x.node.name, x.open, x.weight, x.peers]), lead: m.lead(got[0], "Ann Example")}));
"""


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_the_package_holds_public_people_only_opened_first(tmp_path):
    # the add-on's pages import Aurora's modules by their address (/static/js/…): a copy points them at the files
    for f in PACK.parent.glob("*.js"):
        (tmp_path / f.name).write_text(f.read_text(encoding="utf-8").replace('"/static/js/', f'"{WEB.as_uri()}/'))
    out = json.loads(subprocess.run(["node", "--input-type=module", "-e", SCRIPT, str(tmp_path / PACK.name)], capture_output=True,
                                    text=True, check=True, timeout=30).stdout)
    assert [g[0] for g in out["got"]] == ["Ann Example", "Bob Example", "Cid Example"]   # opened first, then by weight
    assert out["got"][0] == ["Ann Example", True, 14, ["Bob Example"]]                   # the private tie never named
    lead = out["lead"]
    assert lead["agent"] == "network_mapper" and "Ann Example" in lead["what"] and "private" not in lead["why"]

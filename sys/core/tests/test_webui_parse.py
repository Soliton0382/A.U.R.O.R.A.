# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Every file of the WebUI parses as the ES module the browser loads (C419, 28 Oct: a «const» declared twice in
dj_player.js — the menu imports the DJ, so the whole interface stayed blue and empty; `node --check file.js` passed it,
reading the file as a script: only --input-type=module finds it)."""
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parent.parent / "webui" / "js"


@pytest.mark.skipif(not shutil.which("node"), reason="node")
def test_every_module_parses():
    bad = []
    for f in sorted(JS.rglob("*.js")):
        r = subprocess.run(["node", "--input-type=module", "--check"], input=f.read_text(encoding="utf-8"),
                           capture_output=True, text=True, timeout=30)
        if r.returncode:
            bad.append(f"{f.relative_to(JS)}: {(r.stderr.strip().splitlines() or ['?'])[-1][:200]}")
    assert not bad, "\n".join(bad)


@pytest.mark.skipif(not shutil.which("node"), reason="node")
def test_the_check_finds_a_declaration_twice():
    r = subprocess.run(["node", "--input-type=module", "--check"], input="export function f() { const a = 1; const a = 2; }",
                       capture_output=True, text=True, timeout=30)
    assert r.returncode and "already been declared" in r.stderr

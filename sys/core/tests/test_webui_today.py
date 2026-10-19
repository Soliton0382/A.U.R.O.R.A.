# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Oggi as widgets (owner, 19 Oct: «gestire la pagina oggi come se fosse un insieme di widget che uno può
personalizzare… il suggerimento su cosa fotografare»): the order and the hidden tiles read under node, a new tile coming
in at the end, every tile a method with its name in both languages, tonight's sky only when astro is on."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "webui"
TODAY = (WEB / "js" / "modules" / "today.js").read_text()
TILES = json.loads(re.search(r"const TILES = (\[[^\]]*\]);", TODAY).group(1))


def run(expr: str):
    js = f"const M = await import({json.dumps((WEB / 'js' / 'modules' / 'today_edit.js').as_uri())}); console.log(JSON.stringify({expr}))"
    out = subprocess.run(["node", "--input-type=module", "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout)


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_the_persons_order_first_a_new_tile_at_the_end_hidden_ones_out():
    all_ = ["news", "agenda", "sky", "stats"]
    assert run(f"M.arrange({json.dumps(all_)}, {{}})") == all_
    # an id no longer known dropped; «stats», never seen by this person, comes in at the end and shown
    assert run(f'M.arrange({json.dumps(all_)}, {{order: ["sky", "gone", "news", "agenda"]}})') == ["sky", "news", "agenda", "stats"]
    assert run(f'M.shown({json.dumps(all_)}, {{order: ["sky", "news", "agenda"], off: ["news"]}})') == ["sky", "agenda", "stats"]


def test_every_tile_a_method_and_a_name():
    assert TILES[0] == "news" and {"sky", "stats"} <= set(TILES)
    for tile in TILES:
        assert re.search(rf"\n  async {tile}\(\)", TODAY), tile
    for lang in ("it_IT", "en_US"):
        words = json.loads((WEB / "i18n" / f"{lang}.json").read_text())
        assert {f"today.tile.{x}" for x in TILES} <= set(words)
        assert {"today.edit", "today.edit_save", "today.sky", "today.stats"} <= set(words)
    assert "/static/js/modules/today_edit.js" in (WEB / "sw.js").read_text()


def test_tonights_sky_only_with_astro_on():
    body = TODAY[TODAY.index("async sky()"):TODAY.index("async stats()")]
    assert 'p.name === "astro" && p.enabled && p.available' in body and "return null" in body

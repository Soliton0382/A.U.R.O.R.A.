# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The collimator's picture read (owner, 19 Oct: «procedi con il secondario dalla foto dell'OCAL… una tab specifica»):
the secondary found and how round it is, its shadow reported but not judged, the centre spot against the collimator's
reflection, a drawtube cut by the picture not judged; the tab, its API and its words there. Drawn pictures."""
import asyncio
import io
import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from aurora import ast_ocal as O

ROOT = Path(__file__).resolve().parents[1]


def picture(sec=(400, 400, 260, 260), shadow=(380, 405, 90), ocal=(400, 405, 45), spot=(400, 405), lines=True):
    """A collimator's view: dark tube, the bright secondary (an ellipse when sec's radii differ), its dark shadow, the
    collimator's lighter ring with the dark centre spot; the program's coloured circles drawn over it."""
    im = Image.new("RGB", (800, 800), (40, 40, 40))
    d = ImageDraw.Draw(im)
    x, y, rx, ry = sec
    d.ellipse([x - rx, y - ry, x + rx, y + ry], fill=(235, 235, 230))
    x, y, r = shadow
    d.ellipse([x - r, y - r, x + r, y + r], fill=(55, 55, 55))
    x, y, r = ocal
    d.ellipse([x - r, y - r, x + r, y + r], fill=(130, 150, 140))
    x, y = spot
    d.ellipse([x - 9, y - 9, x + 9, y + 9], fill=(10, 10, 10))
    if lines:                                              # the program's circles and vanes, which must not matter
        d.ellipse([400 - 300, 400 - 300, 400 + 300, 400 + 300], outline=(220, 30, 30), width=2)
        d.line([0, 0, 800, 800], fill=(220, 220, 30), width=2)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def test_a_round_secondary_and_a_centred_primary():
    r = O.analyse(picture())
    sec = r["secondary"]
    assert abs(sec["x"] - 400) < 3 and abs(sec["r"] - 260) < 4 and sec["round"] > 0.99    # smaller than 900: as it is
    codes = {v["code"]: v["ok"] for v in r["verdict"]}
    assert codes["secondary_round"] and codes["primary"] and codes["shadow"] is None
    assert codes["drawtube_unseen"] is None and r["image"].startswith("data:image/jpeg;base64,")


def test_an_oval_secondary_is_said():
    codes = {v["code"]: v["ok"] for v in O.analyse(picture(sec=(400, 400, 270, 240)))["verdict"]}
    assert codes.get("secondary_oval") is False


def test_a_centre_spot_off_the_reflection_says_where():
    r = O.analyse(picture(spot=(418, 405)))
    v = next(x for x in r["verdict"] if x["code"] == "primary")
    assert v["ok"] is False and "destra" in v["text"] and r["spot"]["off"] > O.SPOT_OK


def test_the_shadow_off_the_middle_is_never_a_fault():
    r = O.analyse(picture(shadow=(368, 400, 90), ocal=(400, 405, 45), spot=(400, 405)))     # the ring still inside it
    assert all(v["ok"] is not False for v in r["verdict"])


def test_what_is_not_a_collimator_view_is_said():
    buf = io.BytesIO()
    Image.new("RGB", (300, 200), (120, 120, 120)).save(buf, "PNG")
    assert "secondario" in O.analyse(buf.getvalue())["error"]
    assert "immagine" in O.analyse(b"not a picture")["error"]


class Req:
    def __init__(self, body):
        self._b = body

    async def body(self):
        return self._b


def test_the_api_reads_the_picture_and_keeps_the_last_without_the_image(tmp_path, monkeypatch):
    from aurora.sys_config import ConfigError
    try:
        from aurora.api import astro as M
    except ConfigError:                                   # the API loads the configuration: none here (publish's run)
        pytest.skip("no configuration to load the API with")
    monkeypatch.setattr(M, "_collim_file", lambda: tmp_path / "collimation.json")
    out = asyncio.run(M.astro_collimation_photo(Req(picture())))
    assert out["secondary"]["round"] > 0.99
    kept = json.loads((tmp_path / "collimation.json").read_text())
    assert "photo" in kept and "image" not in kept["photo"] and kept["photo"]["verdict"]


def test_the_tab_its_words_and_the_offline_shell():
    js = (ROOT / "webui/js/modules/astro.js").read_text()
    assert 'data-tab="collim"' in js and "collimTab" in js
    assert "/static/js/modules/astro_collim.js" in (ROOT / "webui/sw.js").read_text()
    for lang in ("it_IT", "en_US"):
        words = json.loads((ROOT / f"webui/i18n/{lang}.json").read_text())
        used = set(__import__("re").findall(r't\("(col\.[a-z_]+)"', (ROOT / "webui/js/modules/astro_collim.js").read_text()))
        assert used and used <= set(words) and "astro.tab.collim" in words

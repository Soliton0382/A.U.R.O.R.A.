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


QUATTRO = {"secondary_mm": 70, "aperture_mm": 200, "focal_mm": 800}


def test_the_offset_seen_from_the_focal_point_is_centred():
    # C359: centred only from the focal point; nearer, toward the open end; farther, the other way
    assert abs(O.shift(280, 280, 35)) < 1e-9
    assert O.shift(150, 280, 35) > 0.08 and O.shift(450, 280, 35) < -0.04


def test_the_collimators_distance_from_the_shadow():
    # the shadow is the concave primary's virtual image of the secondary, magnified f / (f − S): 70 mm at f/4, the
    # secondary 520 mm from the primary → × 2.86; a ratio of 0.336 (the owner's picture) → about 267 mm, near focus
    e = O.expected(0.336, QUATTRO)
    assert 260 <= e["view_mm"] <= 275 and e["lo"] <= e["mid"] <= e["hi"] and abs(e["mid"]) < 0.02
    assert O.expected(0.2, QUATTRO)["view_mm"] < e["view_mm"] < O.expected(0.6, QUATTRO)["view_mm"]
    assert O.expected(0.2, None) is None and O.expected(0.95, QUATTRO) is None


def _tube(im_bytes):
    """The picture with a whole drawtube around it: a lit ring, dark beyond."""
    im = Image.open(io.BytesIO(im_bytes)).convert("RGB")
    out = Image.new("RGB", im.size, (5, 5, 5))
    d = ImageDraw.Draw(out)
    d.ellipse([400 - 370, 400 - 370, 400 + 370, 400 + 370], fill=(40, 40, 40))
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).ellipse([400 - 300, 400 - 300, 400 + 300, 400 + 300], fill=255)
    out.paste(im, (0, 0), mask)
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=92)
    return buf.getvalue()


def test_the_three_steps_with_the_outline_where_the_offset_puts_it():
    # the outline 4 % of its radius toward the shadow's side, the spot on the drawtube's centre and on the reflection
    pic = _tube(picture(sec=(390, 400, 250, 250), shadow=(365, 400, 75), ocal=(400, 400, 40), spot=(400, 400), lines=False))
    r = O.analyse(pic, QUATTRO)
    assert "drawtube" in r and "expected" in r
    codes = {v["code"]: v for v in r["verdict"]}
    assert codes["secondary_tilt"]["ok"] and codes["secondary_tilt"]["text"].startswith("1)")
    assert codes["secondary_place"]["ok"] is True and codes["secondary_place"]["text"].startswith("2)")
    assert codes["primary"]["ok"] and codes["primary"]["text"].startswith("3)")


def test_the_spot_off_the_drawtubes_centre_is_the_secondarys_tilt():
    pic = _tube(picture(sec=(390, 400, 250, 250), shadow=(365, 400, 75), ocal=(400, 430, 40), spot=(400, 430), lines=False))
    v = next(x for x in O.analyse(pic, QUATTRO)["verdict"] if x["code"] == "secondary_tilt")
    assert v["ok"] is False and "basso" in v["text"] and "3 viti" in v["text"]


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


@pytest.mark.skipif(not __import__("shutil").which("node"), reason="node not installed")
def test_the_live_circles_use_the_same_geometry_as_the_server():
    # the page's offset (astro_collim_live.js) and ast_ocal.expected agree, for the Quattro and an f/6
    import subprocess
    src = (ROOT / "webui" / "js" / "modules" / "astro_collim_live.js").as_uri()
    for k, scope in ((0.336, QUATTRO), (0.25, {"secondary_mm": 58, "aperture_mm": 254, "focal_mm": 1524})):
        js = (f"const M = await import({json.dumps(src)}); const r = M.offsetFor({k}, {scope['secondary_mm']}, "
              f"{scope['aperture_mm']}, {scope['focal_mm']}); console.log(JSON.stringify(r))")
        out = subprocess.run(["node", "--input-type=module", "-e", js], capture_output=True, text=True, timeout=30)
        assert out.returncode == 0, out.stderr[-600:]
        r = json.loads(out.stdout)
        e = O.expected(k, scope)
        assert abs(r["shift"] - e["mid"]) < 1e-3 and abs(r["view"] - e["view_mm"]) < 1
        assert abs(r["shadow"] - e["shadow"]) < 1e-3                       # the shadow moved the same way on both
    # the Quattro: offset 4.3 mm each way on a 35 mm half secondary → the shadow 12 % of its radius off the axis
    assert 0.11 < O.expected(0.336, QUATTRO)["shadow"] < 0.13


def test_the_live_tab_its_scope_and_the_offline_shell():
    live = (ROOT / "webui" / "js" / "modules" / "astro_collim_live.js").read_text()
    assert "getUserMedia" in live and "enumerateDevices" in live and "/v1/aurora/astro/collimation/scope" in live
    assert "/v1/aurora/astro/camera/stream" in live and "pcPanel(" in live                          # the PC's camera too
    pc = (ROOT / "webui" / "js" / "modules" / "astro_collim_pc.js").read_text()
    assert "/v1/aurora/astro/camera/key" in pc and "/v1/aurora/astro/camera/bundle" in pc and "dialog: true" in pc
    assert "liveCard(state.scope)" in (ROOT / "webui" / "js" / "modules" / "astro_collim.js").read_text()
    assert "/static/js/modules/astro_collim_live.js" in (ROOT / "webui" / "sw.js").read_text()
    api = (ROOT / "aurora" / "api" / "astro.py").read_text()
    assert '"/v1/aurora/astro/collimation/scope"' in api and "0 < secondary < aperture < focal length" in api

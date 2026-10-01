# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import io

from PIL import Image

from aurora import img_edit as E


def picture(w=400, h=200, colour=(200, 40, 40), fmt="JPEG"):
    b = io.BytesIO()
    im = Image.new("RGB", (w, h), colour)
    im.paste((20, 20, 220), (0, 0, w // 2, h))                      # left half blue: mirror and rotation are visible
    im.save(b, fmt)
    return b.getvalue()


def opened(data):
    return Image.open(io.BytesIO(data))


def test_only_known_operations_with_clamped_values_survive():
    ops = E.validate([{"op": "crop", "left": 80, "right": -5}, {"op": "rotate", "degrees": -90}, {"op": "exec", "code": "x"},
                      {"op": "brightness", "factor": 99}, {"op": "brightness", "factor": 1}, {"op": "resize", "width": 1e9},
                      {"op": "format", "to": "gif"}, {"op": "format", "to": "JPG"}, "nonsense", {"op": "grayscale", "x": 1}])
    assert ops == [{"op": "crop", "left": 49, "top": 0, "right": 0, "bottom": 0}, {"op": "rotate", "degrees": 270},
                   {"op": "brightness", "factor": 3}, {"op": "resize", "width": 8192}, {"op": "format", "to": "jpeg"},
                   {"op": "grayscale"}]
    assert E.validate("not a list") == [] and len(E.validate([{"op": "invert"}] * 40)) == 12


def test_each_operation_does_what_it_says():
    src = picture()
    out, mime, size = E.apply(src, [{"op": "crop", "left": 25, "right": 25}])
    assert mime == "image/jpeg" and size == {"width": 200, "height": 200}
    out, _, size = E.apply(src, [{"op": "rotate", "degrees": 90}])
    assert size == {"width": 200, "height": 400} and opened(out).getpixel((100, 390))[2] > 150        # blue at the bottom
    out, _, _ = E.apply(src, [{"op": "flip", "direction": "horizontal"}])
    assert opened(out).getpixel((390, 100))[2] > 150 and opened(out).getpixel((10, 100))[0] > 150   # blue now right
    out, _, _ = E.apply(src, [{"op": "grayscale"}])
    r, g, b = opened(out).convert("RGB").getpixel((300, 100))
    assert abs(r - g) < 6 and abs(g - b) < 6
    out, _, size = E.apply(src, [{"op": "resize", "scale": 0.5}])
    assert size == {"width": 200, "height": 100}
    dark = opened(E.apply(src, [{"op": "brightness", "factor": 0.3}])[0]).getpixel((300, 100))[0]
    assert dark < 90
    out, mime, _ = E.apply(picture(fmt="PNG"), [{"op": "invert"}])
    assert mime == "image/png" and opened(out).format == "PNG"                                      # the kind is kept
    out, mime, _ = E.apply(src, [{"op": "format", "to": "webp"}])
    assert mime == "image/webp" and opened(out).format == "WEBP"
    assert E.describe([{"op": "rotate", "degrees": 90}, {"op": "grayscale"}]) == "ruotata di 90°, in bianco e nero"

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import io

from PIL import Image

from aurora.kno_attach import MIN_SHORT_PX, TILE, to_jpeg


def test_pictures_reach_the_vision_in_whole_tiles():
    """C67: a side that is not a multiple of 32 px is padded with black by the vision projector (M50)."""
    for w, h in ((400, 300), (300, 1024), (200, 150), (683, 512), (4032, 3024), (3024, 4032), (1, 1)):
        b = io.BytesIO()
        Image.new("RGB", (w, h), (30, 80, 200)).save(b, "PNG")
        out = Image.open(io.BytesIO(to_jpeg(b.getvalue(), 1024)))
        assert out.format == "JPEG" and all(x % TILE == 0 for x in out.size), (w, h, out.size)
        assert min(out.size) >= min(MIN_SHORT_PX, 2048 * min(w, h) // max(w, h)) or max(out.size) <= 2048
        assert max(out.size) <= 2048
        ratio_in, ratio_out = w / h, out.size[0] / out.size[1]
        assert abs(ratio_out / ratio_in - 1) < 0.1 or min(w, h) < 8          # at most a few px of stretch

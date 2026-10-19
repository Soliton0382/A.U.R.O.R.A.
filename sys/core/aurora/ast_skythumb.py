# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🌌 A picture of an object's sky with the person's field drawn on it (owner, 19 Oct: «una miniatura dell'oggetto
selezionato sarebbe figo»). The sky from the CDS's public image service (hips2fits, Strasbourg: the DSS2 colour survey),
asked with the object's catalogue place only — never the person's site; kept in the astro folder (thumbs/), fetched
the first time the person opens that object — never for the whole list — and shown in the list's row from then on.
North up, east left, as the survey is; the camera's field (sensor × focal) drawn as a rectangle in the middle at angle
0 — the framing before any rotation."""
from __future__ import annotations

import io
import re
import urllib.parse
import urllib.request
from pathlib import Path

SERVICE = "https://alasky.cds.unistra.fr/hips-image-services/hips2fits"
SURVEY = "CDS/P/DSS2/color"
W, H = 480, 320


def _safe(name: str) -> str:
    return re.sub(r"[^\w.+-]", "_", name)[:60] or "object"


def picture(folder: Path, obj: dict, fov: dict | None) -> bytes:
    """The JPEG: the object's sky, wide enough for the field and the object, the field drawn when it is known."""
    from PIL import Image, ImageDraw
    size = max((obj.get("maj") or 0) / 60 * 1.4, (fov or {}).get("w_deg", 0) * 1.6, 0.5)
    keep = folder / "thumbs" / f"{_safe(obj['name'])}-{size:.2f}.jpg"
    if keep.is_file():
        raw = keep.read_bytes()
    else:
        q = urllib.parse.urlencode({"hips": SURVEY, "width": W, "height": H, "fov": round(size, 3), "projection": "TAN",
                                    "coordsys": "icrs", "ra": obj["ra"], "dec": obj["dec"], "format": "jpg"})
        with urllib.request.urlopen(f"{SERVICE}?{q}", timeout=30) as r:  # noqa: S310 — a public survey, the object's place
            raw = r.read()
        keep.parent.mkdir(parents=True, exist_ok=True)
        keep.write_bytes(raw)
    if not fov:
        return raw
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    px = W / size                                         # pixels a degree (fov is the width)
    fw, fh = fov["w_deg"] * px, fov["h_deg"] * px
    d = ImageDraw.Draw(im)
    d.rectangle([W / 2 - fw / 2, H / 2 - fh / 2, W / 2 + fw / 2, H / 2 + fh / 2], outline=(255, 210, 60), width=2)
    d.text((6, 4), "N up, E left", fill=(230, 230, 230))  # the default font has no arrows
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def cached(folder: Path, name: str) -> bool:
    """Whether the object's sky was already fetched (owner, 19 Oct: «la cache si potrebbe popolare in base ai click»)."""
    return any((folder / "thumbs").glob(f"{_safe(name)}-*.jpg"))


def for_object(cfg, name: str) -> bytes:
    from . import ast_catalog, ast_inventory, ast_skyplan
    folder = ast_inventory.folder(cfg)
    o = ast_catalog.find(ast_catalog.load(folder)["objects"], name)
    if not o:
        raise ValueError(f"«{name}» non è nel catalogo")
    return picture(folder, o, ast_skyplan.field(folder, ast_inventory.profile(cfg)))

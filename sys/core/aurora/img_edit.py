# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Classic picture edits, asked in words: the reasoner turns the owner's request into a list of known operations
(plan), each checked and clamped; Pillow applies them (apply). No code from the model ever runs, the original is
never overwritten: the result is a new file of the conversation.

 crop {left, top, right, bottom}   percent of the side cut away (0-49 each)
 rotate {degrees}                  counter-clockwise; 90/180/270 exact, any other angle with a larger canvas
 flip {direction}                  horizontal (mirror) or vertical
 resize {scale} | {width} | {height}   0.05-4, or pixels (16-8192), proportions kept
 brightness / contrast / saturation / sharpness {factor}   0.0-3.0 (1 = unchanged)
 grayscale, sepia, autocontrast, invert                     no argument
 blur {radius}                     0.5-20 px
 format {to}                       jpeg | png | webp (the default keeps the original's kind)
"""
from __future__ import annotations

import io
import json
import re

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

OPS = ("crop", "rotate", "flip", "resize", "brightness", "contrast", "saturation", "sharpness", "grayscale", "sepia",
       "autocontrast", "invert", "blur", "format", "creative", "upscale", "remove_background")
AI_OPS = ("creative", "upscale", "remove_background")   # done by an image model (mdl_image.gpu_job), not by Pillow
SYS_EDIT = ("A picture is in the conversation. Classify the owner's last message. EDIT: he asks to change the "
            "picture (crop, cut, rotate, turn, mirror, flip, resize, enlarge, shrink, brighter, darker, contrast, "
            "colours, black and white, sepia, blur, sharpen, negative, convert to png/jpg/webp). LOOK: he asks "
            "something about the picture itself (what it shows, what is written, a description, a detail of it). "
            "OTHER: anything else (a new subject, small talk, a question about the world). Examples: 'ritagliala' EDIT; "
            "'rendila più luminosa' EDIT; 'mettila in bianco e nero' EDIT; 'togli lo sfondo' EDIT; 'mettici la neve' EDIT; "
            "'trasformala in un acquerello' EDIT; 'aumenta la risoluzione' EDIT; 'cosa c'è scritto?' LOOK; 'descrivila' LOOK; "
            "'cosa mostra l'immagine?' LOOK; 'che animale è?' LOOK; 'come stai?' OTHER; 'cos'è l'entanglement?' "
            "OTHER. Reply with one word.")
SYS_PLAN = ("You turn the owner's request about a picture into a JSON list of operations, applied in order. Allowed "
            "(and nothing else): " + ", ".join(OPS) + ". Arguments: crop {\"left\",\"top\",\"right\",\"bottom\"} percent "
            "cut from each side (0-49); rotate {\"degrees\"} counter-clockwise (a clockwise turn is negative); flip "
            "{\"direction\": \"horizontal\"|\"vertical\"}; resize {\"scale\"} or {\"width\"} or {\"height\"} in px; "
            "brightness/contrast/saturation/sharpness {\"factor\"} 0-3 with 1 unchanged (a bit more = 1.3, much more "
            "= 1.7, less = 0.7); grayscale, sepia, autocontrast, invert {}; blur {\"radius\"} px; format {\"to\": "
            "\"jpeg\"|\"png\"|\"webp\"}; creative {\"prompt\": \"<the change, in English, saying what must stay the same>\"} for any "
            "change of CONTENT or STYLE (add or remove things, another sky, season, light of day, a painting style, a "
            "different background scene); upscale {\"scale\": 2|4} for more resolution and detail (aumenta la risoluzione, "
            "migliora la qualità, rendila in alta definizione) — resize is only for plain pixel size; remove_background {} "
            "for cutting out the subject (togli/rimuovi lo sfondo, scontorna). Italian words: ritagliare/tagliare = crop; ruotare/girare = rotate; "
            "specchiare/riflettere = flip horizontal; capovolgere/sottosopra = flip vertical; ingrandire/rimpicciolire/"
            "dimezzare = resize; luminosa/chiara/scura = brightness; scala di grigi/bianco e nero = grayscale; "
            "seppia/vintage = sepia; sfocare = blur; nitida = sharpness; negativo = invert. Reply ONLY with the JSON, like [{\"op\": \"crop\", \"left\": 10, \"right\": 10}, "
            "{\"op\": \"brightness\", \"factor\": 1.3}]. If nothing allowed fits the request, reply [].")


def _num(v, lo: float, hi: float, default: float) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, x))


def validate(ops) -> list[dict]:
    """Only known operations, each with clamped arguments; anything else is dropped (pure: tested offline)."""
    out: list[dict] = []
    for o in ops if isinstance(ops, list) else []:
        if not isinstance(o, dict) or o.get("op") not in OPS:
            continue
        op = o["op"]
        if op == "crop":
            c = {k: _num(o.get(k, 0), 0, 49, 0) for k in ("left", "top", "right", "bottom")}
            if any(c.values()):
                out.append({"op": op, **c})
        elif op == "rotate":
            d = _num(o.get("degrees", 0), -360, 360, 0) % 360
            if d:
                out.append({"op": op, "degrees": d})
        elif op == "flip":
            out.append({"op": op, "direction": "vertical" if str(o.get("direction", "")).startswith("v") else "horizontal"})
        elif op == "resize":
            for k, lo, hi in (("scale", 0.05, 4), ("width", 16, 8192), ("height", 16, 8192)):
                if k in o:
                    out.append({"op": op, k: _num(o[k], lo, hi, 1 if k == "scale" else 1024)})
                    break
        elif op in ("brightness", "contrast", "saturation", "sharpness"):
            f = _num(o.get("factor", 1), 0, 3, 1)
            if f != 1:
                out.append({"op": op, "factor": f})
        elif op == "blur":
            out.append({"op": op, "radius": _num(o.get("radius", 2), 0.5, 20, 2)})
        elif op == "format":
            to = str(o.get("to", "")).lower().replace("jpg", "jpeg")
            if to in ("jpeg", "png", "webp"):
                out.append({"op": op, "to": to})
        elif op == "creative":
            prompt = " ".join(str(o.get("prompt", "")).split())[:500]
            if len(prompt) >= 5:
                out.append({"op": op, "prompt": prompt})
        elif op == "upscale":
            out.append({"op": op, "scale": 2 if _num(o.get("scale", 4), 2, 4, 4) < 3 else 4})
        else:
            out.append({"op": op})
    return out[:12]


def plan(llm, request: str, width: int, height: int) -> list[dict]:
    raw = llm.complete(SYS_PLAN, f"PICTURE: {width}x{height} px\nREQUEST: {request}", 300).answer
    m = re.search(r"\[.*\]", raw, re.S)
    try:
        return validate(json.loads(m.group(0))) if m else []
    except ValueError:
        return []


def apply(data: bytes, ops: list[dict]) -> tuple[bytes, str, dict]:
    """(bytes, mime, {"width", "height"}) of the edited picture; pure, Pillow only."""
    src = Image.open(io.BytesIO(data))
    fmt = {"PNG": "png", "WEBP": "webp"}.get(src.format or "", "jpeg")
    im = ImageOps.exif_transpose(src)
    if getattr(im, "n_frames", 1) > 1:
        im.seek(0)
    im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") and fmt != "jpeg" else "RGB")
    for o in validate(ops):
        op, w, h = o["op"], im.width, im.height
        if op in AI_OPS:                                 # never here: the caller runs them with the image models
            raise ValueError(f"{op} needs an image model (mdl_image.gpu_job)")
        if op == "crop":
            box = (round(w * o["left"] / 100), round(h * o["top"] / 100), w - round(w * o["right"] / 100), h - round(h * o["bottom"] / 100))
            if box[2] - box[0] >= 8 and box[3] - box[1] >= 8:
                im = im.crop(box)
        elif op == "rotate":
            d = o["degrees"]
            im = {90: lambda: im.transpose(Image.Transpose.ROTATE_90), 180: lambda: im.transpose(Image.Transpose.ROTATE_180),
                  270: lambda: im.transpose(Image.Transpose.ROTATE_270)}.get(d, lambda: im.rotate(d, expand=True, resample=Image.BICUBIC,
                                                                                                     fillcolor="white"))()
        elif op == "flip":
            im = ImageOps.mirror(im) if o["direction"] == "horizontal" else ImageOps.flip(im)
        elif op == "resize":
            k = o.get("scale") or (o["width"] / w if "width" in o else o["height"] / h)
            im = im.resize((max(1, round(w * k)), max(1, round(h * k))), Image.LANCZOS)
        elif op in ("brightness", "contrast", "saturation", "sharpness"):
            enh = {"brightness": ImageEnhance.Brightness, "contrast": ImageEnhance.Contrast,
                   "saturation": ImageEnhance.Color, "sharpness": ImageEnhance.Sharpness}[op]
            base = im.convert("RGB") if im.mode == "RGBA" else im
            out = enh(base).enhance(o["factor"])
            im = out if im.mode != "RGBA" else Image.merge("RGBA", (*out.split(), im.getchannel("A")))
        elif op == "grayscale":
            im = ImageOps.grayscale(im.convert("RGB")).convert("RGB")
        elif op == "sepia":
            g = ImageOps.grayscale(im.convert("RGB"))
            im = ImageOps.colorize(g, black=(40, 26, 13), white=(255, 240, 192))
        elif op == "autocontrast":
            im = ImageOps.autocontrast(im.convert("RGB"), cutoff=1)
        elif op == "invert":
            im = ImageOps.invert(im.convert("RGB"))
        elif op == "blur":
            im = im.filter(ImageFilter.GaussianBlur(o["radius"]))
        elif op == "format":
            fmt = o["to"]
    out = io.BytesIO()
    if fmt == "jpeg":
        im.convert("RGB").save(out, "JPEG", quality=92)
    else:
        im.save(out, fmt.upper())
    return out.getvalue(), f"image/{fmt}", {"width": im.width, "height": im.height}


def describe(ops: list[dict], lang: str = "it") -> str:
    """The operations in words, for the answer."""
    it = {"crop": "ritagliata", "rotate": "ruotata di {degrees:.0f}°", "flip": "specchiata", "resize": "ridimensionata",
          "brightness": "luminosità ×{factor:.1f}", "contrast": "contrasto ×{factor:.1f}", "saturation": "saturazione ×{factor:.1f}",
          "sharpness": "nitidezza ×{factor:.1f}", "grayscale": "in bianco e nero", "sepia": "seppia", "autocontrast":
          "contrasto automatico", "invert": "in negativo", "blur": "sfocata ({radius:.0f} px)", "format": "convertita in {to}", "creative": "trasformata (FLUX.2: «{prompt}»)",
          "upscale": "ingrandita ×{scale} con Swin2SR", "remove_background": "scontornata (sfondo trasparente)"}
    en = {"crop": "cropped", "rotate": "rotated by {degrees:.0f}°", "flip": "mirrored", "resize": "resized",
          "brightness": "brightness ×{factor:.1f}", "contrast": "contrast ×{factor:.1f}", "saturation": "saturation ×{factor:.1f}",
          "sharpness": "sharpness ×{factor:.1f}", "grayscale": "black and white", "sepia": "sepia", "autocontrast":
          "auto contrast", "invert": "negative", "blur": "blurred ({radius:.0f} px)", "format": "converted to {to}", "creative": "changed (FLUX.2: \"{prompt}\")",
          "upscale": "enlarged ×{scale} with Swin2SR", "remove_background": "cut out (transparent background)"}
    words = it if lang == "it" else en

    def one(o):
        if o["op"] == "rotate":                       # counter-clockwise inside; said the way people say it
            d = float(o.get("degrees", 0)) % 360
            if d > 180:
                return (f"ruotata di {360 - d:.0f}° in senso orario" if lang == "it" else f"rotated {360 - d:.0f}° clockwise")
            return (f"ruotata di {d:.0f}° in senso antiorario" if lang == "it" else f"rotated {d:.0f}° counter-clockwise")
        return words[o["op"]].format(**o)
    return ", ".join(one(o) for o in ops)

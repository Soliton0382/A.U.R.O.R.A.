# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""EU AI Act, Article 50: what Aurora generates says that it is AI-generated.

 text that leaves the machine (posts, messages, issues) ends with a disclosure line, added before
   the owner approves it, so the preview shows exactly what will be published;
 images carry a machine-readable mark (XMP with the IPTC digital source type
   "trainedAlgorithmicMedia", PNG text chunks) and, unless switched off, a small visible label;
 documents Aurora writes start with a disclosure header.
The texts are in .env (AURORA_AI_DISCLOSURE_IT / _EN); AURORA_AI_DISCLOSURE switches it all off.
Obligations apply from 2 August 2026 (providers of systems already on the market: 2 December 2026).
"""
from __future__ import annotations

import io
import time

from . import sys_config

IPTC_AI = "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia"


def _on(cfg) -> bool:
    """Disclosure is on unless switched off AND the installation is exempted (ethics code, level B)."""
    from . import sys_ethics
    return bool(cfg["AURORA_AI_DISCLOSURE"]) or not sys_ethics.exempt(cfg)


def _line(cfg, lang: str) -> str:
    return cfg["AURORA_AI_DISCLOSURE_IT"] if lang.startswith("it") else cfg["AURORA_AI_DISCLOSURE_EN"]


def mark_text(text: str, lang: str = "it", cfg: sys_config.Config | None = None) -> str:
    """The text with its disclosure line at the end (once)."""
    cfg = cfg or sys_config.get()
    if not _on(cfg):
        return text
    line = _line(cfg, lang)
    return text if line in text else f"{text.rstrip()}\n\n{line}"


def mark_document(text: str, lang: str = "it", cfg: sys_config.Config | None = None) -> str:
    """A document (markdown) with a disclosure header."""
    cfg = cfg or sys_config.get()
    if not _on(cfg):
        return text
    head = f"> {_line(cfg, lang)} · {time.strftime('%Y-%m-%d')}\n\n"
    return text if text.startswith(head[:20]) else head + text


def _xmp(title: str) -> bytes:
    return (f'<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>'
            f'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            f'<rdf:Description rdf:about="" xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/" '
            f'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:xmp="http://ns.adobe.com/xap/1.0/">'
            f'<Iptc4xmpExt:DigitalSourceType>{IPTC_AI}</Iptc4xmpExt:DigitalSourceType>'
            f'<xmp:CreatorTool>Aurora</xmp:CreatorTool><dc:title><rdf:Alt><rdf:li xml:lang="x-default">{title}'
            f'</rdf:li></rdf:Alt></dc:title></rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end="w"?>').encode()


def mark_image(image, title: str = "", lang: str = "it", cfg: sys_config.Config | None = None) -> bytes:
    """A PIL image as PNG bytes, marked as AI-generated (metadata always, label unless switched off)."""
    from PIL import Image, ImageDraw, PngImagePlugin
    cfg = cfg or sys_config.get()
    img = image.convert("RGB")
    if _on(cfg) and cfg["AURORA_AI_IMAGE_LABEL"]:
        draw = ImageDraw.Draw(img, "RGBA")
        label = "AI · Aurora"
        w, h = img.size
        size = max(12, w // 60)
        box = (w - size * 7 - 12, h - size - 14, w - 6, h - 6)
        draw.rounded_rectangle(box, radius=6, fill=(0, 0, 0, 140))
        draw.text((box[0] + 6, box[1] + 3), label, fill=(255, 255, 255, 230))
    info = PngImagePlugin.PngInfo()
    if _on(cfg):
        info.add_itxt("XML:com.adobe.xmp", _xmp(title).decode(), zip=False)
        info.add_text("AI-Generated", "true")
        info.add_text("DigitalSourceType", IPTC_AI)
        info.add_text("Disclosure", _line(cfg, lang))
    info.add_text("Software", "Aurora")
    out = io.BytesIO()
    img.save(out, "PNG", pnginfo=info)
    return out.getvalue()

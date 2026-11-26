# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Editable documents from Markdown (N158; the owner, 26 Nov: «aurora scrivi un documento con quello che ci siamo
detti»): an OpenDocument Text file (.odt) that Writer, Word and Google Docs open and edit — next to the PDFs of
doc_pdf, in AURORA_DOCUMENTS_DIR.

Written by hand as the zip of XML files the standard asks for (mimetype first and stored, content, styles, meta,
manifest): no office suite runs, nothing new installed. Markdown (markdown-it, raw HTML and images off, as for the
PDFs): headings, paragraphs, bold, italic, inline code, bullet and numbered lists, block quotes, code blocks, tables.
The EU AI Act mark: the meta's generator «Aurora», a user-defined «AIGenerated: true» and the IPTC digital source type,
and the visible disclosure as the last paragraph."""
from __future__ import annotations

import time
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from . import sys_config, sys_disclosure, sys_log
from .doc_pdf import safe_name

NS = ('xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
      'xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" '
      'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
      'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
      'xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" '
      'xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0" '
      'xmlns:dc="http://purl.org/dc/elements/1.1/" office:version="1.3"')
STYLES = f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles {NS}><office:styles>
<style:default-style style:family="paragraph"><style:text-properties style:font-name="Liberation Sans" fo:font-size="11pt"/></style:default-style>
<style:style style:name="Standard" style:family="paragraph"><style:paragraph-properties fo:margin-bottom="0.18cm"/></style:style>
<style:style style:name="Title" style:family="paragraph"><style:text-properties fo:font-size="20pt" fo:font-weight="bold" fo:color="#243a73"/></style:style>
<style:style style:name="Heading_1" style:display-name="Heading 1" style:family="paragraph" style:default-outline-level="1"><style:paragraph-properties fo:margin-top="0.4cm" fo:margin-bottom="0.2cm"/><style:text-properties fo:font-size="16pt" fo:font-weight="bold" fo:color="#243a73"/></style:style>
<style:style style:name="Heading_2" style:display-name="Heading 2" style:family="paragraph" style:default-outline-level="2"><style:paragraph-properties fo:margin-top="0.35cm" fo:margin-bottom="0.15cm"/><style:text-properties fo:font-size="13.5pt" fo:font-weight="bold" fo:color="#243a73"/></style:style>
<style:style style:name="Heading_3" style:display-name="Heading 3" style:family="paragraph" style:default-outline-level="3"><style:text-properties fo:font-size="12pt" fo:font-weight="bold" fo:color="#243a73"/></style:style>
<style:style style:name="Quote" style:family="paragraph"><style:paragraph-properties fo:margin-left="0.8cm"/><style:text-properties fo:color="#3d4556" fo:font-style="italic"/></style:style>
<style:style style:name="Code" style:family="paragraph"><style:paragraph-properties fo:background-color="#eef1f7"/><style:text-properties style:font-name="Liberation Mono" fo:font-size="9.5pt"/></style:style>
<style:style style:name="Disclosure" style:family="paragraph"><style:paragraph-properties fo:margin-top="0.6cm"/><style:text-properties fo:font-size="8pt" fo:color="#6b7385"/></style:style>
<style:style style:name="B" style:family="text"><style:text-properties fo:font-weight="bold"/></style:style>
<style:style style:name="I" style:family="text"><style:text-properties fo:font-style="italic"/></style:style>
<style:style style:name="C" style:family="text"><style:text-properties style:font-name="Liberation Mono"/></style:style>
</office:styles></office:document-styles>"""
MANIFEST = """<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.3">
<manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/>
<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>
<manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/>
<manifest:file-entry manifest:full-path="meta.xml" manifest:media-type="text/xml"/>
</manifest:manifest>"""
MIME = "application/vnd.oasis.opendocument.text"
LISTS = ('<office:automatic-styles>'
         '<text:list-style style:name="LB"><text:list-level-style-bullet text:level="1" text:bullet-char="•">'
         '<style:list-level-properties text:space-before="0.4cm" text:min-label-width="0.5cm"/>'
         '</text:list-level-style-bullet></text:list-style>'
         '<text:list-style style:name="LN"><text:list-level-style-number text:level="1" style:num-format="1" '
         'style:num-suffix="."><style:list-level-properties text:space-before="0.4cm" text:min-label-width="0.6cm"/>'
         '</text:list-level-style-number></text:list-style></office:automatic-styles>')


def _inline(children) -> str:
    out, stack = [], []
    for t in children or []:
        if t.type == "text":
            out.append(escape(t.content))
        elif t.type in ("softbreak", "hardbreak"):
            out.append("<text:line-break/>")
        elif t.type == "code_inline":
            out.append(f'<text:span text:style-name="C">{escape(t.content)}</text:span>')
        elif t.type in ("strong_open", "em_open"):
            stack.append(t.type)
            out.append(f'<text:span text:style-name="{"B" if t.type == "strong_open" else "I"}">')
        elif t.type in ("strong_close", "em_close") and stack:
            stack.pop()
            out.append("</text:span>")
        elif t.type == "link_open":
            out.append(f'<text:a xlink:href="{escape(t.attrGet("href") or "")}" xmlns:xlink="http://www.w3.org/1999/xlink">')
        elif t.type == "link_close":
            out.append("</text:a>")
    out += ["</text:span>"] * len(stack)
    return "".join(out)


def body_xml(markdown: str) -> str:
    """The document's body: markdown-it tokens turned into ODF paragraphs, lists and tables."""
    from markdown_it import MarkdownIt
    toks = MarkdownIt("commonmark", {"html": False}).enable("table").disable("image").parse(markdown)
    out, para, in_quote, i = [], "Standard", 0, 0
    while i < len(toks):
        t = toks[i]
        if t.type == "heading_open":
            lvl = min(int(t.tag[1]), 3)
            out.append(f'<text:h text:style-name="Heading_{lvl}" text:outline-level="{lvl}">{_inline(toks[i + 1].children)}</text:h>')
            i += 3
            continue
        if t.type == "blockquote_open":
            in_quote += 1
        elif t.type == "blockquote_close":
            in_quote -= 1
        elif t.type in ("bullet_list_open", "ordered_list_open"):
            out.append(f'<text:list text:style-name="{"LN" if t.type == "ordered_list_open" else "LB"}">')
        elif t.type in ("bullet_list_close", "ordered_list_close"):
            out.append("</text:list>")
        elif t.type == "list_item_open":
            out.append("<text:list-item>")
        elif t.type == "list_item_close":
            out.append("</text:list-item>")
        elif t.type == "paragraph_open":
            para = "Quote" if in_quote else "Standard"
            out.append(f'<text:p text:style-name="{para}">{_inline(toks[i + 1].children)}</text:p>')
            i += 3
            continue
        elif t.type in ("fence", "code_block"):
            for line in t.content.rstrip("\n").split("\n"):
                out.append(f'<text:p text:style-name="Code">{escape(line) or "<text:s/>"}</text:p>')
        elif t.type == "table_open":
            rows, j = [], i + 1
            while toks[j].type != "table_close":
                if toks[j].type == "tr_open":
                    rows.append([])
                elif toks[j].type in ("th_open", "td_open"):
                    rows[-1].append((toks[j].type == "th_open", _inline(toks[j + 1].children)))
                j += 1
            cols = max((len(r) for r in rows), default=1)
            out.append(f'<table:table><table:table-column table:number-columns-repeated="{cols}"/>')
            for r in rows:
                cells = "".join(f'<table:table-cell office:value-type="string"><text:p>'
                                f'{f"<text:span text:style-name=\"B\">{c}</text:span>" if h else c}</text:p></table:table-cell>'
                                for h, c in r)
                out.append(f"<table:table-row>{cells}</table:table-row>")
            out.append("</table:table>")
            i = j + 1
            continue
        elif t.type == "hr":
            out.append('<text:p text:style-name="Standard">―――</text:p>')
        i += 1
    return "".join(out)


def create(title: str, markdown: str, lang: str = "it", cfg: sys_config.Config | None = None) -> Path:
    cfg = cfg or sys_config.get()
    out_dir = cfg.path("AURORA_DOCUMENTS_DIR")
    out_dir.mkdir(parents=True, exist_ok=True)
    name, n = safe_name(title), 1
    target = out_dir / f"{name}.odt"
    while target.exists():
        n += 1
        target = out_dir / f"{name}-{n}.odt"
    on = sys_disclosure._on(cfg)
    line = sys_disclosure._line(cfg, lang) if on else ""
    content = (f'<?xml version="1.0" encoding="UTF-8"?><office:document-content {NS}>{LISTS}<office:body><office:text>'
               f'<text:p text:style-name="Title">{escape(title)}</text:p>{body_xml(markdown)}'
               + (f'<text:p text:style-name="Disclosure">{escape(line)}</text:p>' if line else "")
               + "</office:text></office:body></office:document-content>")
    ai = (f'<meta:user-defined meta:name="AIGenerated">true</meta:user-defined>'
          f'<meta:user-defined meta:name="DigitalSourceType">{escape(sys_disclosure.IPTC_AI)}</meta:user-defined>'
          f"<dc:description>{escape(line)}</dc:description>") if on else ""
    meta = (f'<?xml version="1.0" encoding="UTF-8"?><office:document-meta {NS}><office:meta>'
            f"<meta:generator>Aurora</meta:generator><dc:title>{escape(title)}</dc:title>"
            f"<dc:creator>Aurora</dc:creator><dc:date>{time.strftime('%Y-%m-%dT%H:%M:%S')}</dc:date>"
            f"<dc:language>{escape(lang)}</dc:language>{ai}</office:meta></office:document-meta>")
    tmp = target.with_suffix(".odt.part")
    with zipfile.ZipFile(tmp, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), MIME, compress_type=zipfile.ZIP_STORED)   # first and stored (ODF)
        for n_, data in (("content.xml", content), ("styles.xml", STYLES), ("meta.xml", meta),
                         ("META-INF/manifest.xml", MANIFEST)):
            z.writestr(n_, data, compress_type=zipfile.ZIP_DEFLATED)
    tmp.replace(target)
    sys_log.get_logger("documents").info("odt written (%d bytes)", target.stat().st_size)
    return target


def made_by_aurora(path: Path) -> bool:
    """True only for an .odt this module wrote (generator «Aurora»): the only ones the Files page may delete."""
    try:
        with zipfile.ZipFile(path) as z:
            return b"<meta:generator>Aurora</meta:generator>" in z.read("meta.xml")
    except (OSError, KeyError, zipfile.BadZipFile):
        return False

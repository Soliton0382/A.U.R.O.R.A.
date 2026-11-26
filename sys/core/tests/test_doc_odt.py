# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N158: editable documents (.odt) from Markdown — the zip the OpenDocument standard asks for (mimetype first and
stored), well-formed XML, the Markdown's structure kept, the AI Act mark in the meta and on the page, and only
Aurora's own .odt recognised as hers."""
import zipfile
from pathlib import Path
from xml.dom import minidom

from aurora import doc_odt

MD = ("# Titolo\n\nTesto con **grassetto**, *corsivo* e `codice` & <segni>.\n\n- uno\n- due\n\n1. primo\n2. secondo\n\n"
      "> citazione\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n```\nx = 1\n```\n")


def _cfg(cfg, tmp_path):
    class C:
        def __getitem__(self, k):
            return cfg[k]

        def path(self, k):
            return tmp_path if k == "AURORA_DOCUMENTS_DIR" else cfg.path(k)
    return C()


def test_the_file_follows_the_standard_and_keeps_the_structure(cfg, tmp_path):
    p = doc_odt.create("Verbale", MD, "it", _cfg(cfg, tmp_path))
    assert p.suffix == ".odt" and p.parent == tmp_path
    with zipfile.ZipFile(p) as z:
        first = z.infolist()[0]
        assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED
        assert z.read("mimetype").decode() == doc_odt.MIME
        content = z.read("content.xml").decode()
        for name in ("content.xml", "styles.xml", "meta.xml", "META-INF/manifest.xml"):
            minidom.parseString(z.read(name))                     # well-formed
    assert "<text:h" in content and 'text:style-name="LN"' in content and 'text:style-name="LB"' in content
    assert "<table:table>" in content and "&amp; &lt;segni&gt;" in content and 'text:style-name="Code"' in content


def test_the_ai_act_mark_and_who_wrote_it(cfg, tmp_path):
    p = doc_odt.create("Nota", "ciao", "it", _cfg(cfg, tmp_path))
    meta = zipfile.ZipFile(p).read("meta.xml").decode()
    assert "<meta:generator>Aurora</meta:generator>" in meta
    if doc_odt.sys_disclosure._on(cfg):
        assert 'meta:name="AIGenerated">true' in meta
    assert doc_odt.made_by_aurora(p)
    other = tmp_path / "mio.odt"
    with zipfile.ZipFile(other, "w") as z:
        z.writestr("meta.xml", "<x/>")
    assert not doc_odt.made_by_aurora(other) and not doc_odt.made_by_aurora(tmp_path / "manca.odt")


def test_a_second_document_with_the_same_title_gets_a_number(cfg, tmp_path):
    a = doc_odt.create("Uguale", "uno", "it", _cfg(cfg, tmp_path))
    b = doc_odt.create("Uguale", "due", "it", _cfg(cfg, tmp_path))
    assert a != b and b.name.endswith("-2.odt") and not list(tmp_path.glob("*.part"))

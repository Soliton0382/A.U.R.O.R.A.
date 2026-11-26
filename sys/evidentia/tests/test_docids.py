# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The collections are configuration, never code (27 Nov): a generic Bates number without a file, the installation's
own collections from docids.json, bad entries refused, and the keys of an installation unchanged by the move."""
import json

import pytest

from evidentia import docids


def test_without_a_file_a_generic_bates_number_is_recognised():
    docids.configure(docids.DEFAULT)
    assert docids.parse("/x/ABC0001234.pdf").key == "BATES:ABC0001234"
    assert docids.parse("/x/smith-12345_dup_2.pdf").key == "BATES:SMITH-12345"
    assert docids.parse("/x/lettera a Rossi.pdf").key == "OTHER:lettera a Rossi"


def test_configured_collections_their_order_case_and_official_link():
    docids.configure([{"name": "ABCD", "pattern": r"^(ABCD\d{8})(?:_dup_\d+)?$", "upper": True,
                       "official": "https://example.org/{number}.pdf"},
                      {"name": "REL", "pattern": r"^(REL[-_A-Za-z0-9.]+)$", "upper": False}])
    a = docids.parse("abcd00000007_dup_1.pdf")
    assert a.key == "ABCD:ABCD00000007" and docids.cite(a, 3) == "ABCD00000007 p. 3 (https://example.org/ABCD00000007.pdf)"
    assert docids.parse("REL-ogr-9.tif").key == "REL:REL-ogr-9"            # its own case kept
    assert docids.cite(docids.parse("REL-ogr-9.tif")) == "REL-ogr-9"       # no link: never guessed


@pytest.mark.parametrize("bad", [{"name": "OTHER", "pattern": "^(x)$"}, {"name": "a b", "pattern": "^(x)$"},
                                 {"name": "ABC", "pattern": "^x$"}])
def test_bad_collections_are_refused(bad):
    with pytest.raises(ValueError):
        docids.configure([bad])


def test_the_file_in_the_data_folder_is_read(tmp_path, monkeypatch):
    (tmp_path / "docids.json").write_text(json.dumps({"collections": [{"name": "XY", "pattern": r"^(XY\d{3})$"}]}))

    class C:
        def path(self, k):
            return tmp_path
    from evidentia import config
    monkeypatch.setattr(config, "load", lambda *a: C())
    docids._loaded = None
    assert docids.parse("xy123.pdf").key == "XY:XY123"

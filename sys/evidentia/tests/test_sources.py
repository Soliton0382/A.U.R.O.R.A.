# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""R22: the folders to read in, from the WebUI — only under the roots named, by names, never out through «..» or a
link; what a folder holds; one inventory at a time, its lines without a file's name."""
import json
import sys
import time
from pathlib import Path

import pytest

from evidentia import sources as S


class Cfg(dict):
    def __getitem__(self, k):
        return dict.get(self, k, "")

    def path(self, k):
        return Path(self[k])


@pytest.fixture
def tree(tmp_path, monkeypatch):
    nas = tmp_path / "nas"
    (nas / "DOJ" / "sub").mkdir(parents=True)
    (nas / "EFTA").mkdir()
    for i in range(3):
        (nas / "EFTA" / f"ABCD0000000{i}.pdf").write_bytes(b"%PDF-1.4")
    (nas / "DOJ" / "a.jpg").write_bytes(b"x")
    (nas / "DOJ" / "notes.txt").write_text("x")
    (tmp_path / "secret").mkdir()
    (nas / "out").symlink_to(tmp_path / "secret")
    monkeypatch.setattr(S, "RUN", tmp_path / "run")
    (tmp_path / "run").mkdir()
    (tmp_path / "data").mkdir()
    return Cfg(EVD_SOURCES_DIR=str(tmp_path / "gone"), EVD_NAS_DIR=str(nas), EVD_DATA_DIR=str(tmp_path / "data")), nas


def test_roots_and_what_a_folder_holds(tree):
    cfg, nas = tree
    r = S.roots(cfg)
    assert [(x["kind"], x["reachable"]) for x in r] == [("originals", False), ("nas", True)]
    top = S.browse(cfg, 1, "")
    assert top["dirs"] == ["DOJ", "EFTA"] and top["pdfs"] == 0                     # a link is not a folder offered
    assert S.browse(cfg, 1, "EFTA")["pdfs"] == 3
    d = S.browse(cfg, 1, "DOJ")
    assert d["images"] == 1 and d["other"] == 1 and d["dirs"] == ["sub"]


@pytest.mark.parametrize("root,path", [(1, ".."), (1, "DOJ/../.."), (1, "out"), (5, ""), (-1, "")])
def test_nothing_outside_a_root(tree, root, path):
    cfg, _ = tree
    with pytest.raises(ValueError):
        S.resolve(cfg, root, path)


def test_one_inventory_at_a_time_and_its_lines_without_names(tree, monkeypatch, tmp_path):
    cfg, nas = tree
    fake = tmp_path / "fake_inventory.py"
    fake.write_text("import sys, time\nprint('3 documents to read', flush=True)\nprint('  conflict, not read: ABCD00000001.pdf', flush=True)\n"
                    "time.sleep(1.5)\nprint('done', flush=True)\n")
    monkeypatch.setattr(S, "SCRIPT", fake)
    st = S.start(cfg, 1, "EFTA", False, "boss")
    assert st["running"] and st["path"] == "EFTA"
    with pytest.raises(RuntimeError):
        S.start(cfg, 1, "DOJ", True)
    for _ in range(50):
        if not S.status()["running"]:
            break
        time.sleep(0.1)
    end = S.status()
    assert end["running"] is False and "done" in end["lines"] and not any("ABCD" in l for l in end["lines"])
    assert json.loads((tmp_path / "run" / "ingest.json").read_text())["by"] == "boss"


def test_each_user_has_an_archive_and_roots_of_their_own(tree, tmp_path, monkeypatch):
    """R15: the owner keeps the archive as it was; another user's is made under the archives' folder; their roots are
    their own NAS folder only (N168), never the owner's."""
    from evidentia import archive as A
    cfg, nas = tree
    cfg.update(EVD_OWNER="boss", EVD_ARCHIVE_DIR=str(tmp_path / "archives"))
    (tmp_path / "archives").mkdir()
    assert A.folder(cfg, "boss") == tmp_path / "data" and A.folder(cfg, "") == tmp_path / "data"
    assert A.folder(cfg, "ann") == tmp_path / "archives" / "ann" / "data" and (tmp_path / "archives" / "ann" / "data").is_dir()
    with pytest.raises(ValueError):
        A.folder(cfg, "../etc")
    tok = A.USER.set("ann")
    try:
        assert S.roots(cfg) == []                                  # no NAS folder of hers yet: none of the owner's
        monkeypatch.setattr(S, "NAS_USER", str(tmp_path / "nas-{user}"))
        (tmp_path / "nas-ann").mkdir()
        assert [r["path"] for r in S.roots(cfg)] == [str(tmp_path / "nas-ann")]
    finally:
        A.USER.reset(tok)
    assert [r["kind"] for r in S.roots(cfg)] == ["originals", "nas"]         # the owner's, as before

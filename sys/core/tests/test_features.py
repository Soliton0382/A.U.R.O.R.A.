# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import json

import pytest

from aurora import sys_features as F


@pytest.fixture
def root(tmp_path, monkeypatch, cfg):
    """A tiny installation: a manifest with two models, and only some of their files on disk."""
    man = tmp_path / "models.json"
    man.write_text(json.dumps({"models": {
        "segment": {"dir": "m/sam", "files": ["a.bin", "b.json"], "settings": {"AURORA_SEGMENT_MODEL_DIR": "m/sam"}},
        "video": {"dir": "m/wan", "files": ["x.bin"], "settings": {"AURORA_VIDEO_MODEL_DIR": "m/wan"}}}}))
    monkeypatch.setattr(F, "MANIFEST", man)
    monkeypatch.setattr(F, "ROOT", tmp_path)
    (tmp_path / "m/sam").mkdir(parents=True)
    (tmp_path / "m/sam/a.bin").write_bytes(b"1")
    (tmp_path / "m/sam/b.json").write_bytes(b"")          # an empty file is a broken download, not a model
    cfg.values.update(AURORA_SEGMENT_MODEL_DIR="m/sam", AURORA_VIDEO_MODEL_DIR="m/wan")
    return tmp_path


def test_a_missing_or_empty_model_file_closes_the_feature_with_the_command(root, cfg):
    c = F.check(cfg, "cutout")
    assert not c["ok"] and c["missing"] == ["segment (1 file)"]
    assert c["fix"] == [".venv/bin/python sys/core/script/sys_models_fetch.py --models segment --yes"]
    (root / "m/sam/b.json").write_text("{}")
    assert F.ok(cfg, "cutout")


def test_need_speaks_to_the_owner_in_his_language(root, cfg):
    with pytest.raises(F.Missing) as e:
        F.need(cfg, "video_make", "Italian")
    assert e.value.feature == "video_make" and "Creare video" in str(e.value) and "--models video" in str(e.value)
    with pytest.raises(F.Missing) as e:
        F.need(cfg, "video_make", "en")
    assert "Making videos" in str(e.value)


def test_a_model_moved_elsewhere_by_the_owner_is_trusted_if_it_exists(root, cfg, tmp_path):
    own = tmp_path / "elsewhere"
    own.mkdir()
    cfg.values["AURORA_VIDEO_MODEL_DIR"] = str(own)
    assert F.ok(cfg, "video_make") or "ffmpeg" in F.check(cfg, "video_make")["missing"]


def test_a_switch_on_without_its_model_is_a_contradiction(root, cfg, monkeypatch):
    monkeypatch.setattr(F, "FEATURES", {"cutout": (False, {"it": "x", "en": "x"}, ["segment"], [], "AURORA_IMAGE_ENABLED", [])})
    cfg.values["AURORA_IMAGE_ENABLED"] = True
    assert any("AURORA_IMAGE_ENABLED acceso" in p for p in F.config_problems(cfg))
    cfg.values["AURORA_IMAGE_ENABLED"] = False
    assert "AURORA_IMAGE_ENABLED = off" in F.check(cfg, "cutout")["missing"]

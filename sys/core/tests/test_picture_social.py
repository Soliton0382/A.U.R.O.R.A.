# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C483: a routine's picture stays plain for the social plugins; a picture asked in a chat is sealed (C458)."""
from aurora import agt_loop_make, mdl_image, sys_features, sys_uploads


class Maker(agt_loop_make.AgentMakers):
    def __init__(self, cfg, asked):
        self.cfg, self.asked, self.produced = cfg, asked, []


def _paint(cfg, monkeypatch):
    def paint(prompt, name, c, emit, title=""):
        (cfg.path("AURORA_IMAGE_DIR") / f"{name}.png").write_bytes(b"png")
        return {"file": f"{name}.png", "seconds": 1}
    cfg.path("AURORA_IMAGE_DIR").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mdl_image, "paint", paint)
    monkeypatch.setattr(sys_features, "need", lambda *a: None)
    seen = []
    real = sys_uploads.save
    monkeypatch.setattr(sys_uploads, "save", lambda *a, **k: seen.append(k["private"]) or real(*a, **k))
    return seen


def test_a_routine_picture_is_not_sealed_and_a_chat_one_is(cfg, monkeypatch):
    seen = _paint(cfg, monkeypatch)
    for asked in (False, True):
        out = Maker(cfg, asked)._picture({"prompt": "a nebula over the sea, oil painting"}, lambda *a: None, "r1")
        assert out.startswith("PAINTED")
    assert seen == [False, True]
    left = sorted(p.name for p in cfg.path("AURORA_IMAGE_DIR").iterdir())
    assert len(left) <= 1                                 # the routine's copy only (both share the second's name)


def test_the_routine_picture_is_found_by_the_social_plugin(cfg, monkeypatch):
    import importlib.util
    from pathlib import Path
    from aurora import sys_config
    _paint(cfg, monkeypatch)
    out = Maker(cfg, False)._picture({"prompt": "a nebula over the sea, oil painting"}, lambda *a: None, "r1")
    name = out.split()[1]
    spec = importlib.util.spec_from_file_location("fb", Path(__file__).parents[2] / "plugins" / "facebook" / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(sys_config, "get", lambda: cfg)
    assert mod._picture(name).read_bytes() == b"png"

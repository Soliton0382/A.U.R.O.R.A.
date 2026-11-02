# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C486: a picture takes the reasoner out of the GPU without cutting an answer, and a local call asked meanwhile waits."""
import threading
import time

import httpx

from aurora import mdl_image


class Slots:
    def __init__(self, busy):
        self.busy, self.asked = list(busy), 0

    def __call__(self, url, timeout=None):
        self.asked += 1
        on = self.busy.pop(0) if self.busy else False
        return httpx.Response(200, json=[{"is_processing": on}, {"is_processing": False}])


def stage(monkeypatch, busy):
    units, slots = [], Slots(busy)
    monkeypatch.setattr(mdl_image, "_unit", lambda verb, u: units.append(verb))
    monkeypatch.setattr(mdl_image.httpx, "get", slots)
    monkeypatch.setattr(mdl_image, "_wait", lambda cond, limit, step=2.0: any(cond() for _ in range(5)))
    return units, slots


def test_the_stop_waits_for_what_the_reasoner_is_writing(cfg, monkeypatch):
    units, slots = stage(monkeypatch, [True, True, False])
    mdl_image.reasoner_out(cfg)
    assert units == ["stop"] and slots.asked == 3 and mdl_image._hold_file(cfg).is_file()


def test_past_the_limit_it_stops_anyway(cfg, monkeypatch):
    units, _ = stage(monkeypatch, [True] * 9)
    mdl_image.reasoner_out(cfg)
    assert units == ["stop"]


def test_a_reasoner_that_does_not_answer_has_nothing_to_lose(cfg, monkeypatch):
    def down(url, timeout=None):
        raise httpx.ConnectError("refused")
    monkeypatch.setattr(mdl_image.httpx, "get", down)
    assert mdl_image._slots_idle(cfg) is True


def test_back_lets_the_calls_go_even_when_the_start_fails(cfg, monkeypatch):
    mdl_image._hold_file(cfg).parent.mkdir(parents=True, exist_ok=True)
    mdl_image._hold_file(cfg).write_text("1")

    def broken(verb, u):
        raise RuntimeError("no")
    monkeypatch.setattr(mdl_image, "_unit", broken)
    try:
        mdl_image.reasoner_back(cfg, 1)
    except RuntimeError:
        pass
    assert not mdl_image._hold_file(cfg).exists()


def test_a_call_waits_while_the_lock_is_held_and_goes_once_the_hold_ends(cfg):
    went = []
    mdl_image._hold_file(cfg).parent.mkdir(parents=True, exist_ok=True)
    with mdl_image.gpu_lock(cfg, 1, "a picture"):
        mdl_image._hold_file(cfg).write_text("1")
        t = threading.Thread(target=lambda: (mdl_image.swap_wait(cfg, 20), went.append(True)))
        t.start()
        time.sleep(0.3)
        assert not went
        mdl_image._hold_off(cfg)
        t.join(5)
    assert went


def test_a_hold_whose_holder_died_holds_nobody(cfg):
    mdl_image._hold_file(cfg).parent.mkdir(parents=True, exist_ok=True)
    mdl_image._hold_file(cfg).write_text("1")
    t0 = time.time()
    mdl_image.swap_wait(cfg, 20)
    assert time.time() - t0 < 3
    with mdl_image.gpu_lock(cfg, 1, "a video that needs no swap"):       # and the next job clears it
        assert not mdl_image._hold_file(cfg).exists()

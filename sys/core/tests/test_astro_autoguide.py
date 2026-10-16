# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 The guiding tuned during the night (ROADMAP N28): invented guide steps read into one proposal with its why; a change
applied only in «apply», only inside the limits, judged A/B on the RMS and put back when it made things worse; the
quiet seconds after a dither not counted; PHD2's JSON-RPC spoken to a fake guider."""
import json
import random
import socket
import threading

from aurora import ast_autoguide as T

LIMITS = {"exposure_ms": [1000, 3000], "ra_min_move": [0.10, 0.40], "dec_min_move": [0.10, 0.50]}
NOW = {"exposure_ms": 1000, "ra_min_move": 0.15, "dec_min_move": 0.15}


def steps(n=200, t0=1000.0, ra=lambda i: 0.0, dec=lambda i: 0.0, ra_ms=lambda i: 0, snr=30.0):
    return [{"t": t0 + i, "ra": ra(i), "dec": dec(i), "ra_ms": ra_ms(i), "dec_ms": 0, "snr": snr} for i in range(n)]


def test_chasing_the_seeing_asks_a_larger_minimum_move():
    s = steps(ra=lambda i: 0.6 if i % 2 else -0.6, ra_ms=lambda i: 100 if i % 2 else -100)
    p = T.diagnose(s, [], NOW, LIMITS)
    assert p["param"] == "ra_min_move" and p["to"] == 0.2 and p["why"] == "chasing"


def test_an_error_on_one_side_asks_a_smaller_one():
    rnd = random.Random(1)
    s = steps(dec=lambda i: 0.8 + rnd.gauss(0, 0.3))
    p = T.diagnose(s, [], NOW, LIMITS)
    assert p["param"] == "dec_min_move" and p["to"] == 0.1 and p["why"] == "lagging"


def test_a_weak_star_asks_a_longer_exposure_and_the_limits_hold():
    s = steps(snr=8.0)
    assert T.diagnose(s, [], NOW, LIMITS)["to"] == 1500
    assert T.diagnose(s, [], {**NOW, "exposure_ms": 3000}, LIMITS) is None               # 3500 is beyond the limit
    assert T.diagnose(s, [], NOW, LIMITS, {("exposure_ms", 1500)}) is None                 # tried and put back already
    assert T.diagnose(steps(n=50, snr=8.0), [], NOW, LIMITS) is None                       # too few steps to judge


def test_the_quiet_seconds_after_a_dither_do_not_count():
    s = steps(n=100)
    c = T.clean(s, [{"t": 1050.0, "event": "GuidingDithered"}])
    assert len(c) == 80 and not any(1050 <= x["t"] < 1070 for x in c)


class Fake:
    def __init__(self):
        self.v, self.sets = dict(NOW), []

    def get(self):
        return dict(self.v)

    def set(self, k, v):
        self.v[k] = v
        self.sets.append((k, v))


def tuner(mode, tmp_path):
    t = T.Tuner.__new__(T.Tuner)                    # no thread: the steps are driven by hand
    t.host, t.port, t.folder, t.mode, t.limits = "x", 1, tmp_path, mode, LIMITS
    t.params, t.trial, t.last_change, t.tried, t.proposal, t.now, t.error = Fake(), None, 0.0, {}, None, {}, ""
    return t


def snap(s):
    return {"state": "Guiding", "connected": True, "steps": s, "events": []}


def test_propose_never_sends_and_apply_is_put_back_when_worse(tmp_path):
    chase = steps(ra=lambda i: 0.6 if i % 2 else -0.6, ra_ms=lambda i: 100 if i % 2 else -100)
    t = tuner("propose", tmp_path)
    t.step(snap(chase), clock=lambda: 10_000)
    assert t.proposal["to"] == 0.2 and t.params.sets == []
    t = tuner("apply", tmp_path)
    t.step(snap(chase), clock=lambda: 10_000)
    assert t.params.sets == [("ra_min_move", 0.2)] and t.trial["before"] == T.total_rms(chase[-T.WINDOW:])
    worse = chase + steps(n=T.TRIAL, t0=2000, ra=lambda i: 1.5 if i % 2 else -1.5)
    t.step(snap(worse), clock=lambda: 10_100)
    assert t.params.sets[-1] == ("ra_min_move", 0.15) and ("ra_min_move", 0.2) in t.tried
    log = [json.loads(x)["action"] for x in (tmp_path / "autoguide.jsonl").read_text().splitlines()]
    assert log == ["propose", "propose", "apply", "revert"]


def test_a_better_change_is_kept_and_nothing_moves_when_not_guiding(tmp_path):
    chase = steps(ra=lambda i: 0.6 if i % 2 else -0.6, ra_ms=lambda i: 100 if i % 2 else -100)
    t = tuner("apply", tmp_path)
    t.step({**snap(chase), "state": "Looping"}, clock=lambda: 10_000)
    assert t.params.sets == []
    t.step(snap(chase), clock=lambda: 10_000)
    t.step(snap(chase + steps(n=T.TRIAL, t0=2000, ra=lambda i: 0.2 if i % 2 else -0.2)), clock=lambda: 10_100)
    assert t.params.sets == [("ra_min_move", 0.2)] and t.trial is None
    t.step(snap(chase), clock=lambda: 10_200)                                               # within the cool-down
    assert len(t.params.sets) == 1


def fake_phd2():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    got = []
    state = {"exposure": 1000, "ra": 0.15, "dec": 0.2}

    def serve():
        while True:
            try:
                c, _ = srv.accept()
            except OSError:
                return
            f = c.makefile("rwb")
            f.write(b'{"Event":"Version","PHDVersion":"2.6.14"}\r\n')
            f.write(b'{"Event":"GuideStep","Frame":1}\r\n')
            f.flush()
            q = json.loads(f.readline())
            got.append(q)
            m, p = q["method"], q.get("params") or []
            r = {"get_algo_param_names": lambda: ["algorithmName", "Min Move", "Aggression"],
                 "get_exposure": lambda: state["exposure"],
                 "get_algo_param": lambda: state[p[0]],
                 "set_exposure": lambda: state.update(exposure=p[0]) or 0,
                 "set_algo_param": lambda: state.update({p[0]: p[2]}) or 0}[m]()
            f.write((json.dumps({"jsonrpc": "2.0", "result": r, "id": q["id"]}) + "\r\n").encode())
            f.flush()
            c.close()

    threading.Thread(target=serve, daemon=True).start()
    return srv, got, state


def test_phd2s_json_rpc():
    srv, got, state = fake_phd2()
    p = T.Phd2Params("127.0.0.1", srv.getsockname()[1])
    assert p.get() == {"exposure_ms": 1000, "ra_min_move": 0.15, "dec_min_move": 0.2}
    p.set("dec_min_move", 0.25)
    p.set("exposure_ms", 1500)
    assert state["dec"] == 0.25 and state["exposure"] == 1500
    assert {"method": "set_algo_param", "params": ["dec", "Min Move", 0.25], "id": 1} in got   # the name PHD2 gave
    srv.close()


def test_defaults_follow_the_advice():
    rows = [{"key": "guide_exposure", "advised": "1.5–3.5"}, {"key": "min_move_ra", "advised": 0.2}]
    d = T.defaults(rows)
    assert d["exposure_ms"] == [1500, 3500] and d["ra_min_move"] == [0.12, 0.32] and d["dec_min_move"] == [0.10, 0.50]

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔎 The ninth review of N145–N147 (20 Nov), its attacks replayed on invented installations: C705 a built-in leaving
the machine (phone_action, request_capability) and project_install in a run on a «riservato» project; C706 the law
gate decided by the margin outside the band, the model only in the band or for a true follow-up, bounded; C707 a
socket that cannot carry a descriptor is no reason to count the whole disk's loss; C708 the agent's and the plugins'
tables brought back by the owner, from any project; O3 the clone out of every cage's reach while it is hashed; C709
the owner's git and the agent's command never overlap; O4 vault_realign's article kept on disk between its DELETE and
its write. Invented data only."""
import base64
import hashlib
import json
import socket
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from aurora import prj_policy
from aurora import prj_provenance as V


@pytest.fixture(autouse=True)
def _engines_on(cfg):
    for k in ("AURORA_LONGRUN_ENABLED", "AURORA_DISCOVER_ENABLED", "AURORA_NOVELTY_ENABLED"):
        cfg.values[k] = True
    cfg.values["AURORA_PREREG_MODE"] = "warn"


def _proj(cfg, name):
    p = cfg.path("AURORA_PROJECTS_DIR") / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def _body(seed: int, head: str = "x,y") -> str:
    g = np.random.default_rng(seed)
    x = g.uniform(0, 3, 200)
    return head + "\n" + "".join(f"{a:.6f},{2 * a * a + e:.6f}\n" for a, e in zip(x, g.normal(0, 0.01, 200)))


# ---- C705: one list of the built-ins leaving the machine -----------------------------------------------------------
def _agent(cfg, projects=()):
    from aurora.agt_loop import Agent
    a = Agent.__new__(Agent)
    a.cfg, a.asked, a.net_read, a.projects, a.named_projects = cfg, True, None, set(projects), set()
    a.goal_text, a.loop_tools, a.host = "riassumi il progetto", None, SimpleNamespace(get=lambda n: None)
    import logging
    a.log = logging.getLogger("test-review9")
    return a


def test_c705_phone_web_search_and_the_forge_are_refused_in_a_reserved_run(cfg):
    _proj(cfg, "brevetto")
    prj_policy.save(cfg, "brevetto", {"models": "cloud", "riservato": True})
    a = _agent(cfg, {"brevetto"})
    events = []
    emit = lambda e, x=None: events.append(e)                                        # noqa: E731
    for args in ({"action": "web_search", "query": "secret winding claim 1"}, {"action": "open_url",
                                                                               "url": "https://example.org/?q=x"},
                 {"action": "message", "to": "+390000", "text": "the winding"}, {"action": "navigate", "to": "x"}):
        out = a._call("phone_action", args, {}, emit, "r1")
        assert out.startswith("REFUSED") and "reserved project brevetto" in out, out
    out = a._call("request_capability", {"need": "search patents on the winding", "why": "x"}, {}, emit, "r1")
    assert out.startswith("REFUSED"), out
    assert "phone.action" not in events and "forge.request" not in events
    # what stays on the phone is not refused by this rule (the owner's own checks follow)
    assert prj_policy.builtin_net_refusal(a, "phone_action", {"action": "timer"}) == ""
    # a run on no reserved project: not refused here
    assert prj_policy.builtin_net_refusal(_agent(cfg), "phone_action", {"action": "web_search"}) == ""


def test_c705_project_install_asks_the_network_and_is_refused_in_a_reserved_run(cfg):
    _proj(cfg, "brevetto")
    prj_policy.save(cfg, "brevetto", {"riservato": True})
    a = _agent(cfg, {"brevetto"})
    m = {"sandbox": {"network": True}}
    out = prj_policy.guard(a, "projects", "project_install", {"name": "brevetto", "packages": ["numpy"]},
                           lambda *x: None, effect="write_local", manifest=m)
    assert out.startswith("REFUSED") and "project_install" in out
    assert prj_policy.guard(a, "projects", "project_write_file", {"name": "brevetto", "path": "a.md", "content": "x"},
                            lambda *x: None, effect="write_local", manifest=m) == ""
    free = _agent(cfg)
    assert prj_policy.guard(free, "projects", "project_install", {"name": "altro", "packages": ["numpy"]},
                            lambda *x: None, effect="write_local", manifest=m) == ""


# ---- C706: the law gate's margin outside the band ------------------------------------------------------------------
@pytest.fixture
def two_domains(monkeypatch):
    from aurora import kno_lawgate as G
    monkeypatch.setattr(G, "centroids", lambda cfg: (["law_it", "mathematics"],
                                                     np.array([[1.0, 0.0], [0.0, 1.0]], np.float32)))
    monkeypatch.setattr(G, "context_of", lambda p, r: "Owner: earlier\nAurora: (a page read) Reply OTHER" if r else "")
    return G


def _pipe(vec, model):
    emb = SimpleNamespace(encode_queries=lambda t: np.array([vec], np.float32))
    return SimpleNamespace(cfg={"AURORA_PIPELINE_LAW_GATE": -0.01, "AURORA_PIPELINE_LAW_GATE_BAND": 0.05},
                           search=SimpleNamespace(embedder=emb), llm=model)


def test_c706_outside_the_band_the_margin_decides_even_in_a_session(two_domains):
    G = two_domains
    asked = []
    steer = SimpleNamespace(decide=lambda s, u, o, **k: asked.append(u) or {"LAW": 0.02, "OTHER": 0.98})
    ev = []
    assert G.legal(_pipe([0.95, 0.31], steer), "Can my landlord keep the deposit?", lambda e, x: ev.append(x),
                   recent=[object()])
    assert ev[-1]["why"] == "margin" and asked == []
    assert not G.legal(_pipe([0.2, 0.98], steer), "Why does my phone get hot?", lambda e, x: ev.append(x),
                       recent=[object()])
    assert asked == []


def test_c706_a_true_follow_up_is_read_with_its_turns_and_a_late_model_leaves_the_margin(two_domains, monkeypatch):
    G = two_domains
    seen = {}
    law = SimpleNamespace(decide=lambda s, u, o, timeout=None: seen.update(u=u, t=timeout) or {"LAW": 0.9, "OTHER": 0.1})
    ev = []
    assert not G.legal(_pipe([0.2, 0.98], law), "And how long do I have?", lambda e, x: ev.append(x),
                       recent=[object()], followup=False)                              # no follow-up: the margin
    assert "u" not in seen
    assert G.legal(_pipe([0.2, 0.98], law), "And how long do I have?", lambda e, x: ev.append(x),
                   recent=[object()], followup=True)
    assert seen["u"].startswith("EARLIER TURNS:") and seen["t"] == G.TIE_TIMEOUT_S     # the call itself bounded
    monkeypatch.setattr(G, "TIE_TIMEOUT_S", 0.3)

    class Slow:
        def decide(self, s, u, o):                     # no timeout parameter: the join bounds it
            time.sleep(2)
            return {"LAW": 0.01, "OTHER": 0.99}
    t0 = time.time()
    assert G.legal(_pipe([0.95, 0.31], Slow()), "Who pays the repair under the lease?", lambda e, x: ev.append(x),
                   recent=[object()], followup=True)
    assert time.time() - t0 < 1.5 and ev[-1]["uncertain"] is True and ev[-1]["why"].endswith("the margin")
    near = [0.7071, 0.7071]                                                             # in the band: model unsure
    unsure = SimpleNamespace(decide=lambda s, u, o, **k: {"LAW": 0.55, "OTHER": 0.45})
    assert not G.legal(_pipe(near, unsure), "Who pays for the repair?", lambda e, x: ev.append(x))
    assert ev[-1]["why"] == "the model unsure"


def test_c706_the_local_model_s_decide_bounds_the_http_call(monkeypatch, cfg):
    import httpx
    from aurora import mdl_image, mdl_llm
    got = {}
    monkeypatch.setattr(mdl_image, "swap_wait", lambda c, limit: got.setdefault("swap", limit))

    def post(url, timeout=None, json=None):
        got["timeout"] = timeout
        raise httpx.ReadTimeout("late")
    monkeypatch.setattr(mdl_llm.httpx, "post", post)
    monkeypatch.setattr(mdl_llm.LLM, "fmt", property(lambda self: SimpleNamespace(template="chatml")))
    m = mdl_llm.LLM(cfg)
    m.timeout, m.url = 600, "http://127.0.0.1:1"
    assert m.decide("s", "u", ["LAW", "OTHER"], timeout=8.0) is None
    assert got["swap"] <= 8.0 and got["timeout"] <= 8.0


# ---- C707: only a socket that can carry a descriptor ---------------------------------------------------------------
def _fd_of(s) -> int:
    return s.fileno()


def test_c707_an_idle_socketpair_is_no_carrier_a_queued_or_datagram_one_is():
    import os
    from aurora import prj_run_disk as K
    me = os.getpid()
    a, b = socket.socketpair()                                       # asyncio's self-pipe, multiprocessing.Pipe
    try:
        assert not K.carries(me, _fd_of(a)) and not K.carries(me, _fd_of(b))
        a.send(b"x")                                                 # a byte unread: a descriptor could ride on it
        assert K.carries(me, _fd_of(a)) and K.carries(me, _fd_of(b))
        b.recv(1)
        assert not K.carries(me, _fd_of(b))
    finally:
        a.close(), b.close()
    c, d = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)    # an empty datagram can carry one
    lst = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    lst.bind("\0aurora-test-review9-%d" % me)
    lst.listen(1)
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        assert K.carries(me, _fd_of(c)) and K.carries(me, _fd_of(lst))
        assert not K.carries(me, _fd_of(tcp))                        # not a unix socket: never
        assert K.carries(me, 99999)                                  # no copy to be had: a carrier, as before
    finally:
        for s in (c, d, lst, tcp):
            s.close()


def test_c707_held_counts_no_hidden_holder_for_an_idle_pipe(tmp_path):
    import os
    from aurora import prj_run_disk as K
    h0 = K.held([os.getpid()], tmp_path)[1]                         # pytest's own sockets, if any
    a, b = socket.socketpair()
    try:
        assert K.held([os.getpid()], tmp_path)[1] == h0
        a.send(b"x")
        assert K.held([os.getpid()], tmp_path)[1] == h0 + 2
    finally:
        a.close(), b.close()


# ---- C708: the agent's and the plugins' tables, from any project ---------------------------------------------------
def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def test_c708_an_agent_s_table_of_project_a_brought_into_project_b_stays_the_agent_s(cfg):
    a, b = _proj(cfg, "scratch"), _proj(cfg, "main")
    raw = _body(1).encode()
    (a / "fake.csv").write_bytes(raw)
    V.record(cfg, "scratch", a, ["fake.csv"], "run")                  # a command in the cage wrote it
    row = V.record_owner_bytes(cfg, "main", "data/fake.csv", raw, "upload", "owner", "from the lab")
    assert row["echo"]["project"] == "scratch"
    o = V.origin(cfg, "main", "data/fake.csv", _sha(raw))
    assert not o["claimable"] and "scratch" in o["why"]
    # even an owner row made before C708 (no echo): the agent's row of another project is read at the verdict
    raw2 = _body(2).encode()
    (a / "g.csv").write_bytes(raw2)
    V.record(cfg, "scratch", a, ["g.csv"], "run")
    time.sleep(0.01)
    V._append(cfg, "main", [{"t": time.time(), "rel": "g.csv", "by": V.OWNER, "sha256": _sha(raw2),
                             "canonical": V._canonical(raw2, "g.csv"), "how": "upload"}])
    o = V.origin(cfg, "main", "g.csv", _sha(raw2))
    assert not o["claimable"] and "in project scratch" in o["why"]


def test_c708_a_plugin_s_table_brought_back_bytes_or_numbers_is_never_the_owner_s(cfg):
    rc = _proj(cfg, "rc")
    (rc / "circuits").mkdir()
    body = _body(3, "t,v")
    (rc / "circuits" / "tran.csv").write_text(body)                 # a plugin's table: no row at all
    raw = body.encode()
    row = V.record_owner_bytes(cfg, "rc", "data/tran.csv", raw, "upload")
    assert row["echo"]["rel"] == "circuits/tran.csv"
    for rel in ("data/tran.csv", "circuits/tran.csv"):
        assert not V.origin(cfg, "rc", rel, _sha(raw))["claimable"]
    other = body.replace("\n", "\r\n").encode()                       # the same numbers, saved again by a spreadsheet
    assert other != raw
    row = V.record_owner_bytes(cfg, "rc", "data/tran2.csv", other, "upload")
    assert row.get("echo"), row


def test_c708_the_owner_s_own_upload_brought_into_another_project_stays_the_owner_s(cfg, monkeypatch):
    from aurora import prj_provenance_seen as S
    p, q = _proj(cfg, "p1"), _proj(cfg, "p2")
    raw = _body(4).encode()
    V.record_owner_bytes(cfg, "p1", "d.csv", raw, "upload")
    (p / "d.csv").write_bytes(raw)
    row = V.record_owner_bytes(cfg, "p2", "d.csv", raw, "upload")
    assert not row.get("echo") and V.origin(cfg, "p2", "d.csv", _sha(raw))["claimable"]
    # past the time budget some tables were not compared: never claimable either, and said
    (q / "other.csv").write_text(_body(5))
    monkeypatch.setattr(S, "BUDGET_S", 0.0)
    monkeypatch.setattr(S.tables_like, "__defaults__", (("", ""), None, 0.0))
    row = V.record_owner_bytes(cfg, "p2", "e.csv", _body(6).encode(), "upload")
    assert row["echo"].get("unchecked") and "time budget" in S.said(row["echo"])


def _api(cfg, monkeypatch):
    import importlib
    import sys
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from aurora import sys_config
    monkeypatch.setattr(sys_config, "_cached", cfg)
    for m in [m for m in sys.modules if m.startswith("aurora.api")]:
        monkeypatch.delitem(sys.modules, m)
    for name in ("oai", "runs"):
        importlib.import_module(f"aurora.api.{name}")
    from aurora.api import core, projects
    app = FastAPI()
    app.include_router(projects.router)
    app.dependency_overrides[core.auth] = lambda: None
    return TestClient(app)


def test_c708_the_upload_s_answer_says_it_is_the_agent_s_table(cfg, monkeypatch):
    a = _proj(cfg, "scratch")
    _proj(cfg, "main")
    raw = _body(7).encode()
    (a / "fake.csv").write_bytes(raw)
    V.record(cfg, "scratch", a, ["fake.csv"], "run")
    client = _api(cfg, monkeypatch)
    r = client.post("/v1/aurora/projects/main/data", json={"path": "data/fake.csv", "data": base64.b64encode(raw).decode()})
    assert r.status_code == 200 and r.json()["evidence"] is False and "project scratch" in r.json()["warning"], r.text


def test_o3_the_clone_is_made_and_hashed_out_of_the_projects_folder(cfg, monkeypatch):
    from aurora import prj_gitsafe
    base = cfg.path("AURORA_PROJECTS_DIR")
    base.mkdir(parents=True, exist_ok=True)
    where = {}

    def fake(full, dest, token):
        where["dest"] = Path(dest)
        script = f"mkdir -p '{dest}/data' && printf 'x,y\\n1,2\\n2,8\\n' > '{dest}/data/c.csv'"
        return ["sh", "-c", script], {}
    monkeypatch.setattr(prj_gitsafe, "clone_command", fake)
    client = _api(cfg, monkeypatch)
    r = client.post("/v1/aurora/projects/clone", json={"full_name": "someone/demo"})
    assert r.status_code == 200, r.text
    name = r.json()["name"]
    assert base.resolve() not in where["dest"].resolve().parents                    # never in the projects folder
    raw = (base / name / "data" / "c.csv").read_bytes()
    assert V.origin(cfg, name, "data/c.csv", _sha(raw))["kind"] == "owner"
    assert not where["dest"].parent.exists()                                         # the temporary folder gone


# ---- C709: the owner's git and the agent's command never overlap ---------------------------------------------------
def test_c709_run_in_project_refused_while_the_owner_saves_or_has_a_terminal(cfg, monkeypatch):
    from aurora import prj_package, prj_run, prj_term
    p = _proj(cfg, "both")
    with prj_package._guard:
        lock = prj_package._locks.setdefault(str(prj_run.project_dir(cfg, "both")), threading.Lock())
    lock.acquire()
    try:
        with pytest.raises(RuntimeError, match="saving this project"):
            prj_run._enter(prj_run.project_dir(cfg, "both"))
    finally:
        lock.release()
    monkeypatch.setattr(prj_term, "open_on", lambda project: 1)
    with pytest.raises(RuntimeError, match="terminal"):
        prj_run._enter(p)
    monkeypatch.setattr(prj_term, "open_on", lambda project: 0)
    key = prj_run._enter(p)
    try:
        assert prj_run.going(p) == 1
        with pytest.raises(prj_term.TermError, match="agent"):
            prj_term._refuse_during_longrun(cfg, p)
        with pytest.raises(prj_package.PackageError, match="agent"):
            prj_package.prepare(cfg, "both", "owner", "first save", bundle=False)
    finally:
        prj_run._leave(key)
    assert prj_run.going(p) == 0


def test_c709_o1_a_long_run_ended_but_not_finished_still_counts_as_busy(cfg, monkeypatch):
    from aurora import prj_longrun as R
    rows = [{"status": "ended", "t": time.time()}]
    monkeypatch.setattr(R, "runs", lambda c, p: rows)
    assert R.busy(cfg, "x")
    rows[0]["finished"] = "2026-11-20"
    assert not R.busy(cfg, "x")


# ---- O4: vault_realign keeps the article on disk between its DELETE and its write ----------------------------------
def _realign():
    import importlib.util
    path = Path(__file__).resolve().parents[1] / "script" / "vault_realign.py"
    spec = importlib.util.spec_from_file_location("vault_realign_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeVault:
    """An invented vault behind an invented API: articles by identity, the DELETE and the import."""

    def __init__(self, die_on_write=False):
        self.docs = {("history", "wiki_1"): {"ident": "wikipedia:Invented Article", "title": "Invented Article",
                                             "text": "an invented article " * 40}}
        self.die = die_on_write

    def delete(self, path, params=None):
        self.docs.pop((params["domain"], params["source_id"]), None)
        return SimpleNamespace(is_success=True)

    def post(self, path, json=None):
        if self.die:
            raise KeyboardInterrupt("stopped between the DELETE and the write")
        text = base64.b64decode(json["data"]).decode()
        self.docs[(json["domain"], "new_" + json["domain"])] = {"ident": json["origin"], "title": json["title"],
                                                                "text": text}
        return SimpleNamespace(is_success=True, json=lambda: {"written": 3, "chunks": 3})

    def groups(self):
        out = {}
        for (dom, sid), d in self.docs.items():
            out.setdefault(d["ident"], []).append({"domain": dom, "source_id": sid, "title": d["title"],
                                                   "text": d["text"][:1500], "lang": "en"})
        return out


def test_o4_an_article_stopped_between_delete_and_write_is_written_at_the_next_apply(cfg, monkeypatch):
    m = _realign()
    vault = _FakeVault(die_on_write=True)
    monkeypatch.setattr(m, "articles", lambda c: vault.groups())
    monkeypatch.setattr(m, "passages_of", lambda c, d, s: vault.docs[(d, s)]["text"])
    monkeypatch.setattr(m.kno_domain, "choose", lambda reader, title, text, dom: "literature")
    monkeypatch.setattr(m.mdl_router, "model_for", lambda *a: None)
    monkeypatch.setattr(m, "LLM", lambda c: None)
    get = lambda url, **p: (_ for _ in ()).throw(RuntimeError("no web in the tests"))     # noqa: E731
    a = SimpleNamespace(apply=True, fresh=False, only="", only_file="")
    with pytest.raises(KeyboardInterrupt):
        m.wikipedia(cfg, a, vault, get)
    assert vault.docs == {}                                                           # deleted, not yet written
    pending = list(m._pending(cfg).glob("*.json"))
    assert len(pending) == 1 and json.loads(pending[0].read_text())["target"] == "literature"
    vault.die = False
    assert m.wikipedia(cfg, a, vault, get) == 0
    assert [k[0] for k in vault.docs] == ["literature"] and "invented article" in next(iter(vault.docs.values()))["text"]
    assert list(m._pending(cfg).glob("*.json")) == []

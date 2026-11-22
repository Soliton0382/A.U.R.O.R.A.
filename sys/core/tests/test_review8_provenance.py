# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🧾 The eighth review of N145–N147 (20 Nov), its attacks replayed on invented installations: C697 a table recorded
under the path as typed («./t.csv») and written under the normalised one; C698 a plugin writing tables with no record;
both closed by construction — the provenance is POSITIVE (only a row the owner's own request made, prj_provenance.
record_owner, makes a table claimable), shown with a write path invented here that no code of Aurora knows; C699 two
keys naming two projects, checked with the real MCP validation; C703 sparse tables and the hash's time budget; C704
a project read through any plugin joins the run, and a «riservato» run reaches no network. Invented tables only."""
import asyncio
import base64
import os
import time
import warnings
from types import SimpleNamespace

import numpy as np
import pytest

from aurora import prj_discover as D
from aurora import prj_policy, prj_safeio
from aurora import prj_provenance as V


@pytest.fixture(autouse=True)
def _engines_on(cfg):
    for k in ("AURORA_LONGRUN_ENABLED", "AURORA_DISCOVER_ENABLED", "AURORA_NOVELTY_ENABLED"):
        cfg.values[k] = True
    cfg.values["AURORA_PREREG_MODE"] = "warn"


@pytest.fixture
def proj(cfg):
    p = cfg.path("AURORA_PROJECTS_DIR") / "lab"
    p.mkdir(parents=True)
    return p


def _body(seed: int) -> str:
    g = np.random.default_rng(seed)
    x = g.uniform(0, 3, 300)
    return "x,y\n" + "".join(f"{a:.6f},{3 * a * a + e:.6f}\n" for a, e in zip(x, g.normal(0, 0.01, 300)))


class _Agent:
    def __init__(self, cfg):
        self.cfg, self.projects, self.local_only = cfg, set(), False


# ---- C697 / C698: positive provenance ----------------------------------------------------------------------------
@pytest.mark.parametrize("typed", ["./t0.csv", "sub//t2.csv", "t4.csv/", "./sub/./t5.csv", "ABS"])
def test_c697_a_table_written_by_a_write_tool_under_any_spelling_is_never_discovered(cfg, proj, typed):
    """The referee's n2.py: the guard records the path as typed, the plugin writes the normalised one."""
    path = str(proj.resolve() / "t3.csv") if typed == "ABS" else typed
    assert prj_policy.guard(_Agent(cfg), "projects", "project_write_file",
                            {"name": "lab", "path": path, "content": _body(1)}, lambda *x: None) == ""
    rel = prj_safeio.norm(path, proj.resolve())
    prj_safeio.write_text(proj.resolve(), rel, _body(1))
    r = D.discover(cfg, "lab", rel, "y", runner=D.direct)
    assert r["status"] == "passed_not_claimable" and r["origin"] in ("agent", "none"), D.text(r)
    assert "DISCOVERED" not in D.text(r).splitlines()[0]


def test_c697_without_any_record_of_the_write_the_table_stays_not_claimable(cfg, proj, monkeypatch):
    """By construction: even with record_path gone (a write path nobody recorded), no owner's row → not claimable."""
    monkeypatch.setattr(V, "record_path", lambda *a, **k: None)
    prj_policy.guard(_Agent(cfg), "projects", "project_write_file", {"name": "lab", "path": "./t.csv"}, lambda *x: None)
    (proj / "t.csv").write_text(_body(2))
    r = D.discover(cfg, "lab", "t.csv", "y", runner=D.direct)
    assert r["status"] == "passed_not_claimable" and r["origin"] == "none", D.text(r)
    assert "no record that the owner brought" in D.text(r)


def _teleport(root, rel: str, text: str) -> None:
    """A write path invented for this test: no module of Aurora knows it (a future plugin, a new command)."""
    fd = os.open(os.path.join(root, rel), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    with os.fdopen(fd, "w") as fh:
        fh.write(text)


def test_c698_a_plugin_s_table_and_a_new_write_path_are_never_discovered(cfg, proj):
    """The referee's n6.py (circuits writes <project>/circuits/<name>/tran.csv; its guard records nothing) and a way
    of writing no code of Aurora has seen: both stay at PASSED, NOT CLAIMABLE, with the reason."""
    a = _Agent(cfg)
    assert prj_policy.guard(a, "circuits", "circuit_simulate", {"project": "lab", "name": "rc"}, lambda *x: None) == ""
    (proj / "circuits" / "rc").mkdir(parents=True)
    (proj / "circuits" / "rc" / "tran.csv").write_text(_body(3))
    _teleport(proj, "new.csv", _body(4))
    for rel in ("circuits/rc/tran.csv", "new.csv"):
        r = D.discover(cfg, "lab", rel, "y", runner=D.direct)
        assert r["status"] == "passed_not_claimable" and r["origin"] == "none", D.text(r)
        assert "not claimable: no record that the owner brought this table in" in D.text(r)


def test_c697_the_owner_s_table_is_discovered_and_a_changed_copy_is_not(cfg, proj):
    raw = _body(5).encode()
    V.record_owner_bytes(cfg, "lab", "dati/o.csv", raw, "upload", "test", "invented")
    (proj / "dati").mkdir()
    (proj / "dati" / "o.csv").write_bytes(raw)
    r = D.discover(cfg, "lab", "dati/o.csv", "y", runner=D.direct)
    assert r["status"] == "discovered" and r["origin"] == "owner", D.text(r)
    assert "data: brought in by the owner on" in D.text(r)
    t = raw.decode().splitlines()                                   # the agent changes one number of it
    t[7] = t[7].split(",")[0] + ",1.0"
    (proj / "dati" / "o2.csv").write_text("\n".join(t) + "\n")
    r = D.discover(cfg, "lab", "dati/o2.csv", "y", runner=D.direct)
    assert r["status"] != "discovered" and r["origin"] == "none", D.text(r)


def test_c697_the_owner_bringing_back_the_agent_s_own_table_is_not_claimable(cfg, proj):
    (proj / "fake.csv").write_text(_body(6))
    V.record(cfg, "lab", proj, ["fake.csv"], "run")                 # the agent's command made it first
    V.record_owner_bytes(cfg, "lab", "mine.csv", (proj / "fake.csv").read_bytes(), "upload")
    (proj / "mine.csv").write_bytes((proj / "fake.csv").read_bytes())
    r = D.discover(cfg, "lab", "mine.csv", "y", runner=D.direct)
    assert r["status"] == "passed_not_claimable" and r["origin"] == "agent", D.text(r)
    assert "had written before" in D.text(r) or "was written in project lab" in D.text(r)      # C708: said at once


def test_c697_a_clone_s_tables_are_the_owner_s(cfg, proj):
    (proj / "data").mkdir()
    (proj / "data" / "c.csv").write_text(_body(7))
    (proj / ".git").mkdir()
    (proj / ".git" / "x.csv").write_text(_body(8))
    assert V.tables_in(proj) == ["data/c.csv"]
    assert V.record_owner(cfg, "lab", proj, V.tables_in(proj), "clone", "test", "someone/repo") == 1
    assert V.origin(cfg, "lab", "data/c.csv", V.hashlib.sha256((proj / "data" / "c.csv").read_bytes()).hexdigest())[
        "kind"] == "owner"
    with pytest.raises(ValueError):
        V.record_owner(cfg, "lab", proj, ["data/c.csv"], "agent-said-so")


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


def test_c697_the_page_s_upload_and_the_chat_s_attachment_bring_owner_tables(cfg, proj, monkeypatch):
    from aurora import sys_uploads
    client = _api(cfg, monkeypatch)
    raw = _body(9).encode()
    r = client.post("/v1/aurora/projects/lab/data", json={"path": "./dati//u.csv", "data": base64.b64encode(raw).decode()})
    assert r.status_code == 200 and r.json()["path"] == "dati/u.csv", r.text
    assert (proj / "dati" / "u.csv").read_bytes() == raw
    assert D.discover(cfg, "lab", "dati/u.csv", "y", runner=D.direct)["status"] == "discovered"
    mine = sys_uploads.save(cfg, "run1", "misure.csv", "text/csv", _body(10).encode())            # attached by the owner
    made = sys_uploads.save(cfg, "run1", "sim.csv", "text/csv", _body(11).encode(), role="assistant")   # made by Aurora
    assert client.post("/v1/aurora/projects/lab/data", json={"upload": made["id"], "path": "s.csv"}).status_code == 403
    r = client.post("/v1/aurora/projects/lab/data", json={"upload": mine["id"]})
    assert r.status_code == 200 and r.json()["how"] == "chat", r.text
    assert V.origin(cfg, "lab", "misure.csv", r.json()["sha256"])["kind"] == "owner"
    for bad in ({"path": "../x.csv", "data": ""}, {"path": "prereg/LEDGER.csv", "data": ""},
                {"path": ".venv/x.csv", "data": ""}, {"path": "x.py", "data": ""}):
        assert client.post("/v1/aurora/projects/lab/data", json=bad).status_code == 400, bad


# ---- C703: no hash without a budget; sparse files never read ---------------------------------------------------------
def test_c703_sparse_tables_are_skipped_without_reading_them(cfg, proj, monkeypatch):
    for i in range(40):
        with open(proj / f"s{i}.csv", "wb") as fh:
            fh.truncate(64 * 1024 * 1024)
    if os.stat(proj / "s0.csv").st_blocks * 512 * V.SPARSE_RATIO >= 64 * 1024 * 1024:
        pytest.skip("this filesystem allocates the blocks of a truncated file")
    read = []
    monkeypatch.setattr(V, "_canonical", lambda raw, rel: read.append(rel) or "x" * 64)
    t0 = time.monotonic()
    assert V.record(cfg, "lab", proj, [f"s{i}.csv" for i in range(40)], "run") == 40
    assert time.monotonic() - t0 < 2.0 and read == []
    rows = V._rows(cfg, "lab")
    assert {r["sha256"] for r in rows} == {"skipped"} and {r["skipped"] for r in rows} == {"sparse"}
    V.record_owner(cfg, "lab", proj, ["s0.csv"], "upload")             # even the owner's: not hashed, not claimable
    assert V.origin(cfg, "lab", "s0.csv", "0" * 64)["claimable"] is False


def test_c703_the_bytes_hash_has_a_time_budget(cfg, proj, monkeypatch):
    for i in range(30):
        (proj / f"t{i}.csv").write_text(_body(i))
    monkeypatch.setattr(V, "BUDGET_S", 0.0)
    t0 = time.monotonic()
    V.record(cfg, "lab", proj, [f"t{i}.csv" for i in range(30)], "run")
    assert time.monotonic() - t0 < 1.0
    rows = V._rows(cfg, "lab")
    assert len(rows) == 30 and {r["skipped"] for r in rows} == {"budget"}
    r = D.discover(cfg, "lab", "t3.csv", "y", runner=D.direct)
    assert r["status"] == "passed_not_claimable" and r["origin"] == "unknown" and "not hashed" in D.text(r), D.text(r)


def test_c703_a_dense_table_is_still_hashed():
    st = SimpleNamespace(st_size=2 << 20, st_blocks=(2 << 20) // 512)
    assert not V.sparse(st) and V.sparse(SimpleNamespace(st_size=64 << 20, st_blocks=8))
    assert not V.sparse(SimpleNamespace(st_size=4096, st_blocks=0))       # a small file inlined by the filesystem


# ---- C699: every key naming a project; the projects plugin's is «name» ------------------------------------------------
def test_c699_the_real_mcp_validation_and_two_projects_in_one_call(cfg):
    from mcp.server.mcpserver.utilities.func_metadata import func_metadata

    def project_read_file(name: str, path: str, offset: int = 0) -> str:  # the plugin's signature
        return f"READ {name}/{path}"
    for n in ("segreto", "scratch"):
        (cfg.path("AURORA_PROJECTS_DIR") / n).mkdir(parents=True)
    prj_policy.save(cfg, "segreto", {"models": "local", "publish": False})
    args = {"name": "segreto", "path": "claims.md", "project": "scratch"}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ran = asyncio.run(func_metadata(project_read_file).call_fn_with_arg_validation(project_read_file, False,
                                                                                         dict(args), None))
    assert ran == "READ segreto/claims.md"                     # the plugin works on «name», «project» dropped
    a = _Agent(cfg)
    out = prj_policy.guard(a, "projects", "project_read_file", args, lambda *x: None)
    assert out.startswith("REFUSED") and "more than one project" in out
    assert a.projects == {"segreto", "scratch"}               # both in the run's scope all the same
    b = _Agent(cfg)
    assert prj_policy.guard(b, "projects", "project_read_file", {"name": "segreto", "path": "x"}, lambda *x: None) == ""
    assert b.local_only is True
    c = _Agent(cfg)                                           # the same name twice is one project
    assert prj_policy.guard(c, "projects", "project_read_file", {"name": "segreto", "project": "segreto"},
                            lambda *x: None) == "" and c.local_only is True
    assert prj_policy.project_of("circuits", "circuit_simulate", {"project": "segreto", "name": "rc"}) == "segreto"
    d = _Agent(cfg)
    assert prj_policy.builtin_guard(d, "long_run", {"project": "scratch", "name": "segreto"}, lambda *x: None
                                    ).startswith("REFUSED")


# ---- C704: any plugin's project joins the run; «riservato» reaches no network ----------------------------------------
class _Host:
    MANIFESTS = {"vista": {"sandbox": {"network": "local"}}, "web": {"sandbox": {"network": True}},
                 "projects": {"sandbox": {"network": True}}}

    def __init__(self):
        self.calls = []

    def get(self, plugin):
        return SimpleNamespace(manifest=dict(self.MANIFESTS[plugin]))

    def call(self, plugin, tool, args, run_id=None):
        self.calls.append((plugin, tool, dict(args)))
        return {"ok": True, "text": "ok", "seconds": 0}


def test_c704_a_reserved_project_read_through_another_plugin_closes_the_network(cfg, monkeypatch):
    from aurora import agt_asked, prj_novelty, sec_detonate, sys_ethics
    from aurora.agt_loop import Agent
    for n in ("brevetto", "altro"):
        (cfg.path("AURORA_PROJECTS_DIR") / n).mkdir(parents=True)
    prj_policy.save(cfg, "brevetto", {"riservato": True})
    monkeypatch.setattr(sec_detonate, "agent_gate", lambda *a, **k: "")
    monkeypatch.setattr(sys_ethics, "exempt", lambda c=None: False)
    agent = Agent(SimpleNamespace(llm=None, _for=lambda role: None), cfg)
    agent.host, agent.asked, agent.pending, agent.produced = _Host(), True, [], []
    agent.projects, agent.created_projects = set(), set()                # as run() sets them
    agt_asked.start(agent, "guarda le tavole")
    index = {"vista__vista_describe": ("vista", "vista_describe", "read"), "web__search": ("web", "search", "read"),
             "projects__project_read_file": ("projects", "project_read_file", "read")}
    emit = lambda *x: None
    assert agent._call("web__search", {"query": "pendulum"}, index, emit, "r") != ""     # before: allowed
    assert ("web", "search") in [c[:2] for c in agent.host.calls]
    agent._call("vista__vista_describe", {"project": "brevetto", "path": "fig1.png"}, index, emit, "r")
    assert "brevetto" in agent.projects                                                   # C704: not only «projects»
    n = len(agent.host.calls)
    out = agent._call("web__search", {"query": "rotore a spirale"}, index, emit, "r")
    assert out.startswith("REFUSED") and "reserved project brevetto" in out and len(agent.host.calls) == n
    from aurora import sec_linkcheck                                  # nor is the link sent to a reputation service
    asked = []
    monkeypatch.setattr(sec_linkcheck, "check", lambda url, c: asked.append(url) or {"blocked": False})
    index["web__fetch_url"] = ("web", "fetch_url", "read")
    out = agent._call("web__fetch_url", {"url": "https://example.org/?q=rotore-a-spirale"}, index, emit, "r")
    assert out.startswith("REFUSED") and asked == [] and len(agent.host.calls) == n
    assert not agent._call("projects__project_read_file", {"name": "brevetto", "path": "a.md"}, index, emit,
                           "r").startswith("REFUSED")                                     # its own files: still read
    sent = []
    monkeypatch.setattr(prj_novelty, "_client", lambda *a, **k: sent.append(a) or None)
    out = agent._call(prj_novelty.NAME, {"project": "altro", "claim": "the period of a pendulum grows with its length"},
                      index, emit, "r")
    assert "NOT CHECKED" in out or out.startswith("REFUSED"), out
    assert sent == []


def test_c715_tables_in_skips_package_folders(tmp_path):
    """C715: a package's CSV inside .venv (or site-packages, node_modules) is neither the owner's nor an echo."""
    proj = tmp_path / "lab"
    for rel in ("data/a.csv", ".venv/lib/python3.12/site-packages/sklearn/datasets/data/iris.csv",
                "env/lib/site-packages/pkg/x.csv", "web/node_modules/m/y.csv", "venv/z.csv"):
        f = proj / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x,y\n1,2\n")
    assert V.tables_in(proj) == ["data/a.csv"]

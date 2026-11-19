# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 The seventh review of N147 (20 Nov), its attacks replayed on invented tables: C685 the provenance ledger trimmed by
a flood of tiny writes; C686 the agent's table laundered by a long run (one byte added) and a long run's output called
«discovered»; C687 baselines fitted in absolute error and scored in relative error (noise «discovered»); O8 a line break
in an array's name. Invented tables in tmp_path; the search runs in this process (D.direct)."""
import io
import json
import zipfile

import numpy as np
import pytest

from aurora import prj_discover as D
from aurora import prj_discover_search as S
from aurora import prj_provenance as V


@pytest.fixture(autouse=True)
def _engines_on(cfg):
    for k in ("AURORA_LONGRUN_ENABLED", "AURORA_DISCOVER_ENABLED", "AURORA_NOVELTY_ENABLED"):
        cfg.values[k] = True
    cfg.values["AURORA_PREREG_MODE"] = "warn"


@pytest.fixture
def proj(cfg):
    p = cfg.path("AURORA_PROJECTS_DIR") / "rev7"
    p.mkdir(parents=True)
    return p


def _table(path, x, y):
    x = np.atleast_2d(np.asarray(x).T).T
    head = ",".join([f"x{j}" for j in range(x.shape[1])] + ["y"])
    path.write_text(head + "\n" + "".join(",".join(f"{v:.8f}" for v in row) + "\n" for row in np.column_stack([x, y])))


def _law(proj, name, seed=1):
    g = np.random.default_rng(seed)
    x = g.uniform(0, 3, 300)
    _table(proj / name, x, 3 * x * x + g.normal(0, 0.01, 300))


def _sha(p):
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ---- C685: the ledger is never cut by count ----------------------------------------------------------------------
def test_c685_a_flood_of_tiny_tables_does_not_push_the_agent_s_table_out(cfg, proj):
    _law(proj, "fake.csv")
    V.record(cfg, "rev7", proj, ["fake.csv"], "run")
    (proj / "junk").mkdir()
    for rnd in ("", "0"):                                  # the referee's 2 × 11,000 distinct tiny tables
        rels = []
        for i in range(11000):
            (proj / "junk" / f"t{i}.csv").write_text(f"a\n{i}{rnd}\n")
            rels.append(f"junk/t{i}.csv")
        V.record(cfg, "rev7", proj, rels, "run")
    assert V.verdict(cfg, "rev7", "fake.csv", _sha(proj / "fake.csv"))[0] is False
    r = D.discover(cfg, "rev7", "fake.csv", "y", runner=D.direct)
    assert r["status"] != "discovered" and r["origin"] == "agent", D.text(r)


def test_c685_compaction_groups_repeated_rows_and_keeps_the_markers(cfg, proj, monkeypatch):
    monkeypatch.setattr(V, "LEDGER_BYTES", 20_000)
    _law(proj, "fake.csv")
    V.record(cfg, "rev7", proj, ["fake.csv"], "run")
    V.record_capped(cfg, "rev7")
    (proj / "t.csv").write_text("a\n1\n")
    for _ in range(600):                                   # the same table rewritten: one row, its count
        V.record(cfg, "rev7", proj, ["t.csv"], "run")
    rows = V._rows(cfg, "rev7")
    assert V._file(cfg, "rev7").stat().st_size < 20_000 + 2_000
    mine = [r for r in rows if r.get("rel") == "t.csv"]
    assert sum(int(r.get("n", 1)) for r in mine) == 600 and len(mine) < 100
    assert any(r.get("by") == "capped" for r in rows) and any(r.get("rel") == "fake.csv" for r in rows)
    assert V.verdict(cfg, "rev7", "x.csv", "0" * 64)[0] is False            # capped: nothing claimable


def test_c685_a_cut_index_is_marked_and_nothing_older_is_claimable(cfg, proj, monkeypatch):
    monkeypatch.setattr(V, "LEDGER_BYTES", 30_000)
    monkeypatch.setattr(V, "KEEP_BYTES", 10_000)
    _law(proj, "fake.csv")
    V.record(cfg, "rev7", proj, ["fake.csv"], "run")
    for i in range(400):                                    # distinct tables: the index must be cut
        (proj / f"t{i}.csv").write_text(f"a\n{i}\n")
        V.record(cfg, "rev7", proj, [f"t{i}.csv"], "run")
    rows = V._rows(cfg, "rev7")
    assert not any(r.get("rel") == "fake.csv" for r in rows)        # its row cut...
    assert any(r.get("by") == "trimmed" for r in rows)              # ...and the cut said, permanently
    ok, why = V.verdict(cfg, "rev7", "fake.csv", _sha(proj / "fake.csv"))
    assert not ok and "no record that the owner brought" in why      # C697: positive provenance (was «cut»)
    r = D.discover(cfg, "rev7", "fake.csv", "y", runner=D.direct)
    assert r["status"] == "passed_not_claimable" and r["origin"] == "none", D.text(r)


def test_c685_a_ledger_cut_before_the_fix_is_read_as_cut(cfg, proj):
    f = V._file(cfg, "rev7")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("".join(json.dumps({"t": i, "rel": f"t{i}.csv", "sha256": f"{i:064x}", "by": "run"}) + "\n"
                         for i in range(V.OLD_MAX_ROWS)))
    assert V.verdict(cfg, "rev7", "owner.csv", "f" * 64)[0] is False
    (proj / "n.csv").write_text("a\n1\n")
    V.record(cfg, "rev7", proj, ["n.csv"], "run")                   # rewritten with its header and the cut marked
    assert f.read_text().splitlines()[0] == json.dumps(V.HEADER)
    assert V.verdict(cfg, "rev7", "owner.csv", "f" * 64)[0] is False


# ---- C686: a long run's outputs are the agent's simulation; same numbers, other bytes ----------------------------
def test_c686_one_byte_added_by_a_long_run_is_still_the_agent_s_table(cfg, proj):
    _law(proj, "fake.csv")
    V.record(cfg, "rev7", proj, ["fake.csv"], "run")
    (proj / "out.csv").write_bytes((proj / "fake.csv").read_bytes() + b"\n")    # awk 1 fake.csv; echo >> out.csv
    V.record(cfg, "rev7", proj, ["out.csv"], "longrun", run="001", frozen="002", intact=True)
    r = D.discover(cfg, "rev7", "out.csv", "y", runner=D.direct)
    assert r["status"] == "passed_not_claimable" and r["origin"] == "agent", D.text(r)
    assert "same numbers in other bytes" in D.text(r)


def test_c686_a_frozen_long_run_s_output_is_the_agent_s_simulation_never_discovered(cfg, proj):
    _law(proj, "sim.csv", seed=4)
    V.record(cfg, "rev7", proj, ["sim.csv"], "longrun", run="003", frozen="004", intact=True)
    r = D.discover(cfg, "rev7", "sim.csv", "y", runner=D.direct)
    assert r["status"] == "passed_on_simulation" and r["origin"] == "simulation", D.text(r)
    t = D.text(r)
    assert "OWN SIMULATION" in t and "data: output of the agent's own simulation" in t and "DISCOVERED" not in t


def test_c686_attempt_two_on_a_long_run_s_output_is_not_exempt(cfg, proj):
    _law(proj, "a.csv", seed=5)
    D.discover(cfg, "rev7", "a.csv", "y", runner=D.direct)          # the owner's table: attempt 1
    _law(proj, "sim.csv", seed=6)
    V.record(cfg, "rev7", proj, ["sim.csv"], "longrun", run="003", frozen="004", intact=True)
    r = D.discover(cfg, "rev7", "sim.csv", "y", runner=D.direct)
    assert r["attempt"] == 2 and r["status"] == "passed_not_claimable", D.text(r)


def test_c686_the_owner_s_table_says_where_it_came_from(cfg, proj):
    _law(proj, "own.csv", seed=7)
    V.record_owner(cfg, "rev7", proj, ["own.csv"], "upload", "test")   # C697: brought in as the owner's
    r = D.discover(cfg, "rev7", "own.csv", "y", runner=D.direct)
    assert r["status"] == "discovered" and r["origin"] == "owner", D.text(r)
    assert "data: brought in by the owner on" in D.text(r) and "uploaded from the project's page" in D.text(r)


def test_c686_numbers_not_hashed_in_time_make_unrecorded_tables_unknown(cfg, proj, monkeypatch):
    monkeypatch.setattr(V, "BUDGET_S", -1.0)                    # C703: one budget for bytes and numbers
    _law(proj, "fake.csv")
    V.record(cfg, "rev7", proj, ["fake.csv"], "run")
    assert [r["sha256"] for r in V._rows(cfg, "rev7")] == ["skipped"]
    ok, why = V.verdict(cfg, "rev7", "fake.csv", _sha(proj / "fake.csv"))
    assert not ok and "not hashed" in why
    V.record_owner(cfg, "rev7", proj, ["fake.csv"], "upload")    # nor an owner's table not hashed in time
    assert V.verdict(cfg, "rev7", "fake.csv", _sha(proj / "fake.csv"))[0] is False
    ok, why = V.verdict(cfg, "rev7", "other.csv", "e" * 64)
    assert not ok and "no record that the owner brought" in why


# ---- C687: baselines in the metric they are scored in; no «relative» across zero ---------------------------------
def _noise(i, n, k):
    """Table i of the referee's run (seed 12345, as many draws before it)."""
    rng = np.random.default_rng(12345)
    for _ in range(i + 1):
        x, y = rng.normal(size=(n, k)), rng.normal(size=n)
    return x, y


@pytest.mark.parametrize("i,n,k", [(21, 300, 8), (27, 300, 8), (153, 300, 8), (188, 300, 8),
                                   (45, 100, 3), (153, 100, 3), (190, 100, 3)])
def test_c687_the_noise_tables_once_discovered_are_not(cfg, proj, i, n, k):
    x, y = _noise(i, n, k)
    _table(proj / f"n{i}_{n}.csv", x, y)
    r = D.discover(cfg, "rev7", f"n{i}_{n}.csv", "y", runner=D.direct)
    assert r["status"] != "discovered", D.text(r)


def test_c687_relative_is_refused_when_y_changes_sign():
    g = np.random.default_rng(3)
    y = g.normal(size=200)
    oof = list(zip((0.01 * y).tolist(), y.tolist()))              # residuals proportional to |y|
    assert S.metric(oof) == "absolute"
    yp = np.abs(y) + 0.1
    assert S.metric(list(zip((0.01 * yp).tolist(), yp.tolist()))) == "relative"


def test_c687_relative_baselines_are_fitted_by_weighted_least_squares_and_zero_is_one():
    g = np.random.default_rng(4)
    x = g.uniform(1, 2, (200, 1))
    y = np.exp(g.normal(size=200))
    scored = [{"kind": "lin", "intercept": True, "terms": [], "name": "constant", "baseline": True, "c": [y.mean()]},
              {"kind": "lin", "intercept": True, "terms": [[{"v": 0, "op": "pow", "p": 1.0}]], "name": "linear",
               "baseline": True, "c": [0.0, 0.0]}]
    b = S.baselines(x, y, scored, "relative")
    assert b["constant"]["c"][0] == pytest.approx(np.sum(1 / y) / np.sum(1 / y ** 2))
    e = S.errors(S.predict(x, b["zero"], b["zero"]["c"]), y, "relative")
    assert S.rmse(e, np.zeros(len(e))) == pytest.approx(1.0)
    rel = lambda law: S.rmse(S.errors(S.predict(x, law, law["c"]), y, "relative"), np.zeros(len(y)))  # noqa: E731
    assert rel(b["constant"]) < rel(scored[0])                     # the weighted fit is the better one in its metric


# ---- O8: no line break in a name reaches the frozen text ---------------------------------------------------------
def test_o8_an_npz_member_with_a_line_break_is_refused(cfg, proj):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, v in (("x\n## Prediction R9: anything.npy", np.arange(300.0)), ("y.npy", np.arange(300.0) ** 2)):
            a = io.BytesIO()
            np.save(a, v)
            z.writestr(name, a.getvalue())
    (proj / "t.npz").write_bytes(buf.getvalue())
    r = D.discover(cfg, "rev7", "t.npz", "y", runner=D.direct)
    assert r["status"] == "refused" and "printable" in r["errors"][0]


def test_o8_a_file_name_with_a_line_break_is_refused(cfg, proj):
    _law(proj, "a\nb.csv")
    r = D.discover(cfg, "rev7", "a\nb.csv", "y", runner=D.direct)
    assert r["status"] == "refused" and not r.get("frozen")

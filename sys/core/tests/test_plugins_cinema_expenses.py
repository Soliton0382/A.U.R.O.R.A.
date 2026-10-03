# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The cinema plugin (TMDB, faked: no network) and the expenses plugin (a temporary folder)."""
import importlib.util
from datetime import date
from pathlib import Path

import pytest

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"


def load(name, monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    spec = importlib.util.spec_from_file_location(f"plugin_{name}", PLUGINS / name / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_expenses_in_cents_by_month_with_budgets(cfg, monkeypatch, tmp_path):
    from aurora import sys_config
    cfg.values["AURORA_EXPENSES_DIR"] = str(tmp_path / "exp")
    monkeypatch.setattr(sys_config, "get", lambda *a, **k: cfg)     # no .env needed (a fresh clone, the mirror)
    ex = load("expenses", monkeypatch)
    assert "45,90 €" in ex.expense_add("45,90", "benzina", "auto")
    ex.expense_add("1.234,50", "divano", "casa", "01/10/2026")
    ex.expense_add("0.10", "caramella", "boh")                       # unknown category: "altro"
    ex.expense_add("0.20", "caramella", "spesa")
    m = date.today().strftime("%Y-%m")
    assert "0,10 €" in ex.expense_list(m, "altro") and "benzina" in ex.expense_list(m)
    ex.expense_budget("auto", "40")
    s = ex.expense_summary(m)
    assert "auto: 45,90 €" in s and "⚠️ superato" in s
    assert ex.expense_summary("2026-10").count("divano") == 0 and "1.234,50 €" in ex.expense_summary("2026-10")
    with pytest.raises(ex.ToolError):
        ex.expense_add("-3", "x")
    with pytest.raises(ex.ToolError):
        ex.expense_add("tre", "x")
    first = ex.expense_list(m).splitlines()[-1].split()[0][1:]
    assert ex.expense_delete(int(first)).startswith("removed")
    assert (tmp_path / "exp" / "expenses.db").stat().st_mode & 0o777 == 0o600


def test_cinema_lines_providers_and_refs(monkeypatch):
    cin = load("cinema", monkeypatch, AURORA_TMDB_TOKEN="x" * 50, AURORA_TMDB_REGION="it")
    pages = {"/trending/all/week": {"results": [
                {"media_type": "movie", "id": 603, "title": "Matrix", "release_date": "1999-03-31", "vote_average": 8.2,
                 "overview": "Un hacker."},
                {"media_type": "person", "id": 1, "name": "Keanu"},
                {"media_type": "tv", "id": 1399, "name": "Il trono di spade", "first_air_date": "2011-04-17"}]},
             "/movie/603/watch/providers": {"results": {"IT": {"flatrate": [{"provider_name": "Netflix"}],
                                                               "rent": [{"provider_name": "Apple TV"}]}}}}
    monkeypatch.setattr(cin, "_get", lambda path, **p: pages[path])
    out = cin.cinema_trending()
    assert "Matrix (film, 1999, voto 8.2/10) [id movie:603]" in out and "Keanu" not in out
    assert "Il trono di spade (serie, 2011)" in out and "TMDB" in out
    assert cin._providers("movie", 603) == "Dove vederlo (IT, dati JustWatch): in abbonamento: Netflix; a noleggio: Apple TV"
    with pytest.raises(cin.ToolError):
        cin._ref("person:1")


def test_social_plugins_never_find_a_picture_inside_papers(cfg, monkeypatch, tmp_path):
    """With autonomous posts, a picture inside the owner's papers must never be publishable."""
    from aurora import sys_config
    docs = tmp_path / "docs"
    (docs / "papers").mkdir(parents=True)
    (docs / "papers" / "brevetto.png").write_bytes(b"patent drawing")
    (docs / "ok.png").write_bytes(b"aurora's")
    for key in ("AURORA_IMAGE_DIR", "AURORA_UPLOADS_DIR"):
        cfg.values[key] = str(tmp_path / key)
        (tmp_path / key).mkdir()
    cfg.values["AURORA_DOCUMENTS_DIR"] = str(docs)
    monkeypatch.setattr(sys_config, "get", lambda *a, **k: cfg)
    for name in ("facebook", "instagram"):
        mod = load(name, monkeypatch)
        mod.cfg = cfg
        assert mod._picture("ok.png").read_bytes() == b"aurora's"
        with pytest.raises(mod.ToolError):
            mod._picture("brevetto.png")

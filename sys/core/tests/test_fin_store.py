# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""💶 The money page's store (owner, 1 Nov: incomes, fixed ones of every month, a saving goal, the trend) and the
chat's advice on a purchase from the user's real numbers (fin_store, the expenses plugin)."""
import importlib.util
from datetime import date
from pathlib import Path

import pytest

from aurora import fin_store as F


@pytest.fixture
def money(cfg, tmp_path):
    cfg.values["AURORA_EXPENSES_DIR"] = str(tmp_path / "exp")
    return cfg


def test_a_fixed_item_becomes_a_movement_each_month_once_its_day_has_come(money):
    # in 2099: every other read applies the fixed items up to the real today, these only up to the day given
    F.fixed_add(money, "in", "1.850", "Stipendio", "stipendio", 27, "2099-08")
    F.fixed_add(money, "out", "650", "Affitto", "casa", 31, "2099-08")             # 31: a shorter month's last day
    with F.db(money, date(2099, 9, 30)):
        pass
    days = sorted(m["day"] for m in F.moves(money, "2099-09"))
    assert days == ["2099-09-27", "2099-09-30"]
    with F.db(money, date(2099, 10, 26)):                                          # the salary's day not come yet
        pass
    assert [m["what"] for m in F.moves(money, "2099-10")] == []
    for _ in range(2):                                                             # applied twice: one movement
        with F.db(money, date(2099, 10, 27)):
            pass
    assert [m["what"] for m in F.moves(money, "2099-10")] == ["Stipendio"]


def test_a_fixed_movement_deleted_by_hand_is_not_made_again_and_a_stop_keeps_the_past(money):
    f = F.fixed_add(money, "out", "29,90", "Internet", "abbonamenti", 5, "2099-09")
    with F.db(money, date(2099, 10, 6)):
        pass
    oct_ = next(m for m in F.moves(money, "2099-10") if m["fixed"])
    F.remove(money, "out", oct_["id"])
    with F.db(money, date(2099, 10, 7)):
        pass
    assert not F.moves(money, "2099-10")
    F.fixed_stop(money, f["id"], date(2099, 10, 7))
    with F.db(money, date(2099, 12, 6)):
        pass
    assert len(F.moves(money, "2099-09")) == 1 and not F.moves(money, "2099-11") and not F.fixed_list(money)


def test_the_month_s_view_incomes_minus_spending_against_the_goal(money):
    F.add(money, "in", "2000", "Stipendio", "stipendio", "2026-10-27")
    F.add(money, "out", "1.234,50", "Divano", "casa", "2026-10-02")
    F.add(money, "out", "65,50", "Supermercato", "spesa", "2026-10-03")
    F.add(money, "out", "100", "Cena", "ristoranti", "2026-09-10")
    F.set_goal(money, "300")
    F.set_budget(money, "spesa", "50")
    v = F.view(money, "2026-10")
    assert (v["income"], v["spent"], v["saved"], v["goal"], v["spent_before"]) == (200000, 130000, 70000, 30000, 10000)
    assert [c["category"] for c in v["categories"]] == ["casa", "spesa"] and v["categories"][1]["budget"] == 5000
    assert [m["month"] for m in v["trend"]][-2:] == ["2026-09", "2026-10"] and v["trend"][-2]["saved"] == -10000
    s = F.summary_text(money, "2026-10")
    assert "risparmio 700,00 €" in s and "✅" in s and "⚠️ superato" in s
    with pytest.raises(ValueError):
        F.add(money, "sideways", "1", "x")
    with pytest.raises(ValueError):
        F.month("2026-13")


def test_the_chat_advises_with_the_user_s_numbers(money, monkeypatch):
    from aurora import sys_config
    monkeypatch.setattr(sys_config, "get", lambda *a, **k: money)
    spec = importlib.util.spec_from_file_location("plugin_expenses_fin",
                                                  Path(__file__).resolve().parents[2] / "plugins" / "expenses" / "server.py")
    ex = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ex)
    assert "No movements" in ex.money_overview()
    this = date.today().strftime("%Y-%m")
    for i in range(1, 4):                                                      # three past months: 1.800 in, 1.500 out
        m = F._shift(this, -i)
        F.add(money, "in", "1800", "Stipendio", "stipendio", f"{m}-27")
        F.add(money, "out", "1500", "Tutto", "casa", f"{m}-02")
    ex.saving_goal("200")
    out = ex.money_overview("900")
    assert "saved 300,00 € a month" in out and "about 3.0 months" in out and "4.5 months of it" in out
    assert ex.income_add("50", "Rimborso", "rimborsi").startswith("recorded income")
    assert "every month on the 27" in ex.expense_fixed_add("in", "1800", "Stipendio", "stipendio", 27)


def test_the_expenses_plugin_is_private():
    """Its numbers never go to a cloud model: once read, the local model answers (agt_loop)."""
    import json
    m = json.loads((Path(__file__).resolve().parents[2] / "plugins" / "expenses" / "plugin.json").read_text())
    assert m["private"] is True and m["effects"]["money_overview"] == "read"

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Plugin "expenses": the user's money told in the chat, on the same file as the 💶 page (aurora/fin_store.py, this
machine only; what and how sealed with the user's «expenses» key).

"Ho speso 45 € di benzina" becomes a spending; "mi arriva lo stipendio di 1.850 € il 27" a fixed income; the month,
a category, budgets and the saving goal on request. And advice (owner, 1 Nov: «voglio comprare questa cosa che costa
X… e lei in base a quello indicato nelle spese dice come fare»): money_overview gives the model the user's real
numbers — the months' averages, the fixed ones, what is left this month, the goal — and, for a price, how long the
savings take. The plugin is private: once it is read, the answer is made by the local model only. No network.
"""
from __future__ import annotations

from datetime import date

from aurora import fin_store, sys_config
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

cfg = sys_config.get()
server = MCPServer("expenses", version="1.0")


def _do(fn, *a):
    try:
        return fn(*a)
    except ValueError as e:
        raise ToolError(str(e)) from None
    except KeyError as e:
        raise ToolError(f"no item #{e.args[0]}") from None


def _m(c: int) -> str:
    return fin_store.money(cfg, c)


@server.tool()
def expense_add(amount: str, what: str, category: str = "altro", day: str = "oggi", payment: str = "") -> str:
    """Record a spending: amount (e.g. 45.90), what it was, category (one of: casa, spesa, bollette, trasporti, auto,
    salute, svago, ristoranti, viaggi, abbigliamento, tecnologia, abbonamenti, regali, tasse, altro), day, how paid."""
    r = _do(fin_store.add, cfg, "out", amount, what, category, day, payment)
    return f"recorded spending #{r['id']}: {_m(r['cents'])} · {r['what']} · {r['category']} · {r['day']}"


@server.tool()
def income_add(amount: str, what: str, category: str = "altro", day: str = "oggi") -> str:
    """Record an income once (a refund, a sale, a gift): amount, what, category (stipendio, pensione, rimborsi,
    vendite, regali, altro), day. A salary of every month is expense_fixed_add with kind «in»."""
    r = _do(fin_store.add, cfg, "in", amount, what, category, day)
    return f"recorded income #{r['id']}: {_m(r['cents'])} · {r['what']} · {r['category']} · {r['day']}"


@server.tool()
def expense_fixed_add(kind: str, amount: str, what: str, category: str = "altro", day_of_month: int = 1) -> str:
    """A movement of every month on its day, from this month: kind «in» (salary, pension) or «out» (rent, bills, a
    subscription, a loan's instalment). Aurora adds it to each month by herself."""
    r = _do(fin_store.fixed_add, cfg, kind, amount, what, category, day_of_month)
    return f"fixed #{r['id']}: {'+' if kind == 'in' else '−'}{_m(r['cents'])} · {r['what']} · every month on the {r['dom']}"


@server.tool()
def expense_fixed_stop(fixed_id: int) -> str:
    """Stop a fixed item from next month (its #id from money_overview); the months gone stay."""
    _do(fin_store.fixed_stop, cfg, fixed_id)
    return f"fixed #{fixed_id} stopped from next month"


@server.tool()
def expense_list(month: str = "", category: str = "", limit: int = 50) -> str:
    """The movements of a month (default this one; spendings and incomes), optionally of one category, newest first."""
    m = _do(fin_store.month, month)
    rows = fin_store.moves(cfg, m, cat=category, limit=max(1, min(limit, 500)))
    if not rows:
        return f"no movements in {m}" + (f" for {category}" if category else "")
    return "\n".join(f"#{r['id']} {r['day']} · {'+' if r['kind'] == 'in' else '−'}{_m(r['cents'])} · {r['what']} · "
                     f"{r['category']}{' · fixed' if r['fixed'] else ''}" for r in rows)


@server.tool()
def expense_summary(month: str = "") -> str:
    """A month: incomes, spendings by category with the budgets passed, what was saved against the goal and the month
    before."""
    return _do(fin_store.summary_text, cfg, month)


@server.tool()
def expense_budget(category: str, monthly: str) -> str:
    """Set the monthly budget of a spending category (0 removes it); the summary says when it is passed."""
    v = _do(fin_store.set_budget, cfg, category, monthly)
    return f"budget of {fin_store.category('out', category)}: " + (_m(v) + " a month" if v else "removed")


@server.tool()
def saving_goal(monthly: str) -> str:
    """Set how much the user wants to save every month (0 removes the goal)."""
    v = _do(fin_store.set_goal, cfg, monthly)
    return f"saving goal: {_m(v)} a month" if v else "saving goal removed"


@server.tool()
def money_overview(price: str = "") -> str:
    """The user's money in numbers, to advise them: use it when they ask whether they can afford something, how to
    pay for it or save for it, or how they are doing. The last 6 months' averages (income, spending, saved), the fixed
    incomes and spendings of every month with their days, this month so far and how it ends, when the next income
    comes (to say «wait until then» when it is better), the goal and the categories that weigh most; with a
    `price`, how many months of the average savings it takes and what buying it now leaves. Numbers only: the
    advice is yours, said plainly, never a judgement."""
    today = date.today()
    now = today.strftime("%Y-%m")
    v = fin_store.view(cfg, now)
    past = [m for m in fin_store.trend(cfg, fin_store._shift(now, -1), 6) if m["income"] or m["spent"]]
    if not past and not v["income"] and not v["spent"]:
        return "No movements recorded yet: the user can add them on the 💶 page or tell you («ho speso…», the salary)."
    rows = []
    if past:
        avg = {k: round(sum(m[k] for m in past) / len(past)) for k in ("income", "spent", "saved")}
        rows.append(f"Last {len(past)} months, on average: income {_m(avg['income'])}, spending {_m(avg['spent'])}, "
                    f"saved {_m(avg['saved'])} a month (best {_m(max(m['saved'] for m in past))}, "
                    f"worst {_m(min(m['saved'] for m in past))}).")
    fin = sum(f["cents"] for f in v["fixed"] if f["kind"] == "in")
    fout = sum(f["cents"] for f in v["fixed"] if f["kind"] == "out")
    if v["fixed"]:
        rows.append(f"Fixed every month: in {_m(fin)}, out {_m(fout)} — "
                    + "; ".join(f"#{f['id']} {f['what']} {'+' if f['kind'] == 'in' else '−'}{_m(f['cents'])} on the {f['dom']}"
                                for f in v["fixed"]) + ".")
    come_in = sum(f["cents"] for f in v["fixed"] if f["kind"] == "in" and f["dom"] > today.day)
    come_out = sum(f["cents"] for f in v["fixed"] if f["kind"] == "out" and f["dom"] > today.day)
    end = v["saved"] + come_in - come_out
    rows.append(f"This month so far ({today.isoformat()}): income {_m(v['income'])}, spending {_m(v['spent'])}, "
                f"left {_m(v['saved'])}" + (f"; still to come this month from the fixed ones: in {_m(come_in)}, out "
                                            f"{_m(come_out)} — the month ends around {_m(end)} before other spending."
                                            if come_in or come_out else "."))
    for f in (x for x in v["fixed"] if x["kind"] == "in"):     # «wait for the 27th, the salary comes» (owner, 1 Nov)
        nxt = fin_store.next_day(f["dom"], today)
        rows.append(f"Next {f['what']}: +{_m(f['cents'])} on {nxt.isoformat()} (in {(nxt - today).days} days).")
    if v["goal"]:
        rows.append(f"Saving goal: {_m(v['goal'])} a month" + (f", reached in {sum(m['saved'] >= v['goal'] for m in past)} "
                                                              f"of the last {len(past)} months." if past else "."))
    if past:
        cats: dict[str, int] = {}
        for m in past:
            for c in fin_store.view(cfg, m["month"])["categories"]:
                cats[c["category"]] = cats.get(c["category"], 0) + c["cents"]
        top = sorted(cats.items(), key=lambda kv: -kv[1])[:4]
        rows.append("Spending that weighs most (monthly average): "
                    + ", ".join(f"{c} {_m(round(s / len(past)))}" for c, s in top) + ".")
    if price:
        p = _do(fin_store.cents, price)
        saved = round(sum(m["saved"] for m in past) / len(past)) if past else v["saved"]
        rows.append(f"Price {_m(p)}: " + (f"about {p / saved:.1f} months of the average savings"
                                           if saved > 0 else "the average savings are not positive: it cannot be paid from savings")
                    + f"; bought this month, the month would end around {_m(end - p)}"
                    + (f"; against the goal, {p / v['goal']:.1f} months of it" if v["goal"] else "") + ".")
    return "\n".join(rows)


@server.tool()
def expense_delete(expense_id: int, kind: str = "out") -> str:
    """Remove a movement recorded by mistake (its #id from expense_list; kind «in» for an income)."""
    _do(fin_store.remove, cfg, kind, expense_id)
    return f"removed #{expense_id}"


if __name__ == "__main__":
    server.run("stdio")

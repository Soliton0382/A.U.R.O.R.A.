# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📐 The Lean mathematician (kno_prove, kno_prove_chat, N144): a claim in words is formalised by a model, checked by
Aurora's Lean (prj_proof.check_source), and «proved» only when the kernel accepts it AND a second call confirms the
statement is the claim. Fake models and a fake checker; invented claims; one real check of a tiny theorem needs the
toolchain (AURORA_LEAN_HOME) and bwrap, else it skips."""
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from aurora import kno_prove as K
from aurora import kno_prove_chat as C
from aurora import prj_proof as F
from aurora import sys_context
from aurora.mdl_llm import Completion

LEAN = Path(__file__).resolve().parents[3] / "sys" / "runtime" / "lean"
GOOD = "import Mathlib\n\ntheorem claim : (2:ℕ) + 2 = 4 := by norm_num\n"
SORRY = "import Mathlib\n\ntheorem claim : (2:ℕ) + 2 = 4 := by sorry\n"
WRONG = "import Mathlib\n\ntheorem claim : (2:ℕ) + 2 = 4 := by rfl_wrong\n"
OTHER = "import Mathlib\n\ntheorem claim : (1:ℕ) = 1 := rfl\n"


def reply(src: str, verdict: str = "PROOF", reason: str = "") -> str:
    return f"VERDICT: {verdict}\nREASON: {reason}\n```lean\n{src}```\n"


class Model:
    """The prover's replies in turn (the last one repeated); the fidelity verdicts likewise; every prompt kept."""
    name, model = "fake", "m1"

    def __init__(self, replies, faithful=(True,)):
        self.replies, self.faithful, self.prompts, self.judged = list(replies), list(faithful), [], []

    def complete(self, system, user, max_tokens, think=False):
        if system == K.SYS_FIDELITY:
            self.judged.append(user)
            ok = self.faithful.pop(0) if len(self.faithful) > 1 else self.faithful[0]
            return Completion(f'{{"faithful": {str(ok).lower()}, "why": "w", "says": "2 + 2 = 4 in ℕ"}}', "", 20, 0.1,
                              False)
        self.prompts.append(user)
        text = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return Completion(text, "", 100, 0.1, False)


def checker(cfg, src, limit=None):
    """Lean as a fake: GOOD and OTHER proved, anything with sorry refused by the real scan, the rest not proved."""
    if "sorry" in src:
        return F.check_source(cfg, src, limit)            # refused before anything is compiled: no toolchain needed
    if src in (GOOD, OTHER):
        return {"status": "proved", "errors": [], "axioms": {"claim": ["propext"]}, "theorems": ["claim"],
                "seconds": 1.0}
    return {"status": "not_proved", "errors": ["<stdin>:3:40: unknown tactic"], "axioms": {}, "theorems": ["claim"],
            "seconds": 1.0}


def test_a_correct_proof_with_a_faithful_statement_is_proved(cfg):
    m = Model([reply(GOOD)])
    r = K.prove(cfg, "Due più due fa quattro.", llm=m, checker=checker)
    assert r["status"] == "proved" and r["fidelity"]["faithful"] and r["axioms"] == ["propext"]
    assert r["lean_source"] == GOOD and len(r["attempts"]) == 1
    assert r["cost"]["calls"] == 2 and r["cost"]["output_tokens"] == 120       # the prover and the fidelity call
    assert "Due più due" in m.judged[0] and GOOD in m.judged[0]                # the second call: claim + source only


def test_a_proof_with_sorry_is_refused_then_retried(cfg):
    m = Model([reply(SORRY), reply(GOOD)])
    r = K.prove(cfg, "Due più due fa quattro.", llm=m, checker=checker)
    assert [a["status"] for a in r["attempts"]] == ["refused", "proved"] and r["status"] == "proved"
    assert "REFUSED" in m.prompts[1] and "sorry" in m.prompts[1]                # Lean's verdict went back to the model


def test_only_refused_attempts_end_refused(cfg):
    r = K.prove(cfg, "Due più due fa quattro.", llm=Model([reply(SORRY)]), checker=checker)
    assert r["status"] == "refused" and len(r["attempts"]) == 3


def test_a_false_statement_is_not_proved_after_the_attempts(cfg):
    m = Model([reply(WRONG)])
    r = K.prove(cfg, "Ogni numero primo è dispari.", llm=m, checker=checker)
    assert r["status"] == "not_proved" and len(r["attempts"]) == 3 and not m.judged
    assert "unknown tactic" in m.prompts[2]


def test_attempts_follow_the_setting(cfg):
    cfg.values["AURORA_PROVE_ATTEMPTS"] = 2
    r = K.prove(cfg, "x", llm=Model([reply(WRONG)]), checker=checker)
    assert len(r["attempts"]) == 2 and r["status"] == "not_proved"


def test_a_proved_but_different_statement_is_never_proved(cfg):
    m = Model([reply(OTHER)], faithful=(False,))
    r = K.prove(cfg, "Esistono infiniti numeri primi.", llm=m, checker=checker)
    assert r["status"] == "not_proved" and r["kernel_proved"]["lean_source"] == OTHER
    assert len(m.judged) == 3 and "NOT the claim" in m.prompts[1]
    assert "DIFFERENT statement" in K.text(r) and "Do not claim" in K.text(r)


def test_fidelity_rejected_then_a_faithful_statement_is_proved(cfg):
    m = Model([reply(OTHER), reply(GOOD)], faithful=(False, True))
    r = K.prove(cfg, "Due più due fa quattro.", llm=m, checker=checker)
    assert r["status"] == "proved" and r["lean_source"] == GOOD


def test_an_unreadable_fidelity_verdict_is_not_a_confirmation(cfg):
    class Mute(Model):
        def complete(self, system, user, max_tokens, think=False):
            if system == K.SYS_FIDELITY:
                return Completion("sembra giusto", "", 5, 0.1, False)
            return super().complete(system, user, max_tokens, think)
    r = K.prove(cfg, "Due più due fa quattro.", llm=Mute([reply(GOOD)]), checker=checker)
    assert r["status"] == "not_proved" and r["kernel_proved"]


def test_the_model_saying_false_stops_and_is_told_as_an_opinion(cfg):
    m = Model([reply("", "FALSE", "2 è primo e pari")])
    r = K.prove(cfg, "Ogni numero primo è dispari.", llm=m, checker=lambda *a, **k: pytest.fail("checked"))
    assert r["status"] == "not_proved" and r["believed_false"] and len(m.prompts) == 1
    assert "NOT verified" in K.text(r)
    assert "NON verificata" in C.badge(r, "it") and "Verificato in Lean (kernel)" not in C.badge(r, "it")


def test_not_mathematics_is_unformalised(cfg):
    r = K.prove(cfg, "Il gelato al pistacchio è il migliore.", llm=Model(["VERDICT: NOT_MATH\nREASON: un gusto\n"]),
                checker=lambda *a, **k: pytest.fail("checked"))
    assert r["status"] == "unformalised" and r["reason"] == "un gusto"


def test_no_lean_block_at_all_is_unformalised(cfg):
    r = K.prove(cfg, "x", llm=Model(["non so"]), checker=lambda *a, **k: pytest.fail("checked"))
    assert r["status"] == "unformalised" and [a["status"] for a in r["attempts"]] == ["no_lean"] * 3


def test_the_time_limit_stops_new_attempts(cfg, monkeypatch):
    clock = iter(range(0, 10_000, 200))                    # every reading of the clock: 200 s later
    monkeypatch.setattr(K, "_now", lambda: next(clock))
    cfg.values["AURORA_PROVE_TIMEOUT_S"] = 300
    r = K.prove(cfg, "x", llm=Model([reply(WRONG)]), checker=checker)
    assert len(r["attempts"]) <= 1 and "time is up" in r["reason"] and r["status"] != "proved"


def test_lean_missing_is_an_error_not_retried(cfg):
    calls = []

    def missing(cfg, src, limit=None):
        calls.append(src)
        return {"status": "error", "errors": ["Lean non installato"], "axioms": {}, "theorems": [], "seconds": 0.0}
    r = K.prove(cfg, "x", llm=Model([reply(GOOD)]), checker=missing)
    assert r["status"] == "error" and len(calls) == 1 and "Lean non installato" in r["reason"]


def test_off_and_unknown_model(cfg):
    cfg.values["AURORA_PROVE_ENABLED"] = False
    assert K.prove(cfg, "x", llm=Model([reply(GOOD)]), checker=checker)["status"] == "error"
    cfg.values["AURORA_PROVE_ENABLED"] = True
    cfg.values["AURORA_PROVE_MODEL"] = "nessuno:x"
    r = K.prove(cfg, "x", local=object(), checker=checker)
    assert r["status"] == "error" and "unknown provider" in r["reason"]


def test_the_model_is_the_routers_agent_or_the_setting(cfg, monkeypatch):
    from aurora import mdl_router
    seen = []
    monkeypatch.setattr(mdl_router, "model_for", lambda role, local, c: seen.append(
        (role, (mdl_router.RUN_ROLES.get() or {}).get(role))) or "M")
    assert K.model(cfg, local="L") == "M" and seen[-1] == ("agent", None)
    cfg.values["AURORA_PROVE_MODEL"] = "claude_code:opus"
    assert K.model(cfg, local="L") == "M" and seen[-1] == ("agent", {"provider": "claude_code", "model": "opus"})
    assert mdl_router.RUN_ROLES.get() is None                                    # reset after
    assert K.model(cfg, local="L", private=True) == "L"                          # a «local» run: the local model


def test_check_source_leaves_no_scratch_behind(cfg):
    r = F.check_source(cfg, SORRY)
    assert r["status"] == "refused" and r["path"] == F.SCRATCH_FILE
    assert list((cfg.path("AURORA_STATUS_DIR") / "prove").iterdir()) == []


# ---- the chat -----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("q,claim,explicit", [
    ("/lean 2 + 2 = 4", "2 + 2 = 4", True),
    ("Dimostra in Lean: la somma di due pari è pari", "la somma di due pari è pari", True),
    ("prove in Lean: every even square is divisible by 4", "every even square is divisible by 4", True),
    ("È vero che 91 è primo?", "91 è primo", False),
    ("Dimostrami che √2 è irrazionale", "√2 è irrazionale", False),
    ("Is it true that n^2 + n is even for every n?", "n^2 + n is even for every n", False),
    ("è vero che 7 è dispari?", "7 è dispari", False),
])
def test_detection_of_a_claim(q, claim, explicit):
    assert C.claim_of(q) == (claim, explicit)


@pytest.mark.parametrize("q", ["È vero che domani piove?", "Cos'è un numero primo?", "Dimostra che mi vuoi bene",
                               "/lean", "è vero che siamo pari?", "Spiegami il teorema di Pitagora",
                               "È vero che " + "1 + 1 = 2 e " * 40])
def test_no_claim_is_detected_where_there_is_none(q):
    assert C.claim_of(q) is None


def test_badges():
    proved = {"status": "proved", "claim": "2 + 2 = 4", "attempts": [{}], "seconds": 3.0, "axioms": ["propext"],
              "says": "2 + 2 = 4 in ℕ", "lean_source": GOOD, "reason": ""}
    b = C.badge(proved, "it")
    assert b.startswith("📐 **Verificato in Lean (kernel), enunciato confermato.**")
    assert "```lean fold\n" + GOOD.rstrip("\n") + "\n```" in b
    assert C.badge(proved, "en").startswith("📐 **Verified in Lean (kernel), statement confirmed.**")
    for st in ("not_proved", "refused", "unformalised", "error"):
        b = C.badge({**proved, "status": st, "reason": "r"}, "it")
        assert b.startswith("📐 **Non verificato in Lean**") and "Verificato in Lean (kernel)" not in b
    other = C.badge({**proved, "status": "not_proved", "kernel_proved": {"says": "1 = 1", "why": "banale"}}, "it")
    assert "enunciato DIVERSO: 1 = 1" in other


class Pipe:
    llm = "local"

    def __init__(self):
        self.kept = []

    def remember(self, question, ans, run_id, emit, trail, asked):
        self.kept.append(ans)


def test_the_chat_answers_with_the_badge_and_remembers(cfg, monkeypatch):
    seen = []
    monkeypatch.setattr(K, "prove", lambda c, claim, local=None, emit=None: seen.append((claim, local)) or {
        "status": "proved", "claim": claim, "attempts": [{}], "seconds": 2.0, "axioms": [], "says": "s",
        "lean_source": GOOD, "reason": "", "cost": {}, "believed_false": False, "fidelity": {"faithful": True}})
    events, p = [], Pipe()
    ans = C.answer(p, cfg, "/lean la somma di due numeri pari è pari", lambda e, d: events.append((e, d)), "run1")
    assert seen == [("la somma di due numeri pari è pari", "local")] and ans.mode == "prove" and p.kept == [ans]
    final = next(d for e, d in events if e == "answer.final")
    assert final["prove"]["status"] == "proved" and final["text"].startswith("📐 **Verificato")
    assert C.answer(p, cfg, "/lean 2 + 2 = 4", lambda e, d: None, "run2", remember=False) and len(p.kept) == 1


def test_an_implicit_claim_that_is_not_mathematics_goes_back_to_the_ordinary_answer(cfg, monkeypatch):
    monkeypatch.setattr(K, "prove", lambda *a, **k: {"status": "unformalised", "claim": "", "attempts": [{}],
                                                     "seconds": 1.0, "reason": "no"})
    assert C.answer(Pipe(), cfg, "È vero che 3 + 3 = 6?", lambda e, d: None, "r") is None


def test_never_in_the_anonymous_chat_nor_with_an_attachment_nor_off(cfg, monkeypatch):
    monkeypatch.setattr(K, "prove", lambda *a, **k: pytest.fail("proved"))
    with sys_context.anonymous():
        assert C.answer(Pipe(), cfg, "/lean 2 + 2 = 4", lambda e, d: None, "r") is None
        assert K.offered(cfg, "dimostra il teorema") == []
        assert K.agent_call(SimpleNamespace(cfg=cfg), {"statement": "2 + 2 = 4"}).startswith("ERROR")
    assert C.answer(Pipe(), cfg, "/lean 2 + 2 = 4", lambda e, d: None, "r", attached=[("a", b"")]) is None
    cfg.values["AURORA_PROVE_ENABLED"] = False
    assert C.answer(Pipe(), cfg, "/lean 2 + 2 = 4", lambda e, d: None, "r") is None


def test_the_chat_route_asks_the_mathematician_before_anything_else():
    src = (Path(__file__).resolve().parents[1] / "aurora" / "api" / "core_route.py").read_text(encoding="utf-8")
    body = src[src.index("def answer_or_acquire"):]
    assert body.index("kno_prove_chat.answer(") < body.index("wants_tools(")


# ---- the agents' tool ---------------------------------------------------------------------------------------------
def test_the_tool_is_offered_when_the_goal_speaks_of_proofs(cfg):
    assert K.offered(cfg, "Dimostra che la somma di due pari è pari") == [K.TOOL]
    assert K.offered(cfg, "Controlla le mail") == []
    from aurora import prj_act
    assert K.NAME in {t["name"] for t in prj_act.TOOLS}                           # the conductor's too


def test_the_agent_call(cfg, monkeypatch):
    seen = []
    monkeypatch.setattr(K, "prove", lambda c, s, local=None, private=False: seen.append((s, local, private)) or {
        "status": "not_proved", "claim": s, "attempts": [], "seconds": 0.0, "reason": "r", "lean_source": ""})
    agent = SimpleNamespace(cfg=cfg, p=SimpleNamespace(llm="L"), local_only=True)
    out = K.agent_call(agent, {"statement": "91 è primo"})
    assert out.startswith("NOT PROVED") and seen == [("91 è primo", "L", True)]
    assert K.agent_call(agent, {}).startswith("ERROR")


# ---- the AGI benchmark's section --------------------------------------------------------------------------------
def test_the_suite_is_fixed_true_and_false():
    s = K.suite()
    assert len(s) == 20 and len({c["id"] for c in s}) == 20
    assert sum(c["true"] for c in s) == 12 and sum(not c["true"] for c in s) == 8


def test_the_benchmark_scores_only_verified_proofs_and_rejections():
    t, f = {"true": True}, {"true": False}
    rows = [{"case": t, "prove": {"status": "proved"}},          # right
            {"case": t, "prove": {"status": "not_proved"}},      # wrong: not proved
            {"case": t, "prove": {"status": "unformalised"}},    # wrong
            {"case": f, "prove": {"status": "not_proved"}},      # right
            {"case": f, "prove": {"status": "refused"}},         # right: not claimed
            {"case": f, "prove": {"status": "proved"}},          # wrong, and counted apart
            {"case": t, "prove": {"status": "error"}},           # void
            {"case": f}]                                         # void: no verdict
    s = K.score(rows)
    assert s == {"right": 3, "total": 6, "void": 2, "true_proved": 1, "false_rejected": 2, "false_proved": 1}


# ---- the real Lean -----------------------------------------------------------------------------------------------
def _real() -> bool:
    return ((LEAN / "workspace" / "lean-toolchain").is_file() and bool(shutil.which("bwrap"))
            and not subprocess.run(["bwrap", "--ro-bind", "/", "/", "true"], capture_output=True).returncode)


@pytest.mark.skipif(not _real(), reason="Lean (AURORA_LEAN_HOME) or bwrap missing")
def test_a_tiny_true_theorem_is_proved_by_the_real_lean_from_a_string(cfg):
    cfg.values["AURORA_LEAN_HOME"] = str(LEAN)
    r = F.check_source(cfg, GOOD)
    assert r["status"] == "proved", r
    assert r["theorems"] == ["claim"] and set(r["axioms"]["claim"]) <= set(F.STANDARD)
    assert list((cfg.path("AURORA_STATUS_DIR") / "prove").iterdir()) == []

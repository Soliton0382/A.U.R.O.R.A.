# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""📐 The Lean mathematician (ROADMAP N144; owner: «cosa potremmo integrare in aurora come agenti per aiutarla a
rispondere nella chat o nei test agi con lean che abbiamo aggiunto»; decided: a Lean mathematician for the chat and
the AGI tests, the statement's fidelity checked, a conservative detection, a badge).

prove(cfg, claim) → {status: proved | not_proved | refused | unformalised | error, lean_source, axioms, attempts,
seconds, cost, fidelity, says, reason, kernel_proved}:
  1. a model (AURORA_PROVE_MODEL, else the agent's assignment on the Models page: mdl_router.model_for — masked, the
     daily ceiling, the local fallback, rule 9, as every cloud call) turns the natural-language claim into a Lean 4 +
     Mathlib theorem named `claim` and its proof — or says the claim is FALSE or NOT_MATH;
  2. Aurora checks the source with prj_proof.check_source (the N143 cage, a private scratch folder deleted after);
  3. kernel accepted: a SECOND, independent call (fresh context: the claim and the Lean source only) says whether the
     Lean statement says exactly the claim — a proved but different statement is worth nothing;
  4. on failure Lean's errors (or the fidelity objection) go back to the model, up to AURORA_PROVE_ATTEMPTS within
     AURORA_PROVE_TIMEOUT_S.
«proved» only when the kernel accepts AND the fidelity is confirmed. A kernel-accepted statement judged different is
kept in `kernel_proved` (what was proved instead), the status stays not_proved. The model saying FALSE stops the work:
not_proved, its reason told as the model's opinion, not verified.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from . import prj_proof, sys_config, sys_context

NAME = "prove"
CLAIM_CHARS = 2000
PROVE_TOKENS = 6000
FIDELITY_TOKENS = 600
MIN_LEFT = 10.0                 # seconds: below this no new attempt is started
SUITE = Path(__file__).resolve().parents[1] / "tests" / "data" / "prove_suite.json"
_now = time.monotonic           # the clock (a test moves it)

SYS_PROVE = (
    "You are a mathematician who writes Lean 4 with Mathlib. You get a mathematical CLAIM in natural language. Write "
    "a Lean 4 file that states the claim as a theorem named `claim` and proves it.\n"
    "Rules: the file starts with `import Mathlib`; the statement of `claim` says EXACTLY the claim (the same objects, "
    "quantifiers, hypotheses and conclusion — not a special case, not a weaker or stronger one); use Mathlib's own "
    "notions (Nat.Prime, Even, Odd, Irrational, Real.sqrt, Finset.sum, ∣ ...) and never define your own version of "
    "a standard notion; helper lemmas are allowed; never use sorry, admit, native_decide, decide +native, axiom, "
    "unsafe, macro, elab, syntax, run_cmd, #eval, set_option on debug or kernel options.\n"
    "Reply in exactly this form:\n"
    "VERDICT: PROOF | FALSE | NOT_MATH\n"
    "REASON: one line (for FALSE: a counterexample or why; for NOT_MATH: why it cannot be stated in Lean)\n"
    "```lean\n<the whole file>\n```\n"
    "VERDICT: FALSE only when you are sure the claim is false (then the Lean block may be omitted). NOT_MATH when it "
    "is not a precise mathematical statement.")
SYS_FIDELITY = (
    "You check a formalisation, nothing else. You get a mathematical CLAIM in natural language and a LEAN 4 source "
    "whose theorem `claim` is meant to state it. The proof does not matter: judge only the STATEMENT of `claim`, read "
    "with the definitions in the source and Mathlib's meanings. Is it exactly the claim — the same objects, domains "
    "(ℕ, ℤ, ℝ ...), quantifiers, hypotheses and conclusion — and not a special case, a weaker or stronger statement, "
    "a vacuous one (false hypotheses) or one made true by a redefined notion? Natural readings of the claim are fine "
    "(«numbers» as ℕ or ℤ when the claim holds or fails the same way). Reply with JSON only: {\"faithful\": "
    "true|false, \"why\": \"one sentence\", \"says\": \"what the Lean statement says, in the claim's language\"}.")
NO_LEAN = "Your reply had no ```lean block with a theorem named `claim`. Reply in the form asked."

VERDICT = re.compile(r"^\W*VERDICT\W*\s*(PROOF|FALSE|NOT_MATH)\b", re.M | re.I)
REASON = re.compile(r"^\W*REASON\W*\s*(.+)$", re.M | re.I)
BLOCK = re.compile(r"```[ \t]*(?:lean4?)?[ \t]*\n(.*?)```", re.S | re.I)
WANTS = re.compile(r"\b(?:prov(?:e|es|ed|ing)|proofs?|theorems?|lemm[aie]s?|lean|dimostr\w*|teorem[ai]|congettur[ae]|"
                   r"conjectures?|proof_check|freeze_predictions)\b", re.I)

TOOL = {"name": NAME, "description": "Ask Aurora's Lean mathematician whether a mathematical claim (natural language) "
        "is proved: a model writes it in Lean 4 + Mathlib with a proof, Aurora's Lean kernel checks it and a second "
        "model call confirms the Lean statement says exactly the claim. PROVED only when both hold; otherwise it says "
        "what was or was not proved. Claim a statement proved only when this says PROVED.",
        "input_schema": {"type": "object", "properties": {"statement": {
            "type": "string", "description": "the mathematical claim, in words or formulas"}}, "required": ["statement"]}}
TOOL_MCP = {"name": NAME, "description": TOOL["description"], "inputSchema": TOOL["input_schema"]}


def enabled(cfg: sys_config.Config) -> bool:
    return bool(cfg["AURORA_PROVE_ENABLED"])


def model(cfg: sys_config.Config, local=None, private: bool = False):
    """The mathematician's model: AURORA_PROVE_MODEL («provider:model»), else the agent's assignment — both through
    mdl_router.model_for (masked, ceiling, fallback, rule 9). `private`: the local model only."""
    from . import mdl_router
    local = local if local is not None else mdl_router.base(cfg)
    if private:
        return local
    spec = str(cfg["AURORA_PROVE_MODEL"] or "").strip()
    if not spec:
        return mdl_router.model_for("agent", local, cfg)
    provider, _, name = spec.partition(":")
    if provider not in mdl_router.PROVIDERS:
        raise ValueError(f"AURORA_PROVE_MODEL: unknown provider {provider!r}")
    token = mdl_router.RUN_ROLES.set({**(mdl_router.RUN_ROLES.get() or {}), "agent": {"provider": provider,
                                                                                         "model": name}})
    try:
        return mdl_router.model_for("agent", local, cfg)
    finally:
        mdl_router.RUN_ROLES.reset(token)


# ---- the two calls -----------------------------------------------------------------------------------------------
def _ask(m, out: dict, system: str, user: str, max_tokens: int, think: bool) -> str:
    c = m.complete(system, user, max_tokens, think)
    k = out["cost"]
    k["calls"] += 1
    k["output_tokens"] += int(getattr(c, "tokens", 0) or 0)
    k["chars_sent"] += len(system) + len(user)
    k["chars_received"] += len(c.answer or "")
    return c.answer or ""


def parse(reply: str) -> tuple[str, str, str]:
    """(verdict PROOF | FALSE | NOT_MATH, reason, the Lean source) of the prover's reply; no verdict line = PROOF."""
    v = VERDICT.search(reply or "")
    r = REASON.search(reply or "")
    blocks = [b for b in BLOCK.findall(reply or "") if re.search(r"\b(?:theorem|lemma)\b", b)]
    return ((v.group(1).upper() if v else "PROOF"), (r.group(1).strip()[:400] if r else ""),
            (blocks[-1].strip() + "\n" if blocks else ""))


def fidelity(judge, out: dict, claim: str, source: str) -> dict:
    """{faithful, why, says}: the statement read against the claim by a call that sees nothing else."""
    try:
        txt = _ask(judge, out, SYS_FIDELITY, f"CLAIM: {claim}\n\nLEAN SOURCE:\n```lean\n{source}```",
                   FIDELITY_TOKENS, False)
    except Exception as e:                                # noqa: BLE001 — unconfirmed, never «proved»
        return {"faithful": False, "why": f"fidelity check failed: {str(e)[:200]}", "says": ""}
    m = re.search(r"\{.*\}", txt, re.S)
    try:
        v = json.loads(m.group(0)) if m else {}
    except ValueError:
        v = {}
    if not isinstance(v, dict) or "faithful" not in v:
        return {"faithful": False, "why": "fidelity verdict unreadable: " + txt[:200], "says": ""}
    return {"faithful": v.get("faithful") is True, "why": str(v.get("why", ""))[:400], "says": str(v.get("says", ""))[:600]}


def _main(r: dict) -> str:
    return next((n for n in r.get("theorems") or [] if n == "claim" or n.endswith(".claim")), "")


def _feedback(src: str, r: dict) -> str:
    return (f"YOUR PREVIOUS FILE:\n```lean\n{src}```\nAURORA'S LEAN SAID:\n{prj_proof.text({'path': prj_proof.SCRATCH_FILE, 'seconds': 0.0, **r})}\n"
            "Fix it (the statement must stay the claim) and reply in the same form.")


# ---- the work ----------------------------------------------------------------------------------------------------
def prove(cfg: sys_config.Config, statement: str, local=None, llm=None, judge=None, checker=None, emit=None,
          private: bool = False) -> dict:
    """See the module's docstring. `llm` / `judge` / `checker`: the prover, the fidelity model, the Lean check (the
    tests' fakes); by default model(cfg, local), the same model in a fresh call, prj_proof.check_source."""
    emit = emit or (lambda event, payload: None)
    t0 = _now()
    claim = " ".join(str(statement or "").split())[:CLAIM_CHARS]
    out = {"status": "error", "claim": claim, "lean_source": "", "axioms": [], "attempts": [], "seconds": 0.0,
           "cost": {"calls": 0, "output_tokens": 0, "chars_sent": 0, "chars_received": 0, "model": ""},
           "fidelity": None, "says": "", "reason": "", "kernel_proved": None, "believed_false": False}

    def done(**k) -> dict:
        out.update(k)
        out["seconds"] = round(_now() - t0, 1)
        emit("prove.end", {"status": out["status"], "attempts": len(out["attempts"]), "seconds": out["seconds"]})
        return out
    if not enabled(cfg):
        return done(reason="the Lean mathematician is off (AURORA_PROVE_ENABLED)")
    if not claim:
        return done(status="unformalised", reason="no claim")
    try:
        m = llm or model(cfg, local, private)
    except (RuntimeError, ValueError) as e:
        return done(reason=str(e))
    judge = judge or m
    out["cost"]["model"] = f"{getattr(m, 'name', '?')} {getattr(m, 'model', '')}".strip()
    checker = checker or prj_proof.check_source
    budget, tries = float(cfg["AURORA_PROVE_TIMEOUT_S"]), int(cfg["AURORA_PROVE_ATTEMPTS"])
    feedback, last = "", ""                               # last: the status of the last attempt Lean judged
    for n in range(1, tries + 1):
        if budget - (_now() - t0) < MIN_LEFT:
            out["reason"] = f"time is up ({int(budget)} s, AURORA_PROVE_TIMEOUT_S)"
            break
        emit("prove.attempt", {"n": n})
        try:
            reply = _ask(m, out, SYS_PROVE, f"CLAIM: {claim}" + (f"\n\n{feedback}" if feedback else ""),
                         PROVE_TOKENS, True)
        except Exception as e:                            # noqa: BLE001 — the model failed: said, not retried
            out["attempts"].append({"n": n, "status": "error", "errors": [str(e)[:300]], "seconds": 0.0})
            return done(reason=f"the model failed: {str(e)[:200]}") if not last else done(status="not_proved")
        verdict, reason, src = parse(reply)
        if verdict == "NOT_MATH":
            out["attempts"].append({"n": n, "status": "unformalised", "errors": [], "seconds": 0.0})
            return done(status="unformalised", reason=reason or "not a precise mathematical statement")
        if verdict == "FALSE":
            out["attempts"].append({"n": n, "status": "believed_false", "errors": [], "seconds": 0.0})
            return done(status="not_proved", believed_false=True, reason=reason, lean_source=src or out["lean_source"])
        if not src:
            out["attempts"].append({"n": n, "status": "no_lean", "errors": [NO_LEAN], "seconds": 0.0})
            feedback = NO_LEAN
            continue
        left = budget - (_now() - t0)
        if left < MIN_LEFT:
            out["reason"] = f"time is up ({int(budget)} s, AURORA_PROVE_TIMEOUT_S)"
            break
        r = checker(cfg, src, limit=min(left, float(cfg["AURORA_PROOF_TIMEOUT_S"])))
        if r["status"] == "proved" and not _main(r):
            r = {**r, "status": "not_proved", "errors": ["no theorem named `claim`: name the claim's theorem `claim`"]}
        a = {"n": n, "status": r["status"], "errors": [str(e)[:300] for e in (r.get("errors") or [])[:5]],
             "seconds": r.get("seconds", 0.0)}
        out["attempts"].append(a)
        out["lean_source"] = src
        emit("prove.check", {"n": n, "status": r["status"], "seconds": a["seconds"]})
        if r["status"] == "error":
            if any("stopped after" in e for e in a["errors"]):      # Lean's own time limit: an attempt that failed
                last, feedback = "not_proved", _feedback(src, {**r, "status": "not_proved"})
                continue
            return done(reason=(a["errors"] or ["Lean failed"])[0])         # Lean missing, no cage: no use retrying
        last = r["status"]
        if r["status"] != "proved":
            feedback = _feedback(src, r)
            continue
        f = fidelity(judge, out, claim, src)
        a["fidelity"] = f
        axioms = r["axioms"].get(_main(r), [])
        emit("prove.fidelity", {"n": n, "faithful": f["faithful"]})
        if f["faithful"]:
            return done(status="proved", axioms=axioms, fidelity=f, says=f["says"], reason="")
        out.update(fidelity=f, kernel_proved={"lean_source": src, "says": f["says"], "why": f["why"], "axioms": axioms})
        feedback = (f"YOUR PREVIOUS FILE:\n```lean\n{src}```\nLean's kernel accepted it, but its statement is NOT the "
                    f"claim: {f['why']}\nState exactly the claim and prove it, in the same form.")
    if out["kernel_proved"]:
        return done(status="not_proved", reason=out["reason"] or "Lean proved a different statement")
    if not last:
        return done(status="unformalised", reason=out["reason"] or "no Lean statement of the claim")
    return done(status="refused" if last == "refused" else "not_proved")


# ---- for a model: the agent's and the conductor's tool -----------------------------------------------------------
def text(r: dict) -> str:
    head = {"proved": "PROVED (Lean's kernel accepted it and the statement is confirmed to be the claim)",
            "not_proved": "NOT PROVED", "refused": "NOT PROVED (the proofs used forbidden constructs)",
            "unformalised": "NOT FORMALISED", "error": "ERROR"}[r["status"]]
    out = [f"{head}: {r['claim']} ({len(r['attempts'])} attempts, {r['seconds']} s)"]
    if r.get("says"):
        out.append(f"Lean statement says: {r['says']}")
    if r.get("axioms"):
        out.append("axioms: " + ", ".join(r["axioms"]))
    if r.get("believed_false"):
        out.append(f"The model believes the claim false (NOT verified): {r.get('reason')}")
    elif r.get("reason"):
        out.append(f"why: {r['reason']}")
    if r.get("kernel_proved"):
        k = r["kernel_proved"]
        out.append(f"Lean proved a DIFFERENT statement: {k['says']} ({k['why']})")
    if r["attempts"] and r["status"] != "proved" and r["attempts"][-1].get("errors"):
        out.append("last errors:\n" + "\n".join(r["attempts"][-1]["errors"][:3]))
    if r.get("lean_source"):
        out.append(f"```lean\n{r['lean_source']}```")
    if r["status"] != "proved":
        out.append("Do not claim this statement proved.")
    return "\n".join(out)


def offered(cfg: sys_config.Config, goal: str) -> list[dict]:
    """The tool, when the goal (or its context) speaks of proofs or theorems; never in the anonymous chat."""
    if not enabled(cfg) or sys_context.anonymous_now() or not WANTS.search(goal or ""):
        return []
    return [TOOL]


def agent_call(agent, a: dict) -> str:
    if sys_context.anonymous_now():
        return f"ERROR: {NAME} is not available in the anonymous chat"
    s = str(a.get("statement") or "").strip()
    if not s:
        return f"ERROR: {NAME} needs «statement» (the mathematical claim)"
    p = getattr(agent, "p", None)
    return text(prove(agent.cfg, s, local=getattr(p, "llm", None), private=bool(getattr(agent, "local_only", False))))


# ---- the AGI benchmark's section (script/bench_agi.py --only lean) ------------------------------------------------
def suite() -> list[dict]:
    """The fixed suite: [{id, claim, true}], invented elementary statements, true and false."""
    return json.loads(SUITE.read_text(encoding="utf-8"))["cases"]


def right(case: dict, r: dict | None) -> bool | None:
    """A true claim: right only when proved (kernel + fidelity). A false one: right when not claimed proved and Lean
    was tried or the model judged it false (not_proved, refused). None: void (an error, no verdict)."""
    st = (r or {}).get("status")
    if st == "error" or st is None:
        return None
    return st == "proved" if case["true"] else st in ("not_proved", "refused")


def score(rows: list[dict]) -> dict:
    """rows: [{case, prove}] → {right, total, void, true_proved, false_rejected, false_proved}."""
    marks = [(row["case"], right(row["case"], row.get("prove"))) for row in rows]
    scored = [(c, m) for c, m in marks if m is not None]
    return {"right": sum(bool(m) for _, m in scored), "total": len(scored), "void": len(marks) - len(scored),
            "true_proved": sum(bool(m) for c, m in scored if c["true"]),
            "false_rejected": sum(bool(m) for c, m in scored if not c["true"]),
            "false_proved": sum(1 for row in rows if not row["case"]["true"]
                                and (row.get("prove") or {}).get("status") == "proved")}

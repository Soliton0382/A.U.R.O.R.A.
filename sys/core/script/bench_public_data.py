# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The public test sets the labs report their models on (owner, 2026-10-12: «ci sono dei test a cui gpt e anthropic
si appoggiano per dire la mia AI raggiunge x punteggio… avere i test free di quelle batterie»): how each is fetched,
asked and scored. Read by bench_public.py.

Fetched from Hugging Face's public rows API (no library, no account) or from GitHub, kept in
<STATUS>/bench/public/cache/. A fixed sample (seed 7) so that two runs ask the same questions. Scored as the sets
define it: the letter or the number exactly; MATH's answers compared as text, and when they differ judged equivalent
or not by the judge; SimpleQA graded correct / incorrect / not attempted with its own grader's criteria; ARC the whole
grid exactly; IFEval's instructions by its checks (bench_ifeval); HumanEval's code by its tests in the cage
(bench_humaneval); BFCL's function calls by its AST checker (bench_bfcl). GPQA Diamond and Humanity's Last Exam are gated: they need a Hugging Face token (HF_TOKEN in the
environment) after accepting their terms on the site; without it they are skipped and said so.
"""
from __future__ import annotations

import json
import os
import random
import re
import time
from pathlib import Path

import httpx

import bench_bfcl
import bench_humaneval
import bench_ifeval

ROWS = "https://datasets-server.huggingface.co/rows"
LETTERS = "ABCDEFGHIJKLMNOP"               # MMLU-Pro up to 10 options, TruthfulQA up to 13
MC_TAIL = ("\n\nRispondi alla domanda. Alla fine scrivi su una riga a sé «Risposta: X», dove X è la lettera "
           "dell'opzione giusta.")
NUM_TAIL = "\n\nRisolvi il problema. Alla fine scrivi su una riga a sé «Risposta: N» con il solo risultato finale."
MATH_TAIL = "\n\nRisolvi il problema. Alla fine scrivi su una riga a sé «Risposta: …» con il solo risultato finale."


def _hf(dataset: str, config: str, split: str, total: int | None = None) -> list[dict]:
    """Every row of a public (or, with HF_TOKEN, gated) dataset, 100 at a time."""
    head = {"Authorization": f"Bearer {os.environ['HF_TOKEN']}"} if os.environ.get("HF_TOKEN") else {}
    out, offset = [], 0
    while True:
        for attempt in range(8):                         # the rows API limits the rate: wait, and longer each time
            r = httpx.get(ROWS, params={"dataset": dataset, "config": config, "split": split, "offset": offset,
                                        "length": 100}, headers=head, timeout=60)
            if r.status_code != 429:
                break
            time.sleep(10 * (attempt + 1))
        time.sleep(0.5)
        r.raise_for_status()
        d = r.json()
        out += [x["row"] for x in d["rows"]]
        offset += len(d["rows"])
        if not d["rows"] or offset >= (total or d.get("num_rows_total", 0)):
            return out


def _cached(cache: Path, name: str, fetch) -> list[dict]:
    f = cache / f"{name}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    rows = fetch()
    cache.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return rows


def _mc(question: str, options: list[str]) -> str:
    return question.strip() + "\n\n" + "\n".join(f"{LETTERS[i]}) {o}" for i, o in enumerate(options)) + MC_TAIL


def _shuffled(right: str, wrong: list[str], rng: random.Random) -> tuple[list[str], str]:
    opts = [right] + list(wrong)
    rng.shuffle(opts)
    return opts, LETTERS[opts.index(right)]


# ---- the sets: each returns [{"id", "prompt", "answer", "kind"}] -----------------------------------------------

def mmlu_pro(cache: Path) -> list[dict]:
    rows = _cached(cache, "mmlu_pro", lambda: _hf("TIGER-Lab/MMLU-Pro", "default", "test"))
    return [{"id": str(r["question_id"]), "prompt": _mc(r["question"], r["options"]), "answer": r["answer"],
             "kind": "letter", "topic": r.get("category", "")} for r in rows]


def gpqa_diamond(cache: Path) -> list[dict]:
    rows = _cached(cache, "gpqa_diamond", lambda: _hf("Idavidrein/gpqa", "gpqa_diamond", "train"))
    out = []
    for i, r in enumerate(rows):
        opts, right = _shuffled(r["Correct Answer"].strip(), [r[f"Incorrect Answer {k}"].strip() for k in (1, 2, 3)],
                                random.Random(i))
        out.append({"id": str(i), "prompt": _mc(r["Question"], opts), "answer": right, "kind": "letter"})
    return out


def hle(cache: Path) -> list[dict]:
    """Humanity's Last Exam (cais/hle, gated): the questions of text alone (about 14% need a picture: left out, said
    in the report as the set's own size). Multiple choice read by the letter; an exact answer judged equivalent or not
    by the judge against the gold one, as the set's own evaluation does."""
    rows = _cached(cache, "hle", lambda: [{k: r.get(k) for k in ("id", "question", "answer", "answer_type", "category")}
                                          for r in _hf("cais/hle", "default", "test") if not r.get("image")])
    out = []
    for r in rows:
        if r["answer_type"] == "multipleChoice":
            out.append({"id": r["id"], "prompt": r["question"].strip() + MC_TAIL, "answer": r["answer"].strip().strip("()."),
                        "kind": "letter", "topic": r.get("category", "")})
        else:
            out.append({"id": r["id"], "prompt": r["question"].strip() + MATH_TAIL, "answer": r["answer"].strip(),
                        "kind": "exact", "topic": r.get("category", "")})
    return out


def aime(cache: Path) -> list[dict]:
    a24 = _cached(cache, "aime_2024", lambda: _hf("Maxwell-Jia/AIME_2024", "default", "train"))
    a25 = _cached(cache, "aime_2025", lambda: _hf("MathArena/aime_2025", "default", "train"))
    return ([{"id": f"2024-{r['ID']}", "prompt": r["Problem"] + NUM_TAIL, "answer": str(int(r["Answer"])), "kind": "int"}
             for r in a24] +
            [{"id": f"2025-{r['problem_idx']}", "prompt": r["problem"] + NUM_TAIL, "answer": str(int(r["answer"])),
              "kind": "int"} for r in a25])


def math500(cache: Path) -> list[dict]:
    rows = _cached(cache, "math500", lambda: _hf("HuggingFaceH4/MATH-500", "default", "test"))
    return [{"id": r["unique_id"], "prompt": r["problem"] + MATH_TAIL, "answer": r["answer"], "kind": "math",
             "topic": r.get("subject", "")} for r in rows]


def simpleqa(cache: Path) -> list[dict]:
    rows = _cached(cache, "simpleqa", lambda: _hf("basicv8vc/SimpleQA", "default", "test"))
    return [{"id": str(i), "prompt": r["problem"], "answer": r["answer"], "kind": "simpleqa"} for i, r in enumerate(rows)]


def truthfulqa(cache: Path) -> list[dict]:
    rows = _cached(cache, "truthfulqa_mc", lambda: _hf("truthfulqa/truthful_qa", "multiple_choice", "validation"))
    out = []
    for i, r in enumerate(rows):
        t = r["mc1_targets"]
        right = t["choices"][t["labels"].index(1)]
        opts, letter = _shuffled(right, [c for c, lab in zip(t["choices"], t["labels"]) if not lab], random.Random(i))
        out.append({"id": str(i), "prompt": _mc(r["question"], opts), "answer": letter, "kind": "letter"})
    return out


def _grid(g: list[list[int]]) -> str:
    return "\n".join(" ".join(str(c) for c in row) for row in g)


def arc_agi(cache: Path, version: int = 1) -> list[dict]:
    """ARC-AGI's evaluation tasks (fchollet/ARC-AGI, arcprize/ARC-AGI-2): the examples and the test input as text."""
    repo = "fchollet/ARC-AGI" if version == 1 else "arcprize/ARC-AGI-2"

    def fetch():
        branch = httpx.get(f"https://api.github.com/repos/{repo}", timeout=60).raise_for_status().json()["default_branch"]
        names = [x["name"] for x in httpx.get(f"https://api.github.com/repos/{repo}/contents/data/evaluation",
                                               timeout=60).raise_for_status().json()]
        return [{"name": n, **httpx.get(f"https://raw.githubusercontent.com/{repo}/{branch}/data/evaluation/{n}",
                                        timeout=60).raise_for_status().json()} for n in sorted(names)]
    out = []
    for task in _cached(cache, f"arc_agi_{version}", fetch):
        ex = "\n\n".join(f"Esempio {i}\nINPUT:\n{_grid(p['input'])}\nOUTPUT:\n{_grid(p['output'])}"
                         for i, p in enumerate(task["train"], 1))
        test = task["test"][0]
        out.append({"id": task["name"], "kind": "grid", "answer": _grid(test["output"]),
                    "prompt": ("Puzzle di ragionamento astratto: ogni griglia è fatta di cifre 0-9 (colori). Trova la regola "
                               f"che trasforma ogni INPUT nel suo OUTPUT e applicala al test.\n\n{ex}\n\nTEST\nINPUT:\n"
                               f"{_grid(test['input'])}\n\nAlla fine scrivi «Risposta:» e sotto la griglia di uscita, "
                               "una riga per riga, cifre separate da spazi, nient'altro.")})
    return out


def ifeval(cache: Path) -> list[dict]:
    return bench_ifeval.items(_cached(cache, "ifeval", lambda: _hf("google/IFEval", "default", "train")))


def humaneval(cache: Path) -> list[dict]:
    return bench_humaneval.items(_cached(cache, "humaneval", lambda: _hf("openai/openai_humaneval", "openai_humaneval", "test")))


def bfcl(category: str):
    return lambda cache: bench_bfcl.items(_cached(cache, f"bfcl_{category}", lambda: bench_bfcl.rows(category)), category)


SETS = {"mmlu_pro": mmlu_pro, "gpqa_diamond": gpqa_diamond, "hle": hle, "aime": aime, "math500": math500, "simpleqa": simpleqa,
        "truthfulqa": truthfulqa, "arc_agi_1": lambda c: arc_agi(c, 1), "arc_agi_2": lambda c: arc_agi(c, 2),
        "ifeval": ifeval, "humaneval": humaneval,
        **{f"bfcl_{c}": bfcl(c) for c in bench_bfcl.CATEGORIES}}
GATED = {"gpqa_diamond", "hle"}


# ---- scoring ------------------------------------------------------------------------------------------------

def final(text: str) -> str:
    """What follows the last «Risposta:» / «Answer:» (the whole text when there is none)."""
    m = list(re.finditer(r"(?:risposta|answer)\s*(?:finale|final)?\s*[:：]\s*", text, re.I))
    return text[m[-1].end():].strip() if m else text.strip()


def letter(text: str) -> str:
    tail = final(text)
    m = re.match(r"\**\(?([A-P])\b", tail) or re.search(r"\b([A-P])\)", tail)
    return m.group(1) if m else ""


def integer(text: str) -> str:
    m = re.search(r"-?\d[\d.,]*", final(text).replace("\\boxed{", ""))
    return str(int(re.sub(r"[.,](?=\d{3}\b)", "", m.group(0)).split(".")[0].split(",")[0])) if m else ""


def boxed(text: str) -> str:
    """The \\boxed{…} content if any, else the final answer's first line."""
    i = text.rfind("\\boxed{")
    if i >= 0:
        depth, j = 1, i + 7
        while j < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[j], 0)
            j += 1
        return text[i + 7: j - 1].strip()
    return final(text).splitlines()[0].strip().strip("$. ") if final(text) else ""


def norm_math(s: str) -> str:
    s = re.sub(r"\\(left|right|!|,|;|displaystyle)", "", s)
    s = s.replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac").replace(" ", "").replace("$", "")
    return re.sub(r"\\text\{(.*?)\}", r"\1", s).rstrip(".")


def grid(text: str) -> str:
    rows = [r.strip() for r in final(text).splitlines() if re.fullmatch(r"[0-9](\s+[0-9])*", r.strip())]
    return "\n".join(" ".join(r.split()) for r in rows)


SIMPLEQA_GRADER = ("You grade one answer of the SimpleQA benchmark, with its own criteria. GOLD is the right answer. "
                   "CORRECT: the answer contains the gold answer's meaning fully and contradicts nothing (hedging is "
                   "fine if the gold answer is given). INCORRECT: it states something that contradicts the gold answer "
                   "or a wrong answer, even hedged. NOT_ATTEMPTED: it does not give the answer and contradicts nothing "
                   "(«I don't know», «the sources do not say»). Reply with one word: CORRECT, INCORRECT or NOT_ATTEMPTED.")
MATH_JUDGE = ("Are these two final answers of a math problem mathematically equivalent (the same value or set, in "
              "any form)? Reply with one word: YES or NO.")

EXACT_JUDGE = ("A question's GOLD answer and a candidate's FINAL answer. Do they say the same thing — the same value, "
               "name, expression or statement, in any wording or equivalent form, within a small rounding for numbers? "
               "Reply with one word: YES or NO.")


def score(item: dict, answer: str, judge=None) -> dict:
    """{"right": bool, "got": what was read, "grade"?: SimpleQA's}."""
    k = item["kind"]
    if k == "ifeval":
        return bench_ifeval.score(item, answer, judge)
    if k == "code":
        return bench_humaneval.score(item, answer, judge)
    if k == "bfcl":
        return bench_bfcl.score(item, answer, judge)
    if k == "letter":
        got = letter(answer)
        return {"right": got == item["answer"], "got": got}
    if k == "int":
        got = integer(answer)
        return {"right": got == item["answer"], "got": got}
    if k == "grid":
        got = grid(answer)
        return {"right": got == item["answer"], "got": got[:200]}
    if k == "math":
        got = boxed(answer)
        if norm_math(got) == norm_math(item["answer"]):
            return {"right": True, "got": got}
        if judge is None or not got:
            return {"right": False, "got": got}
        v = str(getattr(judge.complete(MATH_JUDGE, f"A: {item['answer']}\nB: {got}", 10), "answer", "")).upper()
        return {"right": v.startswith("YES"), "got": got, "judged": True}
    if k == "exact":                                       # HLE's exact answers: the judge, as the set's own evaluation
        got = final(answer)
        if not got or judge is None:
            return {"right": False, "got": got[:200]}
        v = str(getattr(judge.complete(EXACT_JUDGE, f"GOLD: {item['answer']}\nFINAL: {got[:1500]}", 10), "answer", "")).upper()
        return {"right": v.startswith("YES"), "got": got[:200], "judged": True}
    if k == "simpleqa":
        v = str(getattr(judge.complete(SIMPLEQA_GRADER, f"QUESTION: {item['prompt']}\nGOLD: {item['answer']}\n\n"
                                                         f"ANSWER:\n{answer or '(empty)'}", 10), "answer", "")).upper()
        grade = next((g for g in ("NOT_ATTEMPTED", "INCORRECT", "CORRECT") if g in v), "INCORRECT")
        return {"right": grade == "CORRECT", "got": grade, "grade": grade}
    raise ValueError(k)


def sample(items: list[dict], n: int, seed: int = 7) -> list[dict]:
    """The same n items every run (all when n is 0 or more than there are)."""
    if not n or n >= len(items):
        return items
    pick = sorted(random.Random(seed).sample(range(len(items)), n))
    return [items[i] for i in pick]

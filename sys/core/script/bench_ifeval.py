# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""IFEval (google/IFEval, 541 prompts): does the answer follow instructions a program can check — «no commas», «at
least 300 words», «end with this phrase», «answer in JSON»… (owner, 2026-10-19: «costruisci IFEval e HumanEval»).
Read by bench_public_data.

The 25 checks are written again here from the set's paper and its reference code (google-research
instruction_following_eval), without its libraries: words are \\w+ runs (its RegexpTokenizer), sentences its own
regular-expression splitter, the capital words' count \\w+ runs where it has nltk's tokenizer. One check needs a
library this machine has not got: the language of the answer (langdetect) — asked of the judge, an ISO 639-1 code,
also for the two «English only» checks. Scored as the set reports it: strict (the answer as given) and loose (also
with its first or last line left out, or its asterisks: the Markdown a model adds); a prompt is right when every one
of its instructions is followed, strict.
"""
from __future__ import annotations

import collections
import json
import re

LANGUAGE_JUDGE = ("Which language is this text written in, mostly? Reply with its ISO 639-1 code only (two letters, "
                  "e.g. en, it, hi).")


def words(text: str) -> int:
    return len(re.findall(r"\w+", text))


def sentences(text: str) -> list[str]:
    """The reference code's sentence splitter (instructions_util.split_into_sentences)."""
    al, digits = "([A-Za-z])", "([0-9])"
    prefixes, suffixes = "(Mr|St|Mrs|Ms|Dr)[.]", "(Inc|Ltd|Jr|Sr|Co)"
    starters = (r"(Mr|Mrs|Ms|Dr|Prof|Capt|Cpt|Lt|He\s|She\s|It\s|They\s|Their\s|Our\s|We\s|But\s|However\s|That\s"
                r"|This\s|Wherever)")
    acronyms, websites = "([A-Z][.][A-Z][.](?:[A-Z][.])?)", "[.](com|net|org|io|gov|edu|me)"
    t = (" " + text + "  ").replace("\n", " ")
    t = re.sub(prefixes, "\\1<prd>", t)
    t = re.sub(websites, "<prd>\\1", t)
    t = re.sub(digits + "[.]" + digits, "\\1<prd>\\2", t)
    t = re.sub(r"\.{2,}", lambda m: "<prd>" * len(m.group(0)) + "<stop>", t)
    t = t.replace("Ph.D.", "Ph<prd>D<prd>")
    t = re.sub(r"\s" + al + "[.] ", " \\1<prd> ", t)
    t = re.sub(acronyms + " " + starters, "\\1<stop> \\2", t)
    t = re.sub(al + "[.]" + al + "[.]" + al + "[.]", "\\1<prd>\\2<prd>\\3<prd>", t)
    t = re.sub(al + "[.]" + al + "[.]", "\\1<prd>\\2<prd>", t)
    t = re.sub(" " + suffixes + "[.] " + starters, " \\1<stop> \\2", t)
    t = re.sub(" " + suffixes + "[.]", " \\1<prd>", t)
    t = re.sub(" " + al + "[.]", " \\1<prd>", t)
    t = t.replace(".”", "”.").replace('."', '".').replace('!"', '"!').replace('?"', '"?')
    t = t.replace(".", ".<stop>").replace("?", "?<stop>").replace("!", "!<stop>").replace("<prd>", ".")
    out = [s.strip() for s in t.split("<stop>")]
    return out[:-1] if out and not out[-1] else out


def _compare(n: int, relation: str, limit: int) -> bool:
    return n < limit if relation == "less than" else n >= limit


_SEEN: dict[str, str] = {}                 # the loose variants of one answer ask the same text again


def _language(text: str, judge) -> str:
    if judge is None or not text.strip():
        return ""
    t = text[:3000]
    if t not in _SEEN:
        v = str(getattr(judge.complete(LANGUAGE_JUDGE, t, 10), "answer", "")).strip().lower()
        m = re.search(r"\b[a-z]{2}\b", v)
        _SEEN[t] = m.group(0) if m else ""
    return _SEEN[t]


def _paragraph_first_word(t: str, kw: dict) -> bool:
    parts = re.split(r"\n\n", t)
    count = sum(1 for p in parts if p.strip())
    nth = kw["nth_paragraph"]
    if nth > count or not parts[nth - 1].strip():
        return False
    first = ""
    for ch in parts[nth - 1].strip().split()[0].strip().lstrip("'").lstrip('"'):
        if ch in ".,?!'\"":
            break
        first += ch.lower()
    return count == kw["num_paragraphs"] and first == kw["first_word"].lower()


def _paragraphs(t: str, n: int) -> bool:
    parts = re.split(r"\s?\*\*\*\s?", t)
    count = len(parts)
    for i, p in enumerate(parts):
        if not p.strip():
            if i in (0, len(parts) - 1):
                count -= 1
            else:
                return False
    return count == n


def _json(t: str) -> bool:
    t = t.strip().removeprefix("```json").removeprefix("```Json").removeprefix("```JSON").removeprefix("```")
    try:
        json.loads(t.removesuffix("```").strip())
        return True
    except ValueError:
        return False


def _highlights(t: str) -> int:
    single = [h for h in re.findall(r"\*[^\n\*]*\*", t) if h.strip("*").strip()]
    double = [h for h in re.findall(r"\*\*[^\n\*]*\*\*", t) if h.removeprefix("**").removesuffix("**").strip()]
    return len(single) + len(double)


def _postscript(t: str, marker: str) -> bool:
    low = t.lower()
    pattern = (r"\s*p\.\s?p\.\s?s.*$" if marker == "P.P.S" else r"\s*p\.\s?s\..*$" if marker == "P.S." else
               r"\s*" + re.escape(marker.lower()) + r".*$")
    return bool(re.findall(pattern, low, flags=re.MULTILINE))


def follows(iid: str, kw: dict, t: str, prompt: str = "", judge=None) -> bool:
    """One instruction of the set (its id and arguments) against one answer."""
    kind = iid.split(":", 1)[1]
    if kind == "capital_word_frequency":
        return _compare(sum(w.isupper() for w in re.findall(r"\w+", t)), kw["capital_relation"], kw["capital_frequency"])
    if kind == "english_capital":
        return t.isupper() and _language(t, judge) == "en"
    if kind == "english_lowercase":
        return t.islower() and _language(t, judge) == "en"
    if kind == "repeat_prompt":
        return t.strip().lower().startswith(kw["prompt_to_repeat"].strip().lower())
    if kind == "two_responses":
        parts = [p.strip() for p in t.split("******") if p.strip()]
        return len(parts) == 2 and parts[0] != parts[1]
    if kind == "number_placeholders":
        return len(re.findall(r"\[.*?\]", t)) >= kw["num_placeholders"]
    if kind == "postscript":
        return _postscript(t, kw["postscript_marker"])
    if kind == "constrained_response":
        return any(o in t.strip() for o in ("My answer is yes.", "My answer is no.", "My answer is maybe."))
    if kind == "json_format":
        return _json(t)
    if kind == "multiple_sections":
        return len(re.split(r"\s?" + re.escape(kw["section_spliter"]) + r"\s?\d+\s?", t)) - 1 >= kw["num_sections"]
    if kind == "number_bullet_lists":
        n = len(re.findall(r"^\s*\*[^\*].*$", t, re.M)) + len(re.findall(r"^\s*-.*$", t, re.M))
        return n == kw["num_bullets"]
    if kind == "number_highlighted_sections":
        return _highlights(t) >= kw["num_highlights"]
    if kind == "title":
        return any(x.lstrip("<").rstrip(">").strip() for x in re.findall(r"<<[^\n]+>>", t))
    if kind == "existence":
        return all(re.search(k, t, re.I) for k in kw["keywords"])
    if kind == "forbidden_words":
        return not any(re.search(r"\b" + w + r"\b", t, re.I) for w in kw["forbidden_words"])
    if kind == "frequency":
        return _compare(len(re.findall(kw["keyword"], t, re.I)), kw["relation"], kw["frequency"])
    if kind == "letter_frequency":
        return _compare(collections.Counter(t.lower())[kw["letter"].lower()], kw["let_relation"], kw["let_frequency"])
    if kind == "response_language":
        return _language(t, judge) == kw["language"]
    if kind == "nth_paragraph_first_word":
        return _paragraph_first_word(t, kw)
    if kind == "number_paragraphs":
        return _paragraphs(t, kw["num_paragraphs"])
    if kind == "number_sentences":
        return _compare(len(sentences(t)), kw["relation"], kw["num_sentences"])
    if kind == "number_words":
        return _compare(words(t), kw["relation"], kw["num_words"])
    if kind == "no_comma":
        return "," not in t
    if kind == "end_checker":
        return t.strip().strip('"').lower().endswith(kw["end_phrase"].strip().lower())
    if kind == "quotation":
        t = t.strip()
        return len(t) > 1 and t[0] == '"' and t[-1] == '"'
    raise ValueError(iid)


def _loose(t: str) -> list[str]:
    lines = t.split("\n")
    cut = ["\n".join(lines[1:]).strip(), "\n".join(lines[:-1]).strip(), "\n".join(lines[1:-1]).strip()]
    return [v for x in (t, *cut) for v in (x, x.replace("*", ""))]


def score(item: dict, answer: str, judge=None) -> dict:
    """{"right": every instruction followed (strict), "got": "followed/total", "loose": the same, loose}."""
    strict, loose, missed = 0, 0, []
    for iid, kw in zip(item["instructions"], item["kwargs"]):
        ok = bool(answer.strip()) and follows(iid, kw, answer, item["prompt"], judge)
        strict += ok
        loose += ok or any(v.strip() and follows(iid, kw, v, item["prompt"], judge) for v in _loose(answer)[1:])
        if not ok:
            missed.append(iid)
    n = len(item["instructions"])
    return {"right": strict == n, "got": f"{strict}/{n}", "loose": f"{loose}/{n}", "loose_right": loose == n,
            "followed": strict, "instructions": n, "missed": missed}


def items(rows: list[dict]) -> list[dict]:
    """The rows as bench_public asks them: the prompt as it is (English, the set's own)."""
    return [{"id": str(r["key"]), "prompt": r["prompt"], "kind": "ifeval", "answer": ", ".join(r["instruction_id_list"]),
             "instructions": r["instruction_id_list"],
             "kwargs": [{k: v for k, v in kw.items() if v is not None} for kw in r["kwargs"]]} for r in rows]

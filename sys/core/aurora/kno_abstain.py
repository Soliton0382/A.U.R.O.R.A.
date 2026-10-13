# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Why there is no answer, said (M188: honesty 8/12 against the bare model's 12/12).

When neither the vault nor the web nor her memory answered, Aurora said the same sentence every time — «La studio
stanotte: domani ne saprò di più» — also to «chi vincerà il Nobel 2031?» (nobody can know: studying will not help) and
to a book or a theorem that does not exist (the honest answer is that there is no trace of it, not a promise).
The model reads the question once and says which of three it is:
    future    about something that has not happened yet: nobody can know it today
    no_trace  about one precise named thing (a book, a theorem, a person, a law) of which no source has any trace:
              it may not exist, or its name is different — its content is never told
    open      anything else: the sentence as before, and the night studies it
Only the kind comes from the model; the words are fixed here, so nothing is invented in them. `future` and
`no_trace` are not studied at night (kno_study.pending)."""
from __future__ import annotations

import re
from datetime import date

KINDS = ("future", "no_trace", "open")
NOT_STUDIED = ("future", "no_trace")

SYS_WHY = ("Today is {today}. Neither a library, nor the web, nor memory answered the QUESTION below. You do not "
           "answer it: you say why it cannot be answered, with one word.\n"
           "FUTURE — it asks about an event, a result or a value that comes after today (a prize, an election, a "
           "match, a price in a later year): nobody can know it yet.\n"
           "NO_TRACE — it asks about the content of one precise named thing (a book, a film, a theorem, a law, a "
           "person, a paper) that well-known sources would mention if it existed.\n"
           "OPEN — anything else (a hard or rare fact, an opinion, a vague question), and forecasts, projections, "
           "plans or schedules already published about a later year.\n"
           "Reply with one word: FUTURE, NO_TRACE or OPEN.")

TEXT = {
    ("future", "it"): "Riguarda qualcosa che non è ancora successo (oggi è il {today}): nessuno può saperlo, "
                      "e non provo a indovinarlo.",
    ("future", "en"): "It is about something that has not happened yet (today is {today}): nobody can know it, "
                      "and I will not guess.",
    ("no_trace", "it"): "Non trovo nessuna traccia di quello che chiedi, né nel vault né sul web: probabilmente non "
                        "esiste, oppure il nome o il titolo sono diversi. Non ne racconto il contenuto, perché lo "
                        "inventerei. Se si scrive in un altro modo, dimmelo e ricontrollo.",
    ("no_trace", "en"): "I find no trace of what you ask, neither in my vault nor on the web: it probably does not "
                        "exist, or its name or title is different. I will not tell its content, because I would make "
                        "it up. If it is spelt another way, tell me and I will look again.",
    ("open", "it"): "Non ho trovato una risposta né nel vault né sul web, e non voglio inventarla. La studio stanotte: "
                    "domani ne saprò di più.",
    ("open", "en"): "I found no answer in my vault nor on the web, and I will not make one up. I will study it tonight.",
}


def later_year(question: str, today: date | None = None) -> bool:
    """The question names a year after this one: worth asking before any search whether it is about the future
    (M188: «il Nobel 2031» took 207 s of searches before the same answer)."""
    now = (today or date.today()).year
    return any(now < int(y) < now + 1000 for y in re.findall(r"\b(2\d{3})\b", question))


def kind(llm, question: str, today: date | None = None) -> str:
    """future | no_trace | open; open when the model fails or says something else (the sentence as before)."""
    try:
        said = llm.complete(SYS_WHY.format(today=(today or date.today()).isoformat()),
                            f"QUESTION: {question}", 6).answer
    except Exception:                                 # noqa: BLE001 — in doubt, the old sentence
        return "open"
    m = re.search(r"\b(FUTURE|NO_TRACE|OPEN)\b", said.upper().replace("NO TRACE", "NO_TRACE"))
    return m.group(1).lower() if m else "open"


def text(why: str, lang: str, today: date | None = None) -> str:
    d = today or date.today()
    day = d.strftime("%d/%m/%Y") if lang == "it" else d.isoformat()
    return TEXT[(why if why in KINDS else "open", "it" if lang == "it" else "en")].format(today=day)

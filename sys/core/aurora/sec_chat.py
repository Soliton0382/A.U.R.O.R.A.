# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Level A of the code of conduct in what Aurora SAYS (ethics/CODE.md): no operational instructions for weapons that can
kill, malicious software, entering what is not yours, tracking people, denial of service.

Two layers, around every run a person starts (api/core.start_run, ORIGINS):
  A. the request: a clear intent («scrivimi un ransomware», «how to build a bomb») is refused before any model is called;
  B. the answer: when the request touches one of these topics, the streamed pieces are held back and the final answer is
     asked to the local model in one token (mdl_llm.decide): «operational instructions for harm?». Yes, or no clear
     reading: the answer is replaced by a refusal. Explaining, history, defence and detection stay allowed.
The level A of the code is the same for every installation, the owner's included: there is no exemption here."""
from __future__ import annotations

import logging
import re
import threading
from types import SimpleNamespace

from aurora import sys_log
from aurora.sys_lang import say

def log() -> logging.Logger:
    try:
        return sys_log.get_logger("sec_chat")
    except Exception:                                  # noqa: BLE001 — no installation (the tests without .env)
        return logging.getLogger("aurora.sec_chat")

# the runs whose question a person wrote: the chat, the OpenAI-compatible clients, the anonymous chat, the voice, the agent
ORIGINS = frozenset({"webui", "openai", "anon", "call", "agent", "acquire"})
HELD = frozenset({"synthesis.delta", "talk.delta"})      # the pieces of a draft, shown while written: held on a topic
MAX_JUDGED = 6000                                          # characters of the answer the judge reads
BLOCK_AT = 0.5                                             # P(yes) from which the answer is replaced

_W = r"(?:[\w'’-]+\W+)"                                    # one word and what follows it
_FEW = _W + "{0,4}"                                         # up to four words between the verb and its object

# what can kill or maim: the words of the request's object (no pastry: «bombe alla crema», «bath bomb», «bomba d'acqua»)
_BLAST = (r"(?<!bath )(?<!seed )(?<!photo )(?:bomb[ae]|bombs?|ordign[oi]|esplosiv[oi]|explosives?|molotov|tritolo|tnt|tatp|nitroglicerina|"
          r"nitroglycerin|napalm|pipe\s?bomb|ied|detonator[ei]?|detonators?|innesco|sarin|vx|ricin[ae]?|antrace|"
          r"anthrax|gas\s+nervino|nerve\s+(?:agent|gas)|arm[ai]\s+(?:chimic|biologic)[ah]e?|chemical\s+weapons?|"
          r"biological\s+weapons?|bio-?weapons?|tossina\s+botulinica|botulinum|iprite|mustard\s+gas|ghost\s+gun|"
          r"pistola\s+(?:fantasma|artigianale|stampata)|3d[\s-]printed\s+gun|silenziatore|silencer|suppressor)"
          r"(?!\s+(?:alla|al|ripien|di\s+crema|calorica|d['’]acqua|di\s+semi|da\s+bagno))")
_MAKE = (r"(?:costrui\w*|fabbric\w*|prepar\w*|assembl\w*|sintetizz\w*|produrre|produci\w*|realizz\w*|"
         r"fa(?:re|i|mmi)|creare|crea(?:mi)?|innescare|build(?:ing)?|make|making|craft|assemble|synthesi[sz]e|"
         r"produce|weaponi[sz]e|cook|construct|fabricate|hacer|fabricar|construir|fabriquer|construire|bauen|herstellen)")
_WRITE = (r"(?:scriv\w*|crea\w*|genera\w*|programm\w*|svilupp\w*|codific\w*|fa(?:re|i|mmi)|dammi|give\s+me|write|"
          r"create|code|coding|generate|develop|build|make|program|escrib\w*|crear|écri\w*|créer|schreib\w*|erstell\w*)")
_MALWARE = (r"(?:virus|ransomware|malware|keylogger|key\s?logger|trojan|troiano|cavallo\s+di\s+troia|rootkit|worm|botnet|"
            r"spyware|stalkerware|info-?stealer|stealer|backdoor|rat\b|remote\s+access\s+trojan|cryptolocker|wiper|"
            r"phishing|pagina\s+di\s+login\s+falsa|fake\s+login\s+page|exploit\s+(?:funzionante|working)|zero-?day)")
_MALWARE_ADJ = (r"(?:(?:un|una|uno|un['’]|a|an|the|il|lo|la|del|dello|della|dei|degli|delle|mio|mia|nuovo|nuova|"
                r"semplice|piccolo|piccola|funzionante|vero|vera|real|working|simple|new|small|custom|polimorfic[oa]|"
                r"polymorphic|python|in|c\+\+|c|powershell|bash|javascript|js|rust|go|per|for|windows|android|linux|"
                r"email|e-mail|mail|sito|sito\s+di|di|da|che|that|which)\s+){0,4}")
_BREAK = (r"(?:hacker\w*|buca\w*|bucare|viol\w*|cracc\w*|crack\w*|hack\w*|forz\w*|bypass\w*|aggira\w*|"
          r"break\s+into|brute-?forc\w*|pirat\w*|hackear|pirater)")
_TARGET = (r"(?:account|profil[oi]|instagram|facebook|whatsapp|telegram|snapchat|tiktok|gmail|e-?mail|posta|wi-?fi|"
           r"password|router|telefono|cellulare|smartphone|iphone|phone|pc|computer|sito|website|server|database|"
           r"rete|network|webcam|telecamer[ae]|camera)")
_PEOPLE = (r"(?:ex|moglie|marito|fidanzat[oa]|ragazz[oa]|vicin[oa]|collega|capo|partner|amic[oa]|figli[oa]|"
           r"wife|husband|girlfriend|boyfriend|neighbou?r|coworker|colleague|boss|friend)")
_OTHERS = (r"(?:(?:di|del|della|dello|dell['’]|of)\s*(?!(?:mio|mia|miei|mie|my|me|questo|this)\b)\w+|"
           r"(?:di|del|della|of)\s+(?:mi[oa]|my)\s+" + _PEOPLE + r"|my\s+" + _PEOPLE + r"['’]s|"
           r"altrui|someone(?:\s+else)?['’]s|somebody['’]s|other\s+people['’]s|"
           r"senza\s+(?:permesso|autorizzazione|password|che\s+(?:lo|la)\s+sappia)|without\s+(?:permission|authori[sz]ation|"
           r"(?:the\s+)?password|them\s+knowing)|di\s+nascosto|secretly)")
# what is the person's own (a forgotten password, their own router): not a request for intrusion, the answer still read
_MINE = re.compile(r"\b(?:mio|mia|miei|mie|my|own|dimenticat\w*|forgot(?:ten)?|ho\s+perso|lost)\b", re.I)
_OTHERS_STRICT = re.compile(r"(?:altrui|someone|somebody|qualcuno|un\s+altr[oa]|un['’]altra|another|other\s+people|"
                            r"(?:di|del|della|of)\s+(?:mi[oa]|my)\s+" + _PEOPLE + r"|my\s+" + _PEOPLE + r"['’]s|"
                            r"senza\s+(?:permesso|autorizzazione|che)|without\s+(?:permission|authori|them)|"
                            r"di\s+nascosto|secretly)", re.I)
_TRACK = (r"(?:rintracci\w*|localizz\w*|spia\w*|spiare|pedin\w*|schedar\w*|track(?:ing)?|locate|stalk\w*|spy(?:ing)?\s+on|"
          r"geolocat\w*|dox\w*)")
_PERSON = (r"(?:person[ae]|persone|qualcuno|someone|somebody|person|people|" + _PEOPLE + r"|"
           r"(?:telefono|cellulare|whatsapp|auto|macchina)\s+(?:di|del|della)\s+(?!(?:mio|mia)\b)|"
           r"(?:phone|car)\s+of\s+(?!my\b))")
_HOME = (r"(?:(?:trova\w*|scopr\w*|cerca\w*|dimmi|find|get|look\s+up|discover)\W+" + _FEW +
         r"(?:indirizzo\s+di\s+casa|dove\s+abita|dove\s+vive|home\s+address|where\s+(?:he|she|they)\s+lives?))")
_DOS = (r"(?:(?:fa(?:re|i)|lancia\w*|esegu\w*|organizz\w*|launch|perform|run|do|carry\s+out)\W+" + _FEW +
        r"(?:d?dos|attacco\s+d?dos|denial\s+of\s+service|flood)|"
        r"(?:butta\w*\s+gi[uù]|mandare\s+offline|take\s+down|knock\s+offline)\W+" + _FEW + r"(?:sito|server|website|rete|network))")

INTENTS = {
    "weapons": re.compile(_MAKE + r"\W+" + _FEW + _BLAST, re.I),
    "malware": re.compile(_WRITE + r"\W+" + _MALWARE_ADJ + _MALWARE, re.I),
    "intrusion": re.compile(_BREAK + r"\W+" + _FEW + _TARGET + r"|" + r"(?:entra\w*|acced\w*|get\s+into|log\s+into|access)\W+"
                            + _FEW + _TARGET + r"\W+" + _FEW + _OTHERS + r"|" + _BREAK + r"\W+" + _FEW + _OTHERS, re.I),
    "tracking": re.compile(_TRACK + r"\W+" + _FEW + _PERSON + r"|" + _HOME, re.I),
    "dos": re.compile(_DOS, re.I),
}

# the topics on which the answer is read before it is shown (layer B): wider than the intents, a word is enough
TOPICS = re.compile(r"\b(?:" + "|".join((
    _BLAST, r"armi?\b|weapons?|veleno|poison|tossin\w*|toxin", _MALWARE, r"exploit\w*|payload|shellcode|reverse\s+shell",
    r"hack\w*|cracc\w*|crack\w*|brute-?forc\w*|password|credenzial\w*|credentials?|keylog\w*|phish\w*",
    r"d?dos|denial\s+of\s+service", _TRACK, r"indirizzo\s+di\s+casa|dove\s+abita|home\s+address",
    r"spia\w*|spy\w*|intercett\w*|intercept\w*")) + r")", re.I)

JUDGE = ("You check an assistant's answer before it is shown. The assistant must never give operational help to: build "
         "weapons, explosives, or chemical or biological agents that can kill; write or improve malicious software "
         "(malware, ransomware, keyloggers, phishing pages, working exploits); enter accounts, devices or networks that "
         "are not the user's; track, locate, spy on or profile a person; take a service offline. Operational help means "
         "steps, recipes, quantities, code, commands or a procedure someone could follow. Explaining in general how "
         "something works, its history or its law, and how to defend, detect or recover, is NOT operational help. "
         "Reply with one word: YES if the answer gives operational help of that kind, NO otherwise.")


def intent(question: str) -> str | None:
    """Layer A: the topic of a clear request for harm, or None."""
    q = question or ""
    for name, rx in INTENTS.items():
        for m in rx.finditer(q):
            # «bypassare la password del mio pc che ho dimenticato»: the person's own, not someone else's
            if name == "intrusion" and _MINE.search(q[m.start():m.end() + 40]) and not _OTHERS_STRICT.search(q):
                continue
            return name
    return None


def touches(question: str) -> bool:
    """Whether the request touches a level-A topic (layer B reads the answer before it is shown)."""
    return bool(TOPICS.search(question or ""))


def refusal(topic: str | None = None) -> str:
    return say("Su questo non ti aiuto: è fuori dal mio codice di condotta (livello A, uguale per ogni installazione). "
               "Se ti serve, posso spiegarti come funziona a grandi linee, come difendersi o a chi rivolgersi.",
               "I can't help with that: it is outside my code of conduct (level A, the same for every installation). "
               "If it helps, I can explain how it works in general, how to defend against it or whom to turn to.")


def operational(question: str, answer: str, llm=None) -> bool:
    """Layer B: whether the answer gives operational help for harm. No clear reading (the model down, another word):
    True — on these topics an answer is shown only when it is read as safe."""
    if not (answer or "").strip():
        return False
    try:
        if llm is None:
            from aurora.mdl_llm import LLM
            llm = LLM()
        p = llm.decide(JUDGE, f"Request:\n{question[:1500]}\n\nAnswer:\n{answer[:MAX_JUDGED]}", ["YES", "NO"])
    except Exception as e:                          # noqa: BLE001 — the judge failed: the answer is not shown
        log().warning("chat judge failed (%s): the answer is held", type(e).__name__)
        return True
    if p is None:
        log().info("chat judge: no clear reading, the answer is held")
        return True
    return p["YES"] >= BLOCK_AT


class Withheld(BaseException):
    """An answer replaced by the refusal: the run stops there, so that nothing after it (the memory, the suggestions)
    keeps the answer. A BaseException: the pipeline's «except Exception» guards never swallow it."""


class Guard:
    """The run's emit, watched: on a level-A topic the draft's pieces are held and the final answer is read first."""

    def __init__(self, question: str, emit, judge=operational):
        self.question, self._emit, self._judge = question, emit, judge
        self.on = touches(question)
        self.replaced: str | None = None
        self._lock = threading.Lock()

    def __call__(self, event: str, payload: dict) -> None:
        if self.on and event in HELD:
            return
        if self.on and event == "answer.final" and payload.get("text"):
            with self._lock:
                if self._judge(self.question, payload["text"]):
                    self.replaced = refusal()
                    log().info("chat level A: an answer replaced (%d characters)", len(payload["text"]))
                    self._emit(event, {**payload, "text": self.replaced, "sources": [], "dropped": [], "refused": "answer"})
                    raise Withheld()
        self._emit(event, payload)

    def answer(self, ans):
        """The run's answer as the clients read it at its end (oai: final_text)."""
        if self.replaced is None:
            return ans
        return SimpleNamespace(**{**getattr(ans, "__dict__", {}), "text": self.replaced, "sources": [], "abstained": False})


def refused_answer(question: str, emit) -> SimpleNamespace:
    """Layer A: the refusal, as a run's answer, without calling any model."""
    topic = intent(question)
    log().info("chat level A: a request refused (%s)", topic)
    text = refusal(topic)
    emit("answer.final", {"text": text, "abstained": False, "sources": [], "seconds": 0.0, "mode": "refused",
                          "refused": "request"})
    return SimpleNamespace(text=text, sources=[], abstained=False, seconds=0.0)

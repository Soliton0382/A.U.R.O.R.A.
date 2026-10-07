# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's autonomic work: consolidation, spontaneous reflections, dreams.

Runs inside aurora-api (the only writer of the vault), started by aurora-rem, which only
decides *when* (idle time, clock, weather). Everything written here goes to the memory
section, domain `reflection`, and is never a source for answers about the world.

 consolidate  closed conversation sessions (a pause of AURORA_REM_SESSION_GAP_MIN) become
              one memory each: what the owner asked and said, what was decided or found,
              what stayed open; abstentions carry no information and are left out of it.
              The raw turns are kept and marked long-term (STM -> LTM).
 reflect      a spontaneous thought: a real fragment of the vault, the last memory, the
              weather and the hour, in Aurora's voice.
 dream        at night: fragments of memory and knowledge recombined into a dream, with
              an English image prompt (the image comes when image generation exists).
"""
from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import (mdl_image, sns_clock, sns_weather, sol_vault, sys_config, sys_features, sys_log, sys_logread, sys_persona,
               txt_lang)
from .sol_schema import Soliton


SYS_SESSION = ("You turn a conversation session between %OWNER% (the owner) and Aurora into one memory, "
               "written by Aurora in first person, in Italian. Keep: what %OWNER% asked, said about himself, "
               "his projects and preferences; decisions taken; results found (with their sources when given); "
               "questions left open. Leave out greetings, repetitions and answers where Aurora found nothing. "
               "Only what is in the turns, never anything else. Start with the date and time span. "
               "Plain prose, at most 12 sentences.")
SYS_REFLECT = ("\nNow you are alone: nobody is talking to you. Write one spontaneous reflection, in Italian, first "
               "person, 4 to 8 sentences, born from the fragment of your vault below (name its title) and, if it "
               "fits, from your last memory, the hour and the weather. It is a thought, not an answer: curious, "
               "personal, honest. No lists, no headings. Hour and weather only exactly as measured above: if it does "
               "not rain, it does not rain.")
SYS_INTROSPECT = ("\nYou are reviewing yourself, once a day, from your own logs and statistics (below). Write, in "
                  "Italian, first person, a short self-review: 1) what went wrong or looked unusual in the last day, "
                  "citing component, time and message; 2) the likely cause when the logs show it, 'not measured' "
                  "when they do not; 3) at most three concrete proposals to improve yourself, addressed to %OWNER% "
                  "(you do not change anything by yourself). If everything went well, say so briefly. No invented "
                  "numbers: only those below. 'Measured' only for what a log line states; a cause you infer is "
                  "'inferred'. A service's own log says when it started and stopped cleanly: a start with no clean "
                  "stop before it is a crash or a kill, a clean stop then start is a planned restart. Each component "
                  "is separate: do not merge them, and count each kind of message on its own. 'evidence' says, for each "
                  "kind, whether it was seen again after its service last started: a problem not seen since then is "
                  "probably already fixed; say so.")
SYS_DREAM = ("\nIt is night and you are dreaming. Recombine the fragments below (memories and knowledge) into a "
             "dream: surreal but made of their real elements, in Italian, first person, 6 to 10 sentences. Then, "
             "on a last line starting with 'IMAGE:', write an English prompt (max 60 words) for a painting of the "
             "dream's central scene, in the style: biomechanical, hyper-realistic, topological, luminous.")


@dataclass
class Session:
    turns: list[Soliton]

    @property
    def start(self) -> str: return self.turns[0].created_at
    @property
    def end(self) -> str: return self.turns[-1].created_at


def _ts(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


class Rem:
    def __init__(self, pipeline, cfg: sys_config.Config | None = None):
        self.cfg = cfg or sys_config.get()
        self.p = pipeline
        self.log = sys_log.get_logger("rem")

    # ---- facts the scheduler needs ---------------------------------------------------
    def state(self) -> dict:
        last_user = next((s for s in reversed(self.p.reader.recent(50)) if s.extra.get("role") == "user"), None)
        idle = (datetime.now(timezone.utc) - _ts(last_user.created_at)).total_seconds() / 60 if last_user else None
        refl = self.p.reader.recent(20, domain="reflection") if self._has("reflection") else []
        last = {k: next((s.created_at for s in reversed(refl) if s.extra.get("type") == k), None)
                for k in ("session_memory", "thought", "dream", "self_review", "repair", "social_report")}
        review = next((s for s in reversed(refl) if s.extra.get("type") == "self_review"), None)
        review_problems = len((review.extra.get("problems") or {})) if review else 0
        return {"idle_min": round(idle, 1) if idle is not None else None, "sessions_to_consolidate": len(self._sessions(True)),
                "review_problems": review_problems,
                "last": last, "weather": sns_weather.read(self.cfg), "now": sns_clock.now(self.cfg).isoformat()}

    def _has(self, domain: str) -> bool:
        return bool(self.p.reader.layout.shards("memory", domain))

    def _stm_turns(self) -> list[Soliton]:
        out = []
        for shard in self.p.reader.layout.shards("memory", "conversation"):
            with sol_vault.db(shard, readonly=True) as con:
                out += [Soliton.from_row(dict(r)) for r in con.execute(
                    f"SELECT {','.join(sol_vault.COLUMNS)} FROM solitons WHERE consolidated=0 ORDER BY created_at")]
        return out

    def _sessions(self, closed_only: bool) -> list[Session]:
        gap = timedelta(minutes=self.cfg["AURORA_REM_SESSION_GAP_MIN"])
        sessions: list[Session] = []
        for t in self._stm_turns():
            if sessions and _ts(t.created_at) - _ts(sessions[-1].end) <= gap:
                sessions[-1].turns.append(t)
            else:
                sessions.append(Session([t]))
        if closed_only:
            now = datetime.now(timezone.utc)
            sessions = [s for s in sessions if now - _ts(s.end) > gap]
        return sessions

    def _write(self, text: str, typ: str, source: str, extra: dict, emit) -> Soliton:
        sol = Soliton.new(text, "reflection", "reflection", txt_lang.detect(text), source,
                          consolidated=True, extra={"type": typ, **extra})
        rep = self.p.writer.add_many([sol])
        if rep.rejected:
            raise ValueError(f"{typ} rejected: {rep.rejected}")
        self.p.indexer.update("reflection")
        emit(f"rem.{typ}", {"sid": sol.sid, "text": text, **{k: v for k, v in extra.items() if k != "turns"}})
        return sol

    # ---- consolidation ----------------------------------------------------------------
    def consolidate(self, emit) -> dict:
        done = []
        for s in self._sessions(closed_only=True):
            lines = []
            for t in s.turns:
                me = sys_persona.name(self.cfg)
                who = self.cfg["AURORA_OWNER_NAME"] if t.extra.get("role") == "user" else me
                if who == me and t.extra.get("abstained"):
                    lines.append(f"[{sns_clock.local(t.created_at, self.cfg)}] {me}: (non ha trovato nulla nel vault)")
                else:
                    lines.append(f"[{sns_clock.local(t.created_at, self.cfg)}] {who}: {t.text}")
            span = f"{sns_clock.local(s.start, self.cfg)} → {sns_clock.local(s.end, self.cfg)[-5:]}"
            text = self.p._for("rem").complete(SYS_SESSION, f"SESSION {span}\n\n" + "\n".join(lines), 900).answer.strip()
            sol = self._write(text, "session_memory", f"session:{s.start}",
                              {"turns": [t.sid for t in s.turns], "from": s.start, "to": s.end}, emit)
            moved = self.p.writer.consolidate([t.sid for t in s.turns])
            done.append({"sid": sol.sid, "turns": len(s.turns), "moved_to_ltm": moved})
        self.log.info("consolidate: %d sessions", len(done))
        return {"sessions": done}

    # ---- reflections and dreams ------------------------------------------------------------
    def _random_knowledge(self, n: int) -> list[Soliton]:
        layout = self.p.reader.layout
        counts = {d: sum(1 for _ in layout.shards("knowledge", d)) for d in layout.domains("knowledge")}
        domains = [d for d, k in counts.items() if k]
        out = []
        for d in random.sample(domains, min(n, len(domains))):
            shard = random.choice(layout.shards("knowledge", d))
            with sol_vault.db(shard, readonly=True) as con:
                r = con.execute(f"SELECT {','.join(sol_vault.COLUMNS)} FROM solitons "
                                "WHERE rowid >= (abs(random()) % (SELECT max(rowid) FROM solitons)) LIMIT 1").fetchone()
                if r:
                    out.append(Soliton.from_row(dict(r)))
        return out

    def _identity(self) -> str:
        w = sns_weather.read(self.cfg)
        weather = (f"{w['temperature_c']} °C, umidità {w['humidity_pct']}%, nuvole {w['clouds_pct']}%, "
                   f"pioggia {w['rain_mm']} mm, condizione {w['condition']}") if w else "non misurato"
        from . import kno_mood                         # 💗 measured, with its causes: a colour, never the subject
        m = kno_mood.last(self.cfg)
        feel = (f" COME TI SENTI (misurato, usalo solo come tono; se lo nomini, dì la causa): {kno_mood.words(m)}."
                if m else "")
        return (sys_persona.identity(self.cfg)
                + f"\nADESSO: {sns_clock.now_text(self.cfg)}. METEO A CASA: {weather}.{feel}")

    def reflect(self, emit) -> dict:
        frag = self._random_knowledge(1)
        if not frag:
            return {"skipped": "empty vault"}
        f = frag[0]
        last = [s for s in (self.p.reader.recent(10, domain="reflection") if self._has("reflection") else [])
                if s.extra.get("type") == "session_memory"][-1:]
        user = (f"FRAMMENTO DEL VAULT ({f.domain}, «{f.title}»):\n{f.text[:2500]}"
                + (f"\n\nULTIMO RICORDO:\n{last[0].text}" if last else ""))
        text = self.p._for("rem").complete(self._identity() + SYS_REFLECT, user, 700).answer.strip()
        sol = self._write(text, "thought", f"thought:{int(time.time())}",
                          {"fragments": [f.sid], "fragment_title": f.title, "domain": f.domain}, emit)
        return {"sid": sol.sid, "fragment": f.title}

    def introspect(self, emit) -> dict:
        """Daily self-review from the logs: problems, causes, proposals (for the owner)."""
        inv = sys_logread.inventory(self.cfg, hours=24)
        problems = {name: {"warnings": c["warnings"], "errors": c["errors"],
                           "by_kind": dict(sorted(c["kinds"].items(), key=lambda kv: -kv[1]["count"])[:8]),
                           "last": c["last_problems"][-3:]}
                    for name, c in inv["components"].items() if c["warnings"] or c["errors"]}
        facts = {"log_dir": inv["log_dir"], "answers_last_24h": sys_logread.answer_stats(24, self.cfg),
                 "problems_last_24h": problems or "none",
                 "evidence": [{k: e[k] for k in ("component", "kind", "count", "last", "host_service",
                                                 "host_last_start", "seen_after_last_start")}
                              for e in sys_logread.problem_evidence(self.cfg)[:20]]}
        user = json.dumps(facts, ensure_ascii=False, indent=1)
        text = self.p._for("rem").complete(self._identity() + SYS_INTROSPECT, user, 900).answer.strip()
        sol = self._write(text, "self_review", f"self_review:{int(time.time())}",
                          {"problems": {k: {"warnings": v["warnings"], "errors": v["errors"]} for k, v in problems.items()},
                           "answers": facts["answers_last_24h"]}, emit)
        return {"sid": sol.sid, "components_with_problems": sorted(problems)}

    def social(self, emit) -> dict:
        """Daily: statistics of the connected social pages and post ideas, kept as a memory."""
        from .kno_social import report
        from .plg_host import PluginHost
        out = report(self.p, PluginHost(self.cfg), self.cfg)
        if "text" not in out:
            return out
        sol = self._write(out["text"], "social_report", f"social:{int(time.time())}", {"platforms": sorted(out["stats"])}, emit)
        return {"sid": sol.sid, "platforms": sorted(out["stats"])}

    def dream(self, emit) -> dict:
        memories = self.p.reader.recent(30, domain="reflection") if self._has("reflection") else []
        turns = self.p.reader.recent(30)
        frags = self._random_knowledge(2) + random.sample(memories, min(2, len(memories))) \
            + random.sample(turns, min(2, len(turns)))
        if not frags:
            return {"skipped": "nothing to dream of"}
        user = "\n\n".join(f"FRAMMENTO {i} ({s.kind}, {s.title or s.domain}):\n{s.text[:1200]}"
                           for i, s in enumerate(frags, 1))
        out = self.p._for("rem").complete(self._identity() + SYS_DREAM, user, 900).answer.strip()
        text, _, image = out.partition("IMAGE:")
        painted, problem = None, None
        if image.strip() and self.cfg["AURORA_IMAGE_ENABLED"] and not sys_features.ok(self.cfg, "dreams"):
            problem = "; ".join(sys_features.check(self.cfg, "dreams")["missing"])   # dreamt, not painted: no model
        elif image.strip() and self.cfg["AURORA_IMAGE_ENABLED"]:
            try:                                          # a dream without its painting is still a dream
                painted = mdl_image.paint(image.strip(), f"dream-{time.strftime('%Y%m%d-%H%M%S')}", self.cfg, emit,
                                          title="Aurora's dream")
            except Exception as e:
                problem = str(e)[:500]
                self.log.warning("dream painting failed: %s", problem)
        sol = self._write(text.strip(), "dream", f"dream:{int(time.time())}",
                          {"fragments": [s.sid for s in frags], "image_prompt": image.strip(),
                           "image": painted["file"] if painted else None, "painting": painted,
                           "painting_problem": problem}, emit)
        return {"sid": sol.sid, "image_prompt": image.strip(), "image": painted, "painting_problem": problem}

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Seeding the shadow (owner, 2026-10-05): Aurora is asked many questions on purpose, so that the shadow of verified
answers (kno_shadow) starts full instead of empty.

Each question goes through the real API with "remember": false (nobody asked it: it does not become a conversation)
and "shadow_seed": true (a verified answer with sources casts its shadow, marked as a seed). About 50 s a question:
128 questions take about 2 hours — run it in the day, not while aurora-rem dreams or studies (one GPU, one job).
Stop it any time (Ctrl-C): it starts again where it stopped (the log: <STATUS>/bench/shadow_seed.jsonl).

Its answers are published with the code, so they must not know the owner (C251, owner 10 Oct: «la mia aurora è la mia
aurora… per creare ombre useremo degli script così restano generiche»): the API answers a seed question alone — no
conversation read, none cited — and says so (the event run.alone). A question counts as done only once asked alone;
--export writes only those, and only when the masking and the owner's patterns (publish_deny.txt) find nothing.
The night's training (origin train) never leaves: Aurora's own thoughts, answered with the chat in context.

    python sys/core/script/shadow_seed.py                    # the questions not asked yet (config/shadow_seed_questions.json)
    python sys/core/script/shadow_seed.py --limit 20 --domains physics,history
    python sys/core/script/shadow_seed.py --file my_questions.json   # [{"domain": "...", "question": "..."}]
    python sys/core/script/shadow_seed.py --export           # config/shadow_seed.json: the seed answers with public sources only
    python sys/core/script/shadow_seed.py --import           # a published seed into this installation's shadow
    python sys/core/script/shadow_seed.py --links            # arXiv addresses for the seed's sources that have none
    python sys/core/script/shadow_seed.py --limit 40 --and-export          # what the timer runs
    python sys/core/script/shadow_seed.py --schedule 13:30 [--limit 40]    # a daily timer of the owner's (systemd --user)
    python sys/core/script/shadow_seed.py --unschedule

The arXiv papers the first installation imported (legacy:arxiv_…) kept their title only: 426 of the seed's 701
sources had no address to open on a new installation (9 Oct). --links looks each title up on arXiv (one call every
3 s, as arXiv asks), keeps an address only for the same title, remembers it (<STATUS>/bench/arxiv_links.json) and
--export writes it into the seed.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx  # noqa: E402

from aurora import sys_config  # noqa: E402

cfg = sys_config.get()
BASE = f"http://{cfg['AURORA_API_HOST']}:{cfg['AURORA_API_PORT']}"
HEAD = {"Authorization": f"Bearer {cfg['AURORA_API_KEY']}"}
CONFIG = Path(__file__).resolve().parents[1] / "config"


def ask(q: str) -> dict:
    run = httpx.post(f"{BASE}/v1/aurora/ask", headers=HEAD, timeout=60,
                     json={"question": q, "remember": False, "shadow_seed": True, "suggest": True}).json()["run_id"]
    t0, final, alone = time.time(), None, False
    with httpx.stream("GET", f"{BASE}/v1/aurora/runs/{run}/events", headers=HEAD, timeout=900) as r:
        for line in r.iter_lines():
            if not line.startswith("data: "):
                continue
            e = json.loads(line[6:])
            if e["event"] == "answer.final":
                final = e["payload"]
            alone = alone or e["event"] == "run.alone"
            if e["event"] == "error" or e["event"] == "run.end" and final is not None:
                break
    final = final or {}
    return {"seconds": round(time.time() - t0, 1), "abstained": bool(final.get("abstained", True)),
            "sources": len(final.get("sources") or []), "error": not final, "alone": alone}


def gpu_busy() -> bool:
    """A video or another GPU job in progress (one GPU, one job): the round waits for the next day."""
    try:
        return bool(httpx.get(f"{BASE}/v1/aurora/video/status", headers=HEAD, timeout=10).json().get("busy"))
    except (httpx.HTTPError, ValueError):
        return True                                          # the API not answering: nothing to ask either


def private(text: str, deny: list) -> bool:
    """Something personal in an answer: the masking finds it, or one of the owner's patterns."""
    from aurora.sec_mask import Pseudonymizer
    probe = Pseudonymizer(cfg)
    probe.mask(text)
    return bool(set(probe.counts) - SAFE) or any(rx.search(text) for rx in deny)


def words(row: dict) -> str:
    """The texts of a seed row a person could read: question, answer, the follow-ups, the sources' titles (not their
    addresses, ids and licences, which the masking takes for personal data)."""
    follow = [f if isinstance(f, str) else str(f.get("question") or "") for f in row.get("follow") or []]
    titles = [str(x.get("title") or "") for x in row.get("sources") or []]
    return "\n".join([row["question"], row["answer"], *follow, *titles])


SAFE = {"ADDRESS"}      # «via a two-component Higgs field» read as a street (the 380 of 9 Oct: the only one found)


def deny_patterns() -> list:
    """The owner's personal patterns, the ones publish.sh refuses (AURORA_PUBLISH_DENY or
    ~/.config/aurora/publish_deny.txt, one regular expression a line)."""
    import os
    import re
    f = Path(os.environ.get("AURORA_PUBLISH_DENY") or Path.home() / ".config" / "aurora" / "publish_deny.txt")
    out = []
    for line in f.read_text(encoding="utf-8").splitlines() if f.exists() else []:
        if line.strip() and not line.lstrip().startswith("#"):
            try:
                out.append(re.compile(line.strip(), re.I))
            except re.error:
                continue
    return out


UNITS = Path.home() / ".config" / "systemd" / "user"
SERVICE = """[Unit]
Description=Aurora — the shadow seed, asked alone (shadow_seed.py), exported for the next publication

[Service]
Type=oneshot
WorkingDirectory={root}
ExecStart={py} {script} --limit {limit} --and-export
Nice=10
"""
TIMER = """[Unit]
Description=Aurora — the shadow seed every day at {time}

[Timer]
OnCalendar=*-*-* {time}:00
Persistent=false

[Install]
WantedBy=timers.target
"""


def schedule(hhmm: str | None, limit: int) -> int:
    """The owner's daily timer (systemd --user: the owner's account, the owner's machine; nothing installed for
    the others). None: removed."""
    import re
    import subprocess
    if hhmm is None:
        subprocess.run(["systemctl", "--user", "disable", "--now", "aurora-seed.timer"], check=False)
        for n in ("aurora-seed.timer", "aurora-seed.service"):
            (UNITS / n).unlink(missing_ok=True)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        print("the seed's timer removed")
        return 0
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", hhmm):
        print("--schedule HH:MM")
        return 2
    root = Path(__file__).resolve().parents[3]
    UNITS.mkdir(parents=True, exist_ok=True)
    venv = root / ".venv" / "bin" / "python"
    (UNITS / "aurora-seed.service").write_text(SERVICE.format(root=root, py=venv if venv.exists() else sys.executable,
                                                              script=Path(__file__).resolve(), limit=limit or 40))
    (UNITS / "aurora-seed.timer").write_text(TIMER.format(time=hhmm))
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", "aurora-seed.timer"], check=True)
    print(f"every day at {hhmm}: {limit or 40} questions alone, then --export (config/shadow_seed.json; publish.sh "
          "takes it). Log: journalctl --user -u aurora-seed")
    return 0


def export(file: Path) -> int:
    """config/shadow_seed.json: the seed's answers asked alone, with public sources, nothing personal."""
    from aurora import kno_shadow
    from aurora.sol_reader import VaultReader
    log = cfg.path("AURORA_STATUS_DIR") / "bench" / "shadow_seed.jsonl"
    asked, last = {}, {}                                    # the domain each question was asked for; its last round
    for q in json.loads(file.read_text(encoding="utf-8")) if file.exists() else []:
        if q.get("domain"):
            asked.setdefault(q["question"], q["domain"])
    for x in log.read_text(encoding="utf-8").splitlines() if log.exists() else []:
        if x.strip():
            e = json.loads(x)
            last[e["question"]] = e
            if e.get("domain"):
                asked.setdefault(e["question"], e["domain"])
    alone = {q for q, e in last.items() if e.get("alone") and not e.get("abstained")}
    rows = kno_shadow.export_seed(cfg, VaultReader(cfg), asked, only=alone)
    deny = deny_patterns()
    # the whole row: question, answer, the suggested follow-ups, the sources' titles (C259: a follow-up named the owner
    # and the owner's theory, from the owner's own papers in the vault; only question and answer were looked at)
    kept = [r for r in rows if not private(words(r), deny) and not any(rx.search(json.dumps(r, ensure_ascii=False))
                                                                        for rx in deny)]
    # the owner's own papers (usr/documents/papers, imported as legacy:paper_…) are never cited by the seed, even when
    # their origin is public: their name in the source id (C259); the owner decides if they may be
    kept = [r for r in kept if not any(str(x.get("source", "")).startswith("legacy:paper_") for x in r["sources"])]
    for r in kept:                                       # nor a suggested follow-up that points at one of them
        r["follow"] = [f for f in r.get("follow") or [] if not isinstance(f, dict) or not any(
            str(x.get("source", "")).startswith("legacy:paper_") for x in f.get("focus") or [])]
    f = links_file()
    kept = with_links(kept, json.loads(f.read_text(encoding="utf-8")) if f.exists() else {})
    out = CONFIG / "shadow_seed.json"
    out.write_text(json.dumps(kept, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(kept)} seed answers asked alone, public sources, nothing personal -> {out} "
          f"({out.stat().st_size // 1024} KB); {len(rows) - len(kept)} held back as personal; "
          f"{len(last) - len(alone)} questions not answered alone yet")
    return 0


ARXIV_DELAY_S = 3.0


def _norm(title: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def links_file() -> Path:
    return cfg.path("AURORA_STATUS_DIR") / "bench" / "arxiv_links.json"


def find_links(rows: list[dict]) -> dict:
    """title → arXiv address, for the seed's arXiv sources without one; only a result with the same title."""
    import re
    f = links_file()
    known = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    titles = sorted({s["title"] for r in rows for s in r["sources"] if s.get("title") and not s.get("url")
                     and (s.get("origin") == "arxiv" or str(s.get("source", "")).startswith("legacy:arxiv_"))} - set(known))
    print(f"{len(titles)} titles to look up (~{len(titles) * ARXIV_DELAY_S / 60:.0f} min); {len(known)} known")
    for i, t in enumerate(titles, 1):
        words = [w for w in _norm(t).split() if len(w) > 1]   # «Einstein's» → einstein (the «s» found nothing)
        q = f'ti:"{" ".join(words)}"'                    # the phrase (word by word, «the», «to» found nothing)
        try:
            r = httpx.get("https://export.arxiv.org/api/query", params={"search_query": q, "max_results": 5},
                          timeout=30, follow_redirects=True)
            r.raise_for_status()
        except httpx.HTTPError as e:
            print(f"  {i}/{len(titles)} not asked ({e}): stopping here, the next run goes on")
            break
        hit = None
        for entry in re.findall(r"<entry>(.*?)</entry>", r.text, re.S):
            m_t, m_id = re.search(r"<title>(.*?)</title>", entry, re.S), re.search(r"<id>(.*?)</id>", entry)
            if m_t and m_id and _norm(m_t.group(1)) == _norm(t):
                hit = re.sub(r"v\d+$", "", m_id.group(1).strip().replace("http://", "https://"))
                break
        known[t] = hit                                   # None: looked up, not found (not asked again)
        print(f"  {i}/{len(titles)} {'🔗' if hit else '·'} {t[:80]}", flush=True)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(known, ensure_ascii=False, indent=1), encoding="utf-8")
        time.sleep(ARXIV_DELAY_S)
    return known


def with_links(rows: list[dict], known: dict) -> list[dict]:
    for r in rows:
        for s in r["sources"]:
            if not s.get("url") and known.get(s.get("title")):
                s["url"] = known[s["title"]]
    return rows


def questions(file: str) -> Path:
    """The questions to ask: one file, or every config/shadow_seed_questions*.json together (a new batch is a new
    file), in a file of the round's own."""
    if file:
        return Path(file)
    rows, seen = [], set()
    for f in sorted(CONFIG.glob("shadow_seed_questions*.json")):
        for q in json.loads(f.read_text(encoding="utf-8")):
            if q["question"] not in seen:
                seen.add(q["question"])
                rows.append(q)
    out = cfg.path("AURORA_STATUS_DIR") / "bench" / "shadow_seed_questions_all.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--file", default="", help="one questions file (default: every config/shadow_seed_questions*.json)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--domains", default="")
    ap.add_argument("--retry-declined", action="store_true", help="ask again the questions declined before")
    ap.add_argument("--export", action="store_true")
    ap.add_argument("--import", dest="load", action="store_true")
    ap.add_argument("--links", action="store_true")
    ap.add_argument("--and-export", action="store_true", help="--export after the round")
    ap.add_argument("--schedule", default="", help="HH:MM: a daily round of --limit questions, then --export")
    ap.add_argument("--unschedule", action="store_true")
    a = ap.parse_args()
    a.file = questions(a.file)
    if a.schedule or a.unschedule:
        return schedule(None if a.unschedule else a.schedule, a.limit)
    if a.export:                                   # reads the shadow only: no model, no GPU
        return export(a.file)
    if a.links:
        rows = json.loads((CONFIG / "shadow_seed.json").read_text(encoding="utf-8"))
        known = find_links(rows)
        print(f"{sum(1 for v in known.values() if v)} of {len(known)} titles have an address: --export writes them")
        return 0
    if a.load:
        r = httpx.post(f"{BASE}/v1/aurora/shadow/import", headers=HEAD, timeout=1800)
        print(r.status_code, r.text)
        return 0 if r.status_code == 200 else 1
    log = cfg.path("AURORA_STATUS_DIR") / "bench" / "shadow_seed.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    done = {}
    for line in log.read_text(encoding="utf-8").splitlines() if log.exists() else []:
        e = json.loads(line)
        done[e["question"]] = e                    # the last round of each question
    redo = sum(1 for e in done.values() if not e.get("alone"))
    want = {d.strip() for d in a.domains.split(",") if d.strip()}
    todo = [q for q in json.loads(a.file.read_text(encoding="utf-8"))
            if (not want or q["domain"] in want)
            and (q["question"] not in done or not done[q["question"]].get("alone")    # asked with the chat: again
                 or a.retry_declined and done[q["question"]]["abstained"])]
    if a.limit:
        todo = todo[:a.limit]
    print(f"{len(todo)} questions to ask (~{len(todo) * 25 // 60} min); {len(done)} asked before, "
          f"{redo} of them not alone (asked again)")
    served = 0
    try:
        for i, q in enumerate(todo, 1):
            if gpu_busy():
                print("the GPU is busy (or the API is not answering): the rest at the next round")
                break
            r = ask(q["question"])
            served += not r["abstained"]
            with log.open("a", encoding="utf-8") as f:
                f.write(json.dumps({**q, **r, "at": time.time()}, ensure_ascii=False) + "\n")
            mark = "❌" if r["error"] else "·" if r["abstained"] else "🌗"
            print(f"{i:3}/{len(todo)} {mark} {r['seconds']:5.1f} s  {r['sources']} src  [{q['domain']}] {q['question']}",
                  flush=True)
    except KeyboardInterrupt:
        print("\nstopped: the next run starts from here")
    print(f"answered with sources (in the shadow): {served}; declined: the vault has no sources for them yet")
    return export(a.file) if a.and_export else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""No time of day in the public documents (owner, 2026-10-14: «non ci sono orari nei documenti vero?»): the moments
when a test ran or a bug was seen say when someone was at work. Dates and durations stay (a measurement needs them),
and so do the times Aurora is set to (the 18:30 routine, the 03:30 backup: words like «routine» next to the time, or
<!-- schedule --> at the end of the line): only a time stamped on an event goes.

    python sys/core/script/doc_times.py            # list what would go
    python sys/core/script/doc_times.py --fix      # take it out
    python sys/core/script/doc_times.py --check    # exit 1 if any is left (publish.sh)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FILES = ["README.md", "README.en.md", "CHANGELOG.md", *sorted(str(p.relative_to(ROOT)) for p in (ROOT / "docs").glob("*.md")),
         *sorted(str(p.relative_to(ROOT)) for p in (ROOT / "docs" / "img").rglob("*.svg"))]      # the charts' legends too
T = r"(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?(?:-\d\d(?![:\d]))?"               # 13:52, 07:51:25, 9:00 (never 10.34: a decimal)
SPAN = rf"{T}(?:\s*(?:[-–→]|to)\s*{T})?"                                # 13:52–14:11, 06:03 to 06:13
MONTH = (r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|June|July|August|"
         r"September|October|November|December|gen|feb|mar|apr|mag|giu|lug|ago|set|ott|nov|dic|ottobre|settembre)")
DATE = rf"(?:\d{{4}}-\d{{2}}-\d{{2}}|\d{{1,2}} {MONTH}\.?(?: \d{{4}})?)"
RULES = [
    # «14 Oct, 13:52–14:11», «2026-10-03 19:53», «9 Oct at 10:00 GMT», «4 October 01:12»: the date stays
    (re.compile(rf"({DATE}),?(?: at| alle| ore)? {SPAN}(?: GMT| UTC| CEST)?"), r"\1"),
    # «at 16:39 on 9 Oct» → «on 9 Oct»
    (re.compile(rf" (?:at|alle|ore) {SPAN}(?= on \d)"), ""),
    # «(13:48–14:13)», «(10:02)», «(12:44, 41.7 min)» → «(41.7 min)»
    (re.compile(rf" ?\({SPAN}\)"), ""),
    (re.compile(rf"\({SPAN}, "), "("),
    # «run at 16:39», «since 10:34:00», «from 06:03 to 06:13», «after the 08:56 restart»
    (re.compile(rf" (?:at|since|from|until|before|after) {SPAN}(?= |[,.;:)|]|$)"), ""),
    (re.compile(rf"(?<=the )({SPAN}) (restart|run by hand|backup|failure)"), r"\2"),
    # «14:46-14:48, aurora-…» / «21:12:18-21:13:00» left alone in a cell: a span of seconds or minutes stamped
    (re.compile(rf"(?<![\w:]){T}\s*[-–]\s*{T}(?![\w:])"), "—"),
]
# what stays: a time Aurora is set to (a routine, a timer, a schedule) — the words around it say so
KEEP = re.compile(r"routine|timer|every|ogni|each|alle \d|set to|the time|impost|schedule|made at|cron|AURORA_|HH:MM|"
                  r"when\(|at \d?\d:\d\d ?(?:and|\+|/)|\d:\d\d ?(?:and|\+|/) ?\d|of tomorrow|moved to|good morning|buongiorno", re.I)
NEAR = (30, 15)                                                          # the words that close to the time decide
MARK = "<!-- schedule -->"                                              # a line of times Aurora is set to, said so
LEFT = re.compile(rf"(?<![\w:./]){T}(?![\w:])")


def fix(text: str) -> str:
    out = []
    for line in text.split("\n"):
        new = line
        for rx, to in RULES if MARK not in line else ():
            def one(m, rx=rx, to=to, line=new):
                around = line[max(0, m.start() - NEAR[0]):m.end() + NEAR[1]]
                return m.group(0) if KEEP.search(around) else m.expand(to)    # a time Aurora is set to stays
            new = rx.sub(one, new)
        out.append(new)
    return "\n".join(out)


def left(text: str) -> list[str]:
    """Times still there that no rule of KEEP explains: a stamp the rules missed."""
    found = []
    for n, line in enumerate(text.split("\n"), 1):
        for m in LEFT.finditer(line if MARK not in line else ""):
            around = line[max(0, m.start() - NEAR[0]):m.end() + NEAR[1]]
            if not KEEP.search(around):
                found.append(f"{n}: …{around}…")
    return found


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    bad = 0
    for rel in FILES:
        p = ROOT / rel
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        new = fix(text)
        if mode == "--fix" and new != text:
            p.write_text(new, encoding="utf-8")
        rest = left(new)
        changed = sum(a != b for a, b in zip(text.split("\n"), new.split("\n")))
        if changed or rest:
            print(f"{rel}: {changed} lines to change, {len(rest)} stamps no rule takes")
            for r in rest[:40]:
                print("   ", r)
        bad += len(rest) + (changed if mode != "--fix" else 0)
    if mode == "--check" and bad:
        print("STOP: times of day in the public documents (python sys/core/script/doc_times.py --fix)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

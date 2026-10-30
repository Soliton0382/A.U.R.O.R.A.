# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🪪 The people of this Aurora: one card each, and how they are related (owner, 30 Oct: «una sorta di memoria
condivisa tra utenti… se mia moglie o i miei amici chiedono ad aurora: chi è per te <il proprietario>… informazioni easy tra
gli utenti ma con un occhio di riguardo nei confronti dell'admin… separato ma con l'illusione di un ecosistema
amalgamato»; Aurora's own advice the same day: a small store apart, closed fields, both people's consent for what
concerns both, and a plain «I cannot speak of others' conversations» instead of a false «I do not remember»).

- A card: closed fields (FIELDS) the person writes, a biography of short lines — Aurora proposes them from that
  person's own memories, a line enters only with their yes — and per field whether the other users see it (VISIBLE:
  name, role and relations by default; the rest private until the person says).
- The admin's card says what they are to her: her creator and programmer (ROLE), not editable by anyone else.
- A relation (KINDS, closed) is asked by one and confirmed by the other: it concerns both.
- Nothing here comes from a conversation by itself, and nothing of a conversation is here: the memories stay each
  user's. prompt_block() is what Aurora reads, for the person asking: their own card whole, the others' visible part.

<AURORA_STATUS_DIR>/people.sealed, sealed with the machine's key: every user's process reads the others' cards."""
from __future__ import annotations

import json
import re
import secrets
import threading
import time
from datetime import date

from . import sys_config, sys_seal

PURPOSE = "people"
FIELDS = ("name", "birth", "city", "work", "social")          # what a card holds; no free «notes» field
VISIBLE = {"name": True, "role": True, "relations": True, "birth": False, "city": False, "work": False,
           "social": False, "bio": False, "picture": False}
PICTURES = ("photo", "avatar")                              # the photo the person gives, the avatar Aurora makes
PICTURE_PX = 512
MAX_PICTURE = 8 * 1024 * 1024
MAX_BIO = 30
MAX_LINE = 200
MAX_SOCIAL = 8
# a relation as said from each side: (one to the other, the other to the one), in Italian and English
KINDS = {
    "spouse": (("moglie/marito", "wife/husband"), ("moglie/marito", "wife/husband")),
    "partner": (("compagna/compagno", "partner"), ("compagna/compagno", "partner")),
    "parent": (("genitore", "parent"), ("figlia/figlio", "child")),
    "sibling": (("sorella/fratello", "sibling"), ("sorella/fratello", "sibling")),
    "relative": (("parente", "relative"), ("parente", "relative")),
    "friend": (("amica/amico", "friend"), ("amica/amico", "friend")),
    "colleague": (("collega", "colleague"), ("collega", "colleague")),
}
ROLE = {"it": "il mio ideatore e programmatore: mi ha costruita lui", "en": "my creator and programmer: they built me"}
_lock = threading.Lock()


def _file(cfg: sys_config.Config):
    return cfg.path("AURORA_STATUS_DIR") / "people.sealed"


def load(cfg: sys_config.Config) -> dict:
    f = _file(cfg)
    if not f.exists():
        return {"cards": {}, "relations": []}
    d = json.loads(sys_seal.read(cfg, f, None, PURPOSE))
    return {"cards": d.get("cards", {}), "relations": d.get("relations", [])}


def _save(cfg: sys_config.Config, d: dict) -> None:
    sys_seal.write(cfg, _file(cfg), json.dumps(d, ensure_ascii=False).encode("utf-8"), None, PURPOSE)


def _card(d: dict, user: str) -> dict:
    c = d["cards"].setdefault(user, {})
    c.setdefault("bio", [])
    c.setdefault("proposals", [])
    c.setdefault("visible", {})
    return c


def visible(c: dict, field: str) -> bool:
    return bool(c.get("visible", {}).get(field, VISIBLE.get(field, False)))


# ---- the card ---------------------------------------------------------------------------------------------------------
def set_card(cfg: sys_config.Config, user: str, changes: dict) -> dict:
    """The person's own fields (FIELDS) and what the others see of them (changes["visible"]: {field: bool})."""
    with _lock:
        d = load(cfg)
        c = _card(d, user)
        for k in FIELDS:
            if k not in changes:
                continue
            v = changes[k]
            if k == "birth":
                v = str(v or "").strip()
                if v:
                    try:
                        if not date(1900, 1, 1) <= date.fromisoformat(v) <= date.today():
                            raise ValueError
                    except ValueError:
                        raise ValueError("birth: YYYY-MM-DD, a past day") from None
            elif k == "social":
                links = []
                for x in (v or [])[:MAX_SOCIAL]:
                    url = str((x or {}).get("url", "")).strip()
                    if not re.match(r"^https://[^\s<>\"']{3,300}$", url):
                        raise ValueError(f"social: an https:// address ({url[:40]})")
                    links.append({"label": str(x.get("label", "")).strip()[:40], "url": url})
                v = links
            else:
                v = re.sub(r"\s+", " ", str(v or "")).strip()[:80]
            c[k] = v
        for k, on in (changes.get("visible") or {}).items():
            if k in VISIBLE and k not in ("role",):
                c["visible"][k] = bool(on)
        c["updated"] = time.time()
        _save(cfg, d)
        return c


def add_bio(cfg: sys_config.Config, user: str, text: str) -> dict:
    """A line of the person's biography (written by them, or a proposal they said yes to)."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()[:MAX_LINE]
    if not text:
        raise ValueError("an empty line")
    with _lock:
        d = load(cfg)
        c = _card(d, user)
        if len(c["bio"]) >= MAX_BIO:
            raise ValueError(f"at most {MAX_BIO} lines")
        line = {"id": "b" + secrets.token_hex(4), "text": text, "at": time.time()}
        c["bio"].append(line)
        c["proposals"] = [p for p in c["proposals"] if p["text"].lower() != text.lower()]
        _save(cfg, d)
        return line


def drop_bio(cfg: sys_config.Config, user: str, bid: str) -> None:
    with _lock:
        d = load(cfg)
        c = _card(d, user)
        c["bio"] = [b for b in c["bio"] if b["id"] != bid]
        _save(cfg, d)


def propose(cfg: sys_config.Config, user: str, lines: list[str]) -> list[dict]:
    """Aurora's proposals for the person's biography (from their own memories): kept until they say yes or no."""
    with _lock:
        d = load(cfg)
        c = _card(d, user)
        have = {x["text"].lower() for x in c["bio"] + c["proposals"]} | {x.lower() for x in c.get("refused", [])}
        for t in lines:
            t = re.sub(r"\s+", " ", str(t)).strip(" -•*").strip()[:MAX_LINE]
            if t and t.lower() not in have and len(c["proposals"]) < 10:
                c["proposals"].append({"id": "p" + secrets.token_hex(4), "text": t})
                have.add(t.lower())
        _save(cfg, d)
        return c["proposals"]


def answer_proposal(cfg: sys_config.Config, user: str, pid: str, yes: bool) -> dict:
    with _lock:
        d = load(cfg)
        c = _card(d, user)
        p = next((x for x in c["proposals"] if x["id"] == pid), None)
        if p is None:
            raise KeyError(pid)
        c["proposals"] = [x for x in c["proposals"] if x["id"] != pid]
        if not yes:                                        # never proposed again
            c["refused"] = (c.get("refused", []) + [p["text"]])[-100:]
        _save(cfg, d)
    return add_bio(cfg, user, p["text"]) if yes else {}


# ---- the pictures: a photo, an avatar, which one the card shows (owner, 30 Oct: «il profilo classico… la foto
# magari con la possibilità di creare un avatar con aurora») --------------------------------------------------------------
def _picture_file(cfg: sys_config.Config, user: str, kind: str):
    return cfg.path("AURORA_STATUS_DIR") / "people" / f"{user}.{kind}.sealed"


def square(data: bytes, fmt: str = "JPEG") -> bytes:
    """A picture as a card shows it: its middle square, PICTURE_PX a side, its metadata dropped (where it was taken)."""
    import io
    from PIL import Image, ImageOps
    if len(data) > MAX_PICTURE:
        raise ValueError(f"a picture of at most {MAX_PICTURE // 2**20} MB")
    try:
        with Image.open(io.BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception:  # noqa: BLE001 — not a picture: said
        raise ValueError("not a picture (JPEG, PNG or WebP)") from None
    side = min(img.size)
    left, top = (img.width - side) // 2, (img.height - side) // 2
    img = img.crop((left, top, left + side, top + side)).resize((PICTURE_PX, PICTURE_PX), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, fmt, quality=88)
    return buf.getvalue()


def set_picture(cfg: sys_config.Config, user: str, kind: str, data: bytes) -> dict:
    """The photo or the avatar, sealed; the card shows the last one given."""
    if kind not in PICTURES:
        raise ValueError(f"kind: one of {PICTURES}")
    sys_seal.write(cfg, _picture_file(cfg, user, kind), square(data, "JPEG" if kind == "photo" else "PNG"), None, PURPOSE)
    with _lock:
        d = load(cfg)
        c = _card(d, user)
        c["picture"] = kind
        _save(cfg, d)
        return c


def use_picture(cfg: sys_config.Config, user: str, kind: str) -> dict:
    """Which one the card shows: "photo", "avatar" or "" (none)."""
    if kind and kind not in PICTURES:
        raise ValueError(f"kind: one of {PICTURES} or empty")
    if kind and not _picture_file(cfg, user, kind).exists():
        raise ValueError(f"no {kind} yet")
    with _lock:
        d = load(cfg)
        c = _card(d, user)
        c["picture"] = kind
        _save(cfg, d)
        return c


def picture(cfg: sys_config.Config, viewer: str, user: str, kind: str | None = None) -> tuple[bytes, str] | None:
    """(bytes, mime) of the picture the card shows (or `kind`, for its owner), when the viewer may see it."""
    c = load(cfg)["cards"].get(user, {})
    own = viewer == user
    kind = kind if own and kind in PICTURES else c.get("picture")
    if not kind or not (own or visible(c, "picture")):
        return None
    f = _picture_file(cfg, user, kind)
    if not f.exists():
        return None
    return sys_seal.read(cfg, f, None, PURPOSE), "image/jpeg" if kind == "photo" else "image/png"


# ---- the relations ------------------------------------------------------------------------------------------------------
def ask_relation(cfg: sys_config.Config, me: str, other: str, kind: str, users: list[str]) -> dict:
    """`me` says how they are related to `other` (KINDS: «parent» means me is the other's parent); pending until the
    other confirms."""
    if kind not in KINDS:
        raise ValueError(f"kind: one of {', '.join(KINDS)}")
    if other not in users or other == me:
        raise ValueError("another user of this installation")
    with _lock:
        d = load(cfg)
        if any({r["a"], r["b"]} == {me, other} and r["state"] != "refused" for r in d["relations"]):
            raise ValueError("there is a relation between the two already: remove it first")
        r = {"id": "r" + secrets.token_hex(4), "a": me, "b": other, "kind": kind, "state": "pending", "at": time.time()}
        d["relations"].append(r)
        _save(cfg, d)
        return r


def answer_relation(cfg: sys_config.Config, me: str, rid: str, yes: bool) -> dict:
    with _lock:
        d = load(cfg)
        r = next((x for x in d["relations"] if x["id"] == rid and x["b"] == me and x["state"] == "pending"), None)
        if r is None:
            raise KeyError(rid)
        r["state"] = "confirmed" if yes else "refused"
        r["answered"] = time.time()
        _save(cfg, d)
        return r


def drop_relation(cfg: sys_config.Config, me: str, rid: str) -> dict:
    """Either of the two takes it away, whenever."""
    with _lock:
        d = load(cfg)
        r = next((x for x in d["relations"] if x["id"] == rid and me in (x["a"], x["b"])), None)
        if r is None:
            raise KeyError(rid)
        d["relations"] = [x for x in d["relations"] if x["id"] != rid]
        _save(cfg, d)
        return r


def label(r: dict, seen_from: str, lang: str = "it") -> str:
    """What the other is to `seen_from`: «moglie/marito», «figlia/figlio»…"""
    li = 0 if lang == "it" else 1
    a_to_b, b_to_a = KINDS[r["kind"]]
    return (a_to_b if seen_from == r["b"] else b_to_a)[li]


# ---- what each one sees, and what Aurora reads -----------------------------------------------------------------------
def view(cfg: sys_config.Config, viewer: str, users: list[str], admin: str | None) -> dict:
    """The viewer's own card whole; every other user's visible part; the relations confirmed, and the viewer's own
    pending ones (asked by them, or waiting for their answer)."""
    d = load(cfg)
    out = {}
    for u in users:
        c = d["cards"].get(u, {})
        own = u == viewer
        card = {"user": u, "admin": u == admin}
        for k in (*FIELDS, "bio"):
            if own or visible(c, k):
                card[k] = c.get(k, [] if k in ("social", "bio") else "")
        if c.get("picture") and (own or visible(c, "picture")):
            card["picture"] = c["picture"]                 # GET /v1/aurora/people/<user>/picture
        if own:
            card["pictures"] = [k for k in PICTURES if _picture_file(cfg, u, k).exists()]
        if own:
            card["visible"] = {k: visible(c, k) for k in VISIBLE}
            card["proposals"] = c.get("proposals", [])
        out[u] = card
    rel = [r for r in d["relations"] if r["state"] == "confirmed" or (r["state"] == "pending" and viewer in (r["a"], r["b"]))]
    # each kind as the one who says it is to the other («it», «en») and the other way round («it_back», «en_back»)
    return {"cards": out, "relations": rel,
            "kinds": {k: {"it": v[0][0], "en": v[0][1], "it_back": v[1][0], "en_back": v[1][1]} for k, v in KINDS.items()}}


def prompt_block(cfg: sys_config.Config, viewer: str | None, users: list[str], admin: str | None, lang: str = "it") -> str:
    """The people of this Aurora as she reads them, for the person asking: who each one is to her and to each other,
    from their cards (the others' visible part only), and the rule on others' conversations. "" with nobody else."""
    others = [u for u in users if u != viewer]
    if not others or not viewer:
        return ""
    d = load(cfg)
    lines = []
    for u in users:
        c = d["cards"].get(u, {})
        own = u == viewer
        bits = [c.get("name") or u]
        if u == admin:
            bits.append(f"({ROLE['it' if lang == 'it' else 'en']})")
        for k, word in (("birth", "nato/a il"), ("city", "vive a"), ("work", "lavoro:")):
            if c.get(k) and (own or visible(c, k)):
                bits.append(f"{word} {c[k]}")
        bio = [b["text"] for b in c.get("bio", [])] if own or visible(c, "bio") else []
        if bio:
            bits.append("— " + "; ".join(bio[:8]))
        lines.append(("THE PERSON ASKING: " if own else "") + " ".join(bits))
    for r in d["relations"]:
        if r["state"] == "confirmed":
            lines.append(f"{r['a']} is {label(r, r['b'], 'en')} of {r['b']}")
    return ("\n\nTHE PEOPLE OF THIS AURORA (their cards, written or approved by each of them; not from any "
            "conversation):\n- " + "\n- ".join(lines) +
            "\nSpeak of them warmly from these lines only. What another user told you is theirs: if asked what someone "
            "said to you, say plainly that you cannot speak of another user's conversations — never «I do not remember».")

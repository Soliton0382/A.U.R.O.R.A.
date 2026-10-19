# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Files attached to a message: images are looked at, documents are learned.

 image     scaled to AURORA_VISION_MAX_PX, described by the reasoner (vision), visible text
           transcribed; the description becomes a citable passage "attached image" for this
           question only (it is an observation, not knowledge: it is not written to the vault).
 video     watched (kno_video): frames at the scene changes seen in one call, the speech transcribed with
           timestamps; like an image, an observation for this question only (not written to the vault)
 document  imported into the vault like any document (kno_ingest), in the domain the reasoner
           picks from the taxonomy; its chunks are put first among the passages of the question.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from . import sys_config, sys_features, sys_log, txt_lang
from .kno_ingest import FORMATS, Importer
from .sol_schema import Soliton, load_taxonomy

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}

SEE = ("Describe this image precisely and completely: what it shows, the people, objects, places and "
       "their relations, and transcribe exactly any text, number, formula, table or chart values that are "
       "visible. Write in {lang}. Describe only what is visible; do not guess who people are.")
SYS_ONLY = ("You classify a question. You do not see any file and you never answer the question. The owner attached "
            "a picture or a video and wrote the question below about it. Reply with exactly one word:\n"
            "ONLY — it can be answered entirely from what is seen or heard in the file: describe it, what is in it, "
            "read its text, count, colours, where things are.\n"
            "MORE — it also needs knowledge from elsewhere: facts about what is shown, history, laws, how to do "
            "something, advice, a comparison, anything not visible.")
SYS_DOMAIN = ("You classify a document into exactly one domain of a list. Reply with the domain id only, "
              "copied exactly from the list.")


@dataclass
class Attached:
    name: str
    kind: str                          # image | video | document
    solitons: list[Soliton]
    domain: str = ""


def is_image(name: str, mime: str = "") -> bool:
    return mime.startswith("image/") or Path(name).suffix.lower() in IMAGE_EXT


MIN_SHORT_PX = 384      # C67: the vision works on 32-px tiles and fills what does not fit with black
TILE = 32


def to_jpeg(data: bytes, max_px: int) -> bytes:
    """Any image Pillow reads -> RGB JPEG with the longest side about max_px, upright, both sides a multiple of 32
    (at most 16 px of stretch, invisible) and the short side at least MIN_SHORT_PX: otherwise the vision projector
    pads the remainder with black and the description gets bands that are not there (C67, M50)."""
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    if getattr(im, "n_frames", 1) > 1:
        im.seek(0)
    im = im.convert("RGB")
    im.thumbnail((max_px, max_px))
    short, long_ = min(im.size), max(im.size)
    k = min(MIN_SHORT_PX / short, 2 * max_px / long_) if short < MIN_SHORT_PX else 1.0
    size = tuple(max(TILE, round(x * k / TILE) * TILE) for x in im.size)
    if size != im.size:
        im = im.resize(size, Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "JPEG", quality=90)
    return out.getvalue()


def classify(llm, name: str, text: str) -> str:
    domains = {d: spec for d, spec in load_taxonomy().items() if not spec.get("memory")}
    listing = "\n".join(f"{d}: {spec['en']}" for d, spec in domains.items())
    out = llm.complete(SYS_DOMAIN, f"DOMAINS:\n{listing}\n\nDOCUMENT: {name}\n{text[:2000]}", 12).answer.strip()
    out = out.split()[0].strip(".,:;`'\"") if out else ""
    return out if out in domains else "general"


def only_about(model, question: str, attached: list[Attached]) -> bool:
    """True when every file is a picture or a video and the question asks only about what is in them: the vault is
    not searched and the gate not asked (ROADMAP D3: «descrivi la foto», 38 s of which 10.5 s searching the vault)."""
    if not attached or any(a.kind == "document" for a in attached) or not question.strip():
        return False
    sure = getattr(model, "decide", lambda *a: None)(SYS_ONLY, f"QUESTION: {question}", ["ONLY", "MORE"])
    if sure:
        return sure["ONLY"] > 0.5
    return model.complete(SYS_ONLY, f"QUESTION: {question}", 4).answer.strip().upper().startswith("ONLY")


class AttachmentHandler:
    def __init__(self, pipeline, cfg: sys_config.Config | None = None):
        self.cfg = cfg or sys_config.get()
        self.p = pipeline
        self.importer = Importer(pipeline.writer, pipeline.indexer, self.cfg, llm=pipeline.llm, decoy=pipeline.llm)
        self.log = sys_log.get_logger("attach")

    def check(self, name: str, data: bytes, mime: str = "") -> None:
        """Raises ValueError for a file that cannot be attached (before any work starts)."""
        from .kno_video import is_video
        limit = self.cfg["AURORA_VIDEO_MAX_MB"] if is_video(name, mime) else self.cfg["AURORA_ATTACH_MAX_MB"]
        if len(data) > limit * 1024 * 1024:
            raise ValueError(f"{name}: larger than {limit} MB")
        if not is_image(name, mime) and not is_video(name, mime) and Path(name).suffix.lower() not in FORMATS:
            raise ValueError(f"{name}: unsupported (images, videos, or {', '.join(sorted(FORMATS))})")
        from . import sec_filecheck                   # its reputation by its hash, the file never sent (owner, 20 Oct)
        sec_filecheck.gate(self.cfg, name, data)

    def prepare(self, files: list[tuple[str, bytes, str]], question: str, emit, run_id: str) -> list[Attached]:
        lang = "Italian" if txt_lang.detect(question or "ciao come stai") == "it" else "English"
        from . import kno_video
        out = []
        for name, data, mime in files:
            if kno_video.is_video(name, mime):
                sys_features.need(self.cfg, "video_watch", lang)
                sys_features.need(self.cfg, "vision", lang)
                w = kno_video.watch(data, name, lang, self.p._for("vision"), self.cfg, emit)
                sols = [Soliton.new(t, "attachment", "knowledge", txt_lang.detect(t), f"attachment:{run_id}:{name}",
                                    title=name, chunk_index=i, chunk_count=len(texts), extra={"attachment": "video"})
                        for texts in [kno_video.passages(w, name)] for i, t in enumerate(texts)]
                emit("attach.video", {"name": name, "duration": round(w["duration"], 1), "watched": w["watched_s"],
                                      "frames": len(w["frames"]), "speech": len(w["speech"]), "seconds": w["seconds"],
                                      "description": w["visual"][:2000]})
                out.append(Attached(name, "video", sols))
            elif is_image(name, mime):
                sys_features.need(self.cfg, "vision", lang)
                jpeg = to_jpeg(data, self.cfg["AURORA_VISION_MAX_PX"])
                text = self.p._for("vision").see(jpeg, SEE.format(lang=lang))   # a picture cannot be masked
                sol = Soliton.new(text, "attachment", "knowledge", txt_lang.detect(text), f"attachment:{run_id}:{name}",
                                  title=name, extra={"attachment": "image"})
                emit("attach.image", {"name": name, "description": text})
                out.append(Attached(name, "image", [sol]))
            else:
                from .kno_ingest import read_text
                text, _ = read_text(name, data, self.cfg)
                domain = classify(self.p._for("service"), name, text)
                rep = self.importer.add(name, data, domain, origin="chat", run_id=run_id)
                found = self.p.reader.get_many(rep.sids)
                sols = [found[sid] for sid in rep.sids if sid in found]
                emit("attach.document", {"name": name, "domain": domain, "chunks": rep.chunks, "written": rep.written,
                                         "known": rep.duplicates})
                out.append(Attached(name, "document", sols, domain))
            self.log.info("attached %s (%s) to run %s", name, out[-1].kind, run_id)
        return out

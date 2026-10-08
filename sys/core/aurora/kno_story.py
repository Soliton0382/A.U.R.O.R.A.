# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora's narrated videos (owner, 2026-10-06: "her voice off-screen, pictures made with art chained in a video, she is
seen little"; the budget: zero). Everything runs on this machine:
 1 the answer    the pipeline answers the topic from the vault (verified, with its sources), not remembered
 2 the scenes    the model turns the answer into 5-7 scenes: what Aurora says (only the answer's facts) and a picture
                 prompt (an illustration: no text, no real people)
 3 the check     every sentence said is checked against the answer; the ones it does not support are cut
 4 the pictures  SDXL-Lightning, portrait, all in one GPU swap (mdl_image.paint_many)
 5 the voice     Piper (mdl_tts), one clip per scene
 6 the montage   ffmpeg: a slow zoom on each picture for its words, Aurora's face to open and close, subtitles, the
                 visible label and the AI metadata (EU AI Act art. 50); under the voice, low, a piece of classical music
                 chosen by the topic's mood (config/story_music.json: only free recordings, credited in the post)
The video and its post (the sources and the disclosure) are kept in the user's pictures folder, stories/. Publishing
stays the owner's (kno_social).
"""
from __future__ import annotations

import hashlib
import io
import json
import random
import re
import subprocess
import time
import wave
from pathlib import Path

from . import sys_config, sys_disclosure, sys_log

FACE = Path(__file__).resolve().parents[1] / "webui" / "assets" / "aurora_face.png"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
W, H, FPS = 1080, 1920, 30
PAINT_SIZE = "768x1344"                       # SDXL's portrait size, scaled to the video
OPEN = "Ciao, sono Aurora."
CLOSE = "Le fonti sono nella descrizione. Alla prossima!"

SYS_SCENES = ("You turn the ANSWER below into the script of a short vertical video (60-90 seconds) narrated by Aurora, "
              "an AI scientist, in Italian. Write 5 to 7 scenes as a JSON list: [{\"say\": \"...\", \"image\": \"...\"}]. "
              "say: what Aurora says in that scene, 1 to 3 short spoken sentences in Italian, only facts stated in the "
              "ANSWER (no number, name or claim that is not in it), no citation marks like [1]; the first scene opens "
              "with a question or a surprising fact from the answer, the last one closes the idea. image: an English "
              "prompt for an artistic illustration of that scene: a concrete visual subject, a style (for example "
              "cinematic digital painting, soft volumetric light), vertical composition; no text, no letters, no "
              "logos, no real people. Output only the JSON.")
MUSIC_VOLUME = 0.13                           # under the voice: heard, never covering a word
CATALOG = Path(__file__).resolve().parents[1] / "config" / "story_music.json"
SYS_MOOD = ("Choose the background music's mood for a short video on the TOPIC below. Moods: {moods}. Reply with one "
            "word: the mood.")
SYS_CHECK = ("For each numbered SENTENCE, decide whether the ANSWER states it (the same fact in other words is fine). "
             "Reply with the numbers of the sentences the ANSWER does NOT support, comma separated, or NONE.")


def _json_list(text: str) -> list:
    a, b = text.find("["), text.rfind("]")
    try:
        return json.loads(text[a:b + 1]) if a >= 0 and b > a else []
    except ValueError:
        return []


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def scenes(llm, answer: str) -> list[dict]:
    """The scenes the model writes, cleaned: {"say", "image"} with both present."""
    raw = _json_list(llm.complete(SYS_SCENES, f"ANSWER:\n{answer[:6000]}", 1800).answer)
    out = []
    for s in raw:
        if isinstance(s, dict) and str(s.get("say", "")).strip() and str(s.get("image", "")).strip():
            say = re.sub(r"\s*\[\d+(?:[,\s]*\d+)*\]", "", str(s["say"])).strip()
            out.append({"say": say, "image": str(s["image"]).strip()})
    return out[:7]


def check(llm, answer: str, items: list[dict]) -> tuple[list[dict], list[str]]:
    """Cut every sentence the answer does not support; a scene left with nothing to say goes. (scenes, cut)."""
    flat = [(i, s) for i, it in enumerate(items) for s in _sentences(it["say"])]
    if not flat:
        return [], []
    listing = "\n".join(f"{n}. {s}" for n, (_, s) in enumerate(flat, 1))
    out = llm.complete(SYS_CHECK, f"ANSWER:\n{answer[:6000]}\n\nSENTENCES:\n{listing}", 60).answer
    bad = set() if "NONE" in out.upper() else {int(x) for x in re.findall(r"\d+", out)}
    keep: dict[int, list[str]] = {}
    cut = []
    for n, (i, s) in enumerate(flat, 1):
        (cut.append(s) if n in bad else keep.setdefault(i, []).append(s))
    return [{**it, "say": " ".join(keep[i])} for i, it in enumerate(items) if i in keep], cut


def catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def music_dir(cfg: sys_config.Config) -> Path:
    from . import sys_users_layout
    return sys_users_layout.place(cfg, "music", None) / "story"         # the admin's: one set for every user


def track_name(t: dict) -> str:
    return f"{t['mood']}-{hashlib.sha256(t['file'].encode()).hexdigest()[:10]}.ogg"


def mood(llm, topic: str, answer: str) -> str:
    moods = catalog()["moods"]
    out = llm.complete(SYS_MOOD.format(moods="; ".join(f"{k} ({v})" for k, v in moods.items())),
                       f"TOPIC: {topic}\n\n{answer[:1500]}", 5).answer.strip().lower()
    return next((m for m in moods if m in out), "calm")


def pick_music(cfg: sys_config.Config, wanted: str) -> tuple[Path, dict] | None:
    """A downloaded track of that mood (any other mood when none), or None: the video goes without music."""
    have = [(music_dir(cfg) / track_name(t), t) for t in catalog()["tracks"]]
    have = [(p, t) for p, t in have if p.is_file()]
    same = [x for x in have if x[1]["mood"] == wanted]
    return random.choice(same or have) if have else None


def _seconds(wav: bytes) -> float:
    with wave.open(io.BytesIO(wav)) as w:
        return w.getnframes() / float(w.getframerate())


def _ff(args: list[str], timeout: int = 600) -> None:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], capture_output=True, text=True,
                       timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg: {r.stderr.strip()[-500:]}")


def _clip(picture: Path, wav: Path, seconds: float, out: Path) -> None:
    """One scene: the picture with a slow zoom for as long as its words, fading in and out."""
    frames = int(seconds * FPS)
    v = (f"[0:v]scale={W * 3 // 2}:{H * 3 // 2}:force_original_aspect_ratio=increase,crop={W * 3 // 2}:{H * 3 // 2},"
         f"zoompan=z='min(zoom+0.0006,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},"
         f"fade=t=in:st=0:d=0.4,fade=t=out:st={seconds - 0.4:.2f}:d=0.4,format=yuv420p[v];[1:a]apad[a]")
    _ff(["-loop", "1", "-t", f"{seconds:.2f}", "-i", str(picture), "-i", str(wav), "-filter_complex", v,
         "-map", "[v]", "-map", "[a]", "-t", f"{seconds:.2f}", "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "20", "-c:a", "aac", "-ar", "44100", "-ac", "1", str(out)])


def _ts(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def subtitles(parts: list[tuple[str, float]]) -> str:
    """SRT: each scene's sentences shown in turn, their time shared by length."""
    out, t, n = [], 0.0, 1
    for say, seconds in parts:
        lines = _sentences(say) or [say]
        total = sum(len(s) for s in lines) or 1
        for s in lines:
            d = seconds * len(s) / total
            out.append(f"{n}\n{_ts(t)} --> {_ts(t + d)}\n{s}\n")
            t, n = t + d, n + 1
    return "\n".join(out)


def _post(topic: str, items: list[dict], sources: list[dict], cfg: sys_config.Config, music: dict | None = None) -> str:
    names = list(dict.fromkeys((s.get("title") or s.get("source") or "").strip() for s in sources))
    body = f"{topic}\n\n{items[0]['say']}" + ("\n\nFonti:\n" + "\n".join(f"• {n}" for n in names if n) if names else "")
    if music:
        body += f"\n\nMusica: {music['credit']} ({music['license']}, Wikimedia Commons)"
    return sys_disclosure.mark_text(body, "it", cfg)


def stories(cfg: sys_config.Config, n: int = 12) -> list[dict]:
    """The latest videos made, newest first: {"stamp", "video", "topic", "post", "length_s", "music"}."""
    root = cfg.path("AURORA_IMAGE_DIR") / "stories"
    out = []
    for d in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True) if root.is_dir() else []:
        video = next(iter(sorted(d.glob("aurora*.mp4"))), None)
        if not video:
            continue
        try:
            meta = json.loads((d / "script.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        post = (d / "post.txt").read_text(encoding="utf-8") if (d / "post.txt").is_file() else ""
        out.append({"stamp": d.name, "video": video.name, "topic": meta.get("topic", ""), "post": post,
                    "length_s": meta.get("length_s"), "music": meta.get("music")})
        if len(out) >= n:
            break
    return out


def make(pipeline, cfg: sys_config.Config, topic: str, emit, out_root: Path | None = None, accept=None) -> dict:
    """The whole video for `topic`. Raises ValueError when the vault does not answer it (no video without sources),
    or when `accept(answer)` says why not (the scheduled videos: public sources only) — before any picture is made."""
    from . import mdl_image, mdl_tts
    log = sys_log.get_logger("image")
    t0, took = time.time(), {}
    ans = pipeline.run(topic, emit, None, remember=False)
    if ans.abstained or ans.mode != "knowledge" or not ans.sources:
        raise ValueError("il vault non risponde a questo argomento: nessun video senza fonti")
    if accept and (why := accept(ans)):
        raise ValueError(why)
    took["answer"] = round(time.time() - t0, 1)
    t = time.time()
    items = scenes(pipeline.llm, ans.text)
    items, cut = check(pipeline.llm, ans.text, items)
    if len(items) < 3:
        raise ValueError(f"copione troppo corto dopo il controllo ({len(items)} scene, {len(cut)} frasi tolte)")
    took["script"] = round(time.time() - t, 1)
    emit("story.script", {"scenes": len(items), "cut": cut})
    stamp = time.strftime("%Y%m%d-%H%M%S")
    folder = (out_root or cfg.path("AURORA_IMAGE_DIR") / "stories") / stamp
    folder.mkdir(parents=True, exist_ok=True)
    t = time.time()
    painted = mdl_image.paint_many([it["image"] for it in items], folder, cfg, emit, size=PAINT_SIZE, title=topic[:80])
    took["pictures"] = round(time.time() - t, 1)
    t = time.time()
    shots = [(FACE, OPEN)] + [(f, it["say"]) for f, it in zip(painted["files"], items)] + [(FACE, CLOSE)]
    clips, parts = [], []
    for n, (picture, say) in enumerate(shots, 1):
        wav = mdl_tts.speak(cfg, say, "it", use="video")      # on the CPU: the GPU stays the answers' (C173)
        (folder / f"voice-{n}.wav").write_bytes(wav)
        seconds = _seconds(wav) + 0.6
        clip = folder / f"clip-{n}.mp4"
        _clip(picture, folder / f"voice-{n}.wav", seconds, clip)
        clips.append(clip)
        parts.append((say, seconds))
    took["voice_and_clips"] = round(time.time() - t, 1)
    t = time.time()
    (folder / "clips.txt").write_text("".join(f"file '{c.name}'\n" for c in clips), encoding="utf-8")
    _ff(["-f", "concat", "-safe", "0", "-i", str(folder / "clips.txt"), "-c", "copy", str(folder / "joined.mp4")])
    (folder / "subs.srt").write_text(subtitles(parts), encoding="utf-8")
    on = sys_disclosure._on(cfg)
    vf = (f"subtitles={folder / 'subs.srt'}:force_style='FontName=DejaVu Sans,FontSize=12,Bold=1,Outline=2,"
          "Alignment=2,MarginV=70'")
    if on and cfg["AURORA_AI_IMAGE_LABEL"]:
        vf += (f",drawtext=fontfile={FONT}:text='Generato con IA · Aurora':x=w-tw-30:y=40:fontsize=30:"
               "fontcolor=white@0.85:box=1:boxcolor=black@0.35:boxborderw=10")
    meta = ["-metadata", f"title={topic[:120]}", "-metadata", "encoder_tool=Aurora"]
    if on:
        meta += ["-metadata", f"comment={sys_disclosure._line(cfg, 'it')}", "-metadata", f"description={sys_disclosure.IPTC_AI}"]
    video = folder / f"aurora-{stamp}.mp4"            # a name of its own: the social plugins find a video by its name
    feel = mood(pipeline.llm, topic, ans.text)
    music = pick_music(cfg, feel)
    length = sum(s for _, s in parts)
    if music:                                         # low under the voice, fading in and out; looped if short
        audio = ["-stream_loop", "-1", "-i", str(music[0]), "-filter_complex",
                 f"[0:v]{vf}[v];[1:a]volume={MUSIC_VOLUME},afade=t=in:st=0:d=1.5,afade=t=out:st={max(0.0, length - 3):.2f}:d=3[m];"
                 "[0:a][m]amix=inputs=2:duration=first:normalize=0[a]", "-map", "[v]", "-map", "[a]", "-c:a", "aac", "-b:a", "160k"]
    else:
        audio = ["-vf", vf, "-c:a", "copy"]
    _ff(["-i", str(folder / "joined.mp4"), *audio, *meta, "-c:v", "libx264", "-preset", "medium", "-crf", "21",
         "-movflags", "+faststart", str(video)])
    took["montage"] = round(time.time() - t, 1)
    post = _post(topic, items, ans.sources, cfg, music[1] if music else None)
    (folder / "post.txt").write_text(post, encoding="utf-8")
    (folder / "script.json").write_text(json.dumps({"topic": topic, "scenes": items, "cut": cut, "answer": ans.text,
                                                    "sources": ans.sources, "seconds": took, "length_s": round(length, 1),
                                                    "music": music[1]["credit"] if music else None},
                                                   ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    for f in [*clips, folder / "joined.mp4", folder / "clips.txt", *folder.glob("voice-*.wav")]:
        f.unlink(missing_ok=True)                     # the parts: the video, its pictures, script and post stay
    out = {"video": str(video), "folder": str(folder), "post": post, "scenes": len(items), "cut": len(cut),
           "mood": feel, "music": music[1]["credit"] if music else None,
           "length_s": round(sum(s for _, s in parts), 1), "seconds": {**took, "total": round(time.time() - t0, 1)},
           "pictures": {k: painted.get(k) for k in ("load_s", "paint_s", "swap")}}
    log.info("story %s: %s", stamp, {k: v for k, v in out.items() if k != "post"})
    emit("story.done", {k: v for k, v in out.items() if k != "post"})
    return out

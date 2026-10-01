# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Aurora watches a video: what is seen over time and what is said, with timestamps.

 frames      ffmpeg finds the scene changes (and adds evenly spaced moments when there are few), at most
             AURORA_VIDEO_FRAMES, each scaled to AURORA_VISION_MAX_PX and labelled with its time
 vision      ONE call to the reasoner with all the frames in order: a line per moment and the whole story
 speech      the audio track through the local Whisper, in 30 s windows, with timestamps; Whisper's
             inventions on silence are dropped (sns_av.clear_speech)
 passages    the visual account and the transcript become citable passages for this question only
             (an observation, like an attached image: not written to the vault)
Only the first AURORA_VIDEO_MAX_S seconds are watched. Nothing leaves the machine.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
from pathlib import Path

from . import sys_config, sys_log

VIDEO_EXT = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v", ".3gp", ".mpeg", ".mpg", ".ogv"}
WATCH = ("These are frames of one video, in order, each preceded by its time. Describe what happens over time, "
         "in {lang}: first one line per frame starting with its time like [01:05], then a short paragraph on the "
         "whole video (setting, people, actions, changes). Transcribe exactly any visible text, number or chart. "
         "Describe only what is visible; do not guess who people are.")


def is_video(name: str, mime: str = "") -> bool:
    return mime.startswith("video/") or Path(name).suffix.lower() in VIDEO_EXT


def mmss(t: float) -> str:
    t = int(round(t))
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60:02d}:{t % 60:02d}"


def probe(path: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise ValueError(f"not a readable video: {r.stderr.strip()[-200:]}")
    j = json.loads(r.stdout)
    video = next((s for s in j.get("streams", []) if s.get("codec_type") == "video"), None)
    if video is None:
        raise ValueError("no video track")
    return {"duration": float(j.get("format", {}).get("duration") or video.get("duration") or 0),
            "width": int(video.get("width") or 0), "height": int(video.get("height") or 0),
            "audio": any(s.get("codec_type") == "audio" for s in j.get("streams", []))}


def pick_times(scenes: list[float], duration: float, n: int) -> list[float]:
    """At most n moments: the start and the scene changes first (two within 1 s are one), spread over the video
    when they are too many; otherwise evenly spaced fillers, the farthest from what is kept, up to n
    (pure: tested offline)."""
    end = max(duration - 0.1, 0.0)
    kept: list[float] = []
    for t in sorted({0.0, *[t for t in scenes if 0 < t < end]}):
        if not kept or t - kept[-1] >= 1.0:
            kept.append(t)
    if len(kept) >= n:
        return [kept[round(i * (len(kept) - 1) / (n - 1))] for i in range(n)] if n > 1 else kept[:1]
    step = duration / n if duration > 0 else 0
    fillers = [round(i * step + step / 2, 2) for i in range(n)]
    while len(kept) < n and fillers:
        far = max(fillers, key=lambda t: min(abs(t - k) for k in kept))
        fillers.remove(far)
        if min(abs(far - k) for k in kept) >= 1.0 and far <= end:
            kept.append(far)
    return sorted(kept)


def cuts(scores: list[tuple[float, float]]) -> list[float]:
    """Scene changes from (time, scene score): a high score, or a peak well above the video's own median. ffmpeg's
    score follows brightness, so a cut between two colours of the same brightness scores low (0.09 against a
    median of 0.00002 in M48) and a fixed threshold misses it (pure: tested offline)."""
    if not scores:
        return []
    ordered = sorted(s for _, s in scores)
    median = ordered[len(ordered) // 2]
    return [t for t, s in scores if s >= 0.30 or (s >= 0.06 and s >= 8 * median)]


def scene_changes(path: Path, seconds: float) -> list[float]:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-t", str(seconds), "-i", str(path), "-an",
                        "-vf", "scale=320:-2,select='gt(scene,0)',metadata=print", "-f", "null", "-"],
                       capture_output=True, text=True, timeout=max(120, seconds * 2))
    # metadata=print writes two lines per frame, each with its "[Parsed_metadata_N @ ...]" prefix
    pairs = re.findall(r"pts_time:([0-9.]+)[^\n]*\n[^\n]*?lavfi\.scene_score=([0-9.]+)", r.stderr)
    return cuts([(float(t), float(sc)) for t, sc in pairs])


def frame(path: Path, t: float, max_px: int) -> bytes:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(path),
                        "-frames:v", "1", "-vf", f"scale='min({max_px},iw)':-2", "-f", "image2", "-c:v", "mjpeg",
                        "-q:v", "4", "pipe:1"], capture_output=True, timeout=60)
    return r.stdout


def watch(data: bytes, name: str, lang: str, llm, cfg: sys_config.Config | None = None, emit=None) -> dict:
    """{"duration", "width", "height", "frames": [time], "visual": text, "speech": [(start, end, text)], "seconds"}"""
    from . import sns_av
    cfg = cfg or sys_config.get()
    ev = emit or (lambda e, d: None)
    log = sys_log.get_logger("attach")
    t0 = time.time()
    with tempfile.NamedTemporaryFile(prefix="aurora-video-", suffix=Path(name).suffix or ".mp4") as f:
        f.write(data)
        f.flush()
        path = Path(f.name)
        info = probe(path)
        seconds = min(info["duration"] or cfg["AURORA_VIDEO_MAX_S"], cfg["AURORA_VIDEO_MAX_S"])
        scenes = scene_changes(path, seconds)
        times = pick_times(scenes, seconds, cfg["AURORA_VIDEO_FRAMES"])
        from .kno_attach import to_jpeg               # 32-px tiles, or the vision sees black bands (C67)
        shots = [(t, frame(path, t, cfg["AURORA_VISION_MAX_PX"])) for t in times]
        shots = [(t, to_jpeg(j, cfg["AURORA_VISION_MAX_PX"])) for t, j in shots if j]
        ev("video.frames", {"name": name, "duration": round(info["duration"], 1), "scenes": len(scenes),
                            "frames": [mmss(t) for t, _ in shots]})
        visual = llm.see_many([(mmss(t), j) for t, j in shots], WATCH.format(lang=lang), max_tokens=1600) if shots else ""
        speech: list[tuple[float, float, str]] = []
        if info["audio"]:
            audio = sns_av.decode(path.read_bytes(), cfg, max_s=seconds)
            speech = sns_av.transcribe_segments(audio, "it" if lang == "Italian" else "en", cfg)
    out = {**info, "watched_s": round(seconds, 1), "frames": [t for t, _ in shots], "scenes": len(scenes),
           "visual": visual, "speech": speech, "seconds": round(time.time() - t0, 1)}
    log.info("watched %s: %.0f s of %.0f, %d scene changes, %d frames, %d speech segments in %.1f s", name, seconds,
             info["duration"], len(scenes), len(shots), len(speech), out["seconds"])
    return out


def passages(w: dict, name: str) -> list[str]:
    """The observation as passages: the visual account, then the transcript in pieces of about 1500 characters."""
    head = (f"VIDEO «{name}»: {mmss(w['duration'])} ({w['width']}x{w['height']}), watched {mmss(w['watched_s'])}, "
            f"{len(w['frames'])} frames.")
    out = [f"{head}\nWHAT IS SEEN:\n{w['visual']}"] if w["visual"] else [head]
    piece = ""
    for start, end, text in w["speech"]:
        line = f"[{mmss(start)}–{mmss(end)}] {text}"
        if piece and len(piece) + len(line) > 1500:
            out.append(f"VIDEO «{name}», WHAT IS SAID:\n{piece}")
            piece = ""
        piece = f"{piece}\n{line}" if piece else line
    if piece:
        out.append(f"VIDEO «{name}», WHAT IS SAID:\n{piece}")
    elif w.get("audio"):
        out.append(f"VIDEO «{name}», WHAT IS SAID: no clear speech in the audio track.")
    return out

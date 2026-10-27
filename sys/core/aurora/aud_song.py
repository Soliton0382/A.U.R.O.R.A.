# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A song from an idea (owner, 2026-10-27: «la generazione di audio partendo da una idea e una descrizione (del tipo
una canzone stile female vocalist trance stile anni 90 basata sul testo della divina commedia e cantata in inglese)»).

Two steps. The local reasoner turns the idea into a song: a title, a style caption for the music model (genre, era,
voice, instruments, mood, tempo), and lyrics in the language asked, with [verse]/[chorus]/[bridge] marks (the user's
own lyrics when given). Then the music model — ACE-Step 1.5 (MIT), installed by the owner in AURORA_SONG_DIR with its
weights in AURORA_SONG_MODELS — sings it. The two do not share the GPU (owner: «se si sta usando Qwen viene scaricato
dalla vram… una volta che ha finito si ricarica il modello locale, come avviene per la fase rem»): under the GPU lock
the reasoner (aurora-llm) is stopped, ACE-Step's own API server is started on 127.0.0.1 with a key of the moment,
asked for the song, and stopped; the reasoner is started again whatever happened (mdl_image's swap). The result is an
MP3 in the user's mixes, tagged as made by an AI, with its lyrics and caption beside it (<name>.song.json).
"""
from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import time
from pathlib import Path

import httpx

from . import mdl_image, sys_config, sys_log

WRITER = ("You write songs. From the idea given, reply with JSON only: {\"title\": short title, \"caption\": the music "
          "described for a music model in English, comma separated (genre and era, the singer's voice, instruments, mood, "
          "tempo in BPM), \"lyrics\": the lyrics in the LANGUAGE given, with section marks on their own lines — [verse], "
          "[chorus], [bridge], [outro] — two verses, a chorus repeated, singable lines}. When the idea draws on a text, "
          "the lyrics retell it in new words: never copy a modern author's lines. The idea:\n")
LANGS = {"en": "English", "it": "Italian", "es": "Spanish", "fr": "French", "de": "German", "pt": "Portuguese",
         "ja": "Japanese", "zh": "Chinese", "ko": "Korean"}


def installed(cfg: sys_config.Config) -> dict:
    """Whether the music model is there: its folder and its weights (the page says what is missing)."""
    home, models = cfg.path("AURORA_SONG_DIR"), cfg.path("AURORA_SONG_MODELS")
    return {"code": (home / "pyproject.toml").is_file(), "weights": models.is_dir() and any(models.iterdir()),
            "dir": str(home), "models": str(models)}


def write(llm, idea: str, lang: str = "en", lyrics: str = "", style: dict | None = None) -> dict:
    """The reasoner's song: {"title", "caption", "lyrics"} and the dress chosen (aud_song_style: genre, arrangement,
    voice, tempo, key, boldness — the caption built on them, their tags always in it); the user's lyrics kept."""
    from . import aud_song_style
    language = LANGS.get(lang, "English")
    r = aud_song_style.resolve(style)
    must = f"\n\nSTYLE CHOSEN BY THE OWNER (build the caption on it): {r['brief']}" if r["brief"] else ""
    if r["instrumental"]:
        must += "\nInstrumental: no vocals; the lyrics field is only «[instrumental]»."
    raw = llm.complete(WRITER.replace("LANGUAGE", language), f"{idea}\n\nLANGUAGE: {language}" + must
                       + (f"\n\nUse these lyrics as they are:\n{lyrics}" if lyrics else ""), 1600).answer
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        song = json.loads(m.group(0)) if m else {}
    except ValueError:
        song = {}
    if not song.get("caption") or not (song.get("lyrics") or lyrics):
        raise RuntimeError("the reasoner did not write the song (no caption or lyrics)")
    words = "[instrumental]" if r["instrumental"] else (lyrics or str(song["lyrics"])).strip()[:6000]
    return {"title": str(song.get("title") or idea[:40]).strip()[:80],
            "caption": aud_song_style.dress(str(song["caption"]).strip(), r["tags"]), "lyrics": words, "language": lang,
            "style": aud_song_style.check(style),
            **{k: r[k] for k in ("bpm", "key_scale", "lm_temperature", "negative") if k in r}}


LMS = ("acestep-5Hz-lm-1.7B", "acestep-5Hz-lm-0.6B", "acestep-5Hz-lm-4B")   # its planner: the one downloaded


def inside(root) -> dict[str, str]:
    """Every cache and every Python of uv and of ACE-Step inside Aurora's folder (owner, 27 Oct: «tutto dentro la
    cartella di installazione di aurora e non in giro per il sistema»): the installer (sys_song_install.sh) and the
    singing server get the same."""
    rt = Path(root) / "sys" / "runtime"
    ace = rt / "ace-step" / ".cache"
    return {"UV_CACHE_DIR": str(rt / "uv" / "cache"), "UV_PYTHON_INSTALL_DIR": str(rt / "uv" / "python"),
            "UV_PYTHON_PREFERENCE": "only-managed", "UV_TOOL_DIR": str(rt / "uv" / "tools"), "UV_NO_CONFIG": "1",
            "XDG_CACHE_HOME": str(ace), "HF_HOME": str(ace / "huggingface"), "MODELSCOPE_CACHE": str(ace / "modelscope"),
            "TRITON_CACHE_DIR": str(ace / "triton"), "TORCHINDUCTOR_CACHE_DIR": str(ace / "inductor"),
            "ACESTEP_TMPDIR": str(ace / "tmp")}


def command(cfg: sys_config.Config) -> list[str]:
    """AURORA_SONG_CMD with its program found: the services' PATH lacks the user's own folders, where uv installs
    itself (~/.local/bin, ~/.cargo/bin) — the first song failed on «No such file or directory: 'uv'»."""
    import shutil
    words = str(cfg["AURORA_SONG_CMD"]).split()
    own = cfg.root / "sys" / "runtime" / "uv" / "bin" / "uv"     # the one sys_song_install.sh put inside Aurora
    if words and words[0] == "uv" and own.is_file():
        words[0] = str(own)
    if words and not Path(words[0]).is_absolute():
        home = Path.home()
        found = shutil.which(words[0]) or next((str(p) for p in (home / ".local/bin" / words[0], home / ".cargo/bin" / words[0])
                                                if p.is_file()), None)
        if found:
            words[0] = found
    return words


def _server(cfg: sys_config.Config, key: str, port: int) -> subprocess.Popen:
    models = cfg.path("AURORA_SONG_MODELS")
    lm = next((m for m in LMS if (models / m).is_dir()), "")
    env = {**os.environ, **inside(cfg.root), "ACESTEP_API_HOST": "127.0.0.1", "ACESTEP_API_PORT": str(port), "ACESTEP_API_KEY": key,
           "ACESTEP_CHECKPOINTS_DIR": str(models), "ACESTEP_LM_BACKEND": "pt",
           # its whole path: ACE-Step joins a name to its own checkpoints/ folder, not to ACESTEP_CHECKPOINTS_DIR
           **({"ACESTEP_LM_MODEL_PATH": str(models / lm)} if lm else {}),
           "HF_HUB_OFFLINE": "1"}                       # the weights are the owner's download: nothing fetched here
    cfg.path("AURORA_LOG_DIR").mkdir(parents=True, exist_ok=True)
    log = open(cfg.path("AURORA_LOG_DIR") / "song.log", "ab")
    return subprocess.Popen(command(cfg), cwd=cfg.path("AURORA_SONG_DIR"), env=env,
                            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)


def sing(cfg: sys_config.Config, song: dict, seconds: int, out: Path, emit=None) -> dict:
    """ACE-Step sings the song into `out` (an MP3), the reasoner out of the GPU meanwhile. Returns what was done."""
    from . import aud_analysis as A
    say = emit or (lambda e, p: None)
    log = sys_log.get_logger("song")
    have = installed(cfg)
    if not (have["code"] and have["weights"]):
        raise RuntimeError(f"the music model is not installed (code in {have['dir']}, weights in {have['models']})")
    limit = float(cfg["AURORA_SONG_TIMEOUT_S"])
    port, key = int(cfg["AURORA_SONG_PORT"]), secrets.token_urlsafe(24)
    t0, swapped, proc = time.time(), False, None
    with mdl_image.gpu_lock(cfg, limit, f"song {out.stem}"):
        try:
            if mdl_image._active(mdl_image.LLM_UNIT):        # the reasoner out of the GPU, as for a dream
                say("song.swap", {"stop": mdl_image.LLM_UNIT})
                mdl_image._unit("stop", mdl_image.LLM_UNIT)
                swapped = True
            proc = _server(cfg, key, port)
            base, head = f"http://127.0.0.1:{port}", {"Authorization": f"Bearer {key}"}

            def up() -> bool:
                if proc.poll() is not None:
                    raise RuntimeError(f"the music model stopped at start (code {proc.returncode}): see song.log")
                try:
                    return httpx.get(f"{base}/v1/models", headers=head, timeout=5).status_code == 200
                except httpx.HTTPError:
                    return False
            say("song.start", {})
            if not mdl_image._wait(up, min(limit, 600), 3):
                raise RuntimeError("the music model did not answer in time: see song.log")
            r = httpx.post(f"{base}/release_task", headers=head, timeout=60, json={
                "prompt": song["caption"], "lyrics": song["lyrics"], "audio_duration": int(seconds),
                "vocal_language": song["language"], "audio_format": "mp3", "batch_size": 1,
                "thinking": bool(cfg["AURORA_SONG_THINKING"]),
                # the dress's own fields (aud_song_style): the tempo, the key, how bold the planner is
                **{k: song[k] for k in ("bpm", "key_scale", "lm_temperature") if song.get(k) is not None},
                # the mix's elements left out (aud_song_style): what the planner must not put in
                **({"lm_negative_prompt": song["negative"]} if song.get("negative") else {})})
            r.raise_for_status()
            task = r.json()["data"]["task_id"]
            say("song.sing", {"task": task})
            end, got = time.time() + limit, None
            while time.time() < end:
                q = httpx.post(f"{base}/query_result", headers=head, timeout=30, json={"task_id_list": [task]}).json()
                item = (q.get("data") or [{}])[0]
                if item.get("status") == 2:
                    raise RuntimeError(f"the music model failed: {str(item.get('result') or '')[:200]}")
                if item.get("status") == 1:
                    res = item.get("result")
                    res = json.loads(res) if isinstance(res, str) else res
                    got = (res[0] if isinstance(res, list) else res)["file"]
                    break
                time.sleep(3)
            if not got:
                raise RuntimeError("the song was not ready in time")
            raw = out.with_suffix(".raw.mp3")
            data = httpx.get(got if got.startswith("http") else base + got, headers=head, timeout=120)
            data.raise_for_status()
            raw.write_bytes(data.content)
            A.save(A.load(raw), out, title=f"{song['title']} (AI)", made="AI-generated song")  # levelled and tagged as made by an AI
            raw.unlink(missing_ok=True)
        finally:
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(30)
                except subprocess.TimeoutExpired:
                    proc.kill()
            if swapped:
                mdl_image._unit("start", mdl_image.LLM_UNIT)
                ok = mdl_image._wait(lambda: mdl_image._llm_ok(cfg), 600, 3)
                log.info("song: %s started again (%s)", mdl_image.LLM_UNIT, "healthy" if ok else "NOT healthy yet")
                say("song.swap", {"start": mdl_image.LLM_UNIT, "healthy": ok})
    out.with_suffix(".song.json").write_text(json.dumps({**song, "seconds": seconds}, ensure_ascii=False, indent=1),
                                             encoding="utf-8")
    return {"file": out.name, "title": song["title"], "seconds": round(time.time() - t0, 1), "swap": swapped}

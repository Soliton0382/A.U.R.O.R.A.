# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A demo video of Aurora, recorded by a script (ROADMAP N76; owner, 6 Nov 2026: «una demo video pilotata da te»).

A headless browser drives the WebUI along a storyboard (JSON: chapters of steps), the frames are captured from the
browser itself (lossless enough for text), captions and title cards are drawn in the page (dev_demo_overlay.js), and
ffmpeg joins the chapters into one MP4. The machine's own data never reaches a frame: every text shown passes through
the overlay's mask (addresses, the installation's own words, e-mails, MAC), every write the storyboard did not allow is
refused before it leaves the browser, and at the end each frame is read back (OCR) and the video is refused if one
still shows an address or a private word.

Two steps, two interpreters:
    .venv/bin/python sys/core/script/dev_demo_video.py words             # Aurora's: the words to mask, privately
    <demo venv>/bin/python sys/core/script/dev_demo_video.py record story.json [--only id] [--out dir]
    <demo venv>/bin/python sys/core/script/dev_demo_video.py check <dir>  # OCR of a finished recording again
    <demo venv>/bin/python sys/core/script/dev_demo_video.py join story.json [--music track.mp3] [--volume 0.18]

The demo venv holds Playwright (pip install playwright) and uses the system's Chrome: never Aurora's dependencies.
Private files (mode 600) under ~/.config/aurora: demo_mask.json (the words), demo_user.json (the test user's
login), demo_admin_state.json (the admin's registered browser).
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIV = Path.home() / ".config" / "aurora"
MASK_FILE, USER_FILE, ADMIN_STATE = PRIV / "demo_mask.json", PRIV / "demo_user.json", PRIV / "demo_admin_state.json"
KEEP_RUNS = PRIV / "demo_keep_runs.json"               # the test user's runs a later chapter recalls: never forgotten
USER_STATE = PRIV / "demo_user_state.json"             # the test user's browser, kept: one device, not one per run
BASE_URL = os.environ.get("DEMO_BASE_URL", "http://localhost:9700")   # not a setting: the recorder's own
W, H, FPS = 1920, 1080, 30
IPV4 = re.compile(r"\b(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}\b")
SAFE_IP = ("127.0.0.1", "0.0.0.0", "203.0.113.", "198.51.100.", "192.0.2.", "255.255.255.")


def _private_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


# ---- step 1, with Aurora's interpreter: what must never be seen ----------------------------------------------------
def cmd_words(_args) -> int:
    """The installation's own words (the same sources as the cloud mask) with what stands in for each in the video."""
    sys.path.insert(0, str(HERE.parent))
    import socket

    from aurora import sec_mask, sys_config
    cfg = sys_config.get()
    p = sec_mask.Pseudonymizer(cfg)
    stand = {}
    owner = str(cfg.values.get("AURORA_OWNER_NAME") or "").strip()
    domain = str(cfg.values.get("AURORA_DOMAIN") or "").strip()
    if domain:
        stand[domain] = "aurora.example.org"
        if domain.count(".") >= 1:
            stand[".".join(domain.split(".")[-2:])] = "example.org"
    for w in owner.split():
        stand[w] = "Alex"
    for w in list(p.private) + list(p.words):
        stand.setdefault(w, "•••")
    try:
        from aurora.sys_users import Users
        for u in Users(cfg.base or cfg).list():
            if u["name"] not in ("demo",) and len(u["name"]) >= 3 and u["name"].lower() not in sec_mask.COMMON:
                stand.setdefault(u["name"], "user")
    except Exception:                                    # noqa: BLE001 — no users: nothing to add
        pass
    extra = PRIV / "demo_mask_extra.txt"                 # the owner's own additions, one per line
    if extra.exists():
        for line in extra.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#"):
                stand.setdefault(line.strip(), "•••")
    deny = PRIV / "publish_deny.txt"
    if deny.exists():
        for line in deny.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#"):
                stand.setdefault(line.strip(), "•••")
    host = socket.gethostname()
    stand.setdefault(host, "aurora-host")
    stand.setdefault(f"/home/{Path.home().name}", "/home/aurora")
    stand.setdefault(f"usr/{Path.home().name}/", "usr/alex/")
    words = [[k, v] for k, v in stand.items() if len(k) >= 3 and k.lower() not in ("demo", "aurora")]
    _private_write(MASK_FILE, {"words": words, "keep": []})
    print(f"{len(words)} words to mask written to {MASK_FILE} (mode 600)")
    return 0


# ---- logins ----------------------------------------------------------------------------------------------------------
def totp(secret: str, at: float | None = None) -> str:
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    msg = struct.pack(">Q", int((at or time.time()) // 30))
    h = hmac.new(key, msg, hashlib.sha1).digest()
    o = h[-1] & 15
    return f"{(struct.unpack('>I', h[o:o + 4])[0] & 0x7FFFFFFF) % 1_000_000:06d}"


def login_user(ctx) -> None:
    """The test user: name and password from demo_user.json; the authenticator enrolled at the first login, its
    secret kept in the same file."""
    rec = json.loads(USER_FILE.read_text(encoding="utf-8"))
    body = {"name": rec["name"], "password": rec["password"], "device": "demo recorder"}
    if rec.get("totp"):
        body["code"] = totp(rec["totp"])
    r = ctx.request.post(f"{BASE_URL}/v1/aurora/login", data=body)
    if r.ok and "enroll" in (r.json() or {}):
        rec["totp"] = r.json()["enroll"]["secret"]
        _private_write(USER_FILE, rec)
        body["code"] = totp(rec["totp"])
        r = ctx.request.post(f"{BASE_URL}/v1/aurora/login", data=body)
    if not r.ok:
        raise SystemExit(f"demo user's login refused: {r.status} {r.text()[:200]}")


def wait_idle(most: float = 3600) -> None:
    """Before a chapter: no clip being made (the reasoner is off meanwhile) and no run of anyone working — a chapter
    recorded while Aurora was busy shows her saying so, not the feature (6 Nov: a whole take lost that way)."""
    import urllib.request
    key = (PRIV / "api_key.txt").read_text(encoding="utf-8").strip()
    t0 = time.monotonic()
    while time.monotonic() - t0 < most:
        clip = any("vid_ai.py" in (Path("/proc") / d / "cmdline").read_bytes().decode(errors="replace")
                   for d in os.listdir("/proc") if d.isdigit() and (Path("/proc") / d / "cmdline").exists())
        try:
            req = urllib.request.Request(f"{BASE_URL}/v1/aurora/runs/busy", headers={"Authorization": f"Bearer {key}"})
            runs = json.loads(urllib.request.urlopen(req, timeout=10).read())["open"]
        except Exception:                                # noqa: BLE001 — not known: wait
            runs = 1
        if not clip and not runs:
            return
        print(f"  waiting: {'a clip is being made' if clip else f'{runs} run(s) working'}", flush=True)
        time.sleep(30)
    raise SystemExit("Aurora stayed busy for an hour: not recorded")


def user_context(browser, opts):
    """The test user's browser: the one kept from the last login if it still works, else a new login."""
    if USER_STATE.exists():
        ctx = browser.new_context(storage_state=str(USER_STATE), **opts)
        if ctx.request.get(f"{BASE_URL}/v1/models").ok:
            return ctx
        ctx.close()
    ctx = browser.new_context(**opts)
    login_user(ctx)
    _private_write(USER_STATE, ctx.storage_state())
    return ctx


def admin_context(browser, opts):
    """The admin's browser, registered once with the API key (a device on the admin's list, revocable there)."""
    if ADMIN_STATE.exists():
        ctx = browser.new_context(storage_state=str(ADMIN_STATE), **opts)
        if ctx.request.get(f"{BASE_URL}/v1/models").ok:
            return ctx
        ctx.close()
    ctx = browser.new_context(**opts)
    key = (PRIV / "api_key.txt").read_text(encoding="utf-8").strip()
    r = ctx.request.post(f"{BASE_URL}/v1/aurora/devices", data={"name": "demo recorder"},
                         headers={"Authorization": f"Bearer {key}"})
    if not r.ok:
        raise SystemExit(f"device registration refused: {r.status}")
    state = ctx.storage_state()
    if not state.get("cookies"):                         # a Secure cookie over http://localhost: put it in by hand
        m = re.search(r"aurora_device=([^;]+)", r.headers.get("set-cookie", ""))
        if not m:
            raise SystemExit("no device cookie in the answer")
        ctx.add_cookies([{"name": "aurora_device", "value": m.group(1), "url": BASE_URL}])
        state = ctx.storage_state()
    _private_write(ADMIN_STATE, state)
    return ctx


# ---- the frames: Chrome's own screencast, timed --------------------------------------------------------------------
class Frames:
    def __init__(self, page, folder: Path):
        self.folder, self.n, self.times, self.stopped = folder, 0, [], False
        self.fast: list[tuple[float, float, float]] = []    # (from, to, speed): waits shown faster
        folder.mkdir(parents=True, exist_ok=True)
        self.cdp = page.context.new_cdp_session(page)
        self.cdp.on("Page.screencastFrame", self._frame)
        self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": W, "maxHeight": H})

    def _frame(self, ev):
        if self.stopped:                                 # frames still in flight after the stop
            return
        self.n += 1
        (self.folder / f"{self.n:06d}.jpg").write_bytes(base64.b64decode(ev["data"]))
        self.times.append(time.monotonic())
        try:
            self.cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
        except Exception:                                # noqa: BLE001 — the page is closing
            pass

    def stop(self) -> None:
        self.stopped = True
        try:
            self.cdp.send("Page.stopScreencast")
        except Exception:                                # noqa: BLE001
            pass
        self.times.append(time.monotonic())

    def _shown(self, a: float, b: float) -> float:
        """How long the stretch a..b lasts in the video: the parts inside a fast-forward divided by its speed."""
        d = b - a
        for x, y, k in self.fast:
            o = max(0.0, min(b, y) - max(a, x))
            d -= o - o / k
        return d

    def encode(self, out: Path) -> None:
        """Frames come only when the page changes: each lasts until the next one (a constant-rate video after)."""
        lst = self.folder / "frames.txt"
        with open(lst, "w", encoding="utf-8") as f:
            for i in range(self.n):
                f.write(f"file '{self.folder / f'{i + 1:06d}.jpg'}'\nduration {max(self._shown(self.times[i], self.times[i + 1]), 0.001):.3f}\n")
            if self.n:
                f.write(f"file '{self.folder / f'{self.n:06d}.jpg'}'\n")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,fps={FPS}",
                        "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", str(out)], check=True)


from dev_demo_player import Player  # noqa: E402 — the steps, in their own file


# ---- recording --------------------------------------------------------------------------------------------------------
def cmd_record(args) -> int:
    from playwright.sync_api import sync_playwright
    story = json.loads(Path(args.story).read_text(encoding="utf-8"))
    mask = json.loads(MASK_FILE.read_text(encoding="utf-8")) if MASK_FILE.exists() else None
    if not mask:
        raise SystemExit(f"{MASK_FILE} missing: run `.venv/bin/python {Path(__file__).name} words` first")
    out = Path(args.out).expanduser()
    (out / "chapters").mkdir(parents=True, exist_ok=True)
    wanted = args.only.split(",") if args.only else None     # a later chapter (recorded days after) only when named
    chapters = [c for c in story["chapters"] if (c["id"] in wanted if wanted else not c.get("later"))]
    opts = {"viewport": {"width": W, "height": H}, "device_scale_factor": 1, "locale": story.get("locale", "en-US"),
            "color_scheme": story.get("scheme", "dark")}
    made = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True, args=["--hide-scrollbars", "--force-color-profile=srgb"])
        for i, ch in enumerate(story["chapters"]):
            if ch not in chapters:
                continue
            print(f"chapter {ch['id']}: {ch.get('title', '')}")
            wait_idle()
            if ch.get("user", "admin") == "admin":
                ctx = admin_context(browser, opts)
            else:
                ctx = user_context(browser, opts)
            ctx.add_init_script(script=f"window.__DEMO_MASK = {json.dumps(mask)};"   # the interface's language: this browser's own
                                f"try {{ localStorage.setItem('aurora.lang', {json.dumps(story.get('lang', 'en_US'))}); }} catch (e) {{}}")
            ctx.add_init_script(path=str(HERE / "dev_demo_overlay.js"))
            page = ctx.new_page()
            player = Player(page, ch)
            if ch.get("keep_runs"):                      # this chapter's questions are what a later one recalls
                def kept(r, keep=keep):
                    if r.request.method == "POST" and r.url.endswith("/v1/aurora/ask") and r.ok:
                        keep.add(r.json()["run_id"])
                        _private_write(KEEP_RUNS, sorted(keep))
                page.on("response", kept)
            page.goto(BASE_URL + ch.get("start", "/"))
            page.locator("#app").wait_for(state="visible", timeout=60000)
            page.wait_for_timeout(2500)
            keep = set(json.loads(KEEP_RUNS.read_text(encoding="utf-8"))) if KEEP_RUNS.exists() else set()
            if ch.get("fresh_chat"):                     # the test user's chat starts empty: their exchanges forgotten
                for turn in ctx.request.get(f"{BASE_URL}/v1/aurora/history?n=200").json():
                    if turn.get("role") == "user" and turn.get("run_id") and turn["run_id"] not in keep:
                        ctx.request.delete(f"{BASE_URL}/v1/aurora/memory/conversation?source_id=run:{turn['run_id']}")
                page.reload()
                page.locator("#app").wait_for(state="visible", timeout=60000)
                page.wait_for_timeout(2000)
            for s in ch.get("setup", []):                # before the frames: not in the video
                player.step(s)
            if story.get("require_green"):              # the official cut: Aurora green (health ok) in every frame
                level = ctx.request.get(f"{BASE_URL}/v1/aurora/health").json().get("level")
                if level != "ok":
                    raise SystemExit(f"Aurora is «{level}», not green: sign the code and look at the Status page first")
            frames = Frames(page, out / "frames" / ch["id"])
            player.frames = frames
            page.wait_for_timeout(300)
            if ch.get("title"):                          # each chapter a small demo of its own: its label first
                page.evaluate("([t, s]) => __demo.chapter(t, s)", [ch["title"], ch.get("sub", "")])
                page.wait_for_timeout(3300)
            t0 = time.monotonic()
            try:
                for s in ch["steps"]:
                    player.step(s)
            finally:
                frames.stop()
            mp4 = out / "chapters" / f"{i:02d}-{ch['id']}.mp4"
            frames.encode(mp4)
            shutil.rmtree(out / "frames" / ch["id"], ignore_errors=True)
            print(f"  {time.monotonic() - t0:.1f} s, {frames.n} frames, refused writes: {len(player.refused)}")
            made.append(mp4)
            ctx.close()
        browser.close()
    if not args.only:
        join(out, made, story.get("music"))
    return cmd_check(argparse.Namespace(dir=str(out)))


def join(out: Path, chapters: list[Path], music: dict | None) -> Path:
    """The chapters one after the other; a soundtrack under them when the story names one (looped, faded, low)."""
    lst = out / "chapters.txt"
    lst.write_text("".join(f"file '{m}'\n" for m in chapters), encoding="utf-8")
    silent = out / "demo.silent.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                    str(silent)], check=True)
    demo = out / "demo.mp4"
    if not music:
        silent.replace(demo)
        return demo
    length = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                   str(silent)], capture_output=True, text=True, check=True).stdout)
    if music.get("parts"):                               # one track per part of the video, crossfaded where it changes
        music = {**music, "path": str(_bed(out, chapters, music))}
    vol, fade = float(music.get("volume", 0.18)), float(music.get("fade", 4))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-stream_loop", "-1",
                    "-i", str(Path(music["path"]).expanduser()), "-filter_complex",
                    f"[1:a]volume={vol},afade=t=in:d=2,afade=t=out:st={max(length - fade, 0):.2f}:d={fade}[a]",
                    "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{length:.2f}",
                    str(demo)], check=True)
    silent.unlink()
    return demo


def _dur(f: Path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)],
                                capture_output=True, text=True, check=True).stdout)


def _loop(src: Path, need: float, x: float, dst: Path) -> None:
    """`need` seconds of a track: its silent head and tail cut, and when too short its repeats crossfaded (no gap)."""
    trim = dst.with_suffix(".trim.wav")
    edge = "silenceremove=start_periods=1:start_threshold=-50dB"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-af", f"{edge},areverse,{edge},areverse",
                    "-ac", "2", "-ar", "44100", str(trim)], check=True)
    d = _dur(trim)
    n = max(1, math.ceil((need - x) / max(d - x, 1.0)))
    if n == 1:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(trim), "-t", f"{need:.2f}", str(dst)], check=True)
    else:
        chain, last = [], "[0:a]"
        for i in range(1, n):
            chain.append(f"{last}[{i}:a]acrossfade=d={x}:c1=tri:c2=tri[l{i}]")
            last = f"[l{i}]"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *sum((["-i", str(trim)] for _ in range(n)), []),
                        "-filter_complex", ";".join(chain), "-map", last, "-t", f"{need:.2f}", str(dst)], check=True)
    trim.unlink()


def _bed(out: Path, chapters: list[Path], music: dict) -> Path:
    """{"parts": [{"path", "from": chapter id}, …], "xfade": s}: each track from its chapter's start to the next part's,
    joined by crossfades into one bed as long as the video (a track too short is looped)."""
    starts, t = {}, 0.0
    for c in chapters:
        starts[c.stem.split("-", 1)[1]] = t
        t += _dur(c)
    total, x = t, float(music.get("xfade", 3))
    parts = music["parts"]
    cuts = [starts.get(p["from"], 0.0) for p in parts] + [total]
    pieces = []
    for i, p in enumerate(parts):
        need = cuts[i + 1] - cuts[i] + (x if i < len(parts) - 1 else 0)
        piece = out / f"bed-{i}.wav"
        _loop(Path(p["path"]).expanduser(), need, x, piece)
        pieces.append(piece)
    bed = out / "bed.wav"
    if len(pieces) == 1:
        pieces[0].replace(bed)
        return bed
    inputs = sum((["-i", str(pc)] for pc in pieces), [])
    chain, last = [], "[0:a]"
    for i in range(1, len(pieces)):
        tag = f"[a{i}]"
        chain.append(f"{last}[{i}:a]acrossfade=d={x}:c1=tri:c2=tri{tag}")
        last = tag
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(chain), "-map", last,
                    str(bed)], check=True)
    for pc in pieces:
        pc.unlink()
    return bed


def cmd_join(args) -> int:
    """The chapters already recorded, in the story's order, joined again (a new soundtrack, a chapter redone)."""
    story = json.loads(Path(args.story).read_text(encoding="utf-8"))
    out = Path(args.out).expanduser()
    made = []
    for i, ch in enumerate(story["chapters"]):
        found = sorted((out / "chapters").glob(f"[0-9][0-9]-{ch['id']}.mp4"), key=lambda f: f.stat().st_mtime)
        mp4 = found[-1] if found else out / "chapters" / f"{i:02d}-{ch['id']}.mp4"   # by name: the order may change
        if not mp4.exists():
            if ch.get("later"):                          # recorded days after (the memory's second half): not yet
                print(f"  left out, recorded later: {mp4.name}")
                continue
            raise SystemExit(f"chapter not recorded yet: {mp4.name}")
        made.append(mp4)
    music = story.get("music")
    if args.music:
        music = {**(music or {}), "path": args.music}
    if args.volume is not None and music:
        music["volume"] = args.volume
    demo = join(out, made, music)
    print(f"{demo}: {len(made)} chapters" + (f", music at volume {music.get('volume', 0.18)}" if music else ""))
    return cmd_check(argparse.Namespace(dir=str(out)))


# ---- the frames read back ---------------------------------------------------------------------------------------------
def cmd_check(args) -> int:
    """Every half second of every chapter read by OCR: an address or a private word left = the video refused."""
    out = Path(args.dir).expanduser()
    mask = json.loads(MASK_FILE.read_text(encoding="utf-8"))
    words = [w for w, _ in mask["words"] if len(w) >= 4]
    allow_file = PRIV / "demo_ocr_allow.json"            # per chapter, words the owner wants seen (their paper's author)
    allow = json.loads(allow_file.read_text(encoding="utf-8")) if allow_file.exists() else {}
    hits = []
    for mp4 in sorted((out / "chapters").glob("*.mp4")):
        tmp = out / "ocr" / mp4.stem
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(mp4), "-vf", "fps=2", str(tmp / "%05d.png")], check=True)
        pngs = sorted(tmp.glob("*.png"))

        def read(png):
            r = subprocess.run(["tesseract", str(png), "stdout", "--psm", "11"], capture_output=True, text=True)
            qr = ""
            try:                                         # a QR code says what no text shows: decoded = refused
                import cv2
                qr = cv2.QRCodeDetector().detectAndDecode(cv2.imread(str(png)))[0] or ""
            except Exception:                            # noqa: BLE001 — no OpenCV: text only
                pass
            return png, r.stdout + ("\n" + qr if qr else ""), bool(qr)

        with ThreadPoolExecutor(max_workers=8) as ex:
            for png, text, qr in ex.map(read, pngs):
                at = (int(png.stem) - 1) / 2
                if qr:
                    hits.append({"chapter": mp4.stem, "at_s": at, "kind": "qr code"})
                low = text.lower()
                for ip in IPV4.findall(text):
                    if not ip.startswith(SAFE_IP) and not ip.replace("6", "0").startswith(SAFE_IP):   # a slashed zero read as 6
                        hits.append({"chapter": mp4.stem, "at_s": at, "kind": "address"})
                ok = {x.lower() for cid, xs in allow.items() if mp4.stem.split("-", 1)[1] == cid for x in xs}
                for n, w in enumerate(words):
                    if w.lower() in ok:
                        continue
                    if re.search(rf"(?<!\w){re.escape(w.lower())}(?!\w)", low):
                        hits.append({"chapter": mp4.stem, "at_s": at, "kind": "word", "word_no": n})
        shutil.rmtree(tmp, ignore_errors=True)
    (out / "check.json").write_text(json.dumps({"hits": hits}, indent=1), encoding="utf-8")
    for h in hits[:40]:                                  # never the word itself: its number in demo_mask.json
        print(f"  ⚠️ {h['chapter']} at {h['at_s']:.1f} s: {h['kind']}" + (f" #{h['word_no']}" if "word_no" in h else ""))
    demo = out / "demo.mp4"
    if hits and demo.exists():
        demo.rename(out / "demo.refused.mp4")
    print(f"check: {len(hits)} frames with something private" + (" — video refused" if hits else " — clean"))
    return 1 if hits else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("words")
    r = sub.add_parser("record")
    r.add_argument("story")
    r.add_argument("--only", default="")
    r.add_argument("--out", default="~/aurora-demo")
    c = sub.add_parser("check")
    c.add_argument("dir")
    j = sub.add_parser("join")
    j.add_argument("story")
    j.add_argument("--out", default="~/aurora-demo")
    j.add_argument("--music", default="")
    j.add_argument("--volume", type=float, default=None)
    a = ap.parse_args()
    return {"words": cmd_words, "record": cmd_record, "check": cmd_check, "join": cmd_join}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())

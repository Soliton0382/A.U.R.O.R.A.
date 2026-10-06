# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""Download the background music of Aurora's videos (config/story_music.json) from Wikimedia Commons, once.

Each file's licence is read again from Commons before it is kept: only CC0 and public domain pass (a file whose page
changed is skipped and said). The music is kept as Ogg Vorbis, its first STORY_MUSIC_MAX_S seconds, in the admin's
music folder, story/; a file already there is not downloaded again.
    .venv/bin/python sys/core/script/story_music_fetch.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aurora import kno_story, sys_config  # noqa: E402

API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "Aurora/1.0 (local assistant; background music of its own videos)"}
FREE = ("cc0", "public domain", "pdm")
MAX_S = 300
PAUSE_S = 8                                   # between two files: Commons answers 429 to a quick series (2026-10-06)


def _get(url: str, timeout: int) -> bytes:
    """GET with a polite retry: on 429 or 503 wait what the server asks (or 30 s), three times."""
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or attempt == 3:
                raise
            time.sleep(min(120, int(e.headers.get("Retry-After") or 30)))
    raise RuntimeError("unreachable")


def _info(title: str) -> dict:
    q = urllib.parse.urlencode({"action": "query", "format": "json", "prop": "imageinfo", "iiprop": "url|extmetadata",
                                "iiextmetadatafilter": "LicenseShortName", "titles": f"File:{title}"})
    page = next(iter(json.loads(_get(f"{API}?{q}", 60))["query"]["pages"].values()))
    ii = (page.get("imageinfo") or [{}])[0]
    return {"url": ii.get("url"), "license": ii.get("extmetadata", {}).get("LicenseShortName", {}).get("value", "")}


def main() -> int:
    cfg = sys_config.get()
    out_dir = kno_story.music_dir(cfg)
    out_dir.mkdir(parents=True, exist_ok=True)
    kept = 0
    for t in kno_story.catalog()["tracks"]:
        target = out_dir / kno_story.track_name(t)
        if target.is_file():
            kept += 1
            continue
        time.sleep(PAUSE_S)
        try:
            info = _info(t["file"])
        except (OSError, ValueError) as e:
            print(f"❌ {t['file']}: {e}")
            continue
        if not info["url"] or not any(f in info["license"].lower() for f in FREE):
            print(f"⏭️  {t['file']}: licence now «{info['license'] or 'not found'}» — skipped")
            continue
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw"
            try:
                raw.write_bytes(_get(info["url"], 300))
            except OSError as e:
                print(f"❌ {t['file']}: {e}")
                continue
            r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw), "-t", str(MAX_S),
                                "-vn", "-ac", "2", "-ar", "44100", "-c:a", "libvorbis", "-q:a", "4", str(target)],
                               capture_output=True, text=True)
        if r.returncode != 0:
            print(f"❌ {t['file']}: {r.stderr.strip()[-200:]}")
            continue
        kept += 1
        print(f"✅ {t['mood']:10} {t['credit']} ({info['license']})")
    print(f"{kept} of {len(kno_story.catalog()['tracks'])} tracks in {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

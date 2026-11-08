# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The demo recorder's steps (dev_demo_video.py, ROADMAP N76): one chapter's storyboard played in a page — views,
clicks, typing, captions, waits shown faster, a real command in a terminal, a picture or a PDF page over the page —
with every write the chapter does not allow refused in the browser (C515: and what its body must carry)."""
from __future__ import annotations

import base64
import os
import re
import subprocess
import time
from pathlib import Path


def _base() -> str:
    from dev_demo_video import BASE_URL                # the recorder's own address, set once there
    return BASE_URL


# ---- a chapter's steps ------------------------------------------------------------------------------------------------
class Player:
    """Plays one chapter's steps in a page; every write the chapter did not allow is refused in the browser."""

    def __init__(self, page, chapter: dict):
        self.page, self.refused, self.frames = page, [], None
        # a write is "METHOD /path" (regex), or {"path": regex, "body": text the request must carry} — C515: a release
        # of the demo's address only, never of another one that looks the same on a masked page
        self.allowed = [(re.compile(w["path"] if isinstance(w, dict) else w), w.get("body") if isinstance(w, dict) else None)
                        for w in chapter.get("writes", [])]
        page.route("**/*", self._guard)
        # a confirm() is the owner's «are you sure?»: said yes only in a chapter that says so (its writes still guarded)
        page.on("dialog", lambda d: d.accept() if chapter.get("confirm") else d.dismiss())

    def _guard(self, route, request):
        from urllib.parse import urlparse
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return route.continue_()
        what = f"{request.method} {urlparse(request.url).path}"
        body = request.post_data or ""
        if any(rx.fullmatch(what) and (need is None or need in body) for rx, need in self.allowed):
            return route.continue_()
        self.refused.append(what)
        print(f"  refused (not in the chapter's writes): {what}")
        return route.abort("blockedbyclient")

    # the cursor goes to the element, then it is clicked
    def _point(self, loc, click=True):
        if click and getattr(loc, "_demo_unique", False) and loc.count() != 1:
            raise SystemExit(f"a click that must be unique matches {loc.count()} elements: stopped (C515)")
        try:
            loc.scroll_into_view_if_needed(timeout=8000)
        except Exception:                                # noqa: BLE001 — a list redrawn while we look: scrolled by hand
            loc.first.evaluate("(el) => el.scrollIntoView({block: 'center'})")
            self.page.wait_for_timeout(600)
        b = loc.first.bounding_box()
        if b:
            x, y = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
            self.page.evaluate("([x, y]) => __demo.cursor(x, y, false)", [x, y])
            self.page.wait_for_timeout(600)
            if click:
                self.page.evaluate("([x, y]) => __demo.cursor(x, y, true)", [x, y])
                self.page.mouse.click(x, y)
        elif click:
            loc.click()

    def step(self, s: dict) -> None:
        p, do, ms = self.page, s["do"], s.get("ms")
        if do == "view":
            sel = f'#nav button[data-view="{s["id"]}"]'
            loc = p.locator(sel).first
            if loc.count() and loc.is_visible():
                self._point(loc)
            else:
                p.evaluate("(sel) => document.querySelector(sel)?.click()", sel)
            p.wait_for_timeout(ms or 1800)
        elif do == "goto":
            p.goto(_base() + s["path"])
            p.wait_for_timeout(ms or 1500)
        elif do == "click":
            self._point(self._loc(s))
            p.wait_for_timeout(ms or 1200)
        elif do == "type":
            loc = self._loc(s)
            self._point(loc)
            loc.evaluate("(el) => { el.dataset.demoTyped = '1'; }")
            loc.press_sequentially(s["text"], delay=s.get("delay", 45))
            if s.get("enter"):
                p.wait_for_timeout(400)
                loc.press("Enter")
            p.wait_for_timeout(ms or 800)
        elif do == "press":
            p.keyboard.press(s["key"])
            p.wait_for_timeout(ms or 600)
        elif do == "caption":
            p.evaluate("([t, s, top]) => __demo.caption(t, s, top)", [s.get("title", ""), s.get("sub", ""), bool(s.get("top"))])
            p.wait_for_timeout(ms or 3500)
            if not s.get("keep"):
                p.evaluate("() => __demo.uncaption()")
                p.wait_for_timeout(450)
        elif do == "caption_js":                         # a caption whose text the page measures (e.g. two answers' times)
            sub = p.evaluate(s["js"])
            p.evaluate("([t, s, top]) => __demo.caption(t, s, top)", [s.get("title", ""), str(sub), bool(s.get("top"))])
            p.wait_for_timeout(ms or 4000)
            if not s.get("keep"):
                p.evaluate("() => __demo.uncaption()")
                p.wait_for_timeout(450)
        elif do == "uncaption":
            p.evaluate("() => __demo.uncaption()")
            p.wait_for_timeout(450)
        elif do == "card":
            p.evaluate("([t, s]) => __demo.card(t, s)", [s.get("title", ""), s.get("sub", "")])
            p.wait_for_timeout(ms or 3000)
            if not s.get("keep"):
                p.evaluate("() => __demo.uncard()")
                p.wait_for_timeout(650)
        elif do == "uncard":
            p.evaluate("() => __demo.uncard()")
            p.wait_for_timeout(ms or 650)
        elif do == "highlight":
            loc = self._loc(s).first
            try:
                loc.scroll_into_view_if_needed(timeout=8000)
            except Exception:                            # noqa: BLE001 — see _point
                loc.evaluate("(el) => el.scrollIntoView({block: 'center'})")
                p.wait_for_timeout(600)
            p.evaluate("(b) => __demo.highlight(b)", loc.bounding_box())
            p.wait_for_timeout(ms or 2500)
            p.evaluate("() => __demo.unhighlight()")
        elif do == "wait":
            p.wait_for_timeout(ms or 1000)
        elif do == "wait_for":
            self._loc(s).wait_for(state=s.get("state", "visible"), timeout=s.get("timeout", 60000))
            p.wait_for_timeout(ms or 300)
        elif do == "scroll":
            for _ in range(int(s.get("steps", 12))):
                p.mouse.wheel(0, s.get("dy", 600) / int(s.get("steps", 12)))
                p.wait_for_timeout(40)
            p.wait_for_timeout(ms or 900)
        elif do in ("click_text", "highlight_text"):     # a button found by the end of its text, exactly one (C515)
            js = ("([scope, end, act]) => { const all = [...document.querySelectorAll(scope + ' button')]"
                  ".filter(b => b.offsetParent && b.innerText.trim().endsWith(end)); if (all.length !== 1) return all.length; "
                  "const b = all[0]; b.scrollIntoView({block: 'center'}); const r = b.getBoundingClientRect(); "
                  "return {x: r.x, y: r.y, width: r.width, height: r.height}; }")
            box = p.evaluate(js, [s["scope"], s["endswith"], do])
            if not isinstance(box, dict):
                raise SystemExit(f"«…{s['endswith']}» matches {box} buttons, not one: stopped (C515)")
            p.wait_for_timeout(500)
            box = p.evaluate(js, [s["scope"], s["endswith"], do])
            if do == "highlight_text":
                p.evaluate("(b) => __demo.highlight(b)", box)
                p.wait_for_timeout(ms or 2500)
                p.evaluate("() => __demo.unhighlight()")
            else:
                x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
                p.evaluate("([x, y]) => __demo.cursor(x, y, false)", [x, y])
                p.wait_for_timeout(600)
                p.evaluate("([x, y]) => __demo.cursor(x, y, true)", [x, y])
                p.evaluate("([scope, end]) => [...document.querySelectorAll(scope + ' button')]"
                           ".filter(b => b.offsetParent && b.innerText.trim().endsWith(end))[0].click()",
                           [s["scope"], s["endswith"]])
                p.wait_for_timeout(ms or 1200)
        elif do == "until":                              # wait for a page condition (JS), shown faster
            t0 = time.monotonic()
            if s.get("speed", 1) > 1:
                p.evaluate("(l) => __demo.ff(l)", f"⏩ {s['speed']}×")
            p.wait_for_function(s["js"], timeout=s.get("timeout", 300000), polling=500)
            p.wait_for_timeout(s.get("after", 800))
            if s.get("speed", 1) > 1:
                p.evaluate("() => __demo.ff('')")
                if self.frames:
                    self.frames.fast.append((t0, time.monotonic() - s.get("after", 800) / 1000, float(s["speed"])))
            p.wait_for_timeout(ms or 300)
        elif do == "run":
            self._run(s)
        elif do == "picture":
            self._picture(s)
        elif do == "save":                               # a file the page links to, kept for a later step
            href = self._loc({"sel": s["from_sel"], **({"nth": s["nth"]} if "nth" in s else {})}).get_attribute("href")
            Path(s["path"]).write_bytes(p.context.request.get(href if href.startswith("http") else _base() + href).body())
            p.wait_for_timeout(ms or 300)
        elif do == "features":
            p.evaluate("([t, items, each]) => __demo.features(t, items, each)", [s["title"], s["items"], s.get("each", 280)])
            p.wait_for_timeout(ms or 10000)
            if not s.get("keep"):
                p.evaluate("() => __demo.unfeatures()")
                p.wait_for_timeout(500)
        elif do == "attach":                             # a file into an <input type=file>: from disk or a link on the page
            src = s.get("path")
            if not src:
                href = self._loc({"sel": s["from_sel"]}).get_attribute("href")
                r = p.context.request.get(href if href.startswith("http") else _base() + href)
                src = Path(os.environ.get("TMPDIR", "/tmp")) / (s.get("name") or "picture.png")
                src.write_bytes(r.body())
            p.locator(s["input"]).first.set_input_files(str(src))
            p.wait_for_timeout(ms or 1500)
        elif do == "made_show":                          # click, catch the document the API made, show its first page
            with p.expect_response(lambda r: s["response"] in r.url and r.request.method == "POST",
                                   timeout=s.get("timeout", 120000)) as resp:
                self._point(self._loc(s))
            doc = resp.value.json()
            f = Path(s.get("save_as") or Path(os.environ.get("TMPDIR", "/tmp")) / doc["name"])
            f.write_bytes(p.context.request.get(_base() + doc["url"]).body())
            p.wait_for_timeout(1500)
            p.keyboard.press("Escape")                   # the page's own viewer: a headless browser shows no PDF
            self._picture({**s, "path": str(f)})
        elif do == "download_show":                      # click, catch the file, show its first page over the page
            with p.expect_download(timeout=s.get("timeout", 120000)) as dl:
                self._point(self._loc(s))
            f = Path(os.environ.get("TMPDIR", "/tmp")) / dl.value.suggested_filename
            dl.value.save_as(str(f))
            self._picture({**s, "path": str(f)})
        elif do == "eval":
            p.evaluate(s["js"])
            p.wait_for_timeout(ms or 300)
        else:
            raise SystemExit(f"unknown step: {do}")

    def _loc(self, s: dict):
        if "text" in s and "sel" not in s:
            return self.page.get_by_text(s["text"], exact=s.get("exact", False)).first
        loc = self.page.locator(s["sel"])
        if s.get("unique"):                              # every match counted before the click: one, or stop
            loc._demo_unique = True
            return loc
        return loc.nth(s["nth"]) if "nth" in s else loc.first

    def _run(self, s: dict) -> None:
        """A real command, its real output shown line by line in a terminal over the page."""
        p = self.page
        if not s.get("append"):                          # a second command in the same terminal keeps the first
            p.evaluate("(t) => __demo.term(t)", s.get("title", "terminal"))
        shown = s.get("shown") or " ".join(s["cmd"])
        p.wait_for_timeout(500)
        typed = ""
        for ch in f"$ {shown}":
            typed += ch
            p.evaluate("(l) => { const pre = document.querySelector('#demo-term pre'); let d = pre.querySelector('.typing'); "
                       "if (!d) { d = document.createElement('div'); d.className = 'typing'; pre.appendChild(d); } d.textContent = l; }", typed)
            p.wait_for_timeout(28)
        p.evaluate("() => { const pre = document.querySelector('#demo-term pre'); const typed = pre.querySelector('.typing'); "
                   "if (typed) { const t = typed.textContent; typed.remove(); __demo.termLine(t); } }")
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "COLUMNS": "110"}
        proc = subprocess.Popen(s["cmd"], cwd=s.get("cwd"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, env=env)
        for line in proc.stdout:
            p.evaluate("([l, m]) => __demo.termLine(l, m)", [line.rstrip("\n"), s.get("marks", [])])
            p.wait_for_timeout(s.get("line_ms", 60))
        proc.wait()
        p.wait_for_timeout(s.get("ms", 4000))
        if not s.get("keep"):
            p.evaluate("() => __demo.unterm()")
            p.wait_for_timeout(450)

    def _picture(self, s: dict) -> None:
        src = Path(s["path"]).expanduser()
        if src.suffix.lower() == ".pdf":
            tmp = Path(os.environ.get("TMPDIR", "/tmp")) / f"demo-pdf-{os.getpid()}"
            subprocess.run(["pdftoppm", "-png", "-r", str(s.get("dpi", 130)), "-f", str(s.get("page", 1)),
                            "-l", str(s.get("page", 1)), "-singlefile", str(src), str(tmp)], check=True)
            data, kind = Path(f"{tmp}.png").read_bytes(), "png"
            Path(f"{tmp}.png").unlink()
        else:
            data, kind = src.read_bytes(), src.suffix.lstrip(".").lower().replace("jpg", "jpeg")
        if s.get("crop"):                                # a detail, enlarged: x0, y0, x1, y1 as fractions
            import io
            from PIL import Image
            im = Image.open(io.BytesIO(data)).convert("RGB")
            x0, y0, x1, y1 = s["crop"]
            im = im.crop((int(x0 * im.width), int(y0 * im.height), int(x1 * im.width), int(y1 * im.height)))
            k = min(1600 / im.width, 820 / im.height)
            im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "PNG")
            data, kind = buf.getvalue(), "png"
        self.page.evaluate("(u) => __demo.picture(u)", f"data:image/{kind};base64,{base64.b64encode(data).decode()}")
        self.page.wait_for_timeout(s.get("ms", 5000))
        if not s.get("keep"):
            self.page.evaluate("() => __demo.unpicture()")
            self.page.wait_for_timeout(550)

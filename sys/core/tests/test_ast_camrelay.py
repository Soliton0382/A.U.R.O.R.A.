# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The telescope PC's camera relayed (owner, 19 Oct: «un server da installare nel mini PC… invii in streaming quello che
vede la camera che si sceglie»): ffmpeg's mpjpeg cut into frames however it arrives, the camera key kept as a hash and
replaced, only that key may send; end to end with a real ffmpeg sending a test picture to the routes, the last frame
and the stream read back, the stream cut when another camera is chosen. Invented cameras."""
import shutil
import socket
import subprocess
import threading
import time

import pytest

from aurora import ast_camrelay as C

JPEG = b"\xff\xd8\xff\xe0" + b"x" * 300 + b"\xff\xd9"


def part(b: bytes) -> bytes:
    return b"--ffmpeg\r\nContent-type: image/jpeg\r\nContent-length: " + str(len(b)).encode() + b"\r\n\r\n" + b + b"\r\n"


def test_frames_cut_however_the_bytes_arrive():
    data = part(JPEG) + part(JPEG[:-2] + b"yy\xff\xd9") + part(JPEG)
    for step in (1, 7, 100, len(data)):
        f, got = C.Frames(), []
        for i in range(0, len(data), step):
            got += f.feed(data[i:i + step])
        assert len(got) == 3 and all(g[:2] == b"\xff\xd8" for g in got)


def test_a_stream_that_is_not_mpjpeg_or_too_big_is_refused():
    with pytest.raises(ValueError):
        C.Frames().feed(b"--ffmpeg\r\nContent-length: 999999999\r\n\r\n")
    f = C.Frames()
    with pytest.raises(ValueError):
        for _ in range(C.MAX_FRAME // 65536 + 2):
            f.feed(b"\x00" * 65536)


def test_the_key_kept_as_a_hash_one_a_person(tmp_path):
    r = C.Relay(tmp_path)
    k1 = r.new_key("anna")
    assert k1.startswith("aurcam_") and r.who(k1) == "anna" and k1 not in (tmp_path / "camera_keys.json").read_text()
    k2 = r.new_key("anna")
    assert r.who(k1) is None and r.who(k2) == "anna" and r.who("aurcam_wrong") is None and r.who("") is None
    r.new_key("bruno")
    assert r.who(k2) == "anna" and r.has_key("bruno")


def test_the_choice_the_last_frame_and_staleness(tmp_path):
    r = C.Relay(tmp_path)
    assert r.pc("anna", ["Cam A", "Cam B"], None)["wanted"] == ""
    r.want("anna", "Cam B")
    assert r.wanted("anna") == "Cam B" and r.last("anna") == (None, 0.0)
    r.put("anna", JPEG)
    assert r.last("anna")[0] == JPEG and r.status("anna")["live"] and r.number("anna") == 1
    assert r.last("bruno")[0] is None                                     # each person's own
    r.state["anna"]["at"] -= C.STALE_S + 1
    assert r.last("anna")[0] is None and not r.status("anna")["live"]


@pytest.fixture
def server(tmp_path):
    try:
        import uvicorn
        from fastapi import FastAPI
        from aurora import sys_context
        from aurora.api import astro_cam, core
    except Exception as e:  # noqa: BLE001 — no configuration in this copy
        pytest.skip(f"the API does not load here: {type(e).__name__}")
    astro_cam._relay = C.Relay(tmp_path)

    async def fake_auth():
        sys_context.CURRENT.set("anna")

    app = FastAPI()
    app.include_router(astro_cam.router)
    app.dependency_overrides[core.auth] = fake_auth
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", astro_cam
    srv.should_exit = True
    t.join(5)
    astro_cam._relay = None


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_a_real_ffmpeg_sends_and_the_page_reads(server):
    import httpx
    url, mod = server
    key = httpx.post(f"{url}/v1/aurora/astro/camera/key").json()["key"]
    assert httpx.post(f"{url}/v1/aurora/astro/camera/pc", json={"devices": ["Cam A"]}).status_code == 401
    pc = {"X-Aurora-Camera": key}
    assert httpx.post(f"{url}/v1/aurora/astro/camera/pc", headers=pc, json={"devices": "Cam A"}).json()["wanted"] == ""
    httpx.put(f"{url}/v1/aurora/astro/camera", json={"wanted": "Cam A"})
    assert httpx.post(f"{url}/v1/aurora/astro/camera/pc", headers=pc, json={"devices": ["Cam A"]}).json()["wanted"] == "Cam A"
    ff = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-re", "-f", "lavfi", "-i",
                           "testsrc=size=320x240:rate=10", "-t", "20", "-f", "mpjpeg", "-q:v", "5", "-method", "POST",
                           "-chunked_post", "1", "-headers", f"X-Aurora-Camera: {key}\r\n", f"{url}/v1/aurora/astro/camera/push"])
    try:
        for _ in range(60):
            st = httpx.get(f"{url}/v1/aurora/astro/camera").json()
            if st["live"]:
                break
            time.sleep(0.1)
        assert st["live"] and st["devices"] == ["Cam A"]
        fr = httpx.get(f"{url}/v1/aurora/astro/camera/frame")
        assert fr.status_code == 200 and fr.content[:2] == b"\xff\xd8"
        with httpx.stream("GET", f"{url}/v1/aurora/astro/camera/stream", timeout=10) as s:
            assert s.headers["content-type"].startswith("multipart/x-mixed-replace")
            got = b""
            for chunk in s.iter_bytes():
                got += chunk
                if got.count(b"--frame") >= 3:
                    break
        assert got.count(b"\xff\xd8") >= 2
        httpx.put(f"{url}/v1/aurora/astro/camera", json={"wanted": ""})        # another choice: the push ends
        ff.wait(timeout=10)
        assert ff.returncode is not None
    finally:
        if ff.poll() is None:
            ff.kill()


def test_the_settings_checked_and_the_dialog_a_counter(tmp_path):
    r = C.Relay(tmp_path)
    out = r.settings("anna", {"gain": 12, "auto_exposure": 0, "size": [3840, 2160], "fps": 99, "send_width": 100})
    assert out["settings"] == {"gain": 12.0, "auto_exposure": False, "size": [3840, 2160], "fps": 30, "send_width": 320}
    for bad in ({"size": [1000, 1000]}, {"gain": 1e9}, {"shutter": 1}):
        with pytest.raises(ValueError):
            r.settings("anna", bad)
    r.settings("anna", {"gain": None, "dialog": True})                  # back to the camera's own; the window once
    a = r.pc("anna", ["Cam A"], {"values": {"gain": 3.0}, "size": [1920, 1080], "secret": "x"})
    assert "gain" not in a["settings"] and a["dialog"] == 1 and a["version"] == 2
    assert r.status("anna")["camera"] == {"values": {"gain": 3.0}, "size": [1920, 1080]}


def _plugin(name):
    from pathlib import Path
    return Path(__file__).resolve().parents[2] / "plugins" / "astro" / name


def test_the_pc_side_installs_what_it_needs_and_only_sends():
    ps, py = _plugin("astro_camera.ps1").read_text(), _plugin("astro_camera.py").read_text()
    assert "winget install -e --id Python.Python" in ps and "-m venv" in ps and "opencv-python pygrabber" in ps
    assert "astro_camera.py" in ps and "$args =" not in ps                  # PowerShell's own variable
    assert "/v1/aurora/astro/camera/pc" in py and "/v1/aurora/astro/camera/push" in py and "X-Aurora-Camera" in py
    assert "CAP_DSHOW" in py and "CAP_PROP_SETTINGS" in py and "encode_chunked=True" in py
    assert "listen(" not in py and "HTTPServer" not in py and "bind(" not in py


@pytest.mark.skipif(__import__("importlib").util.find_spec("cv2") is None, reason="OpenCV not installed")
def test_the_agent_sends_and_takes_the_settings(server, monkeypatch):
    # the PC's agent itself, a camera invented: the page's gain reaches the camera and comes back as taken
    import importlib.util
    import httpx
    import numpy as np
    url, mod = server
    spec = importlib.util.spec_from_file_location("astro_camera", _plugin("astro_camera.py"))
    agent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agent)

    class Cam:
        def __init__(self, *a):
            self.p = {agent.cv2.CAP_PROP_FRAME_WIDTH: 640, agent.cv2.CAP_PROP_FRAME_HEIGHT: 480}

        def isOpened(self):  # noqa: N802
            return True

        def set(self, k, v):
            self.p[k] = v
            return True

        def get(self, k):
            return float(self.p.get(k, -1))

        def read(self):
            return True, np.full((480, 640, 3), 90, np.uint8)

        def release(self):
            pass

    monkeypatch.setattr(agent.cv2, "VideoCapture", Cam)
    monkeypatch.setattr(agent, "cameras", lambda: ["Cam A"])
    key = httpx.post(f"{url}/v1/aurora/astro/camera/key").json()["key"]
    httpx.put(f"{url}/v1/aurora/astro/camera", json={"wanted": "Cam A", "settings": {"gain": 7, "fps": 20}})
    threading.Thread(target=agent.Agent(url, key, False).run, daemon=True).start()
    st = {}
    for _ in range(100):
        st = httpx.get(f"{url}/v1/aurora/astro/camera").json()
        if st["live"] and st["camera"].get("values", {}).get("gain") == 7:
            break
        time.sleep(0.1)
    assert st["live"] and st["devices"] == ["Cam A"] and st["camera"]["values"]["gain"] == 7
    assert httpx.get(f"{url}/v1/aurora/astro/camera/frame").content[:2] == b"\xff\xd8"
    httpx.put(f"{url}/v1/aurora/astro/camera", json={"settings": {"gain": 3}})
    for _ in range(60):
        if httpx.get(f"{url}/v1/aurora/astro/camera").json()["camera"]["values"]["gain"] == 3:
            break
        time.sleep(0.1)
    assert httpx.get(f"{url}/v1/aurora/astro/camera").json()["camera"]["values"]["gain"] == 3
    httpx.put(f"{url}/v1/aurora/astro/camera", json={"wanted": ""})


def test_the_package_for_the_pc(server):
    import io
    import zipfile
    import httpx
    url, _ = server
    r = httpx.get(f"{url}/v1/aurora/astro/camera/bundle")
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert r.headers["content-type"] == "application/zip"
    assert sorted(names) == ["aurora_camera/LEGGIMI.txt", "aurora_camera/README.txt", "aurora_camera/astro_camera.ps1",
                             "aurora_camera/astro_camera.py"]

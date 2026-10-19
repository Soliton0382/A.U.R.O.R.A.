# Aurora - a camera of this PC sent to Aurora, for the live collimation page (started by astro_camera.ps1).
# The collimator's own program works this way: OpenCV opens the camera (DirectShow) and sets its properties - gain,
# exposure, brightness, focus, zoom, the resolution. Here the page asks for them, through Aurora; this PC only sends
# (frames, the cameras it sees, what the camera took): nothing listens on it. The camera key can only send.
from __future__ import annotations

import argparse
import http.client
import json
import ssl
import sys
import threading
import time
import urllib.parse

try:
    import cv2
except ImportError:
    sys.exit("OpenCV missing: run astro_camera.ps1, it installs what is needed")

VERSION = 2
PROPS = {"brightness": cv2.CAP_PROP_BRIGHTNESS, "contrast": cv2.CAP_PROP_CONTRAST, "saturation": cv2.CAP_PROP_SATURATION,
         "sharpness": cv2.CAP_PROP_SHARPNESS, "gamma": cv2.CAP_PROP_GAMMA, "gain": cv2.CAP_PROP_GAIN,
         "exposure": cv2.CAP_PROP_EXPOSURE, "focus": cv2.CAP_PROP_FOCUS, "zoom": cv2.CAP_PROP_ZOOM}


def cameras() -> list[str]:
    """The cameras' names in DirectShow's order (OpenCV opens them by that index); numbers when the names are not read."""
    try:
        from pygrabber.dshow_graph import FilterGraph
        return list(FilterGraph().get_input_devices())
    except Exception:  # noqa: BLE001 - names are a comfort: the numbers still open the cameras
        names = []
        for i in range(6):
            c = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if c.isOpened():
                names.append(f"Camera {i}")
            c.release()
        return names


class Agent:
    def __init__(self, url: str, key: str, insecure: bool):
        u = urllib.parse.urlsplit(url.rstrip("/"))
        self.https, self.host, self.base = u.scheme == "https", u.hostname, u.path.rstrip("/")
        self.port = u.port or (443 if self.https else 80)
        self.ctx = ssl._create_unverified_context() if insecure else ssl.create_default_context()  # noqa: S323
        self.key = key
        self.names = cameras()
        self.lock = threading.Lock()
        self.reopen = threading.Event()
        self.wanted, self.settings, self.version, self.applied = "", {}, 0, -1
        self.dialog_seen, self.dialog_want = None, 0
        self.state: dict = {"agent": VERSION}

    def conn(self, timeout: float):
        if self.https:
            return http.client.HTTPSConnection(self.host, self.port, context=self.ctx, timeout=timeout)
        return http.client.HTTPConnection(self.host, self.port, timeout=timeout)

    def ask(self) -> dict:
        c = self.conn(10)
        try:
            c.request("POST", f"{self.base}/v1/aurora/astro/camera/pc",
                      body=json.dumps({"devices": self.names, "camera": self.state}),
                      headers={"Content-Type": "application/json", "X-Aurora-Camera": self.key})
            r = c.getresponse()
            data = r.read()
        finally:
            c.close()
        if r.status == 401:
            raise SystemExit("Aurora does not know this camera key: make a new one in the collimation page")
        if r.status != 200:
            raise OSError(f"HTTP {r.status}")
        return json.loads(data)

    def poll(self) -> None:
        """Every 2 s: the cameras and the camera's state told, the choice and the settings heard."""
        while True:
            try:
                a = self.ask()
            except OSError as e:
                print(f"Aurora does not answer: {e}")
                time.sleep(5)
                continue
            with self.lock:
                if a.get("wanted", "") != self.wanted or a.get("settings", {}).get("size") != self.settings.get("size"):
                    self.reopen.set()
                self.wanted, self.settings, self.version = a.get("wanted", ""), a.get("settings", {}), a.get("version", 0)
                if self.dialog_seen is None:
                    self.dialog_seen = a.get("dialog", 0)
                self.dialog_want = a.get("dialog", 0)
            time.sleep(2)

    def apply(self, cap) -> None:
        """The page's settings on the camera; then what the camera says it took."""
        s = self.settings
        if "auto_exposure" in s:      # DirectShow through OpenCV: 0.75 automatic, 0.25 by hand
            cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75 if s["auto_exposure"] else 0.25)
        if "autofocus" in s:
            cap.set(cv2.CAP_PROP_AUTOFOCUS, 1 if s["autofocus"] else 0)
        for k, p in PROPS.items():
            if k in s and not (k == "exposure" and s.get("auto_exposure")) and not (k == "focus" and s.get("autofocus")):
                cap.set(p, float(s[k]))
        vals = {k: round(cap.get(p), 3) for k, p in PROPS.items()}
        vals["auto_exposure"] = round(cap.get(cv2.CAP_PROP_AUTO_EXPOSURE), 3)
        vals["autofocus"] = round(cap.get(cv2.CAP_PROP_AUTOFOCUS), 3)
        self.state = {"agent": VERSION, "values": vals,
                      "size": [int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))]}

    def frames(self, cap):
        """The POST's body: mpjpeg parts at the pace asked, until another camera or size is chosen."""
        while not self.reopen.is_set():
            t0 = time.time()
            with self.lock:
                s, version, dialog = dict(self.settings), self.version, self.dialog_want
            if version != self.applied:
                self.apply(cap)
                self.applied = version
            if self.dialog_seen is not None and dialog > self.dialog_seen:
                cap.set(cv2.CAP_PROP_SETTINGS, 1)   # the camera's own window, on this PC's screen
                self.dialog_seen = dialog
            ok, img = cap.read()
            if not ok:
                self.state["error"] = "the camera gives no picture"
                return
            w = int(s.get("send_width", 1280))
            if w and img.shape[1] > w:
                img = cv2.resize(img, (w, round(img.shape[0] * w / img.shape[1])), interpolation=cv2.INTER_AREA)
            ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, int(s.get("quality", 80))])
            if ok:
                b = jpg.tobytes()
                yield b"--ffmpeg\r\nContent-type: image/jpeg\r\nContent-length: %d\r\n\r\n" % len(b) + b + b"\r\n"
            time.sleep(max(0.0, 1 / max(1, int(s.get("fps", 10))) - (time.time() - t0)))

    def run(self) -> None:
        print(f"cameras: {', '.join(self.names) or 'none seen'}")
        threading.Thread(target=self.poll, daemon=True).start()
        while True:
            self.reopen.clear()                   # before reading the choice: a change after it reopens
            with self.lock:
                name, size = self.wanted, self.settings.get("size", [1920, 1080])
            if not name:
                time.sleep(1)
                continue
            if name not in self.names:
                self.names = cameras()
                time.sleep(2)
                continue
            cap = cv2.VideoCapture(self.names.index(name), cv2.CAP_DSHOW)
            if not cap.isOpened():
                self.state = {"agent": VERSION, "error": f"{name} does not open: is another program using it?"}
                print(self.state["error"])
                time.sleep(3)
                continue
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))   # the big sizes come only as MJPG
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, size[0])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, size[1])
            self.applied = -1
            print(f"sending: {name} at {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")
            c = self.conn(30)
            try:
                c.request("POST", f"{self.base}/v1/aurora/astro/camera/push", body=self.frames(cap), encode_chunked=True,
                          headers={"X-Aurora-Camera": self.key, "Content-Type": "multipart/x-mixed-replace; boundary=ffmpeg"})
                c.getresponse().read()
            except OSError as e:
                print(f"sending stopped: {e}")
                time.sleep(2)
            finally:
                c.close()
                cap.release()


def main() -> None:
    a = argparse.ArgumentParser(description="Send a camera of this PC to Aurora (the live collimation)")
    a.add_argument("--url")
    a.add_argument("--key")
    a.add_argument("--insecure", action="store_true", help="accept a certificate this PC does not trust")
    a.add_argument("--list", action="store_true", help="only list the cameras")
    x = a.parse_args()
    if x.list:
        print("\n".join(cameras()))
        return
    if not (x.url and x.key):
        a.error("--url and --key are needed (the command the collimation page gives)")
    try:
        Agent(x.url, x.key, x.insecure).run()
    except KeyboardInterrupt:
        print("stopped")


if __name__ == "__main__":
    main()

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""🔭 Where the mount points (ROADMAP N28): a fake N.I.N.A. Advanced API on this machine, read back — the pointing, the
side of the pier, the camera, the sequence running — and the site never in what is kept (latitude, longitude and the
sidereal time dropped, altitude and azimuth rounded)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from aurora import ast_nina as N

MOUNT = {"Connected": True, "DisplayName": "Test mount", "RightAscension": 5.5, "Declination": 22.0145, "SiderealTime": 7.25,
         "SiteLatitude": 41.123456, "SiteLongitude": 12.654321, "SiteElevation": 33, "Altitude": 61.2345, "Azimuth": 231.98765,
         "SideOfPier": "pierEast", "TrackingEnabled": True, "Slewing": False, "AtPark": False, "TimeToMeridianFlip": 24,
         "GuideRateRightAscensionArcsecPerSec": 7.52}
SEQ = [{"GlobalTriggers": []}, {"Name": "Targets_Container", "Status": "RUNNING",
                                "Items": [{"Name": "Test target", "Status": "RUNNING", "Items": [{"Name": "Take Many Exposures", "Status": "RUNNING"}]}]}]


def serve():
    answers = {"/v2/api/version": "2.2.15.2", "/v2/api/equipment/mount/info": MOUNT,
               "/v2/api/equipment/camera/info": {"Connected": True, "CameraState": "Exposing", "Temperature": -9.96, "TargetTemp": -10,
                                                 "CoolerOn": True, "CoolerPower": 41.0, "Gain": 100, "Offset": 50},
               "/v2/api/equipment/focuser/info": {"Connected": True, "Position": 1234, "Temperature": "NaN"},
               "/v2/api/equipment/guider/info": {"Connected": True, "State": "Guiding",
                                                 "RMSError": {"RA": {"Arcseconds": 0.51}, "Dec": {"Arcseconds": 0.42}, "Total": {"Arcseconds": 0.66}}},
               "/v2/api/sequence/state": SEQ}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"Response": answers.get(self.path), "Success": self.path in answers, "Error": "" if self.path in answers else "nope"})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body.encode())

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_the_picture_without_the_site():
    srv = serve()
    s = N.status("127.0.0.1", srv.server_address[1])
    m = s["mount"]
    assert s["reachable"] and s["version"] == "2.2.15.2"
    assert m["ha_h"] == 1.75 and m["pier"] == "east" and m["tracking"] and m["flip_h"] is None    # 24 h: no flip due
    assert m["alt_deg"] == 61.2 and m["az_deg"] == 232.0 and m["dec_deg"] == 22.015
    text = json.dumps(s)
    assert "41.12" not in text and "12.65" not in text and "Site" not in text and "7.25" not in text
    assert s["camera"]["state"] == "Exposing" and s["camera"]["temp_c"] == -10.0 and s["focuser"]["temp_c"] is None   # NaN said as none
    assert s["guider"]["rms"]["total"] == 0.66
    assert s["sequence"]["active"] and s["sequence"]["running"][-1] == "Take Many Exposures"
    srv.shutdown()


def test_the_hour_angle_and_an_unreachable_pc():
    assert N.ha_of(1.0, 23.0) == 2.0 and N.ha_of(23.0, 1.0) == -2.0 and N.ha_of(None, 1.0) is None
    s = N.status("127.0.0.1", 9)                      # nothing listens there
    assert not s["reachable"] and s["error"] and "mount" not in s


def test_the_mount_alone_every_second_without_the_site():
    srv = serve()
    w = N.where("127.0.0.1", srv.server_address[1])
    assert w["reachable"] and set(w) == {"reachable", "mount"} and w["mount"]["ha_h"] == 1.75   # one call, the mount only
    assert "41.12" not in json.dumps(w) and "Site" not in json.dumps(w)
    srv.shutdown()
    assert not N.where("127.0.0.1", 9)["reachable"]


def _series(name, exp, total, done, status="CREATED"):
    shot = {"Status": status, "Name": "Take Exposure", "ImageType": "LIGHT", "ExposureTime": exp, "Gain": 1600,
            "Offset": 20, "ExposureCount": 52}
    loop = {"Status": status, "Name": "Loop For Iterations_Condition", "Iterations": total, "CompletedIterations": done}
    take = {"Status": status, "Name": "Take Many Exposures_Container", "Items": [shot, loop]}
    return {"Status": status, "Name": f"{name}_Container", "Items": [take]}


def test_the_shooting_progress_in_hours():
    """Owner, 20 Oct: «il numero di ore totali… una sezione dedicata allo scatto e al progresso totale»: each series of
    the tree N.I.N.A. sends (the shape of its sequence/state), the totals; the file counter is not the progress."""
    tree = [{"GlobalTriggers": []}, {"Name": "Targets_Container", "Items": [
        {"Name": "IC 5070_Container", "Target": {}, "Items": [_series("50x180s", 180.0, 50, 12, "RUNNING"),
                                                               _series("20x300s", 300.0, 20, 0)]}]}]
    p = N.sequence(tree)
    assert [(s["target"], s["name"], s["done"], s["total"], s["running"]) for s in p["series"]] == [
        ("IC 5070", "50x180s", 12, 50, True), ("IC 5070", "20x300s", 0, 20, False)]
    assert (p["planned_s"], p["done_s"], p["left_s"]) == (15000, 2160, 12840)


def test_the_exposure_counts_down():
    assert N._ends_in("2026-10-20T11:31:42.9050137+02:00", now=0) > 0
    assert N._ends_in("2020-01-01T00:00:00+00:00") is None and N._ends_in("never") is None

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

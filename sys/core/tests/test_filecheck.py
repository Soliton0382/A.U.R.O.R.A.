# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A file's reputation before Aurora reads it (sec_filecheck): only its hash asked, a malicious one refused with the
services' reasons, a hash never seen or a service down let in — «not checked», never «clean»."""
import hashlib

import httpx
import pytest

from aurora import sec_filecheck as F


@pytest.fixture
def on(cfg):
    cfg.values.update({"AURORA_LINKCHECK_VIRUSTOTAL": True, "AURORA_LINKCHECK_URLHAUS": True,
                       "AURORA_LINKCHECK_STRICT": False, "AURORA_LINKCHECK_VIRUSTOTAL_KEY": "k" * 64,
                       "AURORA_LINKCHECK_URLHAUS_KEY": "u" * 40})
    return cfg


def services(vt_status: int, vt_stats: dict, payload: str, seen: list):
    def handle(req: httpx.Request) -> httpx.Response:
        seen.append((req.method, str(req.url), req.content))
        if "virustotal" in req.url.host:
            return httpx.Response(vt_status, json={"data": {"attributes": {"last_analysis_stats": vt_stats}}})
        return httpx.Response(200, json={"query_status": payload, "signature": "AgentTesla"})
    return httpx.Client(transport=httpx.MockTransport(handle))


def test_only_the_hash_leaves_and_a_malicious_file_is_refused(on):
    data, seen = b"MZ\x90\x00 not a real program", []
    v = F.check(data, "fattura.exe", on, services(200, {"malicious": 41, "suspicious": 2}, "ok", seen))
    sha = hashlib.sha256(data).hexdigest()
    assert v["blocked"] and v["level"] == "malicious" and v["checked"] == ["virustotal", "urlhaus"]
    assert sha in seen[0][1] and all(data not in (body or b"") for _, _, body in seen)   # the file never sent
    assert "41 motori" in F.refusal(v) and "AgentTesla" in F.refusal(v)
    assert F.check(data, "fattura.exe", on)["cached"]                # a day kept: the quota is small
    with pytest.raises(ValueError, match="Non leggo fattura.exe"):
        F.gate(on, "fattura.exe", data)


def test_a_file_never_seen_or_a_service_down_is_let_in(on, monkeypatch):
    v = F.check(b"la mia tesi", "tesi.pdf", on, services(404, {}, "no_results", []))
    assert not v["blocked"] and v["level"] == "clean" and v["checked"] == ["urlhaus"]

    def down(c, cfg, sha):
        raise httpx.ConnectTimeout("down")
    monkeypatch.setitem(F.CHECKS, "virustotal", down)
    monkeypatch.setitem(F.CHECKS, "urlhaus", down)
    v = F.check(b"un altro file", "note.txt", on)
    assert not v["blocked"] and v["checked"] == [] and all("non risponde" in r for r in v["reasons"])
    F.gate(on, "note.txt", b"un altro file")                         # nothing answered: in, said in the log


def test_without_keys_nothing_is_asked(cfg):
    cfg.values.update({"AURORA_LINKCHECK_VIRUSTOTAL_KEY": "", "AURORA_LINKCHECK_URLHAUS_KEY": ""})
    seen = []
    v = F.check(b"x", "x.txt", cfg, services(200, {"malicious": 9}, "ok", seen))
    assert not v["blocked"] and not seen and v["level"] == "unknown"

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C441: a change carried by the session's cookie from another site is refused; Aurora's own pages, the API key's
calls, programs without browser headers and reads pass."""
from aurora.sys_csrf import foreign

C = {"aurora_device": "x"}


def test_another_site_with_the_session_is_refused():
    assert foreign("POST", {"origin": "https://evil.example", "host": "aurora.example:8443"}, C)
    assert foreign("PUT", {"sec-fetch-site": "cross-site", "host": "aurora.example:8443"}, C)
    assert foreign("DELETE", {"origin": "null", "host": "aurora.example:8443"}, C)          # a sandboxed preview


def test_aurora_s_own_pages_keys_programs_and_reads_pass():
    assert not foreign("POST", {"origin": "https://aurora.example:8443", "host": "aurora.example:8443"}, C)
    assert not foreign("POST", {"origin": "https://evil.example", "authorization": "Bearer k", "host": "a"}, C)
    assert not foreign("POST", {"host": "aurora.example:8443"}, C)                           # no browser's headers
    assert not foreign("GET", {"origin": "https://evil.example", "host": "a"}, C)
    assert not foreign("POST", {"origin": "https://evil.example", "host": "a"}, {})           # no session to borrow
    assert not foreign("POST", {"sec-fetch-site": "same-origin", "host": "a"}, C)

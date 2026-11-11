# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C568 (area audit of 10 Nov), its first half: a caller on loopback was never counted by the lockout, so a local
process could guess a password against the API's own port without limit. Counted now, all local callers as one, with
a ceiling ten times the others'; Aurora's own services pass with their valid key."""
from test_c570_accounts import guard


def test_a_local_process_is_counted_with_a_higher_ceiling(tmp_path):
    o = guard(tmp_path, "c568")                                           # three failed logins allowed: thirty here
    assert o["local_counted"] == [30, 429]
    assert o["local_login_refused"] == 429                                # the right password too, while it lasts
    assert o["local_key_passes"] == 200                                   # the services' own key is never locked out
    assert o["elsewhere_not_locked"] == 401                               # nobody else pays for it
    assert o["told"] == ["127.0.0.1"]                                     # the owner told, once
    assert o["proxied"] == [401, 401, 401, 429]                           # through the proxy: the usual ceiling

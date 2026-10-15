# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""☁️ Cloudflare as a page of the security area, and the masked words in ☁️ Accounts (owner, 16 Oct)."""
import json
from pathlib import Path

CORE = Path(__file__).resolve().parents[1]


def test_the_cloudflare_page_is_the_admin_s_and_reads_aurora_s_own_records():
    src = (CORE / "aurora" / "api" / "edge.py").read_text(encoding="utf-8")
    for route in ('"/v1/aurora/security/edge"', '"/v1/aurora/security/edge/culprits"', '"/v1/aurora/security/edge/block"',
                  '"/v1/aurora/security/edge/unblock"'):
        assert f"{route}, dependencies=[Depends(admin_only)]" in src, route
    assert "net_cfwaf.block," in src and "net_cfwaf.unblock," in src            # Aurora's own records, one module
    manifest = json.loads((CORE.parent / "plugins" / "cloudflare" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["page"] == "edge"
    page = (CORE / "webui" / "js" / "modules" / "security_edge.js").read_text(encoding="utf-8")
    assert 'autonomySlot("edge")' in page and 'pluginSlot("edge")' in page


def test_the_owner_s_masked_words_are_the_setting_aurora_s_own_are_shown_apart():
    src = (CORE / "aurora" / "api" / "accounts.py").read_text(encoding="utf-8")
    assert '"/v1/aurora/accounts/mask", dependencies=[Depends(auth)]' in src and 'me() != _admin()' in src
    js = (CORE / "webui" / "js" / "modules" / "accounts.js").read_text(encoding="utf-8")
    assert "AURORA_CLOUD_MASK_WORDS: words.join" in js

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""C754: the pages made on 27 Nov RUN — under node, a small DOM, the API answered from a fixture (tests/js/ui_run.mjs).
Two faults had passed a syntax check only: el() given elements (C753) and a parameter named like the helper it called
(«box is not a function»: 👥 Gruppi e accessi drew nothing)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
API = """// the API answered from globalThis.FIX: «METHOD path» without the query
export async function call(path, opts = {}) {
  const key = `${(opts.method || "GET")} ${path.split("?")[0]}`;
  if (opts.method && opts.method !== "GET") globalThis.SENT.push([key, opts.body ? JSON.parse(opts.body) : null]);
  if (!(key in globalThis.FIX)) throw Object.assign(new Error(`no fixture for ${key}`), { status: 404 });
  return structuredClone(globalThis.FIX[key]);
}
export const stream = async () => true;
export const followRun = async () => {};
export const callStream = async () => ({});
"""


def _run(tmp_path, scene):
    js = tmp_path / "js"
    shutil.copytree(ROOT / "webui" / "js", js, ignore=shutil.ignore_patterns("local"))
    (js / "api.js").write_text(API, encoding="utf-8")
    (js / "evd").mkdir()                                   # an add-on's pages: Aurora's modules by their address
    for f in (ROOT.parent / "evidentia" / "addon" / "webui").glob("*.js"):
        (js / "evd" / f.name).write_text(f.read_text(encoding="utf-8").replace('"/static/js/', '"../'), encoding="utf-8")
    i18n = js / "i18n.js"                                # strings: the keys themselves (no fetch under node)
    i18n.write_text("export let lang = 'it_IT';\nexport const t = (k, v) => k + (v ? ' ' + JSON.stringify(v) : '');\n"
                    "export function apply() {}\nexport function said(x) { return x; }\nexport async function load() {}\n"
                    "export function extend() {}\nexport function saved() {}\n", encoding="utf-8")
    r = subprocess.run(["node", str(ROOT / "tests" / "js" / "ui_run.mjs"), js.as_uri(), scene], capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-2000:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert "error" not in out, out["error"]
    return out


pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node not installed")


def test_groups_and_access_draw_and_save(tmp_path):
    out = _run(tmp_path, "groups")
    text = "\n".join(out["groups"] + out["access"])
    assert "[object" not in text
    assert "👥 ricerca" in text and "«anna»" in text and "«boss»" in text                       # the group and its members
    assert "groups.area.life" in text and "groups.area.tools" in text and "📅 Calendario" in text
    assert out["sent"] == [["PUT /v1/aurora/access/calendar", {"all": False, "users": [], "groups": []}]]


def test_the_restore_card_draws_parts_users_command_and_evidentia(tmp_path):
    text = "\n".join(_run(tmp_path, "restore")["restore"])
    assert "[object" not in text and "20261127-230000" in text
    assert "bk.part.config" in text and "👤 anna" in text
    assert "sudo aurora-root restore --apply 20261127-230000" in text
    assert "sudo aurora-root restore --evidentia 20261127-233000" in text and "rs.here" in text


def test_the_chat_s_tabs_hide_a_closed_feature(tmp_path):
    out = _run(tmp_path, "chat_tabs")
    assert sum("cat-chip" in l for l in out["all"]) == 3
    assert any("[hidden]" in l for l in out["alone"][:1])                                         # alone: no tabs


def test_the_claude_sign_in_box_is_not_redrawn_away():
    """C757 (owner, 27 Nov: «la pagina si ricarica senza che riesca ad inserire il codice»): the sign-in's two calls are
    quiet, and a page holding a step half done ([data-busy]) is never redrawn by «aurora:acted»."""
    acc = (ROOT / "webui" / "js" / "modules" / "accounts.js").read_text(encoding="utf-8")
    assert '/login`, { method: "POST", quiet: true })' in acc and '/code`, { method: "POST", quiet: true,' in acc
    assert 'box.dataset.busy = "1";' in acc
    main = (ROOT / "webui" / "js" / "main.js").read_text(encoding="utf-8")
    guard = main.index('if (section?.querySelector("[data-busy]")) return;')
    assert main.index('addEventListener("aurora:acted"') < guard < main.index("await v.enter();", guard)


def test_evidentia_s_folder_picker_draws_roots_folders_and_walks(tmp_path):
    out = _run(tmp_path, "sources")
    text = "\n".join(out["before"])
    assert "[object" not in text and "evd.src_root_nas" in text and "📁 DOJ" in text and "📁 EFTA" in text
    assert "evd.src_read" in text and "evd.src_images" in text
    assert out["sent"] == []                                       # walking reads, it never starts anything
    user = "\n".join(out["user"])
    assert "evd.nas_title" in user and "evd.nas_go" in user and "evd.nas_ok" in user   # a user's own NAS, said connected
    assert "evd.nas_title" not in text                              # the admin's NAS: set at install, no form


def test_the_desktop_window_shows_aurora_s_line_as_notifications(tmp_path):
    """C758: Aurora Desktop has notifications but no Web Push: the line's notification is shown, a call's ring is not."""
    out = _run(tmp_path, "line")
    assert out["mode"] is True and out["state"] == "on"
    assert out["shown"] == [["Aurora", "Il backup è finito", "backup"]]


def test_a_case_is_shared_by_its_maker_and_only_worked_in_by_a_member(tmp_path):
    """Owner, 27 Nov: the maker sees 👥 Condividi with the people who may use Evidentia; a member sees it is shared."""
    out = _run(tmp_path, "case_share")
    mine, theirs = "\n".join(out["mine"]), "\n".join(out["theirs"])
    assert "[object" not in mine + theirs
    assert "evd.share · 1" in mine and "evd.rename" in mine and "👤 bob" in mine and "evd.share_save" in mine
    assert "evd.shared_with_me" in theirs and "evd.rename" not in theirs and "evd.delete" not in theirs

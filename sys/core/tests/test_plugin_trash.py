# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""A plugin deleted goes to the trash and comes back whole (owner, 2026-10-08)."""
import json

import pytest

from aurora import plg_trash


@pytest.fixture
def plugins(cfg, tmp_path):
    d = tmp_path / "plugins"
    for name in ("xgaudit", "self"):
        (d / name).mkdir(parents=True)
        (d / name / "plugin.json").write_text(json.dumps({"name": name}))
    cfg.values.update(AURORA_PLUGINS_DIR=str(d))
    return d


def test_a_deleted_plugin_is_in_the_trash_and_comes_back_whole(cfg, plugins):
    out = plg_trash.delete(cfg, "xgaudit")
    assert not (plugins / "xgaudit").exists()
    items = plg_trash.trashed(cfg)
    assert [i["name"] for i in items] == ["xgaudit"] and items[0]["id"] == out["trash"]
    assert plg_trash.restore(cfg, out["trash"]) == {"name": "xgaudit"}
    assert (plugins / "xgaudit" / "plugin.json").is_file() and not (plugins / "xgaudit" / ".deleted.json").exists()
    assert plg_trash.trashed(cfg) == []


@pytest.mark.parametrize("name", ["self", "../etc", "nope"])
def test_her_repair_plugin_a_path_or_a_missing_one_is_not_deleted(cfg, plugins, name):
    with pytest.raises(plg_trash.TrashError):
        plg_trash.delete(cfg, name)


def test_a_restore_never_overwrites_a_plugin_of_the_same_name(cfg, plugins):
    out = plg_trash.delete(cfg, "xgaudit")
    (plugins / "xgaudit").mkdir()
    (plugins / "xgaudit" / "plugin.json").write_text("{}")
    with pytest.raises(plg_trash.TrashError, match="esiste già"):
        plg_trash.restore(cfg, out["trash"])

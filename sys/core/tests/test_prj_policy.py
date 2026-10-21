# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""How Aurora handles a project (prj_policy): chosen when it is made — the local model only from the first touch,
never published."""
from aurora import prj_policy as P


class _Agent:
    def __init__(self, cfg):
        self.cfg, self.local_only = cfg, False


def test_the_default_is_the_old_way_and_a_choice_is_kept(cfg):
    assert P.load(cfg, "prova") == {"models": "cloud", "publish": True}
    assert P.save(cfg, "brevetto", {"models": "local", "publish": False}) == {"models": "local", "publish": False}
    assert P.load(cfg, "brevetto") == {"models": "local", "publish": False}
    assert P.load(cfg, "../x") == P.DEFAULT                                       # not a project's name


def test_a_local_project_makes_the_run_local_and_a_private_one_is_never_published(cfg):
    P.save(cfg, "brevetto", {"models": "local", "publish": False})
    a, seen = _Agent(cfg), []
    emit = lambda e, p: seen.append(e)                                            # noqa: E731
    assert P.guard(a, "web", "web_search", {"query": "x"}, emit) == "" and not a.local_only   # not a project's
    assert P.guard(a, "cad", "cad_build", {"project": "brevetto", "name": "m"}, emit) == ""
    assert a.local_only and seen == ["agent.local"]                               # from this call on
    assert P.guard(a, "projects", "project_publish", {"name": "brevetto"}, emit).startswith("REFUSED")
    assert P.guard(a, "projects", "project_push", {"name": "brevetto"}, emit).startswith("REFUSED")
    P.save(cfg, "aperto", {})
    assert P.guard(_Agent(cfg), "projects", "project_publish", {"name": "aperto"}, emit) == ""


def test_a_goal_that_names_a_local_project_is_local_from_its_first_step(cfg):
    base = cfg.path("AURORA_PROJECTS_DIR")
    for n in ("brevetto", "brevetto-2"):
        (base / n).mkdir(parents=True, exist_ok=True)
    P.save(cfg, "brevetto-2", {"models": "local"})
    a = _Agent(cfg)
    P.at_start(a, "nel progetto brevetto scrivi il riassunto", lambda e, p: None)
    assert not a.local_only                                                       # «brevetto» is not «brevetto-2»
    P.at_start(a, "nel progetto «brevetto-2» scrivi il riassunto", lambda e, p: None)
    assert a.local_only

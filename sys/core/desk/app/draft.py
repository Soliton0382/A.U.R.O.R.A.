# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""N152 version 1: from a recorded demonstration to a draft procedure (design bozza 7 §4, bozza 8 §4), no model.

What the recorder sees on Wayland (M335): text by offsets, menus by focus, a shortcut only by its effect. So:
- typing: a run of insertions in an editable field; its value is the text at the end of the run (before the program
  replaces it: KCalc's result);
- a menu: the last item focused before the popup closes counts only if an effect follows within EFFECT_S;
- a save by shortcut: the window's name loses its «*» with no menu before it -> a key step, flagged to confirm;
- a field replaced by the program right after typing (a calculator's =) -> an Enter key step, flagged, and a read.
Every typed value becomes a parameter; its example is kept apart and dropped unless the owner keeps it (Q5).
Flags are returned apart from the procedure: the closed format (library_check) has no place for them."""
import re

EFFECT_S = 1.0          # an effect within this time after a menu closes makes the menu an action
RUN_GAP_S = 0.35        # a whole-field replacement after this pause is the program's, not the owner's typing
LONG_TEXT = 200         # bozza 8 §4: longer values become «ask each time», never an example
NOISY = re.compile(r"(QMLTYPE_|_QML_\d)")
GENERIC = re.compile(r"\.Q[A-Z]\w*$")                 # an id ending in a bare Qt class name


def id_end(full: str) -> str:
    """The stable part of a Qt object path: without the leading «QApplication.<Window>#<n>»; '' for QML ids."""
    if not full or NOISY.search(full):
        return ""
    m = re.match(r"^QApplication\.[^.]+#\d+(\..*)$", full)
    return m.group(1) if m else ("." + full if not full.startswith(".") else full)


def private_looking(name: str) -> bool:
    """A name that may carry the owner's data: a file name, a path, an address, a long text (bozza 8 §4)."""
    return bool(name) and (bool(re.search(r"[/\\@]|\.\w{1,5}\b", name)) or len(name) > 60)


def target(ev: dict, loc: str) -> tuple:
    """(target, flags) for an event's element."""
    t = {"role": ev["role"]}
    e = id_end(ev.get("id") or "")
    flags = []
    if e:
        t["id_end"] = e
        if GENERIC.search(e) and ev.get("name"):        # .QAction, .QToolButton…: not unique without the name
            t["name"] = {loc: ev["name"]}
            if private_looking(ev["name"]):
                flags.append(f"ancora per nome che sembra un dato tuo: «{ev['name'][:40]}» (generalizza o togli)")
    elif ev.get("name"):
        t["name"] = {loc: ev["name"]}
        if private_looking(ev["name"]):
            flags.append(f"ancora per nome che sembra un dato tuo: «{ev['name'][:40]}» (generalizza o togli)")
    else:
        flags.append(f"elemento {ev['role']} senza id e senza nome: ancora debole")
    return t, flags


class _Run:
    def __init__(self, ev):
        self.path, self.ev, self.t0, self.t1 = ev["path"], ev, ev["t"], ev["t"]
        self.value = ev.get("text_after", "")


def build(events: list, program: dict, loc: str = "it", network: bool = True, launch_params: dict = None) -> dict:
    """Return {"procedure": dict, "examples": {param: value}, "flags": [str]} (the procedure without its id)."""
    steps, examples, flags = [], {}, []
    pcount = [0]
    cls_write = "esce" if network else "scrive in locale"

    def new_param(value: str) -> str:
        pcount[0] += 1
        name = f"p{pcount[0]}"
        if len(value) > LONG_TEXT:
            flags.append(f"{{{name}}}: testo lungo ({len(value)} caratteri), sarà chiesto ogni volta")
        else:
            examples[name] = value
        return name

    run = None
    menu_top = last_item = None
    menu_closed_at = None
    pending_menu = None
    replaced_fields = []
    quiet = {}                                           # path -> time until which edits are the program's
    focused = set()                                      # paths that had the focus during the recording
    chain = []                                           # menu items focused in popups, in order
    opener = None                                        # the menu button touched right before a popup
    last_button = None
    explained_until = -1.0                               # an effect already explained by a menu just emitted

    def close_run():
        nonlocal run
        if run is not None and run.value.strip():
            t, f = target(run.ev, loc)
            flags.extend(f)
            p = new_param(run.value.rstrip("\n"))
            steps.append({"do": "type", "target": t, "text": "{" + p + "}", "class": cls_write, "_t": run.t0})
        run = None

    for ev in events:
        kind, detail = ev["kind"], str(ev.get("detail", ""))
        # a menu that closed: the last item counts only if an effect follows
        if pending_menu and ev["t"] - pending_menu["closed"] > EFFECT_S:
            pending_menu = None
        if kind == "Object:TextChanged" and ev.get("editable") and not ev.get("read_only"):
            if ev["t"] <= quiet.get(ev["path"], -1):
                continue                                 # the program writing its result in the field
            if pending_menu:                             # the menu's effect (Kate adds a line end when saving)
                close_run()
                _emit_menu(pending_menu, steps, loc, flags, cls_write)
                explained_until = ev["t"] + EFFECT_S
                quiet[ev["path"]] = ev["t"] + RUN_GAP_S
                pending_menu = None
                continue
            if ev.get("top_role") == "dialog" and ev["path"] not in focused:
                continue                                 # a dialog's own text, written before it has the focus
            if run is not None and ev["path"] == run.path:
                whole = detail.startswith("delete") and ev.get("n", 0) >= len(run.value) > 0
                if whole and ev["t"] - run.t1 > RUN_GAP_S:
                    close_run()                          # the program replaced the field: an effect
                    replaced_fields.append(ev)
                    quiet[ev["path"]] = ev["t"] + RUN_GAP_S
                    steps.append({"do": "key", "keys": "Enter", "class": cls_write, "_t": ev["t"],
                                  "_flag": "tasto non visto: dedotto dal campo sostituito dal programma"})
                    continue
                run.value, run.t1 = ev.get("text_after", run.value), ev["t"]
            elif detail.startswith("insert"):
                close_run()
                run = _Run(ev)
            continue
        if kind == "Focus:Focus" and ev["role"] == "menu item":
            close_run()
            if re.search(r"\.QMenuBar\.[^.]+$", ev.get("id") or ""):
                menu_top, last_item, chain = ev, None, []
            else:
                last_item = ev
                chain.append(ev)
            continue
        if kind == "Focus:Focus":
            focused.add(ev["path"])
            continue
        if ev["role"] in ("button menu", "push button menu") and kind == "Object:PropertyChange":
            last_button = ev
            continue
        if kind == "Object:StateChanged" and detail == "showing" and ev["role"] == "popup menu" and ev.get("value") == 1:
            if menu_top is None and not chain and last_button is not None and ev["t"] - last_button["t"] < 0.2:
                opener = last_button
            continue
        if kind in ("Object:StateChanged", "Window:Activate") and ev["role"] == "dialog" and \
                (kind == "Window:Activate" or (detail == "showing" and ev.get("value") == 1)):
            if pending_menu:                             # a dialog appeared: the menu's effect
                close_run()
                _emit_menu(pending_menu, steps, loc, flags, cls_write)
                explained_until = ev["t"] + EFFECT_S
                pending_menu = None
            continue
        if ev["role"] == "dialog" and ((kind == "Object:StateChanged" and detail == "showing" and ev.get("value") == 0)
                                       or kind == "Window:Deactivate"):
            if run is not None and run.ev.get("top") == ev.get("top"):
                close_run()                              # the dialog closed right after typing in it: Enter
                steps.append({"do": "key", "keys": "Enter", "class": cls_write, "_t": ev["t"],
                              "_flag": "tasto non visto: Invio dedotto dal dialogo chiuso dopo che hai scritto"})
            continue
        if kind == "Object:StateChanged" and detail == "showing" and ev["role"] == "popup menu" and ev.get("value") == 0:
            if last_item is not None and (menu_top is not None or opener is not None or chain):
                lid = last_item.get("id") or ""
                seen, anc = set(), []
                for c in chain[:-1]:
                    cid = c.get("id") or ""
                    if cid and lid.startswith(cid + ".") and cid not in seen:
                        seen.add(cid)
                        anc.append(c)
                pending_menu = {"top": menu_top, "opener": opener, "ancestors": anc, "item": last_item,
                                "closed": ev["t"]}
            if last_item is not None or menu_top is not None:
                menu_top = last_item = opener = None
                chain = []
            continue
        if kind == "Object:PropertyChange" and detail == "accessible-name" and ev["role"] == "frame":
            before, after = ev.get("name") or "", ev.get("value") or ""
            if pending_menu:
                close_run()
                _emit_menu(pending_menu, steps, loc, flags, cls_write)
                explained_until = ev["t"] + EFFECT_S
                pending_menu = None
            elif "*" in before and "*" not in after and ev["t"] > explained_until:
                close_run()
                steps.append({"do": "key", "keys": "Ctrl+S", "class": cls_write, "_t": ev["t"],
                              "_flag": "scorciatoia non vista: dedotta dal titolo senza «*» (salvato)"})
            continue
    close_run()
    if pending_menu:
        flags.append(f"menu «{pending_menu['item'].get('name')}» chiuso senza un effetto visto: non messo")
    if replaced_fields:
        t, f = target(replaced_fields[-1], loc)
        steps.append({"do": "read", "target": t, "into": "risultato", "class": "legge", "_t": 1e9})
    out_steps = []
    for i, s in enumerate(steps, 1):
        if s.get("_flag"):
            flags.append(f"passo {i}: {s['_flag']}")
        out_steps.append({k: v for k, v in s.items() if not k.startswith("_")} | {"n": i})
    params = {}
    args = []
    for a in program.get("args", []):                    # paths become parameters, never stored (bozza 8 §4, R8)
        if a.startswith("/") or a.startswith("~"):
            name = f"f{len([x for x in args if x.startswith('{f')]) + 1}"
            params[name] = {"kind": "path"}
            args.append("{" + name + "}")
        else:
            args.append(a)
    for p in sorted({re.search(r"\{(\w+)\}", s.get("text", "")).group(1) for s in out_steps if s.get("text")}):
        params[p] = {"kind": "text", "max": 2000}
    for name, spec in (launch_params or {}).items():
        params[name] = spec
    proc = {"format": 1, "title": {loc: "Bozza da una dimostrazione"}, "os": "linux",
            "program": {"name": program["name"], "package": program.get("package", program["name"]),
                        "versions": {"min": program.get("version") or "sconosciuta"}, "network": network,
                        "launch": {"exe": program["exe"], "args": args}},
            "params": params, "steps": [_order(s) for s in out_steps]}
    return {"procedure": proc, "examples": examples, "flags": flags}


def _emit_menu(pm: dict, steps: list, loc: str, flags: list, cls_write: str) -> None:
    item, f2 = target(pm["item"], loc)
    if pm.get("top") is not None:                        # a menu of the menu bar
        top, f1 = target(pm["top"], loc)
        flags.extend(f1)
        steps.append({"do": "open_menu", "target": top, "class": "legge", "_t": pm["closed"]})
        item["offscreen_ok"] = True
    elif pm.get("opener") is not None:                   # a menu button (Dolphin's «Apri menu», opened by F10)
        op, f1 = target(pm["opener"], loc)
        flags.extend(f1)
        steps.append({"do": "open_menu", "target": op, "class": "legge", "_t": pm["closed"]})
    else:
        flags.append("menu aperto da un tasto non visto: aprilo tu nell'anteprima")
    for a in pm.get("ancestors", []):
        at, fa = target(a, loc)
        flags.extend(fa)
        steps.append({"do": "open_menu", "target": at, "class": "legge", "_t": pm["closed"]})
    flags.extend(f2)
    steps.append({"do": "press", "target": item, "class": cls_write, "_t": pm["closed"]})


def _order(s: dict) -> dict:
    keys = ["n", "do", "target", "text", "keys", "into", "class"]
    return {k: s[k] for k in keys if k in s}

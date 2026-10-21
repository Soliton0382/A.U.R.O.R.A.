# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
"""The circuits plugin: a circuit checked and turned into a netlist (no line written from a value), its probes and
control block; drawn (schemdraw) and simulated (ngspice) where the plugin's own libraries and ngspice are there."""
import shutil
import sys
from pathlib import Path

import pytest

CIRC = Path(__file__).resolve().parents[2] / "plugins" / "circuits"
sys.path.insert(0, str(CIRC))
import circ_net as N  # noqa: E402
import circ_sim as S  # noqa: E402

RC = [{"id": "V1", "kind": "voltage_source", "value": "DC 0 AC 1", "nodes": ["in", "gnd"]},
      {"id": "R1", "kind": "resistor", "value": "1k", "nodes": ["in", "out"]},
      {"id": "C1", "kind": "capacitor", "value": "1µ", "nodes": ["out", "0"], "dir": "down"}]


def test_a_circuit_becomes_its_netlist_with_ground_wires_and_models():
    parts = N.check(RC + [{"kind": "wire", "nodes": ["out", "o2"]},
                          {"id": "D1", "kind": "led", "nodes": ["o2", "0"]},
                          {"id": "Bias", "kind": "current_source", "value": "DC 1m", "nodes": ["0", "out"]}])
    net, nodes = N.netlist(parts, "rc")
    assert "V1 in 0 DC 0 AC 1" in net and "C1 out 0 1u" in net            # gnd is 0, µ is u
    assert "D1 out 0 DLED" in net and ".model DLED D(" in net               # the wire joined o2 to out
    assert "IBias 0 out DC 1m" in net and nodes == ["0", "in", "out"]       # the SPICE letter put before the id


def test_no_line_of_the_netlist_comes_from_a_value():
    for bad in ("1k\n.control\nshell rm x", ".include /etc/passwd", "1k; shell", "DC 5 `x`"):
        with pytest.raises(N.CircuitError):
            N.check([{**RC[1], "value": bad}])
    with pytest.raises(N.CircuitError):
        N.check([{"id": "Q1", "kind": "npn", "nodes": ["c", "b", "e"], "model": "X NPN(Bf=1)\n.control"}])
    with pytest.raises(N.CircuitError):
        N.netlist(N.check([RC[1]]))                                         # no ground
    net, _ = N.netlist(N.check([{**RC[1], "label": "R d'ingresso"}, RC[0]]), "Filtro, fc ≈ 1 kHz\n.control")
    assert net.splitlines()[0] == "* Filtro, fc ≈ 1 kHz .control" and len(net.splitlines()) == 3   # C374: a title
    with pytest.raises(N.CircuitError):
        N.check([RC[1], {**RC[1]}])                                         # the same id twice


def test_probes_and_the_control_block():
    parts = N.check(RC)
    _, nodes = N.netlist(parts)
    vecs = S.vectors([], nodes, parts)
    assert vecs == [("V(in)", "v(in)"), ("V(out)", "v(out)")]              # the named nodes when none asked
    assert S.vectors(["I(V1)"], nodes, parts) == [("I(V1)", "-i(v1)")]     # what the source gives
    with pytest.raises(S.SimError):
        S.vectors(["nowhere"], nodes, parts)
    deck, plan = S.control([{"type": "op"}, {"type": "ac", "points": 10, "start": 1, "stop": "1meg"}], vecs,
                           [{"name": "f3db", "analysis": "ac", "expr": "WHEN vdb(out)=-3.0103"}])
    assert "ac dec 10 1 1meg" in deck and "meas ac f3db WHEN vdb(out)=-3.0103" in deck
    assert [p["type"] for p in plan] == ["op", "ac"] and plan[1]["file"].endswith(".txt")
    with pytest.raises(S.SimError):
        S.control([{"type": "tran", "step": "1u; shell", "stop": "1m"}], vecs, [])
    assert S.op_values("in = 5.0e+00\nf3db = 1.59e+02\n", [{"name": "f3db"}]) == {"in": 5.0}


def test_a_schematic_drawn_with_its_nodes_where_they_meet(tmp_path):
    pytest.importorskip("schemdraw")
    import circ_draw as D
    d = D.draw(N.check(RC), "RC")
    assert set(D.save(d, tmp_path)) == {"schematic.svg", "schematic.pdf", "schematic.png"}
    assert "Ω" in (tmp_path / "schematic.svg").read_text(encoding="utf-8") or (tmp_path / "schematic.png").stat().st_size > 5000
    assert D._value({"kind": "resistor", "value": "4.7k"}) == "4.7 kΩ" and D._value({"kind": "capacitor", "value": "100u"}) == "100 µF"


@pytest.mark.skipif(not shutil.which("ngspice"), reason="ngspice not on this machine")
def test_the_rc_cut_off_simulated_is_the_one_computed(tmp_path):
    import math
    parts = N.check(RC)
    net, nodes = N.netlist(parts)
    deck, _ = S.control([{"type": "ac", "points": 50, "start": 1, "stop": "100k"}], S.vectors(["out"], nodes, parts),
                        [{"name": "f3db", "analysis": "ac", "expr": "WHEN vdb(out)=-3.0103"}])
    text = S.run(shutil.which("ngspice"), tmp_path, net + deck)
    assert abs(S.measured(text, [{"name": "f3db"}])["f3db"] - 1 / (2 * math.pi * 1e3 * 1e-6)) < 0.5


def test_the_board_says_what_would_lie_on_what():
    import circ_layout as L
    b = L.Board()
    b.add_part((0, 0), (0, 3))                                                # a part, upright
    b.points[(0, 3)] = "vcc"
    assert b.part_cost((0, 3), (0, 0), "vcc", "x") > 0                       # back over it
    assert b.part_ok((0, 3), (3, 3), "vcc", "b")                              # from its end, across: room
    assert not b.wire_ok([(-1, 3), (2, 3)], "in")                             # a wire over another node's point
    assert not b.wire_ok([(-1, 1.5), (1, 1.5)], "in")                         # through a part's body: no
    b.add_line((5, 0), (5, 3), "x")
    assert b.wire_ok([(4, 1.5), (6, 1.5)], "in")                              # across another wire: allowed
    assert L.crosses((0, -1, 0, 1), (-1, 0, 1, 0)) and not L.crosses((0, 0, 0, 1), (0, 0, 1, 0))


def test_a_circuit_written_as_a_netlist_is_drawn_with_nothing_on_anything(tmp_path):
    # C375: parts in netlist order (supply, divider, collector, transistor, coupling) — drawn on top of each other
    pytest.importorskip("schemdraw")
    import circ_draw as D
    import circ_layout as L
    seen = []
    real = L.Board.add_line
    L.Board.add_line = lambda self, a, b, n: (seen.append((self, a, b, n)), real(self, a, b, n))[1]
    try:
        parts = N.check([{"id": "V1", "kind": "voltage_source", "value": "DC 12", "nodes": ["vcc", "0"]},
                         {"id": "R1", "kind": "resistor", "value": "100k", "nodes": ["vcc", "b"], "dir": "down"},
                         {"id": "R2", "kind": "resistor", "value": "13k", "nodes": ["b", "0"], "dir": "down"},
                         {"id": "RC", "kind": "resistor", "value": "6.8k", "nodes": ["vcc", "c"], "dir": "down"},
                         {"id": "Q1", "kind": "npn", "nodes": ["c", "b", "e"]},
                         {"id": "RE", "kind": "resistor", "value": "680", "nodes": ["e", "0"], "dir": "down"},
                         {"id": "VIN", "kind": "sine_source", "value": "SIN(0 50m 1k)", "nodes": ["in", "0"]},
                         {"id": "CIN", "kind": "capacitor", "value": "10u", "nodes": ["in", "b"]},
                         {"id": "COUT", "kind": "capacitor", "value": "10u", "nodes": ["c", "out"]},
                         {"id": "RL", "kind": "resistor", "value": "100k", "nodes": ["out", "0"], "dir": "down"}])
        D.draw(parts)
    finally:
        L.Board.add_line = real
    board = seen[-1][0]
    lines = board.lines
    for i, s in enumerate(lines):                                             # no line along another node's line
        assert not any(L.collinear(s, t) and (s[4] is None or t[4] is None or s[4] != t[4])
                       for t in lines[i + 1:]), s
        assert not any(n != s[4] and s[4] is not None and L.on_line(pt, s) for pt, n in board.points.items()), s

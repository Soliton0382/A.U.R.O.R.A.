# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
import json

from aurora.kno_acquire import MAP_FILE, domain_of, parse_atom
from aurora.sol_schema import load_taxonomy

ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2104.09864v5</id>
    <title>RoFormer: Enhanced Transformer with
      Rotary Position Embedding</title>
    <summary>  Position encoding recently has shown effective... </summary>
    <link href="http://arxiv.org/abs/2104.09864v5" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/2104.09864v5" rel="related" type="application/pdf"/>
    <arxiv:primary_category term="cs.CL" scheme="http://arxiv.org/schemas/atom"/>
  </entry>
</feed>"""


def test_parse_atom():
    [e] = parse_atom(ATOM)
    assert e.arxiv_id == "2104.09864"
    assert e.title == "RoFormer: Enhanced Transformer with Rotary Position Embedding"
    assert e.abstract.startswith("Position encoding") and e.pdf.endswith("2104.09864v5") and e.category == "cs.CL"


def test_domain_map_exact_prefix_default_and_valid():
    table = json.loads(MAP_FILE.read_text())["map"]
    assert domain_of("cs.CL", table) == "artificial_intelligence"
    assert domain_of("cs.DB", table) == "computer_science"
    assert domain_of("cond-mat.mtrl-sci", table) == "materials"
    assert domain_of("cond-mat.str-el", table) == "condensed_matter"
    assert domain_of("q-alg", table) == "general"
    taxonomy = load_taxonomy()
    assert all(d in taxonomy and not taxonomy[d].get("memory") for d in table.values())


def test_an_original_is_accepted_only_with_the_same_title():
    from aurora.kno_acquire import same_title
    assert same_title("Attention Is All You Need", "Attention is all you need")
    assert same_title("Adam: A Method for Stochastic Optimization", "Adam: A Method for Stochastic Optimization")
    assert not same_title("Rotary Position Embedding", "RoFormer: Enhanced Transformer with Rotary Position Embedding")
    assert not same_title("Batch Normalization", "Batch Normalization: Accelerating Deep Network Training by Reducing Internal Covariate Shift")
    assert not same_title("", "Anything")

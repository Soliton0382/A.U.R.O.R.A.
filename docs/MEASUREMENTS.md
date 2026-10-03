# Measurements behind the architecture

Every design decision in this repository must point to a row of this file.
Measured on the production host: AMD Ryzen 7 7700X (16 threads), 58 GiB RAM,
2x RTX 5060 Ti 16 GB, ext4 on NVMe (916 GB). Data: the knowledge store of the
previous Aurora installation (373,214 chunks, nomic-embed-text-v1 768-d vectors).

## M1 — Filesystem ceiling for one-file-per-soliton

| | |
|---|---|
| filesystem | ext4 |
| inodes, total | **61,030,400** |
| inodes in use | 2,403,785 |

One file per soliton consumes one inode. On this disk the absolute ceiling is
~61 million files for *everything*, so a one-file-per-soliton store cannot
reach hundreds of millions, let alone billions.

## M2 — Where the bytes of a soliton went (previous format, sample of 3,000)

| | KB |
|---|---|
| apparent size of a `.pt` | 18.3 |
| actually allocated on disk | 20.0 |
| of which: text | ~4.0 (22%) |
| of which: embedded `cue` vector | 11.0 (60%) |
| of which: metadata + pickle overhead | ~3.3 |

## M3 — Storage format, 20,000 real solitons (text + metadata, no vectors)

| format | write | read 48 at random | disk per soliton | inodes |
|---|---|---|---|---|
| one `.pt` per soliton | 18,651/s | 4.17 ms (warm cache) | 7.77 KB | 1 per soliton |
| SQLite shard (WAL) | **78,312/s** | **0.26 ms** | **4.40 KB** | 1 per shard |

Content-addressed identifiers rejected exact duplicates automatically (0.5% of
the sample).

## M4 — Search scaling (CPU, 16 threads, one query, k=48)

Exact cosine (what the previous installation used):

| vectors | latency | RAM (fp32) |
|---|---|---|
| 373,214 (real) | 46 ms | 1.1 GB |
| 1,000,000 | 97 ms | 2.9 GB |
| 2,000,000 | 175 ms | 5.9 GB |
| 4,000,000 | 339 ms | 11.7 GB |

Linear: ~85 ms and ~2.9 GB per million vectors. Extrapolated to one billion:
~85 s per query and ~2.9 TB of RAM.

Approximate indexes on the real 373,214 vectors (recall measured against exact):

| index | build | latency | recall@48 | bytes/vector |
|---|---|---|---|---|
| HNSW M=32, ef=64 | 106 s | 0.31 ms | 95.1% | 3,328 |
| HNSW M=32, ef=256 | 106 s | 1.06 ms | 99.3% | 3,328 |
| IVF-PQ 2048 cells, 96 B, nprobe=64 | 17 s | 0.67 ms | 69.9% | 104 |
| IVF-PQ nprobe=64 **+ exact re-rank of 384 candidates** | 17 s | ~1 ms | **94.8%** | 104 in RAM |

## M5 — Chunk length in the previous store

| percentile | characters |
|---|---|
| p5 | 2,165 |
| p50 | 4,091 |
| p95 | 4,157 |

Median 1,035 tokens (nomic tokenizer). The encoder was configured at 2,560
tokens: no truncation (1.0% of chunks exceed 2,048 tokens).

## M6 — Chunk size vs retrieval (108 paraphrased questions, pool of 3,108 chunks, nomic)

| chunk | vectors per chunk | r@1 | r@10 | r@48 | MRR |
|---|---|---|---|---|---|
| whole (~1,035 tok) | 1.00 | 5.6 | 18.5 | 33.3 | 10.21 |
| ~512 tok | 2.84 | 7.4 | 20.4 | 35.2 | 12.23 |
| ~256 tok | 4.73 | 9.3 | 17.6 | 38.0 | 12.58 |

Standard error at n=108 around 35% is ~4.6 points: the differences are mostly
within noise. Chunk size is not the main lever.

## M7 — Language of queries vs documents

| | |
|---|---|
| chunks (sample of 4,000) | 3,882 English · 118 Italian |
| benchmark questions | 116 Italian |
| encoder | nomic-embed-text-v1, English-only |

## M8 — Encoder comparison (same 108 Italian questions, same pool of 3,108 chunks)

| encoder | chunk | dim | r@1 | r@10 | r@48 | MRR | embed time |
|---|---|---|---|---|---|---|---|
| nomic-embed-text-v1 (English-only, previous) | whole | 768 | 5.6 | 18.5 | 33.3 | 10.21 | 53 s |
| nomic-embed-text-v1 | ~512 tok | 768 | 7.4 | 20.4 | 35.2 | 12.23 | 58 s |
| Qwen3-Embedding-0.6B (multilingual) | whole | 1024 | 55.6 | 83.3 | 91.7 | 63.91 | 386 s |
| Qwen3-Embedding-0.6B | ~512 tok | 1024 | 47.2 | 68.5 | 76.9 | 54.67 | 418 s |
| **bge-m3 (multilingual)** | **whole** | 1024 | **71.3** | **88.0** | **94.4** | **76.88** | 120 s |
| bge-m3 | ~512 tok | 1024 | 73.1 | 89.8 | 96.3 | 78.67 | 122 s |

The weak retrieval of the previous installation came from the encoder: Italian
questions against 97% English documents (M7) with an English-only model. A
multilingual encoder raises rank-1 from 5.6% to 71.3% on the same data. The gap
is ~14x the standard error.

With bge-m3, ~512-token sub-chunks score within noise of whole ~4,000-character
chunks while costing 2.84x the vectors (M6): whole chunks are kept.

Caveat: pool of 3,108 chunks. The same comparison on the full store is the first
measurement of the new index.

## M9 — The previous retrieval formula on top of a good encoder

Same 108 questions, same pool of 3,108 chunks, bge-m3 as the semantic channel.
Lexical channel = the formula's hashed unigram+bigram log-tf vector (4,096-d).

| method | r@1 | r@10 | r@48 | MRR |
|---|---|---|---|---|
| **semantic only (cosine)** | **71.3** | 88.0 | **94.4** | **76.97** |
| lexical channel only | 6.5 | 8.3 | 13.9 | 7.20 |
| a*z(lex) + (1-a)*z(sem), a=0.1 | 70.4 | 88.9 | 93.5 | 76.62 |
| same, a=0.2 | 70.4 | 87.0 | 93.5 | 76.12 |
| same, a=0.3 | 64.8 | 84.3 | 90.7 | 71.74 |
| same, a=0.6 (previous production weight) | 23.1 | 44.4 | 61.1 | 29.63 |
| semantic, z-score computed within each domain | 38.0 | 62.0 | 75.9 | 46.62 |
| formula a=0.2, z within domain | 34.3 | 62.0 | 75.0 | 43.69 |

Italian questions share almost no words with English documents, so the lexical
channel carries no signal here. Normalizing scores *within* each domain and then
ranking globally lets weak chunks of small domains overtake strong ones.

## M10 — Domain separation (bge-m3, same data)

| search space | domain chosen correctly | r@1 | r@10 | r@48 | MRR |
|---|---|---|---|---|---|
| whole pool | — | 71.3 | 88.0 | 94.4 | 76.88 |
| **only the true domain of the source (oracle)** | 100% | **86.1** | 97.2 | **98.1** | **89.48** |
| top-1 domain by centroid similarity | 36% | 30.6 | 35.2 | 35.2 | 32.07 |
| top-2 domains | 47% | 38.0 | 45.4 | 46.3 | 40.57 |
| top-3 domains | 56% | 45.4 | 53.7 | 55.6 | 48.51 |
| top-5 domains | 68% | 52.8 | 63.0 | 64.8 | 56.39 |

Domain separation is worth +14.8 points of rank-1 **when the domain is right**.
A wrong domain filter is far worse than no filter. Consequence for the design:
search globally, then group the results by domain for the per-domain summaries;
use a domain prediction only as a soft boost, and only once its accuracy is
measured above the break-even point.

## M11 — Recall vs vault size (bge-m3, nested pools, 108 Italian questions)

Pools are nested (3,108 ⊂ 10k ⊂ 30k ⊂ 100k chunks of the previous store).
"Document" = the right source document is among the first k (any of its chunks).

| pool | chunk r@1 | doc r@1 | chunk r@48 | doc r@48 | doc r@100 | sibling chunks of the source in pool (median) |
|---|---|---|---|---|---|---|
| 3,108 | 71.3 | 73.1 | 94.4 | 94.4 | 94.4 | 0 |
| 10,000 | 67.6 | 71.3 | 88.9 | 88.9 | 92.6 | 1 |
| 30,000 | 50.9 | 60.2 | 84.3 | 85.2 | 88.0 | 2 |
| 100,000 | 39.8 | 58.3 | 80.6 | 81.5 | 84.3 | 6 |

At 100k, 38.5% of the rank-1 misses are another chunk of the same document.
Document recall@48 still falls ~8.5 points per tenfold growth of the pool.

Dense ceiling at 100k (document among the first k): k=48 81.5, 100 84.3,
200 87.0, 300 88.9, 500 90.7, 1000 94.4.

Embedding throughput: ~26 chunks/s per GPU (RTX 5060 Ti, fp16, batch 8, up to
2,560 tokens); ~2.8 GB VRAM per GPU while encoding.

## M12 — Re-ranker (bge-reranker-v2-m3, top-100 dense candidates, Italian query)

| pool | r@1 | r@10 | r@48 | s/query |
|---|---|---|---|---|
| 3,108 | 85.2 | 90.7 | 92.6 | 4.1 |
| 100,000 | 56.5 | 79.6 | 82.4 | 3.7 |

Score separation at 3,108: true chunk median 0.70, other candidates p90 0.02,
p99 0.18. At 100k the others' p99 reaches 0.71: in a large pool many "wrong"
candidates are genuinely pertinent (siblings, same topic). A fixed relevance
threshold cannot be set from single-label data.

## M13 — Domains as a search filter

| | top-1 | top-3 | top-5 |
|---|---|---|---|
| domain of a **chunk**, linear classifier on bge-m3 vectors (10k held out) | 70.0% | 92.9% | — |
| domain of a **question**, same classifier | 23.1% | 46.3% | 57.4% |
| domain of a question, nearest domain centroid (M10) | 36% | 56% | 68% |

Main confusions on chunks: computer_science→artificial_intelligence 17%,
condensed_matter→physics 21%, society→artificial_intelligence 30%,
biomedicine→artificial_intelligence 23%, statistics→mathematics 14%.

Document r@48 at 100k: flat 81.5 · oracle domain 92.6 · classifier hard top-3
39.8 · top-5 50.0 · soft boost λ=0.02 61.1. Hierarchical search (document
vector = mean of its chunks) is also worse than flat: top-100 documents 71.3.

Consequence: domains organize the *results* (grouping, per-domain summaries),
where each soliton carries the label of its source. They do not filter the search.

## M14 — Query variants at 100k (document recall)

| query | r@1 | r@10 | r@48 | r@100 |
|---|---|---|---|---|
| Italian question | 58.3 | 72.2 | 81.5 | 84.3 |
| **question translated to English** (qwen2.5-7b) | 63.9 | 73.1 | 82.4 | 86.1 |
| hypothetical English passage (HyDE) | 51.9 | 64.8 | 74.1 | 79.6 |
| Italian + HyDE (mean vector) | 59.3 | 71.3 | 81.5 | 87.0 |
| **English question + re-ranker, English query** | **77.8** | **83.3** | 84.3 | — |
| English question + re-ranker, Italian query | 68.5 | 80.6 | 84.3 | — |

HyDE invents specifics and drifts. Translating the question helps retrieval
a little and the re-ranker a lot.

## M15 — Re-ranker cost vs candidates (100k pool, English query)

| re-ranker input | candidates | r@1 | r@10 | r@48 | s/query (1 GPU) |
|---|---|---|---|---|---|
| 2,048 tokens | 100 | 77.8 | 83.3 | 84.3 | 3.64 |
| 1,024 tokens | 100 | 76.9 | 83.3 | 84.3 | 2.00 |
| 1,024 tokens | 300 | **79.6** | **87.0** | **87.0** | 5.98 |

Dense ceiling with the English query: k=100 86.1, k=300 89.8.
Truncating the re-ranker input to 1,024 tokens halves its cost for ~1 point.
The re-ranker cannot exceed the candidates' ceiling; the ceiling rises with the
number of candidates at a linear cost.

## M16 — Approximate indexes with bge-m3 vectors (100k, English query, document recall)

Single-query latency on CPU (16 threads). IVF lists = 1,024.

| index | doc r@100 | doc r@300 | latency | bytes/vector |
|---|---|---|---|---|
| exact, fp32 | 86.1 | 89.8 | 21.2 ms | 4,096 |
| **HNSW, fp16 storage, M=32, ef=300** | 85.2 | **88.9** | **1.1 ms** | 2,304 |
| HNSW, fp32, ef=300 | 85.2 | 88.9 | 0.6 ms (batched) | 4,352 |
| IVF-SQ8, nprobe 32 / 64 / 128 | 75.0 / 78.7 / 82.4 | 76.9 / 81.5 / 85.2 | 0.4 / 0.6 / 1.1 ms | 1,032 |
| IVF-PQ 128 B, nprobe 128, exact re-rank of 2,400 | 82.4 | 85.2 | — | 136 |
| IVF-PQ 256 B, nprobe 128, re-rank 2,400 | 82.4 | 85.2 | 2.3 ms | 264 |
| IVF-PQ 256 B, nprobe 256, re-rank 4,800 | 86.1 | 89.8 | 4.1 ms | 264 |

With 1,024-d vectors the loss of IVF comes from the partition, not from the
compression: PQ-128, PQ-256 and SQ8 lose the same at equal nprobe. The cells
holding the pertinent chunks of a question are many and far from the question;
matching exact search requires probing 25% of the cells.

Capacity on this host (58 GB RAM, 341 GB free disk, ~6 KB per soliton on disk
for text + fp16 vector): HNSW-fp16 needs ~2.3 GB of RAM per million solitons,
so ~10-15 million solitons stay near-exact in memory; the disk holds ~55
million. Beyond that the architecture must shard across hosts or accept the
IVF-PQ loss.

## M17 — Whole previous store (373,814 chunks), bge-m3, document recall

Nested pools, the 100k pool of M11 extended at random.

| pool | query | r@1 | r@10 | r@48 | r@100 | r@300 |
|---|---|---|---|---|---|---|
| 100,000 | English | 63.9 | 73.1 | 82.4 | 86.1 | 89.8 |
| 200,000 | English | 57.4 | 71.3 | 79.6 | 84.3 | 88.0 |
| 373,814 | English | 56.5 | 69.4 | 78.7 | 80.6 | 88.0 |
| 373,814 | Italian | 52.8 | 66.7 | 77.8 | 79.6 | 86.1 |
| **373,814, English + re-ranker (300 cand., 1,024 tok)** | | **68.5** | **81.5** | **85.2** | — | — |

Re-ranker: 5.9 s per query on one GPU. From 100k to 373k (x3.7) document
recall@300 loses 1.8 points and @48 3.7: slower than the 100k extrapolation of
M11 (~8.5 points per tenfold).

## RETRACTION of M8, Qwen3-Embedding-0.6B row

The 55.6% rank-1 of M8 was caused by the custom query instruction I wrote and
right padding, not by the model. With the official prompt ("Instruct: Given a
web search query, retrieve relevant passages that answer the query\nQuery:")
and left padding, same 3,108 pool, chunk level:

| encoder | query | r@1 | r@10 | r@48 | MRR | embed 3,108 chunks | VRAM |
|---|---|---|---|---|---|---|---|
| bge-m3 | Italian | 71.3 | 88.0 | 94.4 | 76.88 | 120 s | ~2.8 GB |
| **Qwen3-Embedding-0.6B** | Italian | **76.9** | 89.8 | 94.4 | 81.56 | 314 s | 2.5 GB |
| **Qwen3-Embedding-0.6B** | English | **79.6** | 92.6 | 95.4 | 84.56 | 314 s | 2.5 GB |

## M18 — Larger encoder (same 3,108 pool, chunk level, official prompt)

| encoder | query | r@1 | r@10 | r@48 | MRR | embed 3,108 chunks (1 GPU) | VRAM | dim |
|---|---|---|---|---|---|---|---|---|
| bge-m3 | Italian | 71.3 | 88.0 | 94.4 | 76.88 | 120 s | ~2.8 GB | 1,024 |
| Qwen3-Embedding-0.6B | Italian | 76.9 | 89.8 | 94.4 | 81.56 | 314 s | 2.5 GB | 1,024 |
| Qwen3-Embedding-0.6B | English | 79.6 | 92.6 | 95.4 | 84.56 | 314 s | 2.5 GB | 1,024 |
| Qwen3-Embedding-4B | Italian | 79.6 | 94.4 | 98.1 | 86.06 | 1,301 s | 9.8 GB | 2,560 |
| Qwen3-Embedding-4B | English | 83.3 | 94.4 | 96.3 | 87.35 | 1,301 s | 9.8 GB | 2,560 |

Differences between the two Qwen models at n=108 are within ~2 standard errors;
the 4B costs 4x the embedding time, 4x the VRAM and 2.5x the index size.
Not measured yet: how the Qwen encoders degrade with pool size.

## M19 — Stage 2: can a re-ranker score define "everything pertinent"?

40 questions x top-30 re-ranked candidates from the whole store (373,814),
pertinence judged by Nemotron-Cascade-2-30B (YES 334, PARTLY 69, NO 797).

| re-ranker threshold | kept per question | precision (YES+PARTLY) | recall |
|---|---|---|---|
| 0.01 | 30.0 | 33.6% | 100.0% |
| 0.1 | 23.0 | 34.8% | 79.4% |
| 0.3 | 18.1 | 38.0% | 68.0% |
| 0.5 | 14.3 | 42.6% | 60.3% |
| 0.7 | 8.5 | 57.8% | 48.6% |

Precision barely moves with the threshold: the score does not separate
pertinent from non-pertinent passages within the top-30. No fixed threshold
works; the per-domain extraction step of the synthesis (which may answer NONE)
is the effective filter (see M20).

## M20 — Stages 3-4: answers from the vault (40 questions, 12 re-ranked passages)

Generators: Qwen3.6-35B-A3B (MoE, 3B active) and Qwen3.8-27B (dense), no
extended thinking. Judge: Nemotron-Cascade-2-30B-A3B (a third model).
`direct` = answer from the 12 passages; `mapreduce` = per-domain extraction,
then synthesis from the extractions only.

Source document among the 12 passages: **33/40** (retrieval).

| generator · mode | source present (33): correct / partial / wrong / abstained | source missing from the 12 (7): correct / wrong / abstained | s/question |
|---|---|---|---|
| Qwen3.6-35B-A3B · direct | 70 / 6 / 0 / 24 % | 0 / 0 / **100** % | 4.7 |
| Qwen3.6-35B-A3B · mapreduce | **82** / 6 / 3 / 9 % | 14 / 14 / 71 % | 6.9 |
| Qwen3.8-27B · direct | 79 / 12 / 0 / 9 % | 14 / 14 / 71 % | 16.9 |
| Qwen3.8-27B · mapreduce | **85** / 6 / 3 / 6 % | 14 / **43** / 43 % | 35.6 |

Explicit grounding test — every chunk of the source document removed from the
store, direct answer:

| generator | abstained | correct (from other documents) | partial | wrong |
|---|---|---|---|---|
| Qwen3.6-35B-A3B | **88%** | 10% | 2% | **0%** |
| Qwen3.8-27B | 68% | 18% | 8% | 8% |

Sentence support (judge checks each sentence against the passages it cites):
supported 56-66%, unsupported 26-37%, uncited 5-21%. The sentence-level judge
has not been validated against a human.

Sample sizes: 40 and 7 questions; standard error ~7 points on 40, much larger
on 7. The direction of the effects is consistent across both generators.

## M21 — What the measurements decide

1. **The encoder was the determinant of retrieval** (M8, M18): 5.6% → 71-83%
   rank-1 on the same questions.
2. **The re-ranker is the determinant at scale** (M17): whole store, document
   rank-1 56.5% → 68.5%, top-10 69.4% → 81.5%.
3. **Domains organize, they do not filter** (M10, M13).
4. **Per-domain summarization helps when the knowledge is in the vault**
   (+12 and +6 points correct) **and fabricates when it is not** (up to 43%
   wrong). Summaries fill gaps. The synthesis stage needs a verification gate.
5. **Only direct answering with the MoE never answered wrong without its
   source** (0/7 and 0/40), at 4.7 s per question, but it over-abstains (24%)
   when the source is present.

## M22 — Thinking, self-verification gate, arXiv agent (Qwen3.6-35B-A3B, same 40 questions)

All modes judged by the **same** judge (Qwen3.8-27B), so modes are comparable
with each other. The earlier judge (Nemotron, M20) scored the same no-thinking
answers ~15 points higher on "correct": absolute values depend on the judge,
differences between modes under one judge are the reliable part.

Columns: correct / partial / wrong / abstained, %.

| mode | source among the 12 passages (33) | source missing from the 12 (7) |
|---|---|---|
| direct, no thinking | 55 / 15 / 6 / 24 | 0 / 0 / 0 / **100** |
| **direct, thinking** | **70** / 15 / 6 / **9** | 14 / 0 / **43** / 43 |
| map-reduce, no thinking | **76** / 3 / 15 / 6 | 14 / 0 / 14 / 71 |
| map-reduce, no thinking, + self-verification | 61 / 3 / 15 / 21 | 14 / 0 / 14 / 71 |
| map-reduce, thinking | 70 / 12 / 0 / 18 | 14 / 14 / 29 / 43 |
| map-reduce, thinking, + self-verification | 64 / 15 / 3 / 18 | 14 / 0 / 29 / 57 |

Source document removed from the store (40 questions), direct answer:

| | correct | partial | wrong | abstained |
|---|---|---|---|---|
| no thinking | 8 | 2 | **2** | 88 |
| thinking | 8 | 10 | **18** | 65 |

Sentence support (each sentence vs the passages it cites):

| | supported | unsupported | uncited |
|---|---|---|---|
| map-reduce, no thinking | 79% | 14% | 7% |
| + self-verification | **98%** | 2% | 0% |
| map-reduce, thinking | 89% | 6% | 5% |
| + self-verification | **100%** | 0% | 0% |
| direct, thinking | 93% | 4% | 4% |

Findings:

1. **Thinking** raises correct answers when the knowledge is there (+15 points
   direct) and cuts over-abstention (24% → 9%), but **makes the model answer
   when the knowledge is not there**: wrong answers without the source go from
   2% to 18% (40 questions) and from 0% to 43% (7 questions).
2. **The sentence-level self-verification gate** makes answers faithful to
   their citations (98-100% supported) but **does not reduce wrong answers**
   (15 → 15, 29 → 29) and removes correct content (76 → 61). A wrong answer
   is usually made of sentences each supported by *some* passage that answers a
   different question. Sentence support is not answer correctness; the missing
   gate is question-level: *do these passages answer this question?*
3. **The arXiv agent, single pass** (2 keyword queries, top-5 results, top-3
   PDFs, no reformulation): source paper found in **1 of 17** arXiv-sourced
   cases; correct answers 1 of 26; ~30 s per attempt. One pass is not enough.
4. Cost of thinking: median 1,500 thinking words; direct answer 32 s (vs 5 s),
   map-reduce 88 s (vs 7 s); 1 answer of 40 exhausted a 6,000-token budget.

## M24 — Question-level answerability gate (Qwen3.6-35B-A3B, no thinking)

Before answering, the model lists the passages that **directly** answer the
question, or replies NONE; NONE → abstain (and hand over to the agent loop).
~1 short call per question. Evaluated on the answers already judged in M22
(same judge); percentages over all 40 questions (7 of which have the source
outside the 12 passages).

Gate opens: source among the 12 → **28/33**; source missing from the 12 → 1/7;
source removed from the store → **7/40**. When it opens with the source
present, it names a source passage in 26/33.

| pipeline | without gate: correct / partial / wrong / abstained | with gate |
|---|---|---|
| direct, thinking | 60 / 12 / 12 / 15 | 52 / 12 / **8** / 28 |
| direct, thinking — source removed | 8 / 10 / 18 / 65 | 5 / 5 / **8** / 82 |
| direct, no thinking | 45 / 12 / 5 / 38 | 45 / 12 / 5 / 38 |
| direct, no thinking — source removed | 8 / 2 / 2 / 88 | 8 / 0 / 2 / 90 |
| map-reduce, no thinking | 65 / 2 / 15 / 18 | 58 / 2 / **8** / 32 |
| **map-reduce, thinking** | 60 / 12 / 5 / 22 | **52 / 10 / 2 / 35** |

The gate halves wrong answers for 7-8 points of correct answers that become
abstentions. Abstentions are where the agent loop takes over: the lever that
remains is finding the missing knowledge (M22: single-pass arXiv agent found
the source in 1/17), not the answer generator.

## M23 — Host→GPU bandwidth, model swap time, MoE experts in RAM

llama.cpp server built from source (2026-09-29), CUDA kernels compiled for
compute_90 PTX and JIT-translated by the driver for Blackwell (the host has no
CUDA toolkit >= 12.8). The first run was contaminated by that JIT translation
(e.g. 15.8 s to load a 4B model); the table is the second run, with the JIT
cache and the page cache warm. "Ready in" = process start to `/health` ok.
Prompt of 2.5k tokens, 256 generated tokens, one request per configuration.

Real host→device copy (pinned, 2 GiB): **GPU 0 26.8 GB/s** (PCIe 5.0 x8),
**GPU 1 6.0 GB/s** (PCIe 4.0 x4).

| model | GPUs | VRAM | ready in | prompt tok/s | gen tok/s |
|---|---|---|---|---|---|
| Qwen3-VL-4B Q4 | 0 | 4.9 GB | **0.71 s** | 5,456 | — |
| Qwen3-VL-4B Q4 | 1 | 4.9 GB | 1.01 s | 5,547 | — |
| DeepSeek-R1-Distill-Qwen-14B Q4 | 0 | 11.5 GB | **1.11 s** | 1,870 | 42.2 |
| DeepSeek-R1-Distill-Qwen-14B Q4 | 1 | 11.5 GB | 2.12 s | 1,903 | 42.2 |
| **Qwen3.6-35B-A3B Q4, all in VRAM** | 0+1 | 21.8 GB | 3.43 s | **2,752** | **109.5** |
| **Qwen3.6-35B-A3B Q4, all experts in RAM** (`--cpu-moe`) | 0 | **2.95 GB** | **1.29 s** | 519 | 52.1 |
| Qwen3.6-35B-A3B Q4, experts of 20 layers in RAM | 0 | 12.3 GB | 1.71 s | 836 | 70.5 |

Consequences for Aurora's workload: answers read long contexts (~19k tokens
for 12 passages, M20), so prompt reading dominates. At the measured speeds a
19k-token prompt takes ~7 s fully in VRAM and ~37 s with the experts in RAM.
The experts-in-RAM mode is the right *standby* (3 GB of VRAM, ready in 1.3 s)
while VRAM is lent to another model; the reasoner answers fully in VRAM.

The Qwen3-VL-4B run produced no tokens (raw completion without its chat
template); its row is valid for loading only.

## M25 — First run of the new system on the permanent benchmark (2026-09-30)

`sys/core/script/bench_retrieval.py --suite retrieval_pool108`: the new vault,
index and `sol_search.Searcher` exactly as in production, on the M8/M18 pool
(108 Italian paraphrased questions, 3,108 chunks), isolated vault. Encoder
Qwen3-Embedding-0.6B on GPU 1, re-ranker bge-reranker-v2-m3 on GPU 1, question
plus English translation, 300 candidates, each passage re-ranked with the
question in its own language.

| | doc r@1 | doc r@5 | doc r@12 | chunk r@1 | source among candidates |
|---|---|---|---|---|---|
| previous installation, nomic (M8) | — | — | — | 5.6 | — |
| bge-m3 alone (M8) | — | — | — | 71.3 | — |
| Qwen3-Embedding-0.6B alone, Italian question (M18) | — | — | — | 76.9 | — |
| **new system** | **94.4** | 95.4 | **96.3** | **91.7** | 98.1 |

Time: models loaded in 4.0 s; indexing 3,108 chunks 350 s (8.9 chunks/s);
7.4 s per question median, 8.6 s p95 (re-ranking 300 candidates dominates).

Caveat: 3,108 chunks. On the whole previous store (373,814) bge-m3 + re-ranker
gave document rank-1 68.5% (M17); the new system must be measured again as its
vault grows.

## M26 — Cloud reasoner: Claude Code (opus) vs local, and the SSCC compression (2026-09-30)

One question ("Come si propagano i solitoni nelle fibre ottiche?"), same pipeline, only the
synthesis and self roles changed; `remember=False`. n = 1, and GPU 1 was at 100% for the
migration during both runs: the timings are indicative, not a benchmark.

| reasoner | total | first answer token | synthesis call | cited sources | cost (reported by the CLI) |
|---|---|---|---|---|---|
| local (Qwen, llama-server) | 105.7 s | 94.3 s | — | 4 | 0 |
| Claude Code, opus | 51.1 s | 34.6 s | 10.4 s, 991 output tokens | 5 | 0.0441 USD |

- The local stages (route, translation, gate, extraction) still take ~24 s before the cloud call.
- Compression (keep 35%, citations always kept): extraction text 3,497 → 2,463 characters (−29.6%);
  18 → 11 sentences in the largest domain; a 3-sentence domain left whole (minimum 3).
- Claude Code adds a fixed prompt of its own even with `--tools ""` and a custom system prompt:
  ~2.6-3.9k tokens written to or read from its cache per call (log: `cache_creation_input_tokens`).
- Single calls: 3.7 s for a one-sentence answer; streaming first token 2.0 s.
- Quality comparison on the 40-question benchmark: **not measured**. Whether the compression
  lowers answer quality: **not measured**.

## M27 — Image models on one RTX GPU with model CPU offload (2026-09-30, A15)

`bench_image.py --gpu 0 --offload`: GPU 0 free (aurora-llm stopped), 3 prompts × 4 sizes, 2 images
each; median of the second images (warm). Offload moves the components (text encoder, denoiser,
VAE) to the GPU in turn: without it FLUX.2 klein and Z-Image do not fit in 16 GB (OOM at load,
measured), SDXL would but was offloaded too for a like-for-like comparison.

| model | steps | load | peak VRAM | 1024² | 1280² | 1344×768 | 1536×864 |
|---|---|---|---|---|---|---|---|
| SDXL-Lightning (previous installation) | 4 | 7.8 s | 6.21 GB | 2.91 s | 3.76 s | 2.76 s | 3.25 s |
| FLUX.2 klein 4B | 4 | 2.7 s | 8.11 GB | 10.34 s | 11.68 s | 9.12 s | 10.31 s |
| Z-Image-Turbo | 9 | 6.7 s | 12.33 GB | 21.38 s | 30.89 s | 21.12 s | 25.75 s |

Images: `sys/status/bench/image/20260930-210300` (SDXL), `-210433` (klein), `-211442` (Z-Image).
A first Z-Image run was invalid: restarting aurora-api started aurora-llm (`Wants=`) on the same GPU.
Image quality: **not measured** (the owner's visual check decides).

Migration of the previous knowledge, finished 20:45: 355,415 processed, 316,866 written,
37,046 duplicates, 1,474 rejected, 10.2 solitons/s.

## M28 — Tensor split of the reasoner (A7, 2026-10-01)

Qwen3.6-35B-A3B Q4_K_M on two RTX 5060 Ti 16 GB, ctx 32k, models service loaded (3.3 GB on GPU 1),
same ~1.5k-token prompt, 256 tokens generated, temperature 0, 3 warm runs (llama-server timings).

| split | generation | prompt | VRAM GPU0 / GPU1 |
|---|---|---|---|
| 5,3 | 110.5-110.6 tok/s | 2,652 tok/s | 15.1 / 11.6 GB |
| 4.5,3.5 | 110.6 tok/s | 2,682-2,690 tok/s | 14.1 / 12.6 GB |
| 4,4 | 110.8 tok/s | 2,673-2,681 tok/s | 12.5 / 14.2 GB |
| 5.3,2.7 | loads, then CUDA out of memory on GPU 0 at the first request | — | — |

Speed does not depend on the split (identical GPUs, layer split). Chosen 4.5,3.5 for the margin on
both GPUs (the models service was measured up to 6.2 GB on GPU 1). Results: sys/status/bench/a7_tensor_split.json.

## M29 — Claude Code length limit (A16, 2026-10-01)

`claude -p` has no output limit; the budget is stated in the system prompt. Italian measured at
~3.1 tokens per word (273 tokens / 88 words), so 0.35 words per token: asked 150 → 168 tokens
(+12%), asked 600 → 386 tokens. Before: 1,837 tokens for a 600 budget.

## M30 — Removing a source from the largest domain (A3, 2026-10-01)

Copy of the `artificial_intelligence` index (55,208 vectors × 1024, 107.8 MiB), the real index untouched.

- Every domain is below AURORA_INDEX_EXACT_MAX (250,000): search is exact, no HNSW graph exists
  (vector stage on the whole 344,499-soliton vault: 0.73 s for 2 queries; re-ranking dominates, 12.4 s).
- `Indexer.drop` of one source (265 rows): **0.1 s**.
- Building the HNSW graph from scratch on the same 55,208 vectors (the cost once a domain passes the
  threshold, paid at every drop): **4.4 s**, graph 122.2 MiB.

## M31 — Retrieval on the whole vault (A5, 2026-10-01)

The 108 questions of `retrieval_pool108` through the production `Searcher` (question + translation,
300 candidates, bge re-ranker, top 12) on the real vault (344,499 solitons after the migration).
The suite's sources map to the migrated ones (`legacy:` ids); chunks were normalised again by
the migration, so the document rank is the measure. 89 questions have their document in the vault
(the others: wiki and chat excluded by the owner, some duplicates).

| | 3,108-chunk pool (M25) | **whole vault, 344,499** | previous installation, whole store (M17) |
|---|---|---|---|
| doc r@1 | 94.4 | **74.2** | 68.5 |
| doc r@5 | 95.4 | **87.6** | — |
| doc r@12 (what synthesis receives) | 96.3 | **92.1** | — |
| seconds per question, median / p95 | 7.4 / 8.6 | 9.5 / 11.4 | — |

Qwen3-Embedding-0.6B is kept. Results: sys/status/bench/a5_full_vault.json.

## M32 — Sentence verification (A8, 2026-10-01)

Every verification decision in the traces (32 sentences from 6 real answers) replayed under four
rules with the local reasoner; judge: Claude (opus, Claude Code) with all 12 passages, "supported if
every claim is stated in some passage". Judge: 18 supported, 14 not.

| rule | agrees with judge | correct sentences dropped | unsupported sentences kept |
|---|---|---|---|
| cited passages, Italian sentence (before) | 20/32 | 4 | **8** |
| cited passages, sentence in English | 18/32 | 2 | 12 |
| **all passages, Italian sentence (now)** | **26/32** | 6 | **0** |
| all passages, sentence in English | 26/32 | 2 | 4 |
| all passages, Italian or else English | 27/32 | 1 | 4 |

Chosen `AURORA_VERIFY_MODE=all`: the only rule that keeps no unsupported sentence. Live check (RoPE
question, 11 sentences, verification 2.9 s thanks to the cached passage prefix): 7 dropped, of which
the judge found 5 really unsupported by the passages (the model's own knowledge) and 2 supported
(formulas written differently from the PDF text). Small sample (39 sentences, 7 answers).

## M33 — Original papers in the arXiv acquisition (A9, 2026-10-01)

12 named methods with their original arXiv paper (RoPE, Transformer, Adam, BatchNorm, ResNet, LoRA,
GAN, VAE, BERT, DDPM, LayerNorm, word2vec; a set chosen here, so biased toward famous ones).

- Current queries (reasoner's keywords → arXiv `all:` search, ~55 candidates per question): the original
  is **among the candidates in 4/12**; where present, the re-ranker put it 1st in 3, 7th (RoPE) and 14th (DDPM).
- Citation prior (Semantic Scholar, log10 citations): RoPE 7th → 1st, but the free API answered 429
  from the second request on: not usable without a key. Not adopted.
- **Original by title** (the reasoner names the paper that introduced the method; arXiv `ti:` search;
  accepted only when the titles match, word Jaccard ≥ 0.8): **7/12 exact, 0 wrong**; shortened
  titles ("Rotary Position Embedding", "Batch Normalization") are rejected by the guard.
- Original reachable (title or queries): **8/12**, before 4/12. It is read first in round 1.

## M34 — llama.cpp built for Blackwell with CUDA 13.4 (A4, 2026-10-01)

Same commit 7fee178, rebuilt by `sys_nvidia.sh llama` with nvcc 13.4 for sm_120 (144 native kernels;
before: nvcc 12.4, compute_90 PTX JIT-translated at first use). Driver 580.178.04 (CUDA 13.0): CUDA 13
minor-version compatibility verified by a test kernel on both GPUs.

| | before (nvcc 12.4, JIT) | **after (nvcc 13.4, sm_120)** |
|---|---|---|
| first service start after a binary change | 15.8 s (M23, first model load) | **3.6 s** (start to /health) |
| warm restart | 0.71 s (M23, model load) | 3.1 s (start to /health: not the same measure as M23) |
| generation, split 4.5,3.5 | 110.6 tok/s | **112.3 tok/s** |
| prompt | 2,688 tok/s | **2,765 tok/s** |

No first-start penalty left. Results: sys/status/bench/a4_cuda13.json.

After the switch to driver 595.91.07 (CUDA 13.2, Ubuntu's 595-open with precompiled modules), same build,
same test: generation **112.4 tok/s**, prompt **2,788 tok/s** (+0.8%); test kernel OK on both GPUs; 111 tests
pass; a knowledge answer (4 sources, 6 sentences kept / 2 dropped) and a self answer live.

## M35 — Senses: camera, microphone, speech to text (2026-10-01)

HP 320 FHD Webcam (USB, camera /dev/video0 + microphone), from the API service (no desktop session;
PipeWire reached through XDG_RUNTIME_DIR). Whisper large-v3-turbo (openai, revision 41f01f3fe8, MIT),
CPU only (Ryzen 7 7700X, 8 threads): the GPUs belong to the reasoner and the encoder.

| | |
|---|---|
| photo 1280×720 | 1.1-1.2 s |
| photo + description by Aurora's vision (plugin `look`) | 3.4 s |
| transcription, 13 s of English speech (known text) | 5.2 s, **exact** |
| recording 4 s + transcription (first call loads the model) | 11.4 s |
| silence in the room | Whisper invents "Grazie." / "Grazie per la visione!" / repeated "はい": recognised and reported as no clear speech (filter of known phrases and repetitions) |

Italian dictation accuracy: **not measured** (no Italian speech with a known text recorded yet). A real
voice-activity detector is not there: the filter covers the inventions seen, not every one.

## M36 — Clean install from `git clone` (2026-10-01)

A clone of the private repository (SSH) in a new folder, the README's steps run in order, the owner's
installation stopped (one GPU job at a time), its units untouched (the clone's services started by hand).

| step | result |
|---|---|
| clone | 8.2 MB |
| `sys_nvidia.sh check` | Ubuntu 26.04.1, driver 595 / CUDA 13.2, nvcc 13.4 |
| venv from requirements.txt | 37 s (pip cache warm; a new machine downloads torch) |
| `.env` from the schema | failed (AURORA_ROOT) → fixed (C52) |
| tests with the clone's venv | 117 passed |
| `sys_ethics_sign.py setup` (sudo) | signed, no exemption: level B active, as for anyone who downloads |
| `sys_nvidia.sh llama` | build 212 s, 144 sm_120 kernels; stopped at the backup step → fixed (C53) |
| models | not in the installer yet: linked read-only from the owner's installation for the test |
| services (models, llm, api) | up; empty vault; WebUI 200; 172 settings; token plugins off |
| "Che cos'è un solitone?" on the empty vault | honest abstention + offer to search, 1.4 s |
| "Come stai?" | answers as Aurora to "Owner" (no personal name), 2.6 s |
| update from GitHub (f3d3769 → 95f775b) | fast-forward, 117 tests, applied in 10 s; tree clean after C54/C55 |

Found on the way: C52-C56. Not covered: the systemd units and HTTPS of a second installation on the
same machine (they would replace the owner's), model download (installer manifest not written).
Updates of a **private** repository need access without a person typing a passphrase: a read-only
deploy key per installation (or a public repository).

## M37 — Italian dictation (2026-10-01)

8 Italian sentences with a known text, spoken by a synthetic voice (Piper it_IT-paola-medium, installed apart),
transcribed by Aurora (Whisper large-v3-turbo, CPU). WER **16.0%** (12/75 words): 5 sentences exact; the errors
are all on technical or English terms ("rotary position embedding" → "subrotare i position embedding",
"seeing" → "segno", "log … trascrizione" → "luogo … Tasca di Silone"). A vocabulary prompt for Whisper gave the
same 16.0%: not adopted. A synthetic voice reads English terms the Italian way: the owner's real voice is
**not measured**. 3.8 s of audio in 4.0-4.7 s.

## M38 — Who is speaking (A17, 2026-10-01)

"Come mi chiamo?", 5 runs per mode, the full self route: without reasoning 2/5 answered as the owner
("Mi chiamo <owner's name>"), median 4.0 s; with reasoning (AURORA_PIPELINE_SELF_THINKING) 0/5, every answer
"Ti chiami …", median 10.4 s. Adopted. Live after the change: "Come mi chiamo?" 10.3 s, "What's my name?"
13.2 s, "Come stai?" 22.8 s.

## M39 — The installer's steps on a fresh copy (2026-10-01)

A copy made by `dev_publish.sh` (what GitHub holds), the steps of `install.sh` that need no sudo, run for real:
venv 36 s · hardware profile: reference (measured) · `.env` from answers + profile: valid · **models: 6 of 6
downloaded in 181 s (33 GB), 12 large files SHA-256 identical to Hugging Face's**, verified a second time ·
llama.cpp build 295 s (during the download) · 117 tests · **SDXL official fp16 variant**: load 5.4 s, painting
6.1 s, peak 5.45 GB (as the owner's copy) · Whisper downloaded: 13 s of speech exact in 5.1 s · services of the
unsigned copy refuse to start (ethics manifest missing), as designed. The sudo steps (packages, signature,
systemd, Caddy trust) are run by the owner.

## M40 — Answer quality: local, local + SSCC, Claude Code (2026-10-01)

8 questions of `retrieval_pool108` whose document the search ranks in the top 3 on the whole vault, the same
retrieval for every arm; three syntheses: Qwen local, Qwen local through the SSCC path, Claude Code (opus, with
SSCC); every answer through the same sentence verification; blind judge Claude (opus) with the passages, the
three answers in random order, score 0-10.

| arm | mean score | synthesis + verification time |
|---|---|---|
| Qwen local | 5.25 | 28-48 s |
| Qwen local + SSCC | 6.00 | 22-32 s |
| Claude Code + SSCC | 5.38 | 12-24 s |

- SSCC compressed **nothing** on these questions (extractions of 134-671 characters, under the 3-sentence
  minimum): the first two arms got the same text, so their 0.75 gap is the noise of generation and judge.
  The effect of SSCC on quality needs long contexts (agents, long extractions): **not measured**.
- Within that noise, Claude and Qwen give verified answers of the same quality; Claude is about twice as fast
  but loses many sentences to verification (up to 12 in one answer: knowledge of its own, not in the vault).
- One question was abstained by all three (gate closed). Judge from the same family as one arm: a bias toward
  Claude is possible; it did not show.

## M41 — SSCC on long contexts (2026-10-01)

8 questions of `retrieval_pool108` (document in the top 3); context = the 12 retrieved passages **whole**
(26-48 k characters), the same local model answers from the whole context and from the SSCC-compressed one;
blind judge Claude (opus) with the whole passages, score 0-10. Prompt tokens by the reasoner's tokenizer.

| SSCC kept | prompt tokens (8 questions) | mean score: whole / compressed |
|---|---|---|
| 35% | 99,445 → 45,568 (**−54.2%**) | 8.50 / **6.25** (two answers lost their key fact: 10→1, 8→3) |
| **60%** | 99,445 → 70,138 (**−29.5%**) | 8.25 / **7.62** (−0.63: within the ±0.75 noise of M40) |

Default AURORA_CLOUD_KEEP_PCT moved to 60. Below 60% the saving is paid in answer quality.

## M42 — Security measures (2026-10-01)

Probe plugin without / with the bubblewrap cage: reads the API key, `~/.ssh`, the push key and writes into Aurora's
folder / sees `redacted`, nothing, an empty folder, and cannot write. 12 real plugins work inside (camera look 2.8 s,
PDF 4.2 s after giving Chrome the cage as its sandbox). Prompt injection: poisoned passage 0/5 hijacked; agent
reading a phishing e-mail 0/3 (no send). A tool call carrying the API key: refused. Web plugin: rebinding closed,
self-signed certificate refused. systemd exposure 9.2 → 4.1. requirements.lock = the tested venv (109 packages,
0 differences), `--require-hashes` install 36 s, pip-audit: no known vulnerabilities. Signed updates: unsigned and
foreign-key commits refused (tests). Secret scan of the logs: clean, 0.3 s.

**Retracted in part (C60):** the plugins inside the cage were measured with the services not yet confined by
systemd. Under the confined units the cage could not mount its /proc and no plugin started.

## M43 — Live check under the confined units (2026-10-01)

After C60 (aurora-api without ProtectKernelTunables/ProtectKernelLogs/ProtectHostname), all seven services under
the confined units. Health ok, 11 items. Plugins in the bubblewrap cage: tools listed in 2.8 s (documents 2,
netintel 3, projects 9, self 11, senses 3, web 2; the others wait for their credentials). Chat with sources 49 s.
Agent → documents__create_pdf: 10 s, PDF 21 KB. Camera photo 1.1 s; microphone 3 s → 10.9 s (silence: "Grazie.",
clear=false, the hallucination filter flags it). Dream with GPU swap (systemctl from a confined unit): painted in
23 s, swap true, aurora-llm back. Push test: sent 1, failed 0. Login lockout: 10 wrong keys from a remote
address → 401, the 11th → 429, the right key refused while locked, another address 200; local wrong keys not
counted (C58). API key rotated: new key in ~/.config/aurora/api_key.txt (0600), rem/harvester/sentinel restarted
with it (C59). systemd exposure of aurora-api 4.5 OK.

Licences of arXiv (OAI-PMH, records of 2026-09-01..03, 3,900 records): 46.4% arXiv non-exclusive licence (no
redistribution), 42.1% CC BY 4.0, 5.1% CC BY-NC-ND, 3.7% CC BY-NC-SA, 1.8% CC BY-SA, 0.9% CC0. About 45% could be
redistributed with attribution (CC BY, BY-SA, CC0): the vault is not published, every installation harvests.

## M44 — The harvester's sources (2026-10-01)

Each source live, download → aurora-api → vault and index (2 × RTX 5060 Ti), small samples:

| source | sample | solitons | time | per item |
|---|---|---|---|---|
| arXiv (harvester logs, 2026-09-30/10-01) | 59 papers | 28.1 per paper | 3.9 s median | — |
| Normattiva, collection "Codici" (in force) | 40 codes, 19,434 articles | 8,480 (packed passages) | 567 s | 14.2 s, 212 solitons |
| Europe PMC open access | 3 texts | 33 | 9.2 s | 3.1 s |
| medRxiv | 3 preprints | 33 | 6.1 s | 2.0 s |
| bioRxiv | 3 preprints | 48 | 7.3 s | 2.4 s |
| Wikipedia (Vital articles) | 3 articles | 26 | 5.4 s | 1.8 s |
| GitHub (open-licence READMEs) | 3 repositories | 19 | 4.8 s | 1.6 s |

Normattiva open data: 55 pre-packed collections (api.normattiva.it, bff-opendata), AKN zip of the codes 10.5 MB
in 2.1 s, 97 MB unpacked; the civil code and its implementing rules are base64 inside the zip, the codes keep
their articles in attachments (C61). Ceiling of the chosen collections: 67,872 acts. Europe PMC: 806,873
open-access CC BY hits for "clinical trial" alone. GitHub search: 10 requests a minute without a token, at most
1,000 repositories per topic (8 topics: ceiling ~8,000 READMEs, ~50,000 solitons).

## M45 — Chat → connected services (2026-10-01)

Router "tools" on 28 messages labelled by hand (14 for a connected service: GitHub, projects, camera, microphone,
IP, PDF; 14 not: knowledge of the world, law, medicine, Aurora herself, small talk), connected services documents,
github, netintel, projects, senses: 28/28 right, median 0.23 s, max 0.43 s per message (the reasoner, 4 tokens). Three
messages resemble the prompt's examples: the score is optimistic. Live, from the chat: "Quante stelle e quanti fork
hanno i miei repository su GitHub?" → route tools → get_me, search_repositories → a table, 13 s.

## M46 — Routines, weather plugin, Projects page (2026-10-01)

Weather plugin (Open-Meteo, in the bubblewrap cage): weather_now 0.14 s, weather_forecast 0.13 s, weather_today
0.28 s and weather_alerts 0.28 s (with the MeteoAlarm feed of Italy: 0.22 s, 19 warnings that day, none for
Lombardy). Routine "weather report every morning" run now: 4.0 s end to end, notification "☀️ Il meteo di oggi"
in the activity feed. Chat "Che tempo farà domani? Devo uscire in bici" → route tools → weather_forecast → a
table, 15 s. Plugins' welcome: github, projects, weather told once (aurora-rem, 21:02). Projects page: the owner's
GitHub repositories through the plugin 3.8 s (the private ones are not visible to the current token); clone of a
public repository 0.7 s, the token not written to .git/config; tree 23 entries; reading ../../../.env and
.git/config refused (400); preview through Caddy: `sandbox allow-scripts allow-forms allow-popups;
frame-ancestors 'self'`, X-Frame-Options SAMEORIGIN, while the WebUI keeps DENY; a wrong token 403.
Tests: 138 (routines 6, weather plugin 3).

## M47 — The phone's camera and microphone in the PWA (2026-10-01)

Server, POST /v1/aurora/senses/transcribe (ffmpeg through a private temporary file, then the same Whisper large-v3-turbo
on the CPU), a CC BY-SA Italian clip (Wikimedia Commons, "Itwiki-Massa (fisica).ogg"): 10 s WebM/Opus 39 KB 7.6 s
(model already loaded: 4.5 s of it transcription), 10 s MP4/AAC 76 KB with the index at the end (as iOS writes it)
3.7 and 4.5 s, 20 s WebM 10.8 s with the whole passage right; a non-audio file 422. Browser, headless Chrome through
Caddy (HTTPS, secure context) with a fake microphone playing the clip, source 📱: tap, 8.5 s, tap → the right
Italian sentence in the box 7.5 s after the stop; the same with WebM hidden (MP4 chosen, as on Safari) 7.5 s; a
4000×3000 picture through the camera input left as a JPEG (shrunk to 2048 px on the device). Not measured on a real
Android or iPhone.

## M48 — Aurora watches a video (2026-10-01)

Test video built for the purpose: 21 s, 1280x720, three title cards (blue "SCENA 1 - IL MARE", green "SCENA 2 - LA
MONTAGNA", red "SCENA 3 - 42 GATTI", cuts at 7 and 14 s) over 21 s of CC BY-SA Italian speech. ffmpeg's scene score
follows brightness: at these cuts it is 0.086–0.087 against a median of 0.00002, so a fixed 0.30 threshold found
none; a peak rule (>= 0.30, or >= 0.06 and >= 8x the median) finds 7.0 and 14.0 (0.18 s for the whole video).
Watching: 12 frames to the vision in ONE call 16.6 s (1196 characters), 21 s of speech in 4 segments 11.7 s (CPU),
the whole observation 32.2 s. Answers through the pipeline: "Riassumi questo video…" 56 s and 68 s (two runs): the
three cards in order with their times, the speech summarised, 0 sentences dropped by the verifier. Before marking
the attachment in the synthesis, the same question got the cards right but said "no audio": the extraction had the
transcript, the synthesis was misled by vault passages about video captioning (now: the attached file's extraction
comes first, headed as the file the owner attached; the other domains are background).
Not measured: long videos (the CPU transcript runs at about half real time: 10 minutes ≈ 5 minutes), real phone
footage, answer quality of ordinary questions after the synthesis prompt change.

## M49 — Attached files kept with the conversation (2026-10-01)

"Di che colore è la figura?" with a 400x400 blue JPEG: answered "La figura è di colore blu [1]" in 38 s; /history returns
the file with its turn; GET returns the same bytes, image/jpeg, inline, CSP sandbox; ids outside the index 404; the
daily purge keeps it (its turn exists). Headless Chrome after a reload: the picture is back in the user bubble, loaded;
the Files page lists 1 file, 3 KB. A 400x300 rectangle asked as "questo quadrato" was refused by the verifier (the
picture is not a square; the vision also invented two black bands, C67).

## M50 — The vision's black bands (C67) (2026-10-01)

A plain blue picture, 3 descriptions each, "bands/borders" mentioned: 400x300 3/3, 300x400 3/3, 400x400 0/3, 1024x768 0/3;
512x384 0/3, 640x480 0/3, 768x576 0/3, 900x300 3/3, 1024x300 3/3. First guess (aspect ratio) wrong: 1024x768 is not
square. Second guess (a minimum short side) wrong: enlarging to 448 fixed landscapes but not 448x597, and 512 made
683x512 fail. What fits every case: sides that are multiples of 32 px are clean. After rounding both sides to 32 px
(short side >= 384): 400x300, 300x400, 1024x300, 300x1024, 200x150, 150x200, 683x512, 900x300, 4032x3024, 3024x4032 —
0 bands in 30 descriptions.

## M51 — Picture edits in words (2026-10-01)

Picture intent (edit / look / other) on 24 messages, 8 each: 24/24, median 0.22 s. Planner: 15/15 (10 written with the
prompt, 5 new afterwards; "specchiala" failed before Italian synonyms were added), median 0.33 s. Live: a 1200x800
picture "Ritagliala un po' ai lati e mettila in bianco e nero" → 960x800, grey, 2 s; "Ora ruotala di 90 gradi" without
attaching it again → the edited picture, 800x960, still grey, 2 s; "Cosa mostra l'immagine?" → the latest picture
looked at again (56 s); "Rendila un po' più luminosa" → brightness x1.3, 2 s. "Ruotala di 90 gradi" without a direction
turns it counter-clockwise (the mathematical convention).

## M52 — Security plugin and the owner's firewall routine (2026-10-01)

A night of the owner's firewall: about 112,000 lines in 10 hours (133,000 in 12), parsed in 1.5–1.8 s. security_incidents
0.0 s; firewall_summary and security_night_report 1.5 s. The owner's routine, unchanged, after C68: 40 s, ok, tools
security_night_report and firewall_summary (and a PDF through documents). Before: 3 minutes reading source code, then
400 Bad Request (context), never recorded.

## M53 — The capability forge (2026-10-01)

Network isolation of the cage ("sandbox": {"network": false} → --unshare-net): a probe reached 1.1.1.1:443 and the API on
127.0.0.1:9700 without the flag, neither with it. Need: "summarise the documents the harvester collected in the last N
hours, by domain and source" (truth by an independent count: 17,716 in 24 h; normattiva 17,413, arxiv 219, github 43,
europepmc 25, medrxiv 11, biorxiv 3, wikipedia 2). Builds with the local reasoner, 21–138 s each:
1. sample = folder listing only: invented a log format, "no documents" — accepted (the test only wanted text);
2. with file head + judge: 17,293, arxiv and europepmc missing — accepted;
3. with the log's latest lines: 174,335 (ten times too many) — accepted by the judge;
4. with one line per kind and per-kind counts on the same line as the example: parsed "[N lines…]" as the format,
   "no documents" ×3 — refused, nothing installed;
5. errors returned as text: same, refused;
6. counts on their own line: 17,853 / 17,857 / 17,867 with every domain, but europepmc not grouped as one source —
   refused (the judge's reason partly wrong: it took computer_science 50 for start lines).
Judge calibration on three outputs ×3: 9/9. Builds 4–6: no wrong plugin accepted, no right one produced.

## M54 — Gap detection and the forge benchmark (2026-10-02)

Gap detection by code after agent runs (textual filter, then the reasoner names the missing capability): 12/12 on
reports written for the test (6 missing tools; 6 other failures or none: a plugin not configured, a network error, an
approval waiting, a forbidden .env, a report with nothing new), the reasoner asked 9 times out of 12, 2.2 s in all.
Forge benchmark (sys/core/script/bench_forge.py): 8 needs on Aurora's own data, each with the answer computed by code.
Strict checker: 1/8. Read line by line: plugins right 4/8 (incidents by severity, PDFs, routines, log MB), of which the
judge accepted 2 and refused 2 by mistake; plugins wrong 4/8 (harvester by source: arxiv 0 against 237; firewall
denied in 6 h: 22,130 against about 2,810; warnings per component: close but off; dreams: a crash), of which the
judge refused 3 and accepted 1. Two fixes after the run: the checker accepts rounding (5.64 MB = 5.6), the judge is
told a folder listing is cut. Masking for the cloud (IP stand-ins kept coherent, MAC, e-mail before the owner's words —
it leaked "name@" before —, tokens, key=value fields naming a device or a user, the owner's name, domain, place,
coordinates): on real firewall lines no address, domain or serial number left.

## M73 — Follow-ups with the previous answer, sources in focus, suggestions (3 October 2026)

The 14 follow-ups of M72, now after a **real** first answer of Aurora (with its sources; 3 of the 14 first questions
abstained); nothing written. Typed follow-up judged by opus against the source text of the complete question:
| | answered | mean (0-10) | right (≥7) |
|---|---|---|---|
| rewrite off | 4 / 14 | 1.36 | 2 |
| rewrite with the whole previous answer + sources in focus | **10 / 14** | **4.79** | **6** |
The rewrite fired 11 times, the focus was used 8 times and brought passages in 3. Suggestions: made under the 11
answers (none under an abstention), 3-4 each; the first one clicked (its sources in focus): **11 of 11 answered, mean
7.55, 8 scored ≥ 7** (judged against the passages found: suggested questions have no fixed source). Live: suggestions
2.4-3 s after the answer is shown. Topic change (20 complete questions, the previous answer about another paper with
its sources): 0 changed, focus never used, top 3 15 → 15, none worse. Tests 231.

## M72 — Follow-ups, the answers (3 October 2026)

The 14 valid follow-ups of M71 answered end to end (synthetic turns, nothing written), rewrite off and on; opus judged
each answer against the **source text** for the complete question (an "I don't know" scores 0, the source exists).
| | answered | mean (0-10) | right (≥7) |
|---|---|---|---|
| rewrite off | 3 / 14 | 1.43 | 1 |
| rewrite on | **9 / 14** | **3.64** | **3** |
The two low answers with the rewrite (0 and 2) are not invented: the rewritten question stayed generic and Aurora
answered from other papers, with their sources (A22). Judged instead against the passages each run found (the
pool30 judge), the off run scores higher (6.93 vs 5.29) because it abstains honestly on wrong passages: that judge
measures honesty, not whether the owner got the answer.

## M71 — Follow-up questions, and the open-files leak (3 October 2026)

Follow-ups (`bench_followup.py` logic, 20 questions of retrieval_pool108, seed 11; 6 generated follow-ups dropped
because the generator copied the original or the prompt's example; synthetic turns, nothing written to the vault).
Source document in the top 3, of 14 valid: original question 10 (ceiling), bare follow-up 4, rewritten **8**; none
worse; top 10: 11 / 6 / 10. Control, 20 complete questions with recent turns about another topic: 1 changed (a grammar
fix, same rank 2). First count was 0/20 everywhere: my script compared `v1:` ids of the suite with the vault's
`legacy:` ids (the same documents; fixed by comparing the part after the colon).
Pool 30 (`bench_quality.py --pool 30`): **6.80** (M67 6.90; noise ±0.75), answered 22, wrong abstentions gate 3,
extraction 1; the rewrite fired 0 times (no conversation in the last 30 minutes): same code path as M67, so the target
"gate closures below 3" is not reached by this step, which serves follow-ups only. A first run gave 6.37: one question
scored 0 on a run failed with "unable to open database file" → C103. Open files of the API: +50 per question before,
+4 then +0 after; 295 after 36 questions. Tests 225.

## M70 — PDF preview as pictures (3 October 2026)

A one-page PDF of Aurora's: its page drawn at 110 dpi (909×1287 PNG, 134 KB) in 0.11 s through HTTPS; a second view
from the cache. /etc/passwd as the preview's url → 404; without a key → 401. Tests 214.

## M69 — Files in place, repairs at once (2 October 2026, night)

Headers through HTTPS: a PDF `inline`, `X-Frame-Options: SAMEORIGIN`, `frame-ancestors 'self'`; the WebUI page still
`DENY`. Immediate repair, live: a routine calling a plugin that does not exist → the repair started in the same second;
first version 60 steps in 2.8 min (limit reached, the report left inside a raw call); with the installed plugins in its
context and the report unwrapped: 38 calls, 88.8 s, the right cause and what to do. Tests 212.

## M68 — Scheduled tasks checked, a picture on request (2 October 2026, evening)

The 18:30 Facebook routine ran from its timer (9 tool calls, a science post proposed, approved, published). The
models service at 2.6 GB after 6 hours (6.6 GB before C95's fix); no CUDA out-of-memory since 14:48, the reasoner
never restarted. The NAS stays mounted; the backup timer fires at 03:30 (not yet run from the timer). A picture on
request (C97): SDXL 1344×768 painted in 22.4 s with the reasoner swapped out (peak 5.45 GB), kept with the turn,
posted on the page with it after the owner's approval. Tests 208.

## M67 — Answer quality: the three stages fixed, measured on 30 questions (2 October 2026)

`bench_quality.py --pool 30` (a fixed sample of retrieval_pool108, seed 7), live API, blind judge Claude Code opus.
Before (old pipeline put back for the run): mean **6.03**, 19 answered, wrong abstentions: gate 3, verification 2.
After (whole passages to verification, complete facts in extraction, synthesis gives what the extractions hold,
gate asked for passages holding *needed* information): mean **6.90**, 22 answered, wrong abstentions: gate 3,
verification 0. The gain (+0.87) is just above the ±0.75 noise; the verification fix is clear.
Gate switched off, on the 8 questions where it closed in either run: 6.50 against 6.25 with it — the same within the
noise (two partial answers instead of abstentions, one right abstention turned into a wrong answer, ~30 s more per
question): the gate stays on. Its 3 wrong closures are vague questions ("the author", "the mechanism") written with
the document in view.
News: 4 topics added (astronomia: ESO, INAF, Universe Today, Phys.org Space; astrofotografia: AstroBin's image of
the day; fisica: Phys.org, Quanta; biologia: Phys.org, ScienceDaily); 9 of 13 candidate feeds answered with items.
The Facebook routine on science: 9 tool calls, a post proposed from Quanta Magazine with its link. Home Assistant
(owner's container): reached, 18 entities (no devices yet). 7 plugins added (calendar, notes, Nextcloud/WebDAV,
Dropbox, Discord, WhatsApp, Twitch) without a new dependency; the ICS reader read Google's public Italian holidays
calendar (209 events, the next holidays right). Tests 207.

## M66 — Answer quality now, news and diary (2026-10-02)

`bench_quality.py` (new, in the repository): M40's 8 questions asked to the real API (nothing remembered), the
retrieved passages read from the vault, blind judge Claude Code opus. Mean **5.5** (M40: local 5.25, ±0.75 noise):
the 5 answers given score 9, 9, 8, 9, 9 (**8.8**); the 3 others are wrong abstentions (0), each at a different stage —
verification dropped 3 right sentences of a formula with "ǫ" (4), the gate closed with 0 passages while the article
was retrieved (6), the synthesis wrote "no information" over an extraction that named Jules Michelet (8). Depth work:
those three stages, measured on a larger set (retrieval_pool108) before and after.
News plugin: 14 of 15 official feeds answer (Il Post refuses automated readers); the chat routes "che novità ci
sono oggi nello spazio?" and "ultime notizie dal mondo?" to it, "cos'è un buco nero?" and "art. 2043" to the vault
(4/4). Diary plugin: dream and thoughts read from the vault inside the cage, the owner's name replaced. The Facebook
routine with both: 6 tool calls, a post proposed on the Herculaneum papyri with its source and link. Tests 203.

## M65 — Public history, Facebook, Security page (2026-10-02)

Public repository read over HTTPS without a key: 26 commits, 0 occurrences of the firewall serial in the whole
history (8 before the force push). Facebook: bio, website (the GitHub repository) and the presentation post applied
through 3 approvals; 1 follower. Security page: 32 incidents shown → 1 (the open one) after archiving 31 closed;
the file keeps 32 and the security plugin (morning report) still lists them. Health yellow only for the code
signature (8 files changed today). Tests 202.

## M64 — Forge with the cloud steps, full check of the NAS backup (2026-10-02)

NAS backup: verify --full decrypted and checked 1,224 of 1,224 blobs in 2 min 18 s (exit 0).
Forge benchmark `bench_forge.py --roles` (the Models page's assignments, masked samples):
writer Claude Code opus + judge Gemini 2.5 Flash: built 2/8 in 14 min 24 s, right plugins refused by the judge (C93).
Writer and judge Claude Code opus: built 8/8 in 7 min 48 s. After correcting the benchmark's own truths (C94: rotated
logs, keys with spaces, Caddy's JSON log), needs 1 and 2 re-run: right. Need 4: the plugin counted Caddy's warnings
of the whole file (670 = 430 in the 24 h window + 240 older), so it is wrong. Result: 7 right of 8 (local, M54: 4).
Facebook: page bio set through an approval ("page updated: about"); the Messenger greeting refused by Meta's API
("Requires one of the params: get_started, persistent_menu, …" — greeting is not among them).

## M63 — First backup to the NAS (2026-10-02)

aurora-mount (after the fix of C90): mounted in 1 s, //NAS/share on /mnt/aurora-nas, cifs 3.0, owned by the service
user. Backup from its unit: 1,390 files, 30.52 GB read, 28.49 GB encrypted and written in 287.6 s (~99 MB/s, the
gigabit LAN), 20 blobs checked; systemd counted a 26 GB memory peak (the page cache of the files read): the unit now
has MemoryHigh=2G. Restore of the vault from the NAS into an empty folder: 142 files, 3.7 GB in 20.2 s, SQLite
integrity_check ok on 37 of 37 databases. Facebook: the new page token has the 8 scopes needed (posts, comments,
answers, page info, Messenger); the agent proposed the page bio (85 characters, the limit is 101) and the welcome
message (152 of 160): both wait for the owner's approval.

## M62 — Facebook, model choices, NAS mount diagnosis (2026-10-02)

Facebook: page token valid, never expiring, scopes pages_show_list, pages_read_engagement, pages_manage_posts; the
saved page id was wrong (C91). Live: page_info, page_stats (2 posts), list_comments. The daily post routine run by
hand: 8 read tools in one run, answer "niente da pubblicare oggi" with its reasons, nothing proposed — it could not
read its own dream or the day's papers (no tool for that). Models: forge to the cloud (M55: 6/8 vs 4/8); synthesis
stays local because M40 measured the same quality (Claude 5.38, Qwen 5.25 and 6.00 out of 10, ±0.75 noise).
NAS: credentials verified with smbclient (the backup folder listed); the mount failure was the unit's private mount
namespace (C90). Tests 201.

## M61 — NAS backup, cloud ceiling, keys (2026-10-02)

Cloud calls of Aurora (115 with Claude Code): median 7,556 tokens in+out, p90 9,968, max 13,695 → the daily ceiling
AURORA_CLOUD_DAILY_TOKENS = 200,000 is ~20 calls at the p90 per paid provider. xAI after the top-up: 14 models; a
masked call to grok-4.20-0309-non-reasoning in 0.9 s, 224 tokens counted in the day's file; Gemini 2.5 Flash 0.9 s.
Local calls now traced with their step (local.call) to measure what a step would cost before moving it.
NAS: AURORA_BACKUP_DIR=smb://… was not a folder (systemd: "path is not absolute"); aurora-mount (root, one job, every
value checked: 10 injection attempts refused in the tests) mounts the share on /mnt/aurora-nas with nofail+automount;
the backup refuses to run while the share is not mounted (never the local disk in its place). Not measured yet: the
mount on the owner's NAS (needs his user/password and the units reinstalled), a backup over SMB.
Harvester: a delivery during an API restart now waits (delivered after 10 s in the probe). Tests 199.

## M60 — Backup, bug reports, cloud keys, routine PDFs (2026-10-02)

Backup (sys_backup, real data, NVMe to the same NVMe, test key and folder): first run 1,340 files, 30.4 GB read, 28.4 GB
written encrypted (identical files once) in 40.2 s; second run 4.5 s, 1 blob written (1 KB of status); verify --full
1,189 blobs decrypted and checked in 17.5 s; restore of the vault 130 files, 3.89 GB in 2.9 s, SQLite integrity_check
ok on every shard; a restored status file identical. Retention computed by hand and by code: the same 14 snapshots.
Bug report (live): 34 files, 443 KB, masked 838 addresses, 45 device fields, 39 tokens, 15 phones, 5 MAC, 5 of the
owner's words; the privacy scan of the publish found none of the owner's terms in it. Cloud: Gemini key valid
(61 models), a masked call to gemini-2.5-flash in 0.9 s with nothing real sent; xAI key valid but the team has no
credit (403, the provider's words now shown by sys_doctor). Routine "resoconto notturno" run by hand: PDF made and
downloadable. API: 37 GET endpoints answer 200, none changed. Tests 193; the publish check passes (no secret, none of the
owner's 13 terms, tests on the clean mirror).
Not measured: a backup to the second disk or the NAS (slower than NVMe), the timer firing at night (the unit is not
installed until the owner sets the folder), a restore of the whole 30 GB, the bug report page in the browser.

## M59 — Clean install, modular API, faster Plugins page (2026-10-02)

Clean install of the published commit (6faed9e, cloned from the mirror: GitHub is not reachable from Claude's shell)
in a new folder, `./install.sh --yes --no-services --with-video`: steps 1–10 in 10 min 55 s, all included — venv
(6.0 GB), hardware profile, every model (81 GB, SHA-256 verified), llama.cpp built for the GPUs (0.98 GB), 181 tests.
Step 11 needs sudo (no terminal here): now it says which commands to run and goes on (C81). Rerun: 7 s, nothing
downloaded or built twice. On the copy: sys_doctor 10/10 features; its llama-server with its model healthy in 6 s,
"17+25" → 42 (81 tok/s on a few words; not comparable with M-reference runs), vision projector loaded; GPU test with
its encoder and re-ranker passed. The ethics key lives in /etc/aurora: setup reuses an existing key (never
overwrites), so a second installation cannot replace the owner's.
API: svc_api.py (2,197 lines) split mechanically into aurora/api/ (core + 14 routers, largest 520 lines) and a
143-line entry point; 94 routes identical in path, methods, function, auth and order; 35 GET endpoints answer as
before; chat and agent runs live. /openapi.json was public (C79): now 404. Plugins page: 3.8 s → 0.002–0.004 s (C80).
Logs: plugins' stderr files rotate above AURORA_LOG_MAX_MB (copy and cut, gzip) in the daily purge. Tests 184.
Not measured: the services of a second installation started for real (same ports as the owner's), install on a
machine without the CUDA toolkit or the packages, a download interrupted and resumed, the agent's time saved per run
by the shared plugin host.

## M58 — Consolidation: features, gates, doctor, installer (2026-10-02)

Features on this machine: 10/10. Live gates, with the model setting pointed to a missing folder (then restored):
"togli lo sfondo" on a photo → plan understood, then the answer "Scontorno (SAM 2.1): non disponibile … Per
attivarla: … --models segment" (no GPU job started); dictation → HTTP 409 with the same kind of sentence; health
"8/10 disponibili". Models: sys_models_fetch --verify exit 0 (every SHA-256 matches, 10 models). GPU end-to-end
test (real encoder and re-ranker, reasoner paused): passed in 6.6 s. pip check: no broken requirements. 31 JS
modules parse. Units: 7/7 enabled and active. Logs of the last day: no new error (the firewall "ERROR" lines are the
firewall's own texts; plugin errors date from 30 Sep–1 Oct, one is C76). Installer selection simulated: this machine
→ dreams, speech, photo tools, photo AI (+23.4 GB), video offered (default no); a 8 GB GPU profile → photo AI and
video not offered with the measured reason. Structure tests: settings ↔ code, it ↔ en texts, a guide line per page,
the offline shell's files, models ↔ features ↔ installer groups. Tests 181, also on the clean mirror (C78).
Not measured: a real installation from scratch with the new installer (simulated only), a caged plugin's log line
written live (tested in the suite), the growth of plugins/*.stderr.log (not rotated by the host).

## M57 — Making videos (2026-10-02)

Model: Wan 2.2 TI2V 5B (Apache-2.0, diffusers, pinned, SHA-256 ok, 34.2 GB, 31.85 GB downloaded). On one RTX 5060 Ti
16 GB with the reasoner stopped: bf16 weights ran out of memory at 5 s 1280×704 (in the transformer); with the
weights stored in fp8 (computed in bf16), model CPU offload and VAE tiling: peak 10.87 GB from words, 13.88 GB from a
picture (the threshold AURORA_VIDEO_MIN_FREE_GB, first set at 12 from the words case only, is 14). Process RAM 42 GB
(probe). 5 s, 121 frames: 2 steps 272 s, 6 steps 384 s → 28 s per step + ~216 s fixed.
From the chat, 30 steps: «una volpe rossa che corre in un bosco innevato all'alba» → 1,089 s in all (estimate 19 min,
announced ready at 07:19, done 07:18:50), 8.2 MB, H.264 1280×704 24 fps; the fox comes from the back to the camera,
the forest stays coherent. «Anima questa foto» (CC photo of a cat, 960×960 kept square) → first failed in 16 s (C74),
then 1,111 s, 3.5 MB: the first frame is the photo, the cat turns its head to the camera and stays the same cat
(the blink asked for is not visible in the 3 frames looked at). Both carry the visible label and the metadata
(comment = disclosure line, description = IPTC trainedAlgorithmicMedia). During the job a chat message got the
"busy, ready at…" answer at once, without the reasoner; push "creation" sent for done and for the failure; the
reasoner healthy again after each job. Range requests on the file: 206. Tests 170.
Not measured: quality at 50 steps vs 30, portrait size, videos shorter than 5 s, the effect of fp8 on quality
(no bf16 run fits to compare), a dream starting during a video (the lock is there, the race was not provoked).

## M56 — Models per step, masking, cloud statistics (2026-10-02)

Router: 12 steps (route, translate, gate, extract, synthesis, verify, self, agent, rem, forge write, forge judge,
vision), each on local or a provider (Claude Code, Anthropic, OpenAI, Google, xAI, Mistral, OpenRouter; the last five
OpenAI-compatible). With no saved choice the old settings decide: all 12 local today, as before. Rule 9 still wins.
Masker: on by default; the first live call (Claude Code haiku, fake data) let a phone out at the end of a sentence
(C72); after the fix nothing real left (IP, e-mail, phone → placeholders) and the answer came back with the real
values, 4.1 s. Statistics from the traces in 0.06 s; 7 days: SSCC 18 compressions, 12% of characters saved (live),
reference M41 99,445 → 70,138 tokens (−29%), quality 8.25 → 7.62. Tests 168.
Not measured: an OpenAI-compatible provider (no key configured), quality of any step on a cloud model other than
Claude, the cost of a full day with cloud steps.

## M55 — Forge with the cloud, and I2 picture models (2026-10-02)

Forge benchmark with the cloud reasoner (owner's consent, masked samples): 8/8 built; right 6 for certain (harvester by
source, firewall denied, incidents, dreams, routines, log MB), 2 ambiguous (warnings per component: the plugin counts 516
firewall lines my truth misses; PDFs: 223 counting subfolders). Local reasoner: 4/8 right.
Models (Hugging Face, pinned, SHA-256 ok, optional in the installer): FLUX.2 klein 4B (Apache-2.0, 14.88 GB), Swin2SR x4
real-world (Apache-2.0, 0.05 GB), SAM 2.1 small (Apache-2.0, 0.17 GB); 15.1 GB in 78.6 s. torchvision 0.29.0 added
(locked with PyPI hashes; SAM 2.1 needs it). On a CC photo: cut-out 3.9 s CPU (score 0.959 with a full-frame box and a
smoothed alpha; 0.907 and a cut border before); upscale x4 of 320 px 23.6 s CPU; klein edit 29.6 s with the GPU swap
(peak 9.23 GB). Planner 24/25 (the miss was right: width 2400 = double), intent 30/30. From the chat: snow 30 s, cut-out
6 s, upscale 24 s — the upscale dropped the transparency (fixed: alpha enlarged apart).


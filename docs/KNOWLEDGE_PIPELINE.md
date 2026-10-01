# Knowledge pipeline — from the vault to the answer

Goal: the model answers **only** from the vault, never from its training. The
vault grows without bound, so what Aurora knows grows with it. Every stage below
has a measurement; no stage is adopted on a claim.

```
question
   │
   ▼
1. RECALL      find everything related, at any vault size
   │           (multilingual dense encoder + ANN index)
   ▼
2. SELECTION   keep what is actually pertinent, drop the rest
   │           (cross-encoder re-ranker + calibrated threshold)
   ▼
3. SYNTHESIS   group by domain → per-domain summary → cross-domain synthesis
   │           every sentence carries the sid of the soliton it comes from
   ▼
4. GROUNDING   answer only from the synthesis; if the vault has nothing
               pertinent, say so
```

## Measured recipe for stages 1-2 (2026-09-29, pool of 100k, MEASUREMENTS M11-M15)

| step | choice | why |
|---|---|---|
| query | translate to English with the LLM | +5.6 rank-1 dense, +9.3 rank-1 after re-ranking (M14) |
| recall | bge-m3 dense, top-100 / top-300 candidates | ceiling 86.1% / 89.8% (M15) |
| selection | bge-reranker-v2-m3, 1,024 tokens, English query | rank-1 76.9% in 2.0 s / 79.6% in 6.0 s (M15) |
| domains | label carried by each soliton, used to group results | as a search filter they hurt (M13) |
| not adopted | HyDE, lexical channel, z-score within domain, hierarchical mean vectors | all measured worse (M9, M13, M14) |

Known limit: dense recall loses ~8.5 points of document recall@48 per tenfold
growth of the vault (M11). More candidates raise the ceiling at a linear
re-ranking cost. The permanent retrieval test must track this curve.

## How each stage is measured

| stage | question it answers | metric | test set |
|---|---|---|---|
| 1 recall | is the right soliton among the candidates? | recall@k vs vault size | paraphrased questions with a known source soliton |
| 2 selection | is it kept, and is the noise dropped? | rank after re-ranking; score separation true vs others | same |
| 3 synthesis | does the information survive the summaries? | answer correct per source (judged); sentences supported by their cited sid | same, answered end to end |
| 4 grounding | does it refuse when the vault does not know? | abstention rate with the source removed; unsupported sentences | same questions, source soliton removed from the pool |

Stage 1 is measured at increasing vault sizes: the requirement is that quality
does not collapse as the vault grows.

## Rules

- A change is adopted only if it improves its stage's metric on the same test
  set, and does not worsen the others.
- Results are appended to `MEASUREMENTS.md`; this file describes the method.
- Test questions are paraphrases written by a model from the source text, in
  Italian, as the owner asks them. Never excerpts of the source: with excerpts
  any lexical method scores 100% and the measurement means nothing.

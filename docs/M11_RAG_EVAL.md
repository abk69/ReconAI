# M11.2 — RAG and grounding evaluation

Offline results on `m11_rag_eval_v1` measure retrieval and grounding against a synthetic policy corpus. They are not a claim about production accuracy.

## Architecture

M11.2 reuses M7.5:

- `hit_at_k`, `recall_at_k`, `mean_reciprocal_rank`
- `citation_precision`, `citation_recall`, `answer_fact_accuracy`
- `seed_eval_corpus` and `FakeEmbeddingProvider`
- `PolicyRetrievalService` and `PolicyGroundingService`

`python -m app.evaluation.m11_rag_runner` scores the dataset in memory with SQLite. It does not call Gemini, the network, or PostgreSQL.

`--live` runs the existing M7.5 live smoke. If `GEMINI_API_KEY` is unset, the command exits 0 and reports `LIVE_NOT_RUN`. Offline evaluation does not depend on that key.

The scripted model is not an LLM judge. It emits fixed statuses and citation choices so the application allowlist, abstention, and conflict rules can be measured.

## Dataset

`m11_rag_eval_v1` has five synthetic policies and 15 cases: direct support, paraphrased support, multi-chunk, irrelevant corpus, insufficient evidence, conflicting active versions, citation required, citation mismatch, low similarity, version boundary, multiple documents, injection in policy text, injection in a retrieved chunk, unsupported conclusion, and evidence below the grounding threshold.

A chunk is relevant when it belongs to the case policy and its section id is expected, or when every expected content marker appears in the chunk. Section matches and marker matches are unioned. This is the M7.5 relevance rule. An empty relevant set makes Hit@K, Recall@K, and MRR undefined.

## Retrieval metrics

Ranked with `top_k=5` and minimum similarity `0`. Undefined results are excluded from the mean. `defined_cases` is the denominator. `case_count` is the dataset size.

| Metric | Definition |
| --- | --- |
| Hit@K | 1 if at least one relevant chunk is in the top K, else 0. K is 1, 3, and 5. |
| Recall@K | relevant chunks in the top K / relevant chunks |
| MRR | 1 / rank of the first relevant chunk, else 0 |

## Grounding metrics

| Metric | Definition |
| --- | --- |
| Answer fact accuracy | Expected fact strings present in a SUPPORTED response / expected facts. Substring, case-insensitive. No LLM judge. |
| Citation precision | cited chunks that were retrieved / cited chunks |
| Citation recall | cited chunks that are relevant / relevant chunks |
| Abstention accuracy | cases with the expected non-answer status / cases that require abstention |

`INSUFFICIENT_EVIDENCE`, `CONFLICTING_POLICY`, and `SUPPORTED` are the M7.4 statuses. `SUPPORTED` with no citation is downgraded. A citation id outside the retrieved set rejects the response. Two ACTIVE versions of one document in the evidence set return `CONFLICTING_POLICY`. The evaluator does not pick a version.

Conflict detection for `conflicting-versions` supplies both ACTIVE versions to the existing detector. Production retrieval is not changed.

## Prompt injection

Injection sentences are policy data. The harness checks that the system instruction stays the M7.4 constant, that those sentences appear only in the user evidence block, that the exception status stays unchanged, and that a citation is still required. The scripted model does not follow policy text.

## Regression gates

`REGRESSION_GATES` freeze the M11.2 offline measurement:

- Hit@1, Hit@3, Hit@5: `1.0000` (14/15 defined)
- Recall@1: `0.8929`
- Recall@3, Recall@5: `1.0000`
- MRR: `1.0000`
- answer fact accuracy: `1.0000` (10/10 scored)
- citation precision: `1.0000` (11/11 scored)
- citation recall: `0.6786` (14/14 scored)
- abstention accuracy: `1.0000` (5/5)

These are regression gates for dataset `m11_rag_eval_v1`, not production accuracy targets.

## Commands

```bash
python -m app.evaluation.m11_rag_runner
python -m app.evaluation.m11_rag_runner --live
```

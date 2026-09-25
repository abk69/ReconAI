# M11.5 Performance, Cost, and Reliability Evaluation

Dataset: `m11_performance_eval_v1`.

Runner:

```text
python -m app.evaluation.m11_performance_runner
python -m app.evaluation.m11_performance_runner --live
```

The default runner does not call Gemini, the network, or another API. `--live` is optional and is printed as `LIVE_LLM_EVALUATION`. Live numbers are not mixed into the offline summaries.

These figures are a synthetic baseline. They are not a production SLA and they are not production performance.

## Clock and percentiles

Durations use `time.perf_counter`. Wall-clock timestamps are not used to compute durations.

Protocol defaults: `warmup_runs = 1`, `measured_runs = 5`. Both are arguments of `evaluate_dataset`.

Summaries report count, min, median, p95, and max. p95 is nearest-rank: `rank = ceil(0.95 * n)`, then the value at `rank - 1` in the sorted sample. For five samples, p95 is the maximum. For one sample, p95 is that sample.

`end_to_end` is the sum of one local M4, embedding, retrieval, grounding, planner, and execution sample. M6 is excluded and reported as `NOT_RUN` offline.

## Workloads

Eighteen synthetic cases. Character counts are stored on each workload. No procurement documents are used.

Document cases cover a 1-line invoice, an 8-line invoice, a 40-line invoice, a purchase order, a goods receipt, tab-separated XLSX-style text, noisy OCR-style text, and an M4-only repeat of the small invoice. The M6 case is present and is not executed offline.

Other cases cover policy retrieval, a grounded explanation, a valid resolution plan, an invalid planner payload, provider failure, timeout, a malformed provider response, a retryable failure, and an idempotent execution.

## Tokens and cost

Offline extraction, grounding, and planning report `TOKEN_USAGE_UNAVAILABLE`. The evaluator does not invent token counts.

Provider-reported usage is recorded only when `LLMUsageMetadata` contains counts. Negative counts fail the run.

Pricing version `m11.5-unpriced` has no prices. The offline cost status is `COST_UNAVAILABLE`. A numeric cost is emitted only when a caller passes an explicit price fixture. Tests use `test-fixture-not-billing` (`2` and `4` per million tokens). That fixture is not a provider price and not a billing charge.

## Reliability gates

Gates fail the runner when any of these is false:

- provider attempts stay within `llm_max_retries + 1` (default maximum attempts is 2)
- a timeout maps to `PROVIDER_TIMEOUT` and a malformed response maps to `PROVIDER_INVALID_RESPONSE`
- an invalid planner payload does not persist a plan
- a nested transaction failure rolls back the exception row
- the same idempotency key returns the same execution
- a different key after success is rejected
- duplicate successful side effects stay 0
- cost stays `COST_UNAVAILABLE` when no price fixture is configured

Latency values are not gated.

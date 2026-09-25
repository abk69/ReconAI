# M11 Evaluation Evidence

This report consolidates M11.1-M11.5.
It is engineering evidence.
It is not a product score, a ranking, or a production-accuracy claim.

ReconAI keeps deterministic financial truth, policy grounding,
AI-assisted interpretation and planning, human authorization,
and controlled execution apart.
M11 measures those dimensions separately.
Passing these checks does not by itself mean the system is production ready.

## Evaluation matrix

| Area | Dataset | Cases | Result type | Live call here? |
| --- | --- | --- | --- | --- |
| Extraction | m11_extraction_eval_v1 | 20 | synthetic offline measurement | no |
| RAG / grounding | m11_rag_eval_v1 | 15 | synthetic offline measurement | no |
| Agent safety | m11_agent_safety_eval_v1 | 30 | deterministic regression gate | no |
| Security | m11_security_eval_v1 | 25 | deterministic regression gate | no |
| Performance | m11_performance_eval_v1 | recorded baseline | observed local baseline | no |

## Extraction

Header accuracy and header completeness use different denominators.
Accuracy counts comparable extracted fields.
Completeness counts expected fields, including fields the evaluator
treats as missing when they are absent.
These are synthetic measurements, not real-world extraction accuracy.

| Metric | Result |
| --- | --- |
| Header accuracy | 58 / 58 = 1.0000 |
| Header completeness | 58 / 75 = 0.7733 |
| Line accuracy | 29 / 30 = 0.9667 |
| Line completeness | 29 / 47 = 0.6170 |
| Exact match | 12 / 20 = 0.6000 |
| Document success | 12 / 20 = 0.6000 |

Error counts: EMPTY_EXTRACTION 1, EXTRA_LINE 3, LINE_FIELD_MISMATCH 1, MISSING_FIELD 17, MISSING_LINE 4.

Offline M6 status is `NOT_RUN`.
Live extraction scores one case via
`python -m app.evaluation.m11_runner --live`.
That is a bounded smoke test, not a 20-case live benchmark.

## RAG / grounding

Hit, recall, and MRR values are copied from the M11.2 evaluator.
Defined cases are the cases where that evaluator defines the metric.

| Metric | Result |
| --- | --- |
| Hit@1 | 1.0000 (defined 14/15) |
| Hit@3 | 1.0000 (defined 14/15) |
| Hit@5 | 1.0000 (defined 14/15) |
| Recall@1 | 0.8929 (defined 14/15) |
| Recall@3 | 1.0000 (defined 14/15) |
| Recall@5 | 1.0000 (defined 14/15) |
| MRR | 1.0000 (defined 14/15) |
| Fact accuracy | 1.0000 (defined 10/10) |
| Citation precision | 1.0000 (defined 11/11) |
| Citation recall | 0.6786 (defined 14/14) |
| Abstention accuracy | 1.0000 (5/5) |
| Conflict detection | 1.0000 (1/1) |

Prompt-injection cases: 2.
Unsafe behavior count: 0.
Instruction-following violations: 0.

Offline retrieval uses the existing fake embedding provider.
Unknown citation ids are rejected by the grounding service.
Conflicting active versions are scored as CONFLICTING_POLICY.
These numbers are not a production RAG quality claim.

## Agent safety

30 / 30 cases were blocked on the properties this dataset measures.
Prompt-injection cases: 3.
Unexpected executions: 0.
Prompt-injection executions: 0.
Prompt-injection violations: 0.
Approval bypass count: 0.
Unsafe execution count: 0.
Idempotency: 4/4.
Audit chain: 1/1.
Parameter tampering count: 0.
Provider failure closed: True.

The planner proposes. The registry validates. A person approves.
Execution validates again. Handlers are allowlisted.
Audit events are append-only.

Missing, conflicting, or insufficient grounding does not by itself
stop planning under the current M8 contract.
Those cases still create no approval and no execution unless a
separate human approval is recorded.
This is evidence against the tested cases.
It is not a claim that the agent is safe in general.

## Security / prompt injection

25 / 25 cases were handled on the measured properties.
Secret leakage: 0.
Fact mutation: 0.
Citation bypass: 0.
Parameter tampering: 0.
Unauthorized execution: 0.

Frontend dangerouslySetInnerHTML count: 0.
Frontend files mentioning storage_path: 0.

Untrusted inputs are document text, OCR text, vendor text,
policy text, and retrieved evidence.
Trusted controls are deterministic M2 facts, application instructions,
schema and registry validation, and execution guardrails.
Injection text is data. It is not authority.
This is not a security certification.

## Performance, cost, and reliability

The latency table is the recorded M11.5 local observation.
M11.6 does not recompute it.
Durations are milliseconds from time.perf_counter.
Execution and end-to-end each have one sample.
They are not an SLA.

| Stage | Count | Min | Median | p95 | Max |
| --- | --- | --- | --- | --- | --- |
| m4 | 40 | 0.016 | 0.096 | 1.316 | 1.965 |
| embedding | 5 | 0.087 | 0.088 | 0.1 | 0.1 |
| retrieval | 5 | 5.641 | 5.961 | 6.6 | 6.6 |
| grounding | 5 | 8.111 | 8.775 | 12.201 | 12.201 |
| planner | 5 | 9.839 | 10.608 | 16.776 | 16.776 |
| execution | 1 | 18.154 | 18.154 | 18.154 | 18.154 |
| end_to_end | 1 | 46.038 | 46.038 | 46.038 | 46.038 |

Offline token status: TOKEN_USAGE_UNAVAILABLE.
Cost status: COST_UNAVAILABLE (m11.5-unpriced).
A numeric cost is not reported.
The test fixture test-fixture-not-billing is not provider pricing
and not a billing charge.

Recorded live M6 smoke, not rerun here:
model gemini-3.1-flash-lite, 7054.268 ms,
attempts 1,
provider-reported tokens input 308, output 272, total 580.
Cost: COST_UNAVAILABLE.

Invalid plan persisted: False.
Rollback: True.
Duplicate side effects: 0.
Same idempotency key reused: True.
Different key after success blocked: True.

## Regression gates

| Gate | This run |
| --- | --- |
| invalid_planner_payload_creates_no_plan | holds |
| unknown_action_execution_count | holds |
| missing_required_parameter_blocked | holds |
| approval_bypass_count | holds |
| unsafe_execution_count | holds |
| parameter_tampering_count | holds |
| idempotency_correct | holds |
| different_key_after_success_blocked | holds |
| duplicate_side_effects | holds |
| audit_chain_correct | holds |
| prompt_injection_execution_count | holds |
| citation_bypass_count | holds |
| frontend_dangerously_set_inner_html | holds |
| transaction_rollback | holds |
| cost_not_fabricated | holds |

## Live Gemini smoke tests

This report does not call Gemini.
There is no combined live pass rate.
A missing API key on an individual command is a skip, not a failure.

| Area | Command | Scope | This report |
| --- | --- | --- | --- |
| extraction | `python -m app.evaluation.m11_runner --live` | Scores clean-invoice only. Bounded smoke test. | NOT_RERUN |
| rag | `python -m app.evaluation.m11_rag_runner --live` | Existing M7.5 live grounding smoke. | NOT_RERUN |
| agent_safety | `python -m app.evaluation.m11_agent_safety_runner --live` | Existing M8.7 planner smoke. Does not approve or execute. | NOT_RERUN |
| security | `python -m app.evaluation.m11_security_runner --live` | One short synthetic invoice. Does not approve or execute. | NOT_RERUN |
| performance | `python -m app.evaluation.m11_performance_runner --live` | One M6 extraction call. Recorded observation is stored separately. | NOT_RERUN |

## Limitations

The datasets are synthetic and small.
Offline retrieval uses a fake embedding provider.
Live LLM checks are bounded smoke tests.
They depend on a local GEMINI_API_KEY and provider availability.
There is no production traffic benchmark, no SLA,
and no concurrency or load benchmark.
Extraction completeness is lower than header accuracy on this dataset.
M6 stays NOT_RUN offline.
Risk scores elsewhere in the product are not fraud probabilities.
Performance figures are one local observation.
Cost stays unavailable unless a price fixture is configured.

## Reproducibility

```text
python -m app.evaluation.m11_runner
python -m app.evaluation.m11_rag_runner
python -m app.evaluation.m11_agent_safety_runner
python -m app.evaluation.m11_security_runner
python -m app.evaluation.m11_performance_runner
python -m app.evaluation.m11_report_runner
python -m app.evaluation.m11_report_runner --json
```

Live commands are listed above. They are opt-in.


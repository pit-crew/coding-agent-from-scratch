# v0.53: Regression Comparison and Memory Retrieval Ablation

## Goal and Boundaries

This version adds a separate comparison result format and uses the fixed `coding-benchmark@1.1` to answer two questions: did v0.53 regress relative to the fixed v0.52; and within v0.53, how do results and usage change when automatic Memory summary retrieval is turned on? The comparison consists of three groups: `old-off`, `current-off`, and `current-on`. Each group repeats each case three times, for 36 independent slots in total; the two predeclared edges allow only the source version or the Memory switch to change.

All groups use the same cases, six-tool surface, permissions, model alias, round/timeout contract, a limit of 48 tool calls, and a cumulative limit of 64,000 tokens. The Memory seed is a semantic snapshot shared by the four cases, and each trial rebuilds the store from its new workspace identity. Only automatic retrieval in the Context is turned on; Memory CRUD tools are not registered, developer Memory/Skills/References/MCP are not inherited, and retrieved bodies are not written into comparison evidence. The independent grader runs after the Agent finishes; fixture results are not model results.

This plan does not authorize paid calls. After the implementation and offline acceptance are complete, a new review manifest is generated. Only after the user reviews the manifest and starts it explicitly can a live batch run. Live runs do not retry, rerun, or replace slots; an interruption keeps the ledger and the unrun slots. A new batch must use a new directory.

## Contract and Runs

The new `mini_agent.evaluation.comparison_schema` separately defines `ComparisonSpec`, `ComparisonRun`, and `ComparisonTrial`, schema 1, without changing the coding case set or the reliability result contract. The Spec validates the field allowlist, complete commit IDs, the fixed budget, the changes allowed between groups, unique slots, decimal fixed-point prices, and sensitive fields; at most 8 groups, at most 10 repetitions, and at most 320 slots in total.

The coordinator executes in order with the current comparison code, and the target version is materialized via `git archive` into a temporary directory the runner creates itself. The external adapter's `PYTHONPATH` points only at the target checkout, and the target Runtime, MemoryStore, MemoryRetriever, and evaluation interfaces are checked before requests. Each run of each case gets a new workspace, HOME, Memory, and temporary path. The worker calls the target version's `AgentRuntime.run()`, `ToolExecutor`, `PermissionGate`, and `EvaluationRuntimePolicy` directly; shell, MCP, Memory CRUD, and subagents are not registered.

Each slot is first recorded atomically as `running`, and after it finishes the trial digest and terminal state are committed atomically. The worker tool observer computes invalid repetitions on the side and does not change Runtime decisions. Comparison evidence stores only relative paths, digests, usage, status, grader results, and bounded logs; Memory bodies are not written into trial results. The grader is read from the frozen cases and started independently with a time limit. Cleanup failures and interruptions are kept as separate states.

## Metrics and Reports

`comparison_metrics.py` computes the grader pass rate, strict task success, Agent/grader call and result counts, permission denials, invalid repetitions, subagent call counts, input/output token sources, cost, duration observation counts/median/p95, and unrun slots. The recovery success rate is fixed at `null` for coding comparisons. Prices are computed with frozen USD per-million-token unit prices and `Decimal`; when prices or usage are missing, cost is `null`, which does not represent an exact bill.

`report-comparison` validates the spec, plan, source digests, slot order, suite copy, trial/artifact paths, and SHA-256, then rebuilds JSON and Markdown from the raw trials. Each paired slot has a grader result and a relative evidence path. Whether the batch's slots are complete and whether all predeclared comparison edges are comparable are reported separately; failures, source mismatches, Memory anomalies, and evidence problems go into the review queue. Three repetitions serve only as descriptive observations.

## CLI

```bash
PYTHONPATH=src python -m mini_agent.evaluation validate-comparison <filled-spec.json>
PYTHONPATH=src python -m mini_agent.evaluation plan-comparison <filled-spec.json> --output <new-plan-dir>
PYTHONPATH=src python -m mini_agent.evaluation self-test-comparison --output <new-run-dir>
PYTHONPATH=src python -m mini_agent.evaluation run-comparison <review-plan.json> --live --output <new-run-dir>
PYTHONPATH=src python -m mini_agent.evaluation report-comparison <run-dir>
```

`validate-comparison` does not connect to a model; the template's revision, profile, and price placeholders must first be filled in according to local conditions. `plan-comparison` pins the current clean HEAD, the case set, grader calibration, the target checkout, the run environment, the Memory digest, and the full execution order. `self-test-comparison` uses fixed responses and runs the 36-slot offline matrix assembled with the real Runtime plus failure/denial/repetition boundary probes, without sending model requests. `run-comparison` runs only with `--live` and the user's explicit approval. `report-comparison` does not connect to providers, does not regrade, and does not change raw evidence; it only produces rebuildable derived reports.

The comparison configuration template and the four Memory seeds are in `tests/fixtures/evaluation/comparison/`. The template is not a live manifest that can be run directly, and the seeds must be confirmed during review to contain no patches, answers, hidden tests, or grader content.

## Change and Acceptance Status

- [x] Separate schema, source snapshots, ordered plan, atomic ledger, and report rebuilding.
- [x] Isolated target-version worker, six-tool permissions, fixed budget, and the automatic Memory retrieval switch.
- [x] Memory seeds for the four cases, the 36-slot fixed-response offline matrix, and denial/failure/repetition probes.
- [x] Public digests of the coding suite and a helper interface for the frozen grader runner; old result formats stay separate.
- [x] CLI, comparison guide, baseline status, tutorial, and version documents synced.
- [x] Dedicated tests, the full test suite, and the fixed-response offline matrix acceptance passed; full pytest is 849 passed, all 36/36 fixture trials are gradable and pass the grader, and both declared comparison edges are comparable. The fixed responses make the Agent state `blocked`, and strict task success is 0/36; these results only verify the harness and are not ability results. See `evaluation-regression-plan.md` for the detailed record.
- [ ] The v0.53 tag required by the tutorial facts script is created manually by the maintainer; the assistant performs no tag operations.
- [x] The user explicitly started the frozen 36-slot live batch; 36/36 slots have terminal states, and the raw evidence and rebuilt report are archived in `docs/evaluation/baselines/v0.53/live-20261008-01/`.
- [ ] Live ability acceptance: all 36 model requests in this batch were `ProviderConnectionError`, with no successful responses or tool calls, so no version regression or Memory benefit can be judged from it. To get ability samples again, the connection failure must be investigated and a new run ID frozen separately; this batch's slots must not be resumed or replaced.

Stage 14 is still not complete as a whole: the v0.51 suite 1.1 live coding baseline and the v0.52 suite 1.6 live reliability baseline remain listed separately; v0.53 has a fully recorded formal live batch, but the ability comparison conclusion is invalid, and live acceptance is still not complete.

## 2026-10-08 Post-Live Grading and Diagnostics Fixes

The grading eligibility of group summaries and paired reports is unified: provider/worker/grader/cleanup failures are excluded from the ability denominator while the raw grader facts are kept; Agent exceptions, execution timeouts, refusals, and budget exhaustion are not hidden. Slot terminal states, contract consistency, valid pairs, and comparison completion are reported separately, and infrastructure errors are deduplicated by slot. Report rule 2 is independent of the historical frozen contract rule 1, and historical spec/plan/trial files are not rewritten.

The external worker adds redacted cause-chain diagnostics of at most four levels, and schema 1 allows optional diagnostic fields; old and new results are compatible. `report-comparison --output` writes the corrected version into a brand-new separate directory. For the corrected version of the formal batch, see [report.md](../evaluation/baselines/v0.53/live-20261008-01-report-corrected/report.md): 36 slots in terminal states, 36 infrastructure failures, 0 valid ability samples and valid pairs, and the comparison is not complete; the hashes of the 150 original archived files are unchanged. This round sent no model requests, did no network probing, and does not claim the root cause of the connection failure is solved.

Fix acceptance: the targeted comparison regression is 37 passed; full offline pytest is 871 passed. The tutorial structure, README, and `git diff --check` pass; the tutorial facts check lacks only the `v0.53` tag the user creates manually. The first full run inside the sandbox was 26 failed, 841 passed, 3 skipped, and the failures came from loopback port binding restrictions; the final full run, approved to run outside the sandbox, all passed. No paid model requests were sent.

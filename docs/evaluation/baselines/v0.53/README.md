# v0.53 Comparison Baseline

## Formal live batch

**Run status: all 36/36 slots have terminal states; no ability comparison conclusion holds, and v0.53 live acceptance is still not complete.** Batch `67583764-8595-4c68-ad4d-8f2254f23bdf` ran on 2026-10-08 according to the reviewed manifest, with the frozen current source at `807b95bf7b1e51cc6d622a8a519b447c77c7fbb5`. The raw ledger, comparison contract, plan, each trial, and the rebuilt report are archived in [`live-20261008-01/`](live-20261008-01/).

Each group's 12 trials made only 1 model request each, and all 36 ended with `ProviderConnectionError`; successful responses and tool calls were both 0. The independent grader ran on each unchanged trial workspace and returned a failure, and cleanup was complete 36/36. Because the Agent received no model response, the grader's 0/36 cannot be interpreted as a version ability regression or as no Memory benefit. The saved evidence contains only redacted error categories, without underlying connection exception details; no specific network or provider cause is inferred from it.

The structural batch status is `completed`, and all 36/36 slots are kept, with no retries, make-up runs, or replacements. The frozen condition checks and pair coverage of both edges passed, each covering 12 pairs; this only means the contract conditions and slot pairing are complete, not that there are interpretable ability samples. The Agent token source is `estimated` throughout, with no provider usage from successful responses; the price snapshot lacks prices, so cost is `null`. These tokens and durations cannot be treated as an actual bill or the cost of a normal model run. The Memory on group had one summary retrieval in each of its 12 trials, but without model responses, the memory benefit cannot be evaluated.

The formal report can be rebuilt from the archived inputs: [`report.json`](live-20261008-01/report.json) and [`report.md`](live-20261008-01/report.md). This report records the evaluation chain and provider failure facts and is not a version regression or Memory ablation conclusion. To get ability comparison results, first find and fix the connection failure, then freeze a new run manifest and run ID; this batch is not continued, and slots are not replaced.

## 2026-10-08 Grading and Diagnostics Correction

The original archived report wrongly treated the normally returned grader boolean as ability grading eligibility, so it still marked `comparison_complete=true`, comparable edges, and a change of 0 when the whole batch failed to connect. The original report, trials, and ledger are all kept, and these fields of the original report can no longer be used to interpret ability.

The [corrected Markdown](live-20261008-01-report-corrected/report.md) and [JSON](live-20261008-01-report-corrected/report.json) use report rule 2 and reference the original run ID and the digests of four input files. All 36/36 slots have terminal states, `batch_complete=true`; 36 infrastructure failures, valid ability samples and valid pairs of both edges are 0, `comparison_complete=false`, and the ability pass rate and difference are `null`. The grader's raw 0/36 failure facts are still shown. The 150 original archived files have matching SHA-256 one by one before and after generating the corrected version; for per-file digests, see the [archive verification record](live-20261008-01-report-corrected/archive-verification.json).

The comparison worker adds bounded, allowlisted exception cause chain diagnostics, keeping only the error category, the recognized underlying exception category, an integer errno, and a TLS verification code. Old results lack this field, and connection causes cannot be made up for them. This round made no network probes or model requests and did not fix or verify the connection root cause; a new live still needs to be re-frozen and started explicitly.

## Offline records

The fixed-response self-test directory `/private/tmp/mini-agent-v053-comparison-offline-20261008-03/` is not a live sample and does not count toward the ability success rate: all 36/36 fixture trials have terminal states, the independent grader passed 36/36, and both comparison edges passed the condition checks; Agent strict task success was 0/36, because the fixed responses triggered `blocked`. The failure, refusal, and repetition boundary probes observed 1 tool failure, 1 permission refusal, and 1 invalid repetition respectively.

The earlier diagnostic run `/private/tmp/mini-agent-v053-comparison-offline-20261008-02/` is kept as a separate failure record: tasks requiring test files lacked an empty `tests/` directory, and the cache regression task's grader did not pass. After fixing the runner, the full fixture self-test was rerun in a new directory; the diagnostic results are not mixed into the formal live batch.

The memory material contains only background, interface conventions, and investigation methods. Each trial rebuilds a separate MemoryStore; evidence does not save injected bodies. The comparison applies only to the frozen four `coding-benchmark@1.1` tasks, model binding, and automatic summary retrieval, and does not represent cross-task memory learning or other capabilities. Three repetitions are only descriptive observations, with no claim of statistical significance.

Stage 14 as a whole is still not complete: the v0.51 `coding-benchmark@1.1` live baseline and the v0.52 `reliability-boundaries@1.6` live baseline each stay listed separately as not complete.

Fix acceptance: targeted comparison regressions 37 passed; full offline pytest 871 passed. The tutorial structure, README, and `git diff --check` passed; the tutorial facts check lacks only the `v0.53` tag the user creates manually. The first full run inside the sandbox was 26 failed, 841 passed, 3 skipped, with failures from loopback port binding limits; the final full run approved to run outside the sandbox all passed. No paid model requests were sent.

# Stage 14: Evaluation & Regression Implementation Plan

> Status: on 2026-10-08 the suite 1.6 candidate completed targeted fixes and offline acceptance (832 tests, 50/50 offline boundaries); there is no live result for this candidate yet. The latest separate 2026-09-30 suite 1.5 live batch completed 21/21 slots with strict recovery 6/14; process wait timeout and recovery after crash each had only 1/3 fault triggers, so the v0.52 live sample baseline is still not complete. Earlier #08/#09 and the pre-fix 5/14 are kept as separate historical results. v0.50 is complete, the v0.51 coding baseline is still separately not complete, and Stage 14 as a whole is not complete
> Suggested version range: `v0.50` Evaluation Harness, `v0.51` Coding Benchmark, `v0.52` Reliability Evaluation, `v0.53` Regression & Comparison
> Capability prerequisites: Stage 13 lightweight Agent Collaboration (`v0.47`–`v0.49`) and the earlier execution, verification, recovery, Memory, MCP, and Skills
> Related plans: `agent-collaboration-plan.md`, `reliable-execution-plan.md`, `session-persistence-resume-plan.md`, `adaptive-planning-plan.md`

## 2026-10-08 v0.53 Comparison Grading Correction

All 36 requests of the v0.53 formal batch `67583764-8595-4c68-ad4d-8f2254f23bdf` failed to connect. The original report wrongly treated the grader's boolean result as ability eligibility and marked the comparison as complete by mistake. It now uses a unified eligibility decision and a separate report rule 2, keeping the raw grader 0/36; valid ability samples are 0, the comparison is not complete, and the ability difference is null. The [corrected report](../evaluation/baselines/v0.53/live-20261008-01-report-corrected/report.md) is saved separately, and the 150 original archived files are unchanged.

The new worker supports bounded, allowlisted connection cause-chain diagnostics, but unknown causes cannot be added to historical batches after the fact. This round only fixes the grading and diagnostics gaps; there were no network probes, paid requests, or new live batches; v0.53 live acceptance is still not complete.

## 2026-10-08 Fixes for Observed Failures

The user authorized fixes. The current executable candidate was raised to suite 1.6, and the old 1.5 keeps being rebuilt read-only. The `SessionValidationError` was located: after an invalid `recover.caused_by_failure_id` was refused, it was still written as a causal reference, so the State export failed. Rejection records now keep only references that exist, unknown IDs are recorded as null, and only rejected records may have no causal failure; no failures are forged and no generation is advanced.

The budget fix is implemented by providing a separate finishing prompt when the application creates/resumes the Runtime; the full project instructions, user, and historical system constraints are kept, and the finish carries only authoritative completion facts, without repeating investigation tool rounds. The working prompt, calibration, the 64k limit, and independent verification are unchanged. The verification repair scenario added the directory and search tools and was frozen again; old batch results cannot be moved into the new suite. For the files, tests, and limitations, see the [fix record](../evaluation/baselines/v0.52/live-failure-repair-20261008.md). This round sends no model requests; offline acceptance must pass first, then whether to run a targeted live is decided.

## 2026-09-30 Live Batch with the Current Binding

The user explicitly started a separate 21-slot batch; the re-frozen suite digest is `833eefa4…`, the Runtime fingerprint `90f115c2…`, and the binding fingerprint `fbfec446…`. All 21/21 slot terminal states are readable, with no infrastructure, cleanup, or source errors; faults triggered 17 times, invariants 15 passed, 2 failed, and 4 incomplete, the grader passed 11, and strict recovery was 6/14. Of 136 request decisions, 126 got provider usage responses, and 10 were refused early because the protected context could not fit into the remaining quota; the input of none of the 126 responses exceeded the original proxy estimate or the calibrated reservation. The report can be rebuilt byte for byte; see the [new batch report](../evaluation/baselines/v0.52/live-20260930-01/report.json) and the [check record](../evaluation/baselines/v0.52/live-20260930-01/report-validation.json).

Process wait timeout and recovery after crash each triggered the fault only 1/3 times, and the other four slots cannot be rerun or replaced; one crash slot hit a local `SessionValidationError` before the trigger, and the exact trigger condition is not confirmed yet. Tool exception recovery was 2/3, verification repair 1/3, MCP disconnect 2/3, and subagent timeout 0/3; permission denial passed the boundary 3/3. Full live sample coverage still does not reach the threshold. The next step is to investigate the local session save exception and the execution paths of the untriggered slots separately, then decide whether the implementation needs changes; the next batch is not continued automatically to reach some recovery rate target.

## 2026-09-30 Separate Provider Probe

The current binding was approved by the user as a separate probe group different from #09, with a cost cap of 1 USD and prices based on Xiaomi's first-party overseas real-time API table. The redacted probe stopped after two requests because a tool request raised `ProviderProtocolError`: the ordinary request used 12 input / 15 output, and the third paired request was not sent; no retries, and no live slots used. The conservative cost upper bound is about 0.1403 USD. See the [probe review](../evaluation/baselines/v0.52/provider-probe-20260930-01/review.json) for details. The next step is to locate the protocol error first; when evidence is insufficient, the whole batch is not rerun.

Later separate probes 02/03 located the error in the name/argument validation of streaming tool calls, and raising the output limit still reproduced it. The adapter now ignores later empty field overwrites; probe 04 completed a three-request tool feedback chain, and the cumulative conservative cost upper bound of the four groups is 0.42294812 USD. See the [baseline notes](../evaluation/baselines/v0.52/README.md) and the [probe 04 review](../evaluation/baselines/v0.52/provider-probe-20260930-04/review.json) for details. The small-request protocol check passed; the single root cause of the historical error, large-input estimation, and Agent recovery were not verified by this evidence, so the suite 1.5 live baseline stays not complete.

One synthetic large-input request with the current binding reported 5,124 input tokens, below the 7,084 proxy estimate and the 14,424 cold-start reservation; the cumulative conservative probe cost upper bound is 0.42367052 USD. That request was close to #09's after-the-fact byte shape, but its body and binding differ, so it cannot replace a historical reproduction or a live recovery sample. The [review record](../evaluation/baselines/v0.52/provider-large-input-20260930-01/review.json) lists this limitation separately. The next step is still to re-freeze the current Runtime and suite first and evaluate whether one controlled live batch is needed; the old 21-slot results are not mixed or rerun.

Then a small-request tool feedback probe was completed with the suite's 1,024 output quota; the cumulative conservative cost upper bound of the six probe groups is 0.42375368 USD. The suite 1.5 pre-check is valid, and the corrected Runtime's offline matrix passed 50/50 boundaries. For the combined numbers, see the [acceptance summary](../evaluation/baselines/v0.52/provider-validation-20260930.json). This completes targeted protocol and estimate shape verification but does not yet form a new live recovery baseline; the next step is to freeze a review manifest under the current Runtime fingerprint, then consider a separate live batch.

## Targeted Fixes After Suite 1.5

Offline addendum on 2026-09-30: the only provider response of #09 actually had 13,748 input tokens, while the old estimate was 2,918 and the reservation 6,092; the cumulative quota was not exhausted. OpenAI Chat admission now estimates the UTF-8 size of the full request JSON (including fields and tool schemas) plus an explicit margin, and the estimator version enters the calibration key; when capacity is tight, only omittable history is trimmed, while user corrections are protected. The late 19k/27k regressions on long histories, byte-for-byte rebuilding of old reports, and the offline matrix must all pass. See the [offline record of this round](../evaluation/baselines/v0.52/estimator-offline-repair.md) for details. This round sends no paid probes and does not use the old suite 1.5 review manifest as the basis for freezing a new candidate.

Whole-batch paid live is paused. Fixed the problem that the current working request could not use the plan progress and verification reservations, added diagnostics for budget refusals and tool argument JSON errors, and added late recovery regressions under long investigation histories. For the specific files, acceptance evidence, and limitations, see the [targeted fix record](../evaluation/baselines/v0.52/stage-budget-repair.md). This round does not create suite 1.6, change historical batch results, or rerun failed slots.

Before the next live, the candidate runtime, request policy, and grading classification must be re-frozen, and the new manifest reviewed; the old suite 1.5 review manifest cannot authorize a changed candidate. Run only one separate batch and keep all failures. Later fixes continue only for reproducible implementation defects; repeated investigation, execution order, and insufficient model recovery ability are recorded as ability results, and reaching some recovery rate cannot be a reason to loop indefinitely.

## v0.50 Implementation Record

- Added the `mini_agent.evaluation` schema, worker, runner, report, and four commands: `validate`, explicit `run --live`, two fixed-response `self-test`s, and read-only rebuilding `report`.
- Real trials use `AgentRuntime.run()`, `ParentRuntimePolicy`, `ToolExecutor`, a six-tool limit, and a non-interactive PermissionGate; the visible tool surface is separate from explicit pre-authorization, and tool paths are limited to the trial workspace before the handler.
- The Runner creates a new workspace, HOME, and temporary Memory path for each trial, limits the size of fixtures/workspaces/logs/diffs/results, and runs the grader after the Agent process stops. Single results are published atomically; live and fixture denominators are not merged.
- Added a scale fix case and a hidden grader. The offline check confirms that the original fixture does not pass and a known correct fix does; two fixed-response trials each completed independently from the same initial files and passed the grader.
- Targeted regression: `PYTHONPATH=src python -m pytest -q tests/test_evaluation_v050.py`, 12 passed; CLI `validate` and `self-test` in two separate output directories both passed.
- Full acceptance: `PYTHONPATH=src python -m pytest -q`, 653 passed; `scripts/check_tutorials.py`, `scripts/check_tutorial_facts.py`, `scripts/check_readme.py`, and `git diff --check` all passed.
- Real `--live` acceptance is complete: the first ProviderConnectionError inside the sandbox is kept as a failed live trial; after network permission was approved, the successful trial `fecf1d04-48f2-4c86-bf42-e0588dabc1fa` finished with `agent_stop_reason=text`, State `done`, the grader passing, and cleanup complete. The successful trial had 4 successful model responses, 3 tool calls, provider usage of 6,520 input / 243 output tokens, Agent 3,004 ms, and grader 38 ms; the price snapshot is missing, so cost is still null.
- Live raw result directory: `/private/tmp/mini-agent-eval-v050-live`; two live trials are kept, and the report has denominator 2, passed 1, and connection errors 1. This small sample is used only to verify the chain and is not a coding ability benchmark.

## v0.51 Implementation Record

- Added the frozen case set `coding-benchmark@1.0`, in the fixed order `pagination-boundary`, `orders-discount-receipt`, `cache-expiry-regression`, `config-priority-investigation`. Each case has its own initial files, grader, and known-good version; the configuration investigation case does not name the faulty file in the task text.
- The offline pre-check confirmed case by case: all four original versions are refused, and all four known-good versions pass. The unittest required by the cache case must also pass on the correct code and fail with an assertion on the original buggy implementation; variants such as pagination errors, one-sided order fixes, weak cache tests, and configuration priority errors are all refused by the grader.
- Added bounded Suite / SuiteRun contracts, case and file tree digests, ID/version fingerprints, schema 2 suite TrialResults, 12-slot ordered orchestration, atomic ledger updates, keeping start failures/interruptions, and per-case report rebuilding; a suite run pins the Git revision, the runtime code fingerprint, and the model source, and checks the implementation source before and after each trial; the original schema 1 Case/TrialRequest/single-case TrialResult stay readable.
- Added `validate-suite`, `run-suite --live --repeats 3`, and `report-suite`, and updated Lesson 51, the operation manual, the evaluation guide, the README, CHANGELOG, and the package version.
- After user review, suite 1.0 ran 12 live trials in order; the raw records are in `docs/evaluation/baselines/v0.51/`; no samples were rerun or replaced. A review on 2026-09-28 found that receipt grading used an unpublished exact format; the old results are kept and marked disputed; the suite was raised to 1.1 with a public format and argument rejection requirements. The real 1.1 baseline has not run yet, and the 1.0 results cannot be reused.
- Review fixes: temporary cleanup restores only the permissions of read-only reference directories the runner itself created and does not follow symlinks; an interruption first stops child processes within bounds and saves started trials, then interrupts the suite; trials with inconsistent sources are kept but excluded from grading, blocking the full baseline decision.
- Fix acceptance: targeted evaluation tests 31 passed, full pytest 674 passed, and the suite 1.1 offline pre-check, tutorial structure, README, and diff checks passed; the tutorial facts check fails only because the user has not created the `v0.51` tag yet, and the assistant does not create tags. Live was not rerun, and historical trials were not rewritten.

## v0.52 Implementation Record

- Froze `reliability-boundaries@1.0`: 18 scenarios, including MCP stdio/loopback HTTP, 3 durable commit failure boundaries, and 2 recovery feedback variants; the offline plan has 50 slots, and the live subset 7 scenarios × 3 runs, 21 slots in total. Suite, scenario, request, and reliability TrialResult use separate schema 1 and pin material digests. The review candidate suite digest at that time was `8ea1fab57ec079a86b22fab140614dada88cc1e22e8e37f527e5c36b9d08904f`.
- Added named bounded fault drivers, a Runtime worker, Evidence verification, a read-only dedicated report, extraction of user-side `/resolve`/plan decision/save actions, and four dedicated CLI commands. The live worker uses `AgentRuntime.run()`, `ParentRuntimePolicy`, the standard tools, and the Manager; crash recovery claims the derived session in a new Python process. The production Runtime's default behavior was not changed and permissions were not widened.
- The current candidate `offline-20260928-security-redaction` ran 50/50 slots: every fault actually triggered, and 50/50 invariants passed; no infrastructure errors, incomplete evidence, or unrun slots. One restricted sandbox self-test produced 8 injection errors because the loopback HTTP fixture could not start; it is kept separately in `offline-20260928-sandbox-loopback-limited`, and no slots were rerun one by one. Fixtures do not run the Agent, so the task grader, task success, and the recovery success rate are null.
- Four live batches of evidence are all kept. In the first batch `live-20260928-01`, several faults did not trigger. In the intermediate candidate `b0db6164…0125a3c`, `live-20260928-02` planned 21 slots: 18 trials ran, and 3 subagent calls were recorded as infrastructure errors because of provider HTTP 400; of the 18 trials, faults triggered 6 times, invariants passed 3 times, the grader passed 0 times, and recovery success was 0/6. `live-20260928-03` recorded 8 trials and 13 infrastructure errors, faults triggered 5 times, invariants passed 3 times, the grader passed 0 times, and recovery success was 0/5. After the redaction fix, `live-20260928-04` recorded 17 trials and 4 infrastructure errors, faults triggered 9 times, invariants passed 7 times, the grader passed 1 time, and recovery success was 0/9. None were rerun or replaced automatically.
- The problems that the live worker did not register the standard `recover`/`request_replan` control tools and that tasks did not state the exact trigger actions were fixed in an earlier candidate. The live batches reproduced the request artifact persisting local provider redacted values; the request copies of the first three batches were all redacted, the raw digest evidence is kept in `artifact-security-findings.json` in each, and the runner was fixed to not persist redacted values and to scan artifacts before publishing. The fixed offline matrix all passed; the live baseline is still not complete because four scenarios did not reach at least 3 gradable trigger samples. The production Runtime's default behavior was not changed and production authorization was not expanded. The suite 1.1 coding baseline is still separately not complete, and the disputed v0.51 suite 1.0 results were not changed.

### 2026-09-29 Evaluator Corrections

- The frozen suite was raised to `reliability-boundaries@1.1`; old artifacts are kept, and the current pinned digests are in the suite and baseline notes.
- `tests/fixtures/evaluation/reliability/`: added initial/known_good public tests for the six recovery scenarios; permission denial changed to a safe termination boundary task; the process changed to wait for explicit termination, and material and suite digests were recomputed.
- `evaluation/reliability_grader.py`: added bounded independent-process behavior grading that supports equivalent correct code; `reliability.py` calibrates with both public tests and behavior grading before the first live request.
- `evaluation/reliability_worker.py`: fixed argument matching of refused attempts, process binding and cleanup, request budget estimation before requests, and tool feedback evidence; keeps the execution phase and redacted exception location/provider diagnostics. Crash recovery also distinguishes an unavailable grader from a task failure.
- `evaluation/reliability_schema.py` keeps old archives readable and allows new runs only for the current suite; `reliability_report.py` excludes pure boundary permission scenarios from the task/recovery denominators.
- `tests/test_evaluation_worker_v052.py` drives the full live worker assembly and uses fixed model responses to check permission termination, process timeout under slow responses, read exception recovery, verification failure repair, request budgets, and HTTP diagnostics; no real API requests are sent.
- Suite 1.1 live ran three batches in order; for the full data and per-scenario results, see `docs/evaluation/baselines/v0.52/README.md`. In the latest batch `live-20260929-03`, all 21 slots have terminal states, 20 trials are gradable, and 1 `mcp-disconnect` slot was excluded as an infrastructure error because of provider HTTP 400; faults triggered 13 times, invariants passed 12 times, the grader passed 9 times, and recovery success was 5/10. `process-wait-timeout`, `crash-after-handler`, `mcp-disconnect`, and `subagent-timeout` did not reach 3 gradable trigger samples each; the baseline is not complete and is not rerun automatically.
- In `live-20260929-01`, the subagent exception diagnostics once hid the original exception by reading the wrong `binding.profile.model` attribute; after switching to `model_id`, the old batch was kept and a new batch started. `live-20260929-02` further exposed that the provider does not accept Python `\Z` in JSON Schema regexes; `tools/delegation.py` now uses a portable pattern for provider schemas, while local UUID argument validation still uses strict fullmatch. Related regression tests 43 passed, and `git diff --check` passed.
- `live-20260929-03` exposed a different provider HTTP 400: in thinking mode the server requires later requests to carry `reasoning_content`, and the generic OpenAI Chat adapter did not keep that provider extension field. The redacted diagnostics are kept; this compatibility problem was not yet fixed or verified live, and it is not an API credential error. One failed request counts only toward an infrastructure slot and is not retried automatically.
- Correction acceptance: worker/schema/recovery/services regressions 58 passed; tests related to the portable UUID schema fix 43 passed; the suite 1.1 public tests and behavior grading pre-check passed, and the 50/50 offline matrix passed. The final full `PYTHONPATH=src python -m pytest -q` was 734 passed. The tutorial structure check, README check, and `git diff --check` passed; the tutorial facts check still fails only because of the missing `v0.52` tag the user creates manually.

### Corrections After the Third Live Batch (suite 1.2)

- `providers/openai_chat.py` keeps `reasoning_content` from ordinary responses and streaming chunks, validates its type and length, and passes it only as ordinary assistant protocol data; it is not shown in the body and does not enter State/Trace summaries. The new `tests/test_reasoning_content_v052.py` checks HTTP encoding/decoding, tool rounds, and full round trips through the context and session, plus refusal of missing/empty values, bad types, and oversize values.
- `tests/fixtures/evaluation/reliability/` corrected the crash precondition phase; the timeout scenario froze the full child budget; four complex scenarios added parent-side directory and search tools. The contract was raised to 1.2, all material and suite digests were recomputed, and old 1.0/1.1 archives stay readable.
- `reliability_worker.py` enforces the public child budget in both schema and argument validation, refusing a second investigation and real child provider requests; invariants whose target fault did not trigger are recorded as incomplete, keeping the preceding stop reason. Full worker regressions cover child timeout collection and task recovery, crash side effects, and the pending boundary.
- This suite 1.2 live used the new directory `docs/evaluation/baselines/v0.52/live-20260929-04/`; old trials/reports were not changed, and the production Runtime's permissions, recovery, or completion conditions were not relaxed. All 21 slots have terminal states, with no infrastructure errors or automatic retries.
- Live results: faults triggered 19 times, invariants passed 17/failed 2/incomplete 2, the grader passed 12, and recovery success was 5/16. All three `crash-after-handler` runs triggered correctly and passed the boundary invariants, but all exhausted the total token budget before verification of the current generation; all three `subagent-timeout` runs triggered and passed the result collection and usage settlement invariants, with only one full recovery; all three `mcp-disconnect` runs triggered with no HTTP 400, with only one successful recovery. `process-wait-timeout` triggered only once; the other two slots did not finish starting the process or did not reach the wait point, so the suite 1.2 live baseline is still incomplete. For the full per-scenario data and evidence, see `docs/evaluation/baselines/v0.52/README.md` and the `report.json` of that run.
- Correction acceptance: full pytest 749 passed; the suite 1.2 pre-check passed and the offline matrix passed 50/50, with raw results at `/private/tmp/mini-agent-reliability-v052-suite12/`. The 8 loopback injection errors from a separate sandbox attempt are kept. The tutorial structure, README, and diff checks passed; the facts check lacks only the v0.52 tag the user creates manually. The suite 1.1 historical results and the suite 1.2 new batch are kept separately.

### Corrections After the Fourth Live Batch (suite 1.3)

- `evaluation/reliability_worker.py`: relative process directories are resolved against the trial workspace and out-of-bounds paths are refused early in the argument validator; the wrapped handler keeps bounded diagnostics while the Executor still converts exceptions; the first run and the crash continuation share the evaluation prompt, and formal resume instruction discovery is unchanged.
- Added `evaluation/reliability_diagnostics.py`: records per-request context category estimates, schema overhead, the provider usage source, the output limit, the cross-phase cumulative budget, and refusal reasons, without saving bodies; the existing budget and completion conditions are unchanged.
- `reliability_schema.py`, `reliability.py`, and the frozen fixtures were raised to 1.3, keeping read-only report compatibility with old versions; process tasks state the cwd semantics publicly, and the new digests are in the baseline notes.
- `tests/test_evaluation_worker_v052.py` covers four legal cwds, refusing illegal cwds before admission, and the new plan and verification of the actual derived session; the new `tests/test_evaluation_diagnostics_v052.py` covers numeric diagnostics, missing usage, limits, paths, and the consistency of the two-phase prompts.
- Synced the evaluation guide, baseline notes, manual, tutorial, README, and CHANGELOG; this round runs no paid live, does not change old trials, and performs no tag operations for the user.
- The full offline matrix for the current source fingerprint passed 50/50; run ID `504b0c57-db4d-4bc9-8436-a12cffe7380c`, directory `/private/tmp/mini-agent-reliability-v052-suite13-final/`.
- Verification: the targeted worker/diagnostics/schema/recovery regressions of this round 59 passed, and the pre-check passed; two full runs were both 758 passed, 1 failed, and the only failure was the old `test_cleanup_cannot_succeed_when_wait_does_not_confirm_exit` hitting `PermissionError: [Errno 1] Operation not permitted` during cleanup, which also reproduced when rerun alone outside the sandbox. The exact reason for the system refusal is not confirmed. `tests/test_process_management_v026.py` keeps all failure assertions and adds a bounded 3-second wait for the real child process in the finishing phase after the mocked wait; the single regression passes, and the production process cleanup conditions are unchanged. The tutorial structure, README, and diff checks passed; the facts check still lacks the v0.52 tag the user creates manually.

- Final acceptance: full pytest 759 passed, targeted regressions including the process tests 77 passed; the pre-check and the current source offline matrix passed 50/50, and historical report rebuilding keeps the original results. The earlier test failure is kept as an investigation record.
- The first suite 1.3 live batch `docs/evaluation/baselines/v0.52/live-20260929-05/` completed 21/21 slots; faults triggered 20 times, invariants passed 18/failed 2/incomplete 1, the grader passed 14, and recovery success was 8/17; infrastructure errors, unrun, unreadable, cleanup failures, and manual review items were all 0. All three `crash-after-handler` runs kept the boundary, but all exhausted the shared token budget in the recovery phase; `process-wait-timeout` triggered 2/3, and the only untriggered slot exhausted the budget before calling the process tool. HTTP 400 did not recur; no automatic reruns or replacements. The suite 1.3 live baseline is therefore still not complete; the full report is that batch's `report.json`.

### Budget Correction After the Fifth Live Batch (suite 1.4)

- `evaluation/reliability_diagnostics.py`: uses the standard library Fraction for calibration and rounding up, with an initial 2× input estimate plus a 256 margin, calibrating upward only from this trial's provider usage (an extra 10%); reserves input and output at once and records layered refusal reasons.
- `evaluation/reliability_worker.py`: the first run and the continuation use the same admission/output limits, and the continuation inherits the real usage and calibration of the earlier phase; the tools of an over-limit response get budget errors fed back one by one and are not admitted to handlers, and plain text cannot complete either. The production Runtime, permissions, and completion conditions are not relaxed.
- `reliability_schema.py`, `reliability.py`, and the 18 frozen scenarios were raised to 1.4, publishing and validating request_budget_policy in the suite/pre-check, with all digests recomputed; old 1.0–1.3 reports keep loading read-only.
- `tests/test_evaluation_diagnostics_v052.py` covers the borderline balance, already over/already exhausted, input underestimation, unknown usage, and cross-phase calibration; `tests/test_evaluation_worker_v052.py` covers a full crash continuation inheriting calibration and the tool/text block after an over-limit response.
- The budget correction and offline acceptance phases did not increase the budget, rerun, or change historical live, and performed no tag operations. A conservative estimate is not an exact tokenizer; context efficiency and execution order still need later work.
- Verification: the offline matrix of the current source passed 50/50, run ID `cd7f12b3-7ffc-408b-8d27-e0e54b7e6b41`, directory `/private/tmp/mini-agent-reliability-v052-suite14-final/`; targeted regressions 67 passed, full pytest 767 passed; the suite pre-check and rebuilding of the historical 1.1/1.2/1.3 reports passed (still 5/10, 5/16, 8/17). The tutorial structure, README, and diff checks passed, and the tutorial facts check lacks only the v0.52 tag the user creates manually. The 26 loopback port failures of the full run inside the sandbox and the 8 offline injection errors are kept separately, with no slots replaced.
- The suite 1.4 live batch `docs/evaluation/baselines/v0.52/live-20260929-06/` completed 21/21, and all 21 faults triggered; invariants passed 19, failed 2, the grader passed 15, and recovery success was 1/18 (permission denial is a boundary-only sample). No infrastructure errors, incomplete evidence, unrun, cleanup failures, or manual review items; sources consistent. All seven scenarios have 3 triggered and gradable samples, reaching the frozen coverage threshold.
- Budget observations: of 144 request decisions, 128 were actually sent and got provider responses, and 16 were refused before sending because of `insufficient_request_budget`, with `planned_output_limit=0`, without continuing tool rounds; all 128 actual inputs were higher than the raw estimate, but none exceeded the calibrated reservation, outputs never exceeded the quota, and recorded budget overruns were 0. The three crash recoveries inherited about 22k cumulative tokens and calibration state from the earlier phase. Because no provider returned an over-limit response, the branch that blocks tools/completion after a response was not triggered by this batch's live samples. The refusals made 16 trials finish with `token_limit`, showing that conservative admission and repeated context/execution order still need further work; the estimate does not guarantee that any provider request is never exceeded. The raw report is that batch's `report.json`, with no retries, reruns, or replacements.

### Systematic Corrections After the Sixth Live Batch (suite 1.5 candidate)

This round implemented the formal parent task budget, the request context view, and the completion finish according to the approved plan, without raising the live 64,000-token limit. The suite 1.5 digest is `833eefa4cb6e108439fb407c0981383fcd8b04724887e42c40ba9bcd65baa3a7`; then, following user instructions, a new separate live batch ran, and the historical 1/18 result of suite 1.4 stays unchanged.

| File | Implemented change |
|---|---|
| `src/mini_agent/budget.py` | Standard-library `TaskBudgetController`; main requests, summaries, and finishing are each calibrated by the frozen binding/schema; reservation, real settlement, full-reservation charging for unknown usage, and request ID idempotency. |
| `src/mini_agent/config.py`, `config_example.py`, `agent.py` | Adds the optional `PARENT_TASK_TOKEN_BUDGET=None`; off by default in the CLI, can be enabled for new tasks, and the saved limit takes priority. |
| `src/mini_agent/state.py`, `session.py` | The optional budget ledger in State takes part in session integrity and atomic commits; a commit failure before the request or after settlement stops; unknown pending requests are charged only once on recovery. Pure query completion blockers are used for reminders and finishing checks. |
| `src/mini_agent/runtime.py` | General cumulative budget admission, output within quota, same-binding summary settlement, finishing reservation; after an overrun, handlers are not run and the task is not completed, with errors fed back per tool. Fixes the defect where repeated admission of background starts without persistence left pending attempts. |
| `src/mini_agent/context.py`, `prompt.py` | Under a budget, keeps the complete tool protocol of the last two rounds, keeps selected reasoning fields as is, and keeps all user messages; the original history is unchanged. Stops explicitly when protected content cannot fit; uses the finishing view and omits tool schemas once verified with no blockers. Reads first when the task has exact paths. |
| `evaluation/reliability_worker.py`, `reliability_diagnostics.py` | Live and crash recovery connect to the same Runtime controller; diagnostics only observe formal admission. Tool count, round, time, and permission constraints are kept. |
| `evaluation/reliability_schema.py`, `reliability.py`, the 18 `scenario.json`, and `suite.json` | Freeze the 1.5 budget contract and recompute digests; old 1.0–1.4 are still rebuilt read-only. |
| `evaluation/reliability_report.py`, `cost_replay.py` | New evidence reports three layers separately: correct files, current-generation verification, and model completion; the strict recovery success rate is still the main metric. When old evidence lacks the new fields, report content is unchanged. |
| `tests/test_task_budget_v052.py`, worker/diagnostics tests | Add regressions for cost, calibration, persistence failure, unknown charging, full recovery and finishing, protocol trimming, and old session compatibility. |

Calibration is done independently under each request category and model/tool schema digest: with fewer than two pure provider observations, the input reservation is `2 × raw + 256`; after that, it uses `ceil((raw + the largest positive estimation error of the last eight) × 1.10) + 256`. Main execution outputs at most 1024, summaries 512, and finishing 512 tokens, still bound by the smaller model configuration limit. Admission requires an output of at least 256 (unless the model limit is smaller). Finishing rounds are reserved according to unfinished steps and verification obligations; this is not automatic plan advancement or automatic completion.

The historical numeric replay is recorded in the [cost replay](../evaluation/baselines/v0.52/budget-repair-cost-replay.json): 144 observed decisions, 16 originally refused, 885,685 input / 44,417 output tokens. Keeping the old requests and old balances and applying only the new reservation rules, 130 decisions would be admitted, and no observed input exceeds the new reservation; 6 historical outputs exceed the new output quota. This replay does not simulate the trimmed context, future model replies, or recovery success, and cannot be used to claim a recovery rate improvement.

The implementation phase started no live, replaced no slots, and performed no tag operations; fix acceptance was based on offline regressions, the 50-slot boundary matrix, the pre-check, historical report rebuilding, and documentation checks. After an explicit instruction to run was received, a suite 1.5 live was run separately; that batch was not retried, rerun, and no slots were replaced.

Fix acceptance: full tests 812 passed, targeted regressions 95 passed; the final source offline matrix triggered all 50/50 with all invariants passing, run ID `831bf1bc-14b9-4886-98e9-344ea8ef4c1b`. The tutorial structure, README, and diff checks passed; the tutorial facts check failed only because of the missing v0.52 tag the user must create manually. The earlier 799 passed / 72 passed were the acceptance of the previous candidate and do not cover this round. The fix acceptance summary is in [stage-budget-repair-validation.json](../evaluation/baselines/v0.52/stage-budget-repair-validation.json).

The new live batch [`live-20260929-07/`](../evaluation/baselines/v0.52/live-20260929-07/) (run ID `45e3d375-d69f-4318-80b7-bf284c078def`) planned 21 slots; 19 have readable trials, and the other 2 reported `provider_protocol_error` during provider response call validation. The error records have no provider status or detail, and the root cause is unknown, so it is not attributed to HTTP 400. All invariants of the 17 triggered and gradable trials passed; the permission boundary-only trial does not enter the recovery denominator, and strict recovery success was 5/14 (35.7%). The layered results are 16 task trials, 10 with correct final files, 5 passing current-generation verification, and 5 with normal model completion; the 5 all meet all three conditions at once.

By scenario, `verification-repair` was 3/3 successful, `mcp-disconnect` 2/3, `tool-handler-exception` 0/2, `process-wait-timeout` 0/2, `crash-after-handler` 0/1, and `subagent-timeout` 0/3. The two protocol errors fell in the tool exception and crash-after-handler scenarios; the process wait scenario also had one untriggered run. Three scenarios do not have enough triggered and gradable trials, so the suite 1.5 live baseline stays not complete.

Of 130 request decisions, 117 got provider responses, 11 were refused because the protected context could not fit into the remaining task budget, and the other 2 are the provider protocol errors above. Actual input was higher than the raw estimate 114/117 times, but no input exceeded the calibrated reservation, no output exceeded the quota, and recorded budget overruns were 0. The live report, rebuilt from the frozen manifest, ledger, and raw trials, is byte-identical to the archived file; the evidence is `report.json`, `suite-run.json`, `review-plan.json`, and `trials/` in the batch directory.

Then, as the fix record suggested, the pre-check was rerun and new suite 1.5 live batches were started separately. All 21 slots of [`live-20260929-08/`](../evaluation/baselines/v0.52/live-20260929-08/) were `provider_http_503` and did not enter recovery grading. [`live-20260929-09/`](../evaluation/baselines/v0.52/live-20260929-09/), run after the provider recovered, had 20 `provider_connection_error`s and 1 trial that stopped on token limit before fault injection; 3 verification repair trials had injection hit records, but the matching model requests failed, so they were still excluded as infrastructure errors. All 21 trials completed cleanup, the recovery denominators of both batches were 0, and the raw reports passed byte-identical rebuilding. No batch was retried, rerun, or had slots replaced; the new recovery rate is still unknown, and the suite 1.5 baseline stays not complete.

## 1. Goal and Positioning

The first thirteen stages answered "what the Agent can do and how to constrain it". The last stage answers: **given the same batch of real tasks, how many can it complete on its own, how many can it recover from after failures, do new capabilities improve results, and what does it cost?**

This stage delivers a repeatable task set, an executor, independent acceptance, structured results, and comparison reports. Coding ability evaluation must really start the matching version of the Agent, let it call the model and tools, and change code in an isolated workspace; existing unit tests can only prove implementation boundaries and cannot replace the task success rate. Offline fixtures are used to verify the evaluator itself and to inject controllable faults, and cannot pose as real model ability results.

Target flow:

```text
freeze testcase + initial repository + run configuration
→ create an isolated workspace for one trial
→ start the real Agent and record run facts
→ run independent acceptance after the Agent stops
→ save results, failure reasons, and reviewable evidence
→ compare repeated trials under the same conditions and different configurations
```

Stage 14 closes with evaluation and defect fixes; it does not by default add a Sandbox, GUI, plugin marketplace, or multi-layer Agent Teams because evaluation found capability gaps.

## 2. Scope and Non-Goals

### 2.1 Scope of this stage

- `v0.50`: define the testcase, runner, trial result, metrics, and offline self-test; the real run path exists from the first version.
- `v0.51`: build a small, representative coding task set covering bug fixes, local changes, multi-file changes, and independent test verification; then expand by difficulty.
- `v0.52`: use controllable fault and recovery scenarios to measure the reliability of permissions, tools, processes, persistence, MCP, and subagents.
- `v0.53`: fix tasks and conditions and compare versions, models/providers, and the presence or absence of Memory, Skills, and Subagents; publish a reviewable summary report.
- Core metrics: task success rate, independent verification pass rate, number of tool calls, tokens/cost, duration, fault recovery success rate, and invalid repetitions. Each must have a fixed denominator, calculation rule, and missing-value semantics.

### 2.2 Not in this stage

- The Agent's final text, `done` status, or its own verification are not treated as an independent success decision.
- PermissionGate, Plan, durable commits, recovery, or subagent permissions are not relaxed for scoring; evaluation configuration can only choose existing supported capabilities.
- Live model calls do not enter the default offline tests or ordinary CI; real evaluation must be started explicitly and is bounded by a budget.
- A single successful demonstration is not used to claim stable improvement; runs with different initial states, permissions, or acceptance conditions cannot be merged directly for comparison.
- Model cost estimates are not written as exact incurred bills, and results never store API keys, real endpoints, or auth headers.

## 3. Evaluation Decisions to Freeze First

### D1: A testcase is a reviewable task contract

Each testcase has a stable ID, version, user task, fixed initial code version or fixture, allowed workspace and run budget, independent acceptance steps, expected observable behavior, and a difficulty label. Acceptance rules are frozen before running and cannot be changed on the spot after seeing some Agent output. The task text does not give away the answers of hidden acceptance scripts; public tests can be task material, while hidden or reserved tests are run only by the evaluator after the end.

The task set should include positive examples and diagnostic negative examples, such as incomplete requirements, permission denials, and verification failures. Tasks must be resettable and rerunnable from the same initial state; fixtures committed to the repository contain no credentials, personal data, or external services that require the network. If real project tasks cannot pin their dependencies or test environment, they are first marked as exploratory samples and do not enter the main success rate.

### D2: The Runner starts the real Agent, and the grader is independent

One trial starts a real Agent process or an equivalent public entry from a clean isolated workspace, using the real model binding and the existing tool, permission, and budget boundaries. Creating and cleaning up the isolated workspace touches only paths the runner itself created and does not change the developer's current working tree. The evaluator records a summary of the start configuration, the process exit status, the Agent terminal state, and resource consumption, and checks the changes and runs acceptance after it stops.

The grader runs outside the Agent process, using assertions and tests frozen in advance. The Agent's own `purpose=verification` runs are run facts; the tests of independent grading are evaluation facts, and the two are recorded separately. If the Agent times out, oversteps, is refused, exits abnormally, or produces no gradable result, the trial is still written to disk with an explicit status and cannot disappear from the denominator. Faults of the evaluator itself are listed separately as `infrastructure_error`, rerun after fixing, and not counted as Agent success or failure.

### D3: Isolation and permissions are part of the evaluation conditions

Each run has its own workspace, session/Memory path, and temporary artifacts; by default it does not inherit the developer's private Memory, Skills, References, MCP configuration, or broad authorizations. Testcases that need some capability explicitly provide checked fixtures and configuration and save a credential-free summary. All side-effect tools are still decided by the original PermissionGate; unattended evaluation uses a predefined, scoped policy, and when authorization is missing it records the refusal and never answers `allow` automatically.

Model calls can depend on the real credentials in the local `config_local.py`, but result files can only store non-sensitive source summaries such as the profile/provider/protocol/fingerprint. Real calls, model usage, and external services may change; offline harness tests never touch the real API. Fault injection acts only on child processes, workspaces, or test Servers the runner created, and never interrupts the developer's processes or real external services.

### D4: Results can be summarized and can also explain failures

Results save at least the suite/testcase version, code revision, a run configuration summary, the random seed or repetition number, the budget, start/end times, the Agent terminal state, the independent acceptance result, the classified failure reason, parent and child model and tool usage, and locatable log/state evidence paths. The references between raw trials and summaries are kept, and aggregate reports cannot overwrite single facts.

Unified metric definitions:

| Metric | Definition |
|---|---|
| Success rate | Trials passing all independent acceptance / gradable trials; also report the counts of unrun trials and evaluation infrastructure faults |
| Verification pass rate | Share of trials passing the predeclared independent tests/checks; separate from the Agent's own verification |
| tool calls | Counted separately for the parent Agent and subagents, then a total; refused and failed calls also have explicit counts |
| token / cost | input/output separately, marking provider, estimated, or mixed; cost depends on an explicit price snapshot and is left empty when prices are missing |
| latency | Wall-clock time from handing the task to the Agent until it terminates; acceptance time listed separately |
| Recovery success rate | Trials that went through the predefined fault, completed the specified recovery flow, and passed acceptance / gradable recovery trials |
| Invalid repetitions | Number of calls in the same progress phase that repeat the same tool and normalized arguments without producing new facts; the rule is fixed and samples are kept |

Besides averages, report distributions or quantiles and show raw counts and denominators. Timeouts, permission denials, budget exhaustion, model errors, Agent code errors, and failed acceptance are counted separately; successful samples cannot be the only ones kept. The existing State/Trace are the source of run facts, and their completion decisions are not changed in reverse to fit grading.

### D5: Fix conditions when comparing, and handle randomness

A comparison group fixes the testcase version, initial code, grader, budget, permissions, workspace initialization, and run order rules; each configuration runs several times, and every raw result is kept. Only when the compared factor is the only difference can the difference be interpreted as that factor's effect. Reports give absolute success counts, rates, durations, and usage together, not just percentages; when samples are too small, they are only observations, with no claim of statistical significance.

Version comparison prefers immutable commit IDs; tags can be created manually by the user, but the runner does not create, move, or delete tags. Different versions may not support the same capabilities or result fields, so a common task subset and field mapping must be defined first, with incompatible items marked as not comparable. Model/provider comparison records the actual binding summary; model version drift or call failures must be listed separately. Memory, Skill, and Subagent ablations use explicit configuration and the same task conditions; a feature cannot be "turned off" by changing core safety logic. The Memory off group and on group must specify the same initial memory snapshot, to avoid contamination across trials.

### D6: People review only the standards and disputed samples

Before a formal batch evaluation, the user reviews representative tasks and success criteria; each trial is run and graded automatically by the runner. Samples where the requirements allow several reasonable solutions, the tests pass but quality is questionable, or automatic acceptance cannot cover them go into a manual review queue, and the report gives their count and decisions. Manual decisions must carry reasons and stay in the results, never silently rewriting the raw automatic grade. Subjective quality dimensions that were not reviewed only show cases and are not folded into the main success rate.

## 4. Version Slices and Implementation Tasks

### 4.1 `v0.50`: Evaluation Harness

1. Define versioned schemas for testcases, suites, trials, run configuration, and results; constrain IDs, paths, commands, budgets, and output sizes, and refuse configuration parse failures before any real call.
2. Implement isolated workspace creation, real Agent start, timeout/cancellation, bounded cleanup, independent acceptance, and atomic result saving. Provide an explicit live entry and a default offline self-test entry.
3. Extract structured facts from the existing Runtime/State/Trace/usage; unify counts and missing values, and never infer success by parsing terminal text. The reporter can rebuild summaries from several trials.
4. Use fixed model responses and a small local fixture to verify the runner's normal path, failures, timeouts, refusals, grader faults, cleanup, and repeated runs; then do a real Agent trial run on a small task and record the actual cost and duration.

Acceptance: the same testcase can be run repeatedly from the same initial state; each run has its own result; the real model is really called, and independent acceptance really runs after the Agent stops; failed trials are not lost.

### 4.2 `v0.51`: Coding Benchmark

1. First build a small number of tasks with clear acceptance: a single-file bug, a multi-file behavior change, a fix with a regression test, and a task that needs investigation before the change. Each case states the problem from the user's point of view and observable success criteria.
2. Pin the task repository/fixture, dependencies, and acceptance commands; verify that the grader rejects the original buggy version and accepts a hand-made correct fix, to avoid cases that "always pass".
3. Run the Agent several times and save the diff, independent test results, failure categories, usage, and duration; review cases that are too easy, ambiguous, environment-dependent, or that leak the answer.
4. Produce the first baseline report: per-case results and summaries side by side, listing cases that automatic tests cannot judge and that need manual review.

Acceptance: the task set covers at least the four kinds of coding work above; the original buggy state cannot pass directly; the report can answer "which cases are completed reliably, and where failures usually happen".

### 4.3 `v0.52`: Reliability Evaluation

1. Define a controllable fault matrix: tool exceptions and denials, repair after verification failure, background process timeouts, crashes at durable commit boundaries, recovery issue handling, MCP disconnects/errors, and subagent timeouts/cancellation/interruption.
2. Each scenario freezes the injection point, the expected invariants, and the success conditions. Uncertain calls after a crash must not be replayed; permission denials must not become implicit approval; child results must not replace parent verification.
3. Offline fixtures trigger faults precisely and verify that the evaluator recognizes them; scenarios that need to evaluate the Agent's decisions and recovery ability then run the real Agent. Distinguish protocol/runtime invariant tests from model-driven recovery success rates.
4. Save the injection facts, raw State/Trace summaries, the source of simulated user feedback, recovery steps, and the final independent acceptance; failures must not be erased automatically by rerunning.

Acceptance: each kind of key boundary has at least one reproducible case; the report distinguishes "the system correctly refused a dangerous action" from "the Agent finally completed the task", and the fault recovery success rate has a clear denominator.

### 4.4 `v0.53`: Regression & Comparison

1. Fix the suite and common task subset used for comparison, and choose reproducible old/current version commits, model/provider configurations, and capability ablation combinations; first check whether the run conditions of each group are comparable.
2. Run and summarize success, verification, calls, tokens, cost, latency, recovery, and repetition metrics with a predeclared number of repetitions; report missing usage and unfinished trials.
3. For significant regressions or unexpected improvements, spot-check the raw traces and changes, identifying grader problems, environment drift, and real behavior changes; after fixing defects, keep the pre-fix report and rerun under the same conditions.
4. Publish rerunnable commands, configuration templates, task versions, result schemas, raw trial references, and stage conclusions; state item by item which capability benefits are supported by data and which have no evidence yet.

Acceptance: complete at least one old/current version comparison and one Memory, Skill, or Subagent ablation; readers can locate the trials and acceptance evidence behind every summary number and reproduce the offline part.

## 5. File and Boundary Mapping

| Location | Expected change | Responsibility |
|---|---|---|
| `src/mini_agent/evaluation/` or a separate `scripts/evaluation/` | New | testcases, runner, grader, results, summaries; choose the least intrusive entry at implementation |
| `tests/fixtures/`, `tests/` | New | Offline tasks, model/fault fixtures, and harness self-tests |
| `docs/evaluation/` | New | Suite notes, how to run, metric definitions, reports, and review records |
| `src/mini_agent/runtime.py`, `state.py`, `trace.py` | Read-only in principle; targeted structured exports when needed | Do not change Agent decisions or safety thresholds for scoring |
| `docs/tutorials/`, the operation manual, `README.md`, `CHANGELOG.md` | Updated with actual versions | Teaching, usage, and version navigation; follow the matching writing rules |
| `AGENTS.md` | Updated only when runtime hard constraints change | Evaluation conventions go first into this plan and the evaluation documents |

## 6. Cross-Cutting Acceptance and Delivery

1. Default tests are fully offline; real Agent evaluation is started through an explicit entry and shows the task count, call budget, and estimated upper bound. Credentials are only read from local configuration and never written into testcases or results.
2. The workspaces, sessions, Memory, and test Servers of each trial do not contaminate each other; after failures and interruptions, cleanup is bounded, and incomplete cleanup must report the path or process identity and cannot be marked successful.
3. The grader is independent of the Agent's `done`, self-reports, and its own verification; grading criteria are frozen before running, and any manual review is recorded.
4. Reports keep all valid trials, unrun trials, timeouts, infrastructure errors, and missing metrics; cross-version or ablation comparisons state the common tasks and configuration differences.
5. Results that use the real Agent cannot be replaced by offline simulated results; offline fault tests and real model performance are presented separately.
6. The core runtime still depends only on the standard library; if the evaluation periphery uses optional dependencies, they must have a standard-library fallback and must not become a default install or core dependency.
7. After each version, run the related tests; before delivery, run `PYTHONPATH=src python -m pytest -q`, `PYTHONPATH=src python scripts/check_tutorials.py`, and `PYTHONPATH=src python scripts/check_readme.py`. If the real API is unavailable, record explicitly that live acceptance did not run; the stage cannot be called complete.
8. If results show a regression, first submit a reproducible testcase and a minimal fix; do not sacrifice permissions, recovery, or protocol completeness for a score. Git tags can only be operated manually by the user.

## 7. Stage-Level End-to-End Scenarios

1. The same bug fix case runs three times in a clean workspace; the Agent really calls the model, changes files, and terminates, and the grader runs tests independently, producing three traceable trials and a summary.
2. The Agent claims completion and its own verification passed, but a hidden behavior test fails; the final grade is a failure, and both kinds of verification facts are kept.
3. A model call failure, a permission denial, and an Agent timeout each become different failure categories; a broken infrastructure test command is not counted as an Agent failure.
4. Inject a crash at the durable tool boundary, derive a recovery session, and handle the issues; uncertain calls are not replayed automatically, and the independent tests after recovery decide the final result.
5. When the MCP test Server disconnects, a subagent times out, or a result is not collected, the evaluation can state whether the safety boundary held and whether the task was finally completed.
6. Compare two code versions and the Memory switch on the same suite; the initial state, permissions, and budget of each group are the same, and the report shows the raw per-case results and summaries, without writing one fluctuation as a definite improvement.

## 8. Definition of Done and Project Wrap-Up

- [x] `v0.50` has a unified harness with offline self-tests and explicit live runs, and the result schema and grading boundary are stable.
- [ ] `v0.51` has a frozen, rerunnable coding task set, and the real Agent baseline and independent acceptance report are reviewable.
- [ ] `v0.52` has a controllable fault matrix that clearly distinguishes runtime safety invariants from Agent recovery ability.
- [x] The `v0.53` regression comparison and Memory retrieval ablation implementation and offline acceptance are complete; the formal 36-slot live batch has run and can be rebuilt, but all 36 model requests were provider connection errors, so no ability comparison conclusion can be formed, and live acceptance is still not complete.
- [ ] The user reviews representative tasks and success criteria; manual review of disputed samples is recorded, with no need for manual acceptance of every run.
- [ ] Documentation, tutorials, change records, and the three full verifications are complete; live evaluation is actually run, and items not run are listed explicitly as not complete.

After these conditions are met, the project closes with the evidence chain "implement capabilities—run for real—accept independently—compare for regressions". Later maintenance follows only discovered defects and concrete user needs, with no preset new large capability stages.

## v0.53 Implementation and Acceptance Record

For implementation details and the contract, see [this version's plan](v053-regression-comparison-plan.md). Comparison results use a separate schema 1 and do not extend the coding case set or the reliability formats. The three fixed groups are v0.52 with Memory retrieval off, v0.53 with retrieval off, and v0.53 with retrieval on; four cases × three repetitions per group, 36 slots in total. The old source commit is pinned to `9d498f91f7ca21caa7f4f842fba0a49075754f20`. The full v0.53 commit and the same model alias are written only into the generated review manifest; missing prices use `null`, and bills are not guessed.

- Added ComparisonSpec / ComparisonRun / ComparisonTrial, target version archives and the Runtime interface pre-check, the isolated worker, the ordered ledger, the shared entry of the independent grader, metrics, and the report rebuilding CLI.
- The four Memory seeds contain only interfaces, background, and investigation methods; trials use the target version's MemoryStore and MemoryRetriever, and the workspace, HOME, Memory, and temporary directories are isolated from each other. Evidence does not save injected bodies.
- The fixed-response self-test runs the actual target version's AgentRuntime without requesting the provider; it also covers failed tools, permission denials, invalid repetitions, corrupted evidence, and old runner/benchmark compatibility.
- Live comparison status: the formal batch `67583764-8595-4c68-ad4d-8f2254f23bdf` ran on 2026-10-08 according to the user-reviewed manifest; the frozen current source is `807b95bf7b1e51cc6d622a8a519b447c77c7fbb5`. All 36/36 slots have terminal states and complete cleanup, with no retries, reruns, or replacements. All 36 model requests were `ProviderConnectionError`, with 0 successful responses and tool calls; the grader ran 36 times on unchanged workspaces and passed 0 times. So the batch chain has a complete record but cannot answer version regression or Memory benefit questions, and v0.53 live ability acceptance is still not complete. The redacted evidence saves only the error category, without finer connection exception causes; prices are missing, and cost is `null`. For the full raw ledger, trials, and report archive, see the [formal live baseline](../evaluation/baselines/v0.53/README.md).
- The v0.51 `coding-benchmark@1.1` live baseline and the v0.52 `reliability-boundaries@1.6` live baseline each remain not complete; Stage 14 as a whole cannot be marked complete because of the v0.53 offline delivery.
- Final implementation revision `34ef871`; the comparison self-test uses the target commit checkout and fixed responses, directory `/private/tmp/mini-agent-v053-comparison-offline-20261008-03/`. All 36/36 trials have terminal states, the independent grader passed 36/36, and both edges passed the comparability check; strict task success of all three groups was 0/12, because the fixture replies triggered the `blocked` terminal state. This is a check of harness structure and evidence, not an Agent ability result. The fixed boundary probes each recorded 1 tool failure, 1 permission denial, and 1 invalid repetition. The earlier failed self-test `/private/tmp/mini-agent-v053-comparison-offline-20261008-02/` is kept; the problem was that cases requiring test files lacked an empty `tests/` directory, and after the fix it was rerun in a brand-new directory.
- Full pytest: 849 passed; `validate-suite` confirms that the grader refuses the original implementations of all four `coding-benchmark@1.1` cases and that all four known_good versions pass. The tutorial structure check, README check, and `git diff --check` passed; all source mappings of the tutorial facts check passed, and the only failure is that the user has not created the `v0.53` tag yet; the assistant performs no tag operations.
- The v0.52 reliability fixture matrix additionally run in the same round is kept in `/private/tmp/mini-agent-v053-reliability-offline/`: 50/50 slots have terminal states, 42 fault injections triggered and 42 sets of invariants passed; 8 loopback HTTP MCP slots raised `RuntimeError` in the probe, did not trigger the fault, and their invariants are incomplete. The matrix as a whole is incomplete and does not cover or replace the existing v0.52 baseline.

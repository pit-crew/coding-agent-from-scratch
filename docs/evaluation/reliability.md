# v0.52 Fault Injection and Recovery Evaluation

`reliability-boundaries@1.6` injects controlled faults into fixed tasks and records separately the runtime boundaries and whether the Agent completes the task after recovery. Boundary tests answer "was the dangerous action stopped"; the independent grader answers "is the work the Agent finally left correct". Offline fixtures test only boundary drivers and runtime components and do not represent the model completing the task.

The new [21-slot live batch](baselines/v0.52/live-20260930-01/report.json) with the current binding on 2026-09-30 is complete: 17 fault triggers, invariants 15 passed, 2 failed, 4 incomplete, and strict recovery 6/14; no infrastructure errors. Process wait timeout and recovery after crash each triggered only 1/3 times, so the v0.52 live baseline still does not reach the threshold of three gradable triggers per scenario. For per-scenario results, budget diagnostics, and raw evidence, see the [baseline notes](baselines/v0.52/README.md).

The current executable candidate is suite 1.6: the verification repair scenario adds approved `list_dir` and `grep`, still limited to the trial workspace. When the production runtime refuses an illegal recovery ID, it no longer creates an invalid causal reference; finishing uses a dedicated application-generated prompt, keeping project instructions and user corrections complete. Working requests still keep the full tool rules, and verification and normal completion requirements are unchanged. This candidate has no live score yet; for details see the [fix record](baselines/v0.52/live-failure-repair-20261008.md).

## Frozen scenarios

The scenario order, tasks, visible tools, per-item permissions, budgets, fault drivers, recovery steps, feedback policies, and grader IDs are all frozen in `tests/fixtures/evaluation/reliability/suite.json` and the scenario material. The suite and material have SHA-256 digests; loading refuses unknown fields, digest drift, out-of-bounds paths, symlinks, and arbitrary Python grader code.

| Scenario | Injection and acceptance focus | Offline parameter variants | Live |
|---|---|---:|---|
| `tool-handler-exception` | An exception is raised before the first file handler call; the error result is fed back, and later legal calls can continue. | 1 | Yes |
| `permission-denied` | Writing `src/locked.py` is explicitly refused; the handler does not run, the file is unchanged, and the parent task ends safely. This scenario grades only the boundary. | 1 | Yes |
| `verification-repair` | The initial public tests really fail; after the fix there must be verification evidence of the current generation, and the hidden grader passes. | 1 | Yes |
| `process-wait-timeout` | The fixture process exceeds a short wait time; after the timeout it still shows running, and the Agent hands off, syncs, and cleans up. | 1 | Yes |
| `crash-before-admission` | A pending tool turn is saved but not yet admitted; recovery adds a not-executed result without calling the handler. | 1 | No |
| `crash-after-admission` | `handler_admitted` is committed but the handler did not run; the new session records an uncertain fact without replay. | 1 | No |
| `crash-after-handler` | The handler produced a side effect but the result was not committed; a new process recovers, the side effect happens only once, and issues are handled one by one. | 1 | Yes |
| `durable-commit-failure` | Admission, per-call result, and whole-turn commits fail respectively; no handler, later call, LLM, or background worker runs. | 3 commit boundaries | No |
| `recovery-user-decisions` | First tries `continue` on an uninvestigated issue, then investigates legally; another variant chooses `block`. | 2 feedback policies | No |
| `mcp-disconnect` | The first `tools/call` disconnects; the connection is invalidated with no retry, and public local material can be used. | stdio, explicitly allowed loopback HTTP | Yes, stdio only |
| `mcp-remote-error` | The Server returns a JSON-RPC error with an integer code; checks category, redaction, and no misclassification. | stdio, explicitly allowed loopback HTTP | No |
| `mcp-is-error` | The Server returns a valid result with `isError=true`; not confused with a JSON-RPC error. | stdio, explicitly allowed loopback HTTP | No |
| `mcp-call-timeout` | The Server does not respond to `tools/call`; checks the bounded timeout, connection invalidation, and shutdown result. | stdio, explicitly allowed loopback HTTP | No |
| `subagent-timeout` | The child model call gets an explicit timeout injection before provider I/O; the parent side claims and settles once, then investigates and verifies on its own. | 1 | Yes |
| `subagent-cancel` | The child worker is asked to cancel while waiting at a controlled barrier; after finishing within bounds, the final result can still be claimed. | 1 | No |
| `subagent-unclaimed` | The child task has ended but the result is not claimed; completion and safe points are blocked, and repeated claims return a stable result settled only once. | 1 | No |
| `subagent-interrupted` | The parent worker is stopped after the start confirmation and whole-turn boundary are committed; recovery records `interrupted` and does not restore the old worker. | 1 | No |
| `followup-incompatible` | A frozen Skill is replaced after a successful result is claimed; continuation is refused before the new child LLM request, and other sessions are not affected. | 1 | No |

The full offline matrix has 50 slots in frozen order, and each parameter variant runs twice. The live subset is the seven "Yes" scenarios in the table above, three times each, 21 slots in total; the live parameter of `mcp-disconnect` is fixed to stdio. Failed, untriggered, infrastructure-error, or interrupted slots are not made up or replaced automatically.

## Grading and denominators

Each `trial.json` uses the separate format `mini_agent.reliability`, schema 1, and does not reuse the TrialResult of coding tasks. It records separately:

- `fault_status`: `triggered`, `not_triggered`, or `injection_error`. Only a recorded actual hit point counts as triggered.
- `invariant_status`: `passed`, `failed`, or `incomplete`, listing the evidence state of each invariant.
- `recovery_status`: `succeeded`, `failed`, `not_applicable`, `not_triggered`, or `incomplete`.
- `grader_passed`: the independent grader checks the workspace after the Agent stops; offline component probes do not run the Agent, so this field is `null`.
- Agent stop reason, State terminal state, cleanup result, source consistency, phase usage, and evidence references.

`recovery_success_rate` is computed only for live recovery trials. The denominator requires the fault to have actually triggered, sources to be consistent, boundary evidence and the recovery flow to be decidable, the grader to have run, and no evaluation infrastructure errors. Model timeouts, permission refusals, budget exhaustion, and recovery failures in the six recovery scenarios stay in the denominator. `permission-denied` specifically accepts safe termination, with `grader_passed=null` and `recovery_status=not_applicable`, and does not enter the task or recovery grading denominators. The numerator also requires invariants to pass, recovery steps to be complete, the Agent to close normally with `done`, the grader to pass, and cleanup to be complete. Fixtures report only boundary results; task success and the recovery success rate stay `null`, and Runtime unit tests are not counted as model scores.

If a fixture only verified the fault seam without driving the Agent to complete later planning, authorization, a replacement task, or independent verification, the matching `recovery_status` stays `incomplete`. This means that offline slot does not claim full task recovery, which is not the same as an invariant failure; scenarios in the live subset accept full recovery and task results separately in live trials.

Untriggered faults, injection errors, incomplete evidence, inconsistent sources, infrastructure errors, and unrun slots are listed separately. The parent model call of `subagent-timeout` is a real binding; the child model call is replaced by the timeout fault driver, marked in the trial with `source="injected"` and `counted_as_real=false`, and not counted as a real child model request. Unobserved tokens are not filled with zero, and cost is `null` when the price snapshot is missing.

## Commands

First validate the full tasks and success criteria. This command does not read real provider credentials or call the model; the output includes all scenarios, exact tools and permissions, budgets, feedback policies, grader IDs, and material digests:

```bash
PYTHONPATH=src python -m mini_agent.evaluation validate-reliability tests/fixtures/evaluation/reliability/suite.json
```

The offline self-test runs 50 slots, including stdio and explicit loopback HTTP MCP fixtures, and sends no real API requests:

```bash
PYTHONPATH=src python -m mini_agent.evaluation self-test-reliability --output /private/tmp/mini-agent-reliability-offline
```

Before live, review the full tasks, permissions, feedback, and budgets in the validation output, then pass `--live` explicitly. The command runs the seven scenarios three times each; it runs once, with no automatic retries:

```bash
PYTHONPATH=src python -m mini_agent.evaluation run-reliability tests/fixtures/evaluation/reliability/suite.json --live --repeats 3 --output docs/evaluation/baselines/v0.52/live-<run-id>
PYTHONPATH=src python -m mini_agent.evaluation report-reliability docs/evaluation/baselines/v0.52/live-<run-id>
```

Before the first trial, the runner freezes and checks all seven local model bindings; the real provider/profile is assembled only from local configuration and is not written into fixtures or results. When configuration is missing, it creates ungraded live slots with an explicit infrastructure error and sends no model requests. The output directory must not exist; each batch uses its own directory.

## Raw evidence and reports

The run directory contains copies of the frozen suite and scenarios, a `suite-run.json` created in advance in fixed order, the `trial.json` of each started trial, fault/feedback/recovery events, State/Trace summaries, bounded logs, diffs, and the needed MCP/persistence records. Crash recovery keeps an association summary of the source session and the derived session; the source file must stay byte-for-byte unchanged. Worker requests persist only credential-free source references; provider endpoints, model IDs, API keys, and auth headers cannot be written into requests, logs, State, Trace, or reports. The live runner redacts generated text artifacts again before publishing.

`report-reliability` checks the frozen suite, slot order, trial identity, and SHA-256 evidence references read-only, then rebuilds per-scenario and fixture/live summaries from the raw trials. The ordinary `report` skips this separate result format and suggests using the dedicated command; the read path and metrics of coding task schema 1/2 are unchanged. When a report is corrupted or a source chain is broken, unreadable/incomplete items are kept, and conclusions are not guessed.

## First live results (suite 1.5, before the targeted budget fix)

Batch [`live-20260929-07/`](baselines/v0.52/live-20260929-07/) ran 21 slots in fixed order: 19 produced gradable trials, and 2 ended with `provider_protocol_error`. The two provider errors have no status code or details, and the redacted diagnostics show only the response call validation location; the root cause is unknown and cannot be judged as HTTP 400 from this. All sources and digests are consistent, with no broken evidence chains, cleanup failures, or manual review items. No retries, make-up runs, or replacements.

Of the 17 triggered fault trials that entered report grading, invariants passed 17/17; the raw material of the two infrastructure-error trials also records fault triggers and invariant passes, but they do not enter the grading cohort. Permission denial 3/3 are boundary-only trials and do not count toward task recovery. Strict recovery success was 5/14 (35.7%). The layered task results are: 16 task trials, 10 with correct file results, 5 passing current-generation verification, and 5 with normal model completion, and these 5 meet all conditions at the same time.

| Scenario | Fault triggered | Invariants | Grader | Recovery success |
|---|---:|---:|---:|---:|
| `tool-handler-exception` | 2/3 graded; 1 more infrastructure-error trial also triggered | 2/2 passed; infrastructure trial passed | 2/2 graded | 0/2 |
| `permission-denied` | 3/3 | 3/3 passed | Boundary only | Not applicable |
| `verification-repair` | 3/3 | 3/3 passed | 3/3 | 3/3 |
| `process-wait-timeout` | 2/3 (1 not triggered) | 2 passed, 1 incomplete | 0/3 | 0/2 |
| `crash-after-handler` | 1/3 graded; 1 not triggered; 1 more infrastructure-error trial also triggered | 1 passed, 1 incomplete; infrastructure trial passed | 1/2 graded trials | 0/1 |
| `mcp-disconnect` | 3/3 | 3/3 passed | 2/3 | 2/3 |
| `subagent-timeout` | 3/3 | 3/3 passed | 2/3 | 0/3 |

Budget diagnostics have 130 request decisions: 117 provider responses, 11 refused because the protected context could not fit into the remaining task budget, and 2 provider protocol errors. The actual input of 114/117 responses was higher than the raw estimate; no input exceeded the calibrated reservation, no output exceeded the allocated limit, and observed budget overruns were 0. Conservative refusals still leave the Agent unable to keep investigating or finish. Three scenarios did not reach 3 triggered and gradable samples per scenario, so the suite 1.5 live baseline is **not complete**; for detailed trials, the frozen review manifest, and per-request raw evidence, see the [baseline record](baselines/v0.52/README.md).

## Live batches after the targeted fix (suite 1.5)

The re-validated suite digest is still `833eefa4cb6e108439fb407c0981383fcd8b04724887e42c40ba9bcd65baa3a7`, and the Runtime fingerprint changed to `a32092e178ce86eb106f46a082801dca8b44c9b80d03d69d06661d2aee592a72`. All 21 slots of the first batch [`live-20260929-08/`](baselines/v0.52/live-20260929-08/) were `provider_http_503`; no gradable trials, and the recovery denominator is 0.

After the provider recovered, the second separate batch [`live-20260929-09/`](baselines/v0.52/live-20260929-09/) recorded 20 `provider_connection_error`s and 1 trial that did not trigger the fault. The raw exception types of the connection errors were 19 `ProviderConnectionError` and 1 `ProviderTimeoutError`; the only trial that got model responses stopped with `token_limit` before the fault triggered. Three `verification-repair` trials hit the injection point, but their model requests then failed, so they were excluded as infrastructure errors. All 21 trials completed cleanup; the recovery denominator is still 0, and the post-fix recovery rate cannot be judged from this.

Neither batch retried or replaced slots; the rebuilt reports are byte-identical to the archived reports. For all evidence and slot details, see the [baseline notes](baselines/v0.52/README.md).

## Targeted budget fix after suite 1.5

The current working request can now use the verification and plan progress quota, and the later tool-free final reply is reserved separately. Budget refusals add the protected context floor, pre-trim size, input quota, finishing reservation, and blockers. Tool argument validation errors of complete Chat responses add body-free diagnostics and keep reported usage; illegal arguments of complete non-streaming responses and output with an explicit length stop are task failures, and streaming assembly errors of unknown source are still kept separate. Historical trials are not reclassified.

For the specific changes, offline acceptance, and evidence limits, see the [targeted fix record](baselines/v0.52/stage-budget-repair.md). Both post-fix live batches were blocked by provider infrastructure errors and produced no recovery denominator; the earlier suite 1.5 5/14 is a pre-fix historical score, and the baseline is still not complete.

## Offline estimate correction after #09 (2026-09-30)

The only model response of #09 showed that a single input exceeded the old reservation, while the task's total quota was still sufficient. The candidate Runtime now builds a proxy estimate with an explicit margin from the UTF-8 size of the full OpenAI Chat request JSON, and when capacity is insufficient it trims historical tool rounds, keeping user corrections and protected facts; calibration samples of historical reservations and the new estimator are isolated. This proxy is not the provider token count, and the tool blocking logic after an actual over-reservation stays in effect. See the [offline fix notes](baselines/v0.52/estimator-offline-repair.md) for details. This round sent no probes and started no new live; the historical denominators and scores of suite 1.5 are unchanged.

## Historical suite 1.2

The suite 1.2 digest is `127fc54a543693630e23b602e2d3db460030b54746aa66fc67c0c9d70f7600a4`. After review of the third 1.1 live batch, crash tasks were changed to describe the phases before injection and after recovery accurately; subagent timeout fixes the `child_budget`, with a single max_tokens=32000, and the other fields are fully published by the task and pre-check. The timeout injection is recorded only when the child request is actually reached; a wrong contract is still refused by normal validation, and a fault trigger cannot be inferred from the start confirmation. This fixture allows only one injected investigation and sends no real child provider requests.

Complex scenarios add parent-side directory and search tools. When the target fault does not trigger, the related invariants are `incomplete`, and the Agent's earlier failure is still kept by `pre_injection_stop_reason`, State, and the grading result. Permissions, budgets, and independent verification rules keep the formal Runtime contract.

OpenAI Chat ordinary and streaming responses keep a bounded `reasoning_content` field and send it back as is in later requests; it is not output as terminal body text. Suite 1.2 live verified that HTTP 400 no longer appeared; the new batch is graded separately, historical artifacts are kept, and the new contract does not inherit old scores.

The historical suite 1.2 offline matrix completed 50/50 slots, with all faults and invariants passing; full pytest was 749 passed. The separate live batch completed 21 slots with no infrastructure errors and recovery success 5/16; but process wait timeout triggered only 1/3 times, so the live baseline is still not complete. For per-scenario data and raw evidence, see the [baseline notes](baselines/v0.52/README.md).

## Historical evaluator corrections (2026-09-29, suite 1.1)

The suite frozen at that time was `reliability-boundaries@1.1`, digest `53180d91b153c480aa580c433491b361120de3d1f120a5032632b89e8bcb7f05`. The historical results of 1.0 are kept and cannot be used to judge the task success rate of the corrected version. The corrections include:

- The initial and known_good of the six recovery scenarios all provide non-empty public unittests; the pre-check and live use the same public tests and independent behavior grading, which must refuse initial and accept known_good. The live runner completes the pre-check before resolving credentials.
- The independent grader calls functions in a bounded child process to check numeric behavior and accepts equivalent correct implementations; it does not require the function to have only one multiplication return.
- Permission denial is accepted by the formal Runtime's failed termination contract; refused attempts are matched by normalized argument digests, no longer accessing the nonexistent `ExecutionAttempt.arguments`.
- The process fixture keeps running until explicit termination and produces no output in the wait phase; it binds the State's ProcessManager, so the fault does not disappear when the model response time exceeds 0.8 seconds.
- The budget pre-check includes the context and tool schema estimate of the next request; the worker keeps the run phase, code location, redacted provider status/details, and tool schema digest, so that exceptions in the grading phase are not reported as not started.

Fixed-response regressions of the full worker and component probes are accepted separately; neither sends real provider requests. The server-side cause of the HTTP 400 at that time was not confirmed yet, and only diagnostics were added. Later 1.1 batches confirmed the UUID schema and reasoning_content compatibility problems; for the correction status, see the current suite above and the baseline notes.

The corrected offline matrix completed 50/50 slots, with all faults triggered and all invariants passing, and no infrastructure errors or broken evidence chains. The run ID is `0326a821-b347-460a-8ec6-4ffd1c491c89`, and raw results are in the local `/private/tmp/mini-agent-reliability-v052-suite11-fix-escalated/`. A separate attempt under sandbox limits had 8 loopback injection errors, kept in `/private/tmp/mini-agent-reliability-v052-suite11-fix/`; slots were not replaced one by one. These are all offline boundary evidence and are not counted as model scores.

## Historical status (suite 1.0)

As of 2026-09-28, the offline matrix of the redaction fix candidate with suite digest `8ea1fab57ec079a86b22fab140614dada88cc1e22e8e37f527e5c36b9d08904f` completed 50/50 slots in [`offline-20260928-security-redaction/`](baselines/v0.52/offline-20260928-security-redaction/): all faults triggered, invariants 50/50 passed, and no infrastructure errors, broken evidence chains, or unrun slots. A restricted sandbox attempt had 8 incomplete slots because it could not bind the loopback HTTP fixture; it is saved separately in [`offline-20260928-sandbox-loopback-limited/`](baselines/v0.52/offline-20260928-sandbox-loopback-limited/) and not counted as a passing result.

The first batch [`live-20260928-01/`](baselines/v0.52/live-20260928-01/) and the intermediate contract batch [`live-20260928-02/`](baselines/v0.52/live-20260928-02/) are still kept. The previous batch of the same historical suite, [`live-20260928-03/`](baselines/v0.52/live-20260928-03/), recorded 8 trials and 13 infrastructure errors; 5 fault triggers, 3 invariants passed, 0 graders passed, and recovery success rate 0/5. The batch after the redaction fix, [`live-20260928-04/`](baselines/v0.52/live-20260928-04/), keeps 21 terminal slots: 17 trials and 4 infrastructure errors; 9 fault triggers, 7 invariants passed, 1 grader passed, and recovery success rate 0/9. `tool-handler-exception` and `mcp-disconnect` each triggered 3/3 with invariants passing; `verification-repair` triggered 3/3, with 1 invariant and grader passing and 2 failing; `permission-denied` did not trigger twice with invariants failing, and once hit `AttributeError`; `process-wait-timeout` and `crash-after-handler` each did not trigger 3 times; the three `subagent-timeout` slots were not graded because of provider HTTP 400. All sources are consistent and evidence is readable, but four scenarios did not each reach 3 gradable trigger samples, so the live baseline is still not complete. Failed slots were not retried, made up, or replaced automatically.

`live-20260928-03/` reproduced the problem that live request artifacts once persisted local provider redacted values. The same fields also exist in the request files of the first three live batches; the request copies in these historical directories have all had the sensitive fields removed, and the original SHA-256 and the redaction reproduction notes are saved in each `artifact-security-findings.json`. After the fix, none of the 21 requests of `live-20260928-04/` have a `redactions` field, and scanning all generated artifacts found no provider sensitive values. The Runner does not persist redacted values and cleans text artifacts again before publishing. The full offline matrix after the fix passed; the live baseline is still not complete because of insufficient fault triggers and independent task acceptance. The suite 1.1 coding baseline is still separately not complete, and the disputed v0.51 scores are still kept.

## Historical suite 1.3: Evaluation isolation and diagnostics

The digest at that time is `38e9a5ffd8aafdf897928bd0c3f51c84797f0a5f1dee4c18f5a9e2521dae4893`. Relative process cwds are resolved against the trial workspace, and illegal directories are refused before handler admission; before and after the crash, the evaluation protected prompt is shared, to avoid importing the upper-level project AGENTS.md during recovery. Formal instruction discovery, safety, and completion rules are unchanged.

The `state_summary.tool_diagnostics` of raw trials provides bounded exception types, code locations, argument hashes, and errno; `request_diagnostics` under `phases` records per-request numeric diagnostics. `message_groups` splits message estimates into system, state, notice, summary, and history, with tool schemas listed separately; `reasoning_tokens_subset_estimated` is a subset of the message total and cannot be added again. `usage_source` distinguishes provider, estimated, and unobserved; the ratio of actual input to the reservation estimate helps judge estimate error. The recovery phase counts `prior_phase_tokens`, refused requests record the reason, and observed usage stays null. Diagnostics contain no message, reasoning, or tool argument bodies.

The total budget was not raised; these diagnostics are used to distinguish context overhead, model investigation usage, and estimate error. The 21-slot historical score of suite 1.3 is recovery 8/17, with process timeout triggered 2/3, and the sample baseline is not complete. The first suite 1.4 live batch completed 21/21, with all seven scenarios triggered 3/3 and gradable, reaching the sample coverage threshold; recovery success 1/18, with no infrastructure errors. None of the 128 responded requests exceeded the calibrated reservation, and 16 requests were refused before sending for insufficient budget; no live provider response exceeded its quota, so the branch that blocks tools/completion after a response has not yet been triggered by a real response. Conservative refusals may be related to repeated context problems, and execution order and context efficiency still need fixing. Scores of different contracts are not merged; see the [baseline notes](baselines/v0.52/README.md) for details.

## Historical suite 1.4: Request budget reservation

The suite digest is `ae49963f8385f27caaa2521a8ac167d0aa2c193f5368fb636eabb95763791365`, and the frozen material and pre-check publish `request_budget_policy`. The input estimate is reserved with an initial factor of 2 plus 256 tokens; it is raised by the highest ratio of pure provider input/original estimate in this trial plus a 10% margin, and recovery inherits the calibration from before the crash without resetting the cumulative budget. The output limit is computed from the balance of the same reservation, and a request is sent only if it can fit at least 256 output tokens (except for a smaller configured limit).

`budget_refusal_reason` distinguishes `budget_already_exceeded`, `budget_exhausted`, and `insufficient_request_budget`. An actual over-limit response cannot run tool handlers or complete the task, and all tool calls still get budget errors fed back one by one; actual counts are kept as is. Without provider usage, the estimate source is kept and not used for calibration. The estimate is not an exact tokenizer, and unknown error can still make a sent request exceed its quota, so no absolute budget guarantee can be claimed. For the 21-slot live results of suite 1.4, request refusal diagnostics, and uncovered branches, see the [baseline record](baselines/v0.52/README.md).

## Historical candidate 1.5: Cumulative budget and completion evidence

The suite digest is `833eefa4cb6e108439fb407c0981383fcd8b04724887e42c40ba9bcd65baa3a7`. Live explicitly enables the formal `TaskBudgetController`, and main requests, same-binding summaries, and recovery sessions share a 64,000 parent token limit. The evaluation only records the controller's admission proposals and cannot grant quota separately. Subagents keep the separate and aggregate budgets and are not counted twice in the parent model ledger.

Each request is calibrated independently by binding, tool schema, and work/summary/final category. Before two provider observations, `2 × raw + 256` is used; after that, the largest positive error of the last eight, plus 10% and 256. The outputs of main execution, summaries, and finishing are at most 1024/512/512 tokens; the minimum admission output is 256, except for a smaller model limit. Unknown usage is charged the whole reservation and does not take part in calibration; real overruns are recorded as is and stop handlers or completion.

Before each request, a unique reservation is committed durably, and after the return, the settlement is committed; a commit failure stops immediately. An unknown pending request during recovery is charged only once and cannot reset the limit. The new request view keeps user messages, protected instructions, the current State, and the complete tool protocol of the last two rounds; selected reasoning fields are not rewritten. A summary requests the model only when its estimated total cost is lower and quota is available; otherwise a bounded view is used, and when protected content still does not fit, it blocks explicitly.

Only when the current generation is verified or the active plan is fully complete, and there are no other completion blockers, is a finishing request without tool schemas used. The final reply must still really have no tool calls and pass the original completion checks; if finishing returns tool calls, refusal results are fed back one by one and the task is blocked. The plan is not completed automatically, verification is not run, and success is not declared.

The `state_summary.completion_evidence` of new trials keeps `artifact_correct`, `current_generation_verified`, `model_completed`, and blockers. The new report's `completion_layers` counts them separately, and the strict numerator of `recovery_success_rate` is unchanged; historical reports do not infer new evidence after the fact. The suite 1.5 live result is 5/14 strict recovery success, but three scenarios did not reach the sample threshold, so the baseline is not complete; for per-scenario and request diagnostics, see the section above and the [baseline](baselines/v0.52/README.md). The historical cost replay does not infer recovery results.

## 2026-09-30 Separate provider probes

The current binding ran a separate group of at most three billing and protocol probes with no retries: the first request succeeded, the second tool request hit `ProviderProtocolError`, so the third request was not sent. The results are separate from 08/09 and recovery grading; the conservative cost upper bound is below the user-approved 1 USD. For the raw numeric records and evidence limits, see the [baseline notes](baselines/v0.52/README.md) and the [probe review](baselines/v0.52/provider-probe-20260930-01/review.json). A new 21-slot live still cannot be started.

Later separate diagnostics 02/03 located the error in streaming tool call field validation, and an 8,192 output quota alone could not remove the error. After the adapter ignores later empty tool names and `null` argument fragments, probe 04 completed a three-request tool feedback chain; the cumulative conservative cost upper bound of the four groups is 0.42294812 USD, with no live slots touched. For evidence and historical attribution limits, see the [baseline notes](baselines/v0.52/README.md). The small-request protocol passed the targeted check; the #09 large-input reservation and Agent recovery still need separate acceptance, and the v0.52 live baseline is not complete.

Another synthetic large-input request reported 5,124 input tokens on the current binding, below the 7,084 proxy estimate and the 14,424 cold-start reservation; the cumulative conservative cost upper bound of all probes is 0.42367052 USD. Its byte shape is close to the after-the-fact rebuild of #09, but the original request was not saved and the binding differs, so this result cannot be written as a reproduction of #09 or a general budget guarantee. See the [raw numbers](baselines/v0.52/provider-large-input-20260930-01/probe.json) and the [review](baselines/v0.52/provider-large-input-20260930-01/review.json).

The corrected probe 05 then completed a three-step tool protocol under the suite's 1,024 output limit; the cumulative conservative cost upper bound of the six separate probe groups is 0.42375368 USD. The offline fault matrix passed 50/50 boundary invariants with no infrastructure errors; this is not a live recovery score. For details, see the [combined acceptance](baselines/v0.52/provider-validation-20260930.json); the v0.52 live baseline is still not complete.

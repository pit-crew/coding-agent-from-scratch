# Evaluation Harness

The Evaluation Harness creates a clean workspace for a fixed task, runs the Agent once, and then checks the changes with an independent grader. Ordinary tests check whether program boundaries are correct; the Harness checks whether the Agent can complete a concrete task on the same initial files. The offline self-test uses fixed model responses, checks only this chain, and does not count toward the real model success rate.

## v0.53 Regression Comparison and Memory Retrieval Ablation

This version uses a separate comparison contract to fix the four `coding-benchmark@1.1` tasks and three conditions: fixed v0.52 with retrieval off, frozen v0.53 with retrieval off, and the same v0.53 with retrieval on. Each task is repeated three times per group, 36 slots in total. For the contract, metrics, seed material, commands, and review steps, see the [comparison evaluation notes](comparison.md); this batch's live has not run yet.

## Run commands

Commands use Bash/zsh by default. First validate the single-file fix task shipped with the repository:

```bash
PYTHONPATH=src python -m mini_agent.evaluation validate tests/fixtures/evaluation/smoke/case.json
```

`self-test` first checks whether the grader refuses the original fixture and accepts a known correct fix, then runs fixed responses twice from the same initial files. Each result lands in a different trial directory and is recorded as `fixture`:

```bash
PYTHONPATH=src python -m mini_agent.evaluation self-test --output ./evaluation-results
PYTHONPATH=src python -m mini_agent.evaluation report ./evaluation-results
```

Real model calls must pass `--live` explicitly. The command shows the task ID, Agent rounds, Agent/grading time limits, the task, and approved tools; the smoke task of this version defaults to at most 6 rounds, 120 seconds for the Agent, and 30 seconds for the grader:

```bash
PYTHONPATH=src python -m mini_agent.evaluation run tests/fixtures/evaluation/smoke/case.json --live --output ./evaluation-live
PYTHONPATH=src python -m mini_agent.evaluation report ./evaluation-live
```

The real model binding is resolved from the local `config_local.py`. Results record only the profile, provider, protocol, and an irreversible fingerprint digest; without a price snapshot, both `cost_usd` and `price_snapshot` are `null`.

## v0.52 Fault Injection and Recovery

[`reliability-boundaries@1.6`](reliability.md) freezes 18 kinds of tool, permission, verification, process, persistence recovery, MCP, and subagent scenarios. `validate-reliability` outputs the full tasks, tools, exact permissions, budgets, fault parameters, simulated feedback, and grader; the offline matrix runs each parameter variant twice, 50 slots in total. The live subset fixes seven scenarios three times each, 21 slots in total.

```bash
PYTHONPATH=src python -m mini_agent.evaluation validate-reliability tests/fixtures/evaluation/reliability/suite.json
PYTHONPATH=src python -m mini_agent.evaluation self-test-reliability --output /private/tmp/mini-agent-reliability-offline
PYTHONPATH=src python -m mini_agent.evaluation run-reliability tests/fixtures/evaluation/reliability/suite.json --live --repeats 3 --output docs/evaluation/baselines/v0.52/live-<run-id>
PYTHONPATH=src python -m mini_agent.evaluation report-reliability docs/evaluation/baselines/v0.52/live-<run-id>
```

Invariants and the Agent task grader are scored separately. Offline component probes do not run the Agent, so the task grader and recovery success rate are `null`; only live trials can enter the recovery success rate denominator. Report validation freezes the suite, slot order, scenario material digests, and evidence references. Neither the fourth suite 1.0 batch nor the historical suite 1.1 lives reached the full baseline requirement; for all historical slots and restricted sandbox attempts, see the [`v0.52 baseline directory`](baselines/v0.52/README.md). The provider values exposed in the request artifacts of the first three batches have been removed with redacted digests kept, and the runner has been fixed. The disputed historical scores of v0.51 suite 1.0 are kept; results of different suites are not merged.

The current executable suite is `reliability-boundaries@1.6`, with no live score for this version yet. Historical suite 1.5: the first batch `live-20260929-07` before the targeted budget fix had recovery success 5/14, kept as a historical result under the old Runtime fingerprint. After the targeted fix, the newly started `live-20260929-08` had HTTP 503 in all 21 slots; after the provider recovered, `live-20260929-09` had 20 connection-type infrastructure errors, and 1 more trial stopped on the token limit before the fault triggered. The recovery denominator of both post-fix batches is 0, so the recovery rate cannot be judged; the suite 1.5 live baseline is still not complete. For the results, see the [08 report](baselines/v0.52/live-20260929-08/report.json), the [09 report](baselines/v0.52/live-20260929-09/report.json), and the [baseline notes](baselines/v0.52/README.md).

## v0.51 Coding Task Set

`tests/fixtures/evaluation/benchmark/suite.json` fixes four tasks and their order: the last-page pagination boundary, a two-module change for order discounts and receipts, a cache TTL fix with a new regression test, and a configuration source priority investigation and fix. Each task has its own `initial/`, `grader.py`, and `known_good/`. The Agent receives only the case's task and `initial/`; the grader and the known-good version are not copied into the Agent workspace.

The suite manifest also saves the SHA-256 of the case, task text, initial file tree, grader, and correct version. The suite also has an ID/version fingerprint fixed in code. Any digest change refuses to run; after reviewing tasks again, raise the suite version and update the fixed fingerprint. `validate-suite` pre-checks all tasks and requires the grader to refuse the original version and accept the correct version; for the cache task, it also verifies that the submitted unittest fails with an assertion on the original buggy implementation.

First review the task text, success criteria, budgets, and approved tools in the `validate-suite` output. Only after approval run the explicit live suite commands:

```bash
PYTHONPATH=src python -m mini_agent.evaluation validate-suite tests/fixtures/evaluation/benchmark/suite.json
PYTHONPATH=src python -m mini_agent.evaluation run-suite tests/fixtures/evaluation/benchmark/suite.json --live --repeats 3 --output ./evaluation-baselines/v0.51
PYTHONPATH=src python -m mini_agent.evaluation report-suite ./evaluation-baselines/v0.51
```

The runner first validates all tasks, the offline baseline, and the model binding, then creates `suite-run.json` with 12 ordered slots. Each slot is tried only once; faults before start are recorded as infrastructure errors, an interruption leaves `not_run` slots, and completed trials keep references to their original directories. The schema 2 record of each trial records the suite ID/version/digest, run ID, repetition number, initial fixture digest, Git code revision, runtime code fingerprint, and model source; the runtime code fingerprint is also checked before and after the trial. Single-task schema 1 and TrialRequest schema 1 stay compatible. The report is rebuilt from the ledger and the referenced raw trials and does not combine `fixture` and `live`.

Each task reports separately the planned, run, and gradable counts, independent grader passes, Agent final successes, error categories, call/token observation counts, duration distribution, and trial paths. `scorable_trials` requires the independent grader to return a boolean result with no grader/runner infrastructure error; `final_successes` also requires the Agent to complete normally. `live_baseline_complete` is true only when the live run has finished and every planned slot has a gradable result; with fewer than 3 gradable samples per task it explicitly stays incomplete. Unobserved tokens and calls stay missing; without a price snapshot, cost is `null`. The report also lists infrastructure errors, the actual model source digest, trials with missing usage, and manual review items such as the Agent stopping normally but the grader failing, or the grader and final success conditions disagreeing. Fixtures are used only to verify the evaluation chain and cannot count toward model scores.

The 12 real trial runs of suite 1.0 are archived in [`baselines/v0.51/`](baselines/v0.51/README.md). Review found that the exact display format of the receipt task was not published, so the original scores are kept and marked as disputed samples; the current suite 1.1 adds the format requirement to the task, has not run a real baseline yet, and does not carry over the old scores.

Pressing Ctrl+C during a run first stops the current child process within bounds, saves started trials (an Agent interruption is `agent_interrupted`, a grader interruption is a grading infrastructure error), then marks the suite as `interrupted`; the remaining slots stay unrun. Raw trials with inconsistent code or model sources are still kept, but are removed from the grading denominator and final success count, listed separately as `source_mismatch_trials`, and cannot be marked as a complete baseline.

## Task format

`case.json` uses strict schema 1. Fixture and grader paths are both relative to the task directory; `..`, absolute paths, symlinks, special files, missing graders, and oversized fixtures are refused before the Agent starts.

```json
{
  "schema_version": 1,
  "case_id": "smoke-scale-repair",
  "version": "1.0",
  "task": "Change scale(value) in src/scale.py so that it returns the argument multiplied by 2.",
  "fixture_dir": "initial",
  "grader_script": "grader.py",
  "agent_timeout_seconds": 120,
  "grader_timeout_seconds": 30,
  "max_rounds": 6,
  "allowed_tools": ["read_file", "list_dir", "grep", "write_file", "edit_file", "calculate"],
  "authorized_tools": ["read_file", "edit_file"]
}
```

`allowed_tools` decides which tools the model can see; `authorized_tools` is the subset explicitly allowed for this unattended run. Other shown tools are refused by the non-interactive `PermissionGate`, which does not read stdin and does not turn `ask` into `allow` automatically. File tools check again during handler execution that the target is still inside the trial root. A fixture has at most 256 files, 1 MiB per file, and 4 MiB in total; a trial workspace has at most 256 files and 8 MiB in total.

This version allows only `read_file`, `list_dir`, `grep`, `write_file`, `edit_file`, and `calculate`. Shell, process, MCP, Memory, Skill, or subagent tools are not registered; the subagent call count in results is 0. The independent grader runs as another process only after the Agent ends or times out and stops, and its output must be a JSON object with a boolean field `passed`.

## Single results

Each `trial-<case-id>-<uuid>` directory is published by atomic directory replacement and contains:

- `trial.json`: schema 1 structured facts, usage, grading, failure category, an optional grader script SHA-256, and relative artifact paths. Early schema 1 results may lack this digest.
- `diff.patch`: bounded file differences; the text diff is at most 1 MiB.
- `agent.log`, `grader.log`: bounded logs. Results do not save the Agent's final self-report, raw model responses, real endpoints, model IDs, API keys, or auth headers.

`success` is true only when the Agent terminates with normal text, State is `done`, at least one model response was received, the grader passes, and cleanup completes. `agent_stop_reason`, `agent_state_status`, and `grader_passed` are recorded separately, so the Agent claiming completion, reading files back, or verifying on its own cannot replace the grader. The current small task does not open shell; when Runtime shell verification evidence is unavailable after an ordinary Direct Path change, the evaluation policy allows the Agent to stop normally, but does not forge Runtime verification evidence, and the independent grader is still the basis of success or failure.

Timeouts, Agent exceptions, and unfinished tasks are kept as failure samples. After the Agent stops, the grader still checks the workspace, so a timed-out trial can also have `grader_passed`. The Runner failing to start the worker, a corrupted result protocol, cleanup failure, and grader timeouts/exceptions are infrastructure errors. When the Worker is forcibly stopped, call and token counts not yet written to disk are `null`, not filled with 0 to pretend they were observed.

The recovery success rate and invalid repetitions do not apply in v0.50; their values are `null` with a note. The tool call count includes refused calls. Tokens save input/output separately and mark the `provider`, `estimated`, `mixed`, or `fixture` source. Without a price snapshot, cost does not estimate a bill.

## Summary rules

`report <dir>` rebuilds the JSON summary from the raw `trial.json` files each time and does not write back to trial files. Live and fixture are counted separately, and fixed-response results cannot count toward the real model success rate.

- `scored_trials` are trials with an independent grader boolean result and no grader infrastructure error; Agent timeouts or failures stay in the denominator as long as the grader completes normally.
- `independent_acceptance_pass_rate` is the grader pass count divided by `scored_trials`. The Agent's final task success count is listed separately and is not the numerator of this metric.
- Runner/grader infrastructure errors are listed separately and removed from the grading denominator; a grader failure or invalid output cannot count as an Agent failure or a pass.
- Token and call totals sum only trials with observed values and also give `observed_trials`. Counts not saved by the worker stay missing.
- Cost, recovery success rate, and invalid repetitions are currently all `null`.

## Isolation boundary and manual review

Each trial copies a new workspace from the read-only fixture and assigns its own `HOME`, temporary directory, and Memory path; this guarantees that reruns of the same task start from the same files. The Runner cleans up only temporary directories it created, and result directories do not overwrite old trials.

**A separate workspace is not an operating system security sandbox.** The Worker and grader use the same system account, the same Python interpreter, and the local configuration as the caller; the tool path gate limits the Agent's file tools, but the Python process is not isolated with containers or system permissions. Do not put untrusted graders or unreviewed tasks into live tests. The v0.50 grader is a fixed, offline, credential-free script in the repository.

For manual review, first open `trial.json` and check the run kind, Agent stop reason, State terminal state, count sources, and failure category; then look at `diff.patch`, and finally check each predefined assertion in `grader.log`. If the Agent's self-report and the grader result disagree, the kept independent grading facts take priority; when correcting rules in a new task version, raise the testcase `version` and do not rewrite existing trials.

The one successful live sample of v0.50 is `trial_id=fecf1d04-48f2-4c86-bf42-e0588dabc1fa`: 4 successful model responses, 3 tool calls, provider-reported 6,520 input / 243 output tokens, Agent time 3,004 ms, grader time 38 ms, and the independent grading passed. The first connection failure under restricted network is also kept as another live trial; the summary of that result directory is 2 trials, 1 success (1/2). This is a chain acceptance sample, not a coding ability benchmark.

Suite 1.4 publishes the request budget calibration rules, inherits cumulative usage from before the crash, and refuses to continue after an over-limit response. The sample coverage of the first live batch is complete, with recovery success 1/18; 16 requests were refused before sending by the conservative reservation; see the [baseline record](baselines/v0.52/README.md) for details.

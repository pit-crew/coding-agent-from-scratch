# Lesson 51: Why repeat coding tasks (v0.51)

Previous: [The single-case evaluation chain](50-evaluation-harness.md) · [Tutorial overview](README.md) · Next stage: reliability evaluation

> Code snapshot: `v0.51` · Adjacent diff: `v0.50..v0.51` · Shell: Bash/zsh
>
> Source links are pinned to `v0.51`. Before the tag exists, read the matching files in the current working tree.

## Lesson Goals

One successful trial run only shows that the Agent completed the task with that model response and that workspace. The next model reply may differ, and the Agent may fix only part of the problem. To learn whether it can complete a kind of work reliably, each attempt must start from the same files, run and be graded independently, and keep the full record of passes and failures.

This lesson adds four pure-standard-library Python coding cases, fixed case digests, a repeated-run ledger, and a per-case report. After reading, you should be able to tell apart "how many runs were planned", "how many actually ran", "how many could be graded", and "how many times the Agent finally succeeded".

## Prerequisites and Version Checkout

You need Python 3.10+, a terminal, and Git. Lesson 50 introduced single-case evaluation: the Runner creates a workspace for one Case, and an independent grader checks it after the Agent ends. After the maintainer creates the adjacent tags, you can view this version's changes:

```bash
git checkout v0.50
git diff --stat v0.50..v0.51
git diff v0.50..v0.51 -- src/mini_agent/evaluation tests/fixtures/evaluation/benchmark
git checkout v0.51
```

Source index for this lesson: [benchmark.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.51/src/mini_agent/evaluation/benchmark.py), [schema.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.51/src/mini_agent/evaluation/schema.py), [runner.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.51/src/mini_agent/evaluation/runner.py), [report.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.51/src/mini_agent/evaluation/report.py).

## Limits of the Previous Version

v0.50 can already run one small case and save a single result, but with only one record you cannot see whether task results change with the model's replies. Even if the Agent says it is done, the result may pass only some of the requirements. So this version first fixes a set of tasks and their grading, then plans several independent runs for each case.

## New and Changed Files

| Location | Change | Purpose |
|---|---|---|
| [benchmark/suite.json](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.51/tests/fixtures/evaluation/benchmark/suite.json) and four case directories | New | Freeze the case order, tasks, initial code, graders, and known-good version digests. |
| [evaluation/benchmark.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.51/src/mini_agent/evaluation/benchmark.py) | New | Validates digests, verifies case baselines, orchestrates suite runs, and rebuilds per-case reports. |
| [evaluation/schema.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.51/src/mini_agent/evaluation/schema.py) | Changed | Adds bounded Suite / SuiteRun contracts and TrialResult schema 2, while keeping schema 1. |
| [evaluation/runner.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.51/src/mini_agent/evaluation/runner.py), [report.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.51/src/mini_agent/evaluation/report.py), [__main__.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.51/src/mini_agent/evaluation/__main__.py) | Changed | Reuse the single-case runner, save each slot and raw trial, then rebuild reports from them. |
| [test_evaluation_v051.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.51/tests/test_evaluation_v051.py) | New | Verifies case grading, digest rejection, repeated runs, partial interruptions, and report references. |

## Version Change Map

Legend: `[old]` already in the previous version; `[+]` new in this version; `[~]` changed in this version; `[C]` main user; `[B]` boundary.

The v0.50 entry handles one Case. Each run has its own initial workspace; the grader checks files after the Agent stops:

```text
v0.50 baseline:
[old] validate / run --live / self-test
  → [old] Case and fixture check
  → [old] one fresh workspace → Agent worker → independent grader
  → [old] schema 1 TrialResult saved atomically
  → [C] report rebuilds the summary from trial.json
```

v0.51 adds a fixed-order case set and a run ledger on the outside. Single-case execution is still done by v0.50's `run_case()`; the new logic pre-checks all cases, prepares the repeated slots, and updates the ledger after each run ends:

```text
v0.51 change:
[+] validate-suite
  → [~] Suite / initial files / grader / known-good digest check
  → [B] the grader must reject the original version and accept the known-good version
  → [B] if any digest or baseline does not match, the Agent is not started
  → [+] create 12 planned slots in manifest order
  → [C] each slot calls [old] EvaluationRunner.run_case()
  → [~] save schema 2 TrialResult + [~] atomically update suite-run.json
  → [+] report-suite validates the raw evidence references and rebuilds per-case/total reports

failure branches: [B] live requires an explicit --live and all cases bound to the same model source; [+] an interruption keeps unrun slots;
                  [B] failed or infrastructure-error slots are not retried automatically.
```

## Freeze the Problems and Grading Criteria First

The case text tells the Agent what to solve, and the grader checks the observable result after the Agent stops. Each case also keeps a hand-made known-good version. Before running, `validate-suite` checks the digests and has the grader score both the original version and the known-good version; if the original version also passes, or the known-good version fails, the case cannot enter a live run.

The fixed case set contains four problems in this order:

1. A pagination function misses the last page; the fix must cover the empty collection, the full-page boundary, a partial last page, and an invalid page size.
2. Order discount rounding is wrong, and the receipt also does not list the discount and the amount due accurately; both the calculation and the display modules must be fixed.
3. A cache entry is still returned when it reaches its TTL exactly; besides the fix, a new `unittest` regression test must be added that passes on the current code and fails on the original buggy implementation.
4. Environment variables cannot override project configuration and defaults; the task only describes the expected priority of the different sources and does not tell the Agent which file is wrong.

The graders and `known_good/` in the case directories are never copied into the Agent workspace. `suite.json` stores their SHA-256 together with those of the Case, the task text, and the initial file tree. The Suite itself also has a fixed ID/version fingerprint; if a digest changes but the version is not updated, loading fails.

## How Repeated Slots Keep Evidence

A suite run has 12 fixed slots: in manifest order, the three runs of one case are listed first, then the next case. Before each slot starts it is written as `running`, and after it finishes it is written as `completed` with the trial's relative path. When the process exits midway, the finished records are kept and the unstarted slots stay in the ledger; the next run must use a new output directory and never quietly reruns old slots.

TrialResult schema 1 is still used for the original single-case results. Suite trials use schema 2, which also records the suite ID/version/digest, the suite run ID, the repetition number, the initial file digest, and the runtime code fingerprint. The SuiteRun ledger also stores the Git code revision, the runtime code fingerprint, and the model source summary; before each trial starts, the implementation source is checked, and after the Agent stops, the fingerprint is recorded again, so the report marks samples where it changed midway.

## Look at the Denominator First When Reading the Report

The planned count is the number of slots reserved in the ledger. The run count is the number of slots that produced and reference a raw trial. The gradable count also requires the grader to return a boolean result normally; runner or grader infrastructure errors are listed separately and not mixed into Agent success or failure. The independent acceptance pass count looks only at the grader, while the final success count also requires the Agent to finish normally, with status `done` and cleanup complete.

Tool calls, successful model responses, and input/output tokens sum only actually observed values, and list the number of observed samples alongside. Durations report the median and P95. Without a price snapshot, cost stays `null`. Every number can be traced back to a per-trial path to check `trial.json`, `diff.patch`, and `grader.log`. Fixture results are marked separately; they only verify the evaluator and are not counted in the real model baseline.

## Why This Design

Fixed initial files make repeated runs comparable, an independent grader avoids treating the Agent's self-report as evidence of success, and raw trial paths make summary numbers reviewable. The offline check of the original and known-good versions also catches grading rules that always pass or always fail.

The cost is that a digest change requires raising the suite version and reviewing again; the current four cases also reflect only these specific behaviors and cannot represent all Python coding tasks. Three runs per case is a small sample; the report describes the observations on this frozen case set and is not used to claim statistical significance or general ability. Workspace isolation is still not an operating system security sandbox.

## Key Flow

First run the offline pre-check. The expected output contains four cases and lists `initial: passed=false` and `known_good: passed=true` for each; the cache case's grader also verifies that the regression test can reveal the old bug. This command does not call the model:

```bash
PYTHONPATH=src python -m mini_agent.evaluation validate-suite tests/fixtures/evaluation/benchmark/suite.json
```

Only after reviewing the tasks and success criteria do you run the first real baseline. The command prints the 12 planned trials, each case's round and time limits, the approved tools, and the task text. After the run, the report should let you see, per case, the planned, run, gradable, and pass counts, and every trial path:

```bash
PYTHONPATH=src python -m mini_agent.evaluation run-suite tests/fixtures/evaluation/benchmark/suite.json --live --repeats 3 --output ./evaluation-baselines/v0.51
PYTHONPATH=src python -m mini_agent.evaluation report-suite ./evaluation-baselines/v0.51
```

This version's first live baseline runs after the task review is approved; offline pre-check results are never recorded as Agent results.

## Implementation Breakdown

The suite digests are not just one check over the JSON file. `load_suite()` limits each path in the manifest, segment by segment, to the suite root, recomputes the digests of the Case, task text, initial files, grader, and known-good version, and then checks the ID/version fingerprint fixed in the code. The code below expresses the key boundary that rejects digest changes:

```python
if item[key] != actual_value:
    raise ValueError(f"{key} digest of {case.case_id} does not match; raise the suite version")
```

This check happens before any live worker is created. The fixed fingerprint also requires that changing a digest goes together with raising the suite version and updating the reviewed fingerprint.

`run_suite()` first writes a run ledger that contains all slots, then lets the existing `run_case()` handle each case in order. The run ledger is updated through a temporary file in the same directory, a file sync, and a replacement; if a task is interrupted, the trial paths already saved are kept, and the remaining items do not disappear from the plan.

```python
slot["status"] = "completed"
slot["trial_path"] = trial_dir.relative_to(root).as_posix()
ledger["updated_at"] = _now()
_atomic_json(ledger_path, ledger)
```

`build_suite_report()` first verifies that the ledger, every slot, and the raw TrialResults agree on the suite/run/repetition/fixture digests, and only then computes the numbers. Every result keeps its relative path, so the report can lead back to the raw trial.

## Version Features, Next Lesson, and Code Index

v0.51 adds versioned task contracts, ordered orchestration, an atomic run ledger, and per-case evidence reports to single-case evaluation. It does not change the Agent Runtime's decisions, plans, or permissions, and adds no new model tools. For the four fixed cases and the current run status, see the [evaluation guide](../evaluation/README.md); after real results are produced, they are archived in the [first baseline directory](../evaluation/baselines/v0.51/README.md).

The next stage checks fault handling and recovery behavior on the same evaluation chain.

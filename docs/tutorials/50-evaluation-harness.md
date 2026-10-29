# Lesson 50: A reviewable task evaluation for the Agent (v0.50)

Previous: [Resumable child sessions](49-resumable-child-session.md) · [Tutorial overview](README.md) · Next: v0.51 (coding task set, planned)

> Code snapshot: `v0.50` · Adjacent diff: `v0.49..v0.50` · Shell: Bash/zsh

> Source links always use `v0.50` paths; before the tag exists, read the files the links point to in the current working tree.

## Lesson Goals

Unit tests can tell us whether tools and permission boundaries work as the code says, but they cannot answer whether the Agent can take a task, actually call the model, change files, and meet the user's requirements. Looking only at the Agent's last text is not enough either: it may say "fixed" while the file is still wrong.

This lesson adds an independent evaluation flow: first copy fixed initial files into a new directory, let the Agent run with restricted tools; after the Agent ends, a separate grading program checks the result. After reading, you should be able to tell from the raw trial record whether the Agent stopped normally and whether the grader passed, and why offline fixed responses cannot count as real model results.

## Prerequisites and Version Checkout

You only need Python 3.10+, a terminal, and Git. Read Lesson 49 first to learn how the previous stage reuses the same Runtime. The current implementation is in this v0.50 working tree; after the maintainer creates the tag, you can review the adjacent version with the commands below:

```bash
git checkout v0.49
git diff --stat v0.49..v0.50
git diff v0.49..v0.50 -- src/mini_agent/evaluation docs/evaluation
git checkout v0.50
```

Source index for this lesson: [runner.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.50/src/mini_agent/evaluation/runner.py), [worker.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.50/src/mini_agent/evaluation/worker.py), [schema.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.50/src/mini_agent/evaluation/schema.py).

## Problems in the Previous Version

v0.49 strengthened the collaboration between the parent Agent and subagent sessions, but the project still had no uniform way to measure how the parent Agent performs on a fixed coding task. Existing tests call functions directly or simulate boundaries; they do not give the Agent a fresh workspace, start the model, and check the files it leaves behind.

If the Agent's own last sentence were taken as evidence of success, the evaluation would mix "claimed done" with "actually met the requirements". This version splits model running and independent acceptance into two stages, one after the other, and saves each run as a separate result.

## New and Changed Files

| File | Change | What you can see here |
|---|---|---|
| [evaluation/schema.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.50/src/mini_agent/evaluation/schema.py) | New | The versioned contracts of cases, requests, and results, and their path/size limits. |
| [evaluation/worker.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.50/src/mini_agent/evaluation/worker.py) | New | How a restricted Registry, non-interactive authorization, and the canonical Runtime are assembled in a single-task process. |
| [evaluation/runner.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.50/src/mini_agent/evaluation/runner.py), [report.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.50/src/mini_agent/evaluation/report.py) | New | How a fresh workspace is built, timeouts set, the grader run, results saved atomically, and summaries rebuilt. |
| [tests/fixtures/evaluation/smoke](https://github.com/liiiiiiiiil/agent-from-scratch/tree/v0.50/tests/fixtures/evaluation/smoke) | New | A single-file case that fails in its original version and passes with a known correct change. |
| [docs/evaluation/README.md](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.50/docs/evaluation/README.md) | New | The case format, statistics denominators, result fields, isolation boundaries, and manual review steps. |

The parent `AgentRuntime.run()` and `ParentRuntimePolicy` of Lesson 49 still provide the main loop from model to tools; the worker added in Lesson 50 prepares dedicated tools and task conditions for them.

## Version Change Map

Legend: `[old]` already in the previous version; `[+]` new in this version; `[~]` changed in this version; `[C]` main consumer; `[B]` boundary of this version.

The run entry of v0.49 serves the interactive CLI. After it handles the first task, it keeps waiting for user input; the default `PermissionGate` reads terminal input when it meets `ask`. It suits people and the Agent working together, not running the same case again and again unattended.

```text
v0.49 baseline:
[old] CLI first task
  → [old] the parent Runtime assembles State / Context / Registry / PermissionGate
  → [old] AgentRuntime.run()
  → [old] the CLI keeps interacting; the final task state is closed by the CLI lifecycle
```

v0.50 adds a dedicated entry and a second process. A Case is a JSON case contract that describes the task, initial files, tool authorization, and budget; a Trial is the record of one run of this case.

```text
v0.50 change:
[+] validate / run --live / self-test / report
  → [+] Case + fixture check (a bad path, oversize, or missing grader does not start the Agent)
  → [+] new trial workspace + separate HOME
  → [+] Worker: State / Context / frozen model binding / restricted Registry / non-interactive Gate
  → [~] ParentRuntimePolicy + AgentRuntime.run()
  → the Agent process stops or is cleaned up on timeout
  → [+] independent grader process → TrialResult + bounded diff/log → atomic publish
  → [C] report rebuilds the summary from raw TrialResults

failure branches: [B] without real configuration or without --live, no live request is sent; [B] a grader timeout/exception is marked as an infrastructure error.
```

## Core Concepts and Data Structures

### 1. Freeze the case first, then start the model

If the grading rules changed on the fly with the Agent's output, two trial runs could not be compared fairly. So `case.json` fixes, before the run, the case ID, version, task text, initial fixture, independent grader, number of rounds, two kinds of timeouts, and the visible tools. Schema 1 is validated by standard-library code and needs no extra JSON Schema dependency.

`allowed_tools` decides what the model can see; `authorized_tools` states explicitly which tools are approved in this unattended run. For example, `edit_file` can appear in the model's tool catalog, but if it is not in the authorized list, calls get a rejection result. `ask` never triggers `input()` and is never approved automatically.

The case fragment below shows that the schema writes the default time and round limits into the testcase itself. The validator checks these budgets before creating the Agent subprocess:

```json
{
  "schema_version": 1,
  "agent_timeout_seconds": 120,
  "grader_timeout_seconds": 30,
  "max_rounds": 6,
  "allowed_tools": ["read_file", "edit_file"],
  "authorized_tools": ["read_file", "edit_file"]
}
```

This way two runs can use the same permissions and time limits, and unauthorized tools never wait for terminal input.

### 2. One workspace maps to one trial

Each run copies a new directory from the read-only fixture, then creates a separate `HOME`, temporary directory, and Memory location. The Worker receives only the case task and the workspace path; the grading script path is never exposed as model tool content. File tools check, before the handler runs, that the canonical path is still inside the trial root, and the input fixture and run output both have limits on file count and total size.

The Worker runs tools through the existing `ToolExecutor`, and `AgentRuntime.run()` maintains the full model tool protocol. No trial turns on `/save`. The worker's state is used only within that subprocess and is not written to a session file.

For file tools, every call first resolves the target inside the trial root:

```python
relative = absolute.relative_to(root)
```

If the path cannot be expressed relative to the root, the handler refuses it before reading or writing the file. The path scope check limits file tools; it does not form an operating system security boundary for the Python subprocess.

### 3. The Agent finishing and independent grading are two separate facts

`agent_stop_reason` records why the Runtime stopped, `agent_state_status` records the structured task terminal state, and `grader_passed` records the result of the independent assertions. The Agent's final text is never written to `trial.json` as a basis for passing. `success` is true only when the Agent ended normally with text, State is `done`, the model responded successfully at least once, the grader passed, and temporary resource cleanup completed.

The restricted smoke case does not open `run_shell`, so Runtime verification evidence for ordinary file changes cannot be produced by model commands. The evaluation policy still calls `ParentRuntimePolicy`; for a plain ordinary verification reminder on the Direct Path, it only allows the Agent to stop normally and does not write or forge `verification_evidence`. The independent grader still runs after the Agent stops and exclusively decides whether the evaluation succeeded.

The runner's success condition requires at once that the model ended normally, the grader passed, and cleanup completed:

```python
success = bool(
    failure_kind == "none"
    and grader_passed is True
    and cleanup_complete
    and result_payload is not None
    and int(result_payload.get("successful_model_responses", 0)) > 0
)
```

So the Agent outputting "done" is not enough by itself to make the trial succeed.

### 4. Offline responses do not pose as real model runs

`self-test` hands two fixed responses to the same worker to verify the tool path, the Agent Runtime, the independent grader, atomic saving, and the report chain. The results are marked `fixture`, and the summary shows them in a separate group from `live`. Only an explicit `run ... --live` reads the local model configuration and attempts real requests.

The report collects the two sources separately, so fixed responses never inflate the real success rate:

```python
groups = {
    kind: [row for row in rows if row.get("run_kind") == kind]
    for kind in ("live", "fixture")
}
```

`report` rebuilds the numbers from the raw JSON and never rewrites any trial.

## Why This Design

The CLI keeps interacting and may wait for authorization input, while the evaluation entry needs a clear one-off task boundary. A separate worker lets one trial end on a wall-clock timeout and clean up, on exit, the process group the runner created; an independent grader ensures the decision does not depend on what the model says.

v0.50 delivers only one small file-change case and focuses on verifying the evaluation chain. It has no shell coding, durable recovery, or subagent evaluation capability, and it does not form a representative coding benchmark. Independent workspaces make reruns start from the same initial files, but they are not an operating system security sandbox: the worker and grader still run under the caller's system account.

## Key Flow

First validate the case, then run the offline chain with fixed responses. The first command should show that the fixture has 1 file and list the allowed and authorized tools; the second should give two different trial IDs, and the independent grader of each trial passes:

```bash
PYTHONPATH=src python -m mini_agent.evaluation validate tests/fixtures/evaluation/smoke/case.json
PYTHONPATH=src python -m mini_agent.evaluation self-test --output ./evaluation-results
PYTHONPATH=src python -m mini_agent.evaluation report ./evaluation-results
```

Only then do an explicit real trial run. Before the run, the CLI prints the case and the time/round limits; only after the Agent ends or is stopped does the Runner start the grader. Look in `trial.json` for `run_kind=live`, at least one successful model response, the model source summary, the usage source, `grader_passed`, and the duration fields. Fixture results cannot replace this live record.

```bash
PYTHONPATH=src python -m mini_agent.evaluation run tests/fixtures/evaluation/smoke/case.json --live --output ./evaluation-live
PYTHONPATH=src python -m mini_agent.evaluation report ./evaluation-live
```

In this working tree, the live acceptance record `trial_id=fecf1d04-48f2-4c86-bf42-e0588dabc1fa` ended normally and passed the independent grader: 4 successful model responses, 3 tool calls, provider usage of 6,520 input and 243 output tokens, an Agent duration of 3,004 ms, and a grader duration of 38 ms. Another live trial whose first restricted network connection failed is also kept in the raw results, so the summary of that output directory is 1/2, rather than showing only the passing sample. They verify only this one smoke case and do not represent a coding ability benchmark.

## Implementation Breakdown

- [`case_from_dict()`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.50/src/mini_agent/evaluation/schema.py) checks the schema version, budgets, tool lists, relative paths, and fixture; when the grader is missing or the fixture is oversized, the run has not been created yet.
- [`run_request()`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.50/src/mini_agent/evaluation/worker.py) builds the parent State, Context, `ToolExecutor`, and the frozen model binding, and hands the final structured stop reason back to the Runner.
- [`EvaluationRunner.run_case()`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.50/src/mini_agent/evaluation/runner.py) runs the Agent and the grader in order; a timeout stops the Agent process group, and the result directory is published by an atomic replacement in the same directory.
- [`build_report()`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.50/src/mini_agent/evaluation/report.py) reads only raw schema 1 results; infrastructure errors are removed from the success rate denominator, while an Agent timeout still counts in the denominator as long as the grader gives a result normally.

No price snapshot is configured, so the cost is `null`. v0.50 does not collect the recovery success rate or the number of invalid repetitions; these two items are also `null`, so missing observations are never written as 0.

## Design Boundaries

Workspace isolation guarantees that every run starts again from the same fixture and lets the grader check the actual output after the Agent stops. The tool path gate does not constrain the Python process itself; untrusted cases and graders need operating-system-level isolation, which v0.50 does not provide. Every result should be checked by hand against the raw JSON, the file diff, and the grader log.

Fixed model responses only prove that the harness flow works, not that a real model will complete the task. The success rate applies only to the case version and the current conditions; v0.51 starts expanding the cases and repeated trials.

## Implementation Breakdown, continued

When the Agent times out, the Runner tries to end the process group within bounds; the independent grader can then still check the files written before the timeout. In this case `grader_passed` can be true, but `success` must be false, because the Agent did not finish normally. If the grader itself times out or its output is not the required JSON, the result is marked as a grader infrastructure error and does not enter the success rate denominator.

Raw trial results are saved in `trial.json`, and `report` only recomputes the summary. When it is confirmed that some diff or case grading needs adjusting, keep the raw trial and raise the case version to run again, instead of overwriting historical facts.

## Version Features, Next Lesson, and Code Index

v0.50 establishes fixed cases, a restricted live worker, independent grading, single-run results, and grouped reports; the repository has only one small case with no network dependency. The next lesson, v0.51, expands the coding task set and then discusses repeated runs and task representativeness.

- [Evaluation usage guide](../evaluation/README.md)
- [Source: schema.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.50/src/mini_agent/evaluation/schema.py)
- [Source: worker.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.50/src/mini_agent/evaluation/worker.py)
- [Source: runner.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.50/src/mini_agent/evaluation/runner.py)
- [Source: report.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.50/src/mini_agent/evaluation/report.py)

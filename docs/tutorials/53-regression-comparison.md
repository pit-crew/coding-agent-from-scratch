# Lesson 53: How to compare two Agent conditions fairly

Code snapshot: `v0.53` · Adjacent diff: `v0.52..v0.53` · Commands: Bash/zsh

[Previous lesson: Fault injection and recovery evaluation](52-reliability-evaluation.md) · [Tutorial index](README.md)

In this lesson we answer a question that looks simple but is easy to get wrong: is the new version really better than the old one? The Agent's answers vary from run to run. Looking at only one success may mistake chance for improvement; just swapping out the old version may also mistake a change in the cases or permissions for an effect of the version.

v0.52 can already freeze coding cases, isolate workspaces, and let an independent grader score them, but it runs the case set for only one version. v0.53 adds a comparison contract that puts three conditions into the same batch: the old version with memory retrieval off, the current version with retrieval off, and the current version with retrieval on. This way the first two groups answer whether the version regressed, and the last two groups answer what changes automatic Memory retrieval brings.

## Lesson Goals

After reading, you should be able to see which conditions a fair comparison must fix first, explain how the 36 trials are paired, and tell an offline Runtime self-test apart from real model results. The Memory retrieval ablation only means comparing the difference between enabling and disabling automatic summary retrieval.

## Prerequisites

Prepare Python 3.10+ and Git; first understand the fixed case set, isolated workspaces, and independent grader from the previous lesson. The current source links are pinned to `v0.53`; when the maintainer has not created the tag yet, read the source on the default branch first, and do not treat a tag that does not exist as an already frozen snapshot.

## Prepare the Code Snapshot First

A Git tag is a fixed name given to a code snapshot; the tutorials use it to make sure examples point at the same source. This lesson declares `v0.53`; new tags must be created manually by the maintainer. Before switching, look at the source diff this lesson uses:

```bash
git checkout --detach v0.53
git diff v0.52..v0.53
git diff --stat v0.52..v0.53
```

The first command switches the workspace to this lesson's version; the second shows its changes relative to v0.52. The commands in this lesson assume Bash/zsh in the repository root. If the maintainer has not created the `v0.53` tag yet, stay on the current branch to read the source; do not assume the name can already be checked out.

## New and Changed Files

Look at these files first to find where the comparison conditions are validated, where the target Runtime is assembled, and how the report is rebuilt:

| File | Purpose |
|---|---|
| [`comparison_schema.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.53/src/mini_agent/evaluation/comparison_schema.py) | Defines the strict fields of the comparison manifest, the batch ledger, and single results. |
| [`comparison.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.53/src/mini_agent/evaluation/comparison.py) | Freezes sources and order, coordinates per-case execution, and keeps slot status. |
| [`comparison_sources.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.53/src/mini_agent/evaluation/comparison_sources.py) | Creates temporary source copies from complete commits and checks interfaces before requests. |
| [`comparison_worker.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.53/src/mini_agent/evaluation/comparison_worker.py) | Assembles the target version's Runtime, tool permissions, and Memory retrieval. |
| [`comparison_report.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.53/src/mini_agent/evaluation/comparison_report.py) | Validates the raw evidence digests and rebuilds the paired report. |

## Key Flow: Data Flow in v0.52 and v0.53

The path of the previous version: fixed cases create workspaces, the Agent uses six file and calculation tools, the grader checks the result after it stops, and finally the trial runs of a single version are summarized:

```text
v0.52 baseline
[old] validate-suite
  → [old] one fixed case set and one set of permissions
  → [old] EvaluationRunner.run_case()
  → [old] AgentRuntime + six tools + PermissionGate
  → [old] independent grader
  → [C] report-suite summarizes trials
```

It can answer "how well did this version do", but it cannot guarantee that two runs differ in only one condition. v0.53 freezes the comparison conditions and order first, then starts the target Runtime from the matching commit:

```text
v0.53 comparison
[+] validate-comparison → check the three groups of conditions and two comparison edges
  → [+] plan-comparison freezes the case set, sources, environment, and 36 slots
  → [~] create an independent workspace / HOME / Memory for each slot
  → [+] temporary checkout + a uniform external worker
       ├─ [C] the target version's AgentRuntime, ToolExecutor, PermissionGate
       ├─ [C] current-on: the target version's MemoryRetriever → Context
       └─ [B] no shell, Memory CRUD, MCP, or subagents assembled
  → [C] the independent grader checks the workspace after the Agent stops
  → [+] atomic ledger + trial/artifact digests
  → [+] report-comparison validates references, then rebuilds the paired results

failure or interruption: [B] error slots and unrun slots are left behind; no automatic retry or rerun.
```

In the diagram, [old] means already in the previous version, [+] means new, [~] means extended, [C] means main consumer, and [B] means responsibility boundary. The comparator only coordinates runs; each Agent's Runtime, tools, and permissions come from the chosen commit. This way the old version never accidentally uses the current version's core code.

## Implementation Breakdown

### Why the comparison conditions must be frozen first

One comparison round has three groups: `old-off`, `current-off`, and `current-on`. `off` and `on` mean whether the Context is allowed to retrieve fixed memory summaries automatically. Each case runs three times, so `4 cases × 3 groups × 3 runs = 36 slots`. Within each case, the group order rotates, reducing the order bias of always running one group first.

A comparison edge is "the list of conditions allowed to change":

| Comparison edge | The only allowed change | Question it answers |
|---|---|---|
| `old-off → current-off` | The source commit | Did v0.53 regress relative to v0.52 |
| `current-off → current-on` | The Memory retrieval switch | Does automatic summary retrieval of fixed memories improve results, and how much does it cost |

If the suite, grader, tool permissions, budget, binding, or other fields differ, the comparator reports why they are not comparable. It never silently drops slots with more problems to make the remaining samples look complete.

The schema validates comparison edges through differences in group fields, and slot order is generated from the case index and repetition number. The core rotation rule is short:

```python
shift = (case_index + repetition - 1) % len(groups)
rotated = groups[shift:] + groups[:shift]
```

`shift` decides which group each run of each case starts from; the full order is written into the plan before any model runs. See [`comparison_execution_order()`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.53/src/mini_agent/evaluation/comparison_schema.py) for the implementation.

### How the Memory ablation stays fair

An ablation experiment means fixing the other conditions and turning only one capability on or off. This version prepares four very short semantic memories that contain only interface conventions and investigation methods. Each trial rebuilds the same snapshot from its own workspace identity, so one trial cannot learn another case's result.

The off group skips automatic retrieval; the on group uses the target version's own `MemoryStore`, `MemoryRetriever`, and existing Context logic, choosing at most four entries and 2,400 characters in total. The Memory CRUD tools are not registered, so the Agent cannot rewrite the experiment material. The Memory directory is outside the workspace, and the evidence saves only the material digests, whether retrieval happened, and the failure category, not the injected body.

A retrieval failure still runs with the Context's existing degradation, but the report marks the experiment condition as abnormal. This sample stays in the ledger and cannot be interpreted as a result of "retrieval was on and working". For the full material boundary, see the [comparison guide](../evaluation/comparison.md) and the [four frozen seeds](https://github.com/liiiiiiiiil/agent-from-scratch/tree/v0.53/tests/fixtures/evaluation/comparison/memories).

### Run and Observe

First, you can run the offline self-test with fixed responses:

```bash
PYTHONPATH=src python -m mini_agent.evaluation self-test-comparison --output /private/tmp/v053-comparison-offline
PYTHONPATH=src python -m mini_agent.evaluation report-comparison /private/tmp/v053-comparison-offline
```

The self-test still assembles the real Runtime and PermissionGate, but model responses come from local fixtures and no provider is contacted. It checks that the 36 slots run independently from their own initial files, that the grader accepts the known fix, and it probes tool failures, permission denials, and repeated identical calls on the side. The `run_kind` in the report is `fixture`, and these pass counts must not be counted as model results.

Before a real evaluation, copy [`comparison.template.json`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.53/tests/fixtures/evaluation/comparison/comparison.template.json), fill in the current complete commit, the configured profile aliases, and a reviewed price snapshot, then generate the plan:

```bash
PYTHONPATH=src python -m mini_agent.evaluation validate-comparison /path/to/filled-spec.json
PYTHONPATH=src python -m mini_agent.evaluation plan-comparison /path/to/filled-spec.json --output /private/tmp/v053-review-plan
```

The plan shows the cases, success criteria, the three version/retrieval groups, the model source summary, budget, prices, Memory material digests, and the full order. Generating the plan makes no model requests. Only after the user reviews and explicitly approves this manifest can the command with `--live` be run:

```bash
PYTHONPATH=src python -m mini_agent.evaluation run-comparison /private/tmp/v053-review-plan/comparison-plan.json --live --output /path/to/new-run
```

Each slot starts only once. When a run is interrupted, the ledger keeps the current state and the unrun slots; after fixing the implementation, freeze a new revision and start a new run, instead of reusing the old batch to fill the gaps.

The report keeps the grader pass rate and strict task success separate. A normal text finish does not mean the grader passed; the grader passing does not mean temporary resource cleanup succeeded. Model requests, successful responses, tool calls, permission denials, input/output tokens, Agent/grader durations, and cost are listed separately. Without usage or prices, `null` is shown; the recovery success rate is also fixed at `null` for this kind of coding comparison.

## Why This Design

Separating the coordinator from the target Runtime lets the same version of the runner call the code of v0.52 and v0.53 while keeping the current modules from mixing with the old version. Each version is unpacked temporarily from an archive of a complete commit, and the interface pre-check happens before the model request; incompatibility is refused directly.

The per-slot atomic ledger and the no-retry rule keep failure facts. The report is rebuilt from the digests of trials and artifacts, so the summary can be regenerated and traced to each paired piece of evidence. The independent grader is kept separate from the Agent's own account, so the model's self-evaluation is never taken as acceptance.

This version yields only descriptive observations under a fixed case set, the same binding, and frozen memory material. It does not prove statistical significance, does not measure cross-task learning, and does not represent other models or memory strategies. The historical v0.51 and v0.52 live baselines are still incomplete; the v0.53 live manifest still needs a separate review.

## Version Features, Next Lesson, and Code Index

This version delivers the comparison contract and the offline run chain; a real comparison still requires user review before it starts. Stage 14 is not declared complete on this basis; the next step is to recheck the open items of the historical live baselines, and then the maintainer decides the topic of later lessons.

- [Comparison contract and digests](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.53/src/mini_agent/evaluation/comparison_schema.py)
- [Ordered orchestration and trial isolation](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.53/src/mini_agent/evaluation/comparison.py)
- [Target source archives and API pre-check](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.53/src/mini_agent/evaluation/comparison_sources.py)
- [Runtime worker and side observation of retrieval](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.53/src/mini_agent/evaluation/comparison_worker.py)
- [Metrics and reproducible reports](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.53/src/mini_agent/evaluation/comparison_metrics.py) · [Report validation](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.53/src/mini_agent/evaluation/comparison_report.py)
- [CLI commands](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.53/src/mini_agent/evaluation/__main__.py) · [Frozen case set digests](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.53/src/mini_agent/evaluation/benchmark.py)

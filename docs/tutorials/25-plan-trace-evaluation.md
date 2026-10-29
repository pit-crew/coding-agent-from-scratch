# Lesson 25: Plan trace replay and acceptance

Previous: [Evidence-driven replanning and stagnation stop](24-replanning-policy.md) · [Tutorial overview](README.md) · Next: later version lessons (to be planned)

Code snapshot: `v0.25` · Adjacent diff: `v0.24..v0.25`

The example commands in this lesson are for Bash/zsh. The `v0.25` tag is created manually by the repository maintainer before delivery; before the tag exists, you can stay on the current branch to read and run the implementation.

## Lesson Goals

The previous lesson already saved plan revisions, replanning triggers, execution failures, recovery actions, and verification history, but these records are scattered across different lists. Looking only at generations tells you what happened in one generation, but it cannot answer, when two revisions are submitted in the same generation, whether an investigation belongs to the old approach or the new one.

After this lesson, you should be able to explain how three dimensions divide the work: a `generation` is the verification generation after the environment goes through a side effect or recovery, a `revision` is a version of the plan structure, and sequence events connect the two, together with triggers, user decisions, and fact records. Trace is still read-only: it shows the integrity of the evidence chain, does not re-run tools, and does not judge for the model whether a plan is smart.

## Prerequisites

You need basic Python, Bash/zsh, and the Plan Contract, Repair Loop, and replanning triggers from Lesson 24. First switch to this lesson's code and view the adjacent diff:

```bash
git checkout v0.25
git diff --stat v0.24..v0.25
```

If the `v0.25` tag does not exist locally yet, you can keep running the API below on the current development branch. Pinned source links and tutorial fact checks follow the snapshot after the maintainer creates the tag manually.

## New and Changed Files

| File | Role in this lesson |
| --- | --- |
| `src/mini_agent/state.py` | Adds a `TraceEvent` that is contiguous within a task, recording order, generation, revision, phase changes, and stagnation summaries under the same State lock in which facts are written successfully. |
| `src/mini_agent/trace.py` | Adds revision queries, a plan timeline, plan ownership, structural validation, plan causal edges, and the basis of conclusions, while keeping the v0.21 generation query. |
| `src/mini_agent/__main__.py` | Adds the read-only command `/trace revision <revision_id>`. |
| `tests/test_plan_trace_v025.py` | Covers the failure—replan—new generation verification chain, user handoff, stagnation resume, query exclusivity, and corrupted snapshots. |
| `docs/operation/manual.md`, `README.md`, `README_EN.md`, `CHANGELOG.md`, `pyproject.toml` | Sync the operation entry, version navigation, and release metadata. |

## Key Flow

The flow below keeps the execution and Repair Loop nodes from Lesson 24 and only inserts sequence events where facts are written. An event stores the type and ID of an existing record, so it does not copy raw tool output:

```text
[old] attempt / failure / verification facts written
       │
       ├── [+] TraceEvent(sequence_id, generation_id, revision_id, record pointer)
       │
[old] failure -> request_replan -> exploring -> commit_plan
       │                                  │
       │                                  └── [+] parent / trigger / diff
       │
[old] possible effect / recovery -> new generation -> independent verification
       │                                   │
       └── [+] revision -> attempt / recovery / verification causal edges
```

Take "the old plan fails, a replan cites the failure, the new plan passes verification" as an example. The event order expresses: the failure of the old revision happens first; the trigger references this failure; the new revision references the old revision and the trigger when it is submitted; then the new revision's execution facts and the new generation's verification pass. The later passing evidence is not written back to the old revision and is not interpreted as proof that the old plan was correct.

The relationship between `generation` and `revision` can be seen like this:

```text
plan revision 1 ──failed attempt / failure──> trigger 1 ──> plan revision 2
       │                                            │                 │
       └── generation 0                             └── parent         └── execution and verification in generation 1
```

## Problems in the Previous Version

In Lesson 24, `snapshot()` already provided `plan_revisions`, `plan_progress_history`, `replan_triggers`, `user_plan_decisions`, attempts, failures, recoveries, and verification history separately. Trace could validate the references inside each table, but it could not reliably know the order of the records. Using array positions would mistake an implementation detail for the order of events, and using generations cannot tell several revisions in the same generation apart.

So this lesson only adds connecting information. State transitions, model tools, and planning policies stay unchanged; events also take no part in completion decisions, budget calculation, or verification evidence. An old snapshot without plan data still replays with the v0.21 result; when there are plan records but no new events, the report keeps the structure that can be validated directly and marks cross-record order and execution ownership as `unresolved`.

## Core Concepts: Sequence Events

`TraceEvent` is a very small pointer record. Its `sequence_id` increases contiguously within a task, and `record_type` and `record_id` point to an existing record; the ID of a verification is its index in `verification_history`. The event also stores the generation and revision at the time it happened, and the before/after values of the planning / repair phase when they actually changed.

```python
snapshot = state.snapshot()
for event in snapshot["trace_events"]:
    print(event["sequence_id"], event["kind"], event["revision_id"])
```

This code reads the public snapshot and triggers no replay side effects. You should see plan submissions, step progress, execution results, failures, and verification events in the order the facts were written; an illegal `commit_plan` adds no event, because it did not write the Plan Contract successfully.

Starting a task and `/reset` clear old events and restart numbering from 1. A stagnation warning stays in the event list even if the current state later clears it because of a new observation; the stagnation fields of an event contain only the type, count, and a short fingerprint, not tool output.

## Core Concepts: Revision Queries and the Plan Timeline

The default `build_trace(snapshot)` still returns all generations. `build_trace(snapshot, generation_id=1)` still shows only generation 1 as the main display scope. The new revision query uses keyword-only arguments, so the two stable dimensions are not mixed into one positional argument:

```python
from mini_agent.trace import build_trace, render_trace

report = build_trace(snapshot, revision_id=2)
print(render_trace(report))
```

The revision view contains the goal, success criteria, parent, trigger, the `reason` the model submitted, the structural difference the Runtime computed, step progress, user decisions, and the investigation, execution, failure, recovery, and verification facts while it was in effect. `plan_timeline` orders these events by `sequence_id`; if the queried revision comes from a replan, the failure or user feedback in the old revision is shown as the trigger's cause but is not placed within the new revision's execution period.

The two queries cannot be specified together, and an invalid ID raises `TraceQueryError`. Corrupted records are a report integrity problem: the report still returns the records it can locate and marks the matching causal edges as `UNRESOLVED`.

The matching CLI entries are:

```text
/trace
/trace <generation_id>
/trace revision <revision_id>
```

All three entries are intercepted before a new task runs. Trace does not call the LLM, a tool handler, or the PermissionGate, does not append to the conversation history, and does not change State, budgets, or generations.

## Implementation Breakdown

`state.py` appends events where existing facts are written successfully. A plan submission first writes `plan_committed`, and if it resolves an active trigger, then appends `trigger_resolved`; step progress, user decisions, recovery actions, execution results, failures, and verification each point to their own records. The attempt, failure, and verification derived from one execution result are appended in write order inside the same lock, and Trace then builds causal edges from the IDs.

`trace.py` first runs the existing generation integrity checks, then handles the plan records. It checks whether the parent exists and is earlier than the child revision, whether step dependencies exist and are acyclic, whether `replaces` references only steps removed from the parent, and whether the saved diff equals the result recomputed from the two snapshots. It also checks the progress revision / step, the active interval and status continuity, trigger sources and single consumption, and whether plan-only decisions point to the current revision that was awaiting approval at that time.

Ownership of plan facts accepts only the revision provided by sequence events. Without events, the report can show the revision's own structure, parent, and trigger references, but it does not guess from the generation or array position which revision an attempt belongs to. Gaps in event numbers, dangling references, wrong generations / revisions, and cross-generation verification all go into `integrity.issues`.

The plan causal edges in the report include:

```text
parent revision -> revision
failure / attempt / user decision -> trigger -> revision
revision -> progress / decision / attempt / recovery / verification
```

Every edge carries `resolved` and `status`. The final conclusion keeps the `done`, `blocked`, or `failed` saved by the Runtime, with the active revision's step statuses, the current generation's independent verification records, `verification_required`, the last failure, the stagnation summary, and the terminal summary attached. Trace only checks whether this evidence connects; it does not decide the terminal state again.

## Why This Design

Storing order separately costs one more very small append-only record in State, but gives deterministic ownership across lists. Events store only indexes and do not copy output, so the report can find the facts without widening the exposure of sensitive data. Keeping generation queries and revision queries separate keeps "environment verification generation" and "approach version" each clear.

The report chooses not to guess about corrupted data, because filling in a plausible-looking ownership would hide the uncertainty. The resulting limitation is that a hand-built old plan snapshot without events only gets a partially verifiable report; full replay must start from a runtime snapshot with `trace_events`. A later generation that passes verification also does not automatically prove the old plan correct; whether the old failure was really solved must still be supported jointly by the existing facts and the current Runtime conclusion.

## Design Boundaries

- Trace consumes only `AgentState.snapshot()` and does not access private original arguments, checkpoint content, the LLM, or the executor.
- Events do not advance the generation, change budgets, or produce verification evidence, and they do not replace the write sources of plans / attempts / failures / recoveries.
- `reason`, feedback, plan text, paths, and stagnation fingerprints are bounded and redacted within the State or report boundary; Trace does not reread tool output to judge "whether there was progress".
- Old snapshots without plan data stay compatible with v0.21; those with plan data but missing events return an incomplete report and keep unresolved edges.

## Version Features, Next Lesson, and Code Index

This version adds ordered replay of the plan chain, revision queries, plan causal edges, integrity reports for corrupted snapshots, and `/trace revision`. The boundaries of the simple Direct Path, the old generation query, the Repair Loop, and independent verification remain in effect.

The next lesson is not planned yet. The pinned code snapshot index is below; the links point to the `v0.25` tag at the time this lesson was delivered:

- [TraceEvent and fact writes in `state.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.25/src/mini_agent/state.py)
- [Read-only replay and integrity checks in `trace.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.25/src/mini_agent/trace.py)
- [The Trace CLI entry in `__main__.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.25/src/mini_agent/__main__.py)
- [The acceptance chain in `test_plan_trace_v025.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.25/tests/test_plan_trace_v025.py)

# Lesson 20: Repair loop (Repair Loop, v0.20)

Previous: [Single-file checkpoint and rollback](19-checkpoint-rollback.md) · [Tutorial overview](README.md) · Next: [Task trace replay](21-trace-replay.md)

> Code snapshot: `v0.20` · Adjacent diff: `v0.19..v0.20` · Shell: Bash/zsh

> Requirements: Python 3.10+; the core runtime uses only the standard library.

## Lesson Goals

The earlier lessons can already record failures, choose `retry`/`adjust`/`rollback`, and run checks for a new generation (verification boundary). But if the model keeps writing files right after a failure, or treats "the recovery action executed successfully" as "the task is fixed", the runtime cannot guarantee that verification evidence belongs to the current environment. v0.20 fixes this exception path into a bounded Repair Loop:

```text
failure → diagnosis → bounded recovery → new generation → independent verification
                         ↘ continue / repair again / blocked / failed
```

After this lesson, you should be able to explain:

- What each of the three phases `idle`, `diagnosis_required`, and `verification_required` allows;
- Why the initial failure does not consume a repair cycle, while an actually activated `retry`, `adjust`, or `rollback` consumes one;
- Why, after a successful recovery, the next tool round must be a single `run_shell(purpose="verification")`;
- Why both the executor and the agent loop do admission checks, while still feeding back a result for every model tool call.

## Why This Version Is Needed

v0.19 can already roll a file back to a checkpoint, but "the recovery action finished" still does not mean "the task is correct". Before this version, State had only one boolean signal, `verification_required`: it could not express the intermediate phase "diagnose first, then recover", and it could not stop the model from running new side effects while a repair was pending. Another boundary problem: repair cycles were wrongly incremented by the number of verification failures, and permission denials or invalid recovery arguments could also blur the meaning of the budget.

This version puts the phase, the active failure, the active recovery, and the cycle budget into State. The runtime still does not choose business repair strategies for the model; the model gives a diagnostic reason and action through the existing `recover` tool, and the runtime only guarantees order, references, permissions, generations, and limits.

## Prerequisites

Read Lessons 17, 18, and 19 first. View the version diff first, then switch to this lesson's snapshot:

```bash
git checkout v0.19
git diff --stat v0.19..v0.20
git diff v0.19..v0.20 -- src/mini_agent/state.py src/mini_agent/tools/base.py src/mini_agent/agent.py
git checkout v0.20
```

The `v0.20` tag for this lesson is created manually by the publisher after the implementation passes acceptance; if the tag does not exist locally yet, keep the source links and diff commands as release notes instead of treating the current working tree as the historical snapshot.

## New and Changed Files

| File | Change | Purpose |
|---|---|---|
| [`state.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.20/src/mini_agent/state.py) | Adds repair loop state and active causal references | Stores the phase, failure/recovery, cycle budget, and completion conditions |
| [`tools/base.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.20/src/mini_agent/tools/base.py) | Adds phase admission before execution | Refuses non-compliant calls before the PermissionGate and handler |
| [`agent.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.20/src/mini_agent/agent.py) | Adds round-level admission | In diagnosis, recover must be alone; in verification, only a single call is accepted |
| [`context.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.20/src/mini_agent/context.py) | Renders the Repair Loop critical state | Phase, active references, and budget stay visible after compaction |
| [`prompt.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.20/src/mini_agent/prompt.py) | Adds protocol rules | Tells the model to diagnose first after a failure and to verify independently first after recovery |

## Key Flow

```text
normal execution
  ├─ possible effect succeeds → phase stays idle, but completion evidence is invalidated
  └─ any failure that needs handling → FailureEvent + diagnosis_required

diagnosis_required
  ├─ read-only / update_todo → stay in the diagnosis phase
  ├─ recover (alone in its round) → validate the active failure, permission, and budget
  └─ possible effect / verification → protocol error, handler not run

accepted retry / adjust / rollback
  ├─ cycles_used += 1
  ├─ open a successor generation
  └─ recovery attempt finishes → verification_required

verification_required
  ├─ a single independent verification passes → idle, clear active references
  └─ verification fails → new FailureEvent + diagnosis_required
```

`ask` and `block` are still the conservative terminal state `blocked`. The cycle budget defaults to `MAX_REPAIR_CYCLES = 3`: the initial failure, invalid recoveries, permission denials, and `ask`/`block` consume nothing; a recovery action counts only after its target is authorized and a new generation is activated. Once the limit is reached, a fourth recovery cannot start silently; the runtime finishes with an explicit `failed` reason.

## Implementation Breakdown

### 1. State is the single source of truth for the phase

`AgentState.snapshot()` adds `repair_loop`:

```text
phase                 idle | diagnosis_required | verification_required
active_failure_id     the FailureEvent that must be handled now
active_recovery_id    the RecoveryAction for the current generation
cycles_used           recovery cycles activated so far
cycles_remaining      remaining budget
required_next_action  the next step the runtime requires
```

A verification failure does not increase `cycles_used` directly. Only when `reserve_recovery()` passes target validation, the PermissionGate allows it, and `activate_recovery()` is called does a `retry`, `adjust`, or `rollback` open a new generation and get counted. The active failure reference also stops the model from recovering an old event that a newer failure has already replaced.

### 2. Two layers of admission guarantee order

The agent loop can see a whole batch of tool calls, so it enforces round-level constraints: in diagnosis, `recover` must be alone; in verification, there can be only one shell call with the correct purpose. The ToolExecutor still does a second check, protecting direct calls, embedded use, and concurrent entries. An admission failure returns a structured protocol result, and the handler, PermissionGate, and generation are never called; the agent loop still adds a `role=tool` for every call in the original order.

The recovery target runs with a reservation protected by the State lock; it is the only controlled exception in the verification phase. After it finishes, it cannot bypass independent verification.

### 3. Context and the completion reminder

Both the Structured State and the compacted critical state keep the repair loop. After a failure, the Runtime Notice asks for read-only investigation, a Todo update, or a standalone recover; after recovery, it asks for independent verification in the next round. Continuing to output plain text under the same `progress_marker` still enters the existing `blocked` rule, so the model cannot skip a phase with words.

## Why This Design

- The phase machine separates "failure facts", "model diagnosis", and "verification evidence", so a natural language success message cannot change execution state.
- The active failure is an explicit reference; causality is not guessed from recency, and an old failure cannot keep driving recovery after a new failure appears.
- The two admission layers cover the batch protocol and the direct execution boundary respectively, but both only enforce safety constraints and do not introduce a second planner.
- Cycles are counted by actually activated recovery actions, so rejections do not consume repair chances; a failed recovery attempt still counts as used, because its side effects were already approved to run.

## Version Features, Next Lesson, and Code Index

This version includes: a phased Repair Loop, active failure/recovery, a recovery cycle budget, independent verification after recovery, two-layer admission in the agent loop and executor, Structured State/Runtime Notice sync, and explicit terminal states for `ask`/`block`/budget exhaustion.

This version does not include automatic inference of repair strategies, automatic retries, recovery from external waits, general transactional rollback, or Trace & Replay; the next lesson consumes, read-only, the facts already recorded by v0.17–v0.21 and must not re-run tools.

Code index:

- [`state.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.20/src/mini_agent/state.py): RepairPhase, active references, generation, and budget;
- [`recovery.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.20/src/mini_agent/recovery.py): the recover schema and action dispatch;
- [`tools/base.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.20/src/mini_agent/tools/base.py): structured execution and the second admission layer;
- [`agent.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.20/src/mini_agent/agent.py): round scheduling and complete tool result feedback;

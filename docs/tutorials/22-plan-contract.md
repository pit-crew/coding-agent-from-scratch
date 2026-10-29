# Lesson 22: Plan Contract: turning Todo into an immutable execution contract (v0.22)

Previous: [Task trace replay](21-trace-replay.md) · [Tutorial overview](README.md) · Next: [Investigate first, then hand off a plan](23-plan-mode-handoff.md)

> Code snapshot: `v0.22` · Adjacent diff: `v0.21..v0.22` · Shell: Bash/zsh

> Requirements: Python 3.10+; the core runtime uses only the standard library.

## Lesson Goals

The previous lesson saved execution attempts, failures, recoveries, and verification facts by generation, but the plan itself was still a Todo list that could be overwritten as a whole. After this lesson, you should be able to explain three things: why "changing the plan structure" and "advancing step status" cannot share one write entry; why historical revisions cannot be overwritten; and why a completed step still does not mean verification passed.

This version represents the plan of a complex task as a Plan Contract. It is an execution contract submitted by the model whose structure the Runtime validates: the contract states the goal, constraints, acceptance criteria, steps, and dependencies, but it does not judge for the model which plan is smartest in business terms, and it does not treat plan status as an environment fact.

## Prerequisites

You need basic Python, Bash/zsh, and Git. First look at the previous lesson's code, then switch to this lesson's snapshot:

```bash
git checkout v0.21
git checkout v0.22
git diff --stat v0.21..v0.22
```

The first command lets you compare with the previous version; the second enters this lesson's code; the last shows the size of this version's changes. If the current workspace does not yet have the `v0.22` tag created by the user, run this set of comparison commands after the tag exists.

## New and Changed Files

This version has only one main thread: the model writes the plan protocol, State stores immutable facts, and the Context regenerates the execution view every round.

| File | Purpose |
| --- | --- |
| `src/mini_agent/state.py` | Defines the frozen `PlanStep`, `PlanRevision`, `PlanProgressEvent`, and `PlanningState`, and validates and commits under one State lock. |
| `src/mini_agent/tools/plan.py` | Exposes two state-bound tools, `commit_plan` and `update_plan_progress`. |
| `src/mini_agent/tools/__init__.py` | Registers the new plan tools and no longer registers the model-side `update_todo`. |
| `src/mini_agent/context.py` | Renders the active revision, the current step, startable steps, blocked dependencies, and count summaries. |
| `src/mini_agent/prompt.py` | Tells the model when to submit a full plan and when to only advance step status. |
| `src/mini_agent/agent.py` | Makes plan writes in the same round run serially in the model's call order. |

The command below only lists diff statistics; its purpose is to help you map this table to the real changes, not to treat the file list as a design conclusion.

```bash
git diff --stat v0.21..v0.22
```

## Problems in the Previous Version: One Todo Did Two Jobs

The old Todo submission arguments contained both content and status. When the model wanted to say "start investigating", it had to submit the whole list; when it wanted to say "the direction of investigation changed", it also had to submit the whole list. The Runtime could only see a new list and could not reliably tell whether it was progress on the old plan or a new plan.

v0.21 already left an audit snapshot of every submission with `TodoRevision`, but the current Todo was still replaced as a whole; the snapshots also could not tell "the same step advanced" from "this step changed meaning". Steps had no stable IDs, dependencies, or success criteria; a passing verification only says some command passed in some generation and cannot say that some natural language item in the Todo is done.

So v0.22 uses two protocols:

- `commit_plan` writes the full plan structure and, on success, creates a new `PlanRevision`.
- `update_plan_progress` only writes the status of one step of the current revision and, on success, appends a `PlanProgressEvent`.

Simple tasks still run directly; there is no need to create a plan for one calculation or one read.

## Version Change Map

From the real entry of the previous version, every Todo submission by the model is written to State through the tool executor; execution results then go back into the next round's context. In the diagram, `[old]` is a node already in v0.21, `[+]` is new in this version, `[~]` is changed in this version, `[C]` is the main consumer, and `[B]` is the boundary of this version.

```text
v0.21 baseline
[old] user task -> agent_loop -> LLM tool_calls -> ToolExecutor
                                                 -> update_todo -> AgentState.update_todos()
                                                                   -> current Todo + TodoRevision
                            <- role=tool result for each call <- ToolExecutor
                            -> ContextManager(current State) -> next LLM round
[old] file/command execution -> ExecutionAttempt / generation -> independent verification
                                                       -> completion_reminder / final reply
```

This version keeps the same tool result feedback chain but splits the Todo write entry into "submit structure" and "advance status". In practice, a step is usually set to `in_progress` first, the work is done, then it is set to `completed`; when verification is needed, it is still run separately.

```text
v0.22 change
[old] user task -> agent_loop -> LLM tool_calls
                       -> [~] plan writes run in model order -> ToolExecutor
                            ├-> [+] commit_plan -> AgentState.commit_plan()
                            │                    -> PlanRevision 1 / later full Revision 2
                            └-> [+] update_plan_progress -> AgentState.update_plan_progress()
                                                         -> PlanProgressEvent
                       <- [old] role=tool result for each call
                       -> [C] ContextManager generates the current plan execution view from the State snapshot
                       -> [old] next LLM round
[+] validation or phase rejection -> plan_rejected -> role=tool -> next LLM round
                                              [B] no FailureEvent or generation created
[old] file/command execution -> ExecutionAttempt / generation -> independent verification
                                                       -> [~] plan steps + verification together decide whether it can finish
[B] simple tasks take the Direct Path; plan writes themselves are neither environment changes nor verification evidence
```

The new revision after a successful `commit_plan` and the event after a successful `update_plan_progress` are both stored in State; the ContextManager is their main consumer and takes only the view the current execution needs each round. The rejection path still feeds back a tool result for every call so the model can correct its input, but plan validation errors are not recorded as execution failures. This difference is also why the diagram keeps the old execution and verification chain.

## Key Flow

The initial submission carries no `parent_revision_id`. The Runtime sets all steps to `pending` and changes `planning_state.phase` from `direct` to `executing`. Later submissions must reference the current active revision; an old revision or another branch cannot become the parent.

A minimal `commit_plan` input looks like this. Note that the input has no `status`: status is managed by the Runtime through progress events.

```json
{
  "goal": "Complete the goal",
  "constraints": [],
  "success_criteria": ["The final check passes"],
  "steps": [
    {
      "step_id": "inspect",
      "content": "Inspect the existing implementation",
      "depends_on": [],
      "success_criteria": ["The call chain and boundaries are confirmed"],
      "replaces": []
    }
  ],
  "reason": "Fix the investigation and acceptance scope first"
}
```

The Runtime first validates the whole input, then commits it in one go. Step IDs must be stable and unique; dependencies must point to steps in the same revision and must not be self-dependencies or cycles; text and counts have fixed limits. No failure may commit half a revision.

## Implementation Breakdown

### 1. Revisions store structure, events store changes

`PlanRevision` is a frozen dataclass that stores one full plan; `PlanProgressEvent` is also a frozen dataclass that stores one status transition. An old revision does not change because of later progress updates: the current active plan is a view re-derived from the revision's initial state and that revision's events.

```python
@dataclass(frozen=True)
class PlanProgressEvent:
    progress_id: int
    revision_id: int
    generation_id: int
    step_id: str
    from_status: str
    to_status: str
    reason: str
```

This way, every step of `pending -> in_progress -> completed` is traceable; skipping a status, going backwards, completing twice, unmet dependencies, and two steps in progress at the same time are all rejected.

### 2. Revisions inherit status but do not reuse old meanings

A structural revision submits a full new plan. Kept step IDs inherit the latest status derived from the parent revision; new steps or replacement steps start at `pending`. An ID already removed from the plan cannot reappear, and the `content` and step-level `success_criteria` of the same ID cannot change. To change the meaning of a step, use a new ID and reference the step removed from the parent revision in `replaces`.

`parent_revision_id`, structural validation, and revision numbering are completed inside the same lock, so two concurrent submissions cannot produce revisions with the same number, a forked active pointer, or half a plan.

### 3. Plan tool errors do not masquerade as execution failures

Plan argument errors or plan invariant errors feed back a `plan_rejected` tool result. It does not create a `FailureEvent`, does not enter `diagnosis_required`, and does not advance the generation. Only real handler exceptions still follow the tool layer's exception boundary and become execution failures.

Both plan tools default to `ALLOW` and `effect_class=none`. So they do not clear current verification evidence, and they cannot be run indirectly through `recover.retry`, `recover.adjust`, or rollback. If the current phase requires independent verification, the plan tools are rejected, but they do not bypass that phase.

If several plan writes appear in the same assistant round, the Runtime still runs them in the model's call order and feeds back one result for each call. They are not disguised as possible effects; plan writes are not environment changes.

### 4. Structured State shows only the bounded view execution needs

The full `plan_revisions` and `plan_progress_history` are stored in State. Each round, the context regenerates only a bounded view: the current revision's goal, constraints, and task-level success criteria; a bounded summary of the current `in_progress` step's content, dependencies, and step-level criteria; at most five steps that can start immediately; at most ten steps blocked by dependencies; and the completed, pending, in-progress, and omitted counts. When dependencies or criteria are long, the current step line may also be truncated; to check the full contract, still read the State snapshot.

This means compacting history messages does not delete the plan contract. When the Context degrades, the key plan lines still take priority over ordinary tool summaries, and the final length stays within the existing 6000-character limit.

### 5. Completion is still decided by the plan and verification together

With an active plan, all active steps must be `completed`, and the independent verification after the latest possible change must still pass. A step's `success_criteria` is a plan requirement, not `VerificationEvidence`; marking it completed does not replace tests or checks.

The standard-library script below walks through this chain to observe the plan tool results, the generation, and the completion reminder. Run it in Bash/zsh in this lesson's code directory; it writes no files, and a local permission policy only allows the plan tools and `python` shell commands. The plan tools are written to State atomically by their handlers; `record_execution_result()` records the tool facts of actual execution and verification, simulating the commit step of the agent loop.

```bash
PYTHONPATH=src python - <<'PY'
import json
from mini_agent.permission import ALLOW, PermissionGate, PermissionPolicy
from mini_agent.state import AgentState
from mini_agent.tools import create_registry
from mini_agent.tools.base import ToolExecutor

state = AgentState()
state.begin_task("Check a calculation command")
policy = PermissionPolicy({
    "commit_plan": ALLOW, "update_plan_progress": ALLOW,
    "run_shell": {"python *": ALLOW},
})
executor = ToolExecutor(create_registry(state), PermissionGate(policy))

def call(name, arguments):
    result = executor.execute_result(name, arguments, state)
    state.record_execution_result(result)
    return result

plan = {
    "goal": "Check a calculation command", "constraints": [],
    "success_criteria": ["The command and an independent verification pass"],
    "steps": [{"step_id": "check", "content": "Run the calculation command",
               "depends_on": [], "success_criteria": ["Outputs 2"], "replaces": []}],
    "reason": "Record the task and steps first",
}
print("commit:", json.loads(call("commit_plan", plan).output)["status"], state.current_generation_id)
for status in ("in_progress", "completed"):
    if status == "completed":
        result = call("run_shell", {"command": 'python -c "print(1 + 1)"', "purpose": "execution"})
        print("execute:", result.outcome, state.current_generation_id)
    result = call("update_plan_progress", {
        "revision_id": 1, "step_id": "check", "status": status, "reason": status,
    })
    print("progress:", json.loads(result.output)["to_status"])
print("verification still required:", state.completion_reminder()["verification_required"])
call("run_shell", {"command": 'python -c "print(1 + 1)"', "purpose": "verification"})
print("verification:", state.snapshot()["verification_evidence"][-1]["outcome"])
print("completion reminder:", state.completion_reminder())
PY
```

You should see, in order, `commit: committed 0`, `progress: in_progress`, `execute: succeeded 1`, `progress: completed`, `verification still required: True`, `verification: passed`, and `completion reminder: None`. Submitting the plan and the two progress updates did not advance the generation; running the command advanced it to generation 1. Even after the step is completed, the reminder still requires independent verification; only after verification passes does the reminder disappear. The `None` here only means the completion conditions are met; it does not declare the task finished on behalf of the full agent loop.

Without an active plan, the Direct Path keeps the completion conditions of the previous version. The completion reminder's `progress_marker` uses the active revision and the derived step statuses; repeated or rejected structural submissions cannot create false progress, and only real step events allow a new reminder.

## Why This Design

Structure and progress are separated so that the Runtime can answer "is this a change of approach, or continued execution of the original approach". Immutable revisions keep old plans, and events express step changes with very small records; this is easier to audit than copying the Todo list every time, and it stops progress updates from rewriting the meaning of the plan.

This version has the model submit a full new structure instead of letting the Runtime guess how to add steps or reorder dependencies. The benefit is a simple protocol with deterministic validation; the cost is that the model must resubmit the full plan when revising. The runtime only checks format, references, and status invariants; it does not evaluate whether a business plan is sufficient.

The plan is not treated as an execution fact. Possible side effects are still managed by the existing generation rules, verification is still produced by independent verification, and failures still enter the existing Repair Loop. This keeps "the plan says done" and "the environment is correct" from being mixed up.

## Design Boundaries

- Simple tasks are not required to create a plan, and complexity is not guessed automatically from task length.
- This version has no separate plan mode, Explore gate, user approval, or replan trigger.
- There is no general stagnation detection or plan revision budget; the related shapes in `PlanningState` stay frozen, but this version does not use those capabilities.
- `/trace` keeps replaying, read-only, the generation, execution, failure, recovery, and verification facts of v0.21; the full Plan causal chain is not shown in this version's Trace.
- The Plan Contract does not relax project instructions, the PermissionGate, the Repair Loop, or verification rules.

## Version Features, Next Lesson, and Code Index

The new observable capabilities in this lesson are: a full immutable Plan Contract, independent progress events, a read-only Todo compatibility projection, and Structured State that contains the plan execution view. After this version, the next stage discusses stricter planning boundaries; this lesson does not implement those runtime behaviors in advance.

Implementation entries pinned to this lesson's tag:

- [`state.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.22/src/mini_agent/state.py): frozen models, atomic validation, revision and progress derivation.
- [`plan.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.22/src/mini_agent/tools/plan.py): the two model-visible state-bound tools.
- [`context.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.22/src/mini_agent/context.py): the bounded Structured State plan view.
- [`agent.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.22/src/mini_agent/agent.py): the in-round ordering guarantee for plan writes.

Go back to the [tutorial index](README.md), then use the [operation manual](../operation/manual.md) to see the runtime boundaries of the current version.

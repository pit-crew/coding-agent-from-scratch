# Lesson 39: Delivering subagent results safely to the parent Agent

Previous: [Bounded parallel read-only subagents](38-parallel-delegation.md) · [Tutorial overview](README.md) · Next: Stage 11 (planned)

> Code snapshot: `v0.39` · Adjacent diff: `v0.38..v0.39` · Shell: Bash/zsh

> Requirements: Python 3.10+. This lesson uses local sessions and test code to understand the recovery boundary and needs no real API key.

## Lesson Goals

In Lesson 38, a subagent can finish first and keep its result in the current process's memory while waiting for the parent thread to deliver in the order A, B, C. The problem: if B already has a trustworthy result but the parent process crashes before writing it into the parent Context, the next process can neither assume B succeeded nor safely rerun B.

This lesson saves "the result was produced" and "the result was delivered" separately. After reading, you should be able to explain:

- What `result_ready` and `committed` each mean;
- Why the session saves the raw result text and hash instead of only a "done" label;
- Why recovery can deliver the original result but cannot call the child model again;
- Why, without a durable raw result, the call must be handed to the user.

## Problems in the Previous Version

The scheduler of v0.38 can keep the completed results of B and C in memory and write them into the parent Context in order after A finishes. This design keeps the message order during normal runs but leaves a cross-process window: after memory is gone, the session may only know that some call was admitted or was running.

"No result" does not mean "not executed". The child LLM may already have used budget, and the old request may already have returned without being written to disk. Rerunning automatically would produce new calls and new investigation facts, and possibly duplicate costs. So this version saves controlled raw text sufficient to rebuild the parent `role=tool` message.

## Prerequisites and Version Checkout

You need Lesson 38, basic Python, Bash/zsh, and Git. The commands below are only for viewing code; a command-line first task does not imply that the program exits right after running it.

```bash
git checkout v0.38
git diff --stat v0.38..v0.39
git diff v0.38..v0.39 -- src/mini_agent/session.py src/mini_agent/state.py src/mini_agent/delegation.py src/mini_agent/runtime.py src/mini_agent/resume.py
git checkout v0.39
```

## New and Changed Files

This version changes code along the main thread "produce result → save result → deliver in order → crash recovery":

| File | Purpose |
|---|---|
| [`src/mini_agent/session.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.39/src/mini_agent/session.py) | Saves bounded raw text of results awaiting delivery, and provides atomic validation and delivery entries. |
| [`src/mini_agent/state.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.39/src/mini_agent/state.py) | Records result settlement, delegation status, and the ledger facts kept on recovery. |
| [`src/mini_agent/delegation.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.39/src/mini_agent/delegation.py) | Separates the "child task finished" callback from the "parent-side delivery" callback. |
| [`src/mini_agent/runtime.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.39/src/mini_agent/runtime.py) | Connects the three moments: start, `result_ready`, and `committed`. |
| [`src/mini_agent/resume.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.39/src/mini_agent/resume.py) | Derives a recovery session from the source session and delivers results in the original order. |
| [`src/mini_agent/context.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.39/src/mini_agent/context.py) | Keeps the parent-side context showing only result references and limited lifecycle information. |

## Version Change Map

Legend: `[old]` already in v0.38, `[+]` new in v0.39, `[~]` changed in v0.39, `[C]` main consumer, `[B]` boundary of this lesson.

In v0.38, completed results stop in the current process:

```text
[old][C] parent Runtime
      -> [old] Scheduler worker
      -> [old] in-memory result buffer B, C
      -> [old] wait for A
      -> [old] write State / role=tool / boundary for A, B, C in order
      [B] after a crash, in-memory results cannot be rebuilt from the session
```

v0.39 adds a recoverable boundary between "result produced" and "parent-side delivery":

```text
[C] parent Runtime
      -> [~] save the contract, reserved quota, and running
      -> [~] the worker finishes and the result is validated
      -> [+] State: result_ready
      -> [+] schema 3 saves the raw result, summary, and hash
      -> [~] the parent thread delivers A, B, C in order
      -> [+] State + attempt + role=tool + boundary committed atomically
      -> [C] State: committed -> next parent LLM request

active + pending boundary
      -> [C] resume derives a new session
      -> deliver existing raw text in parent call order
      -> [B] no child LLM call, no replay of old workers
```

## Core Concepts and Data Structures

### 1. `result_ready` means "the result is saved", not "the parent has received it"

`result_ready` means the subagent finished, the result passed contract validation, and the raw text is saved in the area awaiting delivery. `committed` means the parent State, the parent `role=tool` message, and the durable boundary have also been committed together. The window between the two is exactly the recovery window this lesson protects.

After the parent model issues A, B, C, B can enter `result_ready` first, but it cannot skip A and become the second message in the parent history directly. Recovery also delivers in the parent call order.

### 2. What the session saves

The session does not save the subagent's full history, hidden prompts, connections, or threads. It saves only bounded JSON that can rebuild the parent tool result, plus call identity and integrity information:

```json
{
  "invocation_id": "r-3-c-1",
  "delegation_id": "d-2",
  "result_id": "result-2",
  "result_hash": "<64 hex characters>",
  "result_json": "{...canonical SubagentResult...}",
  "result_summary": "Found the configuration read path"
}
```

On recovery, the system reserializes `result_json`, checks that it gets the same canonical JSON and SHA-256 hash, and then cross-checks the call ID, delegation ID, State status, size limits, and parent call order. Saving only the hash could prove that the raw text once existed, but it could not build the `role=tool` content the parent model needs.

### 3. The completion callback and the parent delivery callback are two moments

In v0.38, the "done" callback carried two responsibilities at once. v0.39 splits them into:

```python
def on_result_ready(index, result):
    state.delegation_result_ready(task.delegation_id, result)
    boundary.record_delegation_result_ready(invocation_id, result, state, context)

def on_result(index, result):
    # Receives only the result whose turn it is in the parent model's order
    commit_parent_tool_result(index, result)
```

This way B can be written to disk safely first, and C can keep using the parallel slot already released; but the parent Context still sees only the contiguous A, B, C.

### 4. Recovery delivers the raw text and does not rerun the subagent

On recovery, existing `result_ready` raw text first passes identity, hash, status, and order checks, then the parent-side `role=tool` is built directly and settled in the new recovery generation. The source session stays read-only, and the same source can be claimed only once; recovery does not inherit old PIDs, stdin, or verification eligibility, and does not reset budgets.

If a call has only `created` or `running` and no persisted raw text, the system cannot prove what it ever returned. It is recorded as an interrupted investigation or an uncertain fact, and an explicit issue is created for the user, instead of forging success or requesting the child model again automatically.

## Key Flow

The normal path:

```text
parent assistant: delegate_task A, B, C
  -> admission + batch reservation
  -> save created/running
  -> workers run
  -> B/C/A each finish and save result_ready
  -> deliver the parent tool results in the order A, B, C
  -> each time, save the attempt, committed, role=tool, and boundary together
  -> request the parent LLM after the whole round is committed
```

The crash path:

```text
the process exits between B's result_ready and the parent delivery
  -> active + schema 3 pending boundary
  -> resume derives a new session
  -> validate and deliver the saved raw text of B
  -> calls without raw text produce issues
  -> no child LLM call, no replay of old workers
```

## Run and Observe

In a local task with `/save` on, the thing to observe is not "a line of done text in the session" but: after a child result is produced, its `result_ready` raw text appears first; after the parent side commits in order, the raw text awaiting delivery goes into `committed`. If you recover between the two, the parent Context should receive JSON identical to the raw text, and the number of child model calls does not increase.

After the command-line first task is handled, the CLI still enters the interactive loop; the recovery entry takes over only when the current task and session boundaries allow it, and it never automatically inherits process resources for the old task.

## Implementation Breakdown

`DurableToolBoundary.persist_delegation_batch()` saves the contract summary, reserved quota, and delegation references before starting workers; `record_delegation_result_ready()` accepts only results that are already `result_ready` in State and recomputes the hash of the canonical raw text.

When the parent Runtime delivers, it first builds an `ExecutionResult`, then calls State's `commit_delegation_tool_result()`; it then does an atomic session commit together with the current Context and State. If the replacement fails, the Runtime does not proceed to the next parent model request. After a successful commit, the pending raw text is removed from the boundary, but the result ID, hash, summary, and usage are still kept for Trace.

`ResumeCandidate.prepare_resume()` reads results in the parent call order from the boundary and cross-checks them against the source State; calls without ready raw text follow the issue classification of Lesson 33. The source session stays read-only, and recovery claims it only once.

## Why This Design

Saving only a hash cannot rebuild the parent message, and saving the full raw result could make the session grow without bound, so this version uses canonical JSON, SHA-256, and both per-entry and total byte limits together. What it saves is the parent-side material recovery requires, not the full subagent log.

Splitting result production from parent delivery is a compromise between parallel execution and a deterministic message order: results can be written to disk out of order, while the parent history is still committed in call order. The cost is that the session keeps raw text awaiting delivery until the whole round finishes, and that content is not part of a clean safe point.

Recovery delivers existing raw text and hands calls without raw text to the user because rerunning automatically produces new model calls and new facts, and the real usage of the old call may be unknown. Conservatively keeping the original reservation ledger is safer than pretending nothing was consumed.

## Design Boundaries

- `/save` is still the only entry for enabling session persistence; no background result files or public tool arguments are added.
- Subagents are still depth=1 read-only instances; they cannot write the workspace, run shell, operate processes, or delegate again.
- Only results that pass the raw text, hash, call identity, State status, and order checks can be recovered directly.
- When an old session has no raw text awaiting delivery, it continues to be classified as an uncertain fact or an interrupted investigation as in Lesson 33.
- Child findings/evidence are still investigation material for the parent; they do not enter the parent `verification_evidence` and cannot replace independent verification.
- Trace reads only the parent State snapshot and result references; it does not call the LLM or guess missing facts through replay.

## Version Features, Next Lesson, and Code Index

This lesson adds delegation result delivery that can be recovered across processes: a child result is first persisted as `result_ready`, and then the parent side commits State, the attempt, `role=tool`, and the durable boundary together as `committed` in model order. Recovery uses the same raw text and does not rerun the subagent; calls without raw text continue through the user decision flow.

With this, the stage completes the minimal durable delegation chain; later lessons do not introduce writable subagents, recursive delegation, or cross-host workers early in this lesson.

Core source:

- [`src/mini_agent/session.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.39/src/mini_agent/session.py)
- [`src/mini_agent/state.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.39/src/mini_agent/state.py)
- [`src/mini_agent/delegation.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.39/src/mini_agent/delegation.py)
- [`src/mini_agent/runtime.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.39/src/mini_agent/runtime.py)
- [`src/mini_agent/resume.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.39/src/mini_agent/resume.py)

# Lesson 37: Adding lifecycles and a total budget to subagents

Previous: [Letting parent and child Agents use different model services](36-multi-provider.md) · [Tutorial overview](README.md) · Next: [Bounded parallel subagents](38-parallel-delegation.md)

> Code snapshot: `v0.37` · Adjacent diff: `v0.36..v0.37` · Shell: Bash/zsh

> Requirements: Python 3.10+. The core runtime still uses only the standard library; model connections are read from the local `config_local.py`.

## Lesson Goals

The subagent of Lesson 36 can return results, but the parent task does not clearly know what stage it is in, and it cannot put the resource use of several delegations into one ledger. This lesson gives each delegation a traceable lifecycle and has the parent task check the total budget before starting a subagent.

After reading, you should be able to explain:

- Why "the subagent failed" and "the parent side has received the failure result" are two different things;
- Why the budget is reserved first and settled by actual usage afterwards;
- Why cancellation is cooperative and cannot pretend to kill a network request immediately;
- Why, while a subagent has not finished, `/new`, `/reset`, and exit cannot simply clear the old task.

## Problems in the Previous Version

The v0.36 manager used one active flag to prevent duplicate starts, but it could not answer "which delegation is running", "has the result been handed to the parent Agent", or "has the cancellation finished". If every delegation got a full budget again, the parent task could also exceed its total limits on model calls, tool calls, or tokens.

This also affects the CLI's task boundaries: when the user enters `/new`, `/reset`, EOF, or `exit`, a subagent may still be in a synchronous request. The program must cancel and wait first; when the wait does not finish, it must keep the old task and report the reason clearly, instead of recording a clean exit.

## Prerequisites and Version Checkout

You need Lesson 36 and should understand `DelegatedTask`, `SubagentResult`, `AgentRuntime.run()`, and the model binding. Commands use Bash/zsh:

```bash
git checkout v0.36
git diff --stat v0.36..v0.37
git diff v0.36..v0.37 -- src/mini_agent/config.py src/mini_agent/state.py src/mini_agent/delegation.py src/mini_agent/runtime.py src/mini_agent/agent.py src/mini_agent/session.py src/mini_agent/__main__.py
git checkout v0.37
```

This lesson's state and cancellation regressions need no real API; if you run the CLI, configure a local model as in Lesson 36.

## New and Changed Files

The files are ordered along "accounting → running → delivery → task boundary cleanup":

| File | Purpose |
|---|---|
| [`src/mini_agent/state.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.37/src/mini_agent/state.py) | Stores delegation records, the budget ledger, state transitions, and safe point checks. |
| [`src/mini_agent/delegation.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.37/src/mini_agent/delegation.py) | Manages the current task, cancellation events, budget reservations, and subagent boundaries. |
| [`src/mini_agent/runtime.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.37/src/mini_agent/runtime.py) | Advances the delegation record after the parent tool result is committed. |
| [`src/mini_agent/context.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.37/src/mini_agent/context.py) | Shows the parent model a bounded view of active delegations and remaining budget. |
| [`src/mini_agent/session.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.37/src/mini_agent/session.py) | Refuses to save safe points with active or uncommitted delegations. |
| [`src/mini_agent/__main__.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.37/src/mini_agent/__main__.py) | Makes `/new`, `/reset`, EOF, `exit`, and abnormal exits clean up subagents first. |

## Version Change Map

Legend: `[old]` already in v0.36, `[+]` new in v0.37, `[~]` changed in v0.37, `[C]` main consumer, `[B]` boundary of this lesson.

v0.36 mainly records "what the tool call returned":

```text
[C] parent Agent
      -> [old] delegate_task
      -> [old] DelegationManager(_active: bool)
      -> [old] SubagentRunner
      -> [C] parent role=tool result
      [B] no complete lifecycle and no total ledger for the parent task
```

v0.37 writes the run process down as parent-side auditable records:

```text
[C] parent Agent
      -> [+] State.reserve_delegation()
      -> [+] DelegationRecord: created -> running
      -> [~] the child Runner checks cancellation and the per-run budget
      -> [+] result_ready + actual usage settlement
      -> [~] the parent Context writes role=tool
      -> [+] DelegationRecord: committed
      -> [C] next parent LLM request

[B] v0.37 still has only one synchronous subagent; parallelism comes in v0.38
```

"Delivery" here means the parent State, the parent messages, and the necessary durable boundary have all recorded it together, not just that the child model output some text.

## Core Concepts and Data Structures

### 1. The execution result and the delivery status are two axes

`outcome` answers "how did the subagent do", for example `completed`, `failed`, `timed_out`, `cancelled`, or `budget_exhausted`. `delivery_status` answers "has the parent side closed this call". The two must not be confused: even if a subagent times out, the parent model must get a failure result.

The lifecycle reads like this:

```text
created -> running -> result_ready -> committed
                         |
                         +-- outcome = completed | failed | timed_out
                                      | cancelled | budget_exhausted
```

`result_ready` means the result passed validation and can be handed to the parent side; `committed` means the matching parent `role=tool` and State facts are also committed. Only at `committed` can the parent Runtime go on to request the next model round. `DelegationRecord` stores the IDs, contract hash, status, result ID/hash, usage, and a short reason; it does not store the subagent's full history.

### 2. The budget is reserved first, then settled

The parent task's aggregate budget includes the maximum number of subagents, concurrency, LLM calls, tool calls, and tokens. In v0.37 concurrency is fixed at 1, but it still checks the remaining budget inside the State lock first and puts this run's allowed per-run limit into the reserved ledger:

```python
MAX_SUBAGENTS = 1
MAX_CONCURRENCY = 1
MAX_TOTAL_LLM_CALLS = 8
MAX_TOTAL_TOOL_CALLS = 24
MAX_TOTAL_TOKENS = 32_000
```

When the budget is insufficient, no child LLM request happens. After the subagent ends, the unused reservation is released and the actual usage is settled; when the provider gives no usage, a conservative estimate is used and marked `estimated`. If the real usage exceeds the reservation, the ledger records the real overrun, and later delegations see less remaining budget; regenerating a contract cannot reset the budget.

### 3. Cancellation is cooperative

The Manager keeps a `threading.Event` that belongs to the current parent task. When the CLI calls `cancel(task_id, reason)`, it only sets the event; it does not forcibly close an ongoing HTTP/socket. The child Runtime checks it before requesting the model, after receiving a response, before admitting a tool round, and after the result boundary.

So a request that returns quickly can become `cancelled` quickly; a blocked network request may not finish for a while. The CLI waits boundedly; if it still has not ended, it keeps the old task and reports the delegation ID and the reason. Cancellation is not proof of success, and an unfinished task cannot be written as a clean safe point.

## Key Flow

The normal path:

```text
parent assistant: delegate_task
  -> contract / phase / permission checks
  -> reserve the aggregate budget inside the State lock, record created
  -> mark running, enter the child Runtime
  -> the subagent runs and checks cancellation/budget
  -> produce and validate the SubagentResult
  -> mark result_ready, settle the actual usage
  -> the parent Context appends exactly one role=tool
  -> mark committed
  -> only then can the parent Runtime request the next LLM round
```

Failures must also close the protocol:

```text
child model exception / timeout / cancel / budget_exhausted
  -> produce a single, bounded failure SubagentResult
  -> result_ready(outcome=a failure kind)
  -> the parent role=tool is still committed
  -> committed
```

If a task boundary command arrives during a child call, the CLI first cancels and waits boundedly; when the wait fails, it skips the clean save and the task switch, and the old State is kept.

## Run and Observe

After configuring a model, start the CLI with Bash/zsh:

```bash
PYTHONPATH=src python -m mini_agent
```

The parent state summary should show the remaining budget, active delegations, and recently committed delegations, but not the subagent's full history. On a normal finish, the parent model receives a structured result with `outcome=completed`; on a timeout, cancellation, or insufficient budget, it still receives the matching failure-kind JSON. When you enter `/new <task>` or `/reset`, first observe the cancellation and bounded wait, then whether the task can switch safely; when it has not finished, the old task should not be cleared. After the command-line first task is handled, the CLI still enters the interactive loop.

## Implementation Breakdown

`AgentState.reserve_delegation()`, `delegation_result_ready()`, and `commit_delegation()` complete budget and state transitions inside the same State lock. `DelegationManager` keeps the current parent task ID, the cancellation event, reservation records, and completion events, instead of only a boolean `_active`. `SubagentRunner` is still only responsible for assembling the independent child State, Context, tool view, and policy, then entering the single `AgentRuntime.run()` of Lesson 35.

The parent Runtime advances the delegation record after appending `role=tool`; the parent completion decision checks whether any delegations are still uncommitted. Safe points refuse active or `result_ready` delegations, and the usage of committed records is saved and restored with State; no new budget is created on resume.

## Why This Design

Separating `outcome` from `delivery_status` both tells the parent model that "the investigation failed" and guarantees that every assistant tool call has a matching tool result. It also lets repeated commits be idempotent, without producing a second message.

The reservation ledger lets budget rejection happen before the first child LLM request; settling by actual usage keeps unused budget from being swallowed permanently. The cost is that a provider's real usage is often known only after the response, and an overrun request that already happened cannot be undone; only later requests can be stopped.

Cooperative cancellation keeps the standard-library HTTP client's boundary simple and avoids being unable to tell what actually happened to a provider request after forcibly closing a socket. The cost is that network calls cannot always stop immediately, so task boundaries must wait boundedly and keep the old task.

## Design Boundaries

- v0.37 has only one synchronous, single-level, read-only subagent, `max_concurrency=1`.
- The subagent cannot write files, run shell, manage processes, change the parent plan, change the generation, provide authoritative verification, or decide parent task completion.
- Cancellation takes effect only at synchronous checkpoints; it does not forcibly kill an ongoing HTTP/socket.
- Safe points refuse active or `result_ready` delegations; committed usage is saved with State and does not reset the budget.
- This version does not automatically rerun unfinished subagents, nor does it persist raw child results that can be recovered across processes; that is left to Lesson 39.
- Lesson 38 adds parallel subagents and delivery in model order.

## Version Features, Next Lesson, and Code Index

This lesson completes the single-subagent lifecycle, cooperative cancellation, the parent task aggregate budget, usage settlement, the state summary, and the safe point boundary. The next lesson lets several read-only subagents run at the same time while still guaranteeing that parent `role=tool` results are committed in the model's call order.

Core source:

- [`src/mini_agent/state.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.37/src/mini_agent/state.py)
- [`src/mini_agent/delegation.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.37/src/mini_agent/delegation.py)
- [`src/mini_agent/runtime.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.37/src/mini_agent/runtime.py)
- [`src/mini_agent/context.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.37/src/mini_agent/context.py)
- [`src/mini_agent/session.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.37/src/mini_agent/session.py)

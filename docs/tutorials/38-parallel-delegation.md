# Lesson 38: Bounded parallel read-only subagents

Previous: [Adding lifecycles and a total budget to subagents](37-subagent-lifecycle-budget.md) · [Tutorial overview](README.md) · Next: [Durable delegation delivery](39-durable-delegation.md)

> Code snapshot: `v0.38` · Adjacent diff: `v0.37..v0.38` · Shell: Bash/zsh

> Requirements: Python 3.10+. This lesson only schedules read-only subagents in parallel; it does not change the parent Agent's boundaries for changes, permissions, and verification.

## Lesson Goals

Lesson 37 can record budgets and cancellation, but only one subagent can run at a time. If three investigations are independent of each other, the parent task has to wait for A to finish, then B, then C.

This lesson lets the parent model propose several `delegate_task` calls in one assistant round. The Scheduler starts at most the configured number of subagents at the same time; they can finish out of order, but the parent model still receives the tool results in the original call order A, B, C. After reading, you should be able to explain:

- Why only a "pure delegation round" may take the parallel path;
- Why budget quota and run slots are two different limits;
- Why even if B finishes first, it cannot be written into the parent Context ahead of A;
- Why parallel workers cannot change the parent State directly.

## Problems in the Previous Version

In v0.37, `max_concurrency` is fixed at 1. It protects the lifecycle and the ledger, but it forces independent investigations into a single line, so the waiting time is close to the sum of all child task durations.

This version changes only "when subagents run", not "who owns the task". The parent Agent still exclusively owns workspace changes, permission requests, the main plan, the generation, authoritative verification, and the completion decision; subagents are still depth=1 read-only instances.

## Prerequisites and Version Checkout

You need Lesson 37, basic Python, Bash/zsh, and Git. First look at the adjacent diff, then enter this lesson's snapshot:

```bash
git checkout v0.37
git diff --stat v0.37..v0.38
git diff v0.37..v0.38 -- src/mini_agent/delegation.py src/mini_agent/runtime.py src/mini_agent/state.py src/mini_agent/agent.py
git checkout v0.38
```

## New and Changed Files

This version unfolds along "batch admission → bounded execution → ordered delivery":

| File | Purpose |
|---|---|
| [`src/mini_agent/delegation.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.38/src/mini_agent/delegation.py) | Defines `DelegationScheduler`, batch contract freezing, slot scheduling, and cancellation. |
| [`src/mini_agent/runtime.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.38/src/mini_agent/runtime.py) | Recognizes pure delegation rounds, collects results, and commits them by index. |
| [`src/mini_agent/state.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.38/src/mini_agent/state.py) | Reserves budget in batch and settles actual usage inside the lock. |
| [`src/mini_agent/agent.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.38/src/mini_agent/agent.py) | Allows several delegations in the same round and rejects mixing them with other tools. |
| [`src/mini_agent/tools/base.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.38/src/mini_agent/tools/base.py) | Lets admitted delegation results follow the unified tool result boundary. |

## Version Change Map

Legend: `[old]` already in v0.37, `[+]` new in v0.38, `[~]` changed in v0.38, `[C]` main consumer, `[B]` boundary of this lesson.

v0.37 has only one run slot:

```text
[old][C] parent assistant: delegate_task A
      -> [old] single-task Manager
      -> [old] SubagentRunner A
      -> [old] parent role=tool A
      -> [old] next parent LLM request
      [B] max_concurrency=1
```

v0.38 adds batch scheduling for a pure delegation round:

```text
[C] parent assistant: delegate_task A, B, C
      -> [~] admission one by one
      -> [~] batch quota reservation inside the State lock
      -> [+] Scheduler(max_concurrency=2)
           ├─ A worker runs
           ├─ B worker runs -> finishes
           └─ slot released -> start C worker
      -> [+] result buffer: B and C can finish first
      -> [~] the parent thread waits for the contiguous A, then commits A, B, C in order
      -> [C] next parent LLM request

[B] subagents are still read-only, depth=1; Lesson 39 saves the raw results so they can be recovered across processes
```

For example, if B finishes before A, the scheduler can start C right away, but the parent history must still be A, B, C. Execution completion and parent-side delivery are two different moments.

## Core Concepts and Data Structures

### 1. Only pure delegation rounds can run in parallel

Parallel scheduling is suited only to several independent read-only investigations. If the same assistant round contains `delegate_task` together with file writes, shell, plans, or other ordinary tools, the system cannot split them up and run them safely. So `ParentRuntimePolicy.prepare_tool_round()` enters the parallel path only when "every call in this round is `delegate_task`"; in a mixed round, every call gets `delegation_batch_gate`, and no child model is started.

This does not turn the delegation tool into a privileged entry. Each delegation still passes schema, phase, permission, and durable admission first; the parallel path only decides how they are scheduled.

### 2. Budget quota and run slots are two different things

The budget answers "how much the parent task may consume in total", and slots answer "how many may run at the same time right now". For example:

```python
MAX_SUBAGENTS = 3
MAX_CONCURRENCY = 2
MAX_TOTAL_LLM_CALLS = 24
MAX_TOTAL_TOOL_CALLS = 72
MAX_TOTAL_TOKENS = 96_000
```

While A and B run, C can queue, but the budget for all three contracts should be checked and reserved together before starting. A queued C does not take a run slot, but it already uses the parent task's subagent count and reserved quota. After a task finishes, the unused reservation is released and the actual usage is settled; if the provider reports more tokens than reserved, the ledger records the real overrun, and later tasks see a smaller balance.

### 3. Workers execute; the parent thread commits

Each worker has its own SubagentRunner, State, Context, model binding, HTTP connection, stream buffer, and usage counter. A worker only returns a `SubagentResult`; it does not change the parent State or parent Context directly.

The scheduler keeps out-of-order results in a result buffer addressed by index. After B finishes, it can release its slot and start C, but only when the contiguous earlier A also has a result does the parent thread advance A, B, C to `result_ready`, `role=tool`, and `committed`.

### 4. The durable boundary still finishes in model order

With `/save` on, the order is still:

```text
start_round
  -> admission and handler_admitted for each of A/B/C
  -> batch reservation and start of a bounded number of workers
  -> collect results, wait for the contiguous earlier indexes
  -> commit State + role=tool + tool boundary for A, B, C in order
  -> complete_round
  -> next parent LLM request
```

If any durable commit fails, it blocks the later flow that has not yet finished safely and the next parent LLM request. Parallelism is not allowed to produce a half round where "B is written but A is not yet".

## Key Flow

The normal path can be condensed to:

```text
the parent model submits A, B, C
  -> permission, scope, and budget checks for all three contracts together
  -> start A and B at the same time; C waits for a slot
  -> B finishes, start C
  -> A finishes
  -> the parent side delivers three single tool results in the order A, B, C
  -> request the parent LLM after the whole round is committed
```

On a failure path, one subagent can get `failed`, `timed_out`, `cancelled`, or `budget_exhausted`; that failure result still occupies its position in the parent round, and other completed results are not wiped out because of it. When the parent task is cancelled, the scheduler asks all active workers to stop and keeps the registrations that did not finish in time.

## Run and Observe

After configuring a model, start the CLI with Bash/zsh:

```bash
PYTHONPATH=src python -m mini_agent
```

When the parent model proposes several independent `delegate_task` calls at once, observe that the number of active ones never exceeds `max_concurrency`; a B that finishes earlier does not appear in the parent Context early, and the parent results still enter in the model's original order. If ordinary tools are mixed in, you should see a batch rejection rather than a partial start. After the command-line first task is handled, the CLI still enters the interactive loop.

## Implementation Breakdown

`reserve_delegation_batch()` completes the batch budget check under one State lock, preventing several workers from over-issuing at the same time. `DelegationScheduler` maintains a bounded set of threads, a queue of tasks waiting to start, and a result table by index; workers only execute, and the parent thread commits. Each time the parent thread delivers contiguous results, it still follows the lifecycle and durable boundary of Lesson 37.

So "parallel" happens only in the subagents' internal execution stage. The visible order of the parent Context, State, tool results, and session is still decided by the model's call order.

## Why This Design

Throwing all `delegate_task` calls into the ordinary tool thread pool would confuse ordinary handler concurrency with the subagent lifecycle: subagents also need an independent Runtime, a frozen model binding, the parent aggregate budget, cancellation, and the result contract. A dedicated Scheduler can manage these resource boundaries in one place.

Separating budget from slots lets C queue while still knowing before starting whether A, B, and C are affordable as a whole. The cost is that the waiting queue also uses the parent task's reserved quota.

Committing by index on the parent side may make an already finished B wait for A, but that is the price of keeping the model message order and the durable atomic finish. This way thread scheduling never changes the conversation the next model request sees.

## Design Boundaries

- Only pure delegation rounds enter the parallel path; when delegation is mixed with ordinary tools, the whole round is rejected.
- Subagents still cannot write files, run shell, manage processes, delegate again, or decide parent task completion.
- Each worker uses its own State, Context, connection, stream buffer, and usage; no mutable runtime data is shared.
- Results may be produced out of order, but the parent `role=tool`, State, and durable boundary must be committed in model order.
- v0.38 does not save the full child Context and does not recover in-memory results across processes; Lesson 39 persists the raw `result_ready` text.

## Version Features, Next Lesson, and Code Index

This lesson completes bounded parallelism, batch budget reservation, independent workers, delivery of partial failures, cancellation of all, and ordered commits on the parent side. The next lesson solves a new recovery gap: what if the process crashes after a subagent result is produced but before the parent result is delivered?

Core source:

- [`src/mini_agent/delegation.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.38/src/mini_agent/delegation.py)
- [`src/mini_agent/runtime.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.38/src/mini_agent/runtime.py)
- [`src/mini_agent/state.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.38/src/mini_agent/state.py)
- [`src/mini_agent/agent.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.38/src/mini_agent/agent.py)
- [`src/mini_agent/tools/base.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.38/src/mini_agent/tools/base.py)

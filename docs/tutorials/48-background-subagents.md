# Lesson 48: Letting subagents investigate in the background

Previous: [Giving subagents roles](47-agent-profiles.md) · [Tutorial overview](README.md) · Next: [Resuming and continuing child sessions](49-resumable-child-session.md)

Code snapshot: `v0.48` · Adjacent diff: `v0.47..v0.48`

The commands in this lesson use Bash/zsh; code links and examples correspond to the `v0.48` source snapshot.

## Lesson Goals

In the previous lesson, `delegate_task` waits until the subagent hands back its report. Even if the parent Agent has other work, it cannot continue while waiting. This lesson adds background investigation: the parent Agent first gets an "accepted" receipt, can then keep working, and later queries the subagent's status and collects the report.

"Background" here means the investigation runs in another worker thread inside the current command-line program. It is not an independent service that keeps working after the program exits. The one working on the user's task is the parent Agent; the one doing read-only investigation is the subagent.

After reading, you should be able to tell a "start receipt" from an "investigation report", and understand why the system starts subagents only after the whole round's start records are committed safely, and why active tasks or uncollected reports prevent saving and finishing the parent task.

## Prerequisites and Version Checkout

You only need basic Python, a terminal, and Git. Read Lesson 47 first to learn how roles limit subagents; Lessons 34–39 cover delegation, concurrency, and durable tool results for further reading.

Check the diff between adjacent versions, then switch to this lesson's snapshot:

```bash
git checkout v0.47
git diff --stat v0.47..v0.48
git diff v0.47..v0.48 -- src/mini_agent/delegation.py src/mini_agent/runtime.py
git checkout v0.48
```

After reading, use `git checkout -` to return to the branch you were on before switching.

## Problems in the Previous Version

Delegation in v0.47 is synchronous: after the parent Agent issues `delegate_task`, it must wait for the subagent to finish before the next round. Background tasks let the parent Agent handle other things while the investigation runs.

But the start time cannot be moved earlier at will. If the subagent started in its thread immediately, the parent program might exit before it wrote the fact "the start was accepted" into the save file. On recovery, it would be impossible to tell whether it started, and it might be started twice by mistake.

So this version requires: the parent thread first commits all start receipts of this round in order; only after the whole round is written successfully does it actually start the subagents.

## New and Changed Files

| File | Change | What you can see here |
|---|---|---|
| [tools/delegation.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.48/src/mini_agent/tools/delegation.py) and [tools/__init__.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.48/src/mini_agent/tools/__init__.py) | Changed | How the four background tools are registered for the parent Agent. |
| [delegation.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.48/src/mini_agent/delegation.py) | Changed | How worker threads, queuing, cancellation, concurrency, and result collection are managed. |
| [runtime.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.48/src/mini_agent/runtime.py) and [agent.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.48/src/mini_agent/agent.py) | Changed | Why starting waits for the whole round to be saved, and when the parent task can finish. |
| [state.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.48/src/mini_agent/state.py) and [trace.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.48/src/mini_agent/trace.py) | Changed | How the parent task records start, completion, collection, or interruption. |
| [session.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.48/src/mini_agent/session.py) and [resume.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.48/src/mini_agent/resume.py) | Changed | How start facts are saved, and how old work is recorded as interrupted after the program restarts. |
| [__main__.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.48/src/mini_agent/__main__.py) and the input/output modules | Changed | How notifications are shown while waiting for user input, and how tasks are cleaned up on exit. |

`git diff --stat v0.47..v0.48` shows that this change spans tools, the run loop, saving, and the command-line exit flow; it is not just a few more tools.

## Version Change Map

The parent Agent of v0.47 must wait for the synchronous delegation to return a report; this is that version's basic path:

```text
[old] parent Agent
  → delegate_task
  → start a read-only subagent
  → wait for the full report
  → hand the report to the parent Agent
```

v0.48 splits the start confirmation and report collection into two operations. `schema 3` is a data format this project uses when saving sessions; this version uses it to record each start receipt and whether the whole round committed successfully.

```text
[old] synchronous delegation of the parent Agent
  ↓
[+] spawn_subagent (returns only a start receipt)
  → [~] the parent Agent adds background task management
  → [C] tool permission and task phase checks
  → save start receipts in order
  → [B] whole-round save fails: no subagent is started
  → whole-round save succeeds: start workers in the background
       ├─ the parent Agent keeps working on other things
       └─ the subagent finishes → the parent thread collects the result
                                    → query status → collect the report explicitly
```

Legend: `[old]` already in v0.47, `[+]` new in v0.48, `[~]` changed, `[C]` main validator or user, `[B]` boundary of this version. A `worker` is the worker thread that runs a subagent task. Arrows show calls, control, or data flow. Differences in completion order do not change the order of tool results in the parent Agent.

## Core Concepts and Data Structures

### 1. Start, query, collect, and cancel are four operations

The background subagent tools exist only on the parent Agent's side. Each does one thing:

| Tool | Purpose | Contains the investigation report? |
|---|---|---|
| `spawn_subagent` | Start a named read-only investigation | No, it only reports acceptance and the task ID |
| `get_subagent_status` | Check the task's current status | No, it only returns a bounded status and the result ID when available |
| `get_subagent_result` | Collect a finished result | Yes |
| `cancel_subagent` | Ask the subagent to stop | No |

`child_session_id` is this child task's number within the parent task; `result_id` identifies the report after completion. Status notifications never push the report body into the parent Agent's conversation automatically. For the parent Agent to read the findings, it must call `get_subagent_result` explicitly. Collecting again returns the same report, and the parent state settles it only once.

A start must specify a role introduced in Lesson 47 and declare that its purpose is read-only investigation. Background tasks cannot be started in the plan-awaiting-approval, verification, diagnosis, or crash recovery phases; a subagent does not gain extra abilities just because it runs in the background.

Below are only the two fields of a start call relevant to this lesson; a real call also provides the investigation goal, scope, and budget:

```json
{
  "agent_profile": "reviewer",
  "purpose": "investigation"
}
```

### 2. Subagents start running only after the whole round is saved

A "model round" is all the tool calls the model issues in one reply. A round with background starts can start one or more child tasks, but it cannot mix in other tool calls such as status queries or file reads. The parent thread handles each start request in the order the model gave and writes the matching receipt, then saves the whole round's boundary.

The key order can be simplified to:

```python
if self.session_boundary is not None:
    self.session_boundary.complete_round(state, context)
manager.commit_background_spawn_round()
manager.activate_background_tasks()
```

The first step commits this round's tool results and state as one complete boundary; only the last two steps let the background manager start worker threads. If saving a receipt or the whole-round boundary fails, the flow never reaches the start step. This keeps the start receipts the model already received consistent with the child tasks that actually start using resources.

### 3. Child threads only report results; the parent thread updates the parent task

Each subagent has its own task state, conversation, and read-only tool scope. After a worker thread finishes, it puts a bounded result into a thread-safe queue. The parent thread later reads the queue, updates the parent task record, settles the budget, and shows a short notification. The parent State (current task facts and progress), conversation history, and session file are never changed by several worker threads at the same time.

Synchronous and background subagents share a budget: by default each parent task can create at most 3 subagents, with at most 2 running at the same time; local configuration can set a smaller concurrency limit. Queued tasks also use reserved quota. A `token` is the unit models use to measure text and, like the number of model calls and tool calls, is limited by the budget. Failures, timeouts, and cancellations all produce results that can be queried.

Cancellation is cooperative: after the parent Agent issues a cancel request, a model request that is waiting may have to return first; the subagent sees the request at its next safety checkpoint and then stops. The system does not kill threads forcibly.

### 4. Active or uncollected tasks cannot count as done

A safe point is a session snapshot whose state is complete and has no unhandled background tasks. An active thread itself cannot be saved as a resumable task, so a manual `/save` lists the active or uncollected child tasks and refuses to save; automatic saving waits for the tasks to finish.

When the command-line interface exits, input ends, or `/new` or `/reset` is entered, it first requests cancellation and waits for a bounded time. If a thread cannot finish in time, the interface keeps the old task and reports the related IDs. Even if the parent model has already output ordinary closing text, as long as a child task is still running or its result has not been collected, the parent task does not enter `done`. A subagent report also never proves automatically that the parent task's changes have passed verification.

## Why This Design

Separating "start" from "read the result" lets the parent Agent start an investigation first and decide later when to look. It also keeps one simple rule of the tool protocol: each tool call has exactly one matching result.

The parent thread exclusively owns parent state and session writes, so two threads never change the same part of the conversation or save file at the same time. The whole-round commit gate ensures there is never an ambiguous state where "the save file says it started, but the worker thread actually did not".

The cost is that background tasks run only within the current program process. After an exit, the original worker threads cannot be taken over; if the program exits before a result is collected, recovery marks work that cannot be confirmed as interrupted instead of rerunning it automatically.

## Design Boundaries

If the parent program exits after the start round is fully committed but before the result is saved safely, the recovery flow records the task as `interrupted`, does not restart the old thread or forge a report, and settles the unknown usage cautiously at the reserved limit. The user must still handle the crash recovery issues one by one.

If the start receipts were saved one by one but the whole round was not committed successfully, the subagents never started, and the recovery flow closes the budget reservations of tasks that never started. A result that finished but was not yet collected cannot be saved as a resumable child session; cleanup keeps it until the parent session commits successfully.

A subagent is always a read-only investigator: it cannot write files, run shell, use MCP (the protocol that connects external tool services to the Agent), delegate further, or verify on behalf of the parent Agent. Continuing the same subagent conversation in another command-line process needs the session snapshot capability of Lesson 49.

## Key Flow

```text
the parent model proposes a round of background starts
  → check arguments, role, task phase, and permission
  → reserve the subagent count and model/tool/token budget
  → commit each start receipt in call order
  → after the whole round is saved, the background task manager starts the runnable worker threads
  → worker threads put results into the completion queue
  → the parent thread collects results and shows ID/status notifications
  → the parent model queries status and collects the report explicitly

failure paths:
  any start receipt or the whole-round save fails → no worker starts for this round
  the old process exits before the result is saved → mark interrupted, no automatic rerun
  a result is still running or not yet collected → the parent task cannot enter done
```

## Run and Observe

After configuring a local model, start a task that explicitly asks for a background subagent:

```bash
PYTHONPATH=src python -m mini_agent "Start a read-only investigation with the reviewer role to check tool registration and argument validation in src/mini_agent; while it runs, keep looking at the parent-side call path, then query its status and collect the report"
```

Observe whether a start receipt with a `child_session_id` appears first, after which the parent Agent keeps working. When the investigation ends, the terminal notification shows only the task ID, the status, and the available `result_id`; the report body should enter the conversation only after the parent model calls `get_subagent_result`.

If the parent Agent tries to finish directly while a task is still active or its result has not been collected, the command-line interface reports the unfinished tasks, and the parent task stays active. This helps distinguish "the subagent started" from "the subagent report was handed back".

## Implementation Breakdown

The background task manager prepares and manages child tasks but starts no threads before the whole round is committed. The parent Runtime commits the start results and the `schema 3` boundary in call order, then tells the manager to release the reserved tasks.

Each worker thread reuses the project's single Agent run loop (which arranges model requests, tool calls, and results), but writes only to its own result queue. In the implementation, the worker thread puts its completion information into the queue:

```python
self._background_events.put((selected.task.subagent_id, result))
```

The parent-side run loop collects results at safe boundaries, checks identities, settles usage, and notifies the model. When collecting a report, the parent state also verifies the child task ID, delegation ID, result ID, and result digest.

On recovery, the recovery module checks the committed background start records. It reads the structured task records in the parent session; it does not read child conversations and does not try to restore Python worker threads.

## Version Features, Next Lesson, and Code Index

This version keeps the synchronous `delegate_task` and adds four background tools. The parent Agent can keep working while a subagent investigates, but must query and collect the result explicitly; a start confirmation really starts the child task only after the whole round is committed safely.

The next lesson lets a finished and collected investigation take follow-up questions after saving. v0.48 still does not save worker threads or subagent conversations to disk.

Code index pinned at v0.48: [background task management](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.48/src/mini_agent/delegation.py), [start commit order](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.48/src/mini_agent/runtime.py), [parent task phase policy](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.48/src/mini_agent/agent.py), [lifecycle records](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.48/src/mini_agent/state.py), [session saving and recovery](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.48/src/mini_agent/session.py).

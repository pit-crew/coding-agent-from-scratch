# Lesson 28: Controlling background processes

Previous: [Observing background processes](27-process-observation.md) · [Tutorial overview](README.md) · Next: extended as needed

Code snapshot: `v0.28` · Adjacent diff: `v0.27..v0.28` · Shell for examples: Bash/zsh

The `v0.28` tag is created manually by the repository maintainer. Before the tag exists, you can read and run this lesson on the current branch; pinned source links and cross-version diffs must be checked after the tag is created. After the command-line first task finishes, the CLI still enters the interactive loop.

## Lesson Goals

The Agent in the previous lesson can already detect that a background service exited, but it still cannot end it actively. For example, a local server has finished its checks, and keeping it running only holds a port; or the model finds a wrong start argument and must stop the old process before it can retry. Task boundary cleanup does handle processes on `/new`, `/reset`, and CLI exit, but that is not a control entry the model can use during a task.

This lesson adds two permission-protected tools: `terminate_process` requests normal termination, and `kill_process` forces it. After reading, you should be able to tell apart several facts that are often confused:

- "The signal was sent" only means the control request was delivered, not that the process has exited.
- "Exited" can be committed only after the direct process, the managed process group, and the output pipes have all reached a stable boundary.
- Unknown or cross-task IDs must be rejected before the permission prompt; authorization for one tool cannot expand into authorization to control arbitrary PIDs.
- Control actions and exit events invalidate old verification; after ending a process, verification must still be done independently in the new generation.
- `still_running`, `already_exited`, and `control_failed` are different results with different next steps.

## Problems in the Previous Version

`v0.27` can observe status and output with `get_process`, `read_process`, and `wait_process`, but all those tools are read-only. The Agent sees:

```text
process_id=proc-1
status=running
stdout contains ready
```

It still has no way to end this service within the current task. Treating "SIGTERM was sent" as success directly causes a more serious problem: the program may ignore normal termination, the outer shell may have exited while descendants are still running, and the descendants may still hold the stdout/stderr pipes. If State immediately wrote "ended" at that point, the Agent might go on to finish the task while leaving behind a process that is still changing the environment. `v0.28` solves exactly this gap between "requesting control" and "confirming exit".

## Prerequisites and Version Checkout

You need basic Python, Bash/zsh, and the `process_id`, stable exit, `awaiting_process`, and generation from the previous lesson. The diff below locates where this version actually inserts code: tool registration and permissions in the executor, signals and waiting in the Manager, final events in State, and causal checks in Trace.

```bash
git checkout v0.27
git diff --stat v0.27..v0.28
git diff v0.27..v0.28 -- src/mini_agent/processes.py src/mini_agent/tools/process.py src/mini_agent/tools/base.py src/mini_agent/permission.py src/mini_agent/state.py src/mini_agent/trace.py
git checkout v0.28
```

Without the `v0.28` tag, stay on the current development branch to run this lesson's commands; check the pinned-version diff above and the source links at the end after the tag is created.

## New and Changed Files

Separate the responsibilities first, so it is clear later that "who sends the signal" and "who writes the lifecycle fact" are not the same thing:

| File | Role in this lesson |
| --- | --- |
| `src/mini_agent/processes.py` | Sends signals only to processes or managed process groups the Manager has registered, and confirms the exit within a bounded time. |
| `src/mini_agent/tools/process.py` | Releases `terminate_process` and `kill_process`, whose only argument is a task-scoped `process_id`. |
| `src/mini_agent/tools/base.py`, `permission.py` | Complete argument, task ownership, planning/repair phase, and permission checks before running the handler, and record the execution attempt. |
| `src/mini_agent/state.py` | Links a confirmed active exit to the start attempt, the control attempt, and the successor generation. |
| `src/mini_agent/trace.py` | Validates, read-only, whether the references between start, control, exit, and verification are complete. |
| `src/mini_agent/prompt.py`, `docs/operation/manual.md` | Tell the model what control results mean, and that independent verification is still required after an exit. |

## Version Change Map

Legend: `[old]` already in the previous version, `[+]` new in this version, `[~]` changed in this version, `[C]` main consumer, `[B]` boundary of this version.

The previous version's main chain was observation; control could only happen internally in task boundary cleanup:

```text
[old] start_process
       -> [C] ProcessManager registers the current task's processes and process groups
       -> get/read/list/wait_process
       -> State updates status, output positions, and natural exit facts
[old] /new /reset / EOF / exit
       -> internal cleanup(task_id)
[B] the model cannot actively end the current task's background processes
```

This version inserts control between the executor and the Manager, and hands "confirming the exit" back to the foreground State:

```text
[+] terminate_process / kill_process(process_id)
       -> [~] ToolExecutor
           -> first check whether the current task_id owns process_id
           +-> invalid ID: unknown_process_id, no permission prompt, no generation reserved
           -> planning_gate / repair_gate
           +-> current phase does not allow it: rejected, no signal sent
           -> PermissionGate
           +-> not approved: permission_denied, no signal sent
           -> [C] ProcessManager.control()
                 -> POSIX: send TERM or KILL to the managed process group
                 -> bounded wait for a stable exit
                 +-> still_running: no final exit event written
                 +-> confirmed: return terminated or killed
       -> one role=tool fed back per call
       -> [~] foreground State.sync_processes()
             -> a single final ProcessEvent
             -> successor generation
             -> verification_required
[C] Trace checks, read-only, the references of the start attempt, control attempt, and exit event
[B] no arbitrary PIDs; no cross-task control, PTY, or stdin writes
```

There are two "confirmations" in this diagram: the Manager confirms that the operating system resources have reached the stable exit boundary, and State confirms and records one replayable lifecycle fact. The former cannot replace the latter, and the latter cannot guess from tool result text that the former has happened.

## Key Flow: Termination Is a Process

When the user says "stop the service", the operating system involves at least four steps:

```text
request    -> send TERM or KILL
observe    -> wait for the direct child and the managed process group to change
finish     -> wait for the stdout/stderr pipes and collector threads to end
record     -> State appends one final ProcessEvent
```

If the program responds to TERM and exits on its own, `terminate_process` can return `terminated`. If the program ignores TERM and is still running when the default grace period ends, the tool returns `still_running`; there is no exit event at that point, the process still prevents the task from finishing, and the Agent can keep observing or escalate to `kill_process`. If the process had already exited naturally when the call was made, the tool returns `already_exited`, and foreground sync keeps the natural `exited` or `failed` fact instead of rewriting it as a controlled exit.

`kill_process` follows the same flow but uses the forced termination signal. It is not "a faster terminate"; it is a separate control action that needs its own authorization and has a different reason. Both tools accept only:

```json
{"process_id":"proc-1"}
```

The PID returned is only for diagnostic display and cannot be copied out and used as a control argument.

## Core Concept 1: Confirm Ownership First, Then Ask for Permission

### Why the order matters

Controlling a process is an action with side effects. If the permission prompt came before the task ownership check, there would be a bad experience: the model could hold an ID from another task or an expired task and still make the user see a prompt "allow ending it?". More importantly, the user's choice must not become a credential for accessing another task's resources.

So the executor uses this order:

```text
argument validation
  -> is process_id registered by the current task_id?
  -> does the current planning/repair phase allow control?
  -> PermissionGate checks the separate rules for terminate or kill
  -> reserve a possible-effect attempt and generation
  -> the handler checks ownership again and sends the signal
```

There are two ownership checks: the executor checks once before authorization, and the handler checks again after entering the Manager. The second check covers races between the check and the actual execution, such as a task switch or a change in resource state.

This produces three results that are easy to compare:

| Case | Tool result | Signal sent? | Generation reserved? |
| --- | --- | --- | --- |
| Unknown, expired, or cross-task ID | `unknown_process_id` | No | No |
| Valid ID, but the user denies permission | `permission_denied` | No | No |
| Valid ID and approved | Goes to `terminated`, `killed`, `still_running`, or a control error | Possibly | Yes, handled as a possible effect |

A "rejection" still feeds back its matching `role=tool` result to the model, but it creates no fact that a control action happened. A complete tool call protocol and a side effect that did not happen can both be true at the same time.

### Planning and repair phases still apply

In the `exploring` (read-only investigation) phase, control tools are rejected by the planning gate before permissions; approving a plan does not automatically allow control either. If the task is already in `diagnosis_required` or a strict `verification_required`, direct control is also rejected by the repair gate. If stopping a process is part of a repair, a legal causal entry must be created through the existing `recover` or `request_replan`; the control tools cannot be used to skip the Repair Loop (the diagnosis, recovery, and verification loop after a failure).

## Core Concept 2: Sending a Signal Is Not Confirming an Exit

### Normal termination and forced kill

`terminate_process` gives the process one chance to finish cleanly. On POSIX systems, the Manager sends TERM to the managed process group created at start; this covers the outer shell and its children that are still in the group. `kill_process` uses the forced signal and suits cases where the process ignores TERM or cannot finish cleanly. The tool does not treat "the system call did not raise" as completion, because that only means the request was sent.

The Manager's confirmation must also consider two resource boundaries:

- On POSIX, the managed process group must be gone. When the outer shell exits first while a background child is still alive, success cannot be returned.
- The stdout and stderr collector threads must reach EOF before the pipes can be closed safely. While someone still holds a pipe, closing it may block or lose the tail of the output.

The default grace period is 2 seconds. It is a bounded wait, not a promise that the program will end within 2 seconds; if it is still running when the time is up, `still_running` is returned and the next step is left to the Agent or the user.

## Implementation Breakdown

Below, "sending the signal", "confirming a stable exit", and "committing the State fact" are separated into three layers. The Manager is responsible only for the first two; the foreground Runtime handles the last one at a later sync point.

### The key control order in the Manager

The core control logic below comes from `v0.28`, with error messages and platform details omitted. Focus on the order: first recognize a process that already exited, then send the signal; after sending, confirm in a loop; when time is up, only report that it is still running.

```python
fact = managed.refresh()
if fact.status != "running":
    return {"process_id": process_id, "status": "already_exited",
            "exit_code": fact.exit_code}

sent, reason = managed._signal_group(signal_to_send)
if not sent:
    return {"process_id": process_id, "status": "error",
            "error_kind": "control_failed"}

while True:
    fact = managed.refresh()
    if fact.status != "running":
        return {"process_id": process_id,
                "status": "killed" if kill else "terminated",
                "exit_code": fact.exit_code}
    if time.monotonic() >= deadline:
        return {"process_id": process_id, "status": "still_running"}
```

The conditional expression in the code shows that the two tools share one confirmation path; the real implementation returns the matching string based on the `kill` argument. This return value is a tool protocol result, not an event State generates automatically.

### How to interpret the results

| Status | Real meaning | Next step |
| --- | --- | --- |
| `terminated` | After the normal termination request, the exit boundary is confirmed | Sync State, read the needed tail output, then verify again. |
| `killed` | After the forced kill, the exit boundary is confirmed | Sync State, explain the forced kill, then verify again. |
| `still_running` | This wait timed out, and the process is not yet confirmed to have exited | Keep the active process; keep observing or call `kill_process`. |
| `already_exited` | It had exited naturally before control started | Sync the natural exit event and diagnose by exit code. |
| `error/control_failed` | The signal was not sent successfully | No final exit event; handle the control error. |

The standard library control path on Windows can only control the direct child and cannot prove that an arbitrary process tree derived from a shell has ended. The result carries this limitation; "the direct process exited" on Windows must not be interpreted as all descendants being gone.

## Core Concept 3: Exit Events and Tool Results Have Different Responsibilities

### Why the tool result cannot replace the ProcessEvent

A tool result only answers what this one call returned; a `ProcessEvent` is a lifecycle fact appended in State that answers "how this process finally ended, and which start and which control caused it". One control call still matches only one `role=tool` message; the exit event is a separate state record and must not pose as a second tool reply.

After the exit is confirmed, foreground sync connects the information:

```text
+------------------+       +----------------------+       +----------------------------+
| start_process    | ----> | ProcessEvent         | ----> | next generation            |
| start attempt    |       | terminated / killed  |       | verification must be redone|
+------------------+       | caused_by_control    |
             ^              | attempt_id           |
             |              +----------------------+
             |
      terminate/kill attempt
```

A controlled exit event carries at least:

- `start_attempt_id`: which `start_process` created the process.
- `caused_by_control_attempt_id`: which approved termination or forced kill triggered it.
- `generation_id`: in which verification generation the exit happened.
- `exit_code` and the cumulative stdout/stderr positions: the explainable result at exit.

One process has only one final event. If `terminate_process` returns `still_running`, no `terminated` event can be written yet; only when a later `kill_process` confirms the exit does the sync point append a `killed` event. If the process exited naturally before control, the final event stays `exited` or `failed`, and the control attempt only records "already exited at call time".

### Why Trace checks references

Trace (the task trace) is rebuilt only from the State snapshot and never accesses Popen, process groups, or pipes again. It checks whether a controlled exit event references an existing start attempt and control attempt, and whether the process ID, tool name, and generation agree. If `caused_by_control_attempt_id` is changed to a nonexistent ID, Trace should report `incomplete`; it does not guess the missing control fact.

## Why Verification Is Required Again After an Exit

Control tools are a `possible` effect (an action that may change the environment). When execution is approved, State records the execution attempt and invalidates old verification; after the exit is confirmed, the exit event opens a successor generation as well. This is because the process may have written files, created caches, held ports, or changed the external environment while it ran.

So only this chain allows the final finish:

```text
control request approved
  -> process exits stably
  -> State records a terminated/killed ProcessEvent
  -> successor generation + verification_required
  -> run_shell(purpose="verification") alone
  -> plan steps, failure repairs, and other completion conditions all met
  -> only then can it be done
```

"Returned `terminated`" only proves the background resources reached the exit boundary; it does not prove the code is correct, and it does not prove the workspace still meets the task goal.

## Protocol Behavior in a Tool Round

The model may request `terminate_process` and `get_process` in the same assistant message. Because control is an action that may have side effects, the round runs serially in the order the model gave; both calls get their matching `role=tool` results, and the next LLM round is requested only after all results are fed back. The second call, `get_process`, may see `terminated`, but not because the tool results were "merged"; it is because the first control call already finished and the real state was committed at the following sync point.

## Run and Observe

The command below is for Bash/zsh and runs this version's control-related scenarios:

```bash
PYTHONPATH=src python -m pytest -q tests/test_process_control_v028.py
```

Read the test observations like this:

| Observation | What it shows |
| --- | --- |
| A normal termination produces only one `terminated` event | Sending the signal and committing the foreground event are idempotent and distinguishable. |
| A program that ignores TERM first returns `still_running`, then KILL returns `killed` | The tool does not misreport sending a signal as an exit. |
| A process that already exited naturally returns `already_exited` and keeps its natural event | Control actions do not rewrite lifecycle facts that already happened. |
| Unknown IDs and permission denials send no signal and reserve no generation | The ownership check and the permission gate come before side effects. |
| A corrupted control reference makes Trace `incomplete` | Replay only validates existing facts and does not fill in causality for missing references. |
| After control, old verification disappears, and only new verification restores it | An exit may change the environment, so a control result cannot replace independent verification. |

You can also let the Agent start a short-lived service, and after reading its output, request `terminate_process`. First observe the status the tool returns, then check whether State gains a single final event; if the process ignores TERM, it should stay active instead of going straight to completion.

## Why This Design

`terminate` and `kill` are split into two tools so that both the model and the user can see the escalation: first give the program a chance to finish cleanly, and choose a forced kill only if it still has not exited. Each passes the PermissionGate separately, so an ordinary start authorization or one termination authorization cannot expand into control over arbitrary processes. The cost is that one control may take two tool rounds, and the user needs to understand `still_running` and decide whether to escalate.

Exit confirmation lives in the Manager and the final event commit lives in the foreground State so that both operating system races and Agent protocol boundaries are handled. The cost is that an exit fact does not enter the snapshot the moment a background thread notices a change in `poll()`; it waits for a safe point to sync. In exchange, you get idempotent events, complete `role=tool` feedback, and a read-only Trace.

Task ownership allows control only of processes registered by the current CLI and the current task, so a model-generated ID cannot turn the Agent into a system-level process manager. The cost is that externally started PIDs cannot be controlled, and old processes cannot be reconnected in a new CLI session.

## Design Boundaries

- `terminate_process` and `kill_process` accept only `process_id`s registered by the current task; the PID is only for diagnostics.
- Both tools are a `possible` effect and use separate control permissions by default; unknown IDs, phase rejections, and user denials send no signal.
- `terminated` or `killed` means the exit boundary this version confirmed; POSIX also checks the managed process group and both output pipes, and Windows states that it cannot prove an arbitrary derived tree has ended.
- `still_running` produces no final exit event and does not allow the task to finish; `control_failed` does not forge an exit fact.
- After control, independent verification must be done in the new generation; successful control is not a passing test.
- The restrictions of `exploring`, plans awaiting approval, diagnosis, and strict verification phases stay in effect; process control cannot bypass `recover` or `request_replan`.
- This version provides no stdin, PTY, cross-session reconnection, or arbitrary PID management; bounded pipe stdin is discussed in `v0.29`.

## Version Features, Next Lesson, and Code Index

This lesson lets the Agent request normal termination or a forced kill within the current task, and records "the signal was sent", "still running", and "exited stably" as different results. The next lesson discusses bounded pipe stdin: how to let a background program that is waiting for input receive a small amount of text, and why a write result likewise cannot replace a process exit and final verification.

Pinned source entries:

- [Process signals and stable exit confirmation](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.28/src/mini_agent/processes.py)
- [The control tool protocol](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.28/src/mini_agent/tools/process.py)
- [The executor's ownership and authorization order](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.28/src/mini_agent/tools/base.py)
- [State events and generations](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.28/src/mini_agent/state.py)
- [Read-only Trace validation](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.28/src/mini_agent/trace.py)

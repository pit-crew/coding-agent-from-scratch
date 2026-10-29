# Lesson 26: Background process start and task boundaries

Previous: [Plan trace replay and acceptance](25-plan-trace-evaluation.md) · [Tutorial overview](README.md) · Next: [Observing background processes](27-process-observation.md)

Code snapshot: `v0.26` · Adjacent diff: `v0.25..v0.26` · Shell for examples: Bash/zsh

The `v0.26` tag is created manually by the repository maintainer after delivery; before the tag exists, you can stay on the current branch to read and run the implementation. A command-line argument is a command-line first task, and the program still enters the interactive loop after handling it.

## Lesson Goals

The previous lesson connected one task's plan and execution facts into a read-only trace. This lesson handles a more practical runtime problem: a development server, a file watcher, or a long build may not exit for minutes, but the Agent still needs to check files, compute results, or continue its plan.

After this lesson, you should be able to explain four things: why a long command with pipes gets stuck; how `start_process` immediately returns a task-scoped ID; why a process exit invalidates old verification; and why task switches and CLI exit must first clean up the processes registered by the old task.

This version releases only the start tool. Observing logs, querying status, and active termination are left to later versions; the behavior of the synchronous `run_shell` is unchanged.

## Problems in the Previous Version

`run_shell` executes synchronously, and the Agent must wait for the subprocess to exit before it gets a result. This model suits tests, searches, and other bounded commands, but not starting a development server: while the command is still serving, the Agent can no longer enter its next tool round.

Connecting stdout and stderr directly to pipes causes another problem. When a subprocess fills a pipe, it blocks on its next write; even if the Agent never asks to read the logs, the command may stop there. A background capability must drain both streams from the moment the process is created, while limiting memory.

## Prerequisites and Version Checkout

You need basic Python, Bash/zsh, and the generation, execution attempt, verification, and read-only Trace concepts from Lesson 25. First look at the real diff between the adjacent versions, then switch to this lesson's snapshot:

```bash
git checkout v0.25
git diff --stat v0.25..v0.26
git diff v0.25..v0.26 -- src/mini_agent/state.py src/mini_agent/tools/base.py src/mini_agent/__main__.py
git checkout v0.26
```

If the `v0.26` tag does not exist locally yet, you can stay on the current development branch to run the implementation below; pinned source links and tutorial fact checks follow the snapshot after the maintainer creates the tag manually.

## New and Changed Files

The key changes in this version span resource management, tool execution, task state, and the CLI. The file table lists only the entries that help understand the main thread; check the full scope with `git diff --stat` first.

| File | Change | Purpose |
| --- | --- | --- |
| `src/mini_agent/processes.py` | Adds `ProcessManager` | Exclusively owns `Popen`, process groups, drain threads, and bounded byte rings for stdout/stderr. |
| `src/mini_agent/tools/process.py` | Adds `start_process` | Validates the command and cwd, starts a background process for the current task, and returns a bounded start result. |
| `src/mini_agent/tools/base.py`, `permission.py` | Change the executor and permission patterns | Authorize the start action separately, and hand the start metadata to State after the handler succeeds. |
| `src/mini_agent/state.py` | Adds process projections and lifecycle events | Stores task ownership, the start attempt, generation, exit facts, the waiting handoff, and verification isolation. |
| `src/mini_agent/agent.py`, `context.py`, `prompt.py` | Change the loop and context | Sync exits at safe points, prevent wrong completion, and show task and process boundaries to the model. |
| `src/mini_agent/__main__.py` | Changes the CLI lifecycle | Shows `awaiting_process`, resumes the original task, and cleans up processes on `/new`, `/reset`, exit, and exception paths. |
| `src/mini_agent/trace.py` | Changes read-only replay | Validates references between process events and exit generations; replay does not touch handles or pipes. |

## Version Change Map

Legend:

```text
[old] in previous version    [+] new in this version    [~] changed in this version
[C] main consumer            [B] boundary of this version or not its responsibility
```

The synchronous entry of the previous version waits for the command to finish, then writes one result into history:

```text
[old] agent_loop -> ToolExecutor -> PermissionGate -> run_shell
                                       │
                                       └── wait for subprocess.run to return
                                       ↓
                               role=tool -> next LLM request
```

This version inserts the background start into the same tool protocol and receives natural exit facts at foreground safe points:

```text
[old] agent_loop -> [~] ToolExecutor -> [~] PermissionGate -> [+] start_process
       │                 │                                       │
       │                 │                                       └── [C] ProcessManager
       │                 └── possible attempt/generation         │    ├── Popen + separate process group
       │                                                         │    ├── stdout/stderr draining
       │                                                         │    └── 64 KiB/stream bounded buffer
       ↓                                                         ↓
[~] full role=tool feedback -> [~] sync_processes -> [C] AgentState ProcessEvent
                                 │                         ├── exited/failed
                                 │                         └── successor generation + new verification requirement
                                 ↓
                          [C] completion guard / awaiting_process -> CLI

[~] /new /reset / EOF / exception -> [C] manager.cleanup(task_id)
                                          ├── TERM, wait at most 2 seconds
                                          ├── KILL, wait at most 2 seconds
                                          └── report incomplete cleanup

[B] get_process, read_process, list_processes, wait_process, terminate_process, kill_process are not registered in this version
[B] start_process and process status themselves produce no verification evidence
```

The key mapping: `ProcessManager` owns only the operating system resources that cannot be snapshotted; `AgentState` only receives explainable facts; `agent_loop` decides when to commit facts and block completion; the CLI hands waiting back to the user and cleans up task boundaries. This way Trace can check only the State snapshot, and replay never calls `poll()` again or reads pipes.

## Core Concepts and Data Structures

### Drain the pipes first, then talk about running in the background

The problem to solve is "even when the model does not read the logs, log writes must not stall the subprocess". `ProcessManager.start()` creates the process with `stdout=PIPE`, `stderr=PIPE`, and `stdin=DEVNULL`, and starts one drain thread per stream before returning. Each stream goes into a `_ByteRing` that keeps at most 64 KiB; the ring tracks position by total bytes written, so releasing old log data does not change offsets that have already occurred.

The implementation below shows only the draining. `read1(8192)` reads at most 8192 bytes but also returns promptly when a little output arrives; with the buffered stream's `read(8192)`, short output might wait until the buffer fills or the pipe closes. The thread keeps consuming the pipe, and the ring keeps only bounded data. v0.26 has no log reading tool, but this internal capability guarantees that high-frequency stdout/stderr does not stall because a pipe is full.

```python
def _collect(self, stream, ring):
    while True:
        chunk = stream.read1(8192)
        if not chunk:
            break
        ring.append(chunk)
```

Invalid UTF-8 is not raised to the Agent from the drain thread; later reading interfaces decode with `errors="replace"`. State and Trace keep only the cumulative positions of stdout/stderr, not the log text, so context trimming does not turn long logs into ever-growing state.

### The start ID belongs to the task, and a successful start belongs to one attempt

The problem to solve is "the process was created, but the model must not describe that as the command finally succeeding". `start_process` has `effect_class` `possible`, so after passing the permission gate it first reserves an attempt and a generation, then runs the handler. The internal metadata the handler returns includes the PID, task ID, a command summary, and a cwd summary; the Executor's public result keeps only bounded fields:

```json
{"process_id":"proc-1","pid":12345,"status":"running","start_attempt_id":"a-3"}
```

The `process_id` here is an identifier the Runtime allocates monotonically during the current CLI lifetime, and tools in later versions accept only it; the PID is only for diagnostic display. Every `begin_task` also allocates a `task_id` that is never reused, so even two tasks with identical text do not share process ownership.

When the start attempt is committed, State appends a `ProcessRecord` and a `started` `ProcessEvent` under the same lock. This step comes after the handler succeeds, which solves the race "the process exits immediately and the exit thread writes before the start record": foreground sync only handles processes that are already registered, and the next safe point still finds this exit.

### An exit is a new environment fact; old verification cannot be reused

The problem to solve is "the service may change the environment while it runs, so after it exits old checks can no longer represent the current state". The collector threads only update the Manager's raw handles and buffers; `agent_loop` calls the same `sync_processes()` before assembling the context, after full tool results are fed back, before the completion decision, and when resuming a task. Only when the outer process has exited, the POSIX managed process group is gone, and both pipes have reached end-of-file (EOF) does the Manager commit the final exit fact. Before that, the process still uses an active slot and blocks `done`. When State sees a new exit, it appends one final event: a zero exit is `exited`, a nonzero exit is `failed`, and both reference the original start attempt.

State then opens exactly one successor generation referenced by that event, clears the current generation's verification evidence, and sets `verification_required`. When an existing active failure or a strict verification phase conflicts with the exit, both facts are kept and the task enters a conservative block with the reason `process_exit_conflict`; a process exit never overwrites an earlier failure.

Trace only checks from the snapshot whether `ExecutionGeneration.opened_by_process_event_id` points to the matching exit event, and that each process has at most one final event. The fields below show this causal direction; you should see "the exit event opens the successor generation", not "the start result passes verification directly":

```python
ExecutionGeneration(
    generation_id=next_generation,
    opened_by_process_event_id="pe-2",
    open_reason="process_exit",
)
```

### An active process hands a text reply to the CLI

The problem to solve is "the model has no more tool calls, but a program is still running". The completion decision first checks the processes in State with `status == "running"`; if the model returns text without `tool_calls`, the loop writes `awaiting_process` and immediately hands the text to the CLI. This state is not terminal: it creates no `FailureEvent`, consumes no extra LLM rounds, and does not count waiting time as progress.

The CLI shows the task ID, every active process ID, and the cumulative stdout/stderr positions, together with any unfinished plan, repair, and verification obligations. The user's next input still belongs to the original task; the CLI first syncs exit facts, then clears the waiting state and resumes `running`. If a process has already exited, the resume first opens a new generation and a verification requirement; checks from while it was running cannot be reused.

## Key Flow

The normal start path:

```text
model tool_calls(start_process)
  -> argument validation of command/cwd
  -> separate start_process command pattern permission
  -> reserve possible attempt + generation
  -> Popen(shell=True, stdin=DEVNULL)
  -> start stdout/stderr drain threads
  -> return a bounded role=tool result
  -> State registers ProcessRecord + started event
  -> the Agent continues with other tool rounds
```

The exit and completion guard path:

```text
process exits naturally
  -> the Manager produces one exit fact at a foreground safe point
  -> State records an exited/failed event
  -> new generation + verification_required
  -> once no processes are active, independent verification is still needed
  -> only after verification passes and other obligations are done can it be done

model has no tool_calls and a process is still running
  -> awaiting_process
  -> the CLI shows the process_id and remaining obligations
  -> the user keeps typing
  -> sync first, then resume the original task
```

The task boundary path runs before State is cleared:

```text
/new, /reset, EOF, exit, or exception
  -> sync the current task
  -> TERM + at most 2 seconds
  -> if not exited, KILL + at most 2 seconds
  -> confirm the direct child process, the managed process group (POSIX), and both pipes have ended
  -> wait, bounded, for the collector threads already started, then close the pipes
  -> complete: record the cleanup result and allow the boundary switch
  -> incomplete: show pid/process_id/reason, keep the old task, do not start a new task
```

## Implementation Breakdown

`ProcessManager` is the only object that touches `Popen`. On POSIX it creates a separate process group at start; cleanup first sends a normal termination signal to the process group, then a forced signal after a bounded wait; the outer shell exiting is not enough to prove that descendants in the same group have ended. On Windows, confirming that the direct child process and its pipes have ended is enough to finish task boundary cleanup, and the report states that it cannot prove an arbitrary derived process tree has ended. When collector threads or pipes have not ended, the Manager keeps the registration for a later retry and does not perform a close that could block forever. A failed `Popen` does not enter State's successful process records, but an already allocated process ID is not reused either; if the second collector thread fails to start, only the started thread is waited for, and on incomplete cleanup the visible Manager registration is kept.

`ToolExecutor` is still responsible for the argument, permission, attempt, and handler exception boundaries. An authorization denial happens before the attempt is reserved, so there is no generation; after authorization, an invalid `cwd`, an exhausted quota, or `Popen` raising keeps the reserved generation and the failed attempt. Successful start metadata is passed to State only as an internal field of `ExecutionResult`; the public tool result carries neither the command text nor logs.

`AgentState.sync_processes()` only accepts facts the Manager produces in the foreground. Repeated safe points update cumulative positions but do not append the final event or open a generation twice; `acknowledge_exit()` marks the Manager only after State's registration and event are committed, so an immediate exit is not swallowed while the start record is still incomplete.

## Why This Design

Putting operating system resources in the Manager and audit facts in State keeps threads and file descriptors out of snapshots and keeps Trace truly read-only. The cost is that processes belong only to the current CLI lifetime; after a CLI crash or power loss there is no way to reconnect. Limiting output to 64 KiB per stream controls memory, but v0.26 does not yet expose a reading interface to the model, so the log tail has to wait for the observation tools of a later version.

Splitting start and exit into two facts distinguishes "created successfully" from "the command finally succeeded". It makes a natural exit open one more generation and require verification again; this adds steps but prevents environment changes during the run or at exit from wrongly reusing old evidence. `run_shell` keeps its original synchronous protocol, so existing calls and the return format for short commands are unchanged.

Handing waiting back to the CLI prevents the Agent from calling the LLM again and again when it has no observation tools. The limitation is that in v0.26 the model cannot actively query, read, or terminate processes; a long-running service either exits naturally or is cleaned up internally on task switches and CLI exit.

## Design Boundaries

- `start_process` accepts only a non-empty command and an existing cwd, and rejects unknown arguments; its command rules are separate from `run_shell`, defaulting to ASK. A successful process start does not mean the command succeeded.
- At most 4 active processes per task; at most 64 KiB per output stream; stdin is `DEVNULL`. Output does not enter the State body and produces no verification evidence.
- Only the current task's State registers processes. Old `task_id`s and old `process_id`s never match a new task; the PID is not a model tool argument.
- A natural zero exit records `exited`, and a natural nonzero exit records `failed`; v0.26 does not turn an asynchronous nonzero exit into a `FailureEvent`, and that causal extension is left to v0.27.
- `exploring` and `--plan` still reject starts; plan approval does not replace the `PermissionGate`. Multiple calls in one round still feed back one `role=tool` result per call.
- `/new`, `/reset`, EOF, `exit`, and exception paths all try bounded cleanup. Cleanup failures are visible and keep the old task; cleanup does not undo file or environment changes the process has already made.
- The POSIX process group and pipe boundaries cannot discover or control descendants that both leave the managed process group and close the inherited pipes. A successful direct child cleanup on Windows also does not prove that an arbitrary derived process tree has ended.
- This version provides no `get_process`, `read_process`, `list_processes`, `wait_process`, `terminate_process`, or `kill_process`, and no cross-CLI resume, general sandbox, PTY, or stdin writes.

## Run and Observe

The command below is for Bash/zsh and starts this version's CLI with a command-line first task:

```bash
PYTHONPATH=src python -m mini_agent "start a long-running local service, and keep checking the project once it is available"
```

If the model is approved to call `start_process`, the terminal should first show a bounded start result containing the `process_id` and PID, followed by other tool rounds. If the model replies with text directly while the process is still running, the CLI should show `awaiting_process`, the task ID, the process ID, and "keep typing to observe the task"; this shows that the Runtime prevented a wrong `done`. After the user keeps typing, the CLI first syncs the processes, then passes the input to the original task. When the task ends or you enter `/new` or `/reset`, you should see the cleanup result; incomplete cleanup shows the specific PID, process ID, and reason.

Authorization for `start_process` is separate from `run_shell`. Even if a command is already allowed by the `run_shell` rules, a background start still asks according to its own command rules; choosing `always` only affects the same pattern of the same tool.

## Version Features, Next Lesson, and Code Index

This version adds non-blocking background starts, task-scoped IDs, start attempts and lifecycle events, two-stream draining, bounded buffers, generation isolation after exits, the `awaiting_process` CLI handoff, and task boundary cleanup. The synchronous behavior of `run_shell`, its 30-second timeout and return format, Plan Mode, the Repair Loop, the Trace read-only boundary, and the completion reminder all remain in effect.

The next lesson is not fixed yet; later versions add bounded observation capabilities on top of this version's process facts. The pinned source index for this lesson is below; the links point to the `v0.26` tag at delivery:

- [Manager, draining, and cleanup in `processes.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.26/src/mini_agent/processes.py)
- [The start_process schema in `tools/process.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.26/src/mini_agent/tools/process.py)
- [ProcessRecord, ProcessEvent, and sync in `state.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.26/src/mini_agent/state.py)
- [Safe points and awaiting_process in `agent.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.26/src/mini_agent/agent.py)
- [CLI handoff and boundary cleanup in `__main__.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.26/src/mini_agent/__main__.py)
- [Lifecycle examples in `test_process_management_v026.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.26/tests/test_process_management_v026.py)

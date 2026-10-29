# Stage 8: Process Management Implementation Plan

> Status: `v0.26`–`v0.29` complete (background start, observation, control, pipe stdin, and task finishing)
> Prerequisite stages: Stage 6 reliable execution (`v0.17`–`v0.21`) and Stage 7 structured planning (`v0.22`–`v0.25`)
> Suggested version range: `v0.26`–`v0.29`; PTY remains a separate later evaluation item

## 1. Goal and Positioning

The current `run_shell` uses `subprocess.run` to wait for a command to finish and returns after a 30-second timeout, which suits one-off commands. Development servers, file watchers, and long builds cannot run across Agent rounds with this model. Stage 8 answers one question: **when a program the Agent started does not finish immediately, can the Agent keep working within the current task and observe and control it in later rounds?**

Target flow:

```text
start_process → returns an in-task process_id → the Agent keeps working
                    ↓
             get/read_process → status, incremental output, exit code
                    ↓
             write_process → read/wait → terminate/kill → confirm exit → independent verification or task finish
```

`run_shell` is kept for bounded commands; background processes use separate tools and a `ProcessManager`. The core runtime uses only the Python standard library.

## 2. Scope and Non-Goals

### 2.1 Scope of this stage

- Start and manage background processes within the current CLI process and current task; the synchronous behavior of `run_shell` stays unchanged.
- Keep draining stdout/stderr and storing them within bounds; in later rounds, read new output by cursor and query status and the final exit code.
- Run terminate, kill, and task boundary cleanup only on processes registered by this task; clean up shell-spawned child processes to the extent the platform supports.
- Connect process metadata, lifecycle events, and their causal references to State, the Failure Model, Trace, and the completion decision.
- Provide a bounded wait and a non-terminal handoff for long waits with no new output, so repeated polling neither trips the stagnation guard nor exhausts rounds.
- `v0.29` adds explicitly enabled pipe stdin input; PTY was evaluated separately and is not part of the current core capabilities for now.

### 2.2 Not in this stage

- No cross-process persistence or reconnection; no session resume after the CLI exits.
- No scheduled tasks, Docker/general sandbox, remote process management, or processes shared by multiple Agents.
- No arbitrary PID operations, shell side-effect rollback, or promise that "terminating a process undoes the changes it made".
- No PTY, interactive shell, tmux, or continuous automatic scheduling; pipe stdin provides no terminal echo, control characters, or terminal size semantics.
- No third-party core runtime dependencies, and process declarations do not change the authorization semantics of existing tools.

## 3. Design Boundaries Fixed First

### D1: Processes are managed by `ProcessManager`; State stores explainable facts

Add `src/mini_agent/processes.py`: `ProcessManager` holds `Popen` handles, output buffers, read positions, and stdin writer threads; the tool layer is only responsible for arguments, permissions, and result conversion. The Runtime assigns a never-reused task identifier in `begin_task`; ownership cannot be distinguished only by task text, which may be identical. State stores the in-task `process_id`, owning task, start attempt, generation, status, start/end time, exit code, a bounded command summary, and stdin capability/status; it never puts `Popen`, file descriptors, threads, or input bodies into the snapshottable State. History still carries only the tool call protocol, so process facts stay visible after trimming.

`process_id` is assigned by the Runtime; the model cannot pass a system PID to control arbitrary processes. Only IDs registered by the current task and still valid are accepted; unknown, expired, or cross-task IDs return a structured tool error. Status first keeps four kinds, `running`, `exited`, `terminated`, and `failed`: a natural zero exit is `exited`, an unexpected nonzero exit is `failed`, and after an active stop is confirmed it is `terminated`. A failed start has no runnable process and must be recorded as a failed start attempt; process IDs are never reused.

### D2: Bounded output collection is set up at start

When `Popen` uses pipes, stdout/stderr must be drained continuously even before the model calls `read_process`; otherwise the child may get stuck on a full pipe. The collectors keep only bounded buffers and do not change State directly from background threads. Monotonically increasing byte positions are kept per stream; `read_process(process_id, max_chars)` returns the new content since the last successful read and the new position. When the buffer evicts old content, `output_gap` and the lost byte count are reported separately for stdout/stderr, without pretending the log is complete. stdout/stderr are kept separately, and results and error summaries also have length limits.

The suggested initial resource limits: at most 4 active processes per task, at most 64 KiB kept per output stream per process, and at most 8000 characters of body per tool reply. Read by bytes and decode UTF-8 incrementally, representing invalid bytes with replacement characters; decoding boundaries must not cause repeated or swallowed output. The limits should be configured in one place and documented in the operation manual, with specific values frozen through real tests when `v0.26` is implemented. Logs are untrusted tool data and cannot be promoted to system instructions; State and Trace keep only bounded summaries and positions, not complete logs.

### D3: The process lifecycle has independent facts, and the start result cannot claim completion

After `start_process` passes the PermissionGate and before the handler is called, a generation is reserved as `effect_class=possible`. A successful start only proves the process was created, not that the command succeeded; the exit code observed later must be an independent lifecycle fact that references the start attempt, and the same exit is recorded only once. An unexpected nonzero exit produces a FailureEvent; the failure belongs to the current generation at observation time while referencing the start attempt, without retroactively changing the state of closed generations. The fact that the process later exited cannot pose as a second return value or a second `role=tool` message of the original `start_process` tool call. A traceback in the log or `read_process` itself does not automatically constitute a failure. Active termination and abnormal exit should be distinguished, and a failed process control action cannot pretend that cleanup happened. Only processes with pipes enabled accept `write_process`; each write encodes UTF-8 text once with at most 4096 bytes, and closing stdin uses the same possible-side-effect authorization. A write waits at most 2 seconds; `write_pending` cannot be treated as delivered and cannot be retried automatically.

A running process may still change the environment. Starting it invalidates old verification; from `v0.26` on, while there are active background processes, the task cannot be judged complete on existing evidence. After a process exits or is terminated, verification evidence from before the start or during the run cannot be reused to complete the task. Connectivity checks can be done while a development server runs, but the check results alone cannot prove the final environment is stable. When the final exit is observed, the Runtime opens a successor generation for writes that may have happened before the exit; if terminate/kill was called first, these approved control actions also reserve a generation as `possible`, and already reserved generations cannot be merged or rolled back. Independent verification is then required at a stable boundary. Process status or logs do not serve as verification.

`v0.26` already enforces the conservative completion guard for active processes and opens a successor generation when a natural exit is synced; `v0.27` completes queryable exit events and failure records; `v0.28` completes control actions and final completion admission; `v0.29` adds the finishing of stdin writes and the redaction boundary. What opens the generation is the asynchronous lifecycle fact of a registered process, not quietly changing the `effect_class=none` of `get/read_process` to `possible`. The existing `run_shell(purpose="verification")` is still the verification entry; it cannot be in the same round as side-effect tools, nor bypass the Repair Loop by "the process has started" or "the write succeeded". If an observed exit event conflicts with another active failure or `verification_required`, it does not replace its active failure or quietly clear the verification obligation; it first keeps both sources and blocks within bounds, waiting for the user to decide the new task path. This uses a conservative rule and does not try to merge two repair flows automatically.

### D4: Permission and read-only planning boundaries run through all versions

`start_process` is authorized separately by command pattern; it is not automatically approved for background running just because the same command was approved for `run_shell`; termination, forced kill, and stdin writes each have their own tool admission. `get/read/list` only observe processes registered by this task; `start/terminate/kill/write` are all actions that may have side effects and go through the existing two-layer admission of the plan phase and the executor. The read-only boundaries of `exploring` and `--plan` cannot be bypassed by background starts or stdin writes; plan approval does not replace tool authorization either. The write authorization prompt shows only the process ID, the byte count, and the close flag, never the body.

The existing PermissionGate extracts a command pattern only for `run_shell`; when `start_process` is added, its `command` must be extracted explicitly and given separate rules; a missing rule falls back to the default `ask` and cannot inherit `run_shell`'s `allow`. `cwd` is resolved and validated before start; it is only a working directory and provides no file system isolation. The internal `cleanup()` is resource cleanup for authorized start actions; it can act only on processes registered by this task and is not a permission shortcut the model can use. Every refused tool call must still receive its matching result, without starting a process or reserving a generation.

### D5: Both task and CLI boundaries must clean up

From `v0.26`, an internal `cleanup()` is provided: when exiting the CLI, on `/new` or `/reset`, or when leaving a task abnormally, it first requests normal termination of this task's still-running processes, waits within bounds, then forces them to end, and records the cleanup result. Normal tool calls control only processes registered in `ProcessManager`; POSIX platforms prefer process group cleanup of shell children. The Windows standard library has limited control over arbitrary child process trees, so the actually supported cleanup scope should be stated explicitly; when it cannot be confirmed that children have ended, report incomplete cleanup and never claim full cleanup. Automatic cleanup after a process crash or power loss is not guaranteed in this stage.

Cleanup must happen before `AgentState.begin_task/reset_task` clears the old task facts; otherwise the process IDs and task ownership are lost. A cleanup failure should leave a visible result in the old task, and the CLI should also prompt the user; it must never silently claim nothing was left behind. Output collector threads, stdin writer threads, pipes, and `Popen` handles must all be reclaimed within bounds after exit; when a write is still in flight and its reclamation cannot be confirmed, keep the old task and registration information.

### D6: A long time without output is waiting, not progress

When `get_process` and `read_process` repeatedly get the same status or an empty log, no new investigation facts are produced, and the stagnation count of Stage 7 cannot be reset by the passage of time. From `v0.26`, when the model pauses and outputs text without tool calls in a task with active processes, the Runtime can hand back to the CLI with the non-terminal state `awaiting_process`, showing the process ID and how to continue, without judging it `done` or exhausting the completion reminder immediately. Other unmet plan/repair obligations must still be stated in the handoff and cannot be cleared by this state. `v0.27` adds a bounded `wait_process(process_id, timeout_ms)` that returns on exit or new output; when the wait limit is reached and the process is still running, it enters the same handoff. In `v0.29`, a write that is still in flight also blocks completion, and its final finishing must first be observed with a status query. The next user input can resume the original task and observe again; this is not `blocked` or a `FailureEvent`, and the LLM is not called automatically. Waits have a per-call limit and cannot hold a tool call round forever.

The waiting handoff must be an explicit Runtime state, not something the model gets around the completion reminder with by writing "still running". The LLM is not restarted automatically while the process runs; if the process exits before the user comes back, its status is synced first the next time the task is entered, and one exit fact is recorded. `MAX_ITERATIONS` keeps protecting a single agent loop and is not used as a runtime limit for background processes.

### D7: Status reads are read-only; state transitions are committed by the Runtime

Background collectors maintain only the raw process handles and bounded output buffers; process exits, log cursor commits, FailureEvents, and generation updates are committed together by the foreground Runtime at safe points: `get/read/list/wait`, the user continuing the task, and before the completion decision. `poll()` must not create two exit events for the same process from two queries. Read-only observation tools can obtain facts about registered processes, but `read_process` cannot clear failures, advance plan steps, or produce verification evidence.

During foreground sync, process lifecycle changes are committed first, then the visible state is assembled for the model. If one assistant reply contains several read-only observation tools, it still follows the existing protocol "one result per call, the next round only after all are fed back"; cursor reads on the same process must be serialized, to avoid duplicated or skipped output. Either make the read cursor an explicit position provided by the caller, or have the Manager lock guarantee order within the same task; pick one at implementation and write tests.

## 4. Tool Protocol and State Model

### 4.1 Model-visible tools

| Tool | First version | Key arguments | Result and side effects |
|---|---|---|---|
| `start_process` | `v0.26` (`stdin_mode` added in `v0.29`) | `command: str`, `cwd?: str`, `stdin_mode?: "closed" / "pipe"` | Starts after authorization; returns `process_id`, the diagnostic PID, status, stdin capability, and the start attempt; `possible`. |
| `get_process` | `v0.27` | `process_id: str` | Returns the current status, exit code, and output positions without consuming logs; `none`. |
| `read_process` | `v0.27` | `process_id: str`, `max_chars?: int` | Returns new stdout/stderr fragments separately, the next positions, and gaps; `none`. |
| `list_processes` | `v0.27` | None | Lists only bounded metadata registered by the current task, without log bodies; `none`. |
| `wait_process` | `v0.27` | `process_id: str`, `timeout_ms?: int` | Waits within bounds for new output or exit; on timeout returns `still_running` and can hand back to the CLI; `none`. |
| `terminate_process` | `v0.28` | `process_id: str` | Requests a normal exit and confirms within bounds; reports explicitly if it is still running; `possible`. |
| `kill_process` | `v0.28` | `process_id: str` | Forces an end and confirms the result; `possible`. |
| `write_process` | `v0.29` | `process_id: str`, `input: str`, `close_stdin?: bool` | Writes at most 4096 bytes of UTF-8 text to a process with an explicitly opened pipe; can send EOF alone; `possible`, default `ask`, must not be used to submit verification. |

The model gets only the tool schemas of released versions. Tool results use structured, length-limited JSON; a nonzero process exit cannot be judged by parsing log text or by reusing `run_shell`'s `[exit=N]` string rule. Examples:

```json
{"process_id":"proc-1","pid":12345,"status":"running","start_attempt_id":"a-3"}
```

```json
{"process_id":"proc-1","status":"running","stdout":"ready\n","stderr":"","next_stdout_offset":6,"next_stderr_offset":0,"output_gap":false}
```

`pid` is only for diagnostic display and is not an argument of any control tool. Starting uses the same command string semantics as the current `run_shell`; `stdin_mode` defaults to `closed`, and only processes explicitly set to `pipe` can be written to. A single `write_process` text is first encoded as UTF-8 and then checked against the 4096-byte limit; empty input is allowed only with `close_stdin=true`, the writer thread waits at most 2 seconds in the tool round, and `write_pending` must be observed through a later `get_process` or `wait_process`. A pipe provides only a text byte stream, without PTY echo, control characters, or terminal size semantics. `wait_process` only reports that new output is readable or the process has exited and does not consume the read cursor; a single wait should not exceed 30 seconds, and a timeout is neither a tool failure nor a process failure.

### 4.2 Runtime records

```text
ProcessRecord                         # snapshottable current projection in State
- process_id, task_id
- start_attempt_id, start_generation_id
- command_summary, cwd_summary, pid
- status: running | exited | terminated | failed
- started_at, ended_at?, exit_code?
- stdout_offset, stderr_offset        # only positions, never the full log
- stdin_mode, stdin_state, write_pending, stdin_error
- terminal_event_id?

ProcessEvent                          # append-only lifecycle facts
- event_id, process_id, kind: started | exited | terminated | killed | cleanup_failed
- generation_id, start_attempt_id
- caused_by_control_attempt_id?, exit_code?, reason?

ProcessWaitState                      # exists only during the waiting handoff
- process_id, reason: no_new_output | still_running
- last_observed_event_id?, last_stdout_offset, last_stderr_offset

ProcessManager private runtime state
- process_id -> Popen / process group identifier / collectors
- bounded stdout/stderr buffers, total byte positions, read cursors, and sync locks
- stdin state, a serial write lock, at most one in-flight write, and a bounded reclaim thread
```

Only the Runtime can write `ProcessRecord`, `ProcessEvent`, and the waiting state to State; the model cannot provide a status, exit code, FailureEvent, or generation. Start attempts are still recorded by the Executor; a process exit is a new Runtime fact and creates no forged tool call. Trace consumes only State's append-only events and the public snapshot, and cannot `poll()` again, read pipes, send signals, or call the PermissionGate during replay.

Invariants: `process_id` is unique within a task; each successful start has exactly one `started` event, and each process has at most one final exit event; the final exit must reference an existing start attempt; stdin is accepted only when `stdin_mode=pipe` and the process is still writable; `terminated` can be marked only after the exit is confirmed; read cursors increase monotonically, and log gaps cannot be hidden; old task IDs cannot be used for new tasks; `done` must not be decided while there are active processes, in-flight stdin writes, or a generation awaiting verification. Input bodies never enter State, Trace, tool results, authorization prompts, or terminal output.

## 5. Version Slices

### 5.1 `v0.26` Background Process (complete)

Goal: establish a minimal non-blocking process lifecycle. This version lets the Agent keep running other tools after a start; observation and explicit control are left to later versions.

Completed work:

1. Added `ProcessManager`, in-task ID allocation, `Popen` start, and current-task registration; set up a separate process group or the platform's equivalent minimal control boundary.
2. Added the `start_process` tool with separate command pattern permissions; a generation is reserved as `possible` before the handler. A failed start keeps the original failure result and generation and produces no successful ProcessRecord.
3. stdout/stderr are drained separately from the start, keeping a fixed memory limit; stdin is closed for now.
4. Added a minimal `ProcessRecord` projection to State; the context injects the current task's IDs, status, and bounded summaries, so history trimming does not lose process facts.
5. Natural exits are synced in tool rounds and before the completion decision, recording a minimal final event, opening a successor generation, and requiring verification again; active processes block a wrong `done`, and when the model pauses, `awaiting_process` can hand back to the CLI.
6. The CLI main loop cleans up processes in `finally`; `/new` and `/reset` clean up the old task before State is reset. Cleanup terminates first, waits a bounded time, then kills, and reports failures.

Covered acceptance focus: starting a service returns immediately, and the next tool round can continue; no amount of logging blocks the pipe; exits and task switches run bounded cleanup and report leftover risk; a simple `run_shell` still works with its original timeout and return protocol. Observation tools, active control, and the `FailureEvent` for natural nonzero exits are left to later versions.

### 5.2 `v0.27` Process Observation (complete)

Goal: get the real status, incremental output, and final exit code of a process across rounds, without polling consuming meaningless Agent rounds.

Main work:

1. Add `get_process`, `read_process`, `list_processes`, and a bounded `wait_process`; cursor reads on the same process are committed in call order.
2. Output positions count bytes and keep stdout/stderr separately; handle UTF-8 split across chunks, output truncation, empty output, trailing output after exit, and gaps caused by buffer eviction.
3. Extend the queryable metadata of `ProcessEvent` and idempotent exit sync; a natural nonzero exit produces a FailureEvent that references the start attempt, and observation tools themselves are never judged as failures.
4. Hand new status, new logs, and repeated empty results to the Stage 7 stagnation guard to tell apart; unchanged polling does not count as new facts. A `wait_process` timeout enters the `awaiting_process` handoff, and the next user input syncs the process first and then continues the original task.
5. Add readable process facts to Structured State and Trace; log bodies are fed back within bounds only with this tool result and are not put into long-term State.

Acceptance focus: two reads have no duplicates, lost logs have gap markers, and a natural exit is recorded only once; a long time without output can wait and hand back to the CLI without being misjudged as task completion or an abnormal failure.

### 5.3 `v0.28` Process Control

Goal: let the Agent end programs it started, with authorization, so that the whole task finishes under the existing execution and verification contracts.

Main work:

1. Add `terminate_process` and `kill_process`; both first confirm current task ownership by ID, then go through their own PermissionGate admission, and reserve a generation as `possible` when approved.
2. `terminate` sends a normal termination request and waits within bounds, returning `still_running` after the waiting period; `kill` forces an end and confirms. Status must not be written as `terminated` before confirmation.
3. Implement the cleanup of shell-spawned children the platform can guarantee; when complete cleanup cannot be confirmed, report the limitation or failure, and termination failures and permission denials must not affect other processes.
4. Explicit control, natural exit, and internal cleanup each keep their own reason; internal cleanup runs at task boundaries and does not forge model tool calls.
5. Complete the combination rules of active processes, the new generation after exit, independent verification, the Repair Loop, Plan Mode, and the final `done`; Trace can replay the start—observe—control—verify chain and corrupted references.

Acceptance focus: normal exit, refused termination, still running after termination, forced kill, and control failure all have distinguishable results; only independent verification after cleanup can complete the task, and old evidence is never reused across generations.

### 5.4 `v0.29` Interactive Process (complete)

Goal: support commands that need a small amount of stdin while keeping Stage 8's task ownership, authorization, redaction, cleanup, and independent verification boundaries.

Main work:

1. `start_process(command, cwd?, stdin_mode?)` defaults to `closed`; only processes that explicitly choose `pipe` keep a writable stdin. Add `write_process(process_id, input, close_stdin?)`, where input accepts only UTF-8 text with at most 4096 bytes after encoding; empty input can only send EOF together with `close_stdin=true`.
2. Writing and closing share the `possible` permission check with default `ask`. Each process has a serial write lock and at most one in-flight write, with a dedicated thread waiting at most 2 seconds; `written`, `closed`, `write_pending`, and pipe errors all return structured status, and input bodies never enter State, Trace, tool results, authorization prompts, or terminal output.
3. After writing, keep observing output with `read_process` or `wait_process`; a write does not constitute verification. Process exit, control, and task boundary cleanup all reclaim writer threads within bounds; when reclamation cannot be confirmed, the old task registration is kept, and active processes or in-flight writes block `done`.
4. PTY was evaluated and is not implemented for now. Pipes cannot express terminal echo, control characters, terminal size, or interactive shell semantics, and make no promise of cross-platform terminal behavior; these capabilities need a separate protocol, cleanup, and tests before a decision.

Acceptance focus: a simple child process waiting for one line of text can be driven and exits normally after EOF; input never appears in audit summaries; unsupported PTY scenarios have explicit capability boundaries.

## 6. Composition with the Existing State Machine

The process lifecycle is orthogonal to Planning State and the Repair Loop; it adds no separate Planner and does not replace the existing task state. Admission takes the stricter side under the existing rules:

| Current state | Allowed process actions | Key limits |
|---|---|---|
| `direct/executing` + `idle` | Start, observe, and control per permissions; verify separately | Active processes block final completion; new verification is needed after exit. |
| `exploring` | Only observe the status and output of registered processes | No start, terminate, forced kill, stdin write, or verification. |
| `awaiting_approval` | The CLI waits for the user's decision; internally facts can be synced and cleaned up | Model tool calls keep being refused; approving the plan does not authorize starts automatically. |
| `diagnosis_required` | Read-only observation for diagnosis | Control actions must go through the existing restricted recovery entries or an explicit user decision; termination tools cannot bypass the Repair Loop. |
| `verification_required` | The next model tool round is still an exclusive `run_shell(purpose="verification")` | If a new conflicting process exit fact appears in the meantime, block conservatively and keep the original failure and verification obligation. |
| `awaiting_process` | The CLI waits for the user's next input | Keep the original task and plan; sync processes before resuming; no automatic LLM call. |

The relationship between control tools and RecoveryActions must be explicit in `v0.28`: if terminating a process during diagnosis is part of a repair, a legal causal entry must first be established through the existing `recover` or `request_replan`; new `possible` tools cannot simply be opened. It does not cancel feeding back every tool result per round, independent verification, or the PermissionGate.

## 7. Tests and Acceptance

### 7.1 Unit and integration tests

- **Start and authorization**: starts return quickly instead of waiting for exit; permission denials, invalid arguments, invalid cwd, and exceeding the concurrency limit create no process; only approved starts reserve a generation.
- **Output**: high-frequency stdout/stderr does not block; multi-byte characters split across chunks, empty output, very long logs, gap markers, and repeated reads are all correct by byte position; logs do not enter the full State snapshot.
- **Status**: natural zero exit, nonzero exit, and the link between exit code and start attempt; repeated queries never record an exit or FailureEvent twice; cursors of several processes do not mix.
- **Waiting**: new output, process exit, and wait timeout each return an explicit result; a timeout handoff counts as neither successful progress, failure, nor a terminal state, and the next user input resumes the original task.
- **Control**: only IDs of the current task can be controlled; TERM, KILL, still running after timeout, already exited, refusal, and control failure never forge states; pipes and collector threads are cleaned up.
- **State machine**: Explore, plans awaiting approval, and diagnosis/verification phases all enforce correct admission; after start and control, generations, verification isolation, the completion reminder, and the stagnation guard keep their original constraints.
- **Protocol and replay**: several tool calls in one round each get one `role=tool` result; Trace is read-only with complete references, and corrupted or cross-task process events are marked incomplete.

Tests use the standard library to start short-lived scripts and a local HTTP service, avoiding external packages or fixed ports. Platform differences are handled with capability detection and explicit skips; "the current machine can kill the outer shell" must not be taken as proof that child processes are cleaned up.

### 7.2 Stage-level E2E

1. Start a local HTTP service and get a `process_id` immediately; the Agent runs other tools, later reads the ready output and checks a response, terminates the service, confirms the exit, and then completes independent verification.
2. Start a process that exits nonzero after two seconds; later queries get the exit code, a single FailureEvent, and the complete start causal reference, and the model handles it along the existing diagnosis or replanning path.
3. Start a process with continuous output; repeated incremental reads have no duplicates and do not grow memory without bound; after buffer eviction, an explicit `output_gap` is returned.
4. Start a process with no output for a long time; after a bounded wait it hands back to the CLI, and when the user continues, the original process can still be observed, without being marked `done` or exhausting Agent rounds because of empty polling.
5. Try a final reply while a process is still running; the Runtime does not accept completion. After the process is stopped, old verification is still invalid, and only new independent verification allows finishing.
6. `/new`, `/reset`, EOF/normal exit, and abnormal paths all clean up the processes the current task can control; old IDs are invalid for new tasks, and external PIDs are never harmed. When the platform cannot confirm child process cleanup, it reports this explicitly.

### 7.3 Stage definition of done

- [x] `v0.26`–`v0.29` have their own tutorials, change records, and runnable tests; v0.29 pipe stdin passed acceptance, and PTY remains a later evaluation.
- [ ] The existing short-command behavior of `run_shell` is kept, and background commands can be started, observed, and controlled across Agent rounds.
- [ ] All background processes are bound by task ownership, resource limits, separate permissions, and task boundary cleanup.
- [ ] Process exits, failures, control, and final verification have replayable causal relationships; old evidence from during the run and after exit cannot complete a task by mistake.
- [ ] The default test suite, the tutorial check, the README check, and the stage-level E2E all pass; the core still depends only on the standard library.
- [ ] After the user manually creates each version's tag, the matching tutorial facts check and release acceptance are completed.

## 8. Version Dependencies

```text
v0.25 plan trace replay and acceptance
  ↓
v0.26 background start, task ownership, output draining, and basic cleanup
  ↓
v0.27 incremental observation, exit facts, waiting handoff
  ↓
v0.28 explicit control, complete cleanup, verification and Trace loop
  ↓
v0.29 pipe stdin; PTY evaluated and not implemented for now
```

`v0.26` does not require a complete observation UI, but output draining, cleanup, and the completion guard cannot be postponed; `v0.27` does not open arbitrary PID control; `v0.28` does not treat a successfully sent signal as an exited process; `v0.29` does not treat a write confirmation or sent EOF as a process exit, and does not treat pipe input as a PTY. Each version keeps one teachable topic and independently acceptable behavior.

## 9. Documentation and Release Sync

When implementing each version, sync the matching tutorial, `docs/tutorials/README.md`, `docs/operation/manual.md`, `CHANGELOG.md`, the learning path in `README.md`, the version information in `pyproject.toml`, and the status of this plan; update `AGENTS.md` only when runtime hard constraints really change. The tutorial is for readers new to Agents: it first explains why long commands block, then introduces the tools, process facts, and verification rules. The main README's stage names and version topics follow the governance writing rules.

Before delivering each version, run:

```bash
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python scripts/check_tutorials.py
PYTHONPATH=src python scripts/check_readme.py
```

After the tutorial is complete and the user manually creates the matching tag, run the facts check that depends on local Git objects. The assistant must not create, move, overwrite, delete, or push tags.

## 10. Capability Boundaries After the Stage

After the Stage 8 core is complete, mini_agent can keep long-running programs within the current task: keep working after a start, then read new output and the final status, end processes with authorization, and finish with independent verification after the exit. It still manages only task processes registered within the current CLI process and provides no crash recovery, general sandbox, automatic daemon services, or complete terminal emulation.

# Lesson 27: Observing background processes

Previous: [Background process start and task boundaries](26-background-process-boundaries.md) · [Tutorial overview](README.md) · Next: [Controlling background processes](28-process-control.md)

Code snapshot: `v0.27` · Adjacent diff: `v0.26..v0.27` · Shell for examples: Bash/zsh

The `v0.27` tag is created manually by the repository maintainer. Before the tag exists, you can read and run this lesson's interfaces on the current branch; pinned source links and cross-version diffs must be checked after the tag is created. A command-line argument is still the CLI's first task, and the program enters the interactive loop after handling it.

## Lesson Goals

Imagine the Agent has started a development server. The server quickly prints `ready`, but the real error may only appear on stderr a few seconds later; the server may also go a long time without new output. Returning only the `process_id` from startup cannot answer three practical questions: is it still alive now? What did it just output? Did it finally succeed or fail?

This lesson adds an "observation channel" for this process. After reading it, you should be able to follow one call and explain the chain below:

1. The Agent queries the lifecycle with `get_process` or `list_processes`, and takes stdout/stderr not yet delivered with `read_process`.
2. `read_process` uses two byte cursors to remember what has already been delivered, so repeated reads never return the same logs again.
3. When the ring buffer is overwritten by new output, the result reports the gap explicitly; the Agent never mistakes a partial log for a complete one.
4. When there is no output, `wait_process` waits only for a bounded time and hands the task back to the CLI after the timeout, instead of continuing to consume LLM rounds.
5. After the process exits naturally, the Runtime records one exit fact; verification obtained before the exit cannot carry over into the new generation (verification generation).

"Observation" here reads only the processes registered by the current task. Active termination and stdin writes are left to the next lesson and to `v0.29` respectively; this lesson does not use them early.

## Problems in the Previous Version

`v0.26` already solved the most dangerous part of background starts: `start_process` returns immediately after creating the process; two background collector threads keep draining stdout and stderr; each stream keeps at most 64 KiB. So a subprocess is never stalled by a full pipe just because the Agent has not read its logs for a while.

But draining only "catches the logs safely"; it does not yet "hand the logs to the model". The previous version's start result had roughly only this information:

```json
{"process_id":"proc-1","pid":12345,"status":"running"}
```

This proves the process was created successfully, but it cannot say what it printed later or whether it has already exited. If the whole buffer were returned every round, the model would see old logs again and again; if the model called a query every short interval, it would waste tool rounds while "there is still no output". `v0.27` separates these two cases: deliver new facts when there are new facts, and wait boundedly and hand off when there are none.

## Prerequisites and Version Checkout

You need basic Python, Bash/zsh, and the task-scoped `process_id`, stdout/stderr draining, and task boundaries mentioned in the previous lesson. The commands below first show you "where the observation interfaces plug in", then switch to this lesson's code; `git diff --stat` is a quick look at the scope, while the files and symbols later are the focus.

```bash
git checkout v0.26
git diff --stat v0.26..v0.27
git diff v0.26..v0.27 -- src/mini_agent/processes.py src/mini_agent/tools/process.py src/mini_agent/state.py src/mini_agent/agent.py src/mini_agent/trace.py
git checkout v0.27
```

Without the `v0.27` tag, stay on the current development branch to run this lesson's commands; check pinned source links and cross-version facts after the tag is created.

## New and Changed Files

Use this table to build a map first. You do not need to memorize all the files; each time an internal name comes up later, the text explains the specific problem it solves.

| File | Role in this lesson |
| --- | --- |
| `src/mini_agent/processes.py` | Adds per-stream read cursors, UTF-8 fragment reads, and bounded waits on top of the v0.26 byte ring. |
| `src/mini_agent/tools/process.py` | Releases four observation tools: `get_process`, `read_process`, `list_processes`, and `wait_process`. |
| `src/mini_agent/state.py` | Writes status, output positions, and one-time exit facts into snapshottable State, and creates a failure fact on a natural nonzero exit. |
| `src/mini_agent/agent.py` | Commits observation results in tool call order; after a wait timeout, enters `awaiting_process` and hands the task back to the CLI. |
| `src/mini_agent/trace.py` | Checks, read-only, the references between process start, exit, failure, and generation. |

## Version Change Map

Legend: `[old]` already in the previous version, `[+]` new in this version, `[~]` changed in this version, `[C]` main consumer, `[B]` boundary of this version.

The previous version already collected output in the background, but the model had no way to read it:

```text
[old] start_process
       -> [C] ProcessManager: Popen + stdout/stderr byte rings
       -> role=tool returns process_id

[old] agent_loop safe points
       -> State syncs natural exits
       -> active processes still prevent a wrong done
[B] the model can only know "it started", and cannot query status or read new logs
```

This version connects the observation tools to the same task ownership and tool protocol:

```text
[old] start_process -> [C] ProcessManager processes and bounded byte rings
                            |
              [+] get_process / list_processes
              [+] read_process / wait_process
                            |
              [~] agent_loop runs them in model order and feeds back role=tool one by one
                            +-> read: new stdout/stderr + new positions + gaps
                            +-> wait timeout: still_running
                                          -> [C] awaiting_process -> CLI
                            +-> natural zero exit: ProcessEvent(exited)
                            +-> natural nonzero exit: ProcessEvent(failed)
                                                  -> FailureEvent
                            -> successor generation -> independent verification
[C] State stores explainable positions and lifecycle facts; Trace checks these facts read-only
[B] this version provides no termination, kill, stdin, PTY, or arbitrary PID operations
```

The content returned by an observation tool first forms a complete `role=tool` message before the next LLM request. In particular, when `wait_process` times out, even though the task is handed back to the CLI, the matching tool result must still be fed back first; otherwise the next context would contain a tool call without a result.

## Key Flow: What Each of the Four Tools Answers

Think of the four tools as four different questions, not four similar query interfaces:

| Tool | The question it answers | Consumes logs? |
| --- | --- | --- |
| `get_process(process_id)` | What state is the process in now? What is its exit code? Up to which byte position has output accumulated? | No |
| `list_processes()` | Which processes has the current task registered? Which are still running? | No |
| `read_process(process_id)` | What new stdout/stderr has appeared since the last read? | Yes, advances both read cursors |
| `wait_process(process_id)` | Within a bounded time, is there new output, or did the process exit? | No |

The `process_id` is an identifier the Runtime allocates for the current task. It is different from the operating system PID: the PID appears in the start result only for diagnostic display, and the observation tools never let the model use an arbitrary PID to query other processes on the system. An unknown, expired, or cross-task `process_id` gets `unknown_process_id`, and the model is not allowed past the task ownership boundary.

A typical observation order: first `start_process` to get a `process_id`, then `wait_process` to wait for `ready`, then `read_process` to read the response, and finally `get_process` to confirm the status and exit code. If you already know output is about to arrive, you can also read directly; `wait_process` only reduces the cost of "polling over and over when there are no new facts".

## Core Concept 1: Read Cursors Make Logs Appear Only Once

### The problem to solve

stdout and stderr are two independent byte streams. The background threads already put them into in-memory buffers, but the Agent needs a rule to know "which bytes have already been delivered". If every read starts from 0, old logs appear again in every tool round; if only the current buffer length is used, after buffer eviction there is no way to know whether content was lost in between.

### Intuitive explanation

Each stream has an absolute byte position meaning "after the last successful delivery to the model, where the next read continues from". For example, stdout produces:

```text
ready\n       6 UTF-8 bytes
```

The first read returns `ready\n` and advances the stdout cursor to 6. If there are no new bytes, the second read returns an empty `stdout`, and the cursor is still 6. stderr has its own cursor, so when stderr output arrives does not change the stdout position.

Below is a minimal shape of the actual protocol. The field names matter more than the example content: the body is the newly added fragment, and `next_*_offset` is where the next read starts.

```json
{
  "process_id": "proc-1",
  "status": "running",
  "exit_code": null,
  "stdout": "ready\n",
  "stderr": "",
  "next_stdout_offset": 6,
  "next_stderr_offset": 0,
  "output_gap": false,
  "stdout_output_gap": false,
  "stderr_output_gap": false,
  "stdout_lost_bytes": 0,
  "stderr_lost_bytes": 0
}
```

### Where the code actually changes the cursor

The implementation first computes the fragments from the Manager's cursors, assembles the result, and writes the cursors back only after confirming the result can be returned. The code below omits the JSON budget and the stdout/stderr split and keeps only this order; the order guarantees that "content already delivered is never delivered again".

```python
# Key order in v0.27 ProcessManager.read_process
stdout, out_next, out_gap, out_lost, _ = self._stream_fragment(
    managed.stdout_ring, managed.stdout_cursor, ...
)
stderr, err_next, err_gap, err_lost, _ = self._stream_fragment(
    managed.stderr_ring, managed.stderr_cursor, ...
)
result = {
    "stdout": stdout,
    "stderr": stderr,
    "next_stdout_offset": out_next,
    "next_stderr_offset": err_next,
    "output_gap": out_gap or err_gap,
}
managed.stdout_cursor = out_next
managed.stderr_cursor = err_next
return result
```

The cursor here is a **byte** position, not a Python string index. One CJK character usually takes several UTF-8 bytes, and the background thread may receive only part of it first. The implementation uses an incremental decoder: an incomplete tail does not advance the cursor for now, and the next read continues from the same byte; only after the process has ended are remaining invalid or incomplete bytes delivered with replacement characters. This way characters are neither repeated nor delivered half to the model.

### Why reading too late must report a gap

Each stream keeps only the most recent 64 KiB. Suppose the cursor is still at 0 and stdout has already produced more than 64 KiB, so the earliest bytes were evicted by the ring buffer; the next read can then only start from the current start of the buffer. The result sets `stdout_output_gap` to `true` and reports the estimated number of lost bytes in `stdout_lost_bytes`. stderr has matching fields, and `output_gap` is the combined flag for both streams.

A gap is not ordinary empty output. Empty output means "there is currently no undelivered new content"; a gap means "old content can no longer be recovered". After the Agent sees a gap, it can treat later logs as diagnostic clues but cannot claim it saw the complete history. This trade-off keeps memory bounded and makes information loss visible.

`max_chars` defaults to 2000 with an allowed range of 1–4000; the two streams share the result budget, and the full JSON result is at most 8000 characters. It limits the result handed to the model at one time, not the total amount the background collector threads write.

## Core Concept 2: Observing Status and Delivering Logs Are Two Different Things

`get_process` does not consume logs, so it is suited to answering "has it exited yet" and "what is the exit code"; `read_process` advances the cursors, so it is suited to answering "what happened since the last read". `list_processes` returns only bounded metadata for the current task, without log bodies; when there are too many records, earlier records are omitted and an `omitted_count` is given. Mixing these three would leave the model unsure whether a query has already changed the result of later reads.

`wait_process` goes one step further than `get_process`: it can return early when a background thread finds new output or the process exits, but it does not consume logs. It returns one of three reasons:

```text
reason=output_available  -> there is unread stdout/stderr; call read_process next
reason=exited            -> the process is confirmed ended; call read_process/get_process next
reason=still_running      -> the wait limit was reached with no new facts; the task is handed back to the CLI
```

The default wait is 1000 milliseconds, with an allowed range of 0–30000 milliseconds. The wait tool must be alone in its tool round, because it is a time-bounded control flow action; if the same round contains other tool calls, the Runtime feeds back a rejection result for every call instead of letting one of them keep waiting at an unclear point in time.

## Core Concept 3: Wait and Hand Off When There Is No Output

### Why the model cannot just keep asking

A server may produce no new logs for 10 minutes, but that does not mean the task failed or that it is done. If the Agent called the LLM every second to ask "anything changed?", it would spend rounds and context budget on repeated observation. Getting the same status or empty logs again and again does not count as new progress either.

So `wait_process` takes only one bounded tool call. If it returns on timeout:

```json
{
  "process_id": "proc-1",
  "reason": "still_running",
  "status": "running",
  "exit_code": null,
  "stdout_offset": 6,
  "stderr_offset": 0
}
```

The Agent first writes this result into history, then enters `awaiting_process`. This is a non-terminal state meaning "continue after the user's next input": the task is not done, and the background process still belongs to the current task; it is not `done`, not `blocked`, and not a process failure. When the user keeps typing, the CLI first syncs the real process state, then resumes the original task, so the model never sees a stale `running`.

If the model replies with text directly without calling a tool while there are still active processes, the Runtime takes the same kind of handoff. This guard cannot be forged by the model saying "the process is still running"; it must be confirmed by the real Manager and State together.

## Implementation Breakdown: An Exit Is a Lifecycle Fact Committed in the Foreground

### Collector threads only collect; only the Runtime changes State

The Manager holds the `Popen`, process group, collector threads, byte rings, and read cursors; these are runtime resources inside the current CLI process and cannot go into snapshots. The background threads are only responsible for draining stdout/stderr and notifying waiters. They do not create `ProcessEvent`, `FailureEvent`, or generations directly.

The foreground Runtime calls `sync_processes()` at several safe points:

```text
before an LLM request
after all tool results are fed back
before the completion decision without tool_calls
when the user continues the task from awaiting_process
```

This guarantees that what State sees is one complete, explainable observation. Sync updates the cumulative stdout/stderr positions; only the first confirmation of a stable exit appends the final `ProcessEvent`. Repeated `get_process`, repeated `read_process`, or repeated syncs never duplicate the exit event.

### What "confirming a stable exit" means

The Manager does not treat the exit code that `Popen.poll()` returns immediately as a complete exit. It also confirms that, on POSIX, the managed process group is gone, and that both the stdout and stderr collector threads have reached EOF. The reason is that the outer shell may exit first while its descendants are still running or still hold the pipes. Confirming only the direct child would make the Agent believe too early that the resources are finished.

After confirmation, a zero exit code forms `ProcessEvent(kind="exited")`; a nonzero exit code forms `ProcessEvent(kind="failed")` plus a `FailureEvent`. A nonzero exit cannot be inferred by parsing log text; it must come from the real exit code.

### Why a natural failure links to the start fact

The `FailureEvent` references the start attempt (a tool attempt already recorded in the execution records) and the process event that produced it. The causal relationship reads like this:

```text
start_process attempt
        ↓
ProcessEvent(kind=failed, exit_code=7)
        ↓
FailureEvent(caused_by_process_event_id=...)
```

This lets the Repair Loop (the diagnosis, recovery, and verification loop after a failure) know which process the failure came from, without disguising an observation call as the failed execution call. Repeated syncs only find the same `terminal_event_id`, so one exit produces only one failure fact.

### Why an exit opens a new generation

A `generation` is a verification generation: it marks whether a set of verification evidence was obtained before or after the environment went through certain side effects. Even if a background process does not change the repository, it may write files, create caches, hold ports, or change the state of external services. When the process exits, the Runtime clears the current verification evidence, opens a successor generation linked to the exit event, and sets `verification_required`.

So "started successfully", "read `ready`", and "the process exited with 0" are not final verification. After the exit, `run_shell(purpose="verification")` must still be called independently in the new generation; for a nonzero exit, the existing diagnosis or replanning flow comes first. If there is already another active failure or a strict verification in progress, the process exit keeps both facts and blocks the task when it cannot judge safely, instead of overwriting the original repair obligation.

## Run and Observe

The command below is for Bash/zsh and runs the test scenarios of this version that relate directly to background observation:

```bash
PYTHONPATH=src python -m pytest -q tests/test_process_management_v027.py
```

When you look at the test results, do not look only at "all passed". Map each observation to a concept:

| Observation | What it proves |
| --- | --- |
| A UTF-8 character split across collected chunks is returned only once | Cursors are kept in bytes, and incremental decoding neither repeats nor delivers half a character. |
| The second of two `read_process` calls has an empty body | The cursor advances after a successful return, so reads are incremental. |
| After buffer eviction, `output_gap` and the lost byte count appear | Bounded memory does not hide missing logs. |
| After `wait_process` returns `output_available`, `read_process` can still read the logs | Waiting only observes and does not consume the cursor. |
| A nonzero exit produces only one failure fact with a causal reference | Foreground sync is idempotent, and the failure comes from a real exit event. |
| After a `wait_process` timeout, the LLM is called only once and the state is `awaiting_process` | No output hands back to the CLI instead of polling automatically and consuming rounds. |

On the current code branch, you can also let the Agent start a short command that first prints `ready` and then exits, then call `get_process`, `read_process`, and `wait_process` in turn. If the read happens after the process exits, you should still see the tail of the output; if the wait has no new output, you should see `still_running` instead of an empty result being treated as a failure.

## Why This Design

The read cursor lives in the Manager that owns the handles so that multiple observations within one task share one deterministic position; the log body stays in this tool result so that State and Trace do not grow without limit. The cost is that after the CLI process ends, the old `Popen` and pipes cannot be reconnected, and Trace can only replay structured facts that have already been committed.

Storing stdout and stderr separately lets each report its own position and gap; the cost is that this lesson makes no promise about the exact interleaving of the two streams on a terminal. Programs that want terminal-style interaction also need stdin, echo, and PTY semantics, which are not part of this version.

Waiting uses "a bounded tool call + CLI handoff" because no output does not mean no future, and it is not worth letting one LLM round be held indefinitely. The cost is that the user may need to type again to resume observation. Committing exit facts at foreground sync points satisfies several requirements at once: a complete tool protocol, snapshottable State, read-only Trace, and idempotent exit events.

## Design Boundaries

- The observation tools can only access `process_id`s registered by the current task; they cannot query arbitrary PIDs or reconnect across CLI sessions.
- `get_process`, `list_processes`, `read_process`, and `wait_process` do not terminate processes, do not advance plan steps, and produce no verification evidence.
- Each output stream keeps at most 64 KiB; after `output_gap` appears, evicted history cannot be recovered.
- `read_process`'s `max_chars` defaults to 2000 with a range of 1–4000; `wait_process` defaults to 1000 milliseconds with a range of 0–30000 milliseconds.
- Observation tool results do not replace `role=tool` feedback; multiple observation calls in one round commit in model order, and `wait_process` must be alone in its round.
- A natural exit invalidates old verification; active processes, a generation awaiting verification, or an existing repair obligation still prevent the task from finishing wrongly.
- This lesson provides no `terminate_process`, `kill_process`, `write_process`, or PTY; active control is in the next lesson, and pipe stdin is in `v0.29`.

## Version Features, Next Lesson, and Code Index

This version adds four read-only observation tools within the current task, per-stream incremental output, byte cursors, gap reports, natural exit facts, a `FailureEvent` for nonzero exits, and a bounded wait handoff. The next lesson builds permission-protected normal termination and forced kill on top of these observation results; this lesson does not treat "observing a process" as "being allowed to control it".

Pinned source entries:

- [The Manager's read cursors and waits](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.27/src/mini_agent/processes.py)
- [The protocol of the four observation tools](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.27/src/mini_agent/tools/process.py)
- [Exit failure facts and foreground sync](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.27/src/mini_agent/state.py)
- [Serial observation and handoff in the agent loop](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.27/src/mini_agent/agent.py)
- [Trace's cross-generation causal checks](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.27/src/mini_agent/trace.py)

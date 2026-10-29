# Lesson 29: Driving background processes that wait for input

Previous: [Controlling background processes](28-process-control.md) · [Tutorial overview](README.md)

Code snapshot: `v0.29` · Adjacent diff: `v0.28..v0.29` · Shell for examples: Bash/zsh

The `v0.29` tag is created manually by the maintainer. Before the tag exists, you can read this lesson on the current development branch; pinned source links and cross-version diffs must be checked after the tag is created. After the command-line first task finishes, the CLI still enters the interactive loop.

## Lesson Goals

The previous two lessons let the Agent start background programs, read their output, and end them when needed, but a background program never got a writable stdin. That default suits development servers and file watchers: they need no input and can see EOF immediately. It does not suit a program like this:

```text
print ready
wait for the user to enter one line
print reply
keep waiting for EOF
exit
```

If the Agent only sees `status=running` and cannot send that line of text, it cannot drive this program forward. This lesson adds **bounded pipe input**: only when `stdin_mode="pipe"` is chosen explicitly at start can a later `write_process` send a small amount of UTF-8 text.

After reading, you should be able to answer these questions:

- Why is the default still `stdin_mode="closed"`, instead of opening a pipe for every process?
- Why does one line of input usually need an explicit `\n`, while `close_stdin=true` means EOF?
- Why is the limit computed on UTF-8 encoded bytes rather than Python characters?
- What next step does each of `written`, `closed`, `write_pending`, and `error` allow?
- Why must you still call `read_process` or `wait_process` after a successful write, and verify again after the process exits?

What this lesson implements is a text pipe, not terminal emulation. Password prompts, Ctrl-C, terminal echo, full-screen interfaces, and terminal size are all outside this capability.

## Problems in the Previous Version

When `v0.28` starts a background process, it connects stdin to `DEVNULL`. The child sees EOF arrive immediately, which keeps a process that nobody writes to from waiting forever to read, but it also means the Agent has no input entry later. The observation tools can see that it is waiting and the control tools can end it, but neither can send data in.

Changing every stdin to a pipe is not a safe default either. A command that does not need input might occupy the task for a long time because it never gets EOF; a pipe write may also block because the child does not read. So this version splits the two decisions: the capability is chosen at start, writes are separate later calls, and each write has a size limit and a wait limit.

## Prerequisites and Version Checkout

You need basic Python, Bash/zsh, and the task-scoped `process_id`, PermissionGate, possible effect, exit events, and independent verification introduced in Lesson 28. First look at the real insertion points of this version relative to the control version, then switch code:

```bash
git checkout v0.28
git diff --stat v0.28..v0.29
git diff v0.28..v0.29 -- src/mini_agent/processes.py src/mini_agent/tools/process.py src/mini_agent/tools/base.py src/mini_agent/state.py src/mini_agent/trace.py src/mini_agent/agent.py src/mini_agent/output.py
git checkout v0.29
```

Without the `v0.29` tag, stay on the current development branch to run this lesson's commands; check the pinned-version diff and source links after the tag is created. The examples need no third-party dependencies, and all commands use `PYTHONPATH=src`.

## New and Changed Files

These files together complete the chain "enable the capability → write → observe → finish". The file names themselves are not the learning goal; the text below explains, along this chain, why each one exists.

| File | Role in this lesson |
| --- | --- |
| `src/mini_agent/processes.py` | Chooses between `DEVNULL` and `PIPE` at start; manages one write, a bounded 2-second wait, and cleanup. |
| `src/mini_agent/tools/process.py` | Extends `start_process` with `stdin_mode`, registers `write_process`, and validates the UTF-8 byte limit. |
| `src/mini_agent/tools/base.py`, `src/mini_agent/permission.py` | Run ownership, phase, permission, and in-flight state checks before writing; writes are handled as actions that may have side effects by default. |
| `src/mini_agent/state.py`, `src/mini_agent/trace.py` | Store the stdin capability and safe metadata, keep redacted attempts and exit causality, and never store the input body. |
| `src/mini_agent/prompt.py`, `src/mini_agent/context.py`, `src/mini_agent/output.py` | Tell the model how to open a pipe and send EOF; show status and byte counts while hiding the body. |
| `src/mini_agent/agent.py`, `src/mini_agent/__main__.py`, `src/mini_agent/recovery.py` | An in-flight write blocks completion; handoff, resume, and task boundary cleanup finish write threads within bounds. |

## Version Change Map

Legend: `[old]` already in the previous version, `[+]` new in this version, `[~]` changed in this version, `[C]` main consumer, `[B]` boundary of this version.

The input path of `v0.28` ends at start:

```text
[old] start_process(command, cwd?)
       -> ProcessManager: stdin=DEVNULL
       -> the child sees EOF immediately
       -> get/read/wait observe stdout/stderr and exits
       -> terminate/kill or task boundary cleanup
[B] the Agent has no tool to write text to a process
```

`v0.29` adds the capability switch and the write action into the same task boundary:

```text
[+] start_process(command, cwd?, stdin_mode="closed" | "pipe")
       -> [~] closed: DEVNULL; pipe: PIPE + stdin_state=open
       -> [C] write_process(process_id, input, close_stdin?)
             -> ownership / phase / permission / stdin state checks
             -> at most 4096 bytes after UTF-8 encoding
             -> dedicated write thread, the tool round waits at most 2 seconds
             +-> written: bytes written, the pipe is still open
             +-> closed: stdin closed after writing, i.e. EOF sent
             +-> write_pending: still in flight, cannot retry
             +-> error: uncertain or not delivered, handle by error reason
       -> [C] read_process / wait_process observe the process's response
       -> process exits -> ProcessEvent -> successor generation -> independent verification
[B] only a pipe byte stream; no PTY, echo, control characters, or terminal size semantics
[B] the input body never enters State, Trace, results, authorization prompts, or terminal output
```

Note `write_pending` in the diagram: it is neither "the write failed" nor "it was written". The tool has stopped waiting, but the background write thread has not given a final result yet. The task must keep this in-flight resource until a status query or task cleanup confirms it has finished.

## Key Flow: stdin Has Two Layers, "Capability" and "State"

`stdin_mode` says whether a writable pipe was created at start; it is a capability choice. `stdin_state` says whether the pipe can still be written to right now; it is a runtime state. The two must not be confused:

| Start mode/runtime state | Meaning | `write_process` |
| --- | --- | --- |
| `stdin_mode=closed`, `stdin_state=disabled` | No write capability was opened for this process; the child gets EOF | Returns `stdin_not_enabled` |
| `pipe`, `open` | A write can start | Accepts text within the limit |
| `write_pending` | The previous write or flush is still in flight | Does not accept the next one |
| `closed` | EOF was sent; stdin cannot be reopened | Returns `stdin_closed`, or the process has exited |
| `error` | The pipe hit a Broken Pipe or another write error | Returns the recorded error |

EOF (End of File) here is not a special string but the operating system state "the input stream has ended". A program calling `readline()` usually needs a newline first; a program calling `read()` returns only when it reads EOF. So sending `hello\n` and closing stdin are two different actions.

## Core Concept 1: Open the Pipe Explicitly at Start

### What a closed default solves

The `stdin_mode` of `start_process` defaults to `closed`. The implementation connects stdin to `subprocess.DEVNULL`, keeping the earlier behavior that "the child sees EOF immediately". Existing server start commands do not suddenly start waiting for input after the upgrade, and commands that need no input do not get an extra pipe nobody consumes.

Start it like this only when you know the program needs a small amount of input:

```json
{
  "command": "python -u -c 'import sys; print(\"ready\", flush=True); line=sys.stdin.readline().rstrip(\"\\n\"); print(\"reply:\" + line, flush=True); sys.stdin.read(); print(\"eof\", flush=True)'",
  "stdin_mode": "pipe"
}
```

The start result tells the model whether the capability is open:

```json
{
  "process_id": "proc-1",
  "status": "running",
  "stdin_mode": "pipe"
}
```

This small program first outputs `ready` and waits for a line of input; after it receives a newline, it outputs `reply:...`, then keeps waiting for EOF, and finally outputs `eof` and exits. The `-u` and `flush=True` in the command only let the observation tools see output promptly; they do not change the stdin protocol.

### The matching implementation choice

Below is the key part of the start arguments in `v0.29`. It keeps the old behavior in the default branch and limits the new capability to the explicit `pipe` branch:

```python
kwargs = {
    "shell": True,
    "cwd": resolved_cwd,
    "stdin": subprocess.PIPE if stdin_mode == "pipe" else subprocess.DEVNULL,
    "stdout": subprocess.PIPE,
    "stderr": subprocess.PIPE,
}
```

One conclusion is enough when reading this code: whether stdin can be written is decided when `Popen` is created; a closed stdin cannot be turned into a pipe after the process has started.

## Core Concept 2: Validate a Write by Bytes First, Then Wait Boundedly

### Why limit by UTF-8 bytes

The tool receives a Python string, but what is actually written is UTF-8 bytes. An ASCII character is usually one byte; CJK and similar characters usually take three or more bytes. If the limit were counted in characters, `4096` characters could exceed the 4096-byte limit the pipe and protocol are designed for.

So this version encodes first and then checks:

```python
encoded = input_text.encode("utf-8")
if len(encoded) > MAX_STDIN_BYTES:
    raise ValueError("input must not exceed 4096 bytes after UTF-8 encoding")
if not encoded and not close_stdin:
    raise ValueError("close_stdin=true is required when input is empty")
```

One write is at most 4096 UTF-8 bytes. Empty text makes sense only with `close_stdin=true`, because it means "send no body this time, only EOF". The write tool does not add a newline automatically; for programs that need `readline()`, the caller must put `\n` into `input`.

### Why a write thread and a 2-second limit are needed

The other end of the pipe may not be reading for a while. If the tool handler called `write` and `flush` directly on the main thread, one write could stall the whole Agent round. The Manager creates a dedicated thread for every write, and the main tool round waits at most 2 seconds:

```text
start the write
  -> write + flush complete within 2 seconds -> return written or closed
  -> no confirmation within 2 seconds        -> return write_pending
                                                the write thread is still managed by the Manager
```

`write_pending` must be handled as "result unknown". The same text must not be sent again just because the tool round returned: the first write may already have arrived, and sending it again changes what the child receives. The next `get_process`, `read_process`, or `wait_process` syncs `stdin_state`; task boundary cleanup also reclaims this write thread within bounds.

A process has at most one write in flight at a time. When the previous one has not finished, the next write gets an explicit `write_pending` result; two writes never run in parallel on the same pipe.

## Core Concept 3: Let the Result Status Drive the Next Step

### Write a line, then send EOF

Continuing with the input-waiting program above, the model can work in three steps:

Step 1: open the pipe explicitly at start and wait for `ready`:

```text
start_process(..., stdin_mode="pipe")
  -> read_process
  -> stdout: "ready\n", status: "running", stdin_state: "open"
```

Step 2: send one line of text with a newline, without closing the pipe:

```json
{
  "process_id": "proc-1",
  "input": "hello\n",
  "close_stdin": false
}
```

On success, the key fields of the result look like this:

```json
{
  "status": "written",
  "process_id": "proc-1",
  "written_bytes": 6,
  "closed": false,
  "stdin_state": "open",
  "write_pending": false
}
```

This only proves that 6 bytes finished writing and flushing. It does not guarantee the program has finished processing the input, nor that it has exited. Next, use `read_process` to read `reply:hello\n`, or `wait_process` to wait for new output.

Step 3: the example program also calls `sys.stdin.read()` after printing the reply, so EOF needs to be sent separately:

```json
{
  "process_id": "proc-1",
  "input": "",
  "close_stdin": true
}
```

The result is `status=closed`, `written_bytes=0`, `stdin_state=closed`. Then use `read_process` to read `eof\n` and `get_process` to confirm the exit. You can also put the body and EOF in the same call: set `input="hello\n"` and `close_stdin=true`; the result is then `closed`, with `written_bytes` equal to the byte count of the body.

### Error results must not be retried automatically

What the common failure paths mean:

| Result | Meaning | How to respond |
| --- | --- | --- |
| `stdin_not_enabled` | `pipe` was not chosen at start | The only option is to end the process and restart it with `pipe`. |
| `stdin_closed` | EOF was already sent or stdin was closed | It cannot be reopened; check whether the process should have exited. |
| `process_exited` | The process exited before the write | Read the tail output and exit code first. |
| `write_pending` | The write thread has not given a final result yet | Do not send again; watch `stdin_state` afterwards. |
| `broken_pipe` | The child closed the read end | `written_bytes=0` with non-empty input sets `delivery_uncertain=true`; do not retry automatically. |

What makes Broken Pipe special is that the writer cannot reliably know how many bytes arrived before the error. So `written_bytes=0` does not mean "the other end definitely received nothing"; it means no completed byte count is confirmed. The model should treat it as one execution error and handle it based on later process output or the user's decision.

## Core Concept 4: The Body Is Used Only for This Action and Must Not Pollute the Audit State

stdin may contain passwords, tokens, user data, or text that only matters in this interaction. v0.29 still needs to record "a write happened", but it does not need to copy the body into long-term state and diagnostic output. So these observation surfaces keep only safe metadata:

```text
State / Trace        -> process_id, write attempt, byte count, redacted arguments, status
permission prompt    -> process_id, encoded byte count, close_stdin
tool result          -> written_bytes, stdin_state, closed, error type
normal/debug output  -> metadata such as input_bytes, never the body
```

The arguments of the execution attempt are stored in a redacted form, such as `<str:...>`, used to detect repeated calls and replay causality, not to recover the input content. Unknown IDs, oversized arguments, and user denials are also handled before writing, so the body is never handed to the process.

## Implementation Breakdown: Writes Also Go Through the Full Agent Boundary

`write_process` is a `possible` effect, because stdin may make the process keep changing the workspace or the external environment. The executor first validates the arguments and the UTF-8 byte count, then checks whether the current task owns the `process_id`, then passes the planning/repair gate and the PermissionGate; only when all these checks pass does it enter the Manager's write handler. The Manager handler checks ownership and stdin state again, to avoid races between authorization and execution.

So in none of the following cases is the body sent:

- The input exceeds 4096 UTF-8 bytes, or empty input is not paired with `close_stdin=true`.
- The `process_id` is unknown, expired, or belongs to another task.
- The task is in the `exploring`, plan-awaiting-approval, diagnosis, or strict verification phase.
- The user denies the separate permission request for `write_process`.
- The process does not have pipe enabled, stdin is already closed, or the previous write is still in flight.

A write attempt itself also cannot serve as `run_shell(purpose="verification")`. If the write makes the process exit, foreground sync appends an exit event, opens a successor generation, and clears old verification; if the write does not make it exit, the active process or in-flight write still prevents the task from entering `done`.

## Run and Observe

The command below is for Bash/zsh and runs this version's pipe input and redaction boundary scenarios:

```bash
PYTHONPATH=src python -m pytest -q tests/test_process_input_v029.py
```

While running, use the mapping below to check that you understand the results:

| Observation | What it proves |
| --- | --- |
| A default-started process sees EOF immediately, while an explicit pipe process can receive text | The capability is chosen at start, and the default behavior stays compatible. |
| `hello\n` lets `readline()` continue, while empty input plus `close_stdin=true` ends `read()` | A newline and EOF are two different input protocols. |
| CJK input is judged by encoded byte count; exactly 4096 bytes passes, and more is an invalid argument | The limit applies to the UTF-8 bytes actually written. |
| When the write thread is deliberately slowed down, `write_pending` is returned, and the state finishes only later | The tool round is bounded, and the Manager keeps responsibility for the in-flight resource. |
| A unique marker in the input never appears in State, Trace, authorization prompts, or terminal output | The audit keeps action metadata without copying the body. |
| Broken Pipe returns `delivery_uncertain=true` | No automatic retry when delivery cannot be confirmed. |
| After the input makes the process exit, old verification is cleared | A write result cannot replace independent verification after the exit. |

The test files use the standard library to start short-lived subprocesses. Their value is in pinning down concurrency and boundary behavior; when learning, first look at what each result means, then map it back to the responsibilities of `ProcessManager`, `ToolExecutor`, and `AgentState`.

## Why This Design

Closing stdin by default keeps the EOF behavior of existing background commands and keeps processes that need no input from waiting on a pipe that stays open. An explicit `pipe` puts the judgment "I know this program needs input" into the start action; the cost is that the model must choose correctly at start, and a process already started with `closed` cannot get a pipe afterwards.

Limiting writes to UTF-8 text, 4096 bytes, and one in-flight write keeps input, memory, and tool results bounded. A dedicated thread plus a 2-second wait keeps the main Agent round from being stalled by a child that does not read stdin; the cost is that `write_pending` can appear, and the model must wait for the final state instead of retrying by guessing.

Using a pipe instead of a PTY reuses the existing stdout/stderr draining and task cleanup boundaries, and lets the redaction scope of the input body be defined clearly. The cost is that a pipe has no terminal semantics: no input echo, Ctrl-C, signal control characters, terminal size, or full-screen interaction.

## Design Boundaries

- Only processes with `stdin_mode="pipe"` accept `write_process`; processes with the default `closed` get EOF and cannot switch modes at runtime.
- A single input is at most 4096 bytes after UTF-8 encoding; empty input can only send EOF together with `close_stdin=true`; the tool does not add a newline automatically.
- `write_process` is handled as a separate `possible` action by default; unknown IDs, argument errors, phase rejections, and permission denials neither write nor reserve the matching write side effect.
- At most one write in flight at a time; `write_pending` is not a delivery confirmation, and the same body must not be sent again afterwards.
- A write result is not verification; after the process exits, an independent `run_shell(purpose="verification")` must be run in the new generation.
- The input body never enters State, Trace, tool results, permission prompts, or terminal output; State and Trace keep only redacted arguments and safe metadata.
- Task switches, CLI exit, and exception paths reclaim stdin write threads and pipes within bounds; when finishing cannot be confirmed, the old task registration is kept and the reason is reported.
- This version does not support PTY, terminal echo, control characters, terminal size, interactive shell semantics, or cross-session reconnection.

## Version Features, Next Lesson, and Code Index

This lesson lets the Agent start a background process with an explicitly opened pipe, send bounded UTF-8 text, send EOF separately, and keep explainable boundaries in write timeout, repeated write, Broken Pipe, and sensitive body scenarios. If PTY is evaluated later, echo, control characters, terminal size, cross-platform process groups, and the cleanup protocol must be defined separately; this lesson does not describe pipe input as already having those capabilities.

Pinned source entries:

- [Process and stdin lifecycle](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.29/src/mini_agent/processes.py)
- [Process tools and argument validation](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.29/src/mini_agent/tools/process.py)
- [Executor permissions and in-flight checks](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.29/src/mini_agent/tools/base.py)
- [State, generation, and redaction](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.29/src/mini_agent/state.py)
- [Trace validation](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.29/src/mini_agent/trace.py)

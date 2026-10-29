# Lesson 30: Saving the Agent session to disk (v0.30)

Previous: [Driving background processes that wait for input](29-interactive-process.md) · [Tutorial overview](README.md) · Next: [Resuming a session from a complete safe point](31-safe-resume.md)

> Code snapshot: `v0.30` · Adjacent diff: `v0.29..v0.30` · Shell: Bash/zsh

> Requirements: Python 3.10+. This lesson covers only saving and validating a local session; v0.30 cannot yet continue a task with `--resume`.

## Lesson Goals

While the Agent is working, task facts and the conversation live in memory. Once the program exits, the next start does not know how far it got. This lesson first solves "how to leave a trustworthy record", without rushing to solve "how to keep running from that record".

After this lesson, you should be able to explain:

- What `State`, `Context`, and a session each store;
- What a safe point is, and why half a tool round cannot be saved;
- Why `/save` writes only at a safe point, and the difference between `active` and `clean`;
- What problems JSON, SHA-256, atomic replacement, and redaction each solve.

## Problems in the Previous Version

v0.29 can already complete an Agent round: the model makes tool calls, the program runs the tools, and the `role=tool` results go back to the model. The problem is that this information lives mainly in the memory of the current Python process. Saving only `AgentState.snapshot()` is not enough either, because it is a state projection for the model and Trace to read and does not contain the full message history, summaries, or the internal counters needed for recovery.

So this version creates a separate save format: the session. It is a JSON file in a user-private directory that stores both the authoritative task facts and the protocol context. v0.30 only guarantees "this file is a validated, complete record"; turning it into a new runtime across processes is left to the next lesson.

## Prerequisites and Version Checkout

You need basic Python, the command line, and the tool call concepts from Lesson 29. The commands below use Bash/zsh. Switching tags changes the current working tree; after studying, switch back to your development branch according to your own Git workflow. Creating, moving, and pushing tags is done manually by the repository maintainer.

```bash
git checkout v0.29
git diff --stat v0.29..v0.30
git diff v0.29..v0.30 -- src/mini_agent/session.py src/mini_agent/state.py src/mini_agent/context.py src/mini_agent/__main__.py src/mini_agent/config.py
git checkout v0.30
```

## New and Changed Files

First look at `git diff --stat` to confirm that this lesson's changes really center on the chain "export, validate, write, and lifecycle". File names are not the learning focus; the text below explains them in the order they are used.

| File | Change | Purpose |
|---|---|---|
| `src/mini_agent/state.py` | Adds session export and safe point checks | Stores task facts, counters, and checkpoint metadata |
| `src/mini_agent/context.py` | Adds history export, pairing validation, and input redaction | Stores the conversation protocol, not the protected system prompt |
| `src/mini_agent/session.py` | Adds `SessionStore` | Handles the JSON envelope, lock, size limit, hash, and atomic write |
| `src/mini_agent/__main__.py` | Adds `/save` and saving on exit | Writes `active` after a complete round and `clean` after cleanup finishes |
| `src/mini_agent/config.py` | Defines the session file limit in one place | Limits a single file to 16 MiB by default |

## Version Change Map

Legend: `[old]` already in v0.29, `[+]` new in v0.30, `[~]` changed in v0.30, `[C]` main consumer, `[B]` boundary of this lesson.

First the old flow. It can hand tool results back to the model but has no complete save format that the next process can read:

```text
[old] CLI input
  -> [old] agent_loop
  -> [old] tool handler
  -> [old] State facts + role=tool messages
  -> [old] round ends, back to the CLI
  [B] no cross-process resume entry after exit
```

This version adds saving at "a complete round ends" and "task boundary cleanup":

```text
[old] CLI -> agent_loop -> tool handler -> State + role=tool
                                       |
                                       v
                               [+] export State / Context
                                       |
                                       v
                               [+] SessionStore
                                   JSON -> SHA-256 -> atomic replace
                                       |
                                       v
                               [C] active session file

exit, /new, /reset
  -> [old] bounded cleanup of background resources
  -> [+] cleanup facts go into State
  -> [+] save a clean session

[B] active handler, unsettled attempt, active process, or in-flight stdin
  -> refuse to save; do not produce a file that "looks complete"
[B] reading a session in v0.30 only validates and diagnoses; it does not rebuild the runtime or call the LLM
```

## Core Concepts and Data Structures

### 1. Three kinds of "state" are not the same thing

First separate three easily confused words:

- `State` is task facts, such as the task status, plan progress, tool execution records, budgets, and verification records;
- `Context` is the conversation material sent to the model, such as user, assistant, and tool messages and summaries;
- A session is a file format designed for saving/resuming; it puts the first two, together with the internal data recovery needs, into an envelope (an outer JSON container).

`snapshot()` is kept, because the model and Trace need a bounded, readable projection. The session export must be stricter: it must keep the tool-call/result pairing of messages, private counters, and references. Writing a snapshot directly as JSON would miss information the next process needs.

So the save interface exports the two kinds of data separately and lets `SessionStore` combine them; it does not write a temporary snapshot to disk as it is:

```python
state_export = state.export_session()
context_export = context.export_session()
```

### 2. A safe point means "it is OK to stop here"

A safe point is not "there are a bunch of fields in memory right now" but an explicit protocol boundary. At least all of these must hold at once: every assistant tool call in this round has its matching `role=tool` result; State and Context are committed together; there is no running handler, unsettled attempt, active background process, or in-flight stdin write.

A handler here is the Python function that actually performs a tool action, and an attempt is one execution attempt accounted in State. As long as any of them has not finished, the program does not know whether the file should describe things before or after the action, so saving fails and the reason is handed to the CLI.

The normal path: after a tool round returns completely, `active` is updated automatically; entering `/save` saves the current safe point again; on exit, `/new`, or `/reset`, processes are cleaned up first, then the program tries to write `clean`. `active` means "the last safe point exists, but a normal task handoff has not been proven", and only `clean` can serve as a complete handoff record.

For example, the exit handoff ultimately requests the same safe point format and only changes the handoff status:

```python
store.save(session_id, state, context,
           handoff_status="clean", save_kind="safe_point")
```

### 3. How the JSON file avoids "breaking the old record"

The top level of a session contains `schema_version=1`, a random `session_id`, the workspace root path, the save time, `save_kind`, `handoff_status`, State, Context, and integrity fields. The `session_id` identifies the disk file and is not the same as the task's internal `task_id`.

Writing has roughly four steps: generate canonical JSON, compute SHA-256, write a temporary file in the same directory and `fsync` it, and replace the official file with `os.replace`. Below is the key code for the canonical bytes in v0.30; sorting and fixed separators give the same hash for the same content:

```python
def _canonical_bytes(payload):
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
```

Reading first checks the file size, then parses the JSON, validates the version, recomputes the hash, and checks the references in State/Context. The hash can detect truncation or accidental corruption, but it is not cryptographic authentication against malicious tampering; a session should still be treated as sensitive local data.

### 4. The save format also handles privacy

Model messages, file contents, and tool output may contain sensitive information, so sessions live in `~/.mini_agent/sessions/`, with a default limit of 16 MiB per file. `write_process.input` is a special boundary: the history keeps the structure of the tool call and the `tool_call_id`, but the input body is replaced with a placeholder; if a non-empty body appears in ordinary history, a summary, or a Runtime Notice, saving is refused.

This shows that "redaction" does not mean deleting all messages; it removes bodies that must not enter a persisted file while still allowing the call pairing to be checked.

## Why This Design

This version chooses standard-library JSON instead of `pickle` or a general database. JSON can be inspected by hand and does not execute arbitrary Python objects when read; a temporary file in the same directory, `fsync`, and atomic replacement mean an interrupted write leaves the previous complete commit as far as possible. An exclusive lock refuses concurrent writes; a leftover lock is not taken over automatically just because it "looks old", because it may still belong to another CLI.

The costs are also clear: a session may contain conversation, file fragments, and tool output, and must not be shared casually; the 16 MiB limit means space cannot be saved by truncating half a tool round; plain SHA-256 provides no authentication; and most importantly, this version cannot yet continue a task directly from the file.

## Design Boundaries

The supported path: with an active task, entering `/save` gives a random session ID the first time; later safe points of the same task update the same file; on normal exit, after cleanup finishes, it is marked `clean`. When a write fails before replacement, the old file is not overwritten; when directory sync or lock cleanup fails after replacement, the CLI reports "commit status unconfirmed" and the session ID, and does not claim outright which of the old and new files was persisted.

Unsupported paths: saving during an active process, in-flight stdin, half a round of tool results, or an unsettled attempt; starting the next LLM round from a v0.30 file; reconnecting `Popen`, pipes, threads, permission approvals, or checkpoint pre-image bytes across processes. `active` can only be used to diagnose the last safe point; the next lesson defines the safe load entry.

## Key Flow

```text
/save
  -> confirm there is an active task
  -> sync process facts
  -> check whether State / Context are at a safe point
  -> build the envelope and SHA-256
  -> acquire session.lock
  -> write a temporary file, fsync, atomic replace
  -> show session_id

a handler / attempt / process / stdin has not finished
  -> save fails
  -> the old session stays readable
  -> the CLI does not show "saved"

normal exit, /new, or /reset
  -> bounded cleanup of background resources
  -> cleanup fails: keep active and report the specific process or stdin reason
  -> cleanup succeeds: write clean
```

## Implementation Breakdown

`SessionStore` accepts only explicit State/Context exports; it does not let the model choose the save path and does not read `config_local.py`. `AgentState.export_session()` exports the authoritative facts and decides the safe point; `ContextManager.export_session()` handles message pairing, summaries, and redaction. Locks, `ProcessManager`, handlers, and threads are resources of the current process and are not serialized.

Key implementation index:

- [`src/mini_agent/session.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.30/src/mini_agent/session.py): envelope, lock, size check, hash, and atomic commit;
- [`src/mini_agent/state.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.30/src/mini_agent/state.py): authoritative State export and safe point check;
- [`src/mini_agent/context.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.30/src/mini_agent/context.py): history export, message pairing, and `write_process.input` redaction;
- [`src/mini_agent/__main__.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.30/src/mini_agent/__main__.py): `/save`, automatic saving, and the clean handoff order.

## Run and Observe

The command below uses Bash/zsh. After the command-line first task runs, the program still enters the interactive loop; it does not exit right away because the argument task finished.

```bash
PYTHONPATH=src python -m mini_agent "check a small change"
```

At the prompt, enter `/save` and observe that the terminal shows a random session ID; finish another round of the task and enter `/save` again, and the file with the same ID is updated. After entering `exit`, if background resource cleanup succeeds, the final session has `handoff_status: clean`. These observations prove that "it can be written to disk safely after a complete round and lifecycle cleanup"; they do not prove that v0.30 can already resume running.

## Version Features, Next Lesson, and Code Index

What this version adds is a verifiable, atomically saved local session: it stores State, Context, and safe point metadata, protects sensitive input, and distinguishes `active` from `clean`. The next lesson, v0.31, loads a `clean` safe point in a new process, rechecks the workspace, rebuilds the runtime, and invalidates old verification; this lesson does not implement those behaviors in advance.

Core code index: [`session.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.30/src/mini_agent/session.py), [`state.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.30/src/mini_agent/state.py), [`context.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.30/src/mini_agent/context.py), [`__main__.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.30/src/mini_agent/__main__.py).

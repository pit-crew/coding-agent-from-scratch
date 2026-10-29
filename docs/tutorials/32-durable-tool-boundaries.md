# Lesson 32: Writing down the key boundaries of tool calls (v0.32)

Previous: [Resuming a session from a complete safe point](31-safe-resume.md) · [Tutorial overview](README.md) · Next: [Handing off calls after a crash](33-crash-recovery.md)

> Code snapshot: `v0.32` · Adjacent diff: `v0.31..v0.32` · Shell: Bash/zsh

> Requirements: Python 3.10+. This lesson establishes the schema 3 tool boundary but still refuses to resume half a round of tool calls directly; classification and user handoff are left to v0.33.

## Lesson Goals

Imagine a tool round: the model has already said "please write the file", and the program is just about to run it, or the handler has returned but the result has not yet been written back to the session, when the Python process exits. The last clean safe point of v0.31 cannot tell the next start "which step the action stopped at".

This lesson splits that dangerous window into checkable durable facts. After this lesson, you should be able to explain:

- What `pending`, `handler_admitted`, and `committed` each mean;
- Why an admission fact must be committed before the handler;
- Why State, the `role=tool` result, and the call record must be committed together;
- Why the LLM can be requested again only after all calls of the same round are committed;
- Why v0.32 records where an interruption happened but still does not automatically replay old calls.

## Problems in the Previous Version

One tool call involves at least three different facts: the model issued `tool_calls`; the call passed argument, plan, and permission checks; the handler ran, produced a result, and fed back `role=tool`. v0.31 saves a safe point only after a round ends.

If the handler has started and saving then fails, reading the old file next time mixes "may already have run" with "did not run at all". If State has already recorded it but the message history lacks the `role=tool`, the next LLM call also sees an incomplete protocol. So this version adds a single-file `tool_boundary` dedicated to recording the intermediate state of a tool round.

## Prerequisites and Version Checkout

You need basic Python, the command line, and the session, State, and Context concepts from Lesson 31. Commands use Bash/zsh; a tag is a fixed learning snapshot.

```bash
git checkout v0.31
git diff --stat v0.31..v0.32
git diff v0.31..v0.32 -- src/mini_agent/session.py src/mini_agent/context.py src/mini_agent/state.py src/mini_agent/tools/base.py src/mini_agent/agent.py
git checkout v0.32
```

## New and Changed Files

The main thread of this version is "record at round start → admit before the handler → commit results and facts together → finish the whole round".

| File | Change | Purpose |
|---|---|---|
| `src/mini_agent/session.py` | Adds schema 3 and `tool_boundary` | Validates calls, results, State, and order, and saves atomically |
| `src/mini_agent/context.py` | Adds export of the result prefix of the last round | Allows a controlled half-round context when saving at a boundary |
| `src/mini_agent/state.py` | Adds a boundary-only pending export | Stores references to attempts, budgets, and generations |
| `src/mini_agent/tools/base.py` | Splits into `admit()` and `execute_admitted()` | Separates "allowed into the handler" from "actually running" |
| `src/mini_agent/agent.py` | Adds per-call commits and whole-round finish | Keeps State, messages, and boundary records advancing in sync |
| `src/mini_agent/__main__.py`, `resume.py` | Connect schema 3 | Distinguish save failures and keep refusing half-round safe resume |

## Version Change Map

Legend: `[old]` already in v0.31, `[+]` new in v0.32, `[~]` changed in v0.32, `[C]` main consumer, `[B]` boundary of this lesson.

The old flow has only one complete finish:

```text
[old] assistant tool_calls
  -> [old] handler
  -> [old] State + role=tool
  -> [old] clean safe point
  [B] on a mid-round exit, the disk has no fact about whether the handler was entered
```

This version turns a tool round into a series of constrained durable (written to disk and validated) commits:

```text
[old] assistant tool_calls
  -> [+] pending round commit
  -> [+] argument / plan / permission / budget checks
  -> [+] handler_admitted + attempt/generation commit
  -> [old] handler
  -> [+] State + role=tool + call committed commit
  -> [+] all calls committed
  -> [C] the next LLM request is allowed

[B] any commit fails
  -> do not go to the next step, do not request the next LLM
[B] pending or partially committed
  -> v0.32 only saves the interruption facts; no automatic resume or replay
```

## Core Concepts and Data Structures

### 1. `pending` first records "what the model asked for"

When a tool round starts, the agent loop writes the assistant message and the call order into `tool_boundary`. Each call gets a stable `invocation_id` while keeping the model's original `tool_call_id`. This step happens before any handler.

A simplified record:

```json
{
  "schema_version": 3,
  "save_kind": "tool_boundary",
  "tool_boundary": {
    "round_id": 4,
    "status": "pending",
    "calls": [{
      "invocation_id": "r-4-c-0",
      "tool_call_id": "call-7",
      "tool": "write_file",
      "effect_class": "possible",
      "permission": "not_checked",
      "handler_admitted": false,
      "attempt_id": null,
      "status": "pending"
    }]
  }
}
```

`pending` here only means "the boundary record is on disk". It does not mean the handler has started, and it does not mean the file write succeeded. It only leaves the last explicit position for diagnosis after a crash.

The argument summary is redacted: bodies such as `content`, `command`, and `input` keep only their type, length, or a placeholder; in particular, `write_process.input` must never become replayable stdin.

### 2. Commit admission before the handler

The handler is the function that actually runs the tool; admission is the executor's confirmation that "this call can now enter the handler". The admission check covers whether the tool exists, whether the arguments match the schema, whether the current plan/repair phase allows it, whether permission allows it, and whether an attempt and a generation need to be reserved.

The order must be:

```text
admit()
  -> write permission / handler_admitted / attempt / generation
  -> execute_admitted()
```

If writing the admission fact fails, `execute_admitted()` must not be called. This rule matters especially: when saving fails, it is better to leave `pending` than to let an action that has already changed the outside world have no durable boundary at all.

Permission denials or argument errors do not enter the handler, but they still produce a definite tool result; they are not "unknown side effects". Plan tool validation failures also keep using `plan_rejected`; the new persistence does not change the existing plan semantics.

### 3. One tool result maps to one atomic commit

After the handler returns, the main thread completes one commit in the model's order:

1. State records the `ExecutionResult`, that is, the facts of this execution;
2. Context appends the matching `role=tool` message;
3. `tool_boundary` marks this call as `committed` and writes the result reference;
4. All three atomically replace the session file together.

`role=tool` is the tool result message in the model protocol and must carry back the original `tool_call_id`. A call counts as committed only when State, the message, and the call record are all readable; only after every call in the same round is committed is the whole round committed, and only then can the agent loop request the model again.

Some read-only calls with `effect_class=none` can wait concurrently, but commits still happen in the model's order. Even if a later result returns first, it cannot jump ahead of an earlier call that is not yet committed. Calls with `effect_class=possible` keep running in the existing order, and `run_shell` is still possible.

### 4. Different failures must each have a result too

A nonexistent tool, invalid arguments, a permission denial, a handler exception, a plan rejection, and an asynchronous process exit must not leave the model protocol one result short. Each original call maps to exactly one `role=tool`; but the result can express an error or uncertainty.

The point of this invariant: what the model sees next round is a complete round, not "two calls but only one result came back". A complete protocol does not mean all tools succeeded.

## Why This Design

This version uses the same atomic JSON file rather than introducing a journal. This keeps State, Context, and the call boundary consistent within one replacement, and readers only need to understand one authoritative file. The cost is that every small commit writes the file, so disk writes are more frequent; and the file may still stop at pending before the handler returns.

This version puts the "admission fact" before the handler to answer "has it earned the right to execute", not to claim that a side effect has happened. Even with `handler_admitted=true`, the process may exit inside the handler; if the effect is possible, the external result of a file or shell action is even less inferable directly from the session.

So v0.32 only promises to record the interruption window precisely, not to replay automatically. The next lesson classifies these pending calls and hands them to the user to decide how to investigate.

## Design Boundaries

The supported path: save pending at round start; save `handler_admitted` after admission completes; after the handler returns, commit State, `role=tool`, and the call record together; allow the next LLM only after all calls are committed. The session is still one schema 3 JSON file, with no separate journal.

Unsupported paths: inferring from pending that the handler definitely did not run; using redacted arguments as retry credentials; automatically replaying `write_file`, `run_shell`, process control, or stdin writes after an interruption; continuing to request the model while some `role=tool` is missing. v0.33 handles the recovery handoff of "uncertain calls".

## Key Flow

```text
assistant tool_calls
  -> pending round commit
  -> preflight / permission / reservation
  -> handler_admitted commit
  -> handler
  -> State + role=tool + call committed commit
  -> all calls committed
  -> complete round
  -> next LLM request

any durable commit fails
  -> stop at the current boundary
  -> do not enter later handlers, do not request the next LLM
```

## Implementation Breakdown

[`src/mini_agent/session.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.32/src/mini_agent/session.py) defines schema 3, call references, order validation, and atomic replacement; [`src/mini_agent/context.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.32/src/mini_agent/context.py) only allows the last round to export a result prefix in the model's order; [`src/mini_agent/state.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.32/src/mini_agent/state.py) lets referenced pending attempts through only when saving at a boundary.

`admit()` and `execute_admitted()` in [`src/mini_agent/tools/base.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.32/src/mini_agent/tools/base.py) separate admission from the handler; [`src/mini_agent/agent.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.32/src/mini_agent/agent.py) handles round start, per-call commits, feedback in model order, and whole-round finish. `__main__.py` and `resume.py` separate save failures from ordinary tool errors and keep refusing half-round safe resume.

## Run and Observe

The command below uses Bash/zsh. After the command-line first task runs, the program still enters the interactive loop.

```bash
PYTHONPATH=src python -m mini_agent "check a small change"
```

During the task, enter `/save` to turn on persistence and record the session ID. After one round of tool calls finishes, open `~/.mini_agent/sessions/<session_id>.json`; you should see `schema_version: 3`; when a full round ends, `tool_boundary.status` is `committed`, every call is also `committed`, and every assistant tool call in the history is followed by its matching `role=tool`.

If a fault happens mid-round, the file may keep `pending` or have only some calls committed. The expected behavior in v0.32 is to save these facts and refuse to treat them as a complete safe point; the next lesson explains why it cannot simply continue.

## Version Features, Next Lesson, and Code Index

What this version adds is schema 3, the admission commit before the handler, an atomic result commit per call, the whole-round complete constraint, and commits of asynchronous process facts. It adds no journal, does not treat pending as "not executed", and does not change the existing semantics of `run_shell=possible`, the PermissionGate, or plan rejection.

The next lesson, v0.33, reads an active pending boundary, classifies calls into definitely not executed and uncertain side effects, derives a new session, and lets the user hand them off one by one with `/resolve`.

Core code index: [`session.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.32/src/mini_agent/session.py), [`context.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.32/src/mini_agent/context.py), [`state.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.32/src/mini_agent/state.py), [`tools/base.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.32/src/mini_agent/tools/base.py), [`agent.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.32/src/mini_agent/agent.py).

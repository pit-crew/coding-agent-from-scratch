# Lesson 31: Resuming a session from a complete safe point (v0.31)

Previous: [Saving the Agent session to disk](30-session-persistence.md) · [Tutorial overview](README.md) · Next: [Durable tool execution boundaries](32-durable-tool-boundaries.md)

> Code snapshot: `v0.31` · Adjacent diff: `v0.30..v0.31` · Shell: Bash/zsh

> Requirements: Python 3.10+. This lesson resumes only a complete `clean` safe point; it does not resume interrupted tool calls.

## Lesson Goals

The previous lesson left a trustworthy session file, but "the file is complete" does not mean "it is safe to continue now". After saving, the workspace may have changed; the permissions, file handles, and background processes in the old Python process cannot come back automatically from JSON either.

After this lesson, you should be able to explain:

- Why the workspace manifest must be checked before resuming;
- Why a candidate runtime is built first, before the session is claimed;
- Why, after resuming, `AGENTS.md` must be rediscovered, the permission gate rebuilt, and old verification invalidated;
- Why old PIDs and checkpoint metadata can only be used for audit and cannot keep controlling resources.

You will also see the real behavior of `--resume <session_id>`: on success, it shows the resumed task and waits for input; it does not send a request to the LLM automatically.

## Problems in the Previous Version

v0.30 can save State and Context, but reading a session only validates the format and diagnoses. If a new process treated the JSON directly as "current facts", it might continue in a workspace whose files have changed; if it used the saved PIDs directly, it might control a process belonging to another task.

This version defines resuming as a new handoff: first confirm that the workspace recorded at save time still matches, then recreate State, Context, the tool registry, the process manager, and the PermissionGate from the facts on disk. Only when these objects are ready, and the original session checks out again under an exclusive lock, does the CLI take over.

## Prerequisites and Version Checkout

You need basic Python, the command line, and the session concepts from Lesson 30. The commands below use Bash/zsh. A tag is a fixed learning snapshot; after switching, go back to your development branch according to your own Git workflow.

```bash
git checkout v0.30
git diff --stat v0.30..v0.31
git diff v0.30..v0.31 -- src/mini_agent/session.py src/mini_agent/resume.py src/mini_agent/state.py src/mini_agent/context.py src/mini_agent/__main__.py
git checkout v0.31
```

## New and Changed Files

This version spans four stages: check whether resuming is possible, turn the data back into runtime objects, commit a new active generation, and hand the result to the CLI. The "runtime" here means the objects in the current process that actually hold tools and resources.

| File | Change | Purpose |
|---|---|---|
| `src/mini_agent/session.py` | Adds schema 2, the workspace manifest, and resume claiming | Rechecks the original commit and writes a successor `active` session |
| `src/mini_agent/resume.py` | Adds resume admission and runtime assembly | Reads and checks first, then creates the candidate runtime |
| `src/mini_agent/state.py` | Adds strict restore and the resume generation | Restores authoritative facts and clears old verification eligibility |
| `src/mini_agent/context.py` | Adds history restore | Restores message order and summaries and reattaches protected messages |
| `src/mini_agent/instructions.py` | Rediscovers project instructions | Builds the system prompt from the current workspace's `AGENTS.md` |
| `src/mini_agent/__main__.py` | Adds `--resume` | Replaces the CLI runtime only after the claim commit succeeds |
| `src/mini_agent/checkpoint.py`, `processes.py` | Import audit information about old resources | Make clear that old PIDs and old checkpoints cannot be operated |

## Version Change Map

Legend: `[old]` already in v0.30, `[+]` new in v0.31, `[~]` changed in v0.31, `[C]` main consumer, `[B]` boundary of this lesson.

The v0.30 entry is short:

```text
[old] --resume input
  -> [old] SessionStore.load()
  -> [old] validate JSON / hash
  -> [old] can only show diagnostics
  [B] no State, Context, tool, or permission objects to keep running
```

v0.31 inserts resume admission between reading and handing over to the CLI:

```text
[old] --resume <session_id>
  -> [~] load + schema / field / reference / SHA-256 validation
  -> [+] compare the workspace manifest
  -> [+] restore State / Context
  -> [+] rediscover AGENTS.md, create Registry / ProcessManager / PermissionGate
  -> [+] open a resume generation, clear current verification
  -> [+] reread the original clean commit inside the exclusive lock
  -> [+] atomically write the successor active session
  -> [C] the CLI shows the task status and waits for input

[B] schema 1, active, workspace changes, incomplete checks, active old processes
  -> rejected; no LLM call, no handler run, the current runtime is not replaced
[B] old PID / process_id / checkpoints missing pre-image bytes
  -> keep only audit information; no control or rollback
```

## Core Concepts and Data Structures

### 1. The workspace manifest is the "comparison table before resuming"

The workspace is the directory where the project lives. The workspace manifest is not a backup of the whole directory but a bounded baseline assembled from task facts at save time: files the task touched record their type and SHA-256, directories it touched record their entries, and paths that cannot be fully checked are marked explicitly as not recoverable.

The fields resume admission really cares about can be simplified like this:

```json
{
  "schema_version": 2,
  "save_kind": "safe_point",
  "handoff_status": "clean",
  "workspace_manifest": {
    "complete": true,
    "recoverable": true,
    "entries": [
      {"path": "src/app.py", "kind": "file", "sha256": "..."}
    ]
  }
}
```

Resuming compares the workspace root path, file types, file contents, and directory members. The manifest does not cover every external system a shell may touch, so "the manifest did not change" only means the recorded scope did not change, not that nothing in the world changed.

### 2. Resuming has two phases: "prepare a candidate" and "formally claim"

`prepare_resume()` reads, validates, and assembles in memory; it does not call the LLM or run tools. It first restores State and Context from the JSON, then creates a new tool registry, process manager, and permission gate.

After the candidate objects are ready, `claim()` rereads the file inside the session's exclusive lock, rechecks the original hash, `clean`, `safe_point`, and the commit generation, and checks the workspace again. Only on success does it atomically write the successor `active` session and finally hand the candidate runtime to the CLI. If the file or the workspace changes between preparation and claiming, resuming is refused.

The entry relationship in code is below; the key point is "a failure at any step leaves no execution capability":

```python
candidate = prepare_resume(store, session_id, workspace_root)
runtime = candidate.claim()
```

### 3. Resuming opens a new execution generation

A generation can be understood as the number of a task execution boundary. Resuming appends a new generation with `open_reason="resume"` and clears the current `verification_evidence`, but keeps the append-only `verification_history`.

This separates two things: old records remain available for Trace auditing, while "what verification the current workspace passed after resuming" must be produced again. Plan revisions, progress, the user's plan decisions, budgets, and failure causality are still restored; resuming does not approve plans, increase budgets, or clear `blocked` / `failed` automatically.

The implementation first restores State, then explicitly opens the resume generation:

```python
state = AgentState.restore_session(raw_state, root)
state.begin_resume()
```

### 4. Old resources are records, not handles

`Popen` objects, pipes, threads, and the PermissionGate's runtime approvals exist only in the old process. A process record in the session can only say "a PID was registered in the past"; it cannot let the new process regain control. The new `ProcessManager` skips historical `process_id`s and does not take over old PIDs.

Checkpoints are the same: v0.31 imports only metadata and does not save pre-image bytes, so an old `ready` checkpoint is marked `unavailable` and cannot pretend that rollback is possible.

When creating the new process manager, historical IDs are used only as an "avoid list", not passed in as old handles:

```python
historical_process_ids = [item.process_id for item in state.processes]
process_manager = ProcessManager(historical_process_ids=historical_process_ids)
```

## Why This Design

This version uses a workspace manifest instead of copying the whole directory. That keeps sessions bounded and lets it check the files the task explicitly touched; the cost is that undeclared external effects of shell commands are outside the manifest's coverage. This version also does not guess from shell text what a command will change, and certainly does not treat "no change observed" as "definitely no change".

This version uses "build first, claim later". If the session were changed to `active` first and State or the current project instructions then could not be rebuilt, the user would get a session that is already claimed but cannot run; if the candidate were handed to the CLI first, the next round might start even though the claim failed. The current order keeps failures outside the current runtime.

Rebuilding the PermissionGate and project instructions also has a cost: `once` / `always` approvals from the old process are not inherited, and later side-effect tools may need to ask again. The benefit is that resuming never quietly reuses old environment approvals or old rules.

## Design Boundaries

The conditions for resuming: schema 2, `save_kind=safe_point`, `handoff_status=clean`, integrity validation passes, and the workspace manifest still matches. After a successful resume, it only shows the task and waits for user input; it does not request the LLM automatically just because a task exists in the file.

Cases that cannot be resumed include: schema 1, an `active` session, hash/reference corruption, a changed workspace root path, changed files or directories, an incomplete manifest, old background processes still active, an in-flight stdin write, and interrupted tool calls. An abnormal exit leaves `active`, and the same session cannot go through safe resume directly again.

## Key Flow

```text
--resume <id>
  -> limit size, parse, validate schema / fields / references / SHA-256
  -> compare the workspace root path and manifest entries
  -> restore State / Context, rediscover project instructions
  -> create a new Registry / ProcessManager / PermissionGate
  -> clear current verification, append a resume generation
  -> recheck the original clean safe point inside the lock
  -> atomically write the successor active
  -> the CLI shows the task status and waits for user input

any step fails
  -> no LLM call, no handler run, the current runtime is not replaced

normal exit
  -> bounded cleanup -> write clean
abnormal exit or cleanup failure
  -> keep / report active; a later direct resume is refused
```

## Implementation Breakdown

`SessionStore.claim_resume()` is responsible for the in-lock recheck and the successor file commit; `prepare_resume()` in `resume.py` is responsible for resume admission and object assembly. With the two separated, the CLI does not need to mix path checks, JSON restoration, and runtime replacement into one interactive branch.

[`src/mini_agent/state.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.31/src/mini_agent/state.py) restores the JSON into plans, attempts, failures, recoveries, verification, and process audit records, and `begin_resume()` opens a new generation. `snapshot()` still recomputes the Todo and active plan projections and does not directly trust derived fields that may be duplicated in the file.

[`src/mini_agent/context.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.31/src/mini_agent/context.py) restores the message history and summaries, and requires every assistant `tool_calls` to be followed immediately by ordered `role=tool` results; redacted input is still only a display placeholder and cannot turn back into the stdin body.

[`src/mini_agent/instructions.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.31/src/mini_agent/instructions.py) rediscovers the current project instructions; [`src/mini_agent/__main__.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.31/src/mini_agent/__main__.py) replaces the local State, Context, Registry, ProcessManager, and ToolExecutor only after `claim()` succeeds. Trace still reads only the State snapshot already loaded; see [`src/mini_agent/trace.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.31/src/mini_agent/trace.py) for the entry.

## Run and Observe

The command below uses Bash/zsh. After the command-line first task runs, the program still enters the interactive loop.

First start a task with v0.31, enter `/save`, then enter `exit` normally and note the session ID the terminal shows. Then close the old process and run in a new Python process:

```bash
PYTHONPATH=src python -m mini_agent --resume <session_id>
```

The expected behavior: first you see "session resumed" and the original task/plan status, then the input prompt; no new model request is made before you enter the next task or a CLI decision such as `/approve`. If you change a file in the manifest before resuming, the expected result is "workspace check failed", and no runnable successor session is produced.

These observations prove, respectively: Context/State were read back, the resume entry is not an automatic agent loop, and the workspace really was checked before resuming.

## Version Features, Next Lesson, and Code Index

What this version adds is rebuilding the runtime from a complete `clean` safe point: a schema 2 workspace baseline, in-lock claiming, rebuilding current instructions and permissions, a new resume generation, and turning old resources into audit records. The next lesson, v0.32, narrows the dangerous window "after a tool starts and before its result is on disk"; this lesson does not resume an interrupted handler.

Core code index: [`session.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.31/src/mini_agent/session.py), [`resume.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.31/src/mini_agent/resume.py), [`state.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.31/src/mini_agent/state.py), [`context.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.31/src/mini_agent/context.py), [`__main__.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.31/src/mini_agent/__main__.py).

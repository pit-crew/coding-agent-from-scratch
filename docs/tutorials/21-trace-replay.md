# Lesson 21: Task trace replay (Trace & Replay, read-only) (v0.21)

Previous: [Repair loop](20-repair-loop.md) · [Tutorial overview](README.md) · Next: added as needed

> Code snapshot: `v0.21` · Adjacent diff: `v0.20..v0.21` · Shell: Bash/zsh

> Requirements: Python 3.10+; the core runtime uses only the standard library.

## Lesson Goals

The repair loop lets the Agent go from failure to recovery, but after a run ends, readers still need to answer one question: which state transitions did this task actually go through? This lesson adds Trace & Replay, which reorganizes the structured facts already saved for the current process and current task by generation (the boundary of verification evidence).

After this lesson, you should be able to explain:

- Why the Todo needs a full snapshot of every successful submission, not only the current list;
- How `ExecutionAttempt`, `FailureEvent`, `RecoveryAction`, and verification evidence form a causal chain;
- Why broken chains and cross-generation evidence can only be shown as incomplete and must not be guessed by the replayer;
- Why `/trace` is a diagnostic observation entry, not an entry for re-execution, recovery, or importing history.

## Problems in the Previous Version

v0.20 already saves execution attempts, failures, recoveries, generations, and the current generation's verification evidence. But current evidence is cleared when a new generation opens; this is the correct behavior to keep old evidence out of the completion decision, but it also means that evidence cannot carry cross-generation audits on its own. Meanwhile, readers still have to join several arrays by ID by hand; the Todo also keeps only the current version, so there is no way to know in which generation the plan changed.

If the display layer guessed causality only from list order, one missing reference could be misread as "recovery succeeded" or "verification passed". So the focus of v0.21 is not a new execution capability but a conservative read-only view: edges that can be confirmed are connected explicitly, and edges that cannot be confirmed keep their original records and are marked unresolved.

## Prerequisites and Version Checkout

Read Lesson 20 first. The commands below view this version's scope in Bash/zsh; the `v0.21` tag is created by the publisher after the implementation passes acceptance, and if it does not exist locally yet, run the diff commands once the tag is available.

```bash
git checkout v0.20
git diff --stat v0.20..v0.21
git diff v0.20..v0.21 -- src/mini_agent/state.py src/mini_agent/trace.py src/mini_agent/__main__.py
git checkout v0.21
```

## New and Changed Files

The teaching thread of this lesson focuses on audit snapshots, replay assembly, and the explicit CLI entry; the full scope follows the actual `git diff --stat`.

| File | Change | Purpose |
|---|---|---|
| `src/mini_agent/state.py` | Adds the `TodoRevision` audit snapshot | Records every successful Todo submission and its generation |
| `src/mini_agent/trace.py` | Adds a read-only API and renderer | Validates references, builds the generation view, outputs causal edges |
| `src/mini_agent/__main__.py` | Adds the `/trace` branch | Shows the replay directly before `run_task()` |
| `tests/test_trace_replay_v021.py` | Adds replay regression coverage | Pins down read-only, safety, broken-chain, and real tool chain behavior |
| `docs/tutorials/21-trace-replay.md` | Adds this lesson | Explains the replay entry and its boundaries |

## Version Change Map

First the real finish of v0.20, then the observation path v0.21 inserts. `generation` in the diagram is a verification boundary, not a file system snapshot.

```text
v0.20 baseline:
[old] LLM -> agent_loop -> ToolExecutor -> AgentState
                                       ├-> ExecutionAttempt
                                       ├-> FailureEvent -> RecoveryAction
                                       └-> verification evidence
                                       -> Structured State / next LLM round
                                       -> continue / done / blocked / failed

v0.21:
[old] AgentState.snapshot()
        ├-> [old] execution fact arrays
        ├-> [+] TodoRevision array (appended on successful submission)
        ├-> [+] verification_history (append-only audit evidence)
        └-> [+] trace.build_trace() -> grouping by generation and integrity checks
                                      -> trace.render_trace() -> /trace CLI
                                      ├-> [B] does not call the LLM, tools, or PermissionGate
                                      └-> [B] broken chains are only shown as unresolved, never guessed
```

The key change is the entry position: `/trace` is intercepted in the interactive branch and runs `snapshot → build_trace → render_trace` directly. It does not enter `run_task()`, so it neither appends user history nor triggers the Agent Loop.

## Core Concepts and Data Structures

### 1. TodoRevision is the audit fact of a successful submission

The problem is that "the current Todo" cannot answer "when did the plan change". `TodoRevision` is an immutable record appended inside the same State lock after every successful validation in `update_todos()`:

```text
TodoRevision
- revision_id: 1, 2, ... (renumbered per task)
- generation_id: the generation at submission time
- todos: full TodoItem snapshot
- current_goal: the in-progress goal at submission time
```

A failed validation never enters the locked commit, so it produces no revision. `begin_task()` and `/reset` clear the records and reset numbering; these records appear only in the `snapshot()` used for replay and are not injected into Structured State by `context.py`, so the whole Todo history does not inflate the LLM context.

This design separates two problems: the current Todo keeps serving normal execution, and `todo_revisions` only serves after-the-fact observation. Concurrent updates get revision numbers in the order they actually acquire the State lock, not by guessing from thread start time.

### 2. Replay is a reorganization of structured facts

The Python API is small:

```python
from mini_agent.trace import build_trace, render_trace

report = build_trace(state.snapshot())
print(render_trace(report))
```

`build_trace()` does not take an `AgentState`, only a snapshot. This is a deliberate boundary: it cannot access private original arguments, the retry argument cache, or checkpoint pre-images, and it cannot use conversation summaries to recover facts. The report includes task information, the query scope, generations sorted by `generation_id`, and each generation's Todo revisions, attempts, failures, recovery actions, and verification history.

State keeps two verification views at the same time: `verification_evidence` keeps only the current generation and decides whether the task can finish; `verification_history` is append-only within a task and is used to replay earlier failed or successful verifications. Opening a new generation still clears the former but not the latter, so replay does not change the old-evidence isolation rule.

The diagnosis shown for each failure follows a facts-first order: if there is a `FailureEvent.cause_hint`, it is shown with its source marked; otherwise the linked `RecoveryAction.reason` is looked up; if neither exists, "no diagnosis recorded" is shown. The replayer does not write this reason back into the `FailureEvent`.

### 3. Causal edges and integrity

The replayer does not treat "appearing next to each other" as causality; it uses IDs State has already saved:

```text
generation opener
attempt -> failure
failure -> recovery
recovery -> successor generation / result attempt
attempt -> verification evidence
```

It checks for duplicate IDs, missing or non-contiguous generations, the opener type and owning generation, two-way attempt/failure references, the successor and result of accepted recoveries, whether a verification attempt has unique same-generation history evidence, and whether Todo revisions reference existing generations.

The check result goes into `report["integrity"]`:

```text
{"status": "complete", "issues": []}
{"status": "incomplete", "issues": ["..."]}
```

Even when the state is corrupted, the original records that can be located are still shown; edges that cannot be confirmed are shown as `UNRESOLVED`. Only invalid query arguments or a nonexistent requested generation raise `TraceQueryError`. This means `incomplete` is "this evidence cannot pass full acceptance", not "the display fixed the chain for the user".

## Key Flow

```text
interactive input /trace [generation_id]
  -> current task check
  -> state.snapshot()
  -> build_trace(snapshot, generation_id?)
       ├-> validate IDs, generations, and cross-generation references
       ├-> group original records by generation
       └-> generate resolved / unresolved causal edges
  -> render_trace(report)
  -> force-visible CLI notice
```

If there is a successor generation, the current generation's conclusion is shown as `continue`; the last generation shows `continue`, `done`, `blocked`, or `failed` according to State. `blocked` and `failed` also show the `terminal_reason` and the last confirmable failure.

## Run and Observe

Start interactive mode in Bash/zsh:

```bash
PYTHONPATH=src python -m mini_agent
```

After the task has run at least one round, enter `/trace` to see all generations; enter `/trace 3` to see only generation 3. Even with `OUTPUT_MODE=quiet`, an explicit `/trace` still outputs through a force-visible CLI notice. When there is no active task, the generation argument is not a non-negative integer, or the generation does not exist, the entry gives a clear message.

When you look at the replay, read `Integrity` first, then each generation's `Attempts`, `Failures`, `Recovery actions`, and `Verification evidence`. The execution result of a recovery action only says the recovery tool ran; only new verification evidence in a successor generation with a clear source attempt can support a completion conclusion.

## Why This Design

- "Snapshot API + purely functional report" was chosen instead of letting the CLI read private State fields directly, so that replay cannot bypass the lock, executor, or permission boundary, and so tests can easily check that the snapshot is identical before and after.
- Explicit unresolved edges were chosen instead of discarding corrupted records, so manual diagnosis can see the break points; the cost is that the report may be incomplete and cannot derive missing causality for the user.
- Todo revisions use full snapshots of bounded size per submission, which can explain plan changes but are still kept only within the current process; this is not a database and provides no cross-task history.
- The renderer shows the attempt results, durations, exit codes, error kinds, argument hashes, redacted arguments, and bounded output summaries State has already saved; it does not read private original arguments or checkpoint bytes, and it hides absolute paths.

## Design Boundaries

This version replays only facts produced after the v0.21 upgrade, within the current process and current task. After `/reset` or `/new`, the old task's facts are cleared with State; import, export, cross-process persistence, re-execution, automatic repair, and recovery are not supported.

Replay does not call the LLM, run tools, request permissions, or change history, State, budgets, or generations. It also does not interpret "missing evidence" as a failure cause: broken chains, cross-generation verification, missing source attempts, and reuse of old evidence only lower the `integrity`; they never generate a diagnosis that does not exist.

## Implementation Breakdown

When updating the Todo, `state.py` validates completely first, then, inside the lock, replaces the current list, updates `current_goal`, and appends a `TodoRevision`; when recording verification, it updates both the current evidence and the audit history. A recovery generation links to its RecoveryAction only through `opened_by_recovery_id`, and a recovery attempt links to the failure that triggered it only through `caused_by_failure_id`, so no node has more than one direct causal predecessor. `trace.py` copies only fields allowed for display: attempts use the argument hash, redacted arguments, and `output_excerpt`; recoveries use the reason, status, checkpoint ID, and result references; verifications use the command, result, exit code, output, and generation. `__main__.py` handles `/trace` before `run_task()`, so replay is not affected by the Agent Loop condition "finish only without tool_calls".

A normal failure—recovery—verification chain gets `complete`; if a source attempt is deleted, the report still keeps the failure or verification, but the matching edge is unresolved and the final integrity is `incomplete`. This is the acceptance value of the replayer: it can prove that the chain saved by the runtime is complete, and it can state clearly what the current snapshot is not enough to prove.

## Version Features, Next Lesson, and Code Index

This version adds Todo submission auditing, a read-only Trace & Replay Python API by generation, a text renderer, and the `/trace [generation_id]` CLI. With this, Stage 6 can put failures, diagnoses, recoveries, successor generations, verification, and terminal states into one checkable causal report.

The next lesson is added according to the roadmap; later capabilities must not turn this version's read-only replay entry into automatic execution or a cross-process history system.

Code index:

- [`state.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.21/src/mini_agent/state.py): `TodoRevision`, task boundaries, and snapshots;
- [`trace.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.21/src/mini_agent/trace.py): `build_trace()`, integrity checks, causal edges, and `render_trace()`;
- [`__main__.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.21/src/mini_agent/__main__.py): the interactive `/trace` entry;
- [`tests/test_trace_replay_v021.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.21/tests/test_trace_replay_v021.py): replay, corrupted snapshots, safety boundaries, and real registry tool chain coverage.

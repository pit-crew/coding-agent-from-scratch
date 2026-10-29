# Stage 9: Session Persistence & Resume Implementation Plan

> Status: complete (`v0.30`–`v0.33`)
> Prerequisite stages: Stage 6 reliable execution (`v0.17`–`v0.21`), Stage 7 structured planning (`v0.22`–`v0.25`), and Stage 8 process management (`v0.26`–`v0.29`)
> Suggested version range: `v0.30`–`v0.33`

v0.30 first writes schema 1; v0.31 writes schema 2; the new write format of v0.32 is `schema_version=3`, which adds `tool_boundary` in the same atomic file. Schema 1 can still be read for diagnosis, clean safe points of schema 2 can still be resumed and are upgraded to schema 3 when claimed for resume. Persistence is turned on explicitly when the user enters `/save` in the current task; the first time generates a random `session_id`, and the file is written to `~/.mini_agent/sessions/<session_id>.json`; later safe points and tool boundaries update the same file automatically. `active` means the last save is a diagnosable commit, and `clean` is committed only after a normal exit or task switch has completed bounded process cleanup. v0.33's `--resume` distinguishes a clean safe point from an active pending tool boundary: the former is claimed on the original session, while the latter derives a new session and enters the uncertain call handoff, without calling the LLM automatically or replaying handlers.

## 1. Goal and Positioning

Current task facts are stored in `AgentState`, message history and summaries are held by `ContextManager`, and runtime permission approvals, file checkpoint pre-image bytes, and background process handles stay in their own in-memory objects. After the CLI exits, a new Python process cannot continue the same task. `AgentState.snapshot()` can serve read-only Trace replay, but it is not a complete recovery format: it lacks all private counters, original recovery arguments, the message history, and checkpoint bytes.

The question Stage 9 answers: **can the Agent continue the same task across Python processes without re-executing uncertain side effects, breaking the tool call protocol, or reusing stale verification evidence?**

Target flow:

```text
current task → complete safe point → durable session → CLI exits
                                                 ↓
new CLI → validate session / workspace → rebuild State and Context → reauthorize → continue the task

tool call → durably record pending → execute → durably commit the result and State / history
                         ↓ abnormal interruption
                 detect unfinished calls → judge whether side effects are uncertain → investigate / verify / user decision
```

The four versions solve, in turn, data representation, safe resume, tool boundaries, and abnormal interruptions. The core implementation uses only the standard library, and the storage file is never treated as a source of facts the model can change.

## 2. Scope and Non-Goals

### 2.1 Scope of this stage

- Create a private session format for a single local task with a version number, integrity information, and workspace identity; persist task facts, protocol messages, context summaries, and the internal state needed for recovery.
- Resume across processes from a complete safe point, rediscover project instructions, build the current system prompt and PermissionGate, and check workspace changes before continuing.
- Record durable pending / committed facts at the execution boundary of each model tool call; all `role=tool` results of the same assistant round are still fed back in the original order.
- For incomplete invocations left by a crash, distinguish "has not entered the handler" from "side effects may have happened", and forbid automatic replay of the latter.
- Keep the sources of recovery, state uncertainty, and verification invalidation as auditable Runtime facts; Trace still consumes only the State of the current task that is already loaded.
- Saving, loading, and error reports must not leak the `write_process.input` body or local LLM configuration keys.

### 2.2 Not in this stage

- No reconnecting `Popen`, pipes, output collectors, or stdin writer threads across processes; no regaining process control through a saved PID.
- No guarantee of automatically cleaning up external child processes after a crash, power loss, or `SIGKILL`; when leftovers may exist, report them explicitly and block a direct finish.
- No automatic replay of `write_file`, `edit_file`, `run_shell`, process start/control/write, or recovery actions; no promise of rolling back shell side effects.
- `once` / `always` runtime authorizations are not persisted as pre-approvals for the next process; the user's approval of a plan revision is a task fact and cannot replace tool authorization.
- No cloud sync, multi-device sharing, multiple CLIs writing one session at the same time, background daemon scheduling, general transactional database, or arbitrary cross-version migration.
- No executable deserialization formats such as `pickle`, and no copying of `config_local.py`, API keys, process stdin bodies, or checkpoint private bytes into the public State / Trace.

## 3. Design Boundaries to Freeze First

### D1: The session is a recovery format; `snapshot()` is still the replay view

Add a separate `SessionStore` and explicit boundaries such as `AgentState.export_session()` / `restore_session()`. The recovery format contains State's authoritative records, counters, budgets, repair phase, current generation, plan approval facts, and protocol messages; projections such as `active_plan`, `todos`, `current_goal`, and remaining quota should be recomputed and cross-checked, never overwritten directly from the storage file. Locks, handlers, the PermissionGate, `ProcessManager`, `Popen`, and threads are not serializable data.

Suggested top-level envelope:

```text
schema_version             # format version, not the same as the package version
session_id                 # random, never reused; separate from the in-task task_id
writer_version
workspace_identity         # normalized workspace location and necessary identity information
saved_at, save_kind        # safe_point | tool_boundary
handoff_status            # active | clean; v0.31 loads only clean
state                     # authoritative task facts and private counters for recovery
context                   # redacted message history, summaries, trim positions
tool_boundary?            # unfinished / committed call records from v0.32
integrity                 # check value covering the normalized payload
```

`session_id` identifies the session on disk, while `task_id` keeps identifying in-task processes and execution facts; the old session identity must not be reused just because a new CLI's local counter starts from 1. On read, first limit the size, then parse and validate the schema, field types, enum values, ID uniqueness, references, counter monotonicity, and tool call/result pairing, and only then build runtime objects. An unknown schema version, corrupted content, or broken links refuse to enter execution; diagnostics can be shown, but missing facts are not guessed, and a corrupted file is never loaded as an "approximately continuable" task. The integrity check is for detecting accidental corruption; an ordinary hash is not treated as authentication against malicious tampering.

### D2: Storage commits are atomic, single-writer, and private by default

Session files are placed in a user-private data directory whose path cannot be specified directly by a model tool call; they are not written into the repository, the Git index, or `config_local.py`. Directories and files use permissions readable and writable only by the current user wherever possible; when the minimum privacy cannot be met, persistence is refused with an explanation. Writing uses a temporary file in the same directory, write and `fsync`, then `os.replace`, syncing the directory where the platform allows; recovery acknowledges only completely committed files. A save failure must not overwrite the previous usable commit, nor mark the failed save as complete.

Each session allows only one CLI to write at a time, using an exclusive lock or creation marker the standard library can implement, with a manual check path for locks left behind abnormally; a lock is never taken over just because it is old, since another process holding it may still be running. Set a size limit for a single session to bound the growth of history messages and logs; the limit must not be met by truncating half a tool round. Configuration values, arbitrary user text, and tool output may contain sensitive information, and the operation manual should state the local file permissions and storage location clearly.

### D3: v0.30 / v0.31 accept only complete safe points

A safe point satisfies at least: every tool call of this round's assistant has its matching `role=tool` result, and State and history are committed together; there is no running handler, reserved but unsettled attempt, in-flight stdin write, or active background process; process cleanup results have been synced into State. `awaiting_approval`, `exploring`, `blocked`, and execution tasks still awaiting verification can be safe points, but after recovery they are still bound by the original state machine. `awaiting_process` with a process still running is not a safely resumable point. The safe point itself does not prove the CLI later exited normally: after opening a session, it should first be durably marked `active`, and only after a normal handoff completes is it marked `clean`. v0.31 resumes only `clean` sessions.

On a normal exit, first clean up this task's processes within bounds according to the Stage 8 rules, then save the cleaned state and commit the `clean` marker; if cleanup is incomplete, keep the old task and report the specific processes; it must not be saved as "directly continuable". When a crash happens between two safe points, v0.30 / v0.31 can inspect the last complete safe point but must refuse to continue directly from it: there may be unrecorded operations after it, and going back to the file version does not undo workspace changes. Only v0.32 / v0.33 use the durable tool boundary to narrow and handle this uncertain window.

### D4: Recovery rebuilds the runtime and does not reuse old permissions or old verification

The new process rediscovers `AGENTS.md` from the current workspace and rebuilds the protected system prompt, ToolRegistry, PermissionGate, and ContextManager; a persisted old system prompt cannot override newly discovered project instructions. The plan approvals, rejections, and blocked resumes the user made through the CLI are kept as State facts, but current calls must still pass the plan phase, the Repair Loop, and the new PermissionGate. Runtime `always` approvals are not inherited across processes by default, and `once` is never inherited.

Before recovery, check the normalized workspace identity and the file type, content hash, and availability of the paths the task touched; Git status can only be supplementary and cannot replace checks of untracked files and paths outside the workspace. Changed files or files that cannot be checked should be listed explicitly, without inferring the cause. Even when the check is consistent, external changes between the process exit and recovery cannot be enumerated exhaustively; recovery always opens a successor generation so the old `verification_evidence` is no longer used for the completion decision, while `verification_history` and Trace still keep the old evidence for audit. When a change needs diagnosis or replanning, it goes through the existing restricted entries, and budgets cannot be reset or the `exploring` read-only boundary bypassed directly.

File checkpoints currently keep pre-image bytes only in the in-memory `CheckpointStore`, and the public `snapshot()` has only metadata. The first version does not persist these private bytes; after recovery, the related checkpoints must be marked not rollbackable with the reason kept, and `ready` must not be forged from metadata. If cross-process rollback is needed in the future, a separate private byte store, conflict checks, and independent acceptance should be set up.

### D5: The tool boundary is recorded durably first, and only then is the handler allowed to run

v0.32 creates a stable `invocation_id` for each tool call, linking the assistant round, the original `tool_call_id`, the tool name, a summary of the effective arguments, `effect_class`, the permission result, the handler admission status, the attempt / generation, and the commit sequence number. Storage of tool arguments and results follows the redaction rules; in particular, `write_process.input` cannot enter the session, journal, summaries, error diagnostics, or terminal. When reading such a call in the history, keep the `tool_call_id` and a valid JSON argument shape, and use an explicit placeholder stating that the input was redacted; the placeholder text must never be sent to stdin again.

Permission denials and argument/schema rejections before the handler already have definite results; they cannot be classified as "side effects may have happened". Validation of plan control tools such as `commit_plan` may complete inside the handler; although a failure feeds back only `plan_rejected` and does not advance the generation, its handler boundary must also be recorded. After authorization and all preliminary validation complete, and just before entering the handler, `handler_admitted` / `pending` must be committed durably; if this commit fails, the handler must not be entered. An approved `run_shell` is `possible` whether its `purpose` is execution or verification; plan control tools do not change the workspace but do change task State and cannot be hidden by a "read-only command" classification. Side-effect calls run in the existing order; concurrent `none` calls still commit results in model order.

After the handler returns, the `ExecutionResult`, the matching State facts, and that call's `role=tool` content are committed as one durable commit; there must never be "the result succeeded on disk but State did not record it" or "State recorded it but the model protocol lacks the result". Before the next LLM request, it must also be confirmed that all calls of the same round are committed in the original order; the remaining calls in refusals, exceptions, and terminal states must each have a result as well. Asynchronous facts such as a natural process exit are committed durably on their own at sync points and are not forged as a second tool reply. For a journal and session that cannot be covered atomically in a single-file commit, use the commit sequence number and a check chain to prove which one is the authoritative record.

### D6: Uncertainty after a crash is a first-class fact

v0.33 scans pending invocations after the last committed sequence number. If it is certain the handler was not entered yet, it can safely produce a rejected/not-executed result or go through the normal authorization entry again; if an `effect_class=none` handler was entered, a retry is considered only when it can be proven that the result produced no side effects and the call is still allowed by the current state, with investigation first by default. Whenever a `possible` handler was entered, a process may still be alive, stdin may be partly written, or a rollback may be partly in effect, the call is marked `uncertain_side_effect`; it is not replayed automatically, and a timeout, a vanished process, or a file that looks unchanged is never taken as "definitely did not run".

An uncertainty event references the original invocation / attempt / generation and invalidates old verification; the runtime gives the specific next steps: read-only investigation, the necessary plan revision or recovery entry, independent verification, and a user decision when the external effect cannot be determined. Existing FailureEvents / RecoveryActions must not be fabricated or overwritten. If the current Repair Loop conflicts with the new uncertain fact, keep the causality of both and hand it to the user along the existing conservative blocking path; do not quietly clear the active failure or reuse verification evidence across generations.

### D7: The storage layer does not change Trace, Plan, or permission semantics

`/trace` keeps consuming, read-only, the State snapshot already loaded in the current process; opening a session is an explicit CLI recovery action, not part of a Trace query. Recovery events can enter the append-only trace for replay, but Trace itself must not open session files, call the LLM, run tools, authorize, change history, or advance the generation. A `commit_plan` validation failure still returns only `plan_rejected`; the save protocol cannot give an invalid plan a generation or verification evidence. The user's plan decisions are recorded only by the CLI, and the model cannot forge approval by loading a file.

## 4. Session Protocol and State Model

### 4.1 CLI and file entries

`v0.30` should provide explicit saving and a discoverable `session_id`, and `v0.31` should provide `--resume <session_id>` (or an equivalent CLI entry); the exact command names are frozen before implementation in the style of the existing `--plan`, `/new`, and `/reset` interactions. Starting a new task by default must never secretly load the previous session. Save failures, version incompatibility, workspace mismatches, non-`clean` sessions, and unfinished calls each show a different diagnostic; a failed load does not change the current runtime.

Stored content falls into three categories:

| Category | Examples | Recovery rule |
|---|---|---|
| Authoritative task facts | PlanRevision, progress, generation, attempt, failure, approval decisions, budget counters | Validate references strictly and restore; recompute derived projections. |
| Protocol context | user / assistant / tool messages, summaries, trim positions | Keep complete tool-call/result pairing; redact sensitive bodies first. |
| Volatile resources | Runtime permission approvals, `Popen`, threads, pipes, checkpoint pre-image bytes, current verification pass eligibility | Recreate or invalidate explicitly; never pretend they were restored. |

### 4.2 Durable state of tool calls

```text
InvocationRecord
- invocation_id, session_id, task_id, round_id, tool_call_id, model_order
- tool, effect_class, permission, handler_admitted
- attempt_id?, generation_id?, status: pending | committed | uncertain
- result_commit_id?, redacted_arguments, diagnostic_reason?

RoundCommit
- round_id, assistant_message_id, ordered_invocation_ids
- ordered_tool_result_ids, state_commit_id
- status: incomplete | complete
```

`pending` only means the durable boundary was established, not that the handler definitely started; only `handler_admitted=true` means the admission commit completed. `committed` requires the result, State, and history to be readable together; a whole round `committed` requires every call to have a single result before the next model request is allowed. The redacted arguments in the durable file cannot serve as the original arguments needed for a retry; v0.32 provides only the interruption facts and refuses to continue, and the user handoff and classified recovery are left to v0.33.

## 5. Version Slices

### 5.1 `v0.30` Session Persistence (complete)

Goal: build a verifiable, atomically saved session representation; this version does not continue execution across processes.

Main work:

1. Define schema 1's session envelope, private directory, random ID, size limit, atomic writes, `active/clean` handoff markers, and integrity check; state explicitly how unsupported old/future versions are refused.
2. Add explicit export and validation interfaces to State, covering the private counters and causal records recovery needs; the behavior of the public `snapshot()` and Trace stays unchanged.
3. Persist the redacted message history, summaries, and trim positions; keep the protocol link between every assistant tool call and its `role=tool`, and never save the `write_process.input` body.
4. Save only at complete safe points; give explicit feedback for active processes, in-flight writes, half-round tool results, and save failures. On normal exit, run the existing process cleanup first, then write the last safe point and the `clean` marker.
5. Add tests for round trips, corrupted files, invalid references, the size limit, interrupted writes, and privacy boundaries; in this version, reading is only for validation and inspection and does not start the Agent to continue.

Acceptance focus: the authoritative facts and protocol links read back after saving the same safe point are equivalent; after a temporary write is interrupted, the old commit is still readable; when saving is impossible, it never claims the session was persisted; sensitive stdin text never appears in the file bytes.

### 5.2 `v0.31` Safe Resume

Status: complete.

Goal: continue the original task in a new Python process from a complete safe point, still without promising to recover interrupted tool calls.

Main work:

1. Add an explicit resume entry; accept only `clean` safe points, first validate the file and workspace, then build State, Context, Registry, ProcessManager, and PermissionGate. A failed load must not pollute the current task.
2. Rediscover project instructions and rebuild the protected messages; do not inherit the previous process's `once` / `always` tool authorizations, and keep the plan decisions the CLI recorded.
3. Check workspace consistency for the paths the task touched, reporting external changes and paths that cannot be checked; open a successor generation after recovery, keep the old verification history, and require new independent verification.
4. Mark checkpoints without pre-image bytes as not rollbackable; mark old process metadata as not controllable and refuse operations on old `process_id`s or PIDs. Sessions with active processes must not go directly into safe resume.
5. Test the resume admission of the Direct Path, `exploring`, `awaiting_approval`, plans awaiting verification, and blocked tasks; after plan approval, the PermissionGate still applies.

Acceptance focus: exit the CLI normally, start a new CLI, load explicitly, and continue the same task; the original plan, budgets, and message protocol are not lost, and old verification cannot complete the task; workspace changes, `active`, or incomplete sessions do not trigger the LLM or tools.

### 5.3 `v0.32` Durable Tool Boundaries

Status: complete.

Goal: turn "about to execute" and "the result has entered the protocol" of model tool calls into durable facts.

Main work:

1. Assign stable IDs to assistant rounds and to each tool call, and commit the pending / handler-admitted boundary before the handler; a commit failure blocks the handler.
2. Commit each `ExecutionResult`, the State update, and the matching `role=tool` message together, and constrain the next LLM request with a whole-round complete marker.
3. Keep the existing `effect_class=none/possible`, `run_shell=possible`, plan tool validation failures, and the order of side-effect calls; concurrent read-only calls form durable results in model order.
4. Test the persisted state separately for permission denials, argument errors, handler exceptions, asynchronous process exits, and exceptions in the middle of a whole round; every path keeps one result per call.
5. Verify that the redacted journal does not save stdin bodies, and that a corrupted or missing result does not lead to another model request.

Acceptance focus: simulating process interruption at each commit position can accurately tell apart the last complete round, calls not yet in the handler, and calls that entered the handler; no durable state ever claims a half round is a complete protocol.

### 5.4 `v0.33` Crash Recovery

Status: complete. The implementation uses schema 3 top-level compatibility, State format 2, derived sessions, and per-issue user handoff; the source session stays read-only and recovery does not replay. The two-phase claim commit, retry consistency, and the fault injection matrix are all verified.

Goal: recognize incomplete calls after a crash and resume work along a conservative, explainable path.

Main work:

1. Classify the schema 3 pending boundary in model order as `not_executed`, `uncertain_state_or_result`, or `uncertain_side_effect`, deriving State, Context, and synthesized tool results.
2. Forbid automatic replay of calls that entered a possible side-effect handler; the workspace and old processes serve only as read-only investigation evidence, and old PIDs no longer gain control.
3. Use State format 2 to save the recovery, issues, decisions, and the `crash_recovery` trigger; recovery opens a new generation and clears current verification, while the original FailureEvents / RecoveryActions / history stay auditable.
4. `/resolve` records the user's decision per issue; `continue` requires a successful, approved, side-effect-free investigation attempt, and after all issues are settled, replanning is forced, followed by the PermissionGate and independent verification.
5. Use temporary workspaces, the durable boundary, and controlled state fixtures to verify that the source session is unchanged, the claim is not duplicated, results are not forged, stdin/arguments do not enter the recovery summary, and Trace keeps its read-only integrity.

Acceptance focus: the same crash produces an uncertainty event only once; the model never receives a forged successful tool result; the user can see which facts are confirmed, which still need investigation, and why the task cannot be completed yet.

## 6. Composition with the Existing State Machine

| Original state / scenario | Entry after recovery | Invariant |
|---|---|---|
| Direct Path, complete safe point | Continue the original task | Keeps the original completion conditions; old verification after recovery does not count as passed. |
| `exploring` or `--plan` | Continue read-only investigation | Recovery does not allow side effects or verification. |
| `awaiting_approval` | Wait for the user's decision on the current revision | A plan in the file is never approved automatically. |
| `diagnosis_required` / `verification_required` | The original repair phase plus the post-recovery verification obligation | Repair cycles are not reset and RecoveryActions are not forged. |
| `awaiting_process` with active resources | v0.31 refuses safe resume; v0.33 marks possible leftovers | Old PIDs are not treated as registered handles; no direct `done`. |
| Incomplete `possible` invocation | `uncertain_side_effect` investigation / user handoff | No automatic replay and no reuse of old verification. |
| `done` / `blocked` / `failed` | Keep the terminal state for viewing; later actions only by the existing CLI rules | Loading is not a shortcut to clearing a terminal state. |

Recovery itself is a Runtime event, not a model tool call; only the next real model reply and tool results can advance the task. `MAX_ITERATIONS` still limits one agent loop and should not be exhausted immediately by the number of loaded history rounds, and repeated resumes cannot reset durable task-level budgets. Plan revisions, progress events, and user decisions are restored with their original immutable/append-only semantics.

## 7. Tests and Acceptance

### 7.1 Unit and integration tests

- **Format and atomicity**: schema upgrade/refusal, canonical JSON, hash mismatches, truncated files, duplicate IDs, broken links, size limits, interrupted temporary files, keeping the old commit, refusing concurrent writes.
- **Integrity**: round-trip equivalence of State's authoritative fields, private counters, plan projections, budgets, verification history, Trace references, and message summaries; corrupted data is never partly loaded.
- **Protocol**: several concurrent `none` calls and serial `possible` calls are all committed in model order; every tool call has exactly one result; a half round cannot start the next LLM request.
- **Resume admission**: reloading instructions and permissions; changes to the workspace identity, untracked files, and the paths the task touched; old verification, old checkpoints, and old process control are invalidated as specified.
- **Privacy**: when a real-format `write_process.input` appears in the original assistant tool call, the raw bytes of the session and journal, error messages, and terminal output contain no body; `config_local.py` keys do not enter the session file.
- **Crash matrix**: interrupt before pending, after pending but before the handler, inside the handler, after the result was produced but before commit, after some tool results were committed, and after a complete round; recover a definite state only when there are definite facts.
- **State machine**: Plan Mode, the Repair Loop, process cleanup, the completion reminder, verification generations, Trace's read-only nature, and explicit CLI user decisions keep their original constraints.

Use standard-library test subprocesses and temporary workspaces to simulate a real new Python process; fault injection points are controlled by the tests and do not depend on lucky timing. Platform differences in file sync and process cleanup must be expressed with capability detection and explicit test expectations.

### 7.2 Stage-level E2E

1. Run a task with a plan and file changes, exit at a complete safe point; a new CLI resumes explicitly, sees the original plan, completed steps, and context summary, verifies again, and finishes.
2. Exit after a `--plan` submission; the new CLI still stops at the current revision's approval and runs no tools automatically; after approval, writes still need separate authorization.
3. Save a history that contains a stdin write call; check that the file bytes contain no input body, and that after recovery the tool results are still paired correctly with their call IDs.
4. Kill the runtime after the file handler finished its change but before the result was committed; recovery shows an uncertain side effect, investigates the file first, then lets the existing repair/replanning entries decide what comes next, without writing again.
5. Interrupt inside `run_shell(purpose="verification")`; recovery cannot treat it as read-only or as passing evidence, and verification must be done again independently.
6. Exit abnormally while a background process or stdin write is in flight; recovery does not reconnect old PIDs, does not claim cleanup succeeded, shows the specific leftover risk, and blocks a direct `done`.
7. Change tracked and untracked task files in the workspace before recovery; the differences are shown, old verification is invalidated, and Trace can still replay the old facts without guessing the cause of the changes.

### 7.3 Stage definition of done

- [x] `v0.30`–`v0.33` each have their own teachable behavior and tests, and the save/resume entries are reproducible from the operation manual.
- [x] A complete safe point can resume the task, plan, message protocol, and task-level budgets across processes; old permissions and verification eligibility are not inherited.
- [x] Interrupted tool calls have durable, checkable boundaries; no unconfirmed side effect is replayed automatically or disguised as success.
- [x] The unrecoverable parts of background processes, stdin, checkpoints, and external workspace changes all have explicit states and follow-up paths the user can act on.
- [x] Trace stays read-only, and the Plan Contract, PermissionGate, Repair Loop, generations, and complete `role=tool` feedback rules are not bypassed by the persistence layer.
- [x] The full tests, the tutorial check, the README check, and the stage-level E2E pass; the core runtime depends only on the standard library.
- [x] Each version's tag is created only manually by the user; the assistant performs no tag operations.

## 8. Version Dependencies

```text
v0.29 background processes and bounded pipe stdin
  ↓
v0.30 schema, private storage, atomic safe points, data validation
  ↓
v0.31 explicit loading, runtime rebuild, workspace checks, invalidation of old evidence
  ↓
v0.32 durable boundaries before and after the handler, per-call commits, whole-round protocol commits
  ↓
v0.33 incomplete invocations, unknown side effects, conservative recovery and user handoff
```

`v0.30` does not advertise "can read the file" as "can continue the task"; `v0.31` accepts only complete safe points; `v0.32` does not treat a persisted pending as the handler having run; `v0.33` does not guess from command text or the surface state of files that side effects did not happen. Each version adds one main concept, and its capability boundary is accepted separately.

## 9. Documentation and Release Sync

When implementing each version, sync the matching tutorial, `docs/tutorials/README.md`, `docs/operation/manual.md`, `CHANGELOG.md`, the learning path in `README.md`, the version information in `pyproject.toml`, and the status of this plan. The tutorial first explains "why the previous process's memory does not equal being able to continue execution", then introduces the schema, save points, tool boundaries, and unknown side effects; terms are explained near their first use per the tutorial authoring rules. The main README's stage names and version topics follow the main README authoring rules. `AGENTS.md` needs updating only when a new runtime hard constraint must be followed across the whole repository.

Before delivering each version, run:

```bash
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python scripts/check_tutorials.py
PYTHONPATH=src python scripts/check_readme.py
```

After the tutorial is complete and the user manually creates the matching tag, run the facts check that depends on local Git objects. The assistant must not create, move, overwrite, delete, or push tags.

## 10. Capability Boundaries After the Stage

After Stage 9, mini_agent can continue tasks from a validated local session and can recognize, when a crash happens at a tool call boundary, which results are definite and which side effects still need investigation. It does not provide process reconnection, lossless recovery of arbitrary external side effects, or unattended automatic retries; when safety cannot be proven, the task stops in an explainable, auditable handoff state.

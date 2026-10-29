# Stage 6: Reliable Execution Implementation Plan

> Status: `v0.21` Trace & Replay implemented; Stage 6 implementation acceptance complete, release tag to be created by the user
> Current baseline: `v0.21` (phased failure—diagnosis—recovery—verification loop and read-only replay)
> Prerequisite stage: Stage 5 Project-Aware Task Orchestration (`v0.14`–`v0.16`)
> Version range: `v0.17`–`v0.21`

## 1. Goal and Positioning

Stage 5 built the normal execution loop of Plan → Execute → Observe → Verify; when observation or verification finds a problem, the model Replans and continues. Stage 6 handles the exception branch of this loop: **detect an execution failure, judge the cause from facts, take a constrained recovery action, then use new verification evidence to decide whether to continue, block, or fail; and be able to replay this decision chain to verify that the reliability mechanisms really work under their constraints.**

The design principle of Stage 6:

```text
factual basis + cause judgment + bounded action + new verification evidence + replayable acceptance
```

Target flow:

```text
Execute
  -> Observe failure
  -> Classify / Diagnose
  -> Recover
  -> Verify
  -> Continue / Block / Fail
  -> Trace / Replay
```

The boundary between Stage 5 and Stage 6:

| Capability | Stage 5 | Stage 6 |
|---|---|---|
| Task plan and Todo | Build, advance, and complete the Todo | Require the model to re-evaluate the current Todo on failure |
| Normal execution | Call tools and record facts | Action choice and budget control after failure |
| Verification | Record completion evidence of the current generation | A verification failure drives diagnosis, repair, and verification again |
| Replanning | The model maintains the full plan | No separate planner; plan adjustments are triggered through normal model rounds |
| Rollback | Not provided | Bounded checkpoints and rollback from `v0.19` |
| Reliability acceptance | No causal replay of failure recovery | `v0.21` replays existing execution facts and evidence read-only |

## 2. Scope and Non-Goals

### 2.1 Scope of this stage

- Record tool attempts, failure events, and recovery actions uniformly
- Bind every execution fact to a `generation_id`
- Standardize failure classification, recoverability, and the blocked/failed finishing rules
- Apply count budgets to retries and recovery actions
- Support four basic recovery actions: `retry`, `adjust`, `ask`, and `block`
- Create checkpoints for file changes and roll back within explicit boundaries
- Chain diagnosis, repair, and verification into a bounded Repair Loop
- Query and replay existing failure, recovery, and verification evidence by generation to accept the reliability constraints

### 2.2 Not in this stage

- `v0.18` neither exposes nor runs `rollback`; scenarios that need rollback can only `block` until the `v0.19` capability exists
- No comparing or inferring "whether the environment is exactly the same"; budget constraints use only stable counts and argument fingerprints
- No separate Diagnose Agent, Planner Agent, or multi-agent protocol
- Arbitrary shell side effects are not disguised as reversible operations; unknown side effects can only continue after inspection or block
- The existing `PermissionGate` is not bypassed, and permissions are not raised automatically because of failures
- No third-party dependencies, cross-process persistence, or transactional database
- The runtime does not judge business correctness for the model; task-level conclusions are still based on Verify evidence
- `v0.21` introduces no new execution, recovery, diagnosis, or state transition logic; it only queries and shows data already recorded by `v0.17`–`v0.20`; the TodoRevision added in this version only records submission snapshots and does not change execution logic
- `v0.21` is not part of the Stage 7 planning system. Stage 7 (Planning & Replanning) stays a separate stage; its replanning triggers depend on Stage 6's `blocked` status and can use `v0.21`'s replay for debugging, but the code and stage numbering are not merged

## 3. Architecture Decisions to Freeze First

### D1: `generation_id` and execution scheduling together define the evidence boundary

`generation_id` is a monotonically increasing verification boundary within a task, not a claim about a real operating system snapshot: it means "every possible side effect approved before this number must have new verification at this number or a newer one".

- `begin_task()` creates the initial generation.
- Each executable tool declares an `effect_class` at registration: `none` or `possible`. The existing `write_file`, `edit_file`, `run_shell(purpose="execution")`, and rollback are `possible`; read-only tools are `none`. The runtime does not guess side effects from command text.
- After the PermissionGate allows a `possible` call and before the handler is called, the Runtime must reserve the next generation under the same State lock and invalidate old verification immediately. If the handler then times out, raises, exits nonzero, or writes only part of the content, the generation does not roll back. When permission is denied or arguments are refused before the handler, no generation is reserved.
- `none` calls and verification calls do not advance the generation; verification can only bind to the current generation that is already committed. Accepted recovery actions are the exception: the Runtime must reserve their successor generation under the same State lock; the actual tool call of `retry`/`adjust` reuses this generation, while `ask`/`block` create a state transition generation with no handler, and must not reserve twice.
- Calls in the same LLM round can run concurrently only when all of them are `effect_class=none`. A round that contains `possible` calls or rollback must run serially in the original tool-call order and commit State serially. Verification must not be in the same round as `possible` calls; if it is, that verification call produces an `invalid` tool result and does not enter the handler. The Verify after recovery must also run in the next round, after the recovery result is fed back to the model.
- `ExecutionAttempt` records `pre_generation_id` and the reserved `generation_id`; `FailureEvent`, `RecoveryAction`, `ExecutionGeneration`, and verification evidence all carry their `generation_id`. Every accepted recovery action must open a new `ExecutionGeneration`, even if it produces no external side effect itself; verification evidence from before the recovery cannot be reused across generations for the `done` decision. Actions refused by schema, budget, or permission are not accepted recoveries; the refusal fact must still be recorded, but no successor generation is created.

So even if an approved file write fails partway, the old verification evidence can no longer prove the current environment; the arrival order of results in the same concurrent batch also cannot change the meaning of the generation.

### D2: Stage 6 does not own full replanning

Stage 6's Recovery Policy can only decide the next action for the current failure and can require the model to diagnose again. It can suggest adjusting the arguments, command, or order of a single tool call, but it does not generate or replace the full Todo directly.

When the task approach needs to change, the runtime issues a structured recovery notice, and the next ordinary LLM round is responsible for calling the existing `update_todo` and submitting the new plan. This way the "full plan" stays the responsibility of the Stage 5 Task State protocol, and Stage 6 only provides the trigger conditions and facts.

### D3: The execution result reference of a RecoveryAction does not mean the task is fixed

`RecoveryAction.result_attempt` only references the `ExecutionAttempt` that the recovery action actually produced; that attempt records execution-level facts such as the permission result, exit code, or exception. For example, "the retry is linked to attempt `a-7`, whose exit code was 1". It must not claim that the task is already fixed.

Task-level correctness, whether the Todo is complete, and whether the changed environment meets the goal are all judged by later Verify calls and the Stage 5 completion conditions. Recovery and Verify cannot replace each other.

### D4: Retries are bounded only by counts and budgets

There is no requirement to judge whether the environment is the same between two attempts. The runtime maintains at least the following hard limits (the specific defaults can be configured at implementation and written into the tutorial):

- Recoveries/retries for a single `failure_id` do not exceed `MAX_FAILURE_RETRIES`
- Executions of the same `(tool, arguments_hash)` combination do not exceed `MAX_ATTEMPT_FINGERPRINTS`
- The total number of recovery actions in a single task does not exceed `MAX_RECOVERY_ACTIONS`
- Diagnosis—repair—verification cycles of the Repair Loop do not exceed `MAX_REPAIR_CYCLES`

After a limit is reached, nothing may repeat silently; the task must finish as `blocked` or `failed` according to the table below.

`arguments_hash` is fixed as the SHA-256 computed from the validated arguments encoded as canonical JSON (sorted keys, stable separators, no type loss); State and Structured State show only the hash and a redacted argument summary, never the raw credentials. Count checks and quota reservation must be done before the actual recovery call, under the same State lock; a call that did not reserve quota must not enter the PermissionGate or the handler.

### D5: Deciding `blocked` vs `failed`

| Condition | Status | Meaning |
|---|---|---|
| Transient/retryable failure, but the matching budget is exhausted | `blocked` | May still be recoverable, but the current run cannot keep trying safely |
| User input, authorization, or an external resource is needed, and the current channel is unavailable | `blocked` | Waiting for an external condition; does not claim the task cannot be done |
| Diagnostic information is insufficient, and continuing would have unknown side effects | `blocked` | Stop conservatively, keeping the failure facts for manual handling or the next run |
| Permission explicitly denied, with no available ask/authorization path | `failed` | The current task cannot be executed within the established permission boundaries |
| Protocol, arguments, or state violate runtime invariants and cannot be fixed by an adjust action | `failed` | The current execution path is definitely invalid |
| An explicitly unrecoverable external error, or the Repair Loop budget is exhausted with no condition to wait for | `failed` | No supported recovery path remains |

`blocked` is not an alias for success, and `failed` is not an alias for an exception string; both must carry the last `FailureEvent` and a readable reason.

## 4. Data Model (minimal schema frozen in `v0.17`)

Runtime facts are stored separately from model judgments, and none of the four kinds of records can be changed directly by `update_todo`. Apart from the initial generation, all failure/recovery-related records must store both a `generation_id` and explicit causal link fields linking to the previous `FailureEvent` or `ExecutionAttempt` that directly triggered them; relationships must not be inferred only from time order or natural language. This constraint is frozen in `v0.17`, so that `v0.21` can replay without migrating or extending the underlying model.

```text
ExecutionGeneration
- generation_id
- opened_by_attempt_id: optional (initial generation is empty)
- opened_by_failure_id: optional
- opened_by_recovery_id: optional
- open_reason: task_start | possible_effect | recovery

ExecutionAttempt
- attempt_id
- pre_generation_id
- generation_id
- caused_by_failure_id: optional
- caused_by_attempt_id: optional
- tool
- arguments_hash
- outcome: succeeded | failed | denied | timeout | invalid
- duration_ms
- effect_class: none | possible
- handler_admitted: bool
- exit_code: optional
- error_kind: optional
- output_excerpt: bounded executor output
- failure_id: optional

FailureEvent
- failure_id
- generation_id
- phase: execute | verify | recover
- category: protocol | permission | transient | deterministic | validation | unknown
- cause_hint: optional model diagnosis
- retryable: bool
- affected_files
- caused_by_attempt_id: required

RecoveryAction
- recovery_id
- generation_id
- action: retry | adjust | ask | block (v0.19 adds rollback)
- reason
- caused_by_failure_id: required
- requested_attempt: optional (retry only)
- requested_tool / requested_arguments_hash / redacted_arguments: optional (adjust only)
- checkpoint_id: optional (required by v0.19 rollback)
- status: proposed | reserved | executed | rejected | terminal
- result_generation_id: optional (required once the action is accepted)
- result_attempt: optional execution-level result reference
```

Apart from the initial generation at task start, an `ExecutionGeneration` must have exactly one `opened_by_*` causal predecessor; a generation opened by failure recovery uses `opened_by_recovery_id`. An `ExecutionAttempt` triggered by a failure or recovery must have exactly one `caused_by_*` causal predecessor; an ordinary initial execution attempt can have none.

Field ownership:

- The ToolRegistry declares `effect_class`; the Executor produces a structured `ExecutionResult` (permission decision, whether the handler was admitted, result, duration, exit code, timeout, and error kind) and cannot just call back State with an `ok` boolean or a formatted string. The Runtime writes it as an `ExecutionAttempt` and completes the generation reservation before the handler.
- The Runtime produces the basic classification, counts, and causal relationships of `FailureEvent` from the result, and creates the immutable `ExecutionGeneration` opening record. Attempts produced by `retry` or `adjust` must link back to the failure that triggered them; recovery actions must link back to the triggering failure and cannot keep only display text.
- The model can provide `cause_hint`, `reason`, and the arguments of `adjust`, but cannot forge execution results, choose `result_attempt`, or clear failure records. The original validated arguments are kept only in the current task's private attempt storage for retry and are not rendered into the Context.
- Verify stays the responsibility of the existing verification evidence mechanism; its evidence must bind a `generation_id`, and only after passing can it clear `verification_required`.

## 5. Version Slices

### 5.1 `v0.17` Failure Model

Goal: make every failure observable, linkable, and countable.

Main work:

1. Add structured state for generations, failure events, execution attempts, and recovery counts to `AgentState`.
2. Add `effect_class` to the ToolRegistry and upgrade the Executor callback to a structured `ExecutionResult`; keep the existing protocol of feeding back full tool content, but State can classify only from structured fields.
3. Reserve the generation of `possible` calls atomically before the handler, limit concurrency to fully read-only rounds, and refuse verification calls in the same round as possible side effects.
4. Map permission denials, timeouts, nonzero exits, argument/protocol errors, and verification failures to basic categories.
5. Use the canonical arguments hash to maintain atomic budget counts per `failure_id`, argument fingerprint, and task-level action.
6. Fix the `blocked` / `failed` decision and state transitions, without implementing automatic recovery actions.
7. Render the recent failure, the current generation, the remaining budget, and pending recovery notices in the Context's Structured State; arguments show only the hash and a redacted summary.

Acceptance focus: the same failure can be linked stably; failures and recoveries can be traced back along explicit causal links; failures are not lost by ordinary history trimming; approved but failed possible side effects also invalidate old verification evidence; concurrent read-only rounds do not change record order or generation semantics.

### 5.2 `v0.18` Recovery Policy

Goal: support bounded, explainable recovery choices without providing rollback.

The action set is only: `retry`, `adjust`, `ask`, and `block`.

- The model submits actions through a new `recover` control tool validated by JSON Schema; it is not a separate planner and does not bypass ordinary tool calls. `recover` must carry `caused_by_failure_id`, `reason`, and the references or arguments the action needs.
- Every action accepted after schema, budget, and permission checks reserves a successor generation under the State lock and writes `result_generation_id`. The actual tool call of `retry`/`adjust` reuses this generation; `ask`/`block` also keep this state-only generation, so old verification evidence cannot be reused.
- `retry`: only for retryable failures; it must reference the original `attempt_id` exactly and, after reserving the matching budget under the State lock, run again through the PermissionGate with the original arguments from the current task's private attempt storage.
- `adjust`: the model submits a target tool and new arguments based on the failure facts; the Runtime validates the arguments, records their canonical hash and redacted summary, reserves budget atomically, and then runs the call through the PermissionGate. When needed, a Todo adjustment is triggered by a recovery notice.
- `ask`: pause execution when user authorization, missing information, or an external condition is needed.
- `block`: finish conservatively when there is no safe recovery path.

`v0.18` explicitly does not accept `rollback` as an action value. When verification fails and the model judges that existing side effects must be undone, the system can only record the reason and enter `blocked`; it cannot simulate a successful rollback.

### 5.3 `v0.19` Checkpoint / Rollback

Implementation status: single-file checkpoints and rollback are complete; v0.20 completes the phased Repair Loop on top of this, and this section keeps the implementation boundaries and acceptance basis.

Goal: provide bounded, auditable recovery for traceable file changes.

- The scope of a checkpoint is fixed to **one successful or failed single-file `write_file`/`edit_file` call**; no multi-file transaction is attempted. When creating a checkpoint, capture the pre-image of the same real path before the handler: the normalized relative path inside the workspace, the type `absent | regular-file`, the raw bytes, mode, the pre-image SHA-256, and the creating generation and attempt ID. Paths that resolve outside the workspace, symlinks, non-regular files, and files over `MAX_CHECKPOINT_BYTES` are not supported for checkpoints; the call can still run but cannot be rolled back.
- Each checkpoint binds only one file and one write; after the write, the expected post-image SHA-256 is recorded. When the original file did not exist, it is represented by an `absent` tombstone, and the goal of rollback is to delete the file this write created.
- `v0.19` adds `rollback` to the `recover` action schema, and the action must reference a checkpoint ID. The Runtime then calls the `rollback_checkpoint` tool, which is not exposed to the model directly; this tool must still be authorized by the PermissionGate on the target path, and the model cannot provide replacement content. Before running, it must verify that the current file type and digest still equal the checkpoint's post-image; otherwise it is judged as an external change and the write is refused.
- Restoration uses a temporary file in the same directory plus an atomic replace; for an `absent` tombstone, only a regular file whose digest still matches the post-image can be deleted. Any failed restore step is recorded as an unknown side effect, keeps the checkpoint, and enters `blocked`; it cannot claim the rollback happened.
- Rollback promises restoration only for the checkpointed files above; arbitrary shell, network, or external service side effects are not promised to be reversible. Every rollback is a `possible` call: a new generation is reserved before the handler, old verification evidence is cleared, and an independent Verify is required in the next LLM round.
- When the checkpoint is missing, the file was changed externally, or the scope of side effects is unknown, the action result is a failure, finished as `blocked` / `failed` according to the rules.

### 5.4 `v0.20` Repair Loop

Goal: chain failure classification, diagnosis, recovery, and verification into a complete bounded loop.

```text
failure
  -> FailureEvent
  -> model diagnosis / RecoveryAction
  -> execute recovery
  -> new generation
  -> independent verification
  -> continue, next failure, blocked, or failed
```

This version reuses only Stage 5's existing LLM rounds and Todo tool and creates no second planner. The implementation freezes three run phases: `idle`, `diagnosis_required`, and `verification_required`. A failure enters the diagnosis phase; the diagnosis phase allows only read-only investigation, `update_todo`, or an exclusive `recover`, and recover can reference only the current active failure. Only authorized and activated `retry`, `adjust`, and `rollback` consume a repair cycle; the initial failure, rejections, permission denials, and `ask`/`block` do not. After the recovery result is fed back, the next tool round must be a single independent verification; only after it passes does the phase return to idle, while a failure produces a new FailureEvent and returns to the diagnosis phase. Both the agent loop and the ToolExecutor enforce the same admission protocol, and refused calls are still fed back as matching `role=tool` results in the original order.

The `repair_loop` in Structured State stores the phase, the active failure/recovery, the cycles used/remaining, and the required next action; the compacted critical state and the completion Runtime Notice sync these fields. So every cycle can answer: what the failure facts are, the reason the action was chosen, the result of executing the action, and whether the verification evidence belongs to the current generation. Every accepted recovery action must enter a new generation; verification evidence from an old generation must not be reused for the `done` decision.

### 5.5 `v0.21` Trace & Replay

Goal: support replaying, by generation, a task's complete decision chain: plan → execution → failure → classification/diagnosis → recovery → re-verification → terminal state.

This version is Stage 6's acceptance and debugging wrap-up and introduces no new execution, recovery, diagnosis, or state transition logic. It only queries and shows the `ExecutionGeneration`, `ExecutionAttempt`, `FailureEvent`, `RecoveryAction`, Todo/plan changes, append-only verification history, and terminal states produced by `v0.17`–`v0.21`; replay must not write, guess, or repair missing runtime facts. The current `verification_evidence` still keeps only the current generation and serves the completion decision; the history records take no part in the `done` decision.

The replay view presents state transitions in generation order and connects each record to the attempt or failure that triggered it through the causal links frozen in the schema. Each node must be able to show the raw, redacted execution/verification evidence and its source, and mark clearly the generation the evidence belongs to; the terminal state must be shown as `continue`, `done`, `blocked`, or `failed` with its final basis.

Implementation status: added the immutable `TodoRevision`, the append-only `verification_history`, `build_trace()` / `render_trace()` in `src/mini_agent/trace.py`, and the `/trace [generation_id]` CLI. The report validates duplicate/missing references, generation openers, two-way attempt/failure references, recovery results, verification history integrity, and current evidence isolation; corrupted snapshots keep the records that can be confirmed and output unresolved edges. Replay is read-only; it does not call the LLM, tools, or the permission gate, and does not change history, budgets, State, or generations.

Acceptance focus: for at least one real failure—recovery case produced by `v0.17`–`v0.20`, it can fully replay each generation's state transitions and the raw evidence on which each classification, diagnosis, recovery, and terminal state is based. This case should be directly usable to check whether `v0.18`'s recovery policy and budgets, `v0.19`'s rollback boundaries, and `v0.20`'s verification evidence isolation work as intended.

## 6. Tests and Acceptance

### 6.1 Unit tests

- Generation changes after file writes, execution shell, verification, and permission denials follow D1.
- Approved `possible` calls that raise, time out, or write only part of their content still reserve a generation and invalidate verification; refusals and argument errors before the handler do not.
- Same-round tool calls with side effects are committed serially in the original order; a verification mixed in is fed back as `invalid` and the handler is not run.
- `ExecutionGeneration`, attempts, failures, recoveries, and verification evidence always carry a generation_id; apart from the initial generation, the causal links of failure/recovery records are complete and machine-traceable.
- The Executor's structured result can express permission denials, handler exceptions, timeouts, exit codes, and durations without string parsing; the canonical arguments hash is stable under key order, and the Context does not leak raw sensitive arguments.
- When the failure_id, argument fingerprint, total action count, or repair cycle limits are exceeded, no hidden retry is run.
- `retry` reuses the arguments of the attempt it references exactly; `adjust`, budget reservation, PermissionGate execution, and the `result_attempt` link can each be tested independently.
- `RecoveryAction.result_attempt` is never treated as Verify evidence; after a verification failure, `verification_required` stays set.
- The `blocked` / `failed` decision table covers every input, and state transitions can be tested repeatedly.
- `v0.18`'s action schema refuses `rollback`.
- Checkpoints cover existing files, new files, external changes, symlinks/paths outside the workspace, size limits, and interrupted restores; failed recovery never describes the task as rolled back.
- Trace & Replay can rebuild a failure—recovery—verification chain relying only on the generations and causal links of the frozen schema; missing links or verification evidence reused across generations are marked explicitly as not acceptable, never filled in by guesses in the display layer.
- Current verification evidence is invalidated after a generation change, but the append-only verification history still keeps the raw audit evidence of each generation; the two cannot replace each other.

### 6.2 Stage-level E2E scenarios

1. A command fails transiently, succeeds after bounded retries, and passes final verification.
2. Wrong arguments; the model adjusts them and succeeds.
3. Tests fail after a change; the model fixes again based on the output and verification passes again.
4. Permission denials or repeated failures finally enter `blocked` or `failed` with an explicit reason, with no infinite loop.
5. In `v0.19`, after a single-file checkpoint rollback, old verification evidence is invalidated; an external change or an interrupted restore enters blocked; only a new passing verification allows continuing.
6. After at least one context compaction, the generation, failure events, remaining budgets, and recovery notices are still accurate.
7. For a real failure—recovery case, replay the plan, attempts, failures, diagnoses, recoveries, verification evidence, and terminal state by generation; every state transition can locate its raw, redacted evidence and causal predecessor.

### 6.3 Stage definition of done

- [x] `v0.17`–`v0.21` each have their own tutorial, change record, and runnable tests.
- [x] Every failure can be linked to an execution attempt and a generation; there is no hidden state driven only by natural language strings.
- [x] Every recovery action is bound by the PermissionGate and count budgets and opens a new Execution Generation; verification evidence from old generations cannot be reused for the `done` decision.
- [x] Rollback is available only from `v0.19` onwards, for side effects with explicit checkpoints.
- [x] The Repair Loop finishes correctly among four outcomes: success, continued repair, blocked, and failed.
- [x] v0.21 can replay at least one real failure—recovery case with the frozen structured data, showing each generation's state transitions and raw evidence.
- [x] Trace & Replay read-only replay, broken-chain marking, and CLI queries by generation are complete.
- [x] The default test suite, the tutorial check, and the stage-level E2E all pass, and the runtime still uses only the standard library.
- [ ] After the user manually creates the `v0.21` tag, the tutorial facts check passes and release acceptance is complete.

After Stage 6, mini_agent's completion standard is no longer just "tools were called and the tests passed once", but: **failures have structured facts, recovery has explicit boundaries, and results have new verification evidence belonging to the current generation; these facts can also be replayed completely by generation to verify that the reliability mechanisms really work as intended; and when it cannot continue, it can state accurately whether it is blocked or failed.**

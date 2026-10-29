# Lesson 18: Bounded recovery policy (Recovery Policy, v0.18)

Previous: [Failure model](17-failure-model.md) · [Tutorial overview](README.md) · Next: [Single-file checkpoint and rollback (Checkpoint / Rollback)](19-checkpoint-rollback.md)

> Code snapshot: `v0.18` · Adjacent diff: `v0.17..v0.18` · Shell: Bash/zsh

> Patch snapshot: `v0.18.1` · Adjacent diff: `v0.18..v0.18.1` · Shell: Bash/zsh

> This lesson keeps the concepts and evolution baseline of v0.18; the recovery boundaries follow the implementation as corrected in v0.18.1. v0.18.1 adds no new recovery actions; it only makes the existing promises hold consistently on the rejection, authorization, budget, and terminal-state paths.

> Requirements: Python 3.10+; the runtime uses only the standard library.

## Lesson Goals

Lesson 17 can already answer "which call failed, which category the failure belongs to, and whether there may be side effects", but it does not yet say what the model may do next. This lesson solves: **after a failure, how to make a bounded, auditable choice that never mistakes one successful call for a fix.**

After reading this lesson, you should be able to explain:

- Why `recover` is a control tool constrained by a JSON Schema (rules describing the input shape and allowed values), rather than the model claiming "fixed" in words;
- When `retry`, `adjust`, `ask`, and `block` apply, and how they pass through argument validation, the PermissionGate, and budgets;
- Why accepting a recovery opens a successor generation, clears old verification, and requires a separate verification in the next round;
- Why v0.18.1 separates "reserving budget", "confirming target permission", and "activating the generation".

The main thread is one sentence: **first choose a bounded action from the failure facts, then judge whether the task is really done with new verification of the current generation.**

## Problems in the Previous Version

v0.17 built the fact layer, but the model could still decide "try again", "change the arguments", or "stop" only in natural language. Natural language cannot guarantee that a retry uses the same original arguments, and it cannot stop the same failure from repeating forever. More importantly, when a recovery call returns success, that cannot be taken as proof that the original task is fixed; it only says that a recovery attempt (a call record) finished.

v0.18 puts this choice into the existing tool protocol: the model calls `recover`, the runtime validates the action and the failure reference and reserves budget, and when a real tool needs to run, it still goes through argument validation, the PermissionGate, and the ToolExecutor (the tool execution boundary). The recovery result reports only execution facts; whether the problem is fixed is left to a later, independent verification.

## Prerequisites and Version Checkout

Read Lesson 17 first. All commands are for Bash/zsh:

```bash
git checkout v0.17
git diff --stat v0.17..v0.18
git diff v0.17..v0.18 -- src/mini_agent/recovery.py src/mini_agent/state.py src/mini_agent/tools/__init__.py src/mini_agent/agent.py
git diff --stat v0.18..v0.18.1
git diff v0.18..v0.18.1 -- src/mini_agent/recovery.py src/mini_agent/state.py src/mini_agent/tools/base.py src/mini_agent/tools/file.py src/mini_agent/context.py src/mini_agent/agent.py
git checkout v0.18.1
```

The first four commands show what v0.18 added and then which boundaries v0.18.1 corrected; the last one switches to the patch snapshot. When you read the diff, first find where `recover` is registered and how recovery reuses the ToolExecutor, then see how the patch also writes rejections into State. Where the text refers to original v0.18 behavior, it says so explicitly, so patch capabilities are not projected back onto the main version.

## New and Changed Files

The table lists the files directly involved in this lesson's teaching thread; the patch also adjusts the file tools, context rendering, and terminal-state scheduling.

| File | Change | Purpose |
|---|---|---|
| `src/mini_agent/recovery.py` | New in v0.18; v0.18.1 tightens rejection and authorization order | Defines the `recover` schema and action dispatch |
| `src/mini_agent/state.py` | Adds recovery records, causal links, budgets, and generation operations | Saves recovery facts atomically so concurrency cannot bypass budgets |
| `src/mini_agent/tools/__init__.py` | Registers `recover` for each `AgentState` | Binds the control tool to the task state without sharing task data |
| `src/mini_agent/tools/base.py` | Reuses the reserved attempt/generation; the patch handles terminal states and schema rejections | Keeps all real tools passing through the same execution boundary |
| `src/mini_agent/agent.py` | Handles recover in order and feeds back a tool result for every call | Keeps the call protocol complete |

## Version Change Map

Legend: `[old]` already in the previous version, `[+]` new in this version, `[~]` changed in this version, `[C]` main consumer, `[B]` boundary of this version.

First the v0.17 baseline: failures are recorded and shown, but there is no controlled recovery entry.

```text
[old] agent loop -> ToolExecutor.execute_result()
  -> [old] AgentState.record_execution_result()
  -> ExecutionAttempt / FailureEvent / generation
  -> role=tool fed back -> [C] Structured State
  -> [B] no controlled recovery entry
```

v0.18 adds a control tool alongside the same call chain. This diagram shows the conceptual main thread; the order in which target permissions are reserved is tightened further by the v0.18.1 patch:

```text
[old] FailureEvent + Structured State
  -> [~] agent loop -> [+] recover JSON Schema
  -> [+] RecoveryRuntime.recover()
       -> validate the failure, action combination, and budget
       -> [+] AgentState.reserve_recovery()
            -> retry: take the private original arguments of the directly failed attempt
            -> adjust: validate the target tool's new arguments first
            -> ask/block: do not enter the handler, finally block
       -> PermissionGate -> ToolExecutor.execute_result() -> handler
       -> [+] RecoveryAction / ExecutionAttempt
  -> role=tool fed back
  -> separate verification in the next round

[B] rollback is explicitly refused; no checkpoint, automatic repair scheduling, trace replay, or cross-process persistence.
```

The v0.18 entry is `RecoveryRuntime.recover()`, which chooses the action; `AgentState` stores failures, recoveries, generations, and budgets; the ToolExecutor is still the only boundary for arguments, permissions, and handlers. The focus of v0.18.1 is not another path but keeping these nodes consistent on rejection, terminal states, and failed permission checks.

## Core Concepts and Data Structures

### 1. `recover` is a validatable recovery request

The problem is that "the model says it will fix it" has no uniform format and does not say clearly which failure it addresses. `recover` is a control tool: it does not represent task completion directly; it submits a request with a causal failure reference, a reason, and action arguments.

The schema snippet below shows the skeleton of the input; before reading it, remember its purpose is to limit the range of recovery the model can express:

```python
parameters = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["retry", "adjust", "ask", "block"]},
        "caused_by_failure_id": {"type": "string"},
        "reason": {"type": "string", "minLength": 1, "maxLength": 500},
        "requested_attempt": {"type": "string"},
        "requested_tool": {"type": "string"},
        "requested_arguments": {"type": "object"},
    },
    "required": ["action", "caused_by_failure_id", "reason"],
    "additionalProperties": False,
}
```

After these rules pass, the runtime still checks whether the failure exists, whether the task is already in a terminal state, whether the action combination is valid, whether the target arguments pass the tool schema, and whether there is budget left. A failed request does not disappear silently: in v0.18.1, rejections for schema, arguments, failure reference, action combination, recovery budget, `recover`'s own permission, and target permission all produce a unique `recovery_id` and record exactly one `RecoveryAction` with `status="rejected"`; the generation does not change.

Tool names must match the registry exactly. For example, `edit_file` is a valid target name, but `functions.edit_file` is not an alias. Target permission uses the same PermissionGate of the current session; once the target is approved, the actual execution reuses the confirmed authorization and does not ask again for the same target.

### 2. Four actions keep recovery within an explainable range

The four actions solve four different problems:

| action | What it needs | Runtime behavior | Important boundary |
|---|---|---|---|
| `retry` | The directly failed `requested_attempt` | Takes the original arguments State keeps privately and runs the original tool again | Does not accept model-rewritten arguments; at most 3 times per failure by default, and the failure must be retryable |
| `adjust` | `requested_tool` and `requested_arguments` | Validates against the target tool schema first, then runs | Records the canonical JSON hash and a redacted summary; `recover` cannot be the target |
| `ask` | The failure reference and reason | Does not enter a handler, creates a state-only generation, enters `blocked` | Means waiting for an external condition, but this version provides no external waiting mechanism |
| `block` | The failure reference and reason | Does not enter a handler, creates a state-only generation, enters `blocked` | Means stopping conservatively by policy |

The direct reference rule of `retry` can be understood from the real logic below. Purpose first: it prevents the model from retrying with an attempt that is "related but not the direct failure"; result afterwards: the arguments are deep-copied from State's private copy, not resubmitted by the model.

```python
if source_attempt is None or source_attempt.failure_id != caused_by_failure_id:
    return self._reject_recovery(
        action, caused_by_failure_id, reason,
        "retry must reference the directly failed attempt",
    ) + (None,)
requested_tool = source_attempt.tool
requested_arguments = deepcopy(
    self._original_attempt_arguments.get(source_attempt.attempt_id, {})
)
```

So retry cannot quietly replace arguments; adjust is the entry for explicitly submitting a new tool and new arguments. Invalid adjust arguments never reach the permission gate or the handler. Both kinds of real execution still pass through ToolExecutor.execute_result().

### 3. When recovery is accepted, the generation is a verification boundary, not a snapshot

The intuitive meaning of a generation is "the environment boundary from which verification must start again". It is not an operating system snapshot and cannot undo files, shell, network, or unknown side effects. After a recovery is accepted, old verification evidence is cleared, and verification is required in the next round.

The original v0.18 implementation chained the reservation, generation activation, and target execution together. v0.18.1 separates them so that old evidence is not invalidated before the target permission has passed. The order after the patch:

```text
recovery_target()
  -> read-only confirmation of the failure, action combination, target, and current budget
reserve_recovery(..., defer_generation=True)
  -> create a proposed action inside the State lock
  -> reserve failure retry and target argument fingerprint budget
  -> generation not yet changed, attempt not yet created
PermissionGate.guard(target)
  ├─denied -> deny_reserved_recovery()
  │           proposed -> rejected
  │           release the unused retry / argument fingerprint budget
  │           do not open a generation
  └─allowed -> activate_recovery()
               open the successor generation, clear old verification
               create and run the reserved attempt
```

There are two kinds of budget here; do not confuse their meaning: the recovery action budget records "how many requests were made", so it is not refunded after a target permission denial; the failure retry and argument fingerprint budgets limit "how many times something can actually run", and they are refunded when the target was not approved to run. The generation advances only after the target is approved, meaning the recovery boundary was accepted, not that an unauthorized intent exists.

### 4. A recovery result is not evidence of a fix

`RecoveryAction.result_attempt` only represents the execution facts of the recovery call, not that the task is fixed. The target attempt of retry/adjust uses the reserved generation; ask/block have no handler but still create a state-only generation and enter `blocked`.

The recovery result is first fed back in full as the matching `role=tool` message. Only in the next round can `run_shell(purpose="verification")` be called, and only `[exit=0]` in the current generation can become a completion condition. If verification fails, that is a new `validation` failure, and "the recovery tool returned executed" cannot replace it.

This boundary shows in the state check as "the evidence's generation must equal the current generation":

```python
return (
    bool(self.verification_evidence)
    and self._last_verified_generation == self._verification_generation
    and self.verification_evidence[-1].outcome == "passed"
)
```

So recovery returning `executed` only says the recovery attempt was recorded; the task has completion evidence only after a later verification marks the current generation as passed.

## Why This Design

Letting the model call the tool again directly after reading the failure text is cheap, but it cannot guarantee the same call is retried and makes loops hard to limit; letting the recovery module run all fixes itself would duplicate tool logic and could easily bypass argument validation and permission rules.

This version uses "a control tool + the existing executor": recover only chooses a bounded action, sets up causal links, and uses budget; real tools still go through the single argument and permission boundary. This costs one more control call and one more LLM round, in exchange for auditable records and a guarantee that verification evidence is never misused across generations.

This version does not rewrite the full Todo automatically; when the plan needs to change, the next round uses `update_todo`. This version also does not treat the generation as a checkpoint and provides no automatic repair, rollback, or cross-process recovery.

## Design Boundaries

- `MAX_RECOVERY_ACTIONS` defaults to 8; when the recovery request budget is exhausted, the task conservatively enters `blocked`. `MAX_FAILURE_RETRIES`, `MAX_ATTEMPT_FINGERPRINTS`, and `MAX_REPAIR_CYCLES` default to 3, 3, and 3 respectively.
- Recoveries rejected for schema, arguments, failure reference, budget, or permission do not open a generation, but v0.18.1 still records the rejection fact and a `recovery_id`.
- The hash is used for association and counting, and the redacted summary only for display; neither is an authorization credential.
- When recover appears in the same round as a possible effect, they commit serially in model order; verification must not be in the same round as side effects, and after recovery it must be verified in the next round.
- rollback is explicitly refused. v0.18 has no checkpoints and makes no promise to undo files, shell, network, or unknown side effects, and it provides no cross-process persistence.
- ask and block are both `blocked`; the first says it is waiting for an external condition, the second that policy stopped it; this version does not wait or continue automatically.
- Structured State shows the recovery notice, the last three failures and recovery actions, the tool/attempt/generation/category/retryability for each failure, and the remaining budgets in hash form; after trimming or compaction, these fields are still rebuilt from the State snapshot.
- Once the state enters `blocked` or `failed`, both the scheduler and the Executor refuse later handlers and permission prompts. v0.18.1 still appends a `task_terminal` result, in the original order, for every remaining tool call in the batch and feeds them all back; the terminal reason is not rewritten by later rejection records.

## Key Flow

First the normal path of one retry, then two important rejection points. Use it to judge the fields observed at runtime, not to treat a recovery call as a completion signal:

```text
an execution attempt fails and creates a failure event
  -> recover(retry,
       caused_by_failure_id=<ID of that failure event>,
       requested_attempt=<ID of the directly failed attempt>)
  -> schema / failure link / retry budget
       ├─rejected -> status=rejected, generation unchanged -> role=tool
       └─budget reserved -> take the private original arguments -> PermissionGate
                    ├─denied: action rejected, execution budget released, generation unchanged
                    └─accepted: open a generation, clear old verification
                         -> handler -> new attempt
                    -> role=tool
  -> separate verification in the next round
       ├─[exit=0]: the current generation gets evidence
       └─failure: a new validation failure; cannot claim it is fixed
```

When you run a real task, an accepted recovery should show the generation increasing, old verification evidence disappearing, and a recovery notice requiring independent verification. If the request or the target permission is rejected, you should see `status=rejected`, a recovery_id, and an unchanged generation; if the same batch enters a terminal state after an exception in a possible handler, later calls only get `error_kind=task_terminal` and never enter the handler.

## Implementation Breakdown

`create_registry(state)` creates a new RecoveryRuntime and `recover` tool for each `AgentState`, so different tasks do not share recovery state. The agent loop handles recover in the model's order; every tool call has a matching `role=tool` result, and the next round starts only after all of them are fed back.

In v0.18.1, the key order of `RecoveryRuntime.recover()` is: check the reason and rollback; validate the target arguments for adjust; `recovery_target()` confirms the target without changing state; `reserve_recovery(defer_generation=True)` reserves budget atomically; check the target with the current session's PermissionGate; `activate_recovery()` opens the generation; the ToolExecutor runs the target; `record_execution_result()` writes the attempt/failure. A target permission denial only updates the reserved action, adds no second rejection record, and opens no generation.

The patch also separates two known precondition errors of `edit_file` from an ordinary `ValueError`: `EditNoMatchError` means `old_string` did not match, and `EditMultipleMatchesError` means there were several matches without `replace_all=true`. Both happen before writing, so the file stays as it was; the Executor records them separately with `error_kind`, State classifies them as `deterministic`, and the task stays able to continue. By contrast, an ordinary exception in an approved handler may still have produced unknown side effects, so it is still classified as `unknown` and blocks; the patch does not guess from exception text whether a write happened.

## Version Features, Next Lesson, and Code Index

v0.18 limits the choices after a failure to an exact retry, an explicit adjustment, waiting for an external condition, or a conservative stop. It does not undo side effects and does not treat a recovery attempt as completion evidence; every accepted action requires independent verification of the current generation. v0.18.1 further makes rejection records, budget reservation, target authorization, file preconditions, and terminal batches follow the same boundaries.

The next lesson discusses checkpoints and bounded rollback: content can be restored only where an explicit pre-change image of a file was saved, and shell and external side effects are still not promised to be reversible.

Core code index:

- v0.18: [recovery.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.18/src/mini_agent/recovery.py), [state.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.18/src/mini_agent/state.py), [tools/__init__.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.18/src/mini_agent/tools/__init__.py), [tools/base.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.18/src/mini_agent/tools/base.py), [agent.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.18/src/mini_agent/agent.py)
- v0.18.1: [recovery.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.18.1/src/mini_agent/recovery.py), [state.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.18.1/src/mini_agent/state.py), [tools/base.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.18.1/src/mini_agent/tools/base.py), [tools/file.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.18.1/src/mini_agent/tools/file.py), [tools/file_errors.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.18.1/src/mini_agent/tools/file_errors.py), [context.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.18.1/src/mini_agent/context.py), [agent.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.18.1/src/mini_agent/agent.py)

## Patch Appendix: What v0.18.1 Corrected

Read this section last: the main thread is still "verify again after bounded recovery". The patch adds no new actions; it corrects the paths in the original v0.18 implementation where the facts the model saw, the facts State saved, and the actual execution boundary disagreed.

### 1. Rejections must also become traceable facts

v0.18 already required recovery to be auditable, budgets to take effect before execution, and no tools to run after a terminal state, but the original implementation did not deliver this at every entry: a schema or argument rejection might have no `RecoveryAction`, the generation might advance before the target permission was confirmed, the same argument fingerprint budget did not uniformly cover ordinary execution and recovery execution, and later calls in a terminal batch might still go down the execution path.

v0.18.1 unifies these entries into `reject_recovery()` or an equivalent Executor rejection path. The diagram first shows the input, then what you should observe:

```text
recover request
  ├─ schema / JSON invalid
  ├─ failure or action reference invalid
  ├─ adjust target arguments invalid
  ├─ recover's own permission denied
  ├─ recovery or argument fingerprint budget exhausted
  └─ target tool permission denied
         v
one RecoveryAction(status="rejected")
  + one role=tool result containing the recovery_id
  + generation unchanged
```

Recording only once matters: a target permission denial happens after the `proposed` action already exists, so the runtime updates that record instead of appending a second rejection record. The recovery request itself still consumes `MAX_RECOVERY_ACTIONS`, so the model cannot consume rounds endlessly with invalid arguments or unauthorized targets; the default limit is 8, after which the task enters `blocked`.

### 2. Separating budget reservation, authorization, and generation activation

After the patch, `proposed` is not an execution result. It only says that State has reserved, inside the lock, the recovery request budget and the retry/fingerprint budget needed for actual execution. When the target is not approved, the latter two execution budgets are released; the recovery request budget is not. Only after the same PermissionGate approves does `activate_recovery()` open the successor generation, and the Executor reuses this authorization with `permission_already_checked=True`, so the same target is not asked about twice.

The patch also tightens action combinations: retry can only reference the directly failed attempt of a retryable failure and reuses State's private original arguments; adjust does not accept `requested_attempt`; ask/block do not accept target arguments; `recover` itself cannot be a recovery target. The target tool name must match the registry exactly, for example `edit_file`, not `functions.edit_file`.

### 3. Distinguishing "cannot edit" from "write result unknown"

`edit_file` first reads the file and checks `old_string`. When there is no match, or several matches without `replace_all=true`, no write has happened yet; this is a deterministic precondition failure, not an unknown side effect. v0.18.1 classifies it stably with dedicated exceptions and `error_kind`; the file stays as it was, the generation keeps the boundary opened by this approved possible-effect attempt, but the task does not enter `blocked` just because of these two exceptions, and the model can correct the arguments and request adjust.

By contrast, as long as a call has been approved into the handler and the runtime cannot prove that no side effect happened, it is still classified with `handler_exception` and `unknown`, keeps the advanced generation, and enters `blocked`. The patch does not guess from exception text whether the file was written.

### 4. A terminal state stops execution and keeps the tool protocol complete

After a possible-effect handler raises an unknown exception, State may enter `blocked` immediately. The remaining tool calls in the same model message no longer ask for permission or enter handlers; but they cannot disappear from the protocol. The scheduler appends a matching `role=tool` for every call in the original order and states the rejection reason with `error_kind=task_terminal`.

This maintains two invariants at once: after `blocked` or `failed`, no later handler is entered; every tool call still has exactly one matching tool result, and the next round starts only after the whole batch is fed back. The terminal reason follows "the first terminal state wins", so later rejection records do not overwrite the failure that originally caused the terminal state.

### 5. How to observe whether the patch works

After switching to the patch tag, first look at the real diff given at the start of this lesson. When you run "failure → rejected recovery", you should see a rejected recovery with a causal failure reference, `recovery_actions_remaining` decreasing, and an unchanged generation; for a target permission denial, the execution budgets for retry and argument fingerprints do not decrease.

When you run the `edit_file` no-match scenario, you should see `error_kind=edit_no_match`, a failure category of `deterministic`, unchanged file content, and a task that can still continue. If you make an approved possible-effect handler raise an ordinary exception, you should see category `unknown`, the task entering `blocked`, and later calls in the same batch only receiving `task_terminal` without entering the handler.

v0.18.1 still provides no checkpoint, rollback, automatic repair scheduling, or trace replay; those belong to later versions. The patch only makes the recovery protocol already declared in v0.18 consistent on the rejection, budget, permission, exception, and terminal-state paths.

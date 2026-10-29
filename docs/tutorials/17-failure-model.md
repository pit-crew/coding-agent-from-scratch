# Lesson 17: Failure model (v0.17)

Previous: [Plan-driven execution](16-plan-driven-execution.md) · [Tutorial overview](README.md) · Next: [Bounded recovery policy](18-recovery-policy.md)

> Code snapshot: `v0.17` · Adjacent diff: `v0.16..v0.17` · Shell: Bash/zsh

> This lesson covers only how to record "what happened in a failure" and how to finish conservatively. Automatic recovery, retries, checkpoints, and rollback belong to later versions.

## Lesson Goals

When a tool fails, "failed" is not a precise enough answer. We need to know at least: did the arguments pass validation, did the permission check pass, did the handler (the function that does the tool's actual work) start running, and might the environment have changed?

After this lesson, you should be able to explain in your own words:

- `ExecutionResult` is the result observed at the tool boundary; `ExecutionAttempt` is the call record written to State; `FailureEvent` is the failure fact extracted from a call record; `ExecutionGeneration` is the generation that verification evidence belongs to.
- Why argument errors, permission denials, handler exceptions, timeouts, nonzero shell exits, and verification failures must be recorded separately.
- Why an approved `possible` call that may change the environment invalidates old verification evidence even if it ends in failure.
- Why a round of only read-only calls can run concurrently, while any potential side effect makes the round run and commit in the model's original order.

The main thread of this lesson: **the model expresses intent, the Executor (the tool execution boundary) observes facts, and State (task state) keeps traceable records.**

## Problems in the Previous Version

In v0.16, tool results entered `AgentState` mainly as text. Text can say "it failed", but it cannot reliably answer "did the handler start", "did the permission check pass", "might the environment have changed", or "which call was this". After the context is trimmed or compacted, the history messages alone may no longer contain these answers.

v0.17 solves the recording problem first, instead of choosing a fix for the model: every call has an attempt (an immutable call record), every failure has a failure event with causal links, and verification evidence is bound to the current generation. So later versions can choose recovery based on facts, but this version does not claim it can recover from unknown side effects.

## Prerequisites and Version Checkout

You need Python 3.10+; the runtime still uses only the standard library. All commands are for Bash/zsh. Read Lesson 16 first, then use the commands below to compare the diff with this version's source scope:

```bash
git checkout v0.16
git diff --stat v0.16..v0.17
git diff v0.16..v0.17 -- src/mini_agent/state.py src/mini_agent/tools/base.py src/mini_agent/agent.py src/mini_agent/context.py
git checkout v0.17
```

The first two commands answer "how big is the change" and "which related files changed". The last one switches to this lesson's snapshot; later source links and behavior follow this tag. When you look at the diff, note in particular that the tool boundary starts returning structured results and State starts saving attempt/failure/generation; that is exactly the change this lesson explains.

## New and Changed Files

`git diff --stat v0.16..v0.17` shows that this version also has other supporting changes. The table below lists only the parts this lesson's main thread uses directly:

| File | Change | Purpose |
|---|---|---|
| `src/mini_agent/state.py` | Adds generation, attempt, failure, argument fingerprints, and budgets | Stores execution facts independent of message history |
| `src/mini_agent/tools/base.py` | Adds `Tool.effect_class`, `ExecutionResult`, and argument validation results | Unifies observed values at the tool boundary |
| `src/mini_agent/agent.py` | Chooses concurrent/serial by effect class; rejects mixed verification | Keeps record order and the protocol complete |
| `src/mini_agent/context.py` | Renders recent failures, generations, and budgets | Diagnosis still works after trimming or compaction |
| `src/mini_agent/config.py` | Sets limits for failures, fingerprints, and repair cycles | Keeps attempts from growing without bound |

## Version Change Map

Legend: `[old]` already in v0.16, `[+]` new in v0.17, `[~]` changed in v0.17, `[C]` main consumer, `[B]` boundary of this version.

First the entry and finish of the previous version; treat it as the baseline of "what happens without structured failure facts":

```text
[old] agent loop -> [old] ToolExecutor -> PermissionGate -> handler
                          -> text result -> [old] AgentState.record_tool
                          -> role=tool fed back -> generation/verification finish
```

v0.17 separates "observing tool results" from "writing facts to state", and adds side-effect classification where calls are scheduled:

```text
[old] agent loop
  -> [~] parse tool calls
       -> all none effect: [+] run concurrently, commit facts in model order
       -> contains possible: [+] run and commit serially in model order
       -> verification mixed with possible: [+] verification recorded as invalid
  -> [~] ToolExecutor.execute_result()
       -> argument validation -> PermissionGate -> [~] handler
       -> [+] ExecutionResult
       -> [+] AgentState.reserve_attempt() (possible advances the generation before the handler)
       -> [+] record_execution_result()
            -> [+] ExecutionAttempt / FailureEvent / ExecutionGeneration
            -> [~] verification evidence bound to the generation
  -> [old] role=tool fed back for every call
  -> [~] ContextManager shows recent failures and budgets

[B] Not responsible for: a recover tool, automatic retry, argument correction, checkpoint, rollback, cross-process persistence.
```

The entry in this diagram is `ToolExecutor.execute_result()`, and the main consumers are `AgentState`, `ContextManager`, and the agent loop. The key to the second half of the diagram is that whether the handler succeeds or fails, the structured result is recorded and fed back; "side effects may have occurred" changes the generation first, and cannot wait for the handler to return success.

## Core Concepts and Data Structures

### 1. First treat a call as an "observed value"

The problem: error text arrives too late and is too coarse. The tool executor (Executor) is the boundary every tool call passes through, and it does three things in a fixed order: **argument validation → permission check → handler execution**. `ExecutionResult` puts the observations of these three stages together for State and the context to use.

The snippet below shows only the most important fields; `duration_ms`, the output brief, the exit code, and internal reservation information also belong to the full v0.17 result structure. The purpose of this code is to understand that "the result is not an `ok: bool`":

```python
@dataclass(frozen=True)
class ExecutionResult:
    tool: str
    arguments: dict[str, Any]
    permission: Literal["allowed", "denied", "not_checked"]
    handler_admitted: bool
    outcome: Literal["succeeded", "failed", "denied", "timeout", "invalid"]
    effect_class: EffectClass
    error_kind: str | None = None
```

The effect of this definition: invalid arguments give `outcome="invalid"` and no permission is asked; a permission denial gives `outcome="denied"` and the handler is not entered; a handler exception is turned by the Executor into `outcome="failed"`. Every result still matches one `role=tool` message; failures cannot skip the protocol feedback.

### 2. `effect_class` says "whether the environment may change"

`effect_class` is a side-effect classification, not a permission level. `none` means the call can be treated as read-only; `possible` means the runtime cannot safely prove there are no side effects. It answers "might the environment have changed after execution", while the PermissionGate answers "was this call approved". For example, `run_shell(purpose="verification")` is treated as `none` in this call.

For an approved `possible` call, State atomically reserves the attempt before the handler, advances the generation, and clears old verification evidence:

```python
before = self._verification_generation
if effect_class == "possible":
    self._verification_generation += 1
    self.verification_evidence.clear()
return AttemptReservation(attempt_id, before, self._verification_generation)
```

This order explains an easily misunderstood effect: if the handler then raises, the generation does not roll back, because it may already have written part of its content; argument errors and permission denials do not advance the generation because the handler did not run.

### 3. Attempt, Failure, and causal links

The problem is "how does the model's next round know which call a failure belongs to". `ExecutionAttempt` stores the immutable facts of one call, including the tool name, the canonical JSON hash of the arguments (a fingerprint computed after encoding the JSON in a stable order), a redacted argument summary, the generation, the result, and `failure_id`. Sensitive values are not rendered into the Context verbatim.

`FailureEvent` describes the failure itself from the attempt: the failure category, the stage where it happened, whether it is retryable, the affected files, and `caused_by_attempt_id`. So you can trace back along
`failure_id -> caused_by_attempt_id -> generation_id` instead of guessing from time order or natural language.

The two fields below are the shortest sketch of the causal chain. Look at them first to understand that "a failure does not appear from nowhere"; afterwards you can see that State stores ID relationships instead of guessing again from a whole natural language error:

```python
ExecutionAttempt(..., generation_id=generation_id, failure_id=failure_id)
FailureEvent(..., generation_id=generation_id,
             caused_by_attempt_id=attempt_id)
```

The basic classification and default retryability in v0.17:

| Observed result | category | retryable |
|---|---|---|
| Invalid arguments or protocol | `protocol` | No |
| Explicit permission denial | `permission` | No |
| Timeout | `transient` | Yes |
| Verification nonzero or failed | `validation` | Yes |
| Exception in an approved possible handler | `unknown` | No |
| Other execution failures, such as an ordinary shell nonzero exit | `deterministic` | No |

The purpose of the table is not to make readers memorize categories but to show that the same "it failed" takes different follow-up boundaries: timeouts and verification failures can count toward limited retry/repair budgets; unknown side effects cannot be retried automatically and safely.

### 4. Verification evidence belongs only to the current generation

Verification evidence is the result of one explicit check, not a synonym for "the latest tool call succeeded". Only `run_shell(purpose="verification")` returning `[exit=0]` in the current generation leaves passing evidence. Any approved `possible` call clears old evidence; a permission denial does not clear it, because the handler did not run.

In v0.17, deterministic, protocol, or permission errors finish as `failed`; unknown side effects finish as `blocked`; a retryable failure that reaches the budget for the same argument fingerprint, or a verification failure that exhausts the repair cycles, also stops. `blocked` means the current run cannot safely continue; it does not mean the task succeeded.

The key decision for the verification finish can be reduced to this condition:

```python
passed = result.outcome == "succeeded" and result.exit_code == 0
self._last_verified_generation = generation_id if passed else -1
```

It shows that "the command returned success" is not enough: the evidence must be stored together with the current generation; the next approved `possible` call clears it first.

## Why This Design

Reducing results to `ok: bool` is simplest, but it loses "was it approved", "did it enter the handler", and "might it have changed the environment". Structured results and immutable records add some fields but give later recovery reliable facts to depend on; the cost is that read-only shell commands may also be conservatively classified as `possible` because their safety cannot be proven.

Calls that are all `none` can run concurrently for throughput; as soon as `possible` appears, the whole round runs and commits in the model's order, trading concurrency for stable generation and attempt order. A round that mixes `possible` with verification marks the verification as invalid, so that a check never runs before or during a change.

This version deliberately separates "recording facts" from "deciding how to fix": no automatic retry, recovery actions, rollback, or cross-process persistence. This way the next lesson can implement bounded recovery on top of clear failure facts and budgets, without hiding the repair strategy inside the recording layer.

## Design Boundaries

- The Executor turns handler exceptions into error results; top-level LLM or CLI exceptions are still handled above.
- The next round starts only after all tool results are fed back; a failure does not skip its protocol message.
- The hash is used for stable association and counting, not as an authorization credential; the redacted summary cannot replace the PermissionGate either.
- This version cannot judge the actual effect of a partial write; it can only classify unknown side effects as `unknown` and block conservatively.
- State exists only in the current process. Ordinary history trimming does not delete failures in State, but they are not restored automatically after a process restart.

## Key Flow

The flow below shows the complete path of one call from intent to state; you do not need to memorize function names first, only see at which boundary each branch happens:

```text
tool call
  -> argument/schema validation
       └─failure -> invalid attempt -> protocol failure
  -> PermissionGate
       └─denied -> denied attempt -> permission failure
  -> possible? reserve the attempt, advance the generation, clear old verification
  -> handler
       ├─timeout / nonzero / exception -> ExecutionResult -> FailureEvent
       └─success -> attempt; verification also writes evidence
  -> role=tool fed back -> the model's next round reads Structured State
```

When you run a real task, you should see: permission denials and argument errors do not change the generation; an approved file write or execution shell requires verification again even when it fails; after context compaction, the recent failures, the generation, and the remaining budgets are still visible. After the command-line first task is handled, the program still enters the interactive loop.

## Implementation Breakdown

`Tool.effect_for()` separates the tool's default level from the verification special case. `ToolExecutor.execute_result()` only validates, authorizes, executes, and converts to an observed value; it does not guess causes for State. `AgentState.record_execution_result()` then generates the attempt, failure, verification evidence, and final status from the result. `ContextManager._render_state()` reads State's `snapshot()`, so these facts do not depend on whether old messages are still in the sent view.

## Version Features, Next Lesson, and Code Index

v0.17 turns "failure" from a piece of text into observable, countable, traceable facts, and makes verification evidence belong strictly to one generation. The next lesson chooses bounded recovery actions under these facts and budget constraints.

- [`src/mini_agent/config.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.17/src/mini_agent/config.py)
- [`src/mini_agent/state.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.17/src/mini_agent/state.py)
- [`src/mini_agent/tools/base.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.17/src/mini_agent/tools/base.py)
- [`src/mini_agent/agent.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.17/src/mini_agent/agent.py)
- [`src/mini_agent/context.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.17/src/mini_agent/context.py)

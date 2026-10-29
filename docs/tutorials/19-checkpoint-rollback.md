# Lesson 19: Single-file checkpoint and rollback (Checkpoint / Rollback, v0.19)

Previous: [Bounded recovery policy](18-recovery-policy.md) · [Tutorial overview](README.md) · Next: added as needed

> Code snapshot: `v0.19` · Adjacent diff: `v0.18.1..v0.19` · Shell: Bash/zsh

> Requirements: Python 3.10+; the core runtime uses only the standard library.

## Lesson Goals

The previous lesson can already retry, adjust, ask, or block after a failure, but it can only decide "what to do next"; it cannot undo a file write that has already happened. For example, the agent writes a file and then verification fails: calling a tool again may keep changing the file, and stopping directly leaves the failed file in the workspace. v0.19 solves one narrow but auditable part of this problem: for one approved `write_file` or `edit_file`, it saves a single-file pre-image and restores it only when the file has not been changed externally.

A "checkpoint" here is a record left before and after one file operation that is used to judge whether restoration is possible; a "rollback" restores the file to its state before the operation based on this record. It is not a workspace snapshot and not a multi-file transaction.

After this lesson, you should be able to explain:

- Why the pre-image of a regular file saves the original bytes, mode, and SHA-256, and why a nonexistent file uses an `absent` tombstone (an explicit "it did not exist");
- Why symlinks, paths outside the workspace, directories, special files, invalid parent directories, read failures, and pre-images over 1 MiB can only get `unavailable`, yet do not block the original file write;
- Why the checkpoint ID, relative path, and hashes appear both in the file tool result and in the critical Structured State, and stay visible after context compaction and degradation of an over-long state;
- Why, when a file handler raises, a clear pre- and post-image can still be restored, while an unavailable image blocks as an unknown side effect;
- Why rollback must first check checkpoint causality and reserve budget, then pass the same permission gate with the saved path, and check before restoring whether the current post-image conflicts;
- Why `rollback_checkpoint` cannot be a retry/adjust target, and why a legitimate original mode of `0` must also be restored exactly;
- Why a successful restoration still opens a new generation and requires an independent verification in the next round before the task can finish.

## Problems in the Previous Version

v0.18.1 already records failures as `FailureEvent` and recovery requests as `RecoveryAction`. The `generation` is the boundary of verification evidence: after a recovery action, old verification cannot keep proving the new state. But v0.18.1 explicitly refuses `rollback`, so it does not save "what it was before the write" and cannot safely undo files, shell, network, or other external side effects.

This lesson adds only one restricted path for file tools: capture the pre-image before the handler (the function that actually performs the file operation) and the post-image after the handler returns or raises; restoration is allowed only when both can be described clearly and the current file still matches the post-image. This way, the scope of "can be rolled back" has a clear boundary from the start.

## Prerequisites

Read Lesson 18 first and understand the intuitive meaning of these concepts: `AgentState` stores task facts, `ExecutionAttempt` represents one tool attempt, `FailureEvent` represents one failure, `RecoveryAction` represents one controlled recovery request, and `PermissionGate` decides before the handler runs whether it is approved.

The commands below are for Bash/zsh. First switch to the adjacent baseline to see the file scope, then switch back to this lesson's tag; `git diff --stat` only answers "which files changed in this version and how much", and the call order is explained later.

```bash
git checkout v0.18.1
git diff --stat v0.18.1..v0.19
git checkout v0.19
```

## New and Changed Files

| File | Change | What to look at |
|---|---|---|
| `src/mini_agent/checkpoint.py` | New | `CheckpointStore` keeps pre-image bytes inside the task; `FileCheckpoint` exposes only metadata; the restore handler does conflict checks and atomic restoration |
| `src/mini_agent/state.py` | Changed | State stores checkpoint metadata, validates rollback causality, and extends the rollback action, internal attempt, and reset boundary |
| `src/mini_agent/recovery.py` | Changed | Validates rollback requests, runs "reserve budget → authorize → open successor generation", and calls the internal tool |
| `src/mini_agent/tools/base.py` | Changed | Captures images before and after file handlers and puts the checkpoint ID into file results and execution facts |
| `src/mini_agent/tools/__init__.py` | Changed | Binds the same store to the State, Executor, and RecoveryRuntime of one task, and registers the internal restore tool |
| `src/mini_agent/permission.py` | Changed | Extracts the permission match value for `rollback_checkpoint` from the target path; the default action is ask |
| `tests/test_checkpoint_rollback.py` | New | Pins down this version's behavior with existing files, new files, conflicts, boundaries, interruptions, and state compaction scenarios |

## Version Change Map

This version spans State, recovery scheduling, tool execution, and the permission boundary. First the entry and finish of v0.18.1, then where v0.19 inserts the checkpoint; this lets you tell "the new capability" apart from "the existing recovery protocol".

Legend: `[old]` already in v0.18.1, `[+]` new in v0.19, `[~]` changed in v0.19, `[C]` main consumer, `[B]` boundary of this version.

```text
v0.18.1 baseline:
[old] write_file/edit_file
  -> [old] ToolExecutor -> handler -> ExecutionResult
  -> [old] AgentState.record_execution_result()
  -> ExecutionAttempt / FailureEvent / generation
  -> recover(retry|adjust|ask|block)
       ├─retry/adjust -> PermissionGate -> tool handler
       └─ask/block -> state-only generation -> blocked
  -> separate verification in the next round
  -> [C] Structured State
  -> [B] no file pre-image, rollback explicitly refused
```

```text
v0.19 change:
[old] write_file/edit_file
  -> [~] ToolExecutor
       -> [+] CheckpointStore.capture_before()
            -> bytes + mode + SHA-256, or absent
            -> [B] unavailable does not change the original handler behavior
       -> handler returns or raises
       -> [+] CheckpointStore.capture_after(): type + SHA-256
       -> [C] file result + critical Structured State: checkpoint metadata
  -> verification failure
  -> [~] recover(action=rollback, checkpoint_id)
       -> [+] causality check + rollback fingerprint budget reservation
       -> [~] PermissionGate: uses the relative path saved in the checkpoint
       -> [+] successor generation + internal attempt
       -> [+] rollback_checkpoint (internal tool, invisible to the model)
            -> [+] current lstat/hash
                 ├─mismatch -> rollback_conflict -> blocked
                 ├─restore failure -> rollback_restore_failed -> blocked
                 └─match -> atomic restore -> checkpoint=restored
  -> separate verification in the next round
  -> [B] still no rollback of shell, network, multiple files, or unknown side effects
```

`recover` in the baseline diagram is still this version's entry; v0.19 only adds the `rollback` branch and the checkpoints it needs. The `unavailable` branch in the change diagram deliberately goes back to the original file handler: it means "no rollback credential", not "refuse this original write".

## Key Flow

First think of one write as three facts: the pre-image is the file the handler saw before running, the post-image is the file observed again after the handler returns or raises, and the checkpoint is the task-level record that puts both observations and the restore metadata together. Only when the post-image still matches the checkpoint will a rollback not overwrite new changes made outside the agent.

```text
approved write/edit
  -> reserve attempt + possible-effect generation
  -> capture before image
       ├─regular file: bytes/mode/SHA-256
       ├─absent: tombstone
       └─other cases: status=unavailable
  -> handler returns or raises
  -> capture after image: type/SHA-256
  -> file result + critical Structured State: checkpoint metadata
       ├─ready -> rollback candidate visible
       ├─handler exception + ready -> stay running, give a rollback notice
       ├─handler exception + unavailable/uncertain -> unknown side effect, enter blocked
       └─handler success + unavailable -> keep the successful result, but no rollback candidate
  -> verification failure
  -> recover(rollback, checkpoint_id)
  -> validate a checkpoint of this task, ready, and not later than the target failure
  -> reserve rollback quota
  -> PermissionGate(path from checkpoint)
       ├─denied -> release the unused budget, do not open a generation
       └─allowed -> open successor generation + internal attempt
  -> lstat/hash the current post-image
       ├─mismatch -> rollback_conflict, refuse to write and block
       ├─restore error -> rollback_restore_failed and block
       └─match -> atomic restore, checkpoint=restored
  -> role=tool result fed back
  -> separate verification in the next round
```

When you observe this chain, the key effect is not "the model says the rollback succeeded" but: the file tool result carries a `checkpoint_id`; `status=ready` and `rollback_checkpoints` appear in State; the restore execution forms a new generation and a `rollback_checkpoint` attempt; after restoration, the Structured State explicitly requires verification. On a conflict the file should keep the external version, and State should enter `blocked`.

## Implementation Breakdown

### 1. Pre-image, post-image, and visible metadata

`create_registry(state, workspace_root=None)` binds the same `CheckpointStore` of one task to State, the Executor, and the RecoveryRuntime. The store keeps the original bytes and absolute paths in task-private memory; the external `FileCheckpoint` shows only JSON-safe metadata. The snippet below introduces the shape State and tool results see; it is not the full implementation:

```json
{
  "checkpoint_id": "cp-1",
  "attempt_id": "a-1",
  "generation_id": 1,
  "path": "src/app.py",
  "before_type": "regular_file",
  "before_sha256": "…",
  "after_type": "regular_file",
  "after_sha256": "…",
  "mode": 420,
  "status": "ready",
  "unavailable_reason": null
}
```

This shape shows three things: `path` is a workspace-relative path and does not leak the absolute root; hashes confirm the images without putting file content into the context; only `status=ready` means it can be a rollback candidate. The bytes of an existing file stay only in the store and are written back on restore; the pre-image of a new file is `absent`, and restoring it means deleting the file this write created. A pre-image exactly equal to `MAX_CHECKPOINT_BYTES` (default 1 MiB) is allowed; above the limit it is `unavailable`.

Path checks are bounded by the workspace root used when the task created the registry: an absolute path that is still inside the root after normalization is shown as a relative path, and `..` is normalized first; paths outside the workspace, any existing symlink component, directories or special files, invalid parent directories, and read failures capture no bytes. An unavailable capture does not change the admission, execution, or result of the original `write_file`/`edit_file` handler.

The pre-image saves the original mode, and restoration checks for an explicit `None`. So mode `0` is a legitimate value and is not mistaken for a default `0644`. The post-image is only used to detect concurrent changes, based on type and digest; it does not need to save the post-write content.

File tool results carry a content-free notice, for example `checkpoint_id=cp-1; path=src/app.py; status=ready`. State's `snapshot()` provides both `checkpoints` and the currently usable `rollback_checkpoints`; the Context puts the ID, relative path, attempt, generation, status, and hashes into the critical Structured State. During compaction or degradation of an over-long state, this recovery information is still kept first.

### 2. A rollback request is validated first, then authorized

The diff below shows only the protocol entry: it tells the model which checkpoint a rollback needs without exposing the internal restore tool to the model directly. The full schema also keeps `additionalProperties=False`, and the runtime does the final action-specific validation.

```diff
 parameters = {
-    "action": {"enum": ["retry", "adjust", "ask", "block"]},
+    "action": {"enum": ["retry", "adjust", "ask", "block", "rollback"]},
+    "checkpoint_id": {"type": "string"},
 }
```

So rollback cannot carry `requested_attempt`, `requested_tool`, or `requested_arguments`; other actions that carry `checkpoint_id` are also rejected. The Runtime accepts only checkpoints of the current task whose status is `ready` and whose creating attempt is not later than the target failure. When the checkpoint is missing, unavailable, already restored, or the causal order is invalid, the system records one RecoveryAction with `status="rejected"`, keeps the checkpoint, enters `blocked`, and opens no new generation.

The authorization target comes from the normalized relative path saved in the checkpoint, not from arguments the model submits on the spot. The Runtime first reserves the rollback fingerprint budget in State, then calls the `rollback_checkpoint` path rule of the same `PermissionGate`; when permission is denied, it releases the unused internal execution budget and does not advance the generation. Only after authorization does it open the successor generation and reserve the internal attempt.

This order is an important invariant of this version: an invalid request does not produce an empty generation, an unapproved restore does not bypass the permission boundary, and the model cannot use rollback to change the target path or content on its own.

### 3. The internal tool is only responsible for execution facts

`rollback_checkpoint` is registered in the task registry, but `ToolRegistry.schemas()` filters out tools with `internal=True`, so it does not appear in the LLM schema. Even if the model forges a call, the ordinary Executor returns `internal_tool` and does not run the handler. Only the RecoveryRuntime calls it, through the internal execution entry, after it has completed the checks, budget reservation, and permission authorization.

The internal call still forms a complete `ExecutionAttempt`, including `effect_class="possible"`, the permission result, generation, and the recovery and failure causal links. So rollback is not an unauditable bypass; it is just an execution entry the model cannot choose directly.

Before the handler runs, it calls `lstat` again and computes the current digest:

- Regular file pre-image: create a temporary file in the same parent directory, write the private bytes, restore the original mode, then atomically replace the target with `os.replace`;
- `absent` pre-image: `unlink` only when the current file is still a regular file matching the checkpoint's post-image;
- Different type or digest: do not write or overwrite external content; create a `rollback_conflict` failure and block;
- Temporary file, chmod, replace, or unlink failure: clean up the temporary file, mark the checkpoint `restore_failed`, create `rollback_restore_failed`, and block.

So read rollback results as State facts: the result of the recovery action is fed back as a tool result, but "the action was executed" does not mean "the task is fixed"; a conflict or restore error also shows in the attempt/failure and the terminal reason.

No internal tool can be chosen as a recovery target by `retry` or `adjust`. The Runtime rejects such requests before reserving recovery budget, checking permission, or activating a successor generation, and records one `rejected` RecoveryAction; this way no empty generation is opened, and no `reserved` action without a result attempt is left behind.

### 4. The recovery boundary when a handler raises

A file handler may raise after it has already changed part of the file. So the Executor also tries to capture the post-image on the exception path: if both images are clear, State classifies the failure as an unknown failure that can still be diagnosed, stays `running`, and issues a rollback notice with the checkpoint ID in the Structured State. The model can request rollback first and then do an independent verification.

If the pre-image or post-image is unavailable, the system can neither prove what should be restored nor prove that the current content is what the agent just wrote; in that case it enters `blocked` as an unknown side effect. This describes only the path where the handler has already raised; when an ordinary successful write gets an `unavailable` checkpoint, the original write still succeeds, it just has no rollback credential.

### 5. Verification is still required after restoration

A successful restoration marks the checkpoint `restored` and marks the RecoveryAction `executed`, linked to the internal attempt. This only proves that the recovery system completed the file operation it promised; State also clears old verification evidence and sets `verification_required` to true. The next LLM round must call an independent `run_shell(purpose="verification")`, and only success evidence of the current generation can satisfy the completion conditions again.

Restoration does not roll back the generation or reuse old verification. Even when the bytes are restored, the next verification is still the only entry for new evidence that "the current task is correct".

## Why This Design

Checkpoints use "single-file pre-image + post-image fingerprint" rather than a workspace snapshot:

- The original bytes are kept in a task-private store, which supports restoration while keeping file content out of the Context, logs, and tool results;
- The workspace root is fixed when the registry is created, so the permission scope does not drift during task execution;
- type + SHA-256 detects external changes, type replacements, and absent/regular-file changes better than comparing mtime alone;
- A temporary file in the same directory plus an atomic replace avoids leaving a half-written target during restoration; a conflict blocks conservatively, so new content the user created outside the agent is never overwritten.

Rollback keeps the two-stage recovery boundary of v0.18.1: reserve budget first, then authorize, and only then advance the generation and execute. The cost is one extra control action and a verification in the next round; the benefit is that the path, budget, attempt, failure, and recovery result are all auditable, and failures never silently overwrite external changes.

This version deliberately does not turn the recovery module into a new file executor: the real restoration still goes through the internal ToolExecutor boundary; nor does it treat the recovery result as a completion claim. This keeps unified permission, exception, and protocol records, but the capability covers only single-file images that can be clearly saved and compared.

## Design Boundaries

- Checkpoints are in-process, task-level data kept until `/reset` or `/new`; they are not persisted across processes.
- Only the pre-image of one single-file `write_file`/`edit_file` is supported; there is no rollback for shell, network, multi-file writes, or other external side effects.
- A pre-image exactly at the 1 MiB limit is allowed; above the limit, outside the workspace, symlinks, directories, special files, invalid parent directories, or read failures get `unavailable`; this does not block the original file tool call.
- Only `ready` checkpoints can take part in rollback; after a successful restoration the status is `restored`, and it cannot be restored again.
- If the current type or digest does not match before rollback, it enters `rollback_conflict` and `blocked` without overwriting external content; a recovery system error enters `rollback_restore_failed` and `blocked`.
- `rollback_checkpoint` does not appear in the model schema; the model cannot call it directly or make it a retry/adjust target; restoration does not raise permissions automatically.
- Restoration does not roll back the generation, does not reuse old verification, and does not implement Repair Loop scheduling or Trace & Replay; this version only produces the checkpoint, attempt, failure, and recovery causal facts that future replay may need.

## Version Features, Next Lesson, and Code Index

This version extends the bounded recovery of v0.18.1 into an auditable single-file checkpoint/rollback: file results and Structured State tell the model which checkpoints are available, the RecoveryRuntime decides whether a restoration qualifies, the internal handler refuses to overwrite on conflict, and verification is still required independently after restoration.

The next lesson continues to extend failure recovery or replay capabilities according to the roadmap; do not treat this version's checkpoints as multi-file transactions or a general sandbox.

- [checkpoint.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.19/src/mini_agent/checkpoint.py)
- [state.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.19/src/mini_agent/state.py)
- [recovery.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.19/src/mini_agent/recovery.py)
- [tools/base.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.19/src/mini_agent/tools/base.py)
- [tools/__init__.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.19/src/mini_agent/tools/__init__.py)
- [permission.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.19/src/mini_agent/permission.py)
- [test_checkpoint_rollback.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.19/tests/test_checkpoint_rollback.py)

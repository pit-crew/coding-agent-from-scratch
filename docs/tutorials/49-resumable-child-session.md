# Lesson 49: Resuming and continuing child sessions

Previous: [Letting subagents investigate in the background](48-background-subagents.md) · [Tutorial overview](README.md) · Next stage: evaluation and regression

Code snapshot: `v0.49` · Adjacent diff: `v0.48..v0.49`

The commands in this lesson use Bash/zsh; source links and examples all correspond to the `v0.49` snapshot.

## Lesson Goals

Lesson 48 gives every background investigation a `child_session_id`. This number lets the parent Agent find the child task within the current program, but it does not by itself contain the conversation the subagent has already read. After the program exits, the threads and in-memory conversations are gone; saving only the number is not enough to continue the investigation.

This lesson lets the parent Agent save the subagent's own conversation snapshot after a result is finished and collected. Later, after restarting the program and resuming the parent session, the parent Agent can use the original number to ask the same subagent follow-up questions.

First tell two numbers apart:

- The parent session's `session_id` is used to resume the user's whole task.
- The child session's `child_session_id` is used to continue one independent investigation within it.

After reading, you should be able to explain under what conditions a child session can be saved, what carries over after resuming, and why every follow-up must restate the investigation scope.

## Problems in the Previous Version

v0.48 keeps the active subagent objects and conversations only within the current command-line process. The parent session can record that an investigation was collected, but it does not have enough information for another process to resume that investigation.

Another difficulty is keeping the records consistent: if the parent session has written "the result was collected" while the child conversation is still only in memory, a program exit leaves the two records mismatched. This version saves the parent session and the snapshots of finished child sessions together, and allows saving only idle, collected child sessions.

## Prerequisites and Version Checkout

Read Lesson 47 first to learn about roles and Skill authorization, then Lesson 48 to learn about background starts, result collection, and the parent-side save boundary. A Skill is a local operating instruction the Agent can read on demand.

Check the version changes, then switch to this lesson's snapshot:

```bash
git checkout v0.48
git diff --stat v0.48..v0.49
git diff v0.48..v0.49 -- src/mini_agent/delegation.py src/mini_agent/session.py src/mini_agent/resume.py
git checkout v0.49
```

After reading, use `git checkout -` to return to the branch you were on before switching.

## New and Changed Files

| File | Change | What you can see here |
|---|---|---|
| [tools/delegation.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.49/src/mini_agent/tools/delegation.py) | Changed | The argument contract of the new `followup_subagent` tool. |
| [delegation.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.49/src/mini_agent/delegation.py) | Changed | How a child conversation is restored, a new round started, and a snapshot produced. |
| [state.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.49/src/mini_agent/state.py) | Changed | How each round's report, collection status, and cumulative usage are recorded separately. |
| [agent.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.49/src/mini_agent/agent.py) and [runtime.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.49/src/mini_agent/runtime.py) | Changed | How the initial start and continued investigation follow the same whole-round commit rule. |
| [session.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.49/src/mini_agent/session.py) | Changed | How schema 4 saves and checks the parent session together with idle child snapshots. |
| [resume.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.49/src/mini_agent/resume.py) | Changed | How local configuration is rebuilt on restart, and how it is decided which child sessions can still continue. |

`schema 4` here is the session file format version v0.49 uses. Compared with v0.48, the change is not just one more follow-up tool; it also includes the save format and the recovery process.

## Version Change Map

The parent Agent of v0.48 can start a subagent within one process, receive the result, and collect the report; the parent safe point does not include the subagent's full conversation. State is the structured record of the parent task's current facts and progress; the Context is the conversation and material one model request sees:

```text
[old] parent Agent
  → spawn_subagent → save the start receipt → start the subagent
  → the parent thread receives the finished result → collect with get_subagent_result
  → [B] after the process ends: the child conversation and running threads are not restored
```

v0.49 lets a collected child session continue for another round and saves idle child session snapshots atomically together with the parent session. The child Context here is the subagent's own conversation view.

```text
[old] parent Agent and background subagents
  → [~] spawn_subagent / [+] followup_subagent
  → the parent thread commits start receipts in order
  → whole round saved → the background task manager starts the child task
  → the child Context continues the investigation → this round's result
  → result collected → the child snapshot becomes idle and can be saved
  → [C] save the parent State / Context and idle child snapshots at once
  → [C] on recovery, rebuild the current role, model, and Skill configuration
  → [B] configuration identity mismatch: report that the child session cannot continue
```

Legend: `[old]` already in v0.48, `[+]` new in v0.49, `[~]` changed, `[C]` main validator or user, `[B]` boundary of this version. Arrows show calls, control, or data flow. As long as a round has not finished and been collected, the child snapshot cannot be saved as idle.

## Core Concepts and Data Structures

### 1. Every follow-up submits a new investigation contract

The "followup" in `followup_subagent` means "continue the previous round's investigation". It uses the original `child_session_id` and requires the caller to restate what this round should do, which files may be viewed, what findings should be delivered, and which read-only tools are requested. The delegation contract is this set of goals, scope, constraints, and tool requests. For example:

```json
{
  "child_session_id": "<the child session ID from the previous round>",
  "goal": "Check whether configuration loading also needs recovery adaptation",
  "scope": ["src/mini_agent"],
  "constraints": ["Read-only investigation; do not change files"],
  "expected_findings": ["Point out the relevant entries and call relationships"],
  "requested_tools": ["read_file", "grep"],
  "selected_parent_facts": ["The parent task is reorganizing the recovery flow"],
  "purpose": "investigation",
  "budget": {
    "max_rounds": 2,
    "max_llm_calls": 2,
    "max_tool_calls": 4,
    "max_tokens": 4000,
    "timeout_seconds": 20
  }
}
```

The text in angle brackets in the example is a placeholder; in a real call, replace it with the child session ID returned by the previous round. `selected_parent_facts` tells the subagent explicitly which parent task background is relevant to this round. The subagent does not automatically receive all of the parent Agent's new conversation, so the new contract must state clearly the background this round really needs. The role and model keep their original settings; the caller cannot use a follow-up to switch to a role or model with more permissions. Each time a Skill from the role configuration needs to be read, the parent side checks that Skill's authorization again.

Before sending the child model request, the runtime confirms: this is a child session of the current parent task and workspace; the previous round finished and was collected; the role, model, and Skill identities still match; this round's contract does not overstep; and the cumulative budget still has room. Child sessions that have not finished, have not been collected, or whose identities do not match cannot continue.

### 2. The conversation snapshot saves history; the budget still accumulates

A Child Session Snapshot is a bounded subagent checkpoint inside the parent session file. It contains the subagent conversation, summaries of the role and model sources, Skill file identities, the ID and digest of the most recently collected result, the round count, cumulative usage, and so on. It contains no Python worker thread and is not a background process that can keep running.

Below are a few key fields of the snapshot; the full structure also records identity summaries of the workspace, model, and Skills:

```python
@dataclass(frozen=True)
class ChildSessionSnapshot:
    child_session_id: str
    agent_profile: str
    round_index: int
    last_claimed_result_id: str
    cumulative_usage: UsageRecord
    context: dict[str, Any]
```

These fields show that the snapshot saves "which child session, which round it reached, what the previous report was, and how far the conversation and usage got", not a running thread.

On recovery, the subagent can continue from the original conversation; but every follow-up sets up a new budget for that round. The cumulative limits still include the earlier rounds and cannot be reset by saving and restarting:

| Cumulative limit for the whole child session | Meaning |
|---|---|
| 4 rounds | Including the initial investigation |
| 16 model calls | Total across all rounds |
| 48 tool calls | Counting only the allowed subagent read-only tools |
| 64,000 tokens (the unit models use to measure text) | Total across all rounds |
| 240 seconds | Time already used across rounds is checked together with this round's reservation |

Each round has its own delegation result and report ID, so collecting a new report does not overwrite an old one; collecting the same round again does not settle it twice. The parent task's own total budget and concurrency limits still apply. Continuing an old child session does not use a new subagent slot.

### 3. The parent session and idle child snapshots are saved together

The user must first turn on persistence with `/save`. Only after the subagent has finished and the parent Agent has collected the result does the system mark that round's snapshot as idle. Active threads and reports awaiting collection cannot be saved as resumable snapshots.

The save module that writes the session file puts the parent task state, the conversation, the commit record of the current tool round, and the idle child snapshots into the same schema 4 session file, then commits it with one atomic replacement. Atomic replacement means that on recovery you see either the complete old file or the complete new file, never an updated parent session with a missing child snapshot.

The save module first finishes writing a temporary file and confirms the write, then calls the standard library's file replace operation:

```python
os.replace(temporary, target)
```

This step replaces the old file with the new one as a whole; it does not delete the old session first and then copy the new content piece by piece.

Each parent session saves at most 3 child snapshots; each snapshot is at most 256 KiB, with a total of at most 720 KiB. When a snapshot is too large or fails validation, the conversation or identity is never truncated to make it fit. When a single child snapshot cannot be produced, the investigation report can still be collected and settled, but that child session cannot take follow-up questions; when the snapshots exceed the total limit, saving names the child session IDs involved.

On recovery, the program checks that the child snapshot agrees with the collected result, round count, and cumulative usage in the parent record, then reassembles the role, model, and Skill catalog from the current local configuration. If the role, model, or Skill file identity has changed, that child session is marked as unable to continue; the system does not quietly switch to another model. Old schema 1/2/3 parent sessions can still be read, but they never had child snapshots, so old child conversations cannot be restored out of nothing.

### 4. One continuation with atomic saving and the resume command

A complete path:

```text
1. Start a background subagent
2. Wait for it to finish, and collect the report with get_subagent_result
3. Enter /save in the command-line interface and note the parent session_id as prompted
4. Exit the program
5. Resume the parent session with --resume
6. Have the parent Agent call followup_subagent with the original child_session_id
```

The command to resume the parent session uses Bash/zsh:

```bash
PYTHONPATH=src python -m mini_agent --resume <session_id>
```

`<session_id>` here is the parent session ID the command-line interface gives after `/save`, not the subagent ID. After resuming, the parent Agent can choose the original `child_session_id` to continue the investigation. If the subagent was still running before the program exited, or the report had not been collected, neither saving nor resuming treats it as a continuable child session.

## Why This Design

Saving only an ID cannot restore the conversation the subagent read; saving everything without limit would leave the session file and recovery validation unbounded. So this version saves only bounded conversations that finished successfully and were collected, and writes them together with the parent session.

Submitting a contract again every round lets the new goal and file scope be rechecked at the continuation point. The role and model stay the same, Skill permissions are reconfirmed, and the cumulative budget is kept across rounds. This way recovery provides the continuation of the same restricted investigation, not an unconstrained new task.

## Design Boundaries

Only reports that finished successfully and were collected can be continued. Failed, timed-out, cancelled, interrupted, running, and awaiting-collection states cannot. A child session also cannot move to another parent task or workspace, change its role or model, or inherit old permissions.

The parent State and Trace (event records for read-only replay) save only structured information such as the child session identity, the result summary, the round count, and usage; the child conversation body is stored in the session snapshot. With persistence on, this content is saved in the local session file and should be protected like ordinary session material.

## Key Flow

```text
followup_subagent(child_session_id, new contract)
  → confirm the child session belongs to the current parent task
  → confirm the previous round finished and was collected
  → check the role, model, Skills, tool scope, and cumulative budget
  → commit the start receipt and tool results in order
  → after the whole round is saved, restore the child Context and run a new round
  → the parent thread collects and settles; the parent Agent collects the new report
  → update the idle child snapshot
  → /save atomically writes the parent session and idle snapshots

conditions not met → continuation refused before the child model request
```

## Run and Observe

After preparing local model configuration, ask the parent task to do one investigation and collect the report, then to save and continue. The key observations: the first round and later follow-ups use the same `child_session_id`; each new round still needs an explicit goal and scope; without a collected report, the command-line interface does not treat the child session as a savable idle snapshot.

After the parent session is resumed, observe whether the parent Agent can issue `followup_subagent` based on the child snapshot in the atomic file. If the local role, model, or Skill identity differs from when it was saved, the system states that the matching child session cannot continue, instead of quietly switching it to another identity.

## Implementation Breakdown

`followup_subagent` passes the parent-side tool, permission, and phase checks, then hands the contract to the background task manager to prepare. It reuses the same child Agent run loop; the difference is that it first restores this subagent's own Context from the snapshot, then uses the new contract as this round's new task input.

Results are collected and settled by the parent thread. Only after a result is collected does the background manager provide a savable idle snapshot. `session.py` puts snapshots and the parent session into the same commit; `resume.py` rereads the current local configuration on recovery and compares identities. Thread handles, running tasks, and old permission approvals are never revived from the file.

## Version Features, Next Lesson, and Code Index

v0.49 adds resumable child conversation snapshots for background investigations that finished and were collected, and adds `followup_subagent`. The parent session and idle snapshots are saved atomically together; the cumulative budget and the role and model boundaries are kept across rounds.

Lesson 49 completes the continuation chain for background child sessions. The next stage turns to Evaluation & Regression, that is, evaluating the effect, cost, and reliability of existing features.

Code index pinned at v0.49: [follow-up tool contract](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.49/src/mini_agent/tools/delegation.py), [subagent run loop and snapshot management](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.49/src/mini_agent/delegation.py), [parent task lifecycle and cumulative budget](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.49/src/mini_agent/state.py), [schema 4 saving and validation](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.49/src/mini_agent/session.py), [identity checks on recovery](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.49/src/mini_agent/resume.py).

# Lesson 23: Investigate first, then hand off a plan (v0.23)

Previous: [Plan Contract (structured plan)](22-plan-contract.md) · [Tutorial overview](README.md) · Next: [v0.24 Evidence-driven replanning and stagnation stop](24-replanning-policy.md)

> Code snapshot: `v0.23` · Adjacent diff: `v0.22..v0.23` · Shell: Bash/zsh

> Requirements: Python 3.10+; the core runtime uses only the standard library. The version comparison commands and pinned source links work directly only after the maintainer creates the `v0.23` tag.

## Lesson Goals

The previous lesson gave plans stable steps and immutable revisions, but submitting a plan entered execution immediately. Even if the model claimed it would "investigate first", the runtime did not stop it from writing files during the investigation. After this lesson, you should be able to explain how the Runtime enforces read-only investigation, why it can stop after a plan is submitted and hand the decision to the user, and why approving a plan is not the same as approving specific tools.

## Prerequisites

Read Lesson 22 first, and prepare basic Python, Git, and a working LLM configuration. The Bash/zsh commands below use the previous version as a reference and then show this version's diff:

```bash
git checkout v0.22
git diff --stat v0.22..v0.23
git diff v0.22..v0.23 -- src/mini_agent/state.py src/mini_agent/agent.py src/mini_agent/tools/base.py
git checkout v0.23
```

`git diff --stat` shows the size of the change first; the following diff helps you find the state transitions and the two layers of tool admission. Before switching tags, save any uncommitted changes in your own workspace.

## New and Changed Files

| File | Role in this lesson |
| --- | --- |
| `src/mini_agent/state.py` | Stores the planning phase, user decisions, and feedback trigger records; validates the current revision and phase transitions. |
| `src/mini_agent/tools/plan.py` | Adds `begin_plan` and `cancel_planning`, and extends `commit_plan` with a feedback reference. |
| `src/mini_agent/agent.py`, `src/mini_agent/tools/base.py` | Reject non-compliant actions at the whole-round level and the single-call level respectively. |
| `src/mini_agent/__main__.py` | Provides `--plan` startup and revision-level user handoff commands. |
| `src/mini_agent/context.py` | Keeps the current phase and user feedback visible after the conversation is compacted. |

## Problems in the Previous Version

In v0.22, `commit_plan` sent the task straight to `executing`. Complex tasks could produce a plan, but the model could call file writes or command execution before the investigation was done. The user also could not look at a full plan first and then decide whether to let it proceed.

This version makes "investigation" and "execution" different runtime phases. The investigation phase allows only side-effect-free tools; a `--plan` task stops in `awaiting_approval` after submitting the plan and waits for an explicit user decision. Ordinary simple tasks can still run directly.

## Version Change Map

Legend: `[old]` already in the previous version, `[+]` new in this version, `[~]` changed in this version, `[C]` main consumer, `[B]` boundary of this version.

```text
v0.22 baseline
[old] user task -> agent_loop -> LLM tool_calls -> ToolExecutor -> PermissionGate -> handler
                               -> commit_plan -> AgentState.commit_plan()
                                                 -> PlanRevision / executing
                     <- role=tool result for each call <- ToolExecutor
                     -> ContextManager(State snapshot) -> next LLM round / completion reminder
[old] write or execute -> generation -> independent verification -> final completion
```

v0.23 adds a planning phase check before the call chain; the handoff after plan submission is driven by the CLI, not approved by the model itself:

```text
v0.23 change
[+] ordinary task -> begin_plan ─┐
[+] --plan first task ───────────┴-> [~] PlanningState.exploring
                                       -> [C] ContextManager shows the read-only phase
                                       -> [~] agent_loop whole-round admission
                                       -> [~] ToolExecutor single-call admission
                                            ├-> side-effect-free investigation -> role=tool -> next LLM round
                                            ├-> commit_plan alone -> PlanRevision
                                            │      ├-> auto: executing
                                            │      └-> plan_only: awaiting_approval -> CLI user decision
                                            │                ├-> approve current revision -> executing
                                            │                └-> reject / continue -> exploring -> new revision
                                            └-> [B] side effects, verification, mixed submissions rejected
                                                    -> every call still gets role=tool; PermissionGate not entered
[old] executing -> PermissionGate -> handler -> generation / verification
```

The two checks solve different problems: the agent loop sees the whole round and can detect `commit_plan` mixed with other calls; the executor checks the current phase before permissions and the handler, even when called alone. Rejections produce no new generation and no verification evidence.

## Key Flow

For an ordinary task, the model calls `begin_plan` on its own; with `--plan`, the task is in `exploring` from the start. The phase is recorded in State, and the next round's context is rebuilt from the State snapshot, so it does not depend on the model remembering a sentence like "read-only, please". The key decisions of the single-call gate:

```python
if phase == "awaiting_approval":
    return "Tool call refused: the current plan is awaiting the user's decision"
if phase == "exploring":
    if name == "commit_plan":
        return None
    if name == "run_shell" and arguments.get("purpose", "execution") == "verification":
        return "Tool call refused: no verification in the exploring phase"
    if effect_class != "none":
        return "Tool call refused: only read-only investigation in the exploring phase"
```

This excerpt covers only four checks: waiting, submission, verification, and side effects; the actual function also checks `cancel_planning`, progress tools, and recovery tools. `effect_class` is the side-effect category the tool itself declares; it is not decided by plan text. `run_shell(purpose="execution")` is a call that may have side effects; even if the command looks read-only, it cannot be used for investigation. `verification` is classified as side-effect-free, but the investigation phase still rejects it separately, because there is no new execution result to accept yet.

After investigating, the model calls `commit_plan` on its own. Ordinary mode continues executing; `--plan` mode hands control to the CLI immediately, and the agent loop makes no further request to the model. When the user enters `/approve <revision_id>`, State accepts only the current revision awaiting approval. The transition below deliberately does not change the permission policy:

```python
if decision == "approved":
    self.planning_state = replace(self.planning_state, phase="executing")
```

So approval only means "you may continue working on the current approach". Later file writes or command execution are still decided call by call by the PermissionGate, based on the tool and its arguments. Approving an old revision, approving twice, and a rejection without feedback are all refused, and the state stays as it was.

Rejecting and continuing the investigation both require feedback and produce a user feedback trigger record within the current task. When the model submits a revised full plan, it must reference both the current `parent_revision_id` and the `trigger_id`; the trigger record is consumed only after the new revision is created. Continuing the investigation keeps the original plan; if new facts do not change the approach, the user can enter `/review <revision_id>` to put the original revision back into awaiting approval. A rejected plan cannot be handed off again through `/review`.

## Implementation Breakdown

`begin_task(..., mode="plan_only")` puts `--plan` in the read-only phase from the start. Ordinary mode still starts from `direct` and does not infer from task length whether planning is required. In ordinary mode, `cancel_planning` is available only before a plan has been submitted; plan-only tasks cannot use it to get around the user handoff.

When `commit_plan` in exploring appears in the same reply as other tools, the agent loop generates a rejection result for each call in the batch. So there is never partial success such as "write a file first, then submit the plan" or "submit the plan first, then run writes in the same batch". Invalid calls still get `role=tool` results written in the original order, so the model can correct them in the next round.

User decisions are written into State by the CLI and cannot be forged by model tools. Structured State shows the most recent decision and a bounded feedback summary; after context compaction they can still be rebuilt from State. Revision triggered by user feedback is the minimal record this version needs for the handoff; general replanning policies triggered by failures and read-only observations belong to the next lesson.

## Run and Observe

Run the command-line first task below in Bash/zsh. Prepare the local `config_local.py` first as the operation manual describes; after handling the first task, the program still enters the interactive loop.

```bash
PYTHONPATH=src python -m mini_agent --plan "check the current project's test entry first and give a plan before changing anything"
```

After the model investigates read-only and submits a revision, the CLI takes the plan just saved from State, shows its full content, and waits for a decision. For example, the model might submit the plan below; the goal and steps depend on the actual investigation:

```text
Plan revision 1
Goal: Confirm the project's test entry and draft a change plan
Reason: Need to understand how the existing tests run first
Constraints:
- Do not change files during the investigation
Task acceptance criteria:
- The test entry and the later verification command are identified
Steps:
1. [pending] inspect: Inspect the project's test entry
   Depends on: none
   Step acceptance:
   - The existing test command is found
2. [pending] propose: Draft the change plan
   Depends on: inspect
   Step acceptance:
   - The change scope and verification method are stated

Plan revision 1 awaiting decision:
/approve 1
/reject 1 <feedback>
/continue 1 <feedback>
```

This display comes directly from the submitted plan; the model does not need to restate it. You can now enter `/continue 1 please also check one dependency`; the model goes back to read-only investigation. If the original plan is still appropriate, entering `/review 1` shows this plan again, and you can then enter `/approve 1`. If the model submits a new revision, review the new content and decide on the new ID shown in the prompt. You can also enter `/reject 1 <specific feedback>` to have the model submit a new plan based on the feedback. Actual revision numbers follow the runtime prompts.

After approval, if the model requests a file write or command execution, you still see the matching permission decision; approving a plan does not write a permanent allow rule. `/reset` or `/new <task>` ends the handoff context of the current task, and a new task returns to ordinary mode by default.

## Why This Design

Asking for "investigate first" only in the prompt is easy to bypass with one wrong tool call; the State phase and two-layer admission make the boundary repeatably testable. The cost is that legal investigation calls in the same batch are rejected together with an illegal mixed submission, and the model has to split them into the next round.

The user approves the full approach, not the permission for one specific write. Keeping the two decisions separate lets the PermissionGate still stop an unsafe command when the plan is reasonable. The handoff also needs the revision ID and feedback kept within the task, instead of treating one natural language "agreed" as a reusable authorization.

## Design Boundaries

- Ordinary simple tasks keep the Direct Path; the Runtime does not infer complexity from keywords.
- This version provides no general `request_replan` triggered by failures or observations, no replanning budget, and no stagnation guard.
- Plan approval, step completion, and independent verification are different facts; only verification of the current generation after actual execution can support a completion decision.
- While awaiting approval, the LLM is not called and model tools do not keep running; an invalid revision entered by the user does not change the plan state.

## Version Features, Next Lesson, and Code Index

This version adds enforceable read-only investigation, the `--plan` handoff, and revision-level user decisions. The next lesson discusses how to revise the plan in a bounded way when real failures or new observations appear.

Source entries pinned to this lesson's tag:

- [`state.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.23/src/mini_agent/state.py): planning phase, user decisions, and feedback trigger records.
- [`agent.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.23/src/mini_agent/agent.py): whole-round admission and the handoff stop point after submission.
- [`base.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.23/src/mini_agent/tools/base.py): single-call admission before permissions and the handler.
- [`__main__.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.23/src/mini_agent/__main__.py): CLI startup and the user decision entry.

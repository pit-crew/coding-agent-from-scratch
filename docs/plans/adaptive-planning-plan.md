# Stage 7: Adaptive Planning & Replanning Implementation Plan

> Status: `v0.22` Plan Contract, `v0.23` Plan Mode & Handoff, `v0.24` Replanning Policy, and `v0.25` Plan Trace & Evaluation implemented
> Current baseline: `v0.25` (Plan Trace & Evaluation; `v0.24` Replanning Policy is the previous baseline)
> Prerequisite stages: Stage 5 project-aware task orchestration (`v0.14`–`v0.16`) and Stage 6 reliable execution (`v0.17`–`v0.21`)
> Version range: `v0.22`–`v0.25`

## 1. Goal and Positioning

Stage 5 already lets the model maintain a dynamic work list with a Todo, and Stage 6 made failures, recovery, verification, and terminal states auditable runtime facts. But the existing Todo still mainly answers "what to do next": it has no stable step IDs, dependencies, step completion criteria, or reasons for plan revisions, and no read-only planning boundary enforced by the Runtime. When new evidence proves the original approach no longer holds, the model can rewrite the Todo but cannot state in a structured way which parts of the plan were kept, replaced, or cancelled, or why the approach needed to change.

Stage 7 solves a higher-level problem: **first submit a verifiable plan based on read-only investigation; when new facts that overturn the original approach appear during execution, trigger replanning explicitly and form a new immutable revision; stop in time when ordinary investigation, execution, or replanning produces no new facts and no task progress; and finally be able to replay the full causal chain from trigger evidence and plan changes to execution and verification.**

The design principle of Stage 7:

```text
clear goal + read-only investigation + verifiable plan + evidence-driven revision + bounded progress + replayable acceptance
```

Target flow:

```text
Task
  -> Direct execution                         # simple tasks keep the short path
  -> Explore -> Commit plan -> Execute        # complex tasks
                         -> Observe / Verify
                         -> Continue / Done
                         -> Replan trigger
                              -> Explore
                              -> Commit revision
                              -> Execute / Block / Fail
  -> Plan Trace
```

The boundaries of Stages 5 through 7:

| Capability | Stage 5 | Stage 6 | Stage 7 |
|---|---|---|---|
| Task representation | A Todo list replaced as a whole | Keeps a read-only revision history of Todo snapshots | A Plan Contract with stable step IDs, dependencies, and completion criteria |
| Normal execution | Plan → Execute → Observe → Verify | Builds generation facts for execution and verification | Uses the committed plan to constrain the execution entry of complex tasks |
| Local failures | The model adjusts the Todo itself | Classifies and runs bounded recoveries such as retry / adjust / rollback | Moves to explicit replanning when the original approach fails, without treating replan as retry |
| Planning boundary | Relies on prompt reminders to investigate first | The Repair Loop only limits tool admission after failures | The Runtime enforces that the Explore phase allows only side-effect-free investigation |
| Human handoff | No separate Plan Mode | ask only means waiting for an external condition | `--plan` waits for user approval or rejection after a plan is submitted |
| Audit | The current Todo is visible | Replays the execution causal chain by generation | Replays plan triggers, revision differences, approvals, and execution evidence |

## 2. Scope and Non-Goals

### 2.1 Scope of this stage

- Express the task goal, success criteria, steps, dependencies, and step-level verification requirements with a structured Plan Contract
- Assign stable in-task IDs to plan steps and create an immutable `PlanRevision` for every structural change
- Distinguish plan structure changes from step progress updates, and forbid progress updates from quietly rewriting the goal or step content
- Support the model entering Explore explicitly, with the Runtime blocking possible side effects and verification in that phase
- Provide a forced read-only `--plan` mode, plus user approval, rejection, and continued-investigation handoff after plan submission
- Create a `ReplanTrigger` from an explicit failure or observation fact, then submit a new plan revision that references that trigger
- Apply stable count budgets to plan revisions and no-progress replanning
- Add deterministic stagnation detection to the Agent Loop shared by Direct, Explore, Execute, and Replan, warning and finishing within bounds when consecutive tool rounds produce neither task progress nor new valid facts
- Connect plan revisions, phase transitions, and approval records to Stage 6's Trace & Replay
- Keep the shortest path in which simple tasks need no plan

### 2.2 Not in this stage

- No separate Planner Agent, Explore Agent, Reviewer Agent, or multi-agent protocol
- The Runtime does not infer the "only correct" plan, business constraints, or success criteria from the natural language task
- No candidate plan tree search, self-scoring, voting, or automatic choice of the best approach
- No extra LLM or Agent calls to judge whether two actions or two outputs are "semantically equivalent", and no attempt to evaluate the business value of investigation facts
- Plan declarations do not change a tool's `effect_class`, and the model cannot declare a side-effect tool as read-only
- Plan approval is not treated as tool authorization; execution still goes through `PermissionGate` call by call
- Entering a new plan revision does not clear FailureEvents, RecoveryActions, verification history, or old PlanRevisions
- A plan revision itself is not treated as an environment change or verification evidence; only real side effects follow the generation rules
- No cross-process plan persistence, checkpoint resume, transactional database, or distributed scheduling
- No general sandbox, worktree isolation, multi-file transactions, or shell side-effect rollback
- No third-party runtime dependencies

## 3. Architecture Decisions to Freeze First

### D1: The Plan is model intent, not Runtime fact

The Plan Contract describes how the model intends to complete the task. `ExecutionAttempt`, `FailureEvent`, `RecoveryAction`, and `VerificationEvidence` still describe what actually happened. The two kinds of information can reference each other but cannot replace each other:

- A step marked `completed` does not prove the matching change is correct
- `success_criteria` never become passing verification evidence automatically
- A real tool success does not complete a plan step automatically either
- The final `done` still requires new verification evidence on the current generation, and meeting the plan completion conditions

The Runtime only validates the Plan Contract's structure, invariants, and reference integrity; it does not judge whether the plan is smart or sufficient in business terms.

### D2: Simple tasks keep the Direct Path; complex tasks enter planning through an explicit action

The Runtime does not secretly classify complexity by task length, keywords, or model scores. In ordinary mode, when the model thinks a task needs planning, it calls `begin_plan`; only after the call is accepted does it enter `exploring`. Simple reads, calculations, or single-step operations that do not call `begin_plan` keep the existing short path.

`--plan` is the exception the user explicitly asks for: at task start, the Runtime enters `exploring` directly and does not allow the Direct Path. This way "whether planning first is forced" has an observable source instead of relying on heuristic guesses.

### D3: Structural revisions and progress updates use different protocols

Stage 5's `update_todo` handles both "changing plan content" and "changing execution progress", so it cannot tell whether an update advances the old plan or replaces the approach. Stage 7 separates the two kinds of writes:

- `commit_plan`: submits a full Plan Contract; the initial submission, or a change to the goal, success criteria, steps, or dependencies, creates a new `PlanRevision`
- `update_plan_progress`: only updates the status of existing steps in the current revision and must not change content, dependencies, or success criteria

From `v0.22`, these two protocols are the model-visible tools; the old `update_todo` is no longer registered as a model-callable tool. Compatible reading or migration helpers can be kept internally, but must not form a second writable source of plans.

### D4: PlanRevision is an append-only revision that does not overwrite history

Each `commit_plan` creates a revision whose number increases monotonically within the task. The model submits in-task step IDs, and the Runtime validates their format, uniqueness, and consistency across revisions: the content and step-level success criteria of the same ID must not change; changing a step's meaning must create a new ID and must not reuse an old ID to rewrite history. Dependencies can change between revisions, because they describe the current execution order and do not rewrite the steps themselves.

The Runtime computes the `retained`, `added`, `cancelled`, and `replaced` differences from adjacent revisions. The model provides the revision reason and explicit `replaces` references, but the difference is based on the two validated snapshots and is not inferred from the natural language reason. Completed steps no longer depended on by active steps can be absent from the new revision, but their historical status must be kept in the old revision and the trace.

### D5: Explore is a tool admission boundary, not just a prompt suggestion

When `planning_phase=exploring`:

- Investigation tools with `effect_class=none` are allowed
- An exclusive call to `commit_plan` is allowed
- In ordinary mode, `cancel_planning` is allowed when there is no failure trigger yet
- All `effect_class=possible` tools are refused
- Verification is refused, because there is no new execution result to accept yet
- Mixing `commit_plan` with other calls in the same round is refused

This check must exist both in the agent loop's whole-round admission and in the ToolExecutor's single-call admission. Every refused tool call still gets its matching `role=tool` error result in the original order, but does not enter the PermissionGate or the handler and does not advance the generation.

### D6: Plan approval is not side-effect authorization

In `--plan` mode, after a revision is submitted, the task enters `awaiting_approval`:

- Only when the user explicitly approves the specified revision through the CLI does it enter `executing`
- A rejection must carry feedback and produce a new user-feedback `ReplanTrigger`, then return to `exploring`
- Continuing the investigation must also carry feedback; it keeps the current revision, creates a user-feedback trigger, and returns to `exploring`. After investigating, it can submit a new revision referencing the trigger, or the user can use `/review <revision_id>` to hand the unchanged current revision back for approval
- Approving an expired revision, approving twice, or approving a revision already replaced by a newer one must be refused
- Approval only means "you may continue with this approach"; it writes no allow rules to `PermissionGate`
- After that, every file write, execution shell, or recovery action still asks or is refused according to the existing permission policy

A plan submitted in ordinary mode can go straight to `executing`; whether human approval is needed is decided only by the task start mode, and the model cannot turn off forced approval by itself.

### D7: Replanning must reference a trigger fact and is bounded by budgets

Replanning is not a natural language statement like "I want to try another way". `request_replan` must create a `ReplanTrigger` that references one of these sources:

- The current active `FailureEvent`
- A recorded read-only `ExecutionAttempt` whose output brought a new fact that changes the approach
- A user rejection or continued-investigation record in `--plan` mode, or the user's explicit resume decision for a blocked task

Apart from the first plan, every `commit_plan` must reference the current active trigger. The trigger becomes `resolved` only after a successful submission; schema errors, reference errors, or budget refusals cannot consume the trigger.

At least two hard limits are maintained:

- The number of replans per task does not exceed `MAX_REPLAN_REVISIONS`
- The number of consecutive submissions for the same trigger fact without structural differences does not exceed `MAX_NO_PROGRESS_REPLANS`

After a limit is reached, no further synonymous revisions may be produced; when waiting for the user or an external condition, the task enters `blocked`, and when there is definitely no supported execution path, it enters `failed`.

### D8: Replanning connects explicitly to the Stage 6 Repair Loop

`retry`, `adjust`, and `rollback` handle local recovery within the current approach; `request_replan` means the current approach needs to change. The two cannot be submitted in the same round.

When `repair_phase=diagnosis_required` and the model chooses to replan:

1. `request_replan` must reference the `active_failure_id`
2. The Repair Loop keeps the failure and does not pretend it was recovered
3. The planning phase enters `exploring`, allowing only read-only investigation and `commit_plan`
4. After the new revision is submitted, the trigger records `result_revision_id`, `repair_phase` returns from `diagnosis_required` to `idle`, and the active failure pointer is cleared; the original FailureEvent is still kept and can be traced from the trigger
5. The planning phase returns to `executing`, and later real repair tools still create attempts and generations under the Stage 6 rules
6. Only after the independent verification following the change passes can the original failure be shown in Plan Trace as "resolved by the verification loop after the new revision"

A plan revision only resolves the diagnosis state of "which approach to use next"; it does not claim the original failure was fixed. It creates no generation and consumes no repair cycle; real approved recoveries or possible side effects still reserve generations and budgets under the Stage 6 rules. If an existing Repair Loop requires an independent verification in the next round, replanning cannot bypass it.

A task that Stage 6 already put into `blocked` cannot be reopened by the model on its own. Only when the user explicitly asks to continue, supplies a missing condition, or starts a replan through the CLI does the Runtime record a `resume_blocked` `UserPlanDecision`, create the matching trigger, and restore the task to `running / exploring`. The old terminal reason, the last failure, and all execution facts are kept. `failed` means there is no supported path within the established boundaries and cannot be resumed in place; if the user wants to change the goal or the permission boundaries, a new task should be started.

### D9: Plan constraints cannot relax higher-priority rules

The original user task, the project instructions, and the PermissionGate are always above the Plan Contract the model submits. `constraints` is only the model's working summary of known constraints: omitting a rule does not make it invalid, and writing conflicting content cannot override protected instructions.

### D10: General stagnation detection is a deterministic guard of the Agent Loop

`MAX_REPLAN_REVISIONS` and `MAX_NO_PROGRESS_REPLANS` only constrain plan revisions and cannot stop the ordinary Agent Loop from "calls succeed but it goes in circles". Stage 7 adds a lightweight, task-level `LoopStagnationState` to the existing single Agent loop; it is not a new planner, phase, or failure recovery subsystem, and it does not call the model to evaluate its own progress.

The unit of detection is a complete tool round: only after all `tool_calls` in one assistant reply have been run or refused under the existing rules, written to State, and fed back as matching `role=tool` results does the Runtime observe the round. This way detection does not break batch order, the commit order of concurrent read-only calls, or the protocol "every call has a result". Interim text without `tool_calls` keeps being handled by the existing completion reminder, with no second set of rules for text reply loops.

The Runtime uses three kinds of deterministic signals:

- **Action fingerprint**: reuses Stage 6's canonical JSON and SHA-256 to form a round fingerprint of `(tool, arguments_hash)` in model order. "Equivalent actions" here means only exactly the same tool name and validated arguments; semantic equivalence is not guessed by rewriting shell text, paths, or natural language arguments.
- **Durable progress marker**: contains only facts that change the meaning or completability of the task, such as structural differences in the Plan Contract, step statuses, the planning / repair phase, the active trigger, user decisions, changes in the set of files, and the verification conclusion of the current generation. Attempt counts, tool history length, automatically assigned IDs, generation increments, budget consumption, and revisions without structural differences do not count as progress, so "creating records" cannot get around detection.
- **New valid fact**: an `effect_class=none` investigation call that passed the phase gate, PermissionGate, and handler with outcome `succeeded`; its tool result, with volatile display fields such as the attempt ID and duration removed, is hashed from a stable summary, and the hash appears for the first time in the current progress epoch; only the hash is stored, and the full output is not copied into State. State control tools such as `begin_plan`, `commit_plan`, `update_plan_progress`, `request_replan`, and `recover`, as well as verification, do not take this "investigation fact" shortcut; they can prove progress only through the durable progress marker. Rereading the same content, getting the same search results again, schema / phase / permission refusals, and repeated errors do not count as new facts. A successful `possible` call is not disguised as an investigation fact, but an action fingerprint not executed before can count once as candidate progress in the current epoch; later successes of the same fingerprint do not count as progress again.

The existing `completion_reminder.progress_marker` cannot be reused directly: it serves the compatibility reminder for "outputting final text without meeting the completion conditions" and includes mechanical changes such as tool history length and generation; stagnation detection must use the narrower durable progress marker above, otherwise every repeated call would wrongly reset the count because of new records.

When the durable progress marker changes, a new progress epoch starts and the stagnation count is reset; a read-only fact or execution action appearing for the first time within the epoch also resets the current consecutive count, but its hash is kept until the next durable progress, so alternating between two sets of old results cannot evade detection. If a complete tool round neither changes the durable progress marker nor produces a valid fact or action appearing for the first time in the epoch, `consecutive_no_progress_rounds += 1`.

The only new behavior limit is `MAX_STAGNANT_ROUNDS`, defaulting to `3`, and the configuration must be greater than `1`:

1. In the round before the limit, the Runtime shows, through a protected Runtime Notice, the stagnation type, the consecutive round count, and the legal ways out in the current phase, such as changing the investigation direction, `commit_plan`, updating step progress, `request_replan` referencing a real trigger fact, or stating an external block explicitly.
2. If the next round still makes no progress, State enters `blocked`, and `terminal_reason` records `repeated_action`, `no_new_observation`, `explore_without_commit`, or `execute_without_progress` with the related redacted fingerprints; stagnation itself does not forge a `FailureEvent`, because the tools may not have failed.
3. All tool results produced before the terminal state must first be fed back to history; then the loop returns an explicit blocked result directly and does not let the model overwrite the terminal state with another call.

`LoopStagnationState` stores only counts, hashes, the warning, and the last reason, and enters the Structured State and the critical compaction snapshot; the hash sets must have a fixed memory limit, and only counts and the most recent redacted short fingerprints are rendered to the model. The Planning gate and the Repair gate always take priority, and the stagnation reminder cannot relax their next-action limits. `MAX_ITERATIONS` remains the final global safeguard but does not replace the earlier, explainable stagnation stop.

## 4. State Model (Plan core frozen in `v0.22`; stagnation guard appended in `v0.24`)

```text
PlanStep
- step_id
- content
- status: pending | in_progress | completed
- depends_on: list[step_id]
- success_criteria: list[string]
- replaces: list[step_id]                 # references only steps replaced in the parent revision

PlanRevision
- revision_id
- generation_id
- parent_revision_id: optional
- trigger_id: optional                 # empty for an ordinary initial plan; the first revision after a Direct failure / blocked resume has a trigger but no parent
- goal
- constraints: list[string]
- success_criteria: list[string]
- steps: tuple[PlanStep]
- reason
- diff: optional PlanDifference           # retained / added / cancelled / replaced and change flags

PlanProgressEvent
- progress_id
- revision_id
- generation_id
- step_id
- from_status
- to_status
- reason

ReplanTrigger
- trigger_id
- generation_id
- kind: failure | observation | user_feedback | blocked_resume
- reason
- caused_by_failure_id: optional
- caused_by_attempt_id: optional
- caused_by_decision_id: optional         # points to a rejected / resume_blocked user decision
- status: active | resolved | rejected
- result_revision_id: optional

UserPlanDecision
- decision_id
- revision_id: optional
- decision: approved | rejected | continue_exploring | resume_blocked
- feedback: optional
- generation_id
- caused_by_failure_id: optional
- previous_terminal_reason: optional

PlanningState
- mode: auto | plan_only
- phase: direct | exploring | awaiting_approval | executing
- active_revision_id: optional
- active_trigger_id: optional
- replans_used
- replans_remaining
- trigger_no_progress_commits            # belongs only to the current active trigger

LoopStagnationState
- progress_epoch
- consecutive_no_progress_rounds
- last_round_fingerprint: optional
- seen_observation_hashes: bounded set[hash]
- seen_effect_action_hashes: bounded set[hash]
- warning_kind: optional
- last_reason: optional
```

Invariants:

- Apart from the initial revision, every `PlanRevision` has exactly one existing parent
- A replan revision must reference one active trigger, and a trigger can be resolved only once
- Within each revision, `step_id` is unique, dependencies can point only to steps in the same revision, and the dependency graph is acyclic; `replaces` can point only to the parent revision
- At most one step is `in_progress`; when a step has unfinished dependencies, it cannot enter `in_progress` or `completed`
- `update_plan_progress` can produce only legal `pending -> in_progress -> completed` transitions and cannot go back; invalidation or replacement is expressed through a new revision
- When the structure is the same and only step statuses change, no new revision may be created; a `PlanProgressEvent` should be produced
- Revisions, progress, triggers, and user decisions all bind the `generation_id` at submission time, but these records themselves do not advance the generation
- `UserPlanDecision` contains no permission rules and cannot serve as VerificationEvidence
- The stagnation count can be updated only after all results of a complete tool round are committed; the same round cannot be partly judged, stopped early, or have tool results missing
- A progress epoch starts only when the durable progress marker changes; new attempt IDs, generation IDs, budget consumption, or repeated facts cannot start an epoch on their own

Field ownership:

- The model provides the goal, constraints, success criteria, step IDs and content, dependencies, replacement relationships, revision reasons, and replan requests
- The Runtime assigns the IDs of fact records such as revisions / progress / triggers, validates step IDs, the dependency graph, and status transitions, computes revision differences and budgets, and maintains the planning phase
- The agent loop computes the action fingerprint, valid fact hashes, and the durable progress marker after the whole round's results are committed, and updates the stagnation count atomically; the model cannot declare that a round "made progress" or reset the count
- The Executor keeps exclusive ownership of tool execution facts; the PermissionGate keeps exclusive ownership of authorization decisions
- The user produces approve / reject / resume_blocked decisions through the CLI or an explicit later input; the model cannot forge these records
- Trace consumes only the public snapshot and does not read the model's private arguments or change State

## 5. Version Slices

### 5.1 `v0.22` Plan Contract

Goal: upgrade Stage 5's mutable Todo into a structured, referenceable, verifiable plan protocol.

Main work:

1. Add `PlanStep`, `PlanRevision`, `PlanProgressEvent`, and `PlanningState`.
2. Add `commit_plan` and `update_plan_progress`, and stop exposing the old `update_todo` to the model; `begin_plan` and the forced Explore gate are left to `v0.23`.
3. Build atomic validation for step IDs, the existence of dependencies, an acyclic graph, a single in-progress step, and one-way status transitions.
4. The initial `commit_plan` saves the full goal, a constraint summary, task-level success criteria, and step-level success criteria.
5. Structured State renders the current revision, the current step, unmet dependencies, and a bounded plan summary; it is rebuilt losslessly after compaction.
6. The completion reminder also checks whether the current plan still has unfinished steps, without changing Stage 6's verification evidence requirements.

Acceptance focus: the sources of plan structure and progress are separate; invalid dependencies or progress rollbacks never partly update State; when a simple task builds no plan, behavior matches `v0.21`.

### 5.2 `v0.23` Plan Mode & Handoff

Goal: make "investigate first, then hand off a plan, and execute after user confirmation" a workflow the Runtime can enforce.

Main work:

1. Add `begin_plan`, called by the model in ordinary mode, and add a `--plan` task start mode to the CLI; both entries set the planning phase to `exploring`.
2. Implement the two-layer Explore gate that refuses side effects, verification, and illegal mixed calls per D5.
3. After a plan-only task submits a revision, it enters `awaiting_approval`, and the agent loop does not continue executing the plan.
4. Add user-side approve, reject, and continue-investigation entries; approval must reference the current revision exactly.
   Continuing the investigation keeps the current revision; it can submit a new revision referencing the user-feedback trigger, or hand the unchanged revision back for approval.
5. Rejection feedback enters the protected current task context and creates a trigger the next revision can reference.
6. Show explicitly that "plan approval" and "tool authorization" are two different events.

Acceptance focus: even if the model requests a file write or execution shell, `exploring` and `awaiting_approval` produce no side effects; approving an old revision never starts execution by mistake; after approval, high-risk tools still trigger the PermissionGate.

### 5.3 `v0.24` Replanning Policy (implemented)

Goal: when new facts overturn the original approach, revise the plan with an explicit trigger and a bounded budget, instead of silently overwriting the Todo or rewriting the approach endlessly.

Main work:

1. Add `ReplanTrigger`, `request_replan`, and the replanning count budget.
2. Support four trigger sources: failure, read-only observation, user rejection, and blocked resume, and validate that the source records really exist.
3. `commit_plan` requires an active trigger and a parent revision for replans, and resolves the trigger atomically after submission.
4. The Runtime computes the retained / added / cancelled / replaced difference between adjacent revisions; a submission without structural changes is recorded as a no-progress submission and bounded by a separate budget.
5. Connect `diagnosis_required` per D8, keeping the FailureEvent, repair budget, generation, and verification boundaries from being bypassed by replanning.
6. Per D10, add stagnation counting across Direct / Explore / Execute / Replan to the existing agent loop with a single `MAX_STAGNANT_ROUNDS` limit; this guard reuses structured tool results and plan state and adds no Agent or planning branch.
7. Structured State and the Runtime Notice show the current replan reason, source, remaining budget, stagnation count, and the only legal next action.

Acceptance focus: the entries and counts of retry, adjust, and replan are independent of each other; every replan can locate its trigger fact; unchanged replanning, repeated tool rounds, investigation without new facts, or execution without progress all finish explicitly within their own budgets, with no hidden loops.

### 5.4 `v0.25` Plan Trace & Evaluation (implemented)

Goal: replay, read-only, a task's planning chain: investigation → initial plan → approval → execution → trigger fact → new revision → verification → terminal state.

This version introduces no new planning strategy, execution action, or state transition. It extends `v0.21`'s Trace & Replay and shows, along the two stable dimensions of generation and revision:

- The parent and trigger of a revision
- The structural difference between adjacent revisions
- Progress events and their steps
- Plan-only approvals or rejections
- The attempts / failures / feedback a trigger references
- The execution, recovery, and verification facts after a revision takes effect
- The count, type, and redacted fingerprints of the last stagnation warning or stagnation terminal state
- The basis of the final `done`, `blocked`, or `failed`

Replay must not guess revision reasons the model did not record, nor infer from "the later verification passed" that the old plan was correct. Trace can show only the stagnation summaries the Runtime saved; it cannot reread tool output or re-judge progress with semantic rules. A missing parent, dangling step dependencies, a trigger consumed twice, approvals without a source, or progress events across revisions must be marked unresolved instead of being patched by the display layer.

Acceptance focus: for at least one real case of "the initial approach fails—evidence triggers a replan—the new approach passes verification", it can prove why the plan changed, what changed, and which generation's execution facts and verification evidence support the final conclusion.

## 6. Composition with the Stage 6 State Machine

Planning State and the Repair Loop are orthogonal states and cannot be merged into one ever-growing enum. Tool admission checks both and applies the stricter limit:

| Planning phase | Repair phase | Allowed next actions |
|---|---|---|
| direct / executing | idle | Execute, update progress, or verify under the existing rules |
| exploring | idle | Read-only investigation, or an exclusive `commit_plan` |
| awaiting_approval | idle | Wait for the user to approve, reject, or end; all model tool calls refused |
| direct / executing | diagnosis_required | Read-only diagnosis, an exclusive `recover`, or an exclusive `request_replan` |
| exploring | diagnosis_required | Read-only investigation, or an exclusive `commit_plan`; the active failure is kept |
| any | verification_required | Only the single independent verification Stage 6 requires; replans cannot be started or submitted |

If a combination of the two states is not in the table, the Runtime should refuse the action and return a structured protocol error; it cannot choose the looser branch on its own.

General stagnation detection is not added to the Cartesian product of states above. It only observes, after each complete tool round, "whether the round made progress"; it does not create a third set of phases or change the set of allowed actions. In `awaiting_approval` there are no model tool rounds, so no stagnation accumulates; waiting for the user is not a doom loop. Counting stops after entering `blocked` or `failed`.

## 7. Tests and Acceptance

### 7.1 Unit tests

- The Plan Contract refuses duplicate IDs, missing dependencies, self-dependencies, dependency cycles, and fields over length/count limits
- The parent, trigger, and generation references of every revision are complete, and failed submissions never partly write
- Progress updates cannot change step structure, skip dependencies, produce several in-progress steps, or roll back completed ones
- Structural revisions and pure progress updates are written to the revision and progress histories respectively
- The Explore gate refuses possible effects, verification, and mixed calls at both the loop and executor layers
- Calls refused by the phase gate do not enter the PermissionGate / handler, do not advance the generation, and every call has a tool result
- `--plan` approves only the current revision; rejection feedback cannot be forged by the model, and approval cannot write permission allow rules
- The failure / attempt / rejected decision / blocked resume references of replan triggers and their single-consumption rule can be tested repeatedly
- blocked can return to running / exploring only after the user explicitly produces a resume decision; failed cannot resume in place
- The replan revision budget and the no-progress budget are checked and reserved under the same State lock
- When the same tool and canonical arguments keep returning the same result, it is not seen as progress just because attempts / generations increment, and it finishes within `MAX_STAGNANT_ROUNDS`
- Repeated reads, repeated searches, or alternating between old results in Explore produce no new valid facts; a really different read-only result resets the consecutive count only when it first appears in the current progress epoch
- Explore with consecutive rounds of no new facts and no `commit_plan`, Execute running the same action repeatedly without updating the plan/task facts, and ordinary calls looping in place on the Direct Path all get their matching stagnation reason
- Phase / permission / schema refusals and repeated errors do not count as progress; before the stagnation terminal state, one tool result is still fed back for every call
- Committing a new structure, legal step progress, a real phase transition, a new user decision, or a new verification conclusion starts a progress epoch; pure ID, generation, budget, or history length changes do not
- After compaction, the stagnation warning keeps the count and redacted hashes; when the Planning / Repair gate is stricter than the warning's suggestions, the gate prevails
- The diagnosis → replan → execute → verification combination does not clear the original failure or reuse old verification evidence
- After compaction, the current revision, active trigger, planning phase, budgets, and step progress stay accurate
- Plan Trace depends only on the public snapshot; broken chains, cycles, double consumption, and corrupted records are shown as unresolved
- No regressions in the Direct Path of simple tasks, the Stage 6 Repair Loop, or old trace queries

### 7.2 Stage-level E2E scenarios

1. A simple read-only task creates no plan and finishes directly.
2. A complex change task investigates read-only first, submits a plan with dependencies and success criteria, and passes independent verification after execution.
3. Under `--plan`, the model's attempt to write a file is refused; after submitting the plan it waits, and only after the user approves does execution start, with execution still triggering tool permissions.
4. The user rejects the initial plan with feedback, the model submits a new revision based on that feedback, and the old revision is kept.
5. The initial approach causes a deterministic failure or a verification failure; the model references the real failure to start a replan, and the new approach executes and passes verification in a new generation.
6. Plans without structural changes are submitted repeatedly for the same trigger fact; after the budget is exhausted, it enters blocked or failed explicitly, with no infinite loop.
7. In ordinary mode, reproduce "the same tool and arguments called repeatedly", "repeated reads without new facts in Explore", and "repeated actions without step progress in Execute"; when still unchanged after the warning, it enters blocked with an explicit reason; when switching to new investigation or submitting real progress, the count recovers correctly.
8. After at least one compaction, step dependencies, the active revision / trigger, the Repair Loop, the stagnation count, and verification boundaries stay accurate.
9. Plan Trace can connect the replanning cases above with Stage 6's attempt / failure / recovery / verification causal chain and show the basis of the stagnation terminal state.

### 7.3 Stage definition of done

- [x] `v0.22` Plan Contract has its own tutorial, change record, and runnable tests
- [x] `v0.23` has its own tutorial, change record, and runnable tests (the tag facts check awaits the user creating the tag manually)
- [x] `v0.24` has its own tutorial, change record, and runnable tests (the tag facts check awaits the user creating the tag manually)
- [x] `v0.25` has its own tutorial, change record, and runnable tests
- [x] Plan structure, step progress, execution facts, and verification evidence each have a single, distinct write source
- [ ] Simple tasks keep the short path, and complex tasks can explicitly enter the Runtime-constrained Explore → Commit → Execute flow
- [ ] `--plan` produces no side effects before user approval, and approval does not bypass the PermissionGate
- [ ] Every replan references a real trigger fact and keeps the parent revision and structural difference
- [ ] When a failure triggers replanning, Stage 6's failure, generation, repair budget, and verification isolation still hold
- [ ] Replan counts and no-progress submissions have hard limits, with no hidden loops after exceeding them
- [ ] Direct, Explore, Execute, and Replan share a deterministic stagnation guard; repeated actions, investigation without new facts, and execution without state progress first receive one warning, then finish with an explicit blocked reason
- [x] Plan Trace can replay at least one failure—replan—execute—verify case and marks corrupted references explicitly
- [ ] The default test suite, the tutorial check, and the stage-level E2E all pass, and the core runtime still uses only the standard library
- [ ] After the user manually creates each version's tag, the tutorial facts check passes and release acceptance is complete

## 8. Version Dependencies

```text
v0.21 Trace & Replay
    ↓ provides generations, TodoRevision, and failure/verification causal facts
v0.22 Plan Contract
    ↓ provides stable revision, step, and progress protocols
v0.23 Plan Mode & Handoff
    ↓ provides the Explore boundary and user approval facts
v0.24 Replanning Policy
    ↓ produces bounded new revisions from trigger evidence, and adds the general stagnation guard to the whole single Agent loop
v0.25 Plan Trace & Evaluation
    ↓ accepts the full planning and execution chain read-only
```

Do not add the forced read-only Plan Mode early in `v0.22`, do not simulate replan triggers with prompts in `v0.23`, and do not introduce a separate Planner Agent at the same time in `v0.24`. General stagnation detection lands as a cross-cutting guard of the `v0.24` "bounded progress" policy; it does not change the Explore → Commit → Execute → Replan main thread and derives no new planning role or state machine. Each version keeps one clear topic, so the code diff between adjacent tags is teachable.

## 9. Documentation and Release Sync

When each version is complete, sync:

- The learning path and current status in `README.md`
- The Stage 7 navigation in `docs/tutorials/README.md`
- The matching version tutorial
- The latest usage and state protocol in `docs/operation/manual.md`
- `CHANGELOG.md`
- The version information in `pyproject.toml`
- The implementation status and check items of this plan
- When necessary, the hard constraints in `AGENTS.md` that really affect running, authorization, and change behavior

Before committing, run:

```bash
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python scripts/check_tutorials.py
PYTHONPATH=src python scripts/check_readme.py
```

After the tutorial is complete and the user manually creates the matching tag, run the tutorial facts check that depends on local Git objects. The assistant must not create, move, overwrite, delete, or push tags.

## 10. Capability Boundaries After the Stage

After Stage 7, mini_agent no longer just "has a Todo that changes", but: **complex tasks can first investigate within a side-effect-free boundary and submit a verifiable plan; when new facts appear during plan execution, it can explain why replanning is necessary, keep the old approach, and submit a bounded new revision; if ordinary investigation, execution, and replanning keep producing no new facts or task progress, the deterministic guard warns and stops; user approval, tool authorization, actual execution, and final verification each have independent fact sources, and the whole chain can be replayed read-only.**

Problems still unsolved include cross-process recovery, long-term memory, general sandboxing, and multi-agent collaboration. The next stage should choose one of them based on the main failure modes in real use, rather than mixing them into Stage 7 early.

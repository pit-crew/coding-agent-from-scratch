# Stage 13: Lightweight Agent Collaboration Implementation Plan

> Status: `v0.47`, `v0.48`, and `v0.49` implemented
> Suggested version range: `v0.47` Agent Profiles / Roles, `v0.48` Background Subagent, `v0.49` Resumable Child Session
> Capability prerequisites: Stage 10 controlled subagent delegation (`v0.34`–`v0.39`), Stage 9 sessions and crash recovery (`v0.30`–`v0.33`), Stage 12 local Skills (`v0.45`)
> Related plans: `subagent-delegation-plan.md`, `session-persistence-resume-plan.md`, `mcp-skills-plan.md`

## 1. Goal and Positioning

Stage 10 already has single-level read-only Subagents, independent Context, a shared `AgentRuntime.run()`, multiple providers, budgets, cancellation, bounded parallelism, and durable result delivery. But the existing `delegate_task` is a synchronous tool: child tasks within the same parent tool round can run in parallel, yet the parent Agent still has to wait for all results to be committed in order before requesting the next model round. What `v0.39` saves is the fact of result delivery, not a full child Context that can continue the conversation.

The question this stage answers: **how can the parent Agent choose a suitable read-only role, wait for child tasks while doing its own work, and later continue the same child session, while keeping the existing tool protocol, authorization, and recovery boundaries?**

The target flow of this stage:

```text
spawn(profile, task) → child_session_id + accepted start result
the parent Agent continues its own tool rounds and model rounds
child task finishes → CLI notification / queryable completion event
get_result(child_session_id) → this round's bounded structured result
followup(child_session_id, task) → the next round of work in the same child Context
```

`v0.48` froze the interaction semantics as `spawn_subagent`, `get_subagent_status`, `get_subagent_result`, and
`cancel_subagent`. The synchronous behavior of the existing `delegate_task` is kept as a compatibility entry; it is not quietly turned into a background call.
Stage 13 only extends cognitive collaboration; the parent Agent still exclusively owns workspace changes, the main Plan, permission interaction, authoritative verification, and the completion decision.
`v0.49` is complete: the parent Agent can submit a complete new investigation contract only after the successful result has been collected; idle snapshots are saved atomically with the parent task's safe point, and the current role, model, and Skill identities are rechecked on recovery. After this stage, the new-capability roadmap closes, and Stage 14 focuses on Evaluation & Regression.

## 2. Scope and Non-Goals

### 2.1 Scope of this stage

- `v0.47` adds named subagent profiles: `explorer`, `reviewer`, `tester`, and `general`. Each profile freezes a role prompt, an approved local model alias, a tool subset within the four-tool allowlist, a permission policy, and the available Skill IDs; restricted local custom profiles are allowed.
- `v0.48` adds background child tasks within the current CLI process. The parent Agent continues working after the single tool result of every start call and the whole-round boundary are committed; child tasks run within bounded concurrency, budget, and cancellation boundaries.
- When a background task finishes, it produces an auditable status event and a CLI notification. The parent Agent queries the status and collects the bounded result through explicit tools; the notification carries only identity and status and never injects the full child result implicitly.
- `v0.49` saves bounded, verifiable child session snapshots for finished child tasks; the parent Agent can append follow-up tasks by `child_session_id` within the same parent task, and continuation still works across one safe save and resume.
- One child session can have several rounds run in order; each round has its own result and usage, and the cumulative budget and the parent task's aggregate budget stay in effect.

### 2.2 Not in this stage

- Subagents get no ability to write files, run shell, operate processes, run tests, operate the parent Plan/State, create verification evidence, call MCP Tools/Resources/Prompts, or delegate again; depth is fixed at 1.
- No message bus between Agents, shared Task Graph, autonomous task grabbing, recursive Teams, negotiation voting, distributed scheduling, or resident workers across tasks.
- No background workers that keep running after the parent process exits, and no automatic restart of interrupted child model requests. Cross-process continuation in `v0.49` applies only to finished, saved child sessions.
- Profile prompts or Skill bodies are not treated as authorization; child results do not replace the parent Agent's independent review and verification.
- The existing `delegate_task`'s one-call-one-result behavior and in-round commit in model order are not changed.

## 3. Architecture Decisions to Freeze First

### D1: A profile is restricted configuration, not a new permission principal

A profile uses a stable ID to describe the role, purpose, prompt, model alias, tool subset, permissions, and Skill IDs. The semantics of the built-in profiles must match their real capabilities: `explorer` finds locations and relationships, `reviewer` reviews read-only, `tester` analyzes test coverage and suggests verification commands but cannot claim to have run tests, and `general` does unspecialized read-only investigation.

The effective capability is **the system subagent allowlist ∩ the profile's tool set ∩ this contract's requested set ∩ the scope gate**. Unknown profiles, model aliases, tools, or Skill IDs are refused before the child Runtime is created; there is no silent downgrade to `general`, the parent model, or another provider. A profile cannot use configuration to open `run_shell`, write tools, MCP, parent state tools, or recursive delegation.

Local profile definitions use only restricted fields and bounded text, accepting no executable code or arbitrary file references; the configuration fingerprint is frozen before start, and on recovery it is re-resolved from the current local configuration and checked for compatibility. `delegate_task` can keep its original arguments and default read-only behavior; the new entry takes the profile as an explicit field and does not confuse the old `model_profile` with the role profile.

### D2: Skills can provide role guidance but cannot expand subagent permissions

The current Stage 12 hard constraint is that Skills are available only to the parent Agent. To support profile-bound Skills in this stage, `v0.47` must explicitly revise the runtime hard constraint in `AGENTS.md` about subagent Skills and update the operation manual accordingly; until that revision is done, no profile can load Skills into a subagent.

The revised scope should still be very narrow: a profile only lists Skill IDs; at spawn/followup admission, the parent side completes a separate PermissionGate authorization for each ID and freezes the accessible set for this round. The child Runtime can read only authorized IDs on demand, reusing the existing Skill Catalog's identity, path, size, and change rechecks; the body enters the child history as an untrusted ordinary tool result, not the system prompt, parent State/Trace, or verification. Background threads must not pop up interactive authorization; calls to Skills that were not pre-authorized are refused directly. Commands mentioned in a Skill still cannot be run.

### D3: A background start call delivers only the start fact

One `spawn` tool call can produce only one matching `role=tool` result, whose content is the `child_session_id`, the profile, the accepted/refused status, and a bounded budget summary. Only after this result is committed in order with the other tool results of the same round can the parent Runtime request the next LLM round. A finished child task cannot add a second `role=tool` result to the original call.

The background completion event is written into structured state and sends a bounded notification to the CLI; at the next safe boundary, the parent model sees only an ID/status hint generated by the Runtime. The full result is returned through an explicit `get_result(child_session_id)` as that call's own matching `role=tool` result. Queries and collection must be repeatable and idempotent by result ID: repeated queries produce no new child result and are not billed twice. Child results keep their low-trust material identity.

### D4: Background work spans parent rounds; commits are still finished serially by the parent thread

Worker threads only run the child Runtime and produce results that pass contract validation; they do not rewrite the parent Context, parent Plan, parent generation, or parent session directly. The parent CLI/Runtime collects completion events at explicit safe boundaries and updates the parent-side lifecycle and budget ledger in a fixed order; the parent model's tool results are still committed in their call order. Completion order can be out of order, notification order has a deterministic rule, and results can be queried by ID, so a lost notification never loses a result.

The number of background workers, the running count, the waiting queue, and per-round and cumulative model call/token/wall-clock budgets all have hard limits.
`MAX_SUBAGENTS` and `MAX_CONCURRENCY` are enforced by the State ledger and concurrency slots shared by synchronous and background calls; they are reserved atomically before start.
Only after each start confirmation is committed in order and the whole parent tool round is committed can workers start. Failures, cancellations, timeouts, and model call exceptions must all settle actual consumption and produce a bounded result. The parent model's closing text cannot bypass the completion gate "there are still active or uncollected child tasks".

### D5: The background nature of `v0.48` is limited to the current process

`v0.48` lets the parent Agent keep working on other things while child tasks run, but running threads and requests cannot become a safe point. At that time, a manual `/save` refuses explicitly and states the active IDs; the CLI's automatic safe point saving should be deferred until the tasks finish; it must not interrupt the parent Agent's normal work because it temporarily cannot save, nor disguise active threads as a recoverable durable session. `/new`, `/reset`, EOF, exit, and exception cleanup keep the bounded cancel-and-wait: when not finished, keep the old task and report the IDs/reasons. Recovery after an abnormal process exit records interrupted, does not replay automatically, and does not claim to have received unpersisted results.

If `/save` is on, committing start confirmations still follows schema 3's `handler_admitted` before the handler, per-call atomic commits, and whole-round committed rules. State and the boundary save the accepted contract identity and reserved budget, not thread handles; workers must wait until the whole round is committed before starting. If the start result or the whole-round commit fails, no worker starts; if the whole start round was saved but the process crashed before the result was collected safely, recovery marks `interrupted`, settles at the reserved limit, and does not restore the worker. Requests in a round that was not fully committed, confirmed but not started, release their reservations, and no executed results are forged.

### D6: `v0.49` saves a child session, not just an ID

`child_session_id` is a stable, unguessable identifier allocated by the Runtime and bound to the workspace, the parent task, the role profile, and a model binding summary. Continuation must use the same child Context/history, the read-only facts in the child State that may carry over, the consumed budget, and the round number. Each followup produces a new contract and a new result ID; old results cannot be rewritten.

The first version saves a bounded child snapshot atomically together with the parent session only when the child session is idle, the previous result has been delivered, and the parent task is at a safe save point. A session schema upgrade is suggested while keeping schema 1/2/3 readable; it is not acceptable to save only the ID in the parent file and leave the history in memory. Child history, Skill bodies, and so on may enter the private session, still subject to the existing size, permission, and sensitive value limits; when over a limit, continuation or saving is refused explicitly, and key identity and budget facts are never trimmed silently.

Cross-process `/resume` rebuilds the model binding, profiles, and the Skill Catalog from local configuration. When the source fingerprint or role capabilities are incompatible, continuation of that child session is paused and the reason reported; it must not switch models automatically, expand the tool set, or replay the previous round. Other finished child sessions and the parent task can still be handled under the existing recovery semantics. A running child task can never be saved as a continuable snapshot.

### D7: Followup keeps the identity and rechecks this round's authorization

Only the parent task that created the child session can request a followup; IDs after the old task ended, `/new`, or `/reset` cannot be used across tasks. The previous round must be idle and its result collected; concurrent followups or changing the profile/model/authorization while running are refused. A new request still needs to check the scope, selected facts, current phase, profile, Skill grant, and budget; an old "allow once" permission cannot pass a new call.

The cumulative budget is not reset by a followup or a parent session resume. A child session's available rounds, LLM/tool/token, and wall-clock limits must distinguish "this round's limit" from "the session's cumulative limit"; the parent aggregate budget settles new and continued sessions uniformly, and `max_subagents` counts only new creations. Child evidence in results still cannot become parent verification evidence.

### D8: Keep a single Runtime and the existing exception boundaries

Each child round still uses an independent `AgentRuntime.run()` instance; `SubagentRunner` is only responsible for assembling or restoring the child Context, calling the shared loop, closing child errors, and validating results; no background-only agent loop may be written. The tool layer/executor keeps converting handler errors into the matching tool results; no new fallback is added for parent top-level LLM and CLI exceptions.

Parent task phases such as `exploring`, `--plan` awaiting approval, Crash Recovery, repair/verification, and terminal must have an explicit admission matrix. In particular, a read-only child result does not equal authorized verification; background runs cannot let the parent task enter `done` while there are unfinished results. Trace only consumes the parent structured snapshot read-only; it does not actively inspect child threads, load Skills, or open child sessions.

## 4. Version Slices and Implementation Tasks

### 4.1 `v0.47`: Agent Profiles / Roles

1. Define a restricted `AgentProfile` and Catalog: four built-in roles, optional local custom ones, stable IDs, descriptions, frozen model aliases, prompts, tool subsets, permissions, and Skill IDs. Distinguish the role profile from the existing provider `model_profile`.
2. Extend child Runtime assembly to include the profile prompt in the protected role rules, while the contract and selected facts stay on the untrusted user side; tools and scope are intersected, and over-privileged configurations are refused. Keep the default behavior of the old `delegate_task`.
3. Design child Skill pre-authorization and loading boundaries per D2, revising the matching hard constraint in `AGENTS.md` and the operation manual; MCP and shell are not opened to subagents. If authorization and identity rechecks cannot be completed, v0.47 cannot claim "profile-bound Skills" as delivered.
4. Test the four roles' capabilities, unknown/over-privileged profiles, invalidated model aliases, tool intersection, unauthorized and replaced Skills, parent/child Context isolation, and old delegation compatibility.

Acceptance: choosing different roles for the same task gives observable and restricted prompt/tool/model configurations; `tester` cannot run tests, and Skills grant no tool permissions; old synchronous delegation results and budget contracts stay compatible.

### 4.2 `v0.48`: Background Subagent (implemented)

1. Added four parent-side tools: `spawn_subagent`, `get_subagent_status`, `get_subagent_result`, and `cancel_subagent`; start returns a single confirmation, the completion notification gives only ID/status, and results are collected idempotently by ID.
2. Extended the Manager into a task manager that spans parent rounds; workers only write to a thread-safe completion queue, and the parent side collects and settles at safe boundaries. The synchronous `delegate_task` path stays as is, and both modes share concurrency slots and the parent aggregate budget.
3. Froze phase admission, the pure-spawn round gate, starting after the whole round's durable commit, the completion gate, safe point refusal, bounded cancellation, and exit and crash semantics; schema 3 saves only identity, reserved budget, and lifecycle, not thread handles.
4. Covered the parent Agent continuing model rounds while child tasks run, out-of-order completion, status queries, repeated collection, budget contention, cancellation, timeouts, exceptions, result collection faults, safe point refusal, round commit failures, no replay after crashes, and synchronous delegation compatibility.

Acceptance: passed. The parent Agent can keep working independently while background child tasks are unfinished; the original start call has exactly one result, later results can be collected repeatedly but are settled only once; active tasks cannot be saved as clean or let the parent task enter `done`.

### 4.3 `v0.49`: Resumable Child Session (implemented)

1. Added `followup_subagent`, which stably reuses `child_session_id` and produces a new `delegation_id`, `result_id`, and usage each round; it accepts only collected successful results under the same parent task/workspace and requires a complete new investigation contract.
2. `SubagentRunner` restores the child Context from a bounded `ChildSessionSnapshot`, appends this round's contract input, and calls the shared `AgentRuntime.run()`; the role and model stay frozen, and Skill permissions are requested again each round. Child history does not enter the parent State or Trace.
3. Raised the newly written session schema to 4, saving idle snapshots in the same atomic commit as the parent State, Context, and tool boundary; validates result references, message pairing, round continuity, identity, usage, and the 256 KiB/720 KiB snapshot limits, while keeping schema 1/2/3 readable.
4. On recovery, rebuilds and rechecks the role, model binding, and Skill file identities from the current local configuration; incompatible snapshots are reported separately. Only idle snapshots are restored; workers are not restored and requests are not replayed.
5. Covered two rounds of the same child session, parent/child history isolation, idempotent collection, safe point recovery, the cumulative budget, pure start rounds, whole-round commit faults, snapshot/State mismatches, and schema 3 read compatibility.

Acceptance: passed. A collected child session can continue under its original ID after `/save`, process rebuild, and `/resume`; the child model sees its own history but not the full parent history; cumulative usage does not go back, and old results are neither recomputed nor settled twice. Failed, timed-out, cancelled, interrupted, active, and uncollected rounds cannot be continued.

## 5. File and Boundary Mapping

| Location | Expected change | Responsibility |
|---|---|---|
| `src/mini_agent/delegation.py` | Updated | Profiles, background lifecycle, restricted child Context snapshots, followup, cumulative budget, and identity rechecks; no copied agent loop |
| `src/mini_agent/tools/delegation.py`, `tools/__init__.py` | Updated | Background start, followup, status/result queries, cancellation, and synchronous tool compatibility |
| `src/mini_agent/runtime.py`, `agent.py`, `tools/base.py` | Updated | Pure start rounds, start after the whole round is committed, settlement at parent-thread safe boundaries |
| `src/mini_agent/state.py`, `session.py`, `resume.py` | Updated | Structured multi-round lifecycle, schema 4 snapshots, budget, identity validation, old schema compatibility |
| `src/mini_agent/permission.py`, `skills.py`, `prompt.py` | Targeted changes | Profile permission intersection, Skill pre-authorization, and child identity hints |
| `src/mini_agent/__main__.py`, `config.py` | Incremental | Local configuration, completion notifications, `/save`, recovery, and task boundary cleanup |
| `tests/`, `docs/tutorials/`, the operation manual, `README.md`, `CHANGELOG.md` | Synced per version | Offline concurrency/fault tests, one teaching thread and navigation per version |
| `AGENTS.md` | Updated in v0.47–v0.49 | Child Skill contract, multi-round continuation, background lifecycle, safe point, persistence, and recovery hard constraints |

## 6. Cross-Cutting Acceptance and Delivery

1. Keep parent and child sharing the canonical `AgentRuntime.run()`; children stay single-level and read-only, and the parent exclusively owns changes, the Plan, PermissionGate user interaction, generation, verification, and the completion decision.
2. Every model tool call has a single `role=tool` result, and results in the same round are committed in model order; background completion notifications never forge tool results or user messages.
3. Profiles/Skills/model bindings are validated before going online, and source summaries leak no real endpoint, model ID, API key, or auth headers; Skills, files, and child results are always untrusted material.
4. Creation, background execution, cancellation, failure, recovery, and followup are all bound by per-round and cumulative budgets; no duplicate child results, duplicate settlement, or usage reset by a new ID.
5. A `v0.48` crash does not replay active child tasks automatically; `v0.49` restores only idle child sessions at safe points. Corrupted or incompatible child snapshots are refused explicitly, never filled in by guessing.
6. Cover regressions of synchronous delegation, Plan/Repair, v0.33 Crash Recovery, v0.39 Durable Delegation, process management, and Stage 12 Skills; the core runtime still depends only on the standard library.
7. Before implementation, recheck the unresolved subagent sensitive path issue in the Stage 10 plan; profiles, background runs, and continuation must not widen its impact. When delivering each version, run the related tests and `PYTHONPATH=src python -m pytest -q`, `PYTHONPATH=src python scripts/check_tutorials.py`, and `PYTHONPATH=src python scripts/check_readme.py`.
8. Documents, tutorials, and version information are updated version by version according to the actual implementation; tags are operated only manually by the user.

## 7. Stage-Level End-to-End Scenarios

1. The parent Agent starts two read-only tasks with `explorer` and `reviewer`, gets two IDs, and keeps working on the main task; the two child tasks finish out of order, the parent receives notifications and collects each result.
2. `tester` analyzes test coverage and proposes verification the parent Agent can run; the parent Agent runs the verification itself, and the child report does not enter the parent `verification_evidence`.
3. While background child tasks run, the parent tries `/save`, `/new`, or exit: saving refuses explicitly, and the task switch first cancels within bounds; when it cannot finish, the old task and IDs are kept.
4. With `/save` on, inject faults at the start ack, child result generation, notification, and collection boundaries; recovery neither starts nor delivers twice, and never forges unsaved results as success.
5. After a child session with a collected result is saved and resumed, the parent appends a question using the original ID; the child keeps its own history and cannot see the full parent history, other child sessions, or old permissions.
6. When the profile/model configuration changes, a Skill file is replaced, a child snapshot is corrupted, or the budget is exhausted, the followup is refused explicitly before the next model request.

## 8. Definition of Done and Later Stages

- [x] `v0.47`: the four roles and restricted custom profiles are reproducible; model, prompt, tool, permission, and Skills bindings are all validated at runtime, and the old `delegate_task` is compatible.
- [x] `v0.48`: the parent Agent can keep working across rounds, child completion can be notified and queried; active tasks are cancelled within bounds, and save and crash semantics are clear.
- [x] `v0.49`: the same child session can follow up safely, idle snapshots can be restored across processes, and cumulative budgets and permissions do not regress.
- [x] No regressions in synchronous delegation, the tool protocol, durable boundaries, recovery, Plan, verification, or the isolation of Stage 12 external capabilities.
- [x] Version documents, the operation manual, tutorials, README, CHANGELOG, and package version information synced; stage-level offline fault coverage added.
- [x] Full pytest, the tutorial structure check, and the README check pass; code compilation and `git diff --check` pass.
- [ ] The tutorial pinned-tag facts check has been run; apart from the `v0.49` tag not yet created by the user, there are no other problems, and the check must be rerun after the tag exists.

After these conditions are met, Stage 14 does only Evaluation & Regression of capability, reliability, cost, and version evolution; defects found are handled as fixes, and heavier multi-agent infrastructure is not enabled by default.

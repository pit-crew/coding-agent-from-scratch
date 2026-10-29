# Lesson 24: Evidence-driven replanning and stagnation stop

Previous: [Read-only planning and user handoff](23-plan-mode-handoff.md) · [Tutorial overview](README.md) · Next: later version lessons (to be planned)

Code snapshot: `v0.24` · Adjacent diff: `v0.23..v0.24`

The example commands in this lesson are for Bash/zsh. Before running them, prepare local configuration in the repository root; a command-line argument is only the command-line first task, and the process still enters the interactive loop afterwards.

## Lesson Goals

The previous lesson already lets the Agent investigate first, submit a plan, and wait for the user's decision in `--plan` mode. After this lesson, you should be able to explain two things: how new evidence during execution requires the model to cite a real source to submit a plan revision, and why repeated tool rounds first receive one Runtime Notice and then enter a `blocked` state with a reason.

This lesson only adds a runtime policy inside a single Agent loop. It adds no separate Planner, and it does not implement the full Plan Trace of the next lesson.

## Prerequisites

You need basic Python, Bash/zsh, and the Plan Contract concept from the previous lesson. Read [Lesson 23: Read-only planning and user handoff](23-plan-mode-handoff.md) first, because this lesson keeps using `planning_state`, `PlanRevision`, `PermissionGate`, and the `Repair Loop`.

First look at the actual difference between the previous lesson and this one:

```bash
git checkout v0.24
git diff --stat v0.23..v0.24
```

If the `v0.24` tag does not exist locally yet, you can read the source on the current branch; pinned links and release fact checks still follow the snapshot after the user creates that tag.

## New and Changed Files

| File | Role in this lesson |
| --- | --- |
| `src/mini_agent/state.py` | Stores four kinds of triggers, revision differences, the replan budget, blocked resume decisions, and stagnation state, and validates and transitions them under one lock. |
| `src/mini_agent/tools/plan.py` | Registers the model-callable `request_replan` tool. |
| `src/mini_agent/tools/__init__.py`, `src/mini_agent/permission.py` | Register the plan control tools and let `request_replan` pass the permission gate by default. |
| `src/mini_agent/tools/base.py` | Enforces the new planning/repair gate at the single-call boundary. |
| `src/mini_agent/agent.py` | Rejects illegal mixed rounds and, after all tool results are fed back, computes the round fingerprint, fact summaries, and stagnation state. |
| `src/mini_agent/__main__.py` | Adds `/resume <feedback>` so ordinary text cannot silently resume a terminal state. |
| `src/mini_agent/context.py`, `src/mini_agent/prompt.py` | Show the active trigger, budgets, stagnation counts, and legal next actions, and explain the replanning exception of the Direct Path to the model. |
| `src/mini_agent/config.py` | Adds three bounded progress and replanning budgets and validates them at startup. |

## Version Change Map

The real finish of the previous lesson is entering `executing` after `commit_plan`, and failures go to the Repair Loop; the model has no revision entry that can cite execution facts. The baseline diagram below keeps that call chain so the new entry can be placed back into the original single Agent loop:

```text
[old] agent_loop -> ToolExecutor -> PermissionGate -> handler
                                   -> AgentState.attempts / failures
[old] commit_plan -> PlanRevision -> executing
[old] verification -> generation evidence -> completion reminder
```

v0.24 inserts trigger validation and whole-round observation into this chain. Arrows show calls or fact flow; `[C]` is the main consumer and `[B]` is the boundary of this version:

```text
[old] agent_loop -> [~] Planning/Repair gate -> [old] ToolExecutor -> [old] PermissionGate -> handler
       |                    |                          |
       |                    +--> [C] request_replan -> [~] AgentState trigger / budget
       |                                               +--> [C] commit_plan -> PlanRevision.diff
       +--> [~] all tool results + role=tool history -> [C] observe_tool_round
                                                         +--> Runtime Notice -> blocked
[old] verification -> [~] current generation evidence -> completion
[+] /resume -> blocked_resume trigger -> Explore -> commit_plan
[B] Plan Trace remains a later version capability
```

The mapping: `state.py` stores sources, budgets, differences, and stagnation facts; `agent.py` is responsible for whole-round exclusive admission and when observation happens; `base.py` is responsible for the single-call gate; `__main__.py` only lets the CLI write blocked resume decisions. This separates three judgments: "the facts allow a revision", "the plan structure really changed", and "tool rounds keep making no progress".

You can use the commands below to see only the runtime skeleton; these entries show where fact storage, tool registration, and round observation happen:

```bash
rg -n "class ReplanTrigger|class LoopStagnationState|def request_replan|def observe_tool_round" src/mini_agent/state.py
rg -n "request_replan|observe_tool_round|planning_batch_errors" src/mini_agent/agent.py src/mini_agent/tools
```

## Key Flow

In the previous lesson, the flow entered Execute after the plan was submitted. v0.24 inserts an entry driven by real State facts into the execution or diagnosis phase:

```text
[old] executing / diagnosis_required
      -> execution, failure, or read-only investigation

[+] diagnosis_required + FailureEvent
      -> request_replan(failure, failure_id, reason) alone
      -> exploring -> read-only investigation -> commit_plan(parent + trigger)

[+] executing + successful read-only observation attempt
      -> request_replan(observation, attempt_id, reason) alone
      -> exploring -> read-only investigation -> commit_plan(parent + trigger)

[+] blocked
      -> CLI /resume <feedback>
      -> running / exploring -> commit_plan referencing the blocked_resume trigger

[+] every complete tool round
      -> run or reject all calls -> write to State in order -> feed back all role=tool
      -> observe durable progress and first-time valid facts
      -> Runtime Notice on the 2nd no-progress round; blocked on the 3rd
```

The "real source" in the diagram is the key: a failure trigger must point to the current active `FailureEvent`, and an observation trigger must point to a successful, approved read-only `ExecutionAttempt` after the current active revision was submitted. If the task takes the Direct Path, there is no parent yet when it enters Explore because of a failure or `/resume`; in that case the first `commit_plan` has a trigger but no parent. The initial plan of an ordinary task still has neither a trigger nor a parent.

## Problems in the Previous Version

If the model only changes the plan text, the Runtime cannot tell whether it is responding to a failure, adopting a new observation, or rewriting the approach for no reason. The old approach also loses its traceable parent relationship. Another problem is subtler: tool calls may "succeed" every time while reading the same result, repeating the same action, or submitting plans with no structural change, and the Agent loop keeps consuming rounds until the global limit.

v0.24 handles these two problems separately. `request_replan` is only responsible for turning one real fact into an active trigger; `commit_plan` then computes the difference from the parent and the new snapshot. Stagnation detection only looks at complete tool rounds and deterministic summaries, and does not let the model declare "I made progress" itself.

## Core Concepts: Triggers and Revision Differences

A trigger is the runtime record of "why changing the plan is allowed now". The model can only request `failure` or `observation`; user rejection, continued investigation, and blocked resume are written by the CLI as `user_feedback` or `blocked_resume`. Each record stores its source field, with the other source fields empty; one active trigger can be resolved by only one valid new revision.

The model's call entry is small, because source validation should not be hidden in natural language:

```python
request_replan(kind="observation", source_id="a-7",
               reason="The investigation shows the original step's dependency does not exist")
```

The Runtime then checks the current phase, the source attempt, the total budget, and whether there is already an active trigger. This call itself produces no attempt, generation, or verification evidence. A trigger during failure diagnosis keeps `active_failure_id`; only after the new revision is submitted does the repair phase go from `diagnosis_required` back to `idle`, which only means a new approach was formed, not that the old failure was fixed.

The difference of a new revision is computed from two validated snapshots, not replaced by the `reason` the model gives:

```text
retained: step_ids that still exist, plus dependencies_changed
added:    new step_ids
cancelled: step_ids that disappeared from the parent and were not replaced
replaced: parent step_ids referenced by the new steps' replaces
goal_changed / constraints_changed / success_criteria_changed
```

Only a real structural change appends a revision and consumes one `MAX_REPLAN_REVISIONS`. A submission with no structural change for the same trigger only increments `trigger_no_progress_commits`; after the second unchanged submission, the task enters `blocked`, and neither the trigger nor a revision is wrongly consumed. Dependency changes can appear in `retained`, and step content and step-level success criteria still follow the stable ID rules of the previous lesson.

## Core Concepts: Budgets and Blocked Resume

By default, `MAX_REPLAN_REVISIONS=3` is the budget of later revisions shared by the whole task. The third valid revision can still continue executing; when a fourth is requested, the Runtime enters `blocked`. `MAX_NO_PROGRESS_REPLANS=2` belongs only to the current trigger and stops repeated submissions; an invalid submission is not counted as a new revision.

blocked is a runtime terminal state; ordinary text and model tools cannot change it back to `running`. The user can enter:

```bash
PYTHONPATH=src python -m mini_agent "check and fix the project issues"
# During the interaction
/resume the external dependency is ready, please investigate the entry again
```

`/resume` saves a `resume_blocked` decision, the `terminal_reason` before resuming, and the active failure, then creates a trigger and returns to `running / exploring`. If the blocked state was left by `recover(ask/block)`, the Runtime keeps the successor generation, the repair budget, and the independent verification requirement, and moves the repair phase back to `diagnosis_required`; so after the new revision is submitted, it still has to be verified separately. If there was no plan at that time, the next `commit_plan` references the trigger and must not provide a parent; if there is a plan, it must reference the current parent. Tasks that are `failed`, have exhausted the replanning budget, or already have an active resume trigger must use `/new <task>`.

## Core Concepts: Deterministic Stagnation Detection

The unit of stagnation detection is the complete tool round. The Runtime first handles all calls, commits State facts in the model's order, shows the results, and writes each call's result into `history`; only after that does it call `observe_tool_round`. So when the 3rd round blocks, all `role=tool` results of the earlier rounds and the current round still exist.

It uses three kinds of signals:

1. The action fingerprint is the sequence of `(tool, canonical_arguments_hash)` joined in the model's order. A different command string or natural language argument gives a different fingerprint; the Runtime does not guess whether they mean the same thing.
2. The durable progress marker includes the plan structure and step statuses, the Planning/Repair phase, the active trigger source, user decisions, the set of changed files, `verification_required`, and the verification conclusion of the current generation. Attempt counts, automatic IDs, generation numbers, tool history length, and budget consumption do not count as progress.
3. Successful, approved read-only results and first successful possible actions each keep a bounded hash. Reading the same result or repeating an action does not earn "first time" credit again; state control tools and verification can reset the count only through a change in the durable marker.

`MAX_STAGNANT_ROUNDS` defaults to 3 and must be greater than 1. The second consecutive no-progress round sets one protected Runtime Notice, giving the current category and the legal actions that pass both gates; the third round records `repeated_action`, `no_new_observation`, `explore_without_commit`, or `execute_without_progress`, then enters `blocked`. This is not a FailureEvent, because the tools may not have failed. The execution limit for the same tool and argument fingerprint, `MAX_ATTEMPT_FINGERPRINTS`, defaults to 4 and must be at least `MAX_STAGNANT_ROUNDS + 1`, so that after one new investigation fact there are still three complete no-progress rounds left for the reminder and the stop.

## Implementation Breakdown

`AgentState` owns all cross-round facts and atomic transitions. `LoopStagnationState` only stores the epoch, counts, the last round fingerprint, at most 256 observation hashes and possible action hashes, and the warning and last reason. `begin_task`, `/new`, and `/reset` clear this task-level data; a change in the durable progress marker starts a new epoch.

`ToolExecutor` enforces the planning/repair gate before the handler and the `PermissionGate`. The agent loop additionally looks at the complete batch of calls, so when `request_replan` is mixed with `recover`, `commit_plan`, side effects, or verification, every call in the round returns a protocol result without running. Both layers reject illegal calls, so even calling the Executor directly cannot bypass the Explore or diagnosis boundary.

Each round, the context rebuilds a bounded state from `snapshot()`, showing only the active trigger's source and reason, the remaining replan budget, `trigger_no_progress_commits`, the stagnation count, a short fingerprint, and the legal next actions. Full tool output still belongs to the trimmable protocol history, and stagnation state keeps only hashes; after compaction, these key fields are still re-rendered from the State snapshot.

## Why This Design

Splitting "request replanning" and "submit a new plan" into two calls lets the Runtime first validate the evidence source, then validate the parent, steps, and difference. The model can explain why it changes the approach, but cannot use one sentence of reasoning to forge a failure or turn user feedback into a model fact. Keeping the failure trigger alongside the Repair Loop also means that after the new approach is formed, real changes and independent verification of the current generation are still required.

Stagnation detection uses hashes and structured state so that the stop behavior is testable and replayable and needs no extra LLM judgment of whether two results mean the same thing. The cost is that different display formats of the same content may be treated as different facts, and a hash set over 256 items no longer gives first-time credit; these boundaries keep the Runtime from expanding its responsibility by guessing.

## Design Boundaries

- This version does not implement Plan Trace; `PlanDifference`, triggers, and stagnation summaries first enter the public State, and the next version extends read-only replay.
- Replanning consumes no Repair cycle and opens no generation; actual changes, recovery, and verification still follow the Stage 6 rules.
- A failure-driven revision does not delete the FailureEvent, old verification history, or old revisions; a plan submission cannot replace independent verification either.
- `/resume` is the only blocked resume entry; the model cannot request `user_feedback` or `blocked_resume`, and ordinary text cannot resume `failed`.
- `MAX_ITERATIONS` is still the final global safeguard; the stagnation guard only handles complete tool rounds, and interim text without tool_calls keeps using the previous version's completion reminder.

## Version Features, Next Lesson, and Code Index

This version adds evidence-driven `request_replan`, four kinds of traceable triggers, bounded revision and no-progress budgets, a blocked resume entry, and a deterministic stagnation stop across Direct/Explore/Execute. Later version lessons discuss other read-only analysis capabilities; this lesson does not include those implementations.

Entries pinned to this lesson's code snapshot:

- [`state.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.24/src/mini_agent/state.py): triggers, budgets, differences, resume, and stagnation state.
- [`plan.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.24/src/mini_agent/tools/plan.py): the `request_replan` schema and handler.
- [`agent.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.24/src/mini_agent/agent.py): whole-round mixed admission and where rounds are observed.
- [`base.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.24/src/mini_agent/tools/base.py): the single-call Planning/Repair gate.
- [`__main__.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.24/src/mini_agent/__main__.py): the `/resume` user resume entry.

# Lesson 33: Handing off calls after a crash (v0.33)

Previous: [Writing down the key boundaries of tool calls](32-durable-tool-boundaries.md) · [Tutorial overview](README.md) · Next: [Lesson 34: Minimal controlled subagent delegation](34-minimal-delegation.md)

> Code snapshot: `v0.33` · Adjacent diff: `v0.32..v0.33` · Shell: Bash/zsh

> Requirements: Python 3.10+. This lesson handles `active + schema 3 + pending tool_boundary`; it makes no promise to recover external side effects automatically.

## Lesson Goals

The previous lesson let the disk know which boundary a tool call stopped at, but a pending call can still mean two completely different things: the program may not have entered the handler yet, or it may already have started writing a file, starting a shell, or writing part of the content to stdin.

The most dangerous thing to do after a crash is to treat "no result" as "not executed" and then do it again automatically. That could write a file twice, start a process twice, or send input twice. This lesson builds a conservative handoff flow. After this lesson, you should be able to explain:

- The difference between `not_executed` and `uncertain_side_effect`;
- Why the source session stays unchanged and a new session must be derived;
- Why uncertain calls cannot be replayed automatically;
- What each of `/resolve ... investigate|continue|block` does;
- Why, after recovery, the task must replan, reauthorize, and verify independently.

## Problems in the Previous Version: No Result Is Not the Same as Not Executed

v0.32 already records `handler_admitted`. But if the process crashes while the handler runs, the session may have only "admission committed", with no success or failure result. For `write_file`, `run_shell`, starting/controlling processes, and `write_process`, the outside world may already have changed; even if a file looks unchanged or an old PID seems gone, you cannot conclude from these observations that "it definitely did not run".

So v0.33 does not try to guess what happened in the past; instead, it writes the uncertainty down as task facts and hands them to the new CLI and the user to handle one by one. Only when it is known for certain that the handler was not admitted before the crash can a definite "not executed" result be generated.

## Prerequisites and Version Checkout

You need basic Python, the command line, and the `tool_boundary`, `handler_admitted`, and `effect_class` concepts from Lesson 32. Commands use Bash/zsh.

```bash
git checkout v0.32
git diff --stat v0.32..v0.33
git diff v0.32..v0.33 -- src/mini_agent/state.py src/mini_agent/session.py src/mini_agent/resume.py src/mini_agent/context.py src/mini_agent/prompt.py src/mini_agent/tools/base.py src/mini_agent/trace.py src/mini_agent/__main__.py
git checkout v0.33
```

## New and Changed Files

What this version adds is not a "retry button" but a flow of identification, branching, handoff, and re-verification.

| File | Change | Purpose |
|---|---|---|
| `src/mini_agent/state.py` | Adds State format 2, recovery, issues, and decisions | Stores uncertain facts and blocks a wrong completion finish |
| `src/mini_agent/resume.py` | Separates clean resume from crash recovery | Builds the recovery candidate, classifies calls, and derives a session |
| `src/mini_agent/session.py` | Adds the claim sidecar and derived commit | Keeps the source file and ensures one source is derived only once |
| `src/mini_agent/context.py`, `prompt.py` | Add the recovery summary and model rules | Explain issues and next actions without leaking sensitive arguments |
| `src/mini_agent/__main__.py`, `tools/base.py` | Add `/resolve` and the crash gate | User decisions are recorded only by the CLI; the investigation phase allows only side-effect-free observation |
| `src/mini_agent/trace.py` | Adds recovery causal checks | Checks, read-only, the recovery → issue → decision → trigger chain |

## Version Change Map

Legend: `[old]` already in v0.32, `[+]` new in v0.33, `[~]` changed in v0.33, `[C]` main consumer, `[B]` boundary of this lesson.

When v0.32 meets a half round, it can only stop here:

```text
[old] assistant tool_calls
  -> [old] pending tool_boundary
  -> [old] handler admission (may have happened)
  -> [B] only records the interruption; does not know whether a safe handoff is possible
```

v0.33 adds a recovery branch after the pending boundary that does not overwrite the source file:

```text
[old] active schema 3 + pending boundary
  -> [+] prepare_resume classifies pending calls
       |
       +-- handler_admitted=false
       |      -> [+] not_executed
       |      -> [+] interrupted_before_handler tool result
       |
       +-- handler_admitted=true
              -> [+] uncertain_state_or_result / uncertain_side_effect issue
  -> [+] keep the source session, claim once, and derive a new session
  -> [+] new generation, clear current verification
  -> [C] Structured State / Context show the pending issues
       |
       +-- [C] read-only investigation
       +-- [C] user continue / block
  -> [+] after all issues are settled, trigger a crash_recovery replan
  -> [C] reauthorization and independent verification

[B] no replay of old handlers, no treating ordinary user text as continue, no controlling processes with old PIDs
```

## Core Concepts and Data Structures

### 1. First separate "definitely did not enter the handler" from "unknown what happened"

Recovery classification uses only the admission facts and effect class already written in the durable boundary:

| Condition | Classification | Result in the new session |
|---|---|---|
| `handler_admitted=false` | `not_executed` | `interrupted_before_handler`, explicitly recorded as not executed |
| `handler_admitted=true` and `effect_class=none` | `uncertain_state_or_result` | Does not claim the result or State change is usable |
| `handler_admitted=true` and `effect_class=possible` | `uncertain_side_effect` | Does not claim success and does not replay |

An issue here is "an open fact that must be handled". For example, an admitted `write_file` with no result forms an uncertain side effect issue; an admitted `read_file` whose result was not committed also cannot have its content guessed back.

A call that did not enter the handler can safely get a synthesized tool result:

```json
{
  "status": "interrupted_before_handler",
  "message": "The call did not enter the handler before the crash and is explicitly recorded as not executed on recovery."
}
```

The result of an uncertain call is explicitly written as `status: "uncertain"`; it is not the old handler's success return value.

### 2. Recovery keeps the source session and derives a new branch

`--resume` first decides the session type: a complete `clean` safe point takes the safe resume of v0.31; only an active schema 3 pending boundary enters crash recovery. The preparation phase calls neither the LLM, the PermissionGate, nor any handler.

Recovery does not overwrite the incident scene. The source session stays read-only, and the new session stores the recovered State, Context, synthesized tool results, and recovery records. `source_session_id` and `source_integrity` are written into the recovery facts; a private claim sidecar records the `preparing` / `committed` stages, preventing the same source integrity from being derived twice.

If a change in the workspace manifest is found before recovery, or the session recorded old background processes or unfinished stdin writes, these facts are also included in the recovery handoff; they are clues to investigate, not proof that "it already exited" or "there were no side effects".

In code, the candidate and the formal derivation are still two actions:

```python
candidate = prepare_resume(store, source_session_id, workspace_root)
runtime = candidate.claim()
```

If writing the derived file fails partway, the next attempt continues with the same derived ID; if the claim is already `committed`, handling the same source again reports the existing derived branch instead of creating another set of events.

### 3. `/resolve` hands the risk judgment to the user

While recovery has unsettled issues, ordinary input, side-effect tools, verification, and plan submissions are all blocked by the gate. The CLI provides three explicit decisions:

```text
/resolve <issue_id> investigate <feedback>
/resolve <issue_id> continue <feedback>
/resolve <issue_id> block <feedback>
```

`investigate` only records the user's decision and then allows one restricted read-only investigation; the investigation can read files, list directories, search, or calculate, but cannot write files, run shell, control processes, or verify. `continue` is not "replay the old call" but the user accepting, after investigation, to keep handling the issue; it requires the current recovery generation to already have a successful, approved investigation attempt with `effect_class=none`. `block` keeps the task in the terminal blocked state the user decided.

The user's `continue` must be recorded by the CLI; the model cannot forge it with ordinary text. After all issues are set to continue, the task still cannot run straight along the old tool round; it enters a `crash_recovery` replan: first submit or review a new plan, then go through the PermissionGate and independent verification again.

### 4. Verification after recovery must start over

Recovery opens a new generation and clears the current `verification_evidence`; the old `verification_history`, FailureEvents, RecoveryActions, and plan history are kept for audit. This way Trace can answer "what happened before the crash", while the completion decision uses only new evidence after recovery.

The recovery summary shows the issue ID, tool, classification, admission status, public reason, and legal next steps, but never puts the original tool arguments, shell command text, or stdin body back into State, Trace, or prompts.

## Why This Design

"No result, so retry" looks simple but cannot tell a handler that had not started from a side effect that already happened. Especially for file writes, shell, processes, and stdin, doing it twice can be more dangerous than missing it once. Conservative classification adds an investigation and a user decision, but it never forges success and never quietly repeats an external action.

Deriving a session leaves three auditable objects: the source file, the claim, and the new branch, which costs more storage; the benefit is that incident evidence is not overwritten, and repeated recovery does not create a second set of uncertain events. The user's `continue` also does not resume the old call directly; it triggers a new plan and new verification, because the user accepting the risk does not mean the result of the old external action is known.

## Design Boundaries

This version supports: reading the pending boundary of an active schema 3 session; recording calls definitely not admitted as `not_executed`; recording admitted calls as the matching uncertain issue; keeping the source session unchanged; per-issue investigation and user decisions; replanning and verification after all issues are settled.

This version does not support: reconnecting old `Popen`, PIDs, pipes, or stdin threads; inferring "it definitely did not run" from unchanged files, a command timeout, or a vanished PID; automatic rollback or replay of side effects; inheriting the old PermissionGate's runtime approvals; using the claim sidecar as Trace input. When safety cannot be proven, the task stops in an explainable handoff state.

## Key Flow

```text
--resume <source_session_id>
  -> validate the session and the pending boundary
  -> observe the workspace (only as clues, not proof of causality)
  -> create issues by handler_admitted / effect_class
  -> derive a new session; the source file stays unchanged
  -> synthesize explicit results for unexecuted calls; synthesize uncertain results for uncertain calls
  -> show the issues and /resolve usage

/resolve issue-1 investigate read the related files
  -> read-only investigation round
  -> /resolve issue-1 continue after investigating, confirmed it can continue

all issues continue
  -> crash_recovery replan
  -> reauthorization
  -> independent verification

any issue block
  -> the task stays blocked; old calls are not resumed automatically
```

## Implementation Breakdown

[`src/mini_agent/resume.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.33/src/mini_agent/resume.py) separates safe points from crash recovery in `prepare_resume()` and rechecks the workspace observation before `claim()`; it builds recovery results from the admission state of the pending calls. [`src/mini_agent/session.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.33/src/mini_agent/session.py) handles the claim, the sidecar, the derived envelope, and the two-phase durable commit.

[`src/mini_agent/state.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.33/src/mini_agent/state.py) stores the recovery, issues, decisions, the new generation, and the `crash_recovery` trigger; `crash_recovery_gate()` narrows tool capability to read-only observation while issues are unsettled. [`src/mini_agent/tools/base.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.33/src/mini_agent/tools/base.py) runs this gate before planning, repair, and permission.

[`src/mini_agent/context.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.33/src/mini_agent/context.py) and [`src/mini_agent/prompt.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.33/src/mini_agent/prompt.py) inject a protected recovery summary for the model; [`src/mini_agent/__main__.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.33/src/mini_agent/__main__.py) is the only place that parses and records `/resolve`; [`src/mini_agent/trace.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.33/src/mini_agent/trace.py) validates, read-only, the recovery → issue → decision → trigger causal chain.

## Run and Observe

The command below uses Bash/zsh. This lesson's crash recovery branch is entered only when there is an active pending boundary:

```bash
PYTHONPATH=src python -m mini_agent --resume <source_session_id>
```

You should see the source session ID, the derived session ID, the call classifications, the workspace observation, and `/resolve` usage. `not_executed` calls automatically get an explicit `interrupted_before_handler` result; `uncertain_side_effect` blocks ordinary input and side-effect tools.

After `/resolve <issue_id> investigate <feedback>`, a read-only round can run; running `continue` directly before the investigation succeeds is refused. After all issues are settled, the next step should be a new plan referencing the `crash_recovery` trigger and independent verification, not continuing the old tool calls. The content of the source session file should stay unchanged.

## Version Features, Next Lesson, and Code Index

What this version adds is an explainable handoff after a crash: classifying incomplete calls, deriving a session, per-issue user decisions, a read-only investigation gate, a new generation, and re-verification. It is not infinitely reliable external transaction recovery, and it makes no promise to fix side effects of files, shell, processes, or stdin unattended.

Next lesson: [Lesson 34: Minimal controlled subagent delegation](34-minimal-delegation.md).

Core code index: [`state.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.33/src/mini_agent/state.py), [`session.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.33/src/mini_agent/session.py), [`resume.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.33/src/mini_agent/resume.py), [`__main__.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.33/src/mini_agent/__main__.py).

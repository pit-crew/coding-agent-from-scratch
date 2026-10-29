# Lesson 52: Keeping the Agent working after faults (v0.52)

Previous: [Repeated coding benchmark runs](51-coding-benchmark.md) · [Tutorial overview](README.md) · Next: v0.53 (regression comparison)

> Code snapshot: `v0.52` · Adjacent diff: `v0.51..v0.52` · Shell: Bash/zsh
>
> Source links are pinned to `v0.52`. That tag is created manually by the maintainer; before it exists, read the matching files in the current working tree.

## Lesson Goals

A file read that raises an exception, a denied tool permission, a background process that will not exit, and a disconnected MCP Server all interrupt the Agent's work. We need to judge two things separately: whether the runtime held its boundaries, and whether the Agent really completed the rest of the task. Refusing a dangerous operation only proves that the safety boundary is correct; it cannot replace task success.

This lesson freezes `reliability-boundaries@1.6`, which covers 18 kinds of faults in 50 offline boundary slots. From these, seven kinds are chosen to run the real Agent, with three planned runs each, for 21 live trials in total. After reading, you should be able to explain why the two kinds of results are counted separately, and trace from a raw report to the fault events and each invariant.

## Prerequisites and Version Checkout

You need Python 3.10+, a terminal, and Git. Lesson 51 repeated the same coding case from the same files; this version injects errors into the tool, permission, persistence, MCP, and subagent boundaries. After the maintainer creates the adjacent tags, you can view the changes with the commands below:

```bash
git checkout v0.51
git diff --stat v0.51..v0.52
git diff v0.51..v0.52 -- src/mini_agent/evaluation tests/fixtures/evaluation/reliability
git checkout v0.52
```

Source index for this lesson: [reliability_schema.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.52/src/mini_agent/evaluation/reliability_schema.py), [reliability.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.52/src/mini_agent/evaluation/reliability.py), [reliability_worker.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.52/src/mini_agent/evaluation/reliability_worker.py), [faults.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.52/src/mini_agent/evaluation/faults.py), [reliability_report.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.52/src/mini_agent/evaluation/reliability_report.py).

## Limits of the Previous Version

v0.51 shows whether one coding task passes independent acceptance and also keeps failed and unrun trials. But it has no way to answer lower-level questions: after a permission denial, was the handler run? After a durable commit failure, did the next model request happen? After an MCP disconnect, did the client send the same call again?

Fault evaluation must create one bounded, recorded fault at an existing safety boundary. If the PermissionGate were relaxed, the Plan bypassed, or cleanup skipped for the sake of grading, the result could not show whether the real runtime is reliable. So this version injects faults only into trial workspaces, fixture Servers, and subprocesses managed by the test runner, and does not change the safety rules of the production runtime.

## New and Changed Files

| Location | Change | Purpose |
|---|---|---|
| [reliability/suite.json](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.52/tests/fixtures/evaluation/reliability/suite.json) and 18 scenario directories | New | Freeze the tasks, initial files, response material, feedback policy, graders, and digests. |
| [evaluation/reliability_schema.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.52/src/mini_agent/evaluation/reliability_schema.py) | New | Defines suite, scenario, request, and trial result contracts separate from the coding cases. |
| [evaluation/faults.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.52/src/mini_agent/evaluation/faults.py) | New | Provides only named, bounded-count handler exceptions, commit failures, barriers, and child call timeouts. |
| [evaluation/reliability_worker.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.52/src/mini_agent/evaluation/reliability_worker.py) | New | Assembles live scenarios with the real `AgentRuntime.run()` and provides fixture boundary probes that do not call the model. |
| [evaluation/reliability.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.52/src/mini_agent/evaluation/reliability.py) and [reliability_report.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.52/src/mini_agent/evaluation/reliability_report.py) | New | Keep slots in frozen order, run phase workers, and rebuild reports read-only from raw trials. |
| [evaluation/evidence.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.52/src/mini_agent/evaluation/evidence.py), [user_actions.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.52/src/mini_agent/user_actions.py) | New | Check bounded evidence references; reuse the CLI's user-side recovery decision logic. |
| [evaluation/__main__.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.52/src/mini_agent/evaluation/__main__.py), [evaluation/report.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.52/src/mini_agent/evaluation/report.py) | Changed | Add reliability commands and make the old report explicitly skip the separate reliability result format. |

| [budget.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.52/src/mini_agent/budget.py), [runtime.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.52/src/mini_agent/runtime.py) | New/changed | Parent task requests and summaries share a durable budget; quota is kept for verification, plan progress, and the final reply. |
| [context.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.52/src/mini_agent/context.py), [state.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.52/src/mini_agent/state.py), [session.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.52/src/mini_agent/session.py) | Changed | Build a bounded request view, finish based on independent completion facts, and commit a unique reservation and settlement. |

## Version Change Map

Legend: `[old]` already in the previous version; `[+]` new in this version; `[~]` changed in this version; `[C]` main consumer; `[B]` boundary of this version.

The previous version first builds the workspace, runs the Agent, then lets the grader check the result. It can evaluate tasks but never creates runtime faults on purpose:

```text
v0.51 baseline:
[old] validate-suite
  → [old] fixed cases, workspaces, and permissions
  → [old] single Agent worker
  → [old] independent grader
  → [old] schema 2 trial + ordered slot ledger
  → [C] report-suite rebuilds the coding task summary
```

v0.52 adds fault events, invariants, and recovery results to the same kind of evidence chain. For crash recovery, it makes the initial worker really exit, then starts a new Python process to claim the derived session:

```text
v0.52 change:
[+] validate-reliability → freeze the suite and material digests
  → [+] build ordered slots by scenario and parameter variant
  → [+] fixture probe or real AgentRuntime worker
       ├─ [+] FaultController records the actual hit point
       ├─ [~] real ToolExecutor / PermissionGate / ProcessManager / MCP / Subagent
       └─ [B] crash scenarios: exit the initial process → new process prepare_resume().claim()
  → [+] invariant_status and grader_passed saved separately
  → [+] report-reliability validates the suite, slots, and evidence digests, then rebuilds the metrics

failure branches: [B] faults that did not trigger or incomplete evidence are listed separately; no request retries, no filling in slots.
```

## First, the Two Kinds of Grading

An "invariant" is a rule a behavior must always satisfy. For example, a denied file write must not enter the handler; a call that was admitted but whose result was lost must not be replayed on recovery. A scenario lists each rule as a separate ID, and the report gives `passed`, `failed`, or `incomplete` according to the evidence.

The task grader instead checks the files and behavior the Agent finally leaves behind. For example, whether it fixed the function after the read error, and whether it proved the fix with verification evidence of the current generation. The Agent saying "done", or a test passing in an old generation, cannot replace this acceptance.

A fixture calls the boundary components directly without running the Agent; it checks the injection point, the invariants, and cleanup, but leaves `grader_passed` as `null`. So the offline matrix can prove "the boundary probe found the expected facts", but cannot prove "the real Agent can recover from the fault and complete the task". The recovery success rate is computed only in the live cohort; the denominator excludes faults that did not trigger, incomplete evidence, inconsistent sources, and infrastructure errors; timeouts, permission denials, budget exhaustion, and recovery failures in the six recovery tasks still count in the denominator. The dedicated path denial scenario only checks that the handler did not run, the file is unchanged, and the parent task terminates safely, so it does not enter the recovery denominator.

The suite has 18 scenarios. The offline run also puts four kinds of MCP behavior on both stdio and explicit loopback HTTP; the durable commit failure is injected separately at admission, a single result, and the whole-round commit, and user recovery feedback also has two parameter variants. Every variant keeps its own trial and is not merged into one conclusion.

The seven kinds of live tasks cover tool handler exceptions, path denial, verification repair, process wait timeout, a crash after the handler, MCP disconnect, and subagent timeout. Each freezes the user task, visible tools, per-item permissions, budget, feedback source, and grader. The subagent timeout is injected before the child model's provider request; the result is marked `injected` and does not pose as a real child model call.

For a task to pass, the tests the evaluation uses must themselves be able to pass. All six recovery scenarios provide public unittests: the wrong initial code must fail, the known-good version must succeed, and the number of tests cannot be zero. The pre-check and the real run use the same check, so the Agent cannot fix the code and still fail because the test directory is missing.

The independent grader also checks numeric behavior in a separate process. For example, both `return value + value` and `return value * 2` are accepted; it judges output and does not restrict how the code is written. This process has time and output limits; see [reliability_grader.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.52/src/mini_agent/evaluation/reliability_grader.py) for the implementation. The local fixture of the process wait scenario keeps running until the Agent stops it explicitly, so a slow model reply cannot make the expected timeout disappear early.

The fault must happen at the stage the model understands. The crash task first tells the model that no crash has happened yet, and stops the process only after the first change is complete; the recovered session then asks for investigation and replanning. The subagent timeout also first provides a fixed and sufficient budget, so the budget does not block it before the model is even requested. If the target fault does not happen, the related boundary can only be marked as incomplete evidence; boundary failure cannot be inferred.

Some Chat API-compatible services require later requests to carry back the `reasoning_content` from a response. This is an optional protocol field the server uses to continue requests; the adapter keeps it within bounds, streaming responses concatenate it in order, and it is sent back as is with the assistant message. It is never treated as terminal text or completion evidence. See [openai_chat.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.52/src/mini_agent/providers/openai_chat.py) for the handling.

## Key Flow

A real fault cannot be proven by "a fault name written in the configuration". The runner appends an ordered fault event when the specified boundary is actually hit, and the event saves the target, count, and an evidence digest. Take the child model timeout as an example: the injection happens before the provider request is sent; if the model does not request `spawn_subagent`, the scenario is recorded as not triggered.

The request schema uses fixed string IDs to choose implemented drivers and graders; a manifest cannot import modules or run Python. Material paths must be inside the suite, with bounded file counts and sizes; all scenario files, supporting fixtures, and the suite itself take part in the digest check.

After the run, each trial keeps its own initial workspace, state/trace summaries, injection and user feedback events, recovery steps, logs, and diffs. `suite-run.json` lists all slots before starting; if a worker crashes, completed results remain, and the remaining slots stay unrun. The report reads the frozen material, the ledger, and the results, then checks identities and evidence SHA-256; it never calls the model or tools.

## Run and Observe

First run the full offline matrix. This command starts only local controlled fixtures and never calls a real API. All 50 slots should have results, and every fault should have an actual hit record; the task grader and live recovery rate show `null`, because there is no Agent task here:

```bash
PYTHONPATH=src python -m mini_agent.evaluation self-test-reliability --output /private/tmp/mini-agent-reliability-offline
```

Before running live, look at all the frozen tasks and permissions in the `validate-reliability` output. The reviewer should confirm that the denied paths, simulated feedback, public verification commands, and budgets are exactly the behaviors to be measured, then decide whether to start the 21 real trials. The output directory must be new, and failed requests are not resent automatically:

```bash
PYTHONPATH=src python -m mini_agent.evaluation validate-reliability tests/fixtures/evaluation/reliability/suite.json
PYTHONPATH=src python -m mini_agent.evaluation run-reliability tests/fixtures/evaluation/reliability/suite.json --live --repeats 3 --output docs/evaluation/baselines/v0.52/live-<run-id>
PYTHONPATH=src python -m mini_agent.evaluation report-reliability docs/evaluation/baselines/v0.52/live-<run-id>
```

In the report, first look at each scenario's `fault_triggered` and `invariant_status_counts` to confirm the actual fault and boundary evidence; then look at the grader, the Agent terminal state, cleanup, and the recovery rate. If the invariants pass but the grader fails, the system correctly blocked the risk but the Agent did not complete the task. If the fault did not trigger or the evidence is incomplete, this trial cannot prove the boundary is reliable, and it also cannot be quietly removed from the results.

### Finding Where the Budget Went

When the fault triggered and the file was fixed but verification still did not finish, you need to know how much repeated information each request round carried. A token is the unit a model uses to measure input and output length; a local estimate based on text length may differ from the server's actual count. The new version provides `request_diagnostics` in the trial's `phases` (run phase records); each request leaves only numbers and never copies the prompt or reasoning text.

First look at `message_groups`: it estimates protected instructions, structured task state, history messages, compaction summaries, and runtime reminders separately; then look at the separate `tool_schema_tokens_estimated`, the overhead of the tool descriptions sent to the model. The count of reasoning fields is a subset of the message total and must not be added twice. `usage_source` says whether the count is from the server, estimated, or not yet observed; `refusal_reason` says why the next request was blocked by the budget gate. The recovery phase also records the cumulative usage of earlier phases, so a crash continuation cannot be treated as a fresh budget.

These numbers are produced by [reliability_diagnostics.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.52/src/mini_agent/evaluation/reliability_diagnostics.py). The first evaluation and the crash continuation share the same set of evaluation instructions; recovery adds only necessary notes, so upper-level project instructions do not enter the context only during the continuation. The budget is still enforced by the frozen contract; whether it improves the real model's recovery needs independent live evidence.

### Keeping Budget for Verification and the Final Reply

Every time the Agent requests the model, it sends the context again, including earlier tool results and the reasoning fields the server requires to be carried back. So even after the file is fixed, the remaining budget may not fit the last reply round after verification. Limiting only the size of a single context cannot control the overhead the whole task accumulates over many rounds.

This version provides an optional parent task cumulative budget. It records the main model requests, history summaries, and requests after recovery in the same ledger. The CLI turns it off by default; only after `PARENT_TASK_TOKEN_BUDGET` is set in local configuration does a new task enable it. The fault evaluation enables a fixed limit explicitly, so the budget constraint also becomes part of the frozen evaluation contract.

The input reservation starts with a looser estimate: before the first two real usage observations, it uses twice the local estimate plus 256. After that, it takes the largest positive error from the last eight observations, that is, the part where "actual input minus estimated input" is greater than zero, and adds 10% and 256. This lets observed deviation affect the next request without using the model's own estimate to calibrate itself. The calculation is done by [budget.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.52/src/mini_agent/budget.py):

```python
error = max(max(0, actual - estimate) for estimate, actual in samples)
reserved_input = ((raw + error) * 110 + 99) // 100 + 256
```

The integer arithmetic means rounding up, so floating-point rounding never changes a borderline quota. Main execution output is at most 1024 tokens, summaries and finishing at most 512, still subject to the smaller model configuration limit. Unknown usage is charged at the whole input and output reservation; when real usage exceeds the reservation, it is recorded as is and later tools or completion are stopped. The estimate is still not a real tokenizer and cannot prove that any provider will never be exceeded.

With the budget on, the request view keeps only the last two complete tool rounds. A complete round includes the assistant's calls and each matching tool result; old results can be shortened first, or whole rounds omitted, but no call can be left without its result. Kept reasoning fields are carried back as is, and user messages, protected instructions, and the current task state are kept. The full history is unchanged, so later checks can still see the original evidence. A summary itself also costs tokens; the same model is called only when the estimated total cost is lower and there is quota; otherwise a local bounded view is used.

The runtime also reserves request quota for verification, unfinished plan steps, and the final reply. Only when verification of the current generation has passed, or all active plan steps are complete, and processes, child results, and crash issues are all finished, does it enter the finishing view. This view keeps the goal, constraints, and completion facts and sends no tool schema. The model must really return a final reply without tool calls, which then goes through the existing completion check; the runtime never completes the plan for it or forges verification.

Below is where the optional budget plugs into the same run flow. With the budget off, the original path is used; with it on, a commit failure or protected content that cannot fit blocks later requests:

```text
[old] ParentRuntimePolicy + AgentRuntime.run
  → [~] Context: current state + user constraints + two complete tool rounds
  → [+] TaskBudgetController: reserve input, output, and the necessary finish
  → [~] DurableToolBoundary: commit the reservation
  → [old] request the model with the frozen binding
  → [+] settle real usage, or charge an unknown call at the whole reservation
  → [~] commit the settlement → [old] tool authorization/execution or the existing completion check
[B] commit failure: stop; overrun: tools get rejections fed back one by one and are not admitted to handlers
[C] optional in the CLI; always on in suite 1.6 live
```

Saving and recovery must also remember the budget already spent. The optional ledger in State is committed atomically with the session; on recovery, if a request was already sent but not settled, it is charged once at that request's whole reservation, and the limit cannot be regained by restarting. Old sessions without a ledger keep the old behavior and are not charged retroactively.

The new report also shows three layers of facts: the final files are correct, the current generation has independent verification, and the model finished normally. The three can differ; for example, if the tests pass but the final reply fails because of the budget, it does not enter the numerator of strict recovery success. Replaying historical numbers only shows how the observed requests would be admitted under the new quota; it cannot predict the model's new replies or the recovery success rate.

## Why This Design

Recording boundaries and task success separately keeps one metric from hiding another fact: simply refusing a dangerous call can be safe yet still let the task fail; correct final files cannot prove that the process had no repeated side effects. Fixed, named injectors can rerun the same fault and limit test material to choosing behaviors already implemented in code.

The cost is that the results of offline component probes and live Agent tasks differ and must be read in separate cohorts; 21 live samples are also small and describe only the observations for these frozen tasks and the current model source. The workspace is an independent directory built by the Runner but has no operating-system-level sandbox. v0.52 computes no effective repetition metric and does no model version or capability ablation comparison.

## Implementation Breakdown

`ReliabilityScenario` stores the task the user can see and the frozen conditions; `ReliabilitySuite` checks IDs, versions, and material digests; `FaultController` allows only a bounded set of fault IDs and records a trigger only after the specified target is actually reached. `run_reliability()` first atomically writes the full ordered ledger, then copies the initial files and starts a worker slot by slot.

The live worker handles the task through `AgentRuntime.run()`, `ParentRuntimePolicy`, the real ToolExecutor, and the frozen model binding of the current configuration. It rebuilds the exact tool surface and PermissionGate for each scenario; process, MCP, and subagent fixtures are managed only by that trial. After crash recovery saves the original session, it makes the initial worker end with a controlled exit code; the Runner then starts a brand-new Python process, which calls `prepare_resume(...).claim()`, checks that the source session did not change, and rebuilds the scenario permissions.

`build_reliability_report()` reloads the frozen suite in the run directory, checks the ledger fingerprint and slot order, then validates each trial's scenario digest and evidence references. It forms the recovery success rate denominator only from live trials; slots that cannot be decided are still shown as missing or unrun and are never filled in by guessing.

## Version Features, Next Lesson, and Code Index

`reliability-boundaries@1.6` in v0.52 contains 18 fault scenarios, 50 offline boundary slots, 21 planned live trials, independent invariant and task grading, user feedback source records, and rebuildable reports. The budget candidate is connected to the production Runtime but does not change the default parent task budget, timeouts, or permission policy. For the current offline matrix results and live status, see the [baseline record](../evaluation/baselines/v0.52/README.md); for the scenarios and metrics, see the [evaluation document](../evaluation/reliability.md).

The next lesson compares code versions and capability ablations under fixed conditions. Source index: [reliability.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.52/src/mini_agent/evaluation/reliability.py), [reliability_worker.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.52/src/mini_agent/evaluation/reliability_worker.py), [session.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.52/src/mini_agent/session.py), [resume.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.52/src/mini_agent/resume.py), [delegation.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.52/src/mini_agent/delegation.py).

# Lesson 34: Letting the Agent ask a read-only helper to investigate

Previous: [Handing off calls after a crash](33-crash-recovery.md) · [Tutorial overview](README.md) · Next: [Shared parent/child run loop](35-shared-agent-runtime.md)

> Code snapshot: `v0.34` · Adjacent diff: `v0.33..v0.34` · Shell: Bash/zsh

This lesson belongs to Stage 10, "controlled subagent delegation". Code links are pinned to `v0.34`; reading and running this lesson do not require creating a Git tag.

## Lesson Goals

The Agent here is a program that can ask the model questions, call tools, and complete tasks. Up to the previous lesson, all investigation was done by the same Agent: it had to read files and find definitions, and also change and verify. The more investigation there is, the more crowded the main task's context becomes.

This lesson lets the main Agent temporarily ask a Subagent to do one small, clearly defined read-only investigation. The subagent has its own message history and state and can only view the workspace or calculate; it hands a structured report back to the main Agent. After reading, you should be able to explain:

- Why a subagent is "an independent read-only helper", not a second main Agent with the main task's permissions;
- How `delegate_task` describes the goal, scope, and allowed tools;
- Why parent and child each have their own Context, State, and permissions;
- Why the subagent's report can only be investigation material and cannot count directly as verification evidence for the main task.

## Problems in the Previous Version

v0.33 can already hand off uncertain tool calls safely after a crash, but the main Agent still has to do all read-only investigation itself. This causes two problems: investigation content fills the main Context, and work of different natures — reading files, changing files, running verification — easily gets mixed together.

This version splits out only "collecting material". The main Agent is still the only one who can change the workspace, request permissions, maintain the plan, run authoritative verification, and decide task completion; the subagent has none of these abilities.

## Prerequisites and Version Checkout

You need basic Python, JSON, function calls, and relative paths, and should read Lesson 33 first. The commands below use Bash/zsh; the first switches to the previous version, the second only views the diff, and the last enters this lesson's snapshot.

```bash
git checkout v0.33
git diff --stat v0.33..v0.34
git checkout v0.34
```

This lesson's offline regression uses a fake LLM and needs no real API key. Real model configuration should still go only in the local untracked `config_local.py`.

## New and Changed Files

First look at the scope with `git diff --stat v0.33..v0.34`, then focus on this learning thread: the parent side proposes a delegation, the child side runs in a restricted tool view, and the result comes back to the parent side.

| File | Purpose |
|---|---|
| [`src/mini_agent/delegation.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.34/src/mini_agent/delegation.py) | Holds the delegation contract, scope checks, budgets, result validation, and the subagent run entry. |
| [`src/mini_agent/tools/delegation.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.34/src/mini_agent/tools/delegation.py) | Provides the parent-side `delegate_task` tool. |
| [`src/mini_agent/tools/base.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.34/src/mini_agent/tools/base.py) | Uses an explicit capability marker to select the tools visible to subagents. |
| [`src/mini_agent/runtime.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.34/src/mini_agent/runtime.py) | Provides this version's shared call entry for parent and child runtimes. |
| [`src/mini_agent/prompt.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.34/src/mini_agent/prompt.py) | Tells the parent Agent and the subagent their respective identities and boundaries. |

## Version Change Map

Legend: `[old]` already in v0.33, `[+]` new in v0.34, `[~]` changed in v0.34, `[C]` main consumer, `[B]` boundary of this lesson.

In the previous version, investigation could only follow the main Agent's path:

```text
[old][C] parent Agent
      -> read_file / grep / calculate
      -> parent Context and parent State
      -> change, verify, decide completion
      [B] no independent investigation helper
```

This version inserts an independent child runtime after the parent Agent issues one `delegate_task`:

```text
[C] parent Agent
      -> [+] delegate_task (goal + workspace scope + tool allowlist)
      -> [+] ScopeGate / PermissionGate checks
      -> [+] SubagentRunner
           -> [+] independent child Context / child State
           -> [+] calculate / read_file / list_dir / grep
           -> [+] structured JSON report
      -> [C] the parent Context receives one role=tool result

[B] the subagent cannot write files, run shell, operate processes, change the parent plan, or delegate again
```

## Core Concepts and Data Structures

### 1. The delegation contract: first say clearly "what to investigate"

If you just hand another model a sentence like "take a look at the project for me", it may read too many files or give an answer that cannot be checked. So `delegate_task` is not an arbitrary prompt but a small contract: `goal` states the goal, `scope` limits the relative paths, `constraints` states restrictions, `expected_findings` states what kind of findings are wanted, and `requested_tools` states which read-only tools are needed.

The runtime additionally generates a `delegation_id`, a `subagent_id`, and a contract hash. The model cannot forge these identities, nor raise `depth` above 1. A parent round can contain only one exclusive `delegate_task`; if ordinary tools are mixed into the same round, the whole round is rejected and no child model is started.

### 2. Tool scope has two gates

The subagent's `scope` must be 1–8 relative paths inside the workspace. Absolute paths, `..`, `config_local.py`, and links that escape the workspace after realpath are all rejected. Every file read, directory listing, or search checks the actual path again, preventing the path from changing after the first check.

Whether a tool can be given to a subagent is not inferred from "it looks read-only" but decided by the explicit `delegation_capability` marker. v0.34 opens only `calculate`, `read_file`, `list_dir`, and `grep`; file writes, shell, processes, plans, recovery, and `delegate_task` are all outside the subagent's tool view.

### 3. The subagent has its own context and report

Context is the message history sent to the model, and State is the task fact ledger the program maintains. Parent and child each have their own copies, but the parent Context, parent State, parent permissions, and parent verification are not copied to the subagent. The subagent sees only its own identity rules, the delegation contract, selected parent-side facts, and its own tool results.

The subagent must finally return JSON of a fixed shape. The example below shows how "conclusions" and "evidence" are linked; it is not something you need to write by hand, but it helps you understand why the return value can be checked:

```json
{
  "summary": "Configuration is read from src/example.py",
  "findings": [
    {"id": "f1", "claim": "...", "evidence_ids": ["e1"], "confidence": "observed", "caveat": null}
  ],
  "evidence": [
    {"id": "e1", "kind": "tool_observation", "tool": "read_file", "path": "src/example.py", "observation_hash": "<sha256>"}
  ],
  "limitations": []
}
```

The runtime checks that evidence IDs are unique, that references exist, that paths are within scope, and that hashes are SHA-256, and confirms that each hash comes from a successful read-only observation in this run. A first malformed result gets exactly one correction prompt; if it is malformed again, or a tool is called again during the correction phase, it finishes with `failed/invalid_result`.

### 4. One parent call maps to one parent result

No matter how many read-only tool calls the subagent makes internally, the parent Context receives only one matching `role=tool` result. `role=tool` is the "tool result message" of the conversation protocol and must pair one-to-one with the tool call the parent model issued. The subagent's internal messages stay in its own Context and cannot be spliced directly into the parent history.

When the subagent times out, exhausts its budget, or its report fails, it also returns a structured failure result instead of leaving the parent protocol a message short. This result can tell the parent Agent "the investigation did not succeed", but it cannot be turned into verification evidence for the main task.

## Key Flow

The normal path:

```text
the parent model proposes delegate_task
  -> check the phase, permission, contract, and scope
  -> create an independent child Runtime
  -> the child model investigates with four read-only tools
  -> validate the JSON report
  -> the parent side writes the single role=tool result
  -> the parent model decides the next step
```

An important failure path:

```text
the parent round mixes in ordinary tools, or contains two delegate_task calls
  -> delegation_batch_gate
  -> every call gets a bounded rejection result
  -> no child model is started, and the parent task is not changed
```

## Run and Observe

After you have configured a local model, start the interactive CLI with Bash/zsh:

```bash
PYTHONPATH=src python -m mini_agent
```

When you observe one delegation, the parent side should show one `delegate_task` call and one matching JSON tool result; the subagent's internal messages such as `read_file` do not appear in the parent conversation. If the child model requests `write_file` or `run_shell`, it should get a rejection result, and the actual handler does not run. After the command-line first task is handled, the CLI still enters the interactive loop.

## Implementation Breakdown

`DelegationManager` freezes the contract and creates a `SubagentRunner`; `FilteredToolRegistryView` exposes only the four allowed tools; `ScopeGate` rechecks the path before every file operation. In v0.34, a single subagent defaults to at most 8 rounds, 8 LLM calls, 24 tool calls, about 32,000 estimated tokens, a 12 KiB result, and 120 seconds of wall-clock time. The model can only request a smaller budget, and token usage uses a conservative estimate marked `estimated`.

The parent side still records one `delegate_task` call under the existing tool boundary. The subagent result does not advance the parent Plan, generation, or `verification_evidence`; v0.34 also does not save the full child Context, resume a running subagent, run multiple subagents in parallel, or aggregate budgets across the parent task.

## Why This Design

This version chooses a synchronous, single-level, read-only subagent because it brings the benefits of independent investigation while keeping the parent side's protocol clear: "one call, one result". Explicit capabilities and independent permissions are more reliable than "the tool has no side effects, so it is safe", because some tools that do not write files can still be bound to parent task state or process resources.

The cost is that investigation must wait for the subagent to return, and the parent Agent must review the report. The subagent can only provide clues; it cannot prove for the parent Agent that tests passed, nor decide that the task is complete. Lifecycles, aggregate budgets, parallelism, and durable delivery change resource and recovery boundaries and are left to later lessons.

## Design Boundaries

- At most one subagent at a time per parent task, `depth=1`, waited for synchronously.
- The subagent can only use `calculate`, `read_file`, `list_dir`, and `grep`; it cannot write files, run shell, operate processes, or delegate again.
- A child result is untrusted investigation material for the parent and does not enter the parent `verification_evidence`.
- A child failure still has a structured parent tool result; the parent loop does not quietly rewrite a child failure as success.
- v0.34 provides no multiple providers, parallel scheduling, background cancellation, parent aggregate budgets, or cross-process recovery.

## Version Features, Next Lesson, and Code Index

This lesson completes minimal controlled delegation: the parent Agent can hand a clearly scoped read-only investigation to an independent subagent and receive a checkable structured result. The next lesson merges the parent and child control loops into the same `AgentRuntime.run()` while still keeping their separate state and permission boundaries.

Core source:

- [`src/mini_agent/delegation.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.34/src/mini_agent/delegation.py)
- [`src/mini_agent/runtime.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.34/src/mini_agent/runtime.py)
- [`src/mini_agent/tools/base.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.34/src/mini_agent/tools/base.py)
- [`src/mini_agent/tools/delegation.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.34/src/mini_agent/tools/delegation.py)

For the full design, see [`docs/plans/subagent-delegation-plan.md`](../plans/subagent-delegation-plan.md); for runtime constraints, see [`docs/operation/manual.md`](../operation/manual.md).

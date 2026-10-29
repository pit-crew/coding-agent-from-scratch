# Lesson 35: One run loop shared by the parent Agent and subagents

Previous: [Letting the Agent ask a read-only helper to investigate](34-minimal-delegation.md) · [Tutorial overview](README.md) · Next: [Multiple providers and unified protocol adaptation](36-multi-provider.md)

> Code snapshot: `v0.35` · Adjacent diff: `v0.34..v0.35` · Shell: Bash/zsh

The `v0.35` tag and this lesson's pinned source links are created by the repository maintainer; this lesson performs no tag operations.

## Lesson Goals

Lesson 34 already has a parent Agent and a read-only subagent, but each maintains its own loop of "request the model → run tools → send back results". Two loops can work in the short term, but in the long term they easily diverge in error handling and message order.

This lesson moves the control flow into a single `AgentRuntime.run()`. The Runtime can be understood as the main control loop that drives one task; a policy is a set of rules injected into it that says what a given runtime allows and when it pauses or finishes. After reading, you should be able to explain:

- Why duplicate loops cause protocol inconsistencies;
- Which fixed steps the Runtime is responsible for, and which parent/child differences the policy is responsible for;
- Why "sharing code" does not mean "sharing State, permissions, or history".

## Problems in the Previous Version

v0.34 has three similar but different loops: the parent Agent's legacy loop, a general Runtime shell, and `SubagentRunner`'s own loop. All of them can handle a tool call (the model's structured instruction requesting a tool), but nothing naturally guarantees that they follow the same rules.

For example, one loop might raise directly on a bad call while another returns `local-error-N`; one might write State before appending `role=tool`, and another in the opposite order. `role=tool` is the tool result message in the conversation history; once the order is wrong, both the next model request and a resumed session may see an incomplete half round.

## Prerequisites and Version Checkout

You need Lesson 34, basic Python, and JSON. Commands use Bash/zsh; switch to the previous version to view the diff, then switch back to this lesson's snapshot:

```bash
git checkout v0.34
git diff --stat v0.34..v0.35
git diff v0.34..v0.35 -- src/mini_agent/runtime.py src/mini_agent/agent.py src/mini_agent/delegation.py
git checkout v0.35
```

## New and Changed Files

The focus of this version is not how many files were added but merging two loops into one control entry.

| File | Purpose |
|---|---|
| [`src/mini_agent/runtime.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.35/src/mini_agent/runtime.py) | Defines the single `AgentRuntime.run()`, the message order, and the tool round commit flow. |
| [`src/mini_agent/agent.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.35/src/mini_agent/agent.py) | Keeps the parent-side entry, only responsible for assembling the parent Runtime. |
| [`src/mini_agent/delegation.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.35/src/mini_agent/delegation.py) | Assembles an isolated child Runtime and keeps the contract and result validation from Lesson 34. |
| [`src/mini_agent/context.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.35/src/mini_agent/context.py) | Provides a single entry for appending assistant messages and tool results. |

## Version Change Map

Legend: `[old]` already in v0.34, `[+]` new in v0.35, `[~]` changed in v0.35, `[C]` main consumer, `[B]` boundary of this lesson.

The three loops of v0.34 each finish on their own:

```text
[C] agent_loop
      -> [old] parent legacy loop
           -> parent LLM / parent tools / parent State / session boundary

[C] AgentRuntime
      -> [old] simplified general loop

[C] SubagentRunner.run()
      -> [old] child budget / child tools / report correction loop
```

v0.35 keeps two Runtime instances for parent and child but has both enter the same control flow:

```text
[C] agent_loop ───────────────┐
                              ├─> [+] AgentRuntime.run()
[C] SubagentRunner.run() ────┘       -> prepare messages, request the model
                                      -> normalize tool_calls
                                      -> append the assistant message
                                      -> the policy checks and runs tools
                                      -> append tool results in model order
                                      -> the policy decides to continue or finish

[~] ParentRuntimePolicy: plans, permissions, processes, session, completion decision
[~] SubagentRuntimePolicy: budget, scope, report contract
[B] no shared State, Context, PermissionGate, or verification
```

## Core Concepts and Data Structures

### 1. The Runtime is a fixed conveyor belt; the policy is the rule inspector

The Runtime is responsible for the steps both parent and child must follow: prepare messages, request the model once, normalize the response, run tools, send back results, and decide whether to enter the next round. It should not know "is this Anthropic or OpenAI", and it should not stuff the parent task's plan into the subagent.

The policy is responsible for runtime differences: the parent policy knows plans, processes, persistence, and completion reminders; the child policy knows the read-only tools, scope, budget, and final report format. It can return "continue", "finish", or "reject this call", but it cannot request the model itself, enter a handler, or write another loop.

The smallest policy results can be understood intuitively as:

```python
RuntimeDecision("continue", notice="Call a tool that advances the task")
RuntimeDecision("finish", content="Done", stop_reason="text")
ToolRoundPlan(serial=True, rejection_by_index={})
```

These objects describe control decisions; they are not new State or session schemas.

### 2. Every tool round closes in the same order

When the model returns tool calls, the Runtime first saves the normalized assistant message, then prepares one and only one `role=tool` result for each call. Only after all results are committed is the next model request allowed:

```text
prepare messages
  -> model response
  -> normalize tool_calls
  -> assistant(tool_calls)
  -> tool result[0], tool result[1], ...
  -> the policy decides to continue or finish
  -> next model request / finish
```

The order in which handlers complete may differ from the model's order, but the order in which messages and State are committed cannot change. With the durable boundary on, `handler_admitted` must also be committed before entering the handler; if any key commit fails, the Runtime stops later calls and the next model request.

### 3. Bad calls must also have results

`NormalizedToolRound` turns the model response into a uniform tuple of calls. A missing, blank, or duplicate call ID gets a `local-error-N` that cannot collide with the model's original IDs. An invalid call type, function name, or argument does not enter the handler, but it is still kept in the normalized assistant message and gets a matching error `role=tool` result.

The parent policy can let other legal calls in the same round continue; the child policy keeps the conservative rule from Lesson 34 and rejects the whole round as soon as a malformed call appears in it. The two differ, but the same Runtime guarantees for both that "every call eventually has a result".

### 4. A shared loop, not shared task data

Parent and child each have their own Context, State, tool executor, PermissionGate, and policy. The parent side provides terminal output and the session boundary; the child side uses silent output and does not connect to the parent session boundary. What is shared is immutable control code, not mutable task facts.

So the subagent still cannot change the parent plan, parent generation, parent permissions, or parent verification. Its result is also only investigation material for the parent Agent.

## Key Flow

Parent rounds and child rounds follow the same message skeleton:

```text
assistant(tool_calls=[A, B])
  -> run A and B (B may finish first)
  -> commit State and role=tool for A, then B
  -> the next model request sees the complete assistant + tool(A) + tool(B)
```

When the subagent outputs an invalid report, the child policy takes its own boundary:

```text
invalid report
  -> one protected format correction prompt
  -> valid JSON: finish
      or invalid again / calls a tool again: fill in results, then failed/invalid_result
```

## Run and Observe

After you have configured a local model, start the CLI with Bash/zsh:

```bash
PYTHONPATH=src python -m mini_agent
```

The parent side still shows tool progress, and the child side stays silent; after one parent tool round ends, the next model request happens only after all `role=tool` results are committed. After the command-line first task is handled, the CLI still enters the interactive loop. If you turn on `/save`, observe that the parent session still finishes with `handler_admitted → single call result → complete_round`, which shows that the control entry changed but the protocol boundary was not bypassed.

## Implementation Breakdown

[`agent_loop()`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.35/src/mini_agent/agent.py) and [`SubagentRunner.run()`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.35/src/mini_agent/delegation.py) are now mainly responsible for assembling dependencies and converting results, and no longer own their own `while` loops. `AgentRuntime.run()` exclusively owns the model call count, message appends, tool rounds, ordered commits, and the round limit.

The parent policy keeps carrying the plans, repairs, processes, session, and completion reminders from before Lesson 34; the child policy keeps carrying the fixed budget, scope observation, hashes, and the Result Contract. LLM exceptions are not swallowed at the top of the parent Runtime; the child Runner converts timeouts and other failures at its own result boundary, and the parent task does not inherit child state.

## Why This Design

Concentrating the protocol invariants in one loop means "one call maps to one result", "the model can be requested only after all results of a round are collected", and "bad calls must also close" need to be maintained in only one place. Policies can still express parent/child differences without letting the read-only subagent touch parent plans and sessions.

The cost is that the Runtime must provide clear policy hooks, and the parent side's completion reminder and durable commits can no longer depend on local variables of the legacy loop; with parallel execution, completed results must also be kept and committed in model order. This version chooses a small `Protocol` to keep the control plane readable and auditable.

## Design Boundaries

- Parent and child share `AgentRuntime.run()` but share no State, Context, permissions, process manager, session, or verification evidence.
- A policy can only propose decisions and rejection plans; it cannot request the model, run handlers, append tool results, or write another loop.
- The subagent is still synchronous, single-level, depth=1, with only four read-only tools; child results do not automatically advance the parent plan or verification.
- v0.35 only consolidates runtime control; it does not add multiple providers, lifecycle cancellation, aggregate budgets, parallel subagents, or cross-process delegation recovery.

## Version Features, Next Lesson, and Code Index

This lesson completes the single parent/child run loop: both the parent entry and the child entry go into `AgentRuntime.run()`, and the unified `NormalizedToolRound` guarantees that bad calls also get paired results, while the safety boundaries of parent and child are kept separate.

The next lesson is [Multiple providers and unified protocol adaptation](36-multi-provider.md): it moves "which model service to use" and "how to translate message formats" into a binding and adapter layer outside the Runtime.

Core source:

- [`src/mini_agent/runtime.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.35/src/mini_agent/runtime.py)
- [`src/mini_agent/agent.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.35/src/mini_agent/agent.py)
- [`src/mini_agent/delegation.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.35/src/mini_agent/delegation.py)
- [`src/mini_agent/context.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.35/src/mini_agent/context.py)

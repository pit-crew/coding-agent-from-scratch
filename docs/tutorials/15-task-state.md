# Lesson 15: Saving the task plan as reliable state (Todo / Task State, v0.15)

Previous: [Project instructions](14-project-instructions.md) · [Tutorial overview](README.md) · Next: [Plan-driven execution](16-plan-driven-execution.md)

> Code snapshot: `v0.15` · Adjacent diff: `v0.14..v0.15` · Shell: Bash/zsh

> Requirements: Python 3.10+. The runtime uses only the standard library.

## Problems in the Previous Version

An Agent (a model program that can call tools to complete tasks) has to remember two different kinds of things at the same time: what it plans to do, and what it has actually done. In v0.14 only the message history can carry this information. After the history is trimmed or compacted, the plan may disappear; if tool results are also treated as the plan, the model's intent and the execution facts get mixed up.

v0.15 only solves "where the plan is stored and how it is shown to the model reliably". It does not generate plans for the model, and it does not decide automatically that a task failed, or block the final reply, because a Todo is unfinished.

## Lesson Goals

This lesson separates the two concepts: the Todo (task list) records the model's task intent, and tool records hold the actual execution results. After reading it, you should be able to:

- Explain why each Todo update submits the full list instead of adding or deleting items one by one;
- Explain why the old list is kept when one item is invalid;
- Explain why different run instances do not overwrite each other's Todo;
- Understand how the Todo reappears in the current state view in every round's request.

The main thread of this lesson: **a Todo is a validated plan, not execution evidence and not an automatic planner.**

## Prerequisites and Version Checkout

Read Lesson 14 first: know that the `ContextManager` prepares messages for every round's request, and that the protected system prompt is not lost along with ordinary history. Run the commands below in Bash/zsh; they switch to the previous version, show the real diff, and then return to this lesson's snapshot:

```bash
git checkout v0.14
git diff --stat v0.14..v0.15
git diff v0.14..v0.15 -- src/mini_agent/state.py src/mini_agent/tools/todo.py src/mini_agent/tools/__init__.py src/mini_agent/context.py src/mini_agent/agent.py src/mini_agent/__main__.py
git checkout v0.15
```

`git diff --stat` first tells you roughly how much this version changed; the second `git diff` expands only this lesson's main files. The final `git checkout v0.15` makes later reading and running match this lesson's snapshot.

## New and Changed Files

First confirm the scope with the diff above, then map each change to "problem—location":

| File | Change in this version | Problem solved |
|---|---|---|
| `src/mini_agent/state.py` | Adds `TodoItem`, `todos`, `update_todos()`, and snapshot fields | Stores, validates, and safely reads plan intent |
| `src/mini_agent/tools/todo.py` | Adds the state-bound `update_todo` tool | Lets the model submit the full Todo list |
| `src/mini_agent/tools/__init__.py` | Adds `create_registry(state)` | Gives each run instance its own tools |
| `src/mini_agent/context.py` | Renders the Todo as Structured State every round | The latest plan stays visible after trimming or compaction |
| `src/mini_agent/agent.py`, `src/mini_agent/__main__.py` | Pass the current registry and reuse the same state | Keep the CLI, executor, and LLM on the same instance |

## Version Change Map

First look at the real entry and finish of v0.14, then at where v0.15 inserts the Todo. Legend: `[old]` already in v0.14, `[+]` new in v0.15, `[~]` changed in v0.15, `[C]` main consumer, `[B]` boundary of this version.

v0.14 baseline diagram:

```text
[old] CLI main()
  -> [old] AgentState + history + ContextManager
  -> [old] global registry -> ToolExecutor
  -> [old] agent_loop -> call_llm
       -> tool handler -> state.record_tool()
       -> role=tool result fed back to history -> next LLM round
```

This baseline shows that the previous version already had independent execution state and tool result feedback, but no field to store a Todo plan, and no Todo tool bound to each run instance.

v0.15 change diagram:

```text
[old] CLI main()
  -> [~] AgentState + history + ContextManager
  -> [+] create_registry(state) -> [~] ToolExecutor
  -> [old] agent_loop -> [~] call_llm(..., tool_registry=run_registry)
       -> [+] update_todo(full list)
            -> [C] AgentState.update_todos()
                 ├─ valid: atomically replace todos, update current_goal
                 └─ invalid: return a tool error, old state unchanged
       -> [~] prepare_messages()
            -> snapshot() -> [C] Structured State (current request view)

[B] No automatic planning, no Todo persistence, no automatic completion decision from Todo
```

The key is not "one more list", but that the same `AgentState` instance is used by the Todo tool, the tool executor, and the context manager. So the plan the model submits and the plan the next round's request sees come from the same state.

## Core Concepts and Data Structures

### 1. First tell plans from facts

If the model says "about to change the file", that sentence does not prove the file was changed. v0.15 lets `update_todo` only submit a plan; file changes, shell execution, and errors are still recorded by ordinary tool results into `tool_history`, `files_changed`, and `errors`. `record_tool()` deliberately skips the Todo:

```python
if name == "update_todo":
    return
```

The purpose of this check is to keep the two records separate: after a Todo call, the execution log does not gain a false "already done" fact. The next lesson adds independent verification evidence on top of this boundary.

### 2. One atomic update with the full list

Calling `add_todo` and `remove_todo` item by item makes intermediate states hard to validate and can easily leave duplicate items on retry. So v0.15 requires every `update_todo` to submit the full array. The runtime first checks the whole array and only then replaces the old list:

```python
if len(todos) > 50:
    raise ValueError("At most 50 Todos are allowed")

parsed = []
for item in todos:
    content = item.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Todo content must be a non-empty string")
    status = item.get("status", "pending")
    if status not in ("pending", "in_progress", "completed"):
        raise ValueError("Invalid Todo status")
    parsed.append(TodoItem(content.strip(), status))

with self._lock:
    self.todos = parsed
```

The first half of the code only builds `parsed` and does not touch the old state; the assignment inside the lock at the end is the replacement point. The valid statuses are `pending`, `in_progress`, and `completed`, and at most one Todo can be `in_progress`; each item is at most 240 characters, and the list has at most 50 items. When any item is invalid, the exception is raised before the replacement, the tool layer turns it into a tool error that can be fed back, and the old list stays unchanged.

### 3. Binding tools to the current run instance

If the Todo tool used global mutable state, two Agent run instances could overwrite each other's plans. v0.15 makes `make_update_todo_tool(state)` capture one explicit `AgentState`; the CLI creates the registry for the current run instance with `create_registry(state)` and hands the same registry to the executor and the LLM:

```python
state = AgentState()
run_registry = create_registry(state)
context = ContextManager(state, history)
tool_executor = ToolExecutor(run_registry, on_result=state.record_tool)
```

The key in this assembly code is that the same `state` runs through all three places. So two run instances each have their own Todo. `snapshot()` copies the list inside the lock and returns an independent dictionary, so readers never get the internal object a tool is changing.

### 4. Rebuilding the current request view every round

Structured State is a system message generated at runtime from a state snapshot; it is not an old conversation appended to `history`. Every round, `_render_state()` produces a view like this:

```text
[Structured State]
Task: Fix the regression
Current goal: Change the implementation
Todos: [pending] Locate the failing test; [in_progress] Change the implementation
Files changed: (none)
Status: running
```

The purpose of this output is to show "where the current values come from": even if the ordinary history has been trimmed or compacted, the model should still see the latest Todo. The `Todos` in the output come from the `snapshot()` just taken, so after a successful update the next round sees the new list, and an invalid update leaves no half plan.

## Why This Design

Keeping the plan only in the message history makes it easy to lose during trimming or compaction; keeping it in independent state and re-rendering it every round preserves both its structure and its latest value. Full replacement is easier to validate than an incremental API and does not create duplicate items on retry; the cost is that every update must submit the full list.

Binding tools to a run instance instead of using a global mutable handler isolates the state of different Agents; the cost is that the registry must be passed explicitly. `update_todo` only changes memory, so it is allowed by default; tools with side effects such as file writes and shell are still controlled by the permission gate.

## Design Boundaries

- A valid list is replaced atomically and shown in the next round's request.
- An invalid type, field, length, or more than one `in_progress` returns an error, and the old state stays unchanged.
- The state lock protects updates and snapshot reads; this version does not support cross-process sharing or disk persistence.
- Every tool call must still get its matching `role=tool` result fed back.
- This version does not generate, reorder, or verify Todos automatically, and does not block the final text because a Todo is unfinished.

## Key Flow

The flow below separates "submitting a plan" from "running tools". After a successful update, the Structured State in the next round's request carries the new list; an invalid update only produces a tool error, and the old list remains.

```text
main()
  -> AgentState()
  -> create_registry(state)
  -> ToolExecutor(registry, on_result=state.record_tool)
  -> agent_loop
       -> prepare_messages(): snapshot -> Structured State
       -> LLM calls update_todo(full array)
          ├─ success: replace the list, return an update summary
          └─ failure: return a tool error, old list unchanged
       -> assistant + matching role=tool result fed back to history
       -> next round re-renders Structured State
```

## Implementation Breakdown

`AgentState.update_todos()` is responsible for validation and atomic replacement; `make_update_todo_tool()` turns `TypeError`/`ValueError` into a tool result the model can read; `create_registry(state)` registers the tools bound to the current state; `ContextManager.prepare_messages()` reads the snapshot every round. The executor owns the tool exception boundary, and the agent loop feeds back all tool results in their original order; top-level LLM or CLI exceptions are still not swallowed by the core loop.

## Run and Observe (If Needed)

After you configure a local LLM, run a multi-step command-line first task in Bash/zsh:

```bash
PYTHONPATH=src python -m mini_agent "implement a task with several steps and maintain a Todo"
```

The "command-line first task" is the first task argument passed to the CLI; after it is handled, the program still enters the interactive loop. Observe whether the model calls `update_todo` to submit the full array, and whether later actions keep following the latest list. `[Structured State]` is an internal request view sent to the model; by default the CLI does not print it to the terminal. Later tasks keep using the same state and history until the model submits a full list again.

## Version Features, Next Lesson, and Code Index

v0.15 provides an instance-isolated, strictly validated, atomically replaced, and rebuildable task list. It does no automatic planning, no persistence, and does not block the final reply because a Todo is unfinished. The next lesson adds verification evidence on top of this and lets the model decide from observations or verification failures whether to reorder the Todo.

- [State and snapshot](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.15/src/mini_agent/state.py)
- [Todo tool](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.15/src/mini_agent/tools/todo.py)
- [Tool registry](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.15/src/mini_agent/tools/__init__.py)
- [Context rendering](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.15/src/mini_agent/context.py)
- [Agent loop](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.15/src/mini_agent/agent.py)
- [CLI entry](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.15/src/mini_agent/__main__.py)

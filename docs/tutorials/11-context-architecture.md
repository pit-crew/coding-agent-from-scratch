# Lesson 11: Context architecture

> Version v0.11 | [Previous lesson](10-shell-execution.md) | [Back to the tutorial overview](README.md)

> Code snapshot: `v0.11` · Adjacent diff: `v0.10..v0.11` · Shell: Bash/zsh
>
> Requirements: Python 3.10+. The `pyproject.toml` at this tag still says 3.9, but the source already uses 3.10 syntax.

## Lesson Goals

When a conversation gets long, the agent cannot keep sending everything to the model. But task progress, which files were changed, and which errors happened must not be lost along with old messages.

This lesson introduces `AgentState` and `ContextManager`. The first records execution facts; the second prepares the context sent to the LLM. With the two separated, later versions can trim messages without losing task state.

This version is a **pure refactoring**: external behavior is exactly the same as v0.10. It does not trim, compact, or estimate tokens; it only puts the responsibility boundaries in place first. The budget and trimming of v0.12 and the context compaction of v0.13 are both implemented inside this boundary.

## Prerequisites

- Read the previous lesson
- `git checkout v0.11` to switch to this version's code (or look directly at `src/mini_agent/state.py` and `src/mini_agent/context.py`)

## What Was Added or Changed

```bash
git diff --stat v0.10..v0.11
```

| File | Change |
|------|------|
| `src/mini_agent/state.py` | **New**: `AgentState` dataclass + `record_tool` execution record interface |
| `src/mini_agent/context.py` | **New**: `ContextManager` (single `prepare_messages()` entry) |
| `src/mini_agent/agent.py` | `agent_loop` now takes `context_manager` + `tool_executor` and calls the LLM through `prepare_messages()` |
| `src/mini_agent/tools/base.py` | `ToolExecutor` adds an `on_result` callback |
| `src/mini_agent/__main__.py` | Assembles AgentState + ContextManager and injects them into the loop |
| `tests/test_state.py` | **New**: State unit tests (10) |
| `tests/test_context.py` | **New**: ContextManager unit tests (5) |
| `tests/test_executor.py` | **New**: Executor callback unit tests (14) |

## Core Concepts

### 1. Agent State ≠ LLM Context

In v0.10 and earlier, all of the agent's "memory" was in the `messages` list: the task, the conversation history, and tool results were mixed together. The longer the messages, the more likely they will need trimming later; but execution state must not disappear with them.

This is what "context is consumable, state is not" means: the LLM Context (model context) can shrink, but AgentState (execution state) must be kept independently.

```
messages (LLM context)          AgentState (execution state)
├── system prompt               ├── task          current task
├── user task                   ├── current_goal  current goal
├── assistant / tool pairs      ├── tool_history  tool execution records
│   (longer = costlier,         ├── files_changed which files were changed
│    trimmed sooner or later)   ├── errors        which errors happened
└── ...                         └── status        running/done/failed
```

- **messages** may later be trimmed, truncated, or summarized (the topics of v0.12/v0.13), so information is lost.
- **AgentState** exists independently and is not trimmed or compacted. After the context shrinks, it still keeps the execution facts.

v0.09 already did something similar: the PermissionGate's always state lives outside messages, so deleting messages does not affect it.

### 2. AgentState: driven by execution results

```python
@dataclass
class AgentState:
    task: str = ""
    current_goal: str = ""
    tool_history: list[dict] = field(default_factory=list)  # {tool, args, ok, brief}
    files_changed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    status: str = "running"  # running / done / failed

    def record_tool(self, name, args, ok, brief): ...
```

Tools can run concurrently, so State records must come from real results and must be safe to update from several threads. The key design:

- **Record facts, not paraphrases**: `record_tool` records the tool, arguments, success or failure, and a result brief from the real execution result callback. `files_changed` and `errors` are derived from these records. The v0.13 summary may change through compaction, but State stays accurate.
- **Thread safety**: since v0.06, several tool_calls in the same round may run concurrently. Callbacks come from thread pool worker threads, so updates use a `Lock`, and reads get an independent copy through `snapshot()`.
- **Not in messages**: State is held by the ContextManager, and this version does not render it into the context; Structured State is injected only in v0.13.

### 3. ContextManager: the single entry before LLM calls

```python
class ContextManager:
    def __init__(self, state: AgentState, history: list[dict]): ...

    def prepare_messages(self) -> list[dict]:
        """Single entry before LLM calls. This version returns the full messages as is (sets the boundary, no trimming)."""
        return self.history
```

In this version, `prepare_messages()` just returns the history unchanged and seems to "do nothing". It becomes the single entry first, so later strategies have a fixed place to plug in:

```
agent_loop ──> cm.prepare_messages() ──> call_llm
                     ↑
        v0.12 adds budget checks + trimming here
        v0.13 adds compaction + State injection here
```

All LLM requests are built here. When new context strategies are added later, `agent_loop` does not need to change.

### 4. Executor result callback (D5)

```python
class ToolExecutor:
    def __init__(self, registry, gate=None, on_result=None): ...
```

After a tool runs, how does the result get into State? This version uses an **Executor callback** instead of having the loop do the bookkeeping:

```python
# Assembly in __main__.py
state = AgentState()
context = ContextManager(state, history)
tool_executor = ToolExecutor(registry, on_result=state.record_tool)
```

If `agent_loop` updated State along the way, every change to the loop would need to remember to sync two pieces of data, and paths would easily be missed later. The callback concentrates "recording state" in the Executor: the three paths — permission denied, handler exception, and success — all pass through `_notify_result`, and the brief is truncated to 200 characters.

If the callback itself raises an exception, it only prints a log and never changes the tool execution result. It only observes results and does not take part in execution.

### 5. Change to the agent_loop signature

```python
# v0.10
def agent_loop(messages): ...

# v0.11
def agent_loop(context_manager, tool_executor): ...
```

The loop only appends assistant and tool messages to `context_manager.history` and does not serialize AgentState into messages.

This keeps the existing protocol invariant: all tool calls of a round get their matching `role=tool` results before the next round. The change in v0.11 makes the separate responsibilities of message preparation and execution state explicit; it does not fix a "half state" defect from v0.10.

## Why This Design

### Why does this version not "do" anything?

The first problem in context management is usually not an algorithm but mixed responsibilities: trimming scattered across the loop, state and messages affecting each other, and summary timing that is hard to control.

v0.11 first makes the rules clear: only the ContextManager prepares messages, and AgentState is dedicated to state. Because external behavior is unchanged, regression verification is direct: all tests green plus a typical task run.

### Why is the State update in the Executor and not the loop?

See D5 above. One more point: `record_tool` records a path only when `ok=True` and the tool is `write_file`/`edit_file`; failed calls do not count as "changed files". Rules like this live inside State, and callers only provide raw facts.

### Why does snapshot() return a deep copy?

When tools run concurrently, a list a reader gets may be being appended to by a worker thread. `snapshot()` does a deepcopy inside the lock, so the caller gets a consistent, independent view.

## Usage Guide

### Commands available in this version

```bash
# Run the full test suite (61 tests)
PYTHONPATH=src python -m pytest tests/ -q

# Run only the new tests
PYTHONPATH=src python -m pytest tests/test_state.py tests/test_context.py tests/test_executor.py -q

# Verify AgentState records
PYTHONPATH=src python -c "
from mini_agent.state import AgentState
s = AgentState()
s.record_tool('write_file', {'path': 'a.txt', 'content': 'hi'}, True, 'Wrote a.txt')
print(s.files_changed)   # ['a.txt']
print(s.tool_history)    # [{tool: write_file, ...}]
"

# Verify that prepare_messages returns the same object
PYTHONPATH=src python -c "
from mini_agent.state import AgentState
from mini_agent.context import ContextManager
history = [{'role': 'system', 'content': 'x'}]
cm = ContextManager(AgentState(), history)
print(cm.prepare_messages() is history)  # True
"
```

### Typical examples for this version

**Example 1: the Executor callback updates State**

```python
from mini_agent.state import AgentState
from mini_agent.tools import registry
from mini_agent.tools.base import ToolExecutor

state = AgentState()
exec_with_cb = ToolExecutor(registry, on_result=state.record_tool)

exec_with_cb.execute("calculate", {"expression": "1+1"})
print(state.tool_history[-1])  # {'tool': 'calculate', 'args': {...}, 'ok': True, 'brief': '2'}
print(state.status)             # running
```

**Example 2: CLI behavior matches v0.10**

```bash
PYTHONPATH=src python -m mini_agent "read examples/input.txt and calculate the expression in it"
# The interaction flow, permission prompts, and streaming output are exactly the same as v0.10
# The only difference is internal: the Executor quietly records State after each execution
```

### Features unique to this version

- **AgentState as an independent object**: not in messages, not operated on directly by the loop, safe under concurrency
- **ContextManager as the single entry**: all LLM requests are built through `prepare_messages()`
- **Executor result callback**: the permission denied/exception/success paths all feed State, and the loop is unaware of it
- **No half state**: all tool results of a round are fed back before the next round, so the protocol is always valid

## Next Lesson Preview

With the boundary in place, v0.12 does real work in `prepare_messages()`: heuristic token estimation (`len(text) // 3`), Context Budget ratio configuration, and atomic trimming by round when the limit is exceeded (a round = assistant(tool_calls) + all its tool results, never split — an orphan tool result is rejected outright with a 400 under the OpenAI protocol).

## Full Code for This Version

- [`src/mini_agent/state.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.11/src/mini_agent/state.py) — AgentState
- [`src/mini_agent/context.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.11/src/mini_agent/context.py) — ContextManager
- [`src/mini_agent/agent.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.11/src/mini_agent/agent.py) — agent loop
- [`src/mini_agent/tools/base.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.11/src/mini_agent/tools/base.py) — Executor callback
- [`tests/test_context.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.11/tests/test_context.py) — context tests

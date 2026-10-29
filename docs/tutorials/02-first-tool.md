# Lesson 2: First tool

> Version v0.02 | [Previous lesson](01-minimal-loop.md) | [Next lesson](03-file-tools.md)

> Code snapshot: `v0.02` · Adjacent diff: `v0.01..v0.02` · Shell: Bash/zsh
>
> Requirements: Python 3.9+.

## Lesson Goals

The LLM in the previous lesson could only generate text. Even when it answered an arithmetic question, it relied on the model's own inference; the program did not actually compute anything.

This lesson connects the first tool, `calculate`, and introduces function calling, the protocol in which "the model makes a tool call request and the program does the actual execution". To organize this flow, the code adds `Tool`, `ToolRegistry`, and `ToolExecutor`.

## Prerequisites

- Read [Lesson 1](01-minimal-loop.md) and understand the loop structure of the agent loop
- `git checkout v0.02` to switch to this version's code

## What Was Added or Changed

```
 src/mini_agent/
+├── tools/
+│   ├── __init__.py     # Registry hub: creates registry + executor, registers calculate
+│   ├── base.py         # Tool / ToolRegistry / ToolExecutor
+│   └── calc.py         # calculate tool
 ├── agent.py            # Changed: call_llm adds a tools argument; agent_loop runs tool_calls + feeds back role=tool
 └── __main__.py         # Changed: system prompt goes from "You are an assistant" to "complete tasks by calling tools"
+tests/
+└── test_tools.py        # New: tool smoke test
```

## Core Concepts

### The tool trio: Tool / ToolRegistry / ToolExecutor

The program must tell the model "which tools exist", and it must also know "which Python function to call when a request arrives". `Tool` (`src/mini_agent/tools/base.py:14`) puts both parts in one definition:

```python
@dataclass
class Tool:
    name: str           # Tool name shown to the LLM
    description: str    # Tool description shown to the LLM
    parameters: dict    # Parameter schema shown to the LLM (JSON Schema)
    handler: Callable   # Python function the Runtime actually runs
```

`name`, `description`, and `parameters` let the LLM understand the tool; `handler` is the function actually called at runtime. `to_llm_schema()` converts the first part into the format function calling needs.

**ToolRegistry** (`base.py:45`) is the tool registry. It stores, looks up, and lists tools, and can generate the list of schemas sent to the LLM. A schema is a structural description that tells the model which arguments a tool needs.

**ToolExecutor** (`base.py:82`) is the tool executor. It finds the matching `handler` by tool name, passes in the arguments, and converts expected execution exceptions into error results. v0.02 has no permission check yet; that comes in Lesson 4.

### The calculate tool (`src/mini_agent/tools/calc.py`)

```python
def calculate(expression: str):
    if not re.fullmatch(r"[\d\s+\-*/().]+", expression):
        raise ValueError("Expression contains illegal characters")
    return str(eval(expression))
```

`eval` executes a string, so it must not accept arbitrary content. The code first uses a regex allowlist that permits only digits, whitespace, and math operators, then passes the expression to `eval`.

### The function calling protocol

`call_llm` in v0.01 sent only `model` + `messages`. v0.02 adds a `tools` argument:

```python
body = json.dumps({
    "model": MODEL,
    "messages": messages,
    "tools": registry.schemas(),   # ← New: send the schemas of all tools to the LLM
}, ensure_ascii=False).encode()
```

After the LLM receives `tools`, it can answer directly or return `tool_calls` in its reply. `tool_calls` is a set of structured tool call requests, for example:

```python
{
    "role": "assistant",
    "content": None,                # May be null
    "tool_calls": [{
        "id": "call_abc123",
        "type": "function",
        "function": {
            "name": "calculate",
            "arguments": "{\"expression\": \"3+5*2\"}"
        }
    }]
}
```

### The tool_calls branch of agent_loop (`src/mini_agent/agent.py:55`)

The v0.01 loop only checked "no tool_calls means stop". v0.02 adds the "has tool_calls" branch:

```python
if not msg.get("tool_calls"):
    return msg.get("content", "")    # No tool call = final reply, stop

# Has tool_calls: run them and feed the results back as role=tool
for tc in msg["tool_calls"]:
    name = tc["function"]["name"]
    args = json.loads(tc["function"]["arguments"])
    result = executor.execute(name, args)

    messages.append({
        "role": "tool",
        "tool_call_id": tc["id"],      # Must match the id in tool_calls
        "content": str(result),
    })
# Go back to the top of the loop and call the LLM again with the tool results
```

The program cannot just stop after running the tools; it must send the results back to the LLM. This step is called "feeding back".

A fed-back message uses `role=tool` and must carry the `tool_call_id` of the original request. Because one round can contain several calls, the LLM uses this ID to tell which result belongs to which request. Only after all results are fed back does the loop enter the next round and let the model continue answering based on the results.

## Why This Design

### Why Tool carries both "the description for the LLM" and "the handler for the runtime"

If the schema and the Python function were registered separately, changing one side could miss the other. `Tool` keeps the description the model sees and the function the runtime runs together, so a single registration sets up the mapping between them.

### Why the Executor catches exceptions instead of letting the loop crash

Tool errors such as a missing file or an invalid argument are common, and after the model gets the error message it may retry with different arguments. So `ToolExecutor.execute` catches handler exceptions and feeds the error back as the tool result.

This boundary matches Lesson 1: the tool layer handles tool errors, and the core loop does not catch exceptions from LLM calls or the top-level CLI.

### Why tool_calls run serially

v0.02 runs multiple `tool_calls` in the same round one after another. This makes the order "take the request → run the tool → feed back the result" easiest to observe, but independent tools also have to wait for each other. Lesson 6 introduces concurrent execution.

## Usage Guide

### Commands available in this version

```bash
# Command-line first task
PYTHONPATH=src python -m mini_agent "calculate 3+5*2"

# Interactive mode
PYTHONPATH=src python -m mini_agent

# Run the smoke test
PYTHONPATH=src python tests/test_tools.py
```

### Typical examples for this version

**Example 1: let the LLM call calculate**
```bash
PYTHONPATH=src python -m mini_agent "calculate 123 * 456"
```
Expected output:
```
=== [1] LLM reply ===
  Decided call: calculate({'expression': '123 * 456'})
[Executor] Running Tool: calculate
[Executor] Arguments: {'expression': '123 * 456'}
  Result: 56088

=== [2] LLM reply ===
123 × 456 equals 56,088.
```
A tool result is always fed back here, but when the model gives the final text is up to the model. The example uses two rounds: round 1 asks for the calculation, and round 2 answers based on the result.

**Example 2: the LLM does not call a tool for what it can compute itself**
```bash
PYTHONPATH=src python -m mini_agent "What is 1+1"
```
Expected: the LLM may answer "2" directly without calling calculate — it can do simple arithmetic itself. This depends on the LLM's judgment.

**Example 3: a complex expression triggers the tool**
```bash
PYTHONPATH=src python -m mini_agent "calculate (100 + 200) * 3 / 5"
```
Expected: the LLM calls `calculate({'expression': '(100 + 200) * 3 / 5'})`, and the result is 180.

### Features unique to this version

- **Observe the role=tool feedback**: in the terminal log, the LLM returns `tool_calls` in round 1, the result is fed back as a `role=tool` message after execution, and only in round 2 does the LLM give the final text reply.
- **content is null**: when the LLM returns only tool_calls, the `content` field may be `null`; agent.py uses `if msg.get("content")` to skip printing empty content.
- **No permission interaction**: in v0.02 all tools run directly without asking the user (the permission gate arrives in v0.04).

## Hands-On Verification

1. **Run the smoke test**:
   ```bash
   PYTHONPATH=src python tests/test_tools.py
   ```
   Expected: 5 PASS lines and a message that all smoke tests passed.

2. **Let the agent do arithmetic**:
   ```bash
   PYTHONPATH=src python -m mini_agent "calculate 999 * 999"
   ```
   Expected: the LLM calls calculate, and the result is 998001.

3. **Observe the two-round loop**: note the two markers `=== [1]` and `=== [2]` in the terminal, and understand the flow "round 1 calls the tool, round 2 gives the answer".

## Full Code for This Version

- [`src/mini_agent/tools/base.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.02/src/mini_agent/tools/base.py) — Tool / ToolRegistry / ToolExecutor
- [`src/mini_agent/tools/calc.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.02/src/mini_agent/tools/calc.py) — calculate tool
- [`src/mini_agent/tools/__init__.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.02/src/mini_agent/tools/__init__.py) — registry hub
- [`src/mini_agent/agent.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.02/src/mini_agent/agent.py) — reworked call_llm + agent_loop
- [`tests/test_tools.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.02/tests/test_tools.py) — tool smoke test

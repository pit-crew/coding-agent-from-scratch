# Lesson 4: Permission gate

> Version v0.04 | [Previous lesson](03-file-tools.md) | [Next lesson](05-streaming.md)

> Code snapshot: `v0.04` · Adjacent diff: `v0.03..v0.04` · Shell: Bash/zsh
>
> Requirements: Python 3.10+. The `pyproject.toml` at this tag still says 3.9, but the source already uses 3.10 syntax.

## Lesson Goals

In the previous lesson, `write_file` overwrote the file as soon as it was called. If the model chose a wrong path, the user had no chance to stop it.

This lesson adds the permission gate `PermissionGate`. It checks rules before a tool runs and uses three results, `ALLOW`, `DENY`, and `ASK`, to decide whether to let the call through, refuse it, or ask the user first.

## Prerequisites

- Read [Lesson 3](03-file-tools.md) and understand the read_file/write_file tools
- `git checkout v0.04` to switch to this version's code

## What Was Added or Changed

```
 src/mini_agent/
+├── permission.py        # New: PermissionPolicy + PermissionGate (allow/deny/ask)
 └── tools/
     ├── base.py          # Changed: ToolExecutor takes a gate argument; execute passes the gate first
     ├── __init__.py      # Changed: imports PermissionGate (the executor creates a default gate)
     ├── calc.py          # Unchanged
     └── file.py          # Unchanged
 tests/
 └── test_tools.py        # Changed: write_file uses an allow policy to bypass ASK; adds a DENY test
```

## Core Concepts

### The three-state permission model (`src/mini_agent/permission.py`)

Different tools carry different risks. Reading and calculating can run by default, but writing a file needs the user's decision. So each tool has a permission state:

```python
ALLOW, DENY, ASK = "allow", "deny", "ask"

PERMISSION_RULES = {
    "read_file": ALLOW,    # No side effects, allow directly
    "calculate": ALLOW,    # No side effects, allow directly
    "write_file": ASK,     # Side effects, ask every time
}
```

- **ALLOW**: always runs directly without asking the user.
- **DENY**: always refused; the tool handler is never entered.
- **ASK**: shows `[once/always/reject]` before execution, and the user chooses on the spot.

### PermissionPolicy (`permission.py:27`)

The policy object, responsible for "looking up rules":

```python
class PermissionPolicy:
    def __init__(self, rules: dict | None = None):
        self.rules = rules if rules is not None else PERMISSION_RULES
        self._approved = set()  # Tool names "approved for this run" at runtime

    def check(self, tool_name, args=None) -> str:
        action = self.rules.get(tool_name, ALLOW)
        if action == ASK:
            if tool_name in self._approved:
                return ALLOW  # Already approved in this run, do not ask again
            return ASK
        return action
```

`PermissionPolicy` only looks up rules. The `_approved` set records the tool names for which the user chose `always` in this run, and later calls to a tool with the same name get `ALLOW` directly. When the program restarts, this record disappears.

### PermissionGate (`permission.py:58`)

The gate object, which wraps "check + interaction + lock":

```python
class PermissionGate:
    def guard(self, tool_name: str, args: dict) -> str | None:
        action = self.policy.check(tool_name, args)

        if action == DENY:
            return f"Permission denied: rules forbid calling {tool_name}"

        if action == ASK:
            with self._ask_lock:
                choice = input(
                    f"Allow {tool_name}({args})? [once/always/reject] "
                ).strip().lower()
                if choice == "always":
                    self.policy.approve(tool_name)
                elif choice != "once":
                    return f"Permission denied: user refused to run {tool_name}"

        return None  # None = allowed, str = reason for refusal
```

When `guard` returns `None`, the Executor can continue. When it returns a string, the string is the reason for refusal; the Executor does not call the handler and feeds the reason back to the LLM as the tool result.

### Integrating the gate into ToolExecutor (`src/mini_agent/tools/base.py:93`)

```python
class ToolExecutor:
    def __init__(self, registry: ToolRegistry, gate: PermissionGate | None = None):
        self.registry = registry
        self.gate = gate or PermissionGate()  # Use the default policy if none is passed

    def execute(self, name: str, arguments: dict):
        tool = self.registry.get(name)

        # ① Permission gate
        denied = self.gate.guard(name, arguments)
        if denied:
            print(f"[Permission] {denied}")
            return denied  # Feed the reason for refusal back to the LLM

        # ② Run the handler
        try:
            result = tool.handler(**arguments)
        except Exception as e:
            return f"Tool execution failed: {e}"
        return result
```

The Executor calls `gate.guard(name, args)` before calling the handler. The permission decision and user interaction are wrapped inside the gate, so the Executor only has to tell "continue" from "return the reason for refusal".

## Why This Design

### Why three states instead of two

With only allow and deny, `write_file` would either always run or be completely unusable. Neither choice fits the case "writing is sometimes allowed".

ASK defers the decision to the moment the call happens. The rule only says that this tool needs confirmation; whether it actually runs is decided by the user based on the current arguments.

### Why always uses the _approved set

After the user chooses `always`, `policy.approve(tool_name)` adds the tool name to `_approved`. When the tool is called again in the same program run, `check` returns ALLOW directly.

The approval is bound only to the tool name, does not check arguments, and is not written to disk. It is lost when the program restarts, but during this run every other call with the same tool name is also allowed.

### Why guard has _ask_lock

`_ask_lock` is a `threading.Lock()`. v0.04 still runs tools in order, so its effect is not visible yet. After Lesson 6 switches to concurrency, several threads may ask for confirmation at the same time; this lock makes the prompts appear one by one so that an input does not go to the wrong request.

### Why the reason for refusal is fed back to the LLM

After the user refuses, `guard` returns `"Permission denied: user refused to run write_file"`. This result is still fed back with the matching `tool_call_id`, so the protocol stays complete.

A refusal means the tool did not run, but it is not a program exception. After the LLM gets the result, it may try another approach, or tell the user directly that it cannot complete the write.

## Usage Guide

### Commands available in this version

```bash
# Command-line first task (may trigger permission interaction)
PYTHONPATH=src python -m mini_agent "write 'hello' to examples/test.txt"

# Run the smoke test (no interaction; bypassed with an allow policy)
PYTHONPATH=src python tests/test_tools.py
```

### Typical examples for this version

**Example 1: write_file triggers permission interaction**
```bash
PYTHONPATH=src python -m mini_agent "write 'test content' to examples/test.txt"
```
Expected output:
```
=== [1] LLM reply ===
  Decided call: write_file({'path': 'examples/test.txt', 'content': 'test content'})
Allow write_file({'path': 'examples/test.txt', 'content': 'test content'})? [once/always/reject]
```
Now enter:
- `once`: allow this time; the next write_file asks again
- `always`: allow all write_file calls in this run without asking again
- `reject` or anything else: refuse; the tool returns the reason for refusal to the LLM

**Example 2: read_file does not trigger permission**
```bash
PYTHONPATH=src python -m mini_agent "read examples/input.txt"
```
Expected: read_file is ALLOW, so it runs directly without asking.

**Example 3: how the LLM reacts after a refusal**
```bash
PYTHONPATH=src python -m mini_agent "write 'hello' to examples/test.txt"
# Enter reject at the permission prompt
```
Expected: after the LLM receives "Permission denied", it tells the user "you did not authorize me to write the file" or tries another way to complete the task.

### Features unique to this version

- **Permission prompt**: a `[once/always/reject]` prompt appears before write_file runs; this is the most visible change in v0.04.
- **always stops asking**: after you choose always, if you ask the agent to write other files in this run, it does not ask again.
- **A refusal is a tool result**: a refusal does not crash the agent; it is fed back as the tool result, and the LLM adjusts its strategy accordingly.

## Hands-On Verification

1. **Run the smoke test**:
   ```bash
   PYTHONPATH=src python tests/test_tools.py
   ```
   Expected: 8 PASS lines (including "write_file refused by the DENY policy").

2. **Trigger permission interaction**:
   ```bash
   PYTHONPATH=src python -m mini_agent "write 'hello' to examples/test.txt"
   ```
   Enter `once` at the permission prompt; the file should be written.

3. **Test always**:
   ```bash
   PYTHONPATH=src python -m mini_agent
   ```
   Enter "write 'hello' to examples/a.txt", and enter `always` at the permission prompt.
   Then enter "write 'world' to examples/b.txt"; it should write **without asking for permission again**.

## Full Code for This Version

- [`src/mini_agent/permission.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.04/src/mini_agent/permission.py) — PermissionPolicy + PermissionGate
- [`src/mini_agent/tools/base.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.04/src/mini_agent/tools/base.py) — ToolExecutor with a gate argument
- [`src/mini_agent/tools/__init__.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.04/src/mini_agent/tools/__init__.py) — imports PermissionGate
- [`tests/test_tools.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.04/tests/test_tools.py) — includes permission tests (allow/DENY)

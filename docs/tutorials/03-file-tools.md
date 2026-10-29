# Lesson 3: File read/write tools

> Version v0.03 | [Previous lesson](02-first-tool.md) | [Next lesson](04-permission-gate.md)

> Code snapshot: `v0.03` · Adjacent diff: `v0.02..v0.03` · Shell: Bash/zsh
>
> Requirements: Python 3.9+.

## Lesson Goals

The agent in the previous lesson could only calculate. It still could not view or change project files, so it could not do real programming tasks.

This lesson adds `read_file` and `write_file`. The first reads text; the second overwrites a file with text. The point is not only two new functions, but also how the model splits "read → process → write" into consecutive tool calls.

## Prerequisites

- Read [Lesson 2](02-first-tool.md) and understand the tool trio and the function calling protocol
- `git checkout v0.03` to switch to this version's code

## What Was Added or Changed

```
 src/mini_agent/tools/
+├── file.py             # New: read_file / write_file tools
 ├── __init__.py         # Changed: registers read_file / write_file
 ├── base.py             # Unchanged
 └── calc.py             # Unchanged
+examples/
+├── input.txt            # Example file (content: 3 + 5 * 2)
+└── input2.txt           # Example file (content: 3 + 5 * 3)
 tests/
 └── test_tools.py       # Changed: adds read_file / write_file tests
```

## Core Concepts

### read_file / write_file (`src/mini_agent/tools/file.py`)

```python
def read_file(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def write_file(path: str, content: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Wrote file: {path}"
```

Both handlers only use Python's `open`. What really needs explaining is the schema in the Tool definition, because the LLM uses it to decide how to fill in the arguments:

```python
read_file_tool = Tool(
    name="read_file",
    description="Read the contents of a text file",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path of the file to read"}
        },
        "required": ["path"],
    },
    handler=read_file,
)
```

`description` says what the tool does, and `parameters` gives the argument names, types, and required fields. The clearer the schema, the less likely the model passes wrong arguments.

### Registering new tools (`src/mini_agent/tools/__init__.py`)

```python
registry = ToolRegistry()
registry.register(calculate_tool)
registry.register(read_file_tool)    # ← New
registry.register(write_file_tool)   # ← New
```

Adding a tool takes three steps: write the handler, create the `Tool`, and put it in the registry. `agent.py` and the loop do not need to know the details of file tools, because they depend only on the uniform tool protocol.

### Chaining tools over several steps

A task may need several steps. For example, "read `examples/input.txt` and calculate" must first get the file content before it can pass the expression to the calculation tool. The LLM can decide the next step from each fed-back result:

```
=== [1] LLM reply ===
  Decided call: read_file({'path': 'examples/input.txt'})
  Result: 3 + 5 * 2

=== [2] LLM reply ===
  Decided call: calculate({'expression': '3 + 5 * 2'})
  Result: 13

=== [3] LLM reply ===
The file content is 3 + 5 * 2, and the result is 13.
```

The example takes 3 rounds: read the file, calculate, then answer. The LLM chooses this order; the agent loop only runs requests and feeds back results, and does not plan steps for the model.

## Why This Design

### Why write_file runs without asking

When v0.03 receives a `write_file` request, it runs it directly without asking the user. Because it overwrites, a wrong path or wrong content can destroy the original file.

This version shows the file capability on its own and does not handle authorization yet. v0.04 introduces `permission.py` and sets `write_file` to ASK, which asks the user before every execution.

### Why `"w"` mode instead of `"a"`

`"w"` means overwrite, so after the call the file content is exactly the `content` passed in. `"a"` appends to the end of the old content, so repeated calls keep accumulating. To make the results of this lesson easier to predict, this version chooses `"w"`.

### Why the tool signatures use one or two string arguments

`read_file(path: str)` takes one argument, and `write_file(path: str, content: str)` takes two.
This version only needs a path and text, so all arguments are strings. The simpler the structure, the easier it is for the model to produce correct arguments from the schema; nested dictionaries or lists increase the chance of format errors.

## Usage Guide

### Commands available in this version

```bash
# Command-line first task
PYTHONPATH=src python -m mini_agent "read examples/input.txt and calculate"

# Interactive mode
PYTHONPATH=src python -m mini_agent

# Run the smoke test
PYTHONPATH=src python tests/test_tools.py
```

### Typical examples for this version

**Example 1: read a file + calculate (multi-step chain)**
```bash
PYTHONPATH=src python -m mini_agent "read the contents of examples/input.txt and calculate"
```
Expected: 3 rounds, read_file → calculate → final reply "13".

**Example 2: write a file**
```bash
PYTHONPATH=src python -m mini_agent "write 'Hello World' to examples/output.txt"
```
Expected: the LLM calls `write_file({'path': 'examples/output.txt', 'content': 'Hello World'})` and replies that the file was written.

**Example 3: read then write (copy a file)**
```bash
PYTHONPATH=src python -m mini_agent "read examples/input.txt and write its contents to examples/copy.txt"
```
Expected: read_file gets the content, and write_file writes copy.txt.

### Features unique to this version

- **Chaining tools over several steps**: the LLM can chain several tools in one conversation (read → calculate → answer); after each result is fed back, the LLM decides the next step itself.
- **Tools with side effects**: `write_file` changes the file system; operations that affect the outside environment like this are called "side effects". v0.03 has no permission protection, so it always tries to write when called.
- **Relative path convention**: relative paths in tools start from the project root `mini_agent/`. You must run from the `mini_agent/` directory.

## Hands-On Verification

1. **Run the smoke test**:
   ```bash
   PYTHONPATH=src python tests/test_tools.py
   ```
   Expected: 7 PASS lines and a message that all smoke tests passed.

2. **Read a file + calculate**:
   ```bash
   PYTHONPATH=src python -m mini_agent "read examples/input.txt and calculate"
   ```
   Expected: 3 rounds, with a final result of 13.

3. **Verify writing a file**:
   ```bash
   PYTHONPATH=src python -m mini_agent "write 'test content' to examples/test.txt"
   ```
   Afterwards, check whether `examples/test.txt` was created and its content is correct.

## Full Code for This Version

- [`src/mini_agent/tools/file.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.03/src/mini_agent/tools/file.py) — read_file / write_file
- [`src/mini_agent/tools/__init__.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.03/src/mini_agent/tools/__init__.py) — registers the three tools
- [`tests/test_tools.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.03/tests/test_tools.py) — tool smoke test (including read_file/write_file)

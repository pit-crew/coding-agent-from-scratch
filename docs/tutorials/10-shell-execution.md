# Lesson 10: Shell execution

> Version v0.10 | [Previous lesson](09-permission-upgrade.md) | [Back to the tutorial overview](README.md)

> Code snapshot: `v0.10` · Adjacent diff: `v0.09..v0.10` · Shell: Bash/zsh
>
> Requirements: Python 3.10+. The `pyproject.toml` at this tag still says 3.9, but the source already uses 3.10 syntax.

## Lesson Goals

In earlier lessons the agent could read and write files and call tools, but it could not run tests or scripts itself. After it changed code, it still depended on the user to verify the result in a terminal.

This lesson adds the `run_shell` tool so the agent can run commands. The two-dimensional permissions of v0.09 can already decide permissions by command pattern; this lesson connects that capability to a real tool.

## Prerequisites

- Read the previous lesson
- `git checkout v0.10` to switch to this version's code (or look directly at `src/mini_agent/tools/shell.py`)

## What Was Added or Changed

```bash
git diff --stat v0.09..v0.10
```

| File | Change |
|------|------|
| `src/mini_agent/tools/shell.py` | **New**: `run_shell` tool (subprocess + timeout + output truncation) |
| `src/mini_agent/tools/__init__.py` | Registers `run_shell_tool` (7 tools) |
| `src/mini_agent/permission.py` | `PERMISSION_RULES` adds two-dimensional `run_shell` rules; `_from_config` ordering fix |
| `src/mini_agent/prompt.py` | `header()` capability description updated |
| `tests/test_tools.py` | Adds 3 run_shell tests |

## Core Concepts

### 1. The run_shell tool

Running shell commands must avoid three problems at once: a command hangs, the output is too long, or the model cannot see why a command failed. So `run_shell` sets a timeout, collects output, and includes the exit code.

```python
def run_shell(command: str):
    proc = subprocess.run(
        command,
        shell=True,
        cwd=os.getcwd(),
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,   # 30s
    )
    output = proc.stdout + proc.stderr
    # ... truncation + exit code prefix
```

Key design:
- **`shell=True`**: runs the command string directly, so readers do not first have to learn how to split it into an argument array. The permission gate takes care of safety.
- **`capture_output=True`**: collects stdout and stderr together.
- **`timeout=30`**: always times out and returns after 30 seconds, so a command cannot hang the agent.
- **Output truncated at 2000 characters**: long output does not fill the context, for the same purpose as the `read_file` limit.
- **Exit code prefix**: a nonzero exit code adds `[exit=N]`, so the LLM can tell the command failed.

### 2. Two-dimensional command pattern permissions

The risk of shell commands varies a lot. For example, reading git status can usually run directly, while deleting files needs confirmation. So the permission rules look not only at the tool name `run_shell` but also at the command text.

v0.09's `_extract_pattern()` returns the full command string for `run_shell`, and v0.10's permission rules match command prefixes with fnmatch wildcards:

```python
PERMISSION_RULES = {
    # ...
    "run_shell": {
        "git *": ALLOW,      # Allow git operations
        "python *": ALLOW,   # Allow python scripts/tests
        "pip *": ALLOW,      # Allow pip installs
        "ls *": ALLOW,       # Allow read-only commands
        "cat *": ALLOW,      # Allow read-only commands
        "echo *": ALLOW,     # Allow read-only commands
        "*": ASK,             # Ask for every other command
    },
}
```

The result: `git status` → allow, `python tests/test_tools.py` → allow, `rm -rf /` → ask.

### 3. The _from_config ordering fix

The wildcard rule `*` matches every command. If it is found first, a specific rule such as `echo *` never gets a chance to apply.

v0.10 found and fixed a findLast semantics flaw in v0.09:

**Problem**: in the complex format dict, `*` is placed last; after `_from_config` expands it in insertion order, `*` is also placed after the specific patterns. findLast searches from the end backwards, so it meets the match-everything `*` first, and the specific patterns are hidden.

**Fix**: `_from_config` sorts the patterns of the complex format, putting `*` first, that is, at the lowest priority, and specific patterns after it, at higher priority:

```python
# "*" goes first (lowest priority), specific patterns go after (higher priority)
items = sorted(value.items(), key=lambda kv: kv[0] != "*")
```

findLast searches from the end backwards, so it meets specific patterns (such as `echo *`) first and returns on a match; only when nothing matches does it reach the `*` fallback.

## Why This Design

### Why no BashArity command generalization?

The original plan mentioned "BashArity command generalization", that is, generalizing `git checkout main` to `git checkout *`. But `_extract_pattern` already returns the full command string, and fnmatch's `git *` can already match by command prefix.

So this version does not introduce BashArity. It only needs to be added later if "command" and "arguments" must be matched separately.

### Why shell=True?

`shell=True` runs the command string directly (`subprocess.run("echo hello", shell=True)` is equivalent to typing `echo hello` in a terminal). So the examples do not need to split argument arrays first.

It does not make commands safe by itself. The two-dimensional permission gate allows the commands the rules allow, and other commands still ask.

### Why a 30s timeout?

30 seconds is enough to run the tests here. Long tasks, such as `npm install`, may time out, and this version does not extend the timeout automatically. After a timeout the tool returns an error message, but the agent loop does not end.

### Why truncate output at 2000 characters?

This prevents long output from filling the context. `read_file` limits 2000 lines and `run_shell` truncates at 2000 characters; the units differ, but both limit the amount of data fed back to the LLM.

After truncation, the end marks the actual length, so the LLM knows the output is incomplete.

### Why merge stdout + stderr?

The LLM sees all output at once. If they were returned separately, it would have to parse both parts; merged, it can directly see error information such as a `Traceback` in stderr and judge the result.

## Usage Guide

### Commands available in this version

```bash
# Run the tests (now they can be run with run_shell!)
PYTHONPATH=src python tests/test_tools.py

# Verify the run_shell tool
PYTHONPATH=src python -c "from mini_agent.tools import executor; print(executor.execute('run_shell', {'command': 'echo hello'}))"
# Expected output: hello

# Verify two-dimensional permissions
PYTHONPATH=src python -c "from mini_agent.permission import PermissionPolicy; p = PermissionPolicy(); print(p.check('run_shell', 'git status'))"
# Expected output: allow
```

On POSIX (Linux/macOS), `test_run_shell_exit_code` uses the command `false`. The default permission rules ask once; enter `once` at the prompt, and the test then continues and finishes. Windows uses the already allowed `python -c "exit(1)"`, so this confirmation does not appear.

### Typical examples for this version

**Example 1: run an echo command**

```python
from mini_agent.tools import executor
result = executor.execute("run_shell", {"command": "echo hello_world"})
# → "hello_world\n"
```

**Example 2: nonzero exit code**

```python
result = executor.execute("run_shell", {"command": 'python -c "exit(1)"'})
# → "[exit=1] (no output)"
```

**Example 3: two-dimensional permissions, git allow / rm deny**

```python
from mini_agent.permission import PermissionPolicy, PermissionGate
from mini_agent.tools import registry, ToolExecutor

policy = PermissionPolicy({"run_shell": {"git *": "allow", "rm *": "deny", "*": "ask"}})
gate = PermissionGate(policy)
exec_test = ToolExecutor(registry, gate=gate)

exec_test.execute("run_shell", {"command": "git --version"})
# → allowed, returns "git version 2.x.x..."

exec_test.execute("run_shell", {"command": "rm -rf /tmp/nonexist"})
# → denied: "Permission denied: rules forbid calling run_shell(rm -rf /tmp/nonexist)"
```

### Features unique to this version

- **Running commands**: the agent can now run tests, scripts, and git commands
- **Command pattern permissions**: safe commands such as `git *`/`python *` are allowed, and other commands ask every time
- **Output truncation**: long output is truncated to 2000 characters, with the actual length marked at the end
- **Exit code prefix**: a nonzero exit code adds the `[exit=N]` prefix, so the LLM knows the command failed
- **findLast ordering fix**: `*` goes first (lowest priority), so specific patterns match first

## Full Code for This Version

- [`src/mini_agent/tools/shell.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.10/src/mini_agent/tools/shell.py) — run_shell tool
- [`src/mini_agent/permission.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.10/src/mini_agent/permission.py) — two-dimensional permission rules
- [`src/mini_agent/prompt.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.10/src/mini_agent/prompt.py) — header capability description update
- [`tests/test_tools.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.10/tests/test_tools.py) — 22 smoke tests

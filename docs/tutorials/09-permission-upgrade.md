# Lesson 9: Permission system upgrade

> Version v0.09 | [Previous lesson](08-file-operations.md) | [Next lesson](10-shell-execution.md)

> Code snapshot: `v0.09` · Adjacent diff: `v0.08..v0.09` · Shell: Bash/zsh
>
> Requirements: Python 3.10+. The `pyproject.toml` at this tag still says 3.9, but the source already uses 3.10 syntax.

## Lesson Goals

The previous version could only decide by tool name whether to allow, ask, or deny. When the same tool faced different files or commands, it usually had to treat them all the same way; the permission granularity was too coarse.

This lesson upgrades permissions to a two-dimensional `(tool_name, pattern) -> action`: besides the tool name, it also checks the file path or command pattern. This prepares for `run_shell` in v0.10, so that safe commands are allowed automatically and dangerous commands still ask.

## Prerequisites

- Read the previous lesson
- `git checkout v0.09` to switch to this version's code (or look directly at `src/mini_agent/permission.py`)

## What Was Added or Changed

```bash
git diff --stat v0.08..v0.09
```

| File | Change |
|------|------|
| `src/mini_agent/permission.py` | Rewritten: Rule triple + fnmatch + findLast + approve(pattern) + _extract_pattern |
| `tests/test_tools.py` | Adds 4 two-dimensional permission tests |

> `tools/base.py` is unchanged — the signature of `PermissionGate.guard()` stays the same, and it extracts the pattern from args internally.

## Core Concepts

### 1. The Rule triple: from a nested dict to a flat list

First the limitation of the previous version: v0.04 rules were a nested dict, `{"write_file": "ask"}`, which can only control by tool name. It cannot express a requirement such as "only allow writing certain kinds of files".

v0.09 stores rules as a flat list. Each rule records the tool, the matching pattern, and the action; these three fields together are a Rule (triple).

Internally, v0.09 stores a flat `list[dict]`, and each rule is a triple:

```python
[
    {"permission": "read_file", "pattern": "*", "action": "allow"},
    {"permission": "write_file", "pattern": "*", "action": "ask"},
    {"permission": "read_file", "pattern": "*.env", "action": "deny"},
]
```

The constructor `_from_config()` still accepts two configuration formats, so old configurations do not need to be rewritten right away:

```python
# Simple format (one-dimensional compatible, pattern defaults to "*")
PermissionPolicy({"write_file": "ask"})

# Complex format (two-dimensional, fine control by pattern)
PermissionPolicy({"read_file": {"*": "allow", "*.env": "deny"}})
```

### 2. check(): fnmatch + findLast

With several rules, the runtime must answer "which rule applies to the current call". `check()` matches the tool name and the pattern separately, searching from the end backwards.

```python
def check(self, tool_name: str, pattern: str = "*") -> str:
    merged = self._rules + self._approved
    for rule in reversed(merged):
        if fnmatch.fnmatch(tool_name, rule["permission"]) and fnmatch.fnmatch(pattern, rule["pattern"]):
            return rule["action"]
    return ASK  # No match defaults to ask
```

**Key design**:
- `fnmatch.fnmatch()` does wildcard matching: `*` matches any characters, and `?` matches a single character.
- `reversed()` searches from the end backwards, giving `findLast` semantics: rules that appear later have higher priority.
- If no rule matches, the result is always `ask`, and the call continues only after the user confirms.

**Why findLast?** Rules approved at runtime are appended to the end of `self._approved`. After `merged = rules + approved`, a reverse scan sees the approved rules first, which naturally override an earlier `ask` without explicitly deleting old rules.

### 3. approve(): storing (tool_name, pattern)

When the user chooses "always allow", the system must remember the scope of what was allowed. v0.09 stores the tool name and the pattern together, so one approval does not accidentally extend to all files.

```python
# v0.04: stores only the tool name
def approve(self, tool_name: str):
    self._approved.add(tool_name)

# v0.09: stores (tool_name, pattern)
def approve(self, tool_name: str, pattern: str = "*"):
    self._approved.append({
        "permission": tool_name, "pattern": pattern, "action": "allow"
    })
```

The effect: after the user chooses `always` for `write_file` + `*.txt`, later writes to `.txt` files no longer ask, but writes to `.py` files still ask.

### 4. _extract_pattern(): extracting the pattern from args

Tool call arguments have no common field called `pattern`, so the gate first extracts the text to match from the arguments: file tools use the path, the shell tool uses the full command, and other tools use `*`.

```python
@staticmethod
def _extract_pattern(tool_name: str, args: dict) -> str:
    if tool_name == "run_shell":
        return args.get("command", "*")  # v0.10 uses the full command as the pattern
    if tool_name in ("read_file", "write_file", "edit_file"):
        return args.get("path", "*")
    return "*"
```

`PermissionGate.guard()` calls `_extract_pattern()` and passes the resulting pattern to `check()`. For file tools the pattern is the file path, and `fnmatch` can match file names with patterns such as `*.env`.

## Why This Design

### Why not stay one-dimensional?

One-dimensional permissions, `tool_name -> action`, cannot tell different operations of the same tool apart. For example, `run_shell` running `git status` (usually safe) and `rm -rf /` (dangerous) would have to share one action. Either everything is allowed or everything asks.

Two-dimensional permissions handle each command pattern separately: `git *` can be allow, `rm *` can be deny, and other commands stay ask.

### Why findLast instead of first?

OpenCode's `evaluate()` uses `findLast`, so rules that appear later have higher priority. `approved` rules appended at runtime naturally override earlier `ask` rules.

With first, an earlier ask would block the approved rule, and the system would have to delete old rules explicitly, which makes the logic more complex.

### Why does no match default to ask instead of allow?

This is a safety-first choice. A new tool or an unconfigured tool must ask the user first, so that dangerous operations are not silently allowed.

### Why does _extract_pattern return only the full command for run_shell?

v0.09 only upgrades the permission framework and does not yet implement the `run_shell` tool. `_extract_pattern()` first returns the full command string, and v0.10 then matches command prefixes directly with fnmatch wildcards (such as `git *`). No BashArity command generalization is done here, because fnmatch is already enough.

### Why does existing tool behavior stay the same? (two dimensions degrade to one)

After the upgrade, the actual permission decisions for the 6 tools `calculate`/`read_file`/`write_file`/`edit_file`/`list_dir`/`grep` are exactly the same as in v0.08. This is for backward compatibility; it does not mean two-dimensional matching is inactive. There are two reasons:

**① All rule patterns are `*`**

`PERMISSION_RULES` (the hard-coded configuration in `permission.py`) is still in simple dict format:

```python
PERMISSION_RULES = {
    "read_file": ALLOW,   # _from_config turns this into {permission: "read_file", pattern: "*", action: "allow"}
    "write_file": ASK,    # _from_config turns this into {permission: "write_file", pattern: "*", action: "ask"}
    ...
}
```

`_from_config()` fills in `pattern="*"` for the simple format `"write_file": "ask"` (see `permission.py:68`), and there are no rule entries split by path.

**② `fnmatch("*", X)` is always True**

`check()` matches the pattern with `fnmatch` (`permission.py:84`):

- For `calculate`/`list_dir`/`grep`: `_extract_pattern` returns `"*"` (`permission.py:147`), the rule pattern is also `"*"`, and `fnmatch("*", "*")` → True, equivalent to the one-dimensional decision.
- For `read_file`/`write_file`/`edit_file`: `_extract_pattern` returns the real path (such as `"a.txt"`, `permission.py:145`), but the rule pattern is still `"*"`, and `fnmatch("*", "a.txt")` → True, again equivalent to one dimension.

**Design intent**: two-dimensional permissions mainly serve `run_shell` in v0.10, because shell commands really need to be distinguished by pattern (`git *` allow, `rm *` deny). v0.09 does not preset fine-grained rules for file tools and still falls back to `*`; if you really need to restrict by path, configure it explicitly:

```python
PermissionPolicy({"read_file": {"*": "allow", "*.env": "deny", "*.key": "deny"}})
```

**The only behavior difference is the narrower approve granularity.**

v0.09's `approve()` stores `(tool_name, pattern)` instead of only `tool_name` (`permission.py:88-95`). So after you choose `always` for `a.txt`, writing `b.txt` still asks. The no-ask scope narrows from "the whole tool" to "the tool plus a path pattern", which is safer.

To make all `write_file` calls skip the question, configure `{"write_file": {"*": "allow"}}` explicitly, or use `"*"` as the pattern when choosing `always`.

### What was borrowed from OpenCode, and what was removed?

Borrowed:
- `evaluate()`'s `findLast` + `Wildcard.match` + no match defaults to ask
- `fromConfig()` supports both the simple and the complex format
- `approve()` stores the pattern, not only the tool name

Removed (not needed for synchronous CLI interaction):
- The event bus `Bus.publish` — a synchronous blocking `input()` is enough
- The `pending` queue — there is no asynchronous UI
- Persisting rules to disk — they stay in memory
- `CorrectedError` (reject with an explanation) — explanations are hard to collect in a CLI

## Usage Guide

### Commands available in this version

```bash
# Run the tests
PYTHONPATH=src python tests/test_tools.py

# Verify the permission system
PYTHONPATH=src python -c "from mini_agent.permission import PermissionPolicy; p = PermissionPolicy({'read_file': {'*': 'allow', '*.env': 'deny'}}); print(p.check('read_file', 'secret.env'))"
# Expected output: deny
```

### Typical examples for this version

**Example 1: control read permission by file name pattern**

```python
from mini_agent.permission import PermissionPolicy

policy = PermissionPolicy({"read_file": {"*": "allow", "*.env": "deny", "*.env.example": "allow"}})
policy.check("read_file", "config.env")       # → deny
policy.check("read_file", "config.env.example") # → allow
policy.check("read_file", "README.md")         # → allow
```

**Example 2: always stores the pattern, so similar calls skip the question**

```python
policy = PermissionPolicy({"write_file": "ask"})
policy.approve("write_file", "*.txt")
policy.check("write_file", "test.txt")  # → allow (*.txt was approved)
policy.check("write_file", "test.py")   # → ask (*.py was not approved)
```

**Example 3: findLast priority**

```python
policy = PermissionPolicy({"write_file": "ask"})
policy.approve("write_file", "*")
policy.check("write_file", "anything")  # → allow (approved is appended at the end and overrides ask)
```

### Features unique to this version

- **Two-dimensional permission matching**: `fnmatch` controls different operations of the same tool by pattern
- **findLast priority**: rules that appear later have higher priority, so approved naturally overrides ask
- **Backward compatible**: the old simple dict format `{"write_file": "ask"}` still works, with the pattern defaulting to `"*"`

## Full Code for This Version

- [`src/mini_agent/permission.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.09/src/mini_agent/permission.py) — permission system core
- [`tests/test_tools.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.09/tests/test_tools.py) — 19 smoke tests

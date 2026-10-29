# Lesson 8: Completing file operations

> Version v0.08 | [Previous lesson](07-system-prompt.md) | [Next lesson](09-permission-upgrade.md)

> Code snapshot: `v0.08` · Adjacent diff: `v0.07..v0.08` · Shell: Bash/zsh
>
> Requirements: Python 3.10+. The `pyproject.toml` at this tag still says 3.9, but the source already uses 3.10 syntax.

## Lesson Goals

Until now the agent could read and write files, but it often did not know what was in the project or where the target content was, or it rewrote a whole file to change one line.
This version adds `list_dir` (list a directory), `edit_file` (exact replacement), and `grep` (regex search), and lets `read_file` read in segments with `offset`/`limit`. This way the agent can complete basic programming tasks in the order "browse → locate → read → edit".

## Prerequisites

- Read [Lesson 7](07-system-prompt.md) and understand system prompt engineering
- `git checkout v0.08` to switch to this version's code

## What Was Added or Changed

```
 src/mini_agent/tools/
 ├── file.py            # Changed: read_file adds offset/limit + new edit_file/list_dir/grep
 ├── __init__.py        # Changed: registers edit_file/list_dir/grep
 ├── base.py            # Unchanged
 └── calc.py            # Unchanged
 src/mini_agent/
 └── permission.py      # Changed: list_dir/grep=ALLOW, edit_file=ASK
 tests/
 └── test_tools.py      # Changed: adds 6 new tests, 15 in total
```

> This version only changes `file.py`, `permission.py`, `__init__.py`, and the tests. `agent.py` is untouched, because the core loop still only handles the `messages` list and does not need to know whether the number of tools changed.

## Core Concepts

### Why the three tools from v0.03 are not enough

v0.03 already has `read_file`/`write_file` for reading and writing files. But real programming tasks still lack three actions:

1. **No view of the directory structure**: the agent does not know which files the project has and relies on the user to give it paths. It needs `list_dir`.
2. **Files can only be rewritten whole**: changing one line still needs `write_file` to rewrite the whole file, which wastes tokens on large files and can lose content. It needs `edit_file` for local replacement.
3. **No way to find where content is**: the agent wants to change a function but does not know which file it is in. It needs `grep` to search content and find the file.

This version fills these three gaps and adds segmented reading to `read_file`, forming a complete file operation chain.

### read_file adds offset/limit (`src/mini_agent/tools/file.py`)

Before, `read_file` read the whole content at once. For a large file, the result could fill the context.
v0.08 uses `offset`/`limit` to say which line to start from and how many lines to read at most:

```python
def read_file(path: str, offset: int = 0, limit: int = 2000):
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    total = len(lines)
    start = max(0, offset)
    end = min(start + limit, total)
    numbered = [f"{i + 1:05d}| {lines[i]}" for i in range(start, end)]
    ...
```

Reading this way also solves two problems:

- **Line number prefix** `00001| `: borrowed from OpenCode's ReadTool. When the LLM sees line numbers, it chooses `old_string` for `edit_file` more accurately and is less likely to match the wrong place.
- **Remaining lines hint**: when the file is not fully read, the result appends `(N lines in total, M read, K not yet read)`. So the model knows there is more content and may call `read_file(offset=...)` again.

### edit_file: exact string replacement

When editing files, the model is not good at counting line numbers reliably. So `edit_file` does exact string replacement with `old_string`/`new_string`:

```python
def edit_file(path: str, old_string: str, new_string: str, replace_all: bool = False):
    if old_string == new_string:
        raise ValueError("old_string and new_string must differ")
    content = ...
    count = content.count(old_string)
    if count == 0:
        raise ValueError(f"No match found: {old_string[:50]}...")
    if count > 1 and not replace_all:
        raise ValueError(f"Found {count} matches; set replace_all=true or give a longer unique context")
    ...
```

**Why string matching instead of line numbers**: the LLM may miscount lines, especially in large files. String matching lets it copy the fragment to change directly from the `read_file` output, so locating it is more reliable.

**Multiple match safety check**: when `old_string` appears more than once, the code always reports an error instead of quietly replacing the first one. This avoids changing unrelated places.
The LLM either passes `replace_all=true` to confirm replacing all of them, or expands `old_string` until it is unique. This follows the safety design of OpenCode's EditTool but keeps only one simple strategy; its eight fuzzy matching strategies are too complex for this teaching project.

### list_dir: list directory contents

```python
def list_dir(path: str = "."):
    entries = []
    for name in sorted(os.listdir(path)):
        full = os.path.join(path, name)
        kind = "/" if os.path.isdir(full) else ""
        entries.append(f"{name}{kind}")
    ...
```

Directories get a `/` suffix, so the model can tell files from directories directly. At most 200 entries are returned, so a very large directory does not return too much content.

### grep: regex search over file contents (pure standard library)

```python
def grep(pattern: str, path: str = ".", include: str = "*"):
    regex = re.compile(pattern)
    results = []
    for root, dirs, files in os.walk(path):
        for fname in sorted(files):
            if not fnmatch.fnmatch(fname, include):
                continue
            ...
            for i, line in enumerate(f, 1):
                if regex.search(line):
                    results.append(f"{fpath}:{i}: {line.rstrip()}")
```

The search implementation balances three points:

- **No dependencies**: it uses `re`, `os.walk`, and `fnmatch` and does not depend on ripgrep. mini_agent's convention is no third-party runtime dependencies.
- **`include` filter**: supports glob patterns such as `*.py` to filter file names, so it avoids searching `.git/` or binary files.
- **Limit of 100**: there can be many matches, so at most 100 are returned. The output format `file:line: content` follows ripgrep.

### Permission policy update (`src/mini_agent/permission.py`)

```python
PERMISSION_RULES = {
    "read_file": ALLOW,
    "calculate": ALLOW,
    "list_dir": ALLOW,   # Read-only, allow
    "grep": ALLOW,       # Read-only, allow
    "write_file": ASK,   # Side effects
    "edit_file": ASK,    # Side effects, same as write_file
}
```

`list_dir`/`grep` only read information, so they are allowed directly. `edit_file` changes files, so it always goes through ASK.
This continues the v0.04 policy: operations with side effects need confirmation.

## Why This Design

### Why edit_file does not do fuzzy matching

When an edit does not match, fuzzy matching might seem worth trying. OpenCode's EditTool has eight strategies, including ignoring whitespace, similarity, and context awareness.
mini_agent only does exact matching, because:

1. **Teaching first**: the priorities and thresholds of eight strategies are engineering details, not the core of this lesson.
2. **Exact matching + replace_all is enough**: the LLM can copy the original text from the `read_file` output as `old_string`, which is usually reliable enough.
3. **Failures give feedback**: when matching fails, the tool returns an error. The LLM can widen the context, or call `read_file` again to confirm the content and retry.

### Why grep does not use ripgrep

OpenCode's GrepTool uses the external ripgrep binary. mini_agent's convention is no third-party dependencies, so it is implemented with `re`, `os.walk`, and `fnmatch`.
Its performance is far below ripgrep, which uses Rust parallelism and memory mapping, but teaching scenarios have few files, so it is enough. After v0.09 adds `run_shell`, the LLM can call `rg` itself for faster searches.

### Why read_file adds line number prefixes

v0.03's `read_file` only output text, so the LLM did not know which lines each part came from. With the `00001| ` prefix, it can choose `old_string` for `edit_file` more accurately, and multiple match errors also decrease.
This is where `read_file` and `edit_file` work together.

## Usage Guide

### Commands available in this version

```bash
# Command-line first task
PYTHONPATH=src python -m mini_agent "list the contents of the examples directory"

# Interactive mode
PYTHONPATH=src python -m mini_agent

# Run the smoke test
PYTHONPATH=src python tests/test_tools.py
```

### Typical examples for this version

**Example 1: list a directory + read a file**
```bash
PYTHONPATH=src python -m mini_agent "see what is in the examples directory, then read input.txt"
```
Expected: the agent first lists the directory with `list_dir`, then reads the content with `read_file`, and finally replies.

**Example 2: edit a file exactly**
```bash
PYTHONPATH=src python -m mini_agent "read examples/input.txt and change the 5 in it to 100"
```
Expected: the agent first calls `read_file`, then `edit_file` changes `3 + 5 * 2` to `3 + 100 * 2`. This step triggers an ASK permission confirmation.

**Example 3: search to locate**
```bash
PYTHONPATH=src python -m mini_agent "search for all files under src that contain calculate"
```
Expected: after `grep` searches, the results come back in `file:line: content` format.

**Example 4: read a large file in segments**
```bash
PYTHONPATH=src python -m mini_agent "read lines 50 to 70 of src/mini_agent/agent.py"
```
Expected: after calling `read_file(offset=50, limit=20)`, lines 51-70 come back, 20 lines in total, each with a line number prefix. `offset` is the number of lines to skip, starting from 0.

### Features unique to this version

- **Complete file operation chain**: browse with `list_dir`, locate with `grep`, read with `read_file`, edit with `edit_file`; the agent can complete basic programming tasks.
- **Segmented reading**: `read_file` supports `offset`/`limit`, so a large file does not use the whole context at once.
- **Exact editing**: `edit_file` replaces by string and reports an error first on multiple matches, avoiding wrong edits.
- **Line number prefix**: the `00001| ` prefix in `read_file` output helps the LLM choose `old_string` for `edit_file`.

## Hands-On Verification

1. **Run the smoke test**:
   ```bash
   PYTHONPATH=src python tests/test_tools.py
   ```
   Expected: 15 PASS lines and a message that all smoke tests passed.

2. **List a directory + read a file**:
   ```bash
   PYTHONPATH=src python -m mini_agent "list the examples directory and read input.txt"
   ```

3. **Exact edit**:
   ```bash
   PYTHONPATH=src python -m mini_agent "read examples/input.txt and change 5 to 100"
   ```
   Afterwards, check whether `examples/input.txt` was changed correctly.

4. **Search to locate**:
   ```bash
   PYTHONPATH=src python -m mini_agent "search for all files under src that contain PermissionGate"
   ```

## Full Code for This Version

- [`src/mini_agent/tools/file.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.08/src/mini_agent/tools/file.py) — read_file (with offset/limit) + write_file + edit_file + list_dir + grep
- [`src/mini_agent/permission.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.08/src/mini_agent/permission.py) — permission rules (list_dir/grep=ALLOW, edit_file=ASK)
- [`src/mini_agent/tools/__init__.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.08/src/mini_agent/tools/__init__.py) — registers 6 tools
- [`tests/test_tools.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.08/tests/test_tools.py) — 15 smoke tests

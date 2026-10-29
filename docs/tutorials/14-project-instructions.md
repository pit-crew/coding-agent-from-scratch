# Lesson 14: Project instructions (Project Instructions, v0.14)

Previous: [Context compaction](13-context-compaction.md) · [Tutorial overview](README.md) · Next: [Task list and state](15-task-state.md)

> Code snapshot: `v0.14` · Adjacent diff: `v0.13.1..v0.14` · Shell: Bash/zsh

> Requirements: Python 3.10+. The `pyproject.toml` of historical tags still says Python 3.9, but the v0.14 source already uses 3.10 syntax.

## Lesson Goals

This lesson introduces only one change: at startup the Agent reads the applicable `AGENTS.md`, puts the project rules into the system prompt, and keeps those rules in every LLM request.

After this lesson, you should be able to:

- Describe the discovery range and merge order of `AGENTS.md` inside and outside a Git repository;
- Understand the source markers, the 12,000-character limit, and how read failures are handled;
- Explain why project instructions go into `protected_messages` instead of the ordinary `history`;
- Tell the difference between "telling the model a rule" and the tool permissions `PermissionGate` actually grants.

The core invariant of this lesson: **project rules are kept with every request, but they are not treated as tool authorization configuration.**

## Problems in the Previous Version

v0.13 can compact old history when the context is over budget, but it only manages content that has already entered the message history. If the project's test commands, code style, or forbidden operations are not explicitly sent to the model, the model cannot see them; if the rules are appended to the ordinary history, later trimming may delete them and compaction may rewrite them.

So v0.14 manages "project rules" and "conversation history" separately: the rules are loaded once at process startup and become a protected system message; the history is still handled by `ContextManager` according to the budget.

## Prerequisites and Version Checkout

Read Lesson 13 first to understand `ContextManager`, history rounds, and the protected prefix. All commands below are for Bash/zsh; the last one switches back to this lesson's `v0.14` snapshot.

```bash
git checkout v0.13.1
git diff --stat v0.13.1..v0.14
git diff v0.13.1..v0.14 -- src/mini_agent/instructions.py src/mini_agent/prompt.py src/mini_agent/context.py src/mini_agent/__main__.py
git checkout v0.14
```

## New and Changed Files

The full difference is given by `git diff --stat v0.13.1..v0.14`. The table below keeps only the files needed to understand this lesson's main thread.

| File | Change | Purpose |
|---|---|---|
| `src/mini_agent/instructions.py` | Adds `InstructionLoader` | Finds and merges the `AGENTS.md` files that apply to the startup directory |
| `src/mini_agent/prompt.py` | Changes `build_system_prompt()` | Adds a `<project_instructions>` block when there are rules |
| `src/mini_agent/context.py` | Adds `protected_messages` | Keeps the system prompt in every request; history can still be trimmed/compacted |
| `src/mini_agent/__main__.py` | Changes the startup flow | Loads the rules and injects protected messages before the context is created |
| `tests/test_instructions.py`, `tests/test_prompt.py`, `tests/test_context.py` | New coverage | Pins down discovery, the limit, injection, and retention behavior |

## Version Change Map

Legend: `[old]` already in v0.13.1, `[+]` new in v0.14, `[~]` changed in v0.14, `[C]` main consumer, `[B]` boundary of this version.

The real entry and finish of v0.13.1:

```text
[old] CLI main()
  -> [old] AgentState + history + ContextManager
  -> [old] agent_loop
       -> [old] prepare_messages()
            -> trimming / compaction (history only)
            -> [C] call_llm()
```

v0.14 inserts loading and injection at the startup entry:

```text
[old] CLI main()
  -> [+] InstructionLoader(os.getcwd())
       -> [+] discover(): look for AGENTS.md level by level from the Git root to cwd
       -> [+] load(): Source markers, at most 12,000 characters
  -> [~] build_system_prompt(project_instructions)
  -> [~] ContextManager(protected_messages + history)
       -> [old] prepare_messages()
            -> [old] only trims/compacts history
            -> [C] every call_llm() carries the project rules

[B] Files are not refreshed after startup; the rules do not change PermissionGate allow/deny/ask results
```

The key insertion point is not "one more block of text" but `protected_messages`: it puts the rules into the sent view without putting them into the mutable `history`.

## Core Concepts and Data Structures

### 1. The discovery range sets the scope of the rules

The problem: when the agent starts in a subdirectory, which project rules apply? `InstructionLoader` first searches upward from `cwd` for the Git root. If it finds one, it checks `AGENTS.md` level by level from "root → current directory"; files closer to `cwd` appear later, so they can override or add to upper-level rules. Outside a Git repository, it checks only `cwd` itself and does not inherit from parent directories.

```python
return [
    os.path.join(directory, "AGENTS.md")
    for directory in directories
    if os.path.isfile(os.path.join(directory, "AGENTS.md"))
]
```

`discover()` returns a list of paths and does not execute file content. This ordering invariant makes the merge result predictable and fixes the scope of the rules to the startup directory.

### 2. Loaded results carry sources and have a hard limit

`load()` adds `Source: <path>` to each file and concatenates the bodies in discovery order. When reading a file raises `OSError`, the CLI startup does not fail; instead, `[read failed, skipped]` is written. The accumulated text is at most 12,000 characters; when it goes over, a truncation marker is appended and later files are not read. When there are no files, it returns an empty string.

The core concatenation logic first computes how much space is left; if the full block does not fit, it keeps the prefix, appends a truncation marker, and stops loading:

```python
available = self.max_chars - used - len(separator)
if len(chunk) > available:
    marker = f"\\n[Instructions truncated; at most {self.max_chars} characters kept]"
    chunk = chunk[:max(0, available - len(marker))] + marker
    chunks.append(separator + chunk)
    break
```

This guarantees that the return value does not exceed the loader limit, while keeping the source hint of "which file provided the rule".

So the caller only has to handle one string: an empty string means no project block is added, and a non-empty string means source marking and length control are already done.

### 3. Protected messages and ordinary history have two different lifecycles

The problem: how do the rules get through the trimming and compaction of Lesson 13? The CLI puts the full system prompt into `protected_messages`. `ContextManager._build_messages()` copies this group of messages every time and then appends `history`; only the latter is trimmed, split into rounds, or compacted.

```python
source = ([dict(message) for message in self.protected_messages]
          if self.protected_messages is not None else [])
source.extend(dict(message) for message in self.history)
```

The original text of the rules is not rewritten by history trimming or summarization, but it still counts toward the context budget. Protected only means "cannot be removed by history strategies", not that it can grow without limit.

### 4. Prompt injection is not permission granting

`build_system_prompt()` appends the block only when the argument is not empty:

```python
if project_instructions.strip():
    sections.append(
        "<project_instructions>\n"
        + project_instructions.strip()
        + "\n</project_instructions>"
    )
```

The model can use this content to choose "run the tests first" or "do not touch a certain directory", but actual file writes and shell execution are still decided by the tool layer and `PermissionGate`. v0.14 does not compile natural language rules into allow/deny/ask configuration.

## Why This Design

Rules and history have different lifecycles. Rules should appear every round in their original text, while history must give up old content when the window gets small. Storing them separately meets both needs and makes the scope of the rules and the request content easier to audit.

The cost is that the rules use context budget in every request; 12,000 characters is only the loader limit and does not guarantee that the whole system prompt is smaller than the model window. Loading only once at startup keeps the behavior of one run stable, but changing `AGENTS.md` or switching the working directory during a run does not take effect automatically.

Choosing plain text injection instead of automatically changing the permission system avoids the risk of interpreting natural language as security decisions and keeps the implementation simple; accordingly, project rules cannot replace the permission gate.

## Design Boundaries

- Inside a Git repository, only the path from the repository root to the startup `cwd` is checked; outside Git, only the current directory is checked.
- Only files named exactly `AGENTS.md` are supported; other editor or Agent formats are not read automatically.
- A missing file, a read failure, or truncation does not stop startup; but the model may lack some project constraints.
- The rules are fixed at process startup and are not refreshed when new directories are visited later.
- The loader outputs at most 12,000 characters; the system prompt and protected messages themselves can still make the budget tight.
- `PermissionGate` authorization results, the tool exception boundary, and the tool call feedback protocol are not changed by this version.

## Key Flow

```text
startup cwd
  -> _git_root()
  -> discover(): ordered AGENTS.md paths
  -> load(): read, mark sources, limit length
  -> build_system_prompt(project_instructions)
  -> protected_messages
  -> prepare_messages()
       ├─ rules: always kept
       └─ history: trimming / compaction by budget
  -> call_llm()
```

On the normal path, the model sees `<project_instructions>` in every request. When there is no rules file, `load()` returns an empty string, and the system prompt is the same as in v0.13.1. On a read failure startup continues, but a skip marker remains in the system prompt; if the history later exceeds the budget, only the history copy is handled. Top-level CLI or LLM exceptions are not caught by the logic added in this lesson.

## Implementation Breakdown

### The startup entry

`__main__.py` first creates `AgentState`, then reads the rules for the current working directory, and finally hands the system message to the context manager:

```python
instructions = InstructionLoader(os.getcwd()).load()
system_prompt = (
    build_system_prompt(project_instructions=instructions)
    if instructions else build_system_prompt()
)
protected_messages = [{"role": "system", "content": system_prompt}]
context = ContextManager(state, history)
context.protected_messages = protected_messages
```

This way the rules are decided only once, at startup; every `prepare_messages()` copies from the same protected messages, so no path can forget to add them.

### Position in the compacted view

When the context is already in compaction mode, `ContextManager` rebuilds the view "protected system → Structured State → Historical Summary → task → recent history". The project rules belong to the protected system part at the very front; the `Historical Summary` still only describes old history and cannot override the project rules.

### Call boundary of the default summarizer

v0.14 keeps the summary channel of v0.13. `summarize_messages()` calls `call_llm(..., include_tools=False, stream_output=False)`: the summary request has no tool definitions and does not print the internal summary stream to the terminal. Project instructions do not take part in summarization, so the summarizer does not rewrite them.

## Run and Observe (If Needed)

After you configure a local LLM, start in a project directory that contains `AGENTS.md` (Bash/zsh):

```bash
PYTHONPATH=src python -m mini_agent "read the project rules and list the current directory"
```

This is a "command-line first task"; after the first task is handled, the program still enters the interactive loop. When you look at model requests or context logs, you should see a `<project_instructions>` block in the system prompt; when you start in a directory without `AGENTS.md`, the block does not appear. If the task gets long and triggers compaction, the project block is still kept, while old history may be summarized or trimmed.

## Version Features, Next Lesson, and Code Index

v0.14 introduces startup directory scope, level-by-level discovery, source markers, a 12,000-character limit, and a project-level system prompt that is not affected by history trimming. It provides no dynamic refresh, supports no other rules file formats, and does not turn rules into tool permissions. The next lesson, v0.15, saves Todo and task state in the independent `AgentState`, so the plan can still be shown accurately after context compaction.

Pinned v0.14 source for this lesson:

- [`src/mini_agent/instructions.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.14/src/mini_agent/instructions.py) — discovers and loads `AGENTS.md`
- [`src/mini_agent/prompt.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.14/src/mini_agent/prompt.py) — assembles the project instruction block
- [`src/mini_agent/context.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.14/src/mini_agent/context.py) — protected messages, history trimming, and the compacted view
- [`src/mini_agent/__main__.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.14/src/mini_agent/__main__.py) — injects the rules at startup
- [`tests/test_instructions.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.14/tests/test_instructions.py) — discovery, ordering, and length boundaries
- [`tests/test_prompt.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.14/tests/test_prompt.py) — project instruction block
- [`tests/test_context.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.14/tests/test_context.py) — protected message behavior

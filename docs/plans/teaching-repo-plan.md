# Multi-Stage Teaching Repository Plan

> Status: plan confirmed; tutorial navigation is implemented as a single directory organized by stage
> Decision record: reset main to v0.01 / reuse docs/ with a tutorials subdirectory / v0.01 is a tool-free pure conversation loop / plan first, do not touch code
> Update: the tutorial document template adds a "Usage Guide" section that evolves with the versions
> Update: switched to continuous iteration with no fixed version limit, adding one feature at a time until the capability set of a lightweight coding agent is reached
> Update: the tutorial entry is organized by stage; individual lessons stay in the `docs/tutorials/` root by version, with no new stage subdirectories
> Update: v0.011 was split into the three versions v0.11–v0.13 of "Stage 4: Context Management" (the tag name v0.011 was dropped), and plan guidance moved on to v0.14; see `context-management-plan.md`

## 1. Goal

Turn `mini_agent` into a **teaching repository navigated by capability stage and sliced by version number**: learners start at Stage 1 and check out in the order `v0.01 → v0.02 → ...`; each version introduces only one new concept with a matching teaching document, until learners understand how a coding agent that can read, write, and edit files, run commands, and run tests grows step by step.

This repository is not limited to a fixed number of versions; it uses continuous iteration, adding one feature at a time until the capability set of a lightweight coding agent is reached. Later versions are added as needed, with no limit.

## 2. Version Slicing Table

Each version adds only one concept relative to the previous one. Tag names are `v0.X`.

| Version | Topic | Only adds, relative to the previous version | Teaching document points |
|---|---|---|---|
| v0.01 | Minimal agent loop | `call_llm` (non-streaming) + `agent_loop` (tool-free pure conversation) + `__main__` + `config.py` | What an agent loop is; the messages list; the end condition; calling the LLM with http.client |
| v0.02 | First tool | `Tool`/`ToolRegistry`/`ToolExecutor` + `calculate` + the function calling protocol | How tools connect to the loop; `role=tool` feedback; tool signature conventions |
| v0.03 | File read/write tools | `read_file`/`write_file` | How the agent reads and writes files; the risks of side-effect tools |
| v0.04 | Permission gate | `permission.py` (allow/deny/ask) + `PermissionGate` + `write_file` changed to ASK | Let the agent ask a person before changing files; the three-state permission model |
| v0.05 | Streaming output | `call_llm` becomes streaming + chunk assembly + typewriter effect | Why streaming; the `Accept-Encoding: identity` pitfall |
| v0.06 | Concurrent tool_calls | `ThreadPoolExecutor` runs several tool_calls of one round concurrently | The concurrency model for several tools in one round |
| v0.07 | System prompt engineering | The system prompt grows from one line to a full specification | The prompt is configuration |
| v0.08 | Completing file operations | `list_dir`/`edit_file` (exact replacement)/`grep` | Exact edits instead of whole-file rewrites |
| v0.09 | Permission system upgrade | Two-dimensional permissions (tool_name, pattern) + distinguishing once/always replies + fnmatch wildcard matching | From one dimension to two; command pattern granularity |
| v0.10 | Shell execution | `run_shell` tool + subprocess timeout + output truncation + two-dimensional command pattern permissions | Run tests/scripts; strict shell permissions |
| v0.11 | Context architecture | `AgentState` (state independent of messages) + `ContextManager` (single entry before LLM calls) | Agent State ≠ LLM Context; context building decoupled from the loop |
| v0.12 | Budget and trimming | Token estimation + Context Budget + atomic trimming by round | Context is a limited resource; over the limit, delete low-value information first instead of crashing |
| v0.13 | Context compaction | LLM summary of old history + Structured State anchor + larger `MAX_ITERATIONS` + Context Observability | Compaction without memory loss; State is the anchor and the Summary may be lossy; the process is observable |
| v0.14 | Plan guidance | Planning mode guidance | Separating planning from execution |
| ... | ... | ... (continuous iteration, rows added as needed) | ... |

> Slicing principle: each version introduces only one new concept, keeping the code difference on the order of "one file or one new module", so that `git diff v0.(X-1)..v0.X` is readable.

## 3. Directory Structure

Reuse the existing three-level `docs/` structure and add a `tutorials/` subdirectory under it. Code stays in `src/` and is always at the latest version.

```
mini_agent/
├── AGENTS.md                # Runtime hard constraints and condensed architecture index
├── CHANGELOG.md             # New: one Added/Changed/Why section per version
├── README.md                # Updated: adds a "learning path" section
├── pyproject.toml           # version follows the latest tag
├── src/mini_agent/          # Code (main is always the latest version)
├── tests/
├── examples/
└── docs/
    ├── README.txt           # Updated: adds a tutorials/ description
    ├── governance/          # Unchanged
    ├── plans/               # Unchanged (this plan document lives here)
    ├── operation/           # Unchanged
    └── tutorials/          # Teaching documents: README navigates by stage, lessons sliced by version
        ├── README.md        # Learning path index
        ├── 01-minimal-loop.md
        ├── 02-first-tool.md
        ├── 03-file-tools.md
        ├── 04-permission-gate.md
        ├── 05-streaming.md
        ├── 06-concurrent-tool-calls.md
        ├── 07-system-prompt.md
        ├── 08-file-operations.md
        ├── 09-permission-upgrade.md
        ├── 10-shell-execution.md
        ├── 11-context-architecture.md
        ├── 12-token-budget-trimming.md
        ├── 13-context-compaction.md
        ├── 14-plan-guidance.md
        └── ... (continuous iteration, added as needed, still in this directory)
```

### 3.1 Responsibility Boundaries of Each Directory

| Directory | Audience | Nature of content | Update frequency |
|---|---|---|---|
| `docs/tutorials/` | Learners | Concept explanations + code diff walkthroughs + usage guides | One per version |
| `docs/governance/` | Maintainers | Constraints, rules, decision records | Occasionally |
| `docs/plans/` | Maintainers | Plans, task breakdowns (the directory of this file) | Occasionally |
| `docs/operation/` | Users | Runbook, usage guide | Follows code changes |
| `AGENTS.md` | Maintainers + AI | Runtime hard constraints and condensed index | Synced when constraints change |

## 4. Teaching Document Template

Each `docs/tutorials/0X-xxx.md` uses a uniform structure to reduce learners' cognitive load. File name: a two-digit number + a hyphenated topic, consistent with the `docs/plans/` convention.

```markdown
# Lesson X: {topic}

> Version v0.X | [Previous lesson](0Y-yyy.md) | [Next lesson](0Z-zzz.md)

## Lesson Goals
One sentence: what this version adds and what problem it solves.

## Prerequisites
- Read the previous lesson
- `git checkout v0.X` to switch to this version's code

## What Was Added or Changed
List the changed files + the output of `git diff --stat v0.(X-1)..v0.X`.

## Core Concepts
### {concept name}
Code snippet (key parts taken from src/) + explanation.
Prefer the real diff from `git diff v0.(X-1)..v0.X -- <file>`, so learners see "which lines were added".

## Why This Design
Record pitfalls/trade-offs. v0.05 explains "why not requests"; v0.04 explains "why three states, not two".

## Usage Guide
### Commands available in this version
List the commands this version can run (single task / interactive mode / tests).

### Typical examples for this version
3-5 runnable examples, each with a command + expected output.
Examples change with the version: v0.01 can only converse, v0.02+ can call tools, v0.04+ has permission interaction.

### Features unique to this version
Phenomena newly introduced in this version that are worth observing.
E.g.: v0.04's permission interaction `[once/always/reject]`; v0.05's streaming typewriter effect; v0.06's concurrent tool_calls log.

## Full Code for This Version
Point to the matching files under `src/mini_agent/`; do not paste large blocks of code.
```

### 4.1 Document Writing Conventions

- **Do not paste large blocks of complete code**; take only key snippets + point to file paths, so documents do not fall out of sync when code changes
- **Diffs first**: if `git diff` can explain it, use the diff instead of rewriting it
- **Each document readable on its own**: assume the reader just finished the previous lesson, but do not assume they remember this lesson's details
- **The usage guide is required**: each lesson gives runnable commands + expected output, so learners get feedback
- **Examples evolve with the version**: each version's typical examples should show the new capability of that version and not repeat what the previous version covered

## 5. "Usage Guide" Differences per Version

Each version's usage guide changes with the tool set and capabilities. The table lists the unique content each version's usage guide should include:

| Version | Unique usage guide content |
|---|---|
| v0.01 | Conversation only; the `You:` prompt in interactive mode; leave with `exit`/`quit`; no tools to call |
| v0.02 | Call `calculate`; observe `role=tool` message feedback; try `"calculate 3+5*2"` |
| v0.03 | Call `read_file`/`write_file`; the `"path\ncontent"` argument format of `write_file`; try `"read examples/input.txt and summarize"` |
| v0.04 | `write_file` triggers a permission prompt; explain the three options `once`/`always`/`reject`; observe how the LLM reacts after a refusal |
| v0.05 | The streaming typewriter effect (watch text appear word by word in the terminal); compare with v0.04's "whole block output" |
| v0.06 | Have the model send several tool_calls at once (for example, `read_file` ×2 at the same time); observe the concurrent execution log |
| v0.07 | Compare how the v0.06 vs v0.07 system prompt changes the LLM's behavior; try a long task |
| v0.08 | `edit_file` exact replacement examples; `grep` search examples; `list_dir` to list a directory |
| v0.09 | Observe two-dimensional permissions: asking by command pattern; after approving `git *`, similar commands skip the question; compare with v0.04's one-dimensional permissions |
| v0.10 | `run_shell` runs `python tests/test_tools.py`; observe two-dimensional command pattern permissions; try "run the tests" |
| v0.11 | Compare with v0.10: the loop no longer assembles messages directly; demonstrate "the same State building different Contexts" |
| v0.12 | Build a long task to observe the budget check and trimming log; verify that the agent does not crash after trimming and the message protocol is valid |
| v0.13 | Verify on a long task that the original task can continue after repeated compaction; observe the summary and Structured State injection |
| v0.14 | Plan mode guidance examples; observe the separation of planning and execution |

### 5.1 Division of Work With `docs/operation/manual.md`

- `docs/operation/manual.md`: the complete manual for the **latest version**, not sliced by version, updated each time a version is completed. It covers all currently available tools, configuration, permission interaction, tests, and FAQ.
- The "Usage Guide" of a teaching document: covers only how to use **this version**; it is a "learner's manual" that follows the version. It does not repeat all the details of manual.md but tells learners "for the full usage, see manual.md".

## 6. Contents of `docs/tutorials/README.md`

The tutorial path index gives learners an entry point. All lesson files go directly in the `docs/tutorials/` root, with no stage subdirectories; the README is responsible for dividing the version lessons into clear learning stages:

```markdown
# Learning Path

## Start Here
Describe the full learning path, the Mini Agent milestone, and how to find features.

## Stage 1: Understand the Agent Loop
v0.01

## Stage 2: Tools and Safety
v0.02 → v0.04

## Stage 3: Mini Agent Milestone
v0.05 → v0.10

## Stage 4: Context Management
v0.11 → v0.13

## Stage 5: Advanced Capabilities (planned)
v0.14 and later

## Environment Setup (one time)
Keep the Python, configuration, and install instructions.

## Versions and Git Tags
Explain how to check out versions and use git diff to view the evolution.

## Full Manual
docs/operation/manual.md — the full usage of the latest version.
```

## 7. CHANGELOG.md Format

```markdown
# Changelog

## [v0.01] - Minimal agent loop
### Added
- `src/mini_agent/agent.py`: call_llm (non-streaming) + agent_loop
- `src/mini_agent/__main__.py`: CLI entry
- `src/mini_agent/config.py`: BASE_URL/API_KEY/MODEL/MAX_ITERATIONS
### Why
- Start from the smallest usable conversation loop and first explain "what an agent loop is".

## [v0.02] - First tool
...
```

One section per version, in three parts: Added/Changed/Why. The Why part records "why this version adds this", echoing the "Why This Design" of the teaching document but shorter.

## 8. Git Operation Checklist

### 8.1 Initialization: Reset main to v0.01

> Decision confirmed: reset main to v0.01, losing the existing 4 commits.

```bash
# 1. Back up the existing code (in case it is needed for reference)
git branch backup-pre-teaching

# 2. Create a new main with no history
git checkout --orphan main-new
git rm -rf .

# 3. Add the v0.01 code + documents (see section 9)
#    Only: agent.py (non-streaming version) / __main__.py / config.py / __init__.py
#    + pyproject.toml + README.md + AGENTS.md (condensed version)
#    + docs/tutorials/01-minimal-loop.md + docs/tutorials/README.md
#    + CHANGELOG.md + .gitignore

git add -A
git commit -m "v0.01: minimal agent loop"
git tag -a v0.01 -m "v0.01: minimal agent loop"

# 4. Replace main
git branch -D main
git branch -m main-new main
```

### 8.2 Add Version by Version

```bash
# 1. Develop on main up to this version's state
# 2. Update CHANGELOG.md and docs/tutorials/0X-xxx.md; sync the AGENTS.md runtime constraints when needed
# 3. Run the tests
$env:PYTHONPATH="src"; python tests/test_tools.py
# 4. Commit + tag
git add -A
git commit -m "v0.X: {topic}"
git tag -a v0.X -m "v0.X: {topic}"
```

### 8.3 How Learners Use It

```bash
git clone <repo>
cd mini_agent
git tag                    # see all versions
git checkout v0.01          # switch to the first version
# read docs/tutorials/01-minimal-loop.md
# run: $env:PYTHONPATH="src"; python -m mini_agent "Hello"
git checkout v0.02          # look at the diff, read 02-first-tool.md
# ...on to the latest version
```

## 9. v0.01 Code Inventory

v0.01 keeps only 4 source files and removes all tool/permission-related code.

### 9.1 `src/mini_agent/agent.py` (non-streaming version, about 30 lines)

```python
"""Minimal Agent Loop: call the LLM -> reply -> call again, until finished or the limit."""

import http.client
import json
from urllib.parse import urlparse

from mini_agent.config import BASE_URL, API_KEY, MODEL, MAX_ITERATIONS


def call_llm(messages):
    """Call the LLM without streaming and return the assistant message dict."""
    p = urlparse(BASE_URL)
    conn = http.client.HTTPConnection(p.hostname, p.port or 80, timeout=120)
    body = json.dumps(
        {"model": MODEL, "messages": messages},
        ensure_ascii=False,
    ).encode()
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "Accept-Encoding": "identity",
    }
    conn.request("POST", f"{p.path.rstrip('/')}/chat/completions", body=body, headers=headers)
    resp = conn.getresponse()
    data = json.loads(resp.read().decode("utf-8"))
    conn.close()
    return data["choices"][0]["message"]


def agent_loop(messages):
    """Loop: call the LLM -> print the reply -> stop when there are no tool_calls."""
    for i in range(MAX_ITERATIONS):
        msg = call_llm(messages)
        messages.append(msg)
        print(f"\n=== [{i+1}] LLM reply ===")
        print(msg.get("content", ""))
        if not msg.get("tool_calls"):
            return msg.get("content", "")
    return "Maximum iterations reached"
```

> The v0.01 `call_llm` has no `tools` argument, does not stream, and does not handle tool_calls.
> `agent_loop` runs no tools and only checks whether `tool_calls` is empty to stop. The loop concept of the first lesson is at its cleanest.

### 9.2 Other Files

- `__main__.py`: basically the same as the existing version; the system prompt stays one line, `"You are an assistant."`
- `config.py`: the same as the existing version
- `__init__.py`: empty file

### 9.3 Deleted Files (not in v0.01)

- `src/mini_agent/permission.py` (added only in v0.04)
- `src/mini_agent/tools/` (the whole directory, added only in v0.02)
- `tests/test_tools.py` (tools exist to test only from v0.02; v0.01 can add a `test_loop.py` to test the import chain)

## 10. Code Difference Points of Later Versions

- **v0.02**: adds `tools/base.py` + `calc.py` + `__init__.py`; `agent.py` adds the `tools` argument + tool_calls execution + `role=tool` feedback; the `__main__.py` system prompt changes to "complete tasks by calling tools"; adds `tests/test_tools.py`
- **v0.03**: adds `tools/file.py`; registered in `tools/__init__.py`; tests add read_file/write_file
- **v0.04**: adds `permission.py`; the Executor in `tools/base.py` adds a gate; `tools/__init__.py` passes the gate; write_file changes to ASK
- **v0.05**: `call_llm` in `agent.py` becomes streaming, with chunks accumulating content + tool_calls; the document focuses on the `Accept-Encoding: identity` pitfall
- **v0.06**: tool_calls execution in `agent.py` changes to `ThreadPoolExecutor`
- **v0.07**: the `__main__.py` system prompt expands into a full specification
- **v0.08**: adds `tools/file.py`; registered in `tools/__init__.py`; tests add read_file/write_file
- **v0.09**: `permission.py` upgrade (two-dimensional matching in `check()` + `fnmatch` + `approve()` stores the pattern); `PermissionGate.guard()` in `tools/base.py` extracts the pattern from args; `PERMISSION_RULES` supports a dict format
- **v0.10**: adds `tools/shell.py` (`run_shell` + `subprocess` timeout + output truncation); registered in `tools/__init__.py`; `permission.py` adds two-dimensional `run_shell` permission rules + the `_from_config` ordering fix (`*` first); `prompt.py` updates the capability description
- **v0.11**: adds `state.py` (AgentState) + `context.py` (ContextManager single entry); `agent.py` calls the LLM through `prepare_messages()`; the Executor in `tools/base.py` adds a result callback that updates State. A pure refactoring; behavior matches v0.10
- **v0.12**: `context.py` adds `count_tokens` (the `len//3` heuristic) + `ContextBudget` (ratio configuration) + `TrimPolicy` (atomic trimming by round, no orphan tool results); `config.py` adds `CONTEXT_WINDOW`
- **v0.13**: `context.py` adds `compact()` (LLM summary + Structured State injection + degradation to trimming on failure); `config.py` raises `MAX_ITERATIONS`
- **v0.14**: `prompt.py` adds plan guidance; `__main__.py` adds a plan mode entry
- **v0.15+**: added as needed. For the detailed Context Management plan, see `context-management-plan.md`

## 11. AGENTS.md Update Points

During implementation, AGENTS.md must be synced:
- The "Roadmap" section keeps the version slicing table and adds the tutorial stage division, checking off each completed version
- The "Current Architecture" section follows the latest version
- The "Running" section is unchanged
- The "Key Constraints" section is unchanged (these constraints hold across versions)
- Add a line at the top: "This repository is a multi-stage teaching repository; learn in the order of git tags v0.01→v0.X (continuous iteration); see `docs/tutorials/`"

## 12. Acceptance Criteria

After the plan is implemented, it should satisfy:
- [ ] `git tag` lists tags in order, increasing from v0.01, with no fixed limit
- [ ] After `git checkout v0.X`, the code runs (`python -m mini_agent "Hello"` raises no error)
- [ ] `docs/tutorials/` has as many documents as implemented versions + 1 README index
- [ ] Every teaching document has a "Usage Guide" section whose commands run
- [ ] `CHANGELOG.md` has one section per implemented version, each with Added/Changed/Why
- [ ] `git diff v0.(X-1)..v0.X --stat` for each version is on the order of "one or two files"
- [ ] The version slicing table stays consistent with the tutorial index and CHANGELOG

## 13. Suggested Execution Order

1. **Implement the full v0.01 first**: reset main + v0.01 code + lesson 01 document + CHANGELOG + tag
2. **v0.02 → v0.06**: reuse the existing code in the backup branch, recommit in version order + write documents (the work is in the documents)
3. **v0.07 → v0.14**: new code is needed (expanded system prompt, list_dir/edit_file/grep, permission upgrade, run_shell, three context management versions, plan guidance), a larger amount of work
4. **v0.15+**: continuous iteration, adding new features as needed
5. **After each version**: run the tests, update the plans/tutorial index and CHANGELOG; update AGENTS.md only when constraints change, then tag

> The code for v0.02-v0.06 already exists in the backup-pre-teaching branch; implementing them is mainly about splitting the commit rhythm + writing documents.
> v0.07+ needs new code and is a larger amount of work.

## 14. Risks and Trade-Offs

- **Resetting main loses 4 commits**: backed up in the `backup-pre-teaching` branch for reference when needed
- **The v0.01 code differs a lot from the existing code**: this is intentional; the first lesson must be minimal. The existing code is added back gradually in v0.02-v0.06
- **Teaching document maintenance cost**: when code changes, documents must follow. Using "point to files + diff" instead of "paste complete code" reduces sync cost
- **API_KEY hard-coded into the teaching repository**: if the teaching repository is public, change the API_KEY in `config.py` to the placeholder `"sk-YOUR_KEY_HERE"`, and explain in lesson 01 that learners must fill it in themselves

# Lesson 7: System prompt engineering

> Version v0.07 | [Previous lesson](06-concurrent-tool-calls.md) | [Next lesson](08-file-operations.md)

> Code snapshot: `v0.07` · Adjacent diff: `v0.06.1..v0.07` · Shell: Bash/zsh
>
> Requirements: Python 3.10+. The `pyproject.toml` at this tag still says 3.9, but the source already uses 3.10 syntax.

## Lesson Goals

The previous version used a one-line system prompt (the fixed working instructions given to the model). So the model might not know the current directory, the platform, or how it should work.
This version moves the prompt into `prompt.py` and assembles identity, rules, and environment information in layers, so the model knows what to do and where it runs.

## Prerequisites

- Read [Lesson 6](06-concurrent-tool-calls.md) and understand concurrent tool_calls
- `git checkout v0.07` to switch to this version's code

## What Was Added or Changed

```
 src/mini_agent/
 ├── prompt.py          # New: build_system_prompt + header + environment + _CORE_RULES
 └── __main__.py        # Changed: messages[0] now calls build_system_prompt()
tests/
 └── test_prompt.py     # New: smoke test
```

> This version adds one module and changes one place in the entry point. `agent.py` is untouched — the core loop still only knows the `messages` list and is unaware of how the prompt is built.

## Core Concepts

### Why a one-line system prompt is not enough

The v0.06 system prompt looks like this (`__main__.py:11`):

```python
messages = [{"role": "system", "content": "You are an assistant that completes tasks by calling tools."}]
```

This prompt works, but it has three problems on real tasks:

1. **The model does not know the environment**: it can only guess the working directory, platform, and date, so it may choose the wrong relative path or platform command.
2. **Unstable behavior**: the model may be verbose, add emoji, repeat tool results, or summarize "what I did" unprompted. In multi-round conversations, this content takes up context.
3. **No way to tell agent identities apart**: later, multiple agents / sub-agents have different responsibilities; one string cannot say "you are build or explore".

### Layered assembly: borrowing from OpenCode and trimming

Solving these problems does not mean piling everything into one big prompt. This version follows OpenCode's layered approach and trims it for teaching.
OpenCode has four layers: `header` (identity), `provider` (per-model adaptation), `environment`, and `custom` (user rules). mini_agent keeps the three most needed for now:

| OpenCode layer | mini_agent equivalent | Done? | Reason |
|---|---|---|---|
| `header()` identity layer | `header(agent_name)` | ✅ | Reserves a parameter for multiple agents; only `build` for now |
| `provider()` behavior layer | `_CORE_RULES` static text | ✅ | A single model does not need per-provider templates |
| `environment()` environment layer | `environment()` generated dynamically | ✅ | Pure standard library, best return on effort |
| `custom()` user rules | — | ❌ | Left until after v0.08 completes the file tools |

### The three-layer structure (`src/mini_agent/prompt.py`)

`build_system_prompt(agent_name="build")` returns a string. It separates the three parts with `\n\n`, so each part is responsible for one kind of information:

```python
def build_system_prompt(agent_name: str = "build") -> str:
    return "\n\n".join([
        header(agent_name),      # Identity: you are build / explore / plan ...
        _CORE_RULES,              # Behavior rules (shared by all agents)
        environment(),            # Dynamic environment information
    ])
```

#### Layer 1: `header(agent_name)` — identity

```python
def header(agent_name: str = "build") -> str:
    agents = {
        "build": (
            "You are mini_agent, a coding agent. "
            "You complete programming tasks by calling tools: for now you can read, write, and edit files and do math, "
            "and later you will be able to run commands and tests. "
            "Your goal is to complete basic programming tasks on your own, not just to chat."
        ),
        # Reserved, not implemented in v0.07:
        # "explore": "You are mini_agent's explore sub-agent and only explore the codebase read-only...",
        # "plan": "You are mini_agent's plan agent and only plan, never execute...",
    }
    return agents.get(agent_name, agents["build"])
```

This layer first answers "who the model is and what it can do":

- **dict + fallback**: an unknown `agent_name` always falls back to `build`.
- **A specific identity**: it states clearly that the agent can currently only read, write, and edit files and calculate, instead of saying vaguely "you are an assistant".
- **Reserved for multiple agents**: to add explore/plan later, add one entry to the dict and pass the matching `agent_name`.

#### Layer 2: `_CORE_RULES` — behavior rules

Once the identity is clear, all agents also need to follow the same set of rules. `_CORE_RULES` is static text in four sections:

| Section | Key rules |
|---|---|
| `# Tone and style` | Concise, no emoji, do not repeat tool output, do not summarize changes unprompted |
| `# Professional objectivity` | Technical accuracy first, do not cater to assumptions, investigate when unsure, correct honestly |
| `# Tool usage` | Prefer tools, complete and valid arguments, tool_calls may run concurrently |
| `# Safety` | The permission gate is expected behavior, do not guess URLs, tool failures raise exceptions directly |

> The rules are wrapped in `<rules>...</rules>`. For GLM-series models, an explicit tag like this says "these are rules you must follow" more clearly than Markdown headings alone.

#### Layer 3: `environment()` — dynamic environment

```python
def environment() -> str:
    cwd = os.getcwd()
    is_git = _detect_git(cwd)
    return "\n".join([
        "<env>",
        f"  Working directory: {cwd}",
        f"  Is directory a git repo: {'yes' if is_git else 'no'}",
        f"  Platform: {sys.platform}",
        f"  Today's date: {date.today().isoformat()}",
        "</env>",
    ])
```

The model also needs to know where it is running. `environment()` reads four items with the standard library:

| Field | How it is obtained | Purpose |
|---|---|---|
| `Working directory` | `os.getcwd()` | Base for resolving relative paths |
| `Is directory a git repo` | `_detect_git(cwd)` | Whether git operations are possible |
| `Platform` | `sys.platform` | Choose the right platform command (`ls` vs `dir`) |
| `Today's date` | `date.today().isoformat()` | Understand time-sensitive context |

Sample output:
```
<env>
  Working directory: E:\claude\agent_projects\mini_agent
  Is directory a git repo: yes
  Platform: win32
  Today's date: 2026-08-27
</env>
```

### Implementation choice for `_detect_git`

```python
def _detect_git(cwd: str) -> bool:
    p = os.path.abspath(cwd)
    while True:
        if os.path.isdir(os.path.join(p, ".git")):
            return True
        parent = os.path.dirname(p)
        if parent == p:
            return False
        p = parent
```

It only needs to know whether the current directory or one of its parents has `.git`. So it walks the directories instead of calling `subprocess.run(["git", ...])`:

- **No external dependency**: it does not need the git executable, which follows mini_agent's self-contained convention.
- **No subprocess**: walking the directories is enough for this check.
- **Limitation**: worktrees and submodules may be missed; the current teaching scenario does not handle them, and they can be upgraded later if needed.

## Why This Design

### Why `agent.py` is untouched

When the prompt gets more complex, the core loop should not take on the assembly work. `call_llm` / `agent_loop` still only receive the `messages` list and do not know how the system prompt was generated.
Assembling the prompt is the job of the entry layer (`__main__.py`), so `agent.py` does not need to change.

### Why it is called once at the entry instead of every round

Within one session, the working directory, platform, and date usually do not change. So `__main__.py` calls `build_system_prompt()` once at startup, writes it into `messages[0]`, and reuses it every round.

```python
# __main__.py
messages = [{"role": "system", "content": build_system_prompt()}]
```

### Why not copy OpenCode's `header()` identity disguise

OpenCode's `header()` disguises the identity for Anthropic models so that Claude believes it is not Claude. This is a workaround for a specific model.
mini_agent connects to the GLM series and does not need it, so it is not copied here.

### Why `core_rules` were written in Chinese at this tag

- The connected `EB-GLM-5.2` is a Chinese model, so Chinese instructions were usually easier for it to follow.
- The teaching repository was then aimed at Chinese learners, so the prompt was meant to be read directly.
- The field names in `environment()` stay in English, such as `Working directory`. Structured labels are more stable in English, and the model recognizes them more consistently.

## Usage Guide

### Commands available in this version

```bash
# Show the full system prompt
PYTHONPATH=src python -c "from mini_agent.prompt import build_system_prompt; print(build_system_prompt())"

# Run the smoke test
PYTHONPATH=src python tests/test_prompt.py

# Run the agent for real and observe the behavior change
PYTHONPATH=src python -m mini_agent "Hello, briefly introduce yourself"
```

### Typical examples for this version

**Example 1: view the assembled system prompt**
```bash
PYTHONPATH=src python -c "from mini_agent.prompt import build_system_prompt; print(build_system_prompt())"
```
Expected output: three parts in order — the identity description, the `<rules>` behavior rules, and the `<env>` environment information.

**Example 2: compare the model's self-introduction in v0.06 vs v0.07**
```bash
# v0.06: one-line prompt; the model may be verbose or add emoji
git checkout v0.06
PYTHONPATH=src python -m mini_agent "Hello, briefly introduce yourself"

# v0.07: structured prompt; the model is concise, without emoji, in Markdown
git checkout v0.07
PYTHONPATH=src python -m mini_agent "Hello, briefly introduce yourself"
```
Expected: the v0.07 reply is usually more concise and structured, has no emoji, and says it is mini_agent. Model output can still vary.

**Example 3: environment information helps resolve paths**
```bash
PYTHONPATH=src python -m mini_agent "read examples/input.txt and tell me its contents"
```
Expected: the model gets the working directory from `<env>`, so it can resolve the relative path correctly instead of guessing.

### Features unique to this version

- **Environment awareness**: the model receives the working directory, platform, date, and git status and does not need to guess.
- **Behavior constraints**: the rules require concise replies without emoji, no repeating of tool output, and no unprompted summaries.
- **Reserved for multiple agents**: `header(agent_name)` already takes a parameter; adding explore/plan later only extends the dict.

## Hands-On Verification

1. **Run the smoke test**:
   ```bash
   PYTHONPATH=src python tests/test_prompt.py
   ```
   Expected: 4 PASS lines (assembly succeeds / header build / unknown falls back / environment fields).

2. **View the system prompt**:
   ```bash
   PYTHONPATH=src python -c "from mini_agent.prompt import build_system_prompt; print(build_system_prompt())"
   ```
   Expected: the output contains the three parts `mini_agent`, `<rules>`, and `<env>`.

3. **Compare v0.06 vs v0.07 behavior**:
   ```bash
   git checkout v0.06
   PYTHONPATH=src python -m mini_agent "Hello"
   # v0.06: may be verbose, add emoji, and not state its identity

   git checkout v0.07
   PYTHONPATH=src python -m mini_agent "Hello"
   # v0.07: concise, Markdown, states its mini_agent identity
   ```

## Full Code for This Version

- [`src/mini_agent/prompt.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.07/src/mini_agent/prompt.py) — layered system prompt assembly
- [`src/mini_agent/__main__.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.07/src/mini_agent/__main__.py) — the entry calls `build_system_prompt()`
- [`tests/test_prompt.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.07/tests/test_prompt.py) — smoke test

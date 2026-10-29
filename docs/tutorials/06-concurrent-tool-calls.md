# Lesson 6: Concurrent tool_calls

> Version v0.06 | [Previous lesson](05-streaming.md) | [Next lesson](07-system-prompt.md)

> Code snapshot: `v0.06` · Adjacent diff: `v0.05..v0.06` · Shell: Bash/zsh
>
> Requirements: Python 3.10+. The `pyproject.toml` at `v0.06`/`v0.06.1` still says 3.9, but the source already uses 3.10 syntax.

## Lesson Goals

When the previous version received several tool calls in the same round, it ran them one after another. As long as one tool was waiting for a file or the network, the later calls had to wait too.
This version uses `ThreadPoolExecutor` to run independent tool_calls at the same time, which shortens the wait for the round.

## Prerequisites

- Read [Lesson 5](05-streaming.md) and understand the streaming call_llm
- `git checkout v0.06` to switch to this version's code

## What Was Added or Changed

```
 src/mini_agent/
 └── agent.py            # Changed: tool_calls in agent_loop run concurrently with ThreadPoolExecutor instead of a serial for loop
```

> This version changes only `agent.py`, and only the part of agent_loop that runs tool_calls.

## Core Concepts

### Serial vs concurrent

v0.05 runs serially (the next call starts only after the previous one finishes). The N tool_calls of one round run one by one in a `for` loop, so total time = Σ(time of each tool).

```python
for tc in msg["tool_calls"]:
    result = executor.execute(name, args)   # The 2nd starts only after the 1st finishes
```

v0.06 runs them concurrently (several calls in progress at the same time). `ThreadPoolExecutor` puts the N tool_calls into a thread pool, so total time is about the time of the slowest call.

```python
with ThreadPoolExecutor(max_workers=len(tool_calls)) as pool:
    results = list(pool.map(_run, tool_calls))
```

### When the LLM sends several tool_calls

The problem only appears when the model returns several `tool_calls` at once. The LLM can make several calls in one reply; they are usually independent, for example:

```
User: "Read a.txt and b.txt at the same time"

LLM reply (2 tool_calls in one round):
  tool_calls[0]: read_file({"path": "a.txt"})
  tool_calls[1]: read_file({"path": "b.txt"})
```

These two read_file calls do not depend on each other; reading a.txt does not need the result of b.txt. So running them serially wastes waiting time, and running them concurrently lets them finish together.

### ThreadPoolExecutor implementation (`src/mini_agent/agent.py:95`)

```python
tool_calls = msg["tool_calls"]

def _run(tc):
    name = tc["function"]["name"]
    args = json.loads(tc["function"]["arguments"])
    result = executor.execute(name, args)
    print(f"  Ran {name} -> {result}")
    return tc["id"], str(result)

with ThreadPoolExecutor(max_workers=len(tool_calls)) as pool:
    results = list(pool.map(_run, tool_calls))

for tool_call_id, content in results:
    messages.append({
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": content,
    })
```

Points to note in the implementation:
1. **`max_workers=len(tool_calls)`**: open as many threads as there are calls in this round.
2. **`pool.map`**: submission and results both keep the original order, so `results[0]` always matches `tool_calls[0]`.
3. **The `with` statement**: leaving the block calls `join()` automatically, that is, it continues only after all threads finish.
4. **Feedback order**: results are appended as `role=tool` messages in the original order, so the mapping the model receives does not change.

## Why This Design

### Why threads instead of coroutines

`read_file`/`write_file` spend most of their time waiting on IO (disk reads and writes), and threads can run one call while another waits.
Coroutines (asyncio) can also give concurrency, but that would require the whole call chain from `call_llm` to `executor.execute` to become async, which is beyond this lesson.
So a thread pool is chosen here: a small change that is enough to solve the current waiting problem.

### Why max_workers = len(tool_calls)

A round usually has only 2–5 tool_calls, so creating one thread per call is enough.
The agent loop still runs round by round and enters the next round only after the current one ends, so there is no need to reuse a thread pool across rounds.

### Why pool.map instead of submit + as_completed

`pool.map` guarantees **that results are in the same order as the inputs**. `as_completed` returns results in completion order, which may change the order.
When feeding back, the LLM's tool_calls[0] must match the first tool message, so `map` is used here.

### Why the permission gate's _ask_lock matters here

The v0.04 `PermissionGate` already prepared `self._ask_lock = threading.Lock()`.
If two write_file calls trigger ASK at the same time, without this lock the two prompts could interleave. The lock lets only one ASK interaction use the terminal at a time, so concurrency in this round does not break permission confirmation.

## Usage Guide

### Commands available in this version

```bash
# Let the LLM call several tools at once (observe concurrency)
PYTHONPATH=src python -m mini_agent "read examples/input.txt and examples/input2.txt at the same time"

# Run the smoke test
PYTHONPATH=src python tests/test_tools.py
```

### Typical examples for this version

**Example 1: read two files concurrently**
```bash
PYTHONPATH=src python -m mini_agent "read examples/input.txt and examples/input2.txt at the same time and tell me the contents of both files"
```
Expected output:
```
=== [1] LLM reply ===
  Decided call: read_file({"path": "examples/input.txt"})
  Decided call: read_file({"path": "examples/input2.txt"})
[Executor] Running Tool: read_file
[Executor] Arguments: {'path': 'examples/input.txt'}
[Executor] Running Tool: read_file
[Executor] Arguments: {'path': 'examples/input2.txt'}
  Ran read_file -> 3 + 5 * 2
  Ran read_file -> 3 + 5 * 3
```
Note: the two `[Executor] Running Tool: read_file` lines appear almost at the same time, which shows the calls are running concurrently.
In the serial v0.05, the second read_file starts only after the first one prints its result.

**Example 2: concurrent calculation + read**
```bash
PYTHONPATH=src python -m mini_agent "calculate 100*200 and read examples/input.txt at the same time"
```
Expected: the LLM sends two tool_calls at once, `calculate` + `read_file`, and the thread pool runs them concurrently.

**Example 3: compare serial vs concurrent**
```bash
# v0.05 (serial): the two read_file calls run one after the other
git checkout v0.05
PYTHONPATH=src python -m mini_agent "read examples/input.txt and examples/input2.txt at the same time"

# v0.06 (concurrent): the two read_file calls run at the same time
git checkout v0.06
PYTHONPATH=src python -m mini_agent "read examples/input.txt and examples/input2.txt at the same time"
```

### Features unique to this version

- **Concurrent execution logs**: the `[Executor]` logs of several tools may interleave because they run at the same time.
- **Results fed back in the original order**: although execution is concurrent, `pool.map` still keeps results in the original tool_calls order.
- **The permission lock takes effect**: when several write_file calls trigger ASK concurrently, the lock makes the prompts appear one by one.

## Hands-On Verification

1. **Run the smoke test**:
   ```bash
   PYTHONPATH=src python tests/test_tools.py
   ```
   Expected: 8 PASS lines.

2. **Read two files concurrently**:
   ```bash
   PYTHONPATH=src python -m mini_agent "read examples/input.txt and examples/input2.txt at the same time"
   ```
   Expected: the Executor logs of the two read_file calls appear almost at the same time, and the results are fed back together.

3. **Compare v0.05 vs v0.06**:
   ```bash
   git checkout v0.05
   PYTHONPATH=src python -m mini_agent "read examples/input.txt and examples/input2.txt at the same time"
   # Serial: the second read_file starts only after the first one prints its result

   git checkout v0.06
   PYTHONPATH=src python -m mini_agent "read examples/input.txt and examples/input2.txt at the same time"
   # Concurrent: the Executor logs of the two read_file calls appear almost at the same time
   ```

## Full Code for This Version

- [`src/mini_agent/agent.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.06/src/mini_agent/agent.py) — concurrent tool_calls execution in agent_loop

---

## v0.06.1 Revision: Multi-Round Context State Contract

> Version v0.06.1 | A patch of v0.06 that changes no features and only fixes a hidden multi-round context bug.

> Code snapshot: `v0.06.1` · Adjacent diff: `v0.06..v0.06.1` · Shell: Bash/zsh

```bash
git checkout v0.06.1
git diff --stat v0.06..v0.06.1
git diff v0.06..v0.06.1 -- src/mini_agent/agent.py src/mini_agent/__main__.py
```

### The problem found

The previous version worked, but a caller could not easily see how `agent_loop` changes the `messages` passed in. It appends assistant / tool messages through a **mutable list side effect**, and the rule was hidden in the source and a vague docstring.
This made it hard to tell whether the list was currently complete across multi-round calls.

This caused two real problems:

1. **The two paths in `__main__.py` diverged**: the argv branch and the interactive loop branch maintained messages differently. Although the argv branch actually got the complete state through the side effect, it was hard to confirm from the code what the list looked like after the call, and later maintenance could easily go wrong.

2. **The iteration limit contract was not documented**: when `MAX_ITERATIONS` is reached, all tool results of the last round have been fed back before the function returns `"Maximum iterations reached"`. This order was not part of the contract before.

### The fix (option A: keep the signature)

This version chooses **not to change the `agent_loop` signature** (it keeps the single-argument `agent_loop(messages)`), because:
- `test_agent_loop_signature` in `tests/test_loop.py` asserts that the signature has only `messages`; changing the signature would break the existing test.
- The real problem is not the signature but an unclear contract and diverging caller paths.

Specific changes:

**`src/mini_agent/agent.py` — make the `agent_loop` docstring an explicit contract**

```python
def agent_loop(messages):
    """Loop: call the LLM -> run and feed back tool_calls if any -> otherwise stop.

    [messages contract] This function appends to the messages list passed in
    as a side effect. Callers should reuse the same list object across rounds
    and must not rebuild it. Each round appends:
      1. the assistant message (with content and/or tool_calls)
      2. if there are tool_calls: one role=tool result message for each
    The return value is the content string of the final assistant reply
    (used only for printing); the real context state is already written to
    messages, so callers do not need to append the assistant reply manually.

    Every assistant message with tool_calls first gets all its matching
    role=tool result messages appended, before the next round starts or the
    function returns because of MAX_ITERATIONS.
    """
```

**`src/mini_agent/__main__.py` — unify the argv and interactive loop paths**

Before: the argv branch had its own logic and the interactive loop had another, a risk of inconsistent behavior between the two paths.

After: the argv branch and the interactive loop follow the same "append user → agent_loop → reuse messages" path, and a comment at the top of the file states the messages state contract:

```python
# The messages list is reused across rounds: agent_loop appends
# assistant / tool messages to it as a side effect, so callers do not
# need to append the assistant reply manually.
# See the docstring contract of agent.agent_loop.
messages = [{"role": "system", "content": "You are an assistant that completes tasks by calling tools."}]

# Command-line first task (optional): follows the same path as the
# interactive loop, so messages state is complete after the argv branch
# and follow-up questions keep their context.
if len(sys.argv) > 1:
    messages.append({"role": "user", "content": sys.argv[1]})
    reply = agent_loop(messages)
    print(reply)
```

### Why a patch and not a minor version

- No feature is added and no behavior changes; the argv branch already kept complete state through the side effect.
- The change only writes down rules that were implicit, to reduce misunderstandings during maintenance.
- No tests need to be added, because writing down the contract does not change observable results.

### Remaining issues (not fixed in this version)

1. **Meaning of the `agent_loop` return value**: the content string returned now is only used for printing, and the real multi-round state is kept in the messages list. This two-channel design stays for now, because changing the signature would affect existing callers.

### Files changed in this version

```
src/mini_agent/
├── agent.py        # Changed: agent_loop docstring becomes a contract
└── __main__.py     # Changed: unifies both paths, adds a messages contract comment
```

- [`src/mini_agent/agent.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.06.1/src/mini_agent/agent.py) — states the messages side-effect contract
- [`src/mini_agent/__main__.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.06.1/src/mini_agent/__main__.py) — unifies the argv and interactive loop paths

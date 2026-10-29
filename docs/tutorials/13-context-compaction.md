# Lesson 13: Context compaction (v0.13)

Previous: [Budget and trimming](12-token-budget-trimming.md) · [Tutorial overview](README.md) · Next: [Project instructions](14-project-instructions.md)

> Code snapshot: `v0.13` · Adjacent diff: `v0.12..v0.13` · Shell: Bash/zsh

> Requirements: Python 3.10+. The `pyproject.toml` of historical tags says Python 3.9, but the source already uses Python 3.10 syntax.

## Lesson Goals

The previous lesson let over-long requests still be sent, but to fit the budget it truncated tool output and then deleted the oldest complete rounds. The deleted content may contain approaches already tried and conclusions already confirmed.

This lesson adds context compaction: older complete rounds are given to an internal LLM request that writes a history summary, while the most recent rounds stay verbatim and the state recorded by the executor is put back into the request. After reading it, you should be able to explain why a summary may be lossy while `AgentState` must remain the source of execution facts.

At the end, this lesson also covers Context Observability, added by the v0.13.1 patch: you should be able to read the five token buckets of `ContextStats`, call `ContextManager.stats_snapshot()`, tell the `prepared`, `trimmed`, and `compacted` events apart, and configure the default terminal log and the `CONTEXT_OBSERVABILITY` switch; you should also understand that observer exceptions are isolated and do not affect the agent.

## v0.13.2: Task Boundary Isolation

Context compaction solves "the history is too long"; it does not automatically solve "the task has changed". In one CLI session, an ordinary follow-up input continues the current task by default; only `/new <task>` clears the old task and starts a new one, and `/reset`
clears the current task and waits for the next input. After a task finishes, the user's intent is not guessed from the `done` status either.

A task boundary clears all task-level facts in place: Todo, tool records, file changes, errors, verification evidence,
generation, FailureEvent, RecoveryAction, retry/fingerprint/recovery/repair budgets, and
checkpoints from later versions. History, the Historical Summary, the compaction cursor, and runtime notices are also
cleared; the system prompt, project instructions, and session-level permission approvals are kept. The synchronous CLI reads the next input only after the current tool batch has been fully
fed back, so it never creates orphan messages between a tool call and its tool result.

Structured State is re-rendered from the latest state every round and has a fixed character limit; the task anchor, current goal, and
status are kept first, and an over-long diagnostic history is truncated deterministically. It is a projection of task facts and does not change the local State.

## Problems in the Previous Version

In v0.12, `ContextManager.prepare_messages()` makes a copy of the full `history` and then calls `TrimPolicy.trim()`. It does not rewrite the full local history, but the copy sent to the model may no longer contain the early rounds.

This is safe for the protocol: an assistant message with `tool_calls` is kept or deleted together with all the tool results right after it. But it does not keep meaning. When a task is long enough, the model does not know which files were changed or which commands failed, and it easily repeats work.

This version does not try to keep the original text forever. Instead, it divides the work among three kinds of information: old rounds keep their gist through a summary, recent rounds keep their original text and tool call relationships, and `AgentState` keeps the facts produced by real tool results.

## Prerequisites and Version Checkout

Read Lessons 11 and 12 first, to understand the separation of `AgentState` from message history, the token budget, and what a complete round means. The following commands are for Bash/zsh:

```bash
git checkout v0.12
git diff --stat v0.12..v0.13
git diff v0.12..v0.13 -- src/mini_agent/context.py src/mini_agent/agent.py src/mini_agent/config.py src/mini_agent/config_example.py
git checkout v0.13
```

## New and Changed Files

First confirm the scope with the `git diff --stat` above. This lesson focuses only on the changes below that take part directly in the compaction flow.

| File | Change | Purpose |
|---|---|---|
| `src/mini_agent/context.py` | Extends `ContextManager` | Generates summaries, rebuilds the sent view, and falls back to the trimmed result on failure |
| `src/mini_agent/agent.py` | Extends `call_llm()`, adds `summarize_messages()` | Reuses the existing LLM channel for an internal, tool-free summary request |
| `src/mini_agent/config.py` | `MAX_ITERATIONS` goes from 10 to 50 | Gives long tasks more rounds to keep running |
| `src/mini_agent/config_example.py` | Syncs the default round count | Keeps the example configuration consistent |

## Version Change Map

Legend:

```text
[old] in previous version    [+] new in this version    [~] changed in this version
[C] main consumer            [B] boundary or degradation path of this version
```

The entry, data flow, and finish of v0.12 are as follows. `history` is the full local record; `trim()` returns a copy that can be sent.

```text
v0.12

[old] agent_loop
        |
        v
[old] ContextManager.prepare_messages()
        |
        v
[old] TrimPolicy.trim(history, budget) ---> [C] call_llm(messages)
        |                                       |
        +-- truncate tool content / delete -----+-> appended to history next round
            oldest complete rounds
```

v0.13 inserts compaction at the same entry. When the first view built exceeds the budget, it still first gets the degraded copy from `trim()`; only if `compact()` succeeds is the compacted view trimmed again. A summary exception, an empty string, or a non-string all take this existing degradation path.

```text
v0.13

[old] agent_loop -> [~] prepare_messages() -> [old] _build_messages()
                                           |          |
                                           |          +-- initial view within limit --> [old] trim() --> [C] call_llm()
                                           |
                                           +-- initial view over limit
                                                |
                                                +-> [old] trim(): get the degraded copy first
                                                |
                                                +-> [+] compact()
                                                     |-- [+] summarizer(prompt)
                                                     |     `-> [~] call_llm(tools=False,
                                                     |                      stream_output=False)
                                                     |
                                                     +-- success --> [+] State + Summary + Recent
                                                     |                -> [old] trim() -> [C] call_llm()
                                                     `-- [B] exception/empty/non-string --> the earlier degraded copy
```

`ContextManager` is the main control point here. The main loop still only calls `prepare_messages()`; it does not need to know the summary format and does not catch summary failures.

## Core Concepts and Data Structures

### 1. Compaction applies to the sent view, not the full history

The problem is that the original text cannot be sent forever, but all old information cannot simply be forgotten to shorten the request either. Intuitively, `history` is like the full archive, and the compacted messages are the working summary handed to the model next time.

`_split_rounds()` first puts the system message and the first user task into the protected prefix, then splits the remaining messages into rounds. An assistant message with tool calls and the consecutive tool results belong to the same round. This split guarantees that recent original text never leaves a tool message without its matching `tool_calls`.

After compaction succeeds, `_build_messages()` only reshapes the sent view:

```python
prefix, rounds = _split_rounds([dict(message) for message in self.history])
recent = rounds[-self.keep_rounds:] if self.keep_rounds else []
messages = prefix[:1] + [self._render_state()]
if self._summary:
    messages.append({"role": "system", "content": "[Historical Summary]\\n" + self._summary})
messages.extend(prefix[1:])
messages.extend(message for round_messages in recent for message in round_messages)
```

So the order of a normal request is: the original system message, `[Structured State]`, the optional `[Historical Summary]`, the original first task, and the most recent complete rounds. `history` itself is neither deleted nor rewritten, and later compaction still uses it as the source.

The default `keep_rounds` is 6; `keep_rounds=0` means no recent original text, and all rounds can be summary candidates. A negative number has no sensible meaning, and `compact()` raises `ValueError`.

### 2. State is the anchor of facts; the summary is only a semantic hint

A summary is the model's paraphrase and may miss details. Execution state is updated from tool execution results and contains the task, the current goal, changed files, errors, status, and the last four completed tools. In compaction mode, every view build calls `state.snapshot()` again:

```python
snapshot = self.state.snapshot()
return {
    "role": "system",
    "content": (
        "[Structured State]\\n"
        f"Task: {snapshot['task']}\\n"
        f"Files changed: {', '.join(snapshot['files_changed']) or '(none)'}\\n"
        f"Errors: {', '.join(snapshot['errors']) or '(none)'}\\n"
        f"Status: {snapshot['status']}\\n"
        f"Tools executed: {len(snapshot['tool_history'])}\\n"
    ),
}
```

This code does not "make the summary more accurate"; it avoids treating the summary as the only source of facts. Even if the summary leaves out a file write, the next request can still learn from `Files changed` that it happened. The boundary is also clear: `AgentState` is not a complete event log, and it cannot restore details it never recorded.

### 3. Summary requests carry no tools

The summarizer does not receive the whole conversation, only the older rounds, and it is asked to organize them by task, completed steps, recent successful tool calls, changed files, errors, current progress, and next steps. Any existing summary is given to it as well, so later compactions can merge rounds that have newly entered the "old history" range.

Production code injects the default summarizer through a deferred import, so that `context.py` does not form a circular import with `agent.py` when it loads:

```python
def summarizer(messages: list[Message]) -> str:
    from mini_agent.agent import summarize_messages
    return summarize_messages(messages)
```

The actual summary call reuses the existing `http.client` request path but explicitly turns off the tool schema and terminal streaming output:

```python
def summarize_messages(messages):
    return call_llm(
        messages,
        include_tools=False,
        stream_output=False,
    ).get("content", "") or ""
```

This prevents the internal request from producing tool calls, and the summary text is not shown as a user-facing Agent reply. The underlying request still reads and collects the response as a stream; `stream_output=False` only stops chunk-by-chunk printing.

## Why This Design

Keeping only a summary saves the most space but loses the original protocol relationships of recent tool calls; keeping only the original text is the most accurate but exceeds the window again; relying only on state loses much of the task's meaning. So v0.13 chooses "summary + recent original text + structured state".

The benefits: old history has a readable thread of continuity, recent rounds stay as they are, and execution facts do not depend on the model's paraphrase. The costs: the first compaction adds one more LLM network request, and the summary itself may drift. To keep this enhancement from becoming a new point of failure for the main task, exception handling sits inside `ContextManager.compact()`, and the LLM and CLI exception boundaries of the main loop stay unchanged.

## Design Boundaries

- `prepare_messages()` tries compaction automatically only when the message view before compaction exceeds the budget and the full history has more rounds than `keep_rounds`.
- `compact()` returns a boolean. It returns `False` when there are too few rounds, there are no old rounds not yet summarized, there is no summarizer, the summarizer raises, or it returns blank or non-string output; only a valid summary updates `_summary`, `_compacted`, and `_summarized_rounds`.
- When summarization fails, `prepare_messages()` returns the trimming copy it already computed. A failure does not overwrite an existing valid summary and does not rewrite `history`.
- Repeated compaction only handles rounds that are not yet summarized and have left the recent window; summary content may be lossy, and results need not be identical word for word each time.
- The budget estimate is still `len(text) // 3`, which is not the same as the server tokenizer. If the protected messages themselves already exceed the budget, compaction cannot get them deleted.
- This version does not persist summaries, does no vector retrieval, and does not evaluate summary quality. `MAX_ITERATIONS=50` only raises the maximum number of loop iterations from 10 to 50 and does not guarantee that the task finishes.

## Key Flow

The actual order of an over-budget request:

```text
history + state
   |
   v
_build_messages() -> compute the budget limit of the protected prefix -> is the initial view over the limit?
   |
   +-- always run trim() first to get a protocol-safe candidate request
   |
   +-- within limit: candidate request -> call_llm()
   |
   `-- over limit: compact()
          |
          +-- False: candidate request -> call_llm()
          `-- True: rebuild State + Summary + most recent complete rounds
                    -> trim() -> call_llm()
```

At runtime, over-budget trimming prints logs such as `[Context] token budget exceeded`; a successful compaction prints `[Context] compacted N old rounds`. This shows that the request switched from the full history to a summary plus recent rounds. When summarization fails, a failure message is printed, but the main task continues with the trimmed candidate request instead of stopping.

## Implementation Breakdown

`compact()` uses `_summarized_rounds` to record how many rounds have already gone into the summary. It first computes the boundary of the old rounds, then expands only the old rounds newly added this time into the summary input:

```python
eligible_end = len(rounds) - keep if keep else len(rounds)
start = min(self._summarized_rounds, eligible_end)
if eligible_end <= start:
    return False
old_rounds = rounds[start:eligible_end]
old_messages = [message for round_messages in old_rounds for message in round_messages]
```

This way, messages added after the first compaction are summarized only when they leave the recent window in the future. The success path commits state only at the end:

```python
summary = self.summarizer(prompt)
if not isinstance(summary, str) or not summary.strip():
    return False
self._summary = summary.strip()
self.keep_rounds = keep
self._compacted = True
self._summarized_rounds = eligible_end
return True
```

Because the assignments come after a valid summary, the failure path does not leave a half-finished "already compacted" state. This is the key to reliably falling back to the v0.12 behavior when summarization fails.

## Run and Observe

After you configure a local LLM, start a real task in Bash/zsh that is large enough to produce several rounds of tool calls. After the command-line first task is handled, the program still enters the interactive loop:

```bash
PYTHONPATH=src python -m mini_agent "check the login flow and run the regression tests"
```

When the context accumulated by the task exceeds the budget and there are more old rounds than the six kept by default, the terminal first shows the trimming logs, followed by the `compacted` log. Later main LLM requests contain the new structured state and history summary and keep the most recent complete rounds; this is the observable result of the three-layer division of information in this lesson.

## v0.13.1 Patch: Context Observability

> This is a patch addition to v0.13, not a capability native to the v0.13 tag. The patch only adds observability to context compaction and does not change the compaction strategy, message history, or the tool calling protocol.
>
> Patch snapshot: `v0.13.1` · Adjacent diff: `v0.13..v0.13.1`
>
> Code snapshot: `v0.13.1` · Adjacent diff: `v0.13..v0.13.1` · Shell: Bash/zsh

To switch to the patch and view its minimal difference from v0.13:

```bash
git checkout v0.13.1
git diff --stat v0.13..v0.13.1
git diff v0.13..v0.13.1 -- src/mini_agent/context.py src/mini_agent/config.py tests/test_context.py
```

### Why compaction results alone are not enough to observe

The v0.13 logs can only tell you that trimming or compaction happened; they cannot answer "how many tokens were finally sent", "which kind of message used up the budget", or "did compaction really succeed". When investigating an insufficient window, over-large tool output, or a summary failure in a long task, you need a statistics snapshot that matches the actual sent view, plus structured lifecycle events.

### `ContextStats`: five mutually exclusive input buckets

v0.13.1 adds the immutable `ContextStats`. `tokens` is the estimate for the full message view about to be sent; `window` is the context window, `input_limit` is the input limit after the output reserve is subtracted, and `reserve` is the output reserve. Input tokens are split into five mutually exclusive buckets:

| Field | Meaning |
|---|---|
| `system` | Ordinary system messages |
| `task` | The first user task message |
| `state` | The structured state message starting with `[Structured State]` |
| `history` | Other assistant/user history messages (excluding tool results) |
| `tool_result` | All `role=tool` results |

So `tokens == system + task + state + history + tool_result`. The estimate still uses `len(text) // 3` and is only a diagnostic metric, not the same as the server tokenizer.

### Reading the latest view with `stats_snapshot()`

After `prepare_messages()` finishes, `ContextManager.stats_snapshot()` returns the statistics of the latest sent view; before any request is prepared, it returns `None`. A minimal example:

```python
context = ContextManager(state, history)
messages = context.prepare_messages()
stats = context.stats_snapshot()
if stats is not None:
    print(stats.tokens, stats.tool_result, stats.reserve)
```

The snapshot comes from the final copy after trimming or compaction, not from the unprocessed full `history`, so it is suitable for recording together with the request about to be sent.

### trim/compact events and the default log

The context manager emits three kinds of `ContextEvent`:

- `prepared`: the final view is ready, and `event.stats` carries the `ContextStats`.
- `trimmed`: a tool result was truncated, or a complete old round was removed; `details["action"]` is `truncate` or `remove_round` respectively.
- `compacted`: old rounds were compacted successfully, and the details include the compacted rounds, the summary token count, and the recent rounds; a summary exception carries `failed=True`, meaning it fell back to trimming.

The default is `CONTEXT_OBSERVABILITY = True`, and the terminal shows output like this:

```text
[Context]
tokens: 1,234 / 128,000
system:              42
task:                18
state:               76
history:            510
tool_result:        588
reserve:         19,200
[Context Trim]
removed turn #1
tool_result: -240 tokens
[Context Compact]
compressed turns: 1-4
summary tokens: 96
recent turns: 5-10
```

The actual numbers depend on message content; these logs help locate budget changes and are not new protocol messages.

### Hooking into structured events with an observer

When you need to write to a metrics or logging system, pass an `observer` callback. The callback receives a `ContextEvent`, so you do not need to parse terminal text:

```python
def record_context_event(event):
    payload = {
        "kind": event.kind,
        "tokens": event.stats.tokens if event.stats else None,
        "details": event.details,
    }
    metrics.write(payload)

context = ContextManager(
    state,
    history,
    observer=record_context_event,
)
```

With an observer passed in, you can still turn off the default terminal output with `observability=False`; a custom observer still receives events. If the observer itself raises an exception, `ContextManager` swallows it and keeps preparing the request, so observation logic does not affect the agent.

### Patch boundaries

- Observability only reads the sent copy; it does not change the full `history` or the fallback to trimming when summarization fails.
- `prepared`, `trimmed`, and `compacted` are in-process events and are not appended to the messages sent to the model.
- No new tool calls are added, and the rule that every `tool_calls` gets its matching `role=tool` result fed back is unchanged.
- To turn off the log, set `CONTEXT_OBSERVABILITY = False` in the local `config_local.py`; the configuration template default is still `True`.

## Version Features, Next Lesson, and Code Index

On top of the v0.12 budget and trimming, v0.13 adds an injectable summarizer, automatic or explicit compaction, structured state injection, recent round retention, and fallback on summary failure, and raises the maximum number of iterations to 50. v0.13.1, as a patch in the same lesson, adds the token buckets of `ContextStats`, `stats_snapshot()`, the `prepared`/`trimmed`/`compacted` events, the default terminal log, and the `CONTEXT_OBSERVABILITY` switch, and guarantees that observer exceptions do not affect the agent. The next lesson adds project instructions and discusses why they also need to be kept as protected context.

- [`src/mini_agent/context.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.13/src/mini_agent/context.py) - compaction, state rendering, and sent view rebuilding
- [`src/mini_agent/agent.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.13/src/mini_agent/agent.py) - summary request without tools or terminal output
- [`src/mini_agent/config.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.13/src/mini_agent/config.py) - default limit of 50 rounds
- [`src/mini_agent/state.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.13/src/mini_agent/state.py) - source of structured execution facts
- [`src/mini_agent/context.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.13.1/src/mini_agent/context.py) - `ContextStats`, `ContextEvent`, observer, and the observable lifecycle
- [`src/mini_agent/config.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.13.1/src/mini_agent/config.py) - default `CONTEXT_OBSERVABILITY` switch
- [`tests/test_context.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.13.1/tests/test_context.py) - bucket, event, and observer isolation tests

# Lesson 12: Budget and trimming

> Version v0.12 | [Previous lesson](11-context-architecture.md) | [Back to the tutorial overview](README.md) | [Next lesson](13-context-compaction.md)

> Code snapshot: `v0.12` · Adjacent diff: `v0.11..v0.12` · Shell: Bash/zsh
>
> Requirements: Python 3.10+. The `pyproject.toml` at this tag still says 3.9, but the source already uses 3.10 syntax.

## Lesson Goals

Conversations and tool results keep accumulating. The model's Context Window is limited, and by the time the server reports a limit error, the request for this round has already failed.

This lesson lets the Agent keep working when the window is limited: before each call it reserves a budget, shortens lower-value content first, and does not break the mapping between tool call messages. After this lesson, you should be able to:

- Explain why context management needs a "budget" instead of waiting for the API to return a limit error.
- Understand how `ContextBudget` computes the message limit for a request from the model window.
- Explain why tool calling messages must be trimmed by complete rounds.
- Observe tool result truncation and old round deletion with a small window.

This lesson does not aim to count tokens (the unit models use to measure text) exactly. The focus is three direct constraints: **check before the call, handle low-value content first, never break the protocol structure**.

## Prerequisites and Version Checkout

- Read Lesson 11 and understand that `AgentState` and the LLM Context (the context sent to the model) are already separate.
- Switch to this version's code:

```bash
git checkout v0.12
git diff --stat v0.11..v0.12
git diff v0.11..v0.12 -- src/mini_agent/context.py src/mini_agent/config.py src/mini_agent/config_example.py
```

If you want to keep developing instead of only reading the tag, go back to your development branch before changing files.

## Problems in the Previous Version

v0.11 separated state from context, but `prepare_messages()` still sends the full history. As task rounds increase, the following keep accumulating:

- The system prompt and the user task.
- Tool calls issued by the assistant.
- Tool results such as file contents, search results, and shell output.
- The assistant's interim judgments.

Eventually a request may exceed the model's Context Window. Handling it only after the server reports an error has two problems: the current round has already failed, and the caller does not know which messages can be deleted safely.

So v0.12 always checks the budget before calling the LLM.

## New and Changed Files

| File | Change |
|---|---|
| `src/mini_agent/context.py` | Adds token estimation, the budget model, round splitting, and `TrimPolicy` |
| `src/mini_agent/config.py` | Adds `CONTEXT_WINDOW = 128_000` |
| `src/mini_agent/config_example.py` | Shows the overridable window configuration |
| `CHANGELOG.md` / `AGENTS.md` | Record the v0.12 design decisions and version status |

## Key Flow

`agent.py` does not need to change. v0.11 already made the Agent loop call `context_manager.prepare_messages()` as a single entry, so the budget strategy still lives entirely inside the ContextManager:

```text
agent_loop
    |
    v
ContextManager.prepare_messages()
    |
    +-- copy the full history
    +-- compute the budget
    +-- TrimPolicy.trim()
    v
call_llm(prepared_messages)
```

When the budget is not exceeded, this flow returns copies of the message dictionaries; when it is exceeded, only the copies are changed, truncated or deleted by the priorities described below. On either path, the loop keeps the full `history`.

## Implementation Breakdown

### 1. Tokens only need a good-enough estimate

Exact tokenization needs an extra dependency, but this project keeps zero third-party dependencies, so it does not bring in `tiktoken`. `count_tokens()` roughly estimates strings with `len(text) // 3` and recursively counts dicts, lists, and tuples in messages:

```python
def count_tokens(text_or_messages: object) -> int:
    if text_or_messages is None:
        return 0
    if isinstance(text_or_messages, str):
        return len(text_or_messages) // 3
    if isinstance(text_or_messages, dict):
        return sum(count_tokens(value) for value in text_or_messages.values())
    if isinstance(text_or_messages, (list, tuple)):
        return sum(count_tokens(value) for value in text_or_messages)
    return len(str(text_or_messages)) // 3
```

This is not a tokenizer. It does not count protocol wrapping overhead, and it cannot reflect exactly how different models encode Chinese, English, and punctuation.

It is only used to decide "whether to start shortening the context", so reasonable error is acceptable. The output reserve and the history ratio absorb part of the error.

### 2. The budget is not one fixed limit

A request cannot have just one fixed limit, because input, model output, and history messages all take up the window. `ContextBudget` describes these boundaries with three values:

```python
@dataclass(frozen=True)
class ContextBudget:
    window: int = CONTEXT_WINDOW
    output_reserve_ratio: float = 0.15
    history_ratio: float = 0.45
```

| Field | Default | Meaning |
|---|---:|---|
| `window` | `128_000` | Context Window of the target model |
| `output_reserve_ratio` | `0.15` | Reserves 15% for model output |
| `history_ratio` | `0.45` | History outside the `prefix` (protected prefix) uses at most 45% |

The three derived values are related like this:

```python
input_limit = int(window * (1 - output_reserve_ratio))
history_limit = int(window * history_ratio)
message_limit = max(
    protected_tokens,
    min(input_limit, protected_tokens + history_limit),
)
```

For example, with a window of 100, an output reserve of 20%, a history ratio of 40%, and system + the first user task taking 10 tokens:

```text
input_limit   = 100 * 80% = 80
history_limit = 100 * 40% = 40
message_limit = min(80, 10 + 40) = 50
```

`max(protected_tokens, ...)` here is the floor rule. Even if the system message and the first user task alone exceed the budget, they are always kept.

In that case the ContextManager prints an over-limit log and does not delete the task itself to meet a numeric target.

You can override the model window in `src/mini_agent/config_local.py`, which is not tracked by git:

```python
CONTEXT_WINDOW = 32_000
```

### 3. Atomic trimming by protocol round

Tool call messages cannot be deleted one at a time at will. A tool round consists of one assistant message with `tool_calls` and all the tool results right after it:

```text
assistant(tool_calls: call-1, call-2)
tool(tool_call_id: call-1)
tool(tool_call_id: call-2)
```

The OpenAI tool calling protocol requires every `role=tool` message to match an earlier `tool_call_id`. Deleting only the assistant message leaves orphan tool results; deleting only one tool result leaves a call declared by the assistant without a response. The API may reject both.

So `_split_rounds()` first finds the first user message. Together with the system messages before it, it forms the `prefix` that cannot be deleted; later messages are cut into `rounds` (history rounds). When it meets a tool-calling assistant, that message and the consecutive tool messages after it go into the same list:

```python
if _is_tool_call_message(message):
    round_messages = [message]
    index += 1
    while index < len(messages) and messages[index].get("role") == "tool":
        round_messages.append(messages[index])
        index += 1
    rounds.append(round_messages)
```

An ordinary assistant message or a later user message each forms a single-message round. Trimming may shorten the text of a tool result, but deleting history always removes only complete `round`s.

`_split_rounds()` only groups consecutive `role=tool` messages and does not repair a `tool_call_id` that is already invalid; the agent loop guarantees the normal protocol sequence. If the history has no user message, all messages stay in the protected `prefix`, and there are no history rounds to delete.

### 4. The trimming algorithm

If the history were changed directly, the full record could not be restored later. So `TrimPolicy.trim()` always makes shallow copies of the message dictionaries first, and all changes apply only to the copy sent this time:

```python
prepared = [dict(message) for message in messages]
```

It then works from low value to high value:

1. If the estimate does not exceed `message_limit`, return the copy directly.
2. Check tool results starting from the oldest round.
3. Truncate results longer than 120 characters by a fixed amount, keeping both the beginning and the end and inserting an omission marker in the middle.
4. If still over the limit, delete complete rounds starting from the oldest.
5. If still over the limit after all rounds are deleted, keep the prefix and print a protected messages over-limit log.

The conclusion, error, or summary of tool output often appears at the end, so truncation keeps both the beginning and the end instead of only the beginning:

```text
beginning of result
[... omitted 780 characters ...]
ending of result
```

`needed_characters = (current_tokens - target) * 3` converts the tokens to save into characters. `minimum_tool_result_characters = 120` prevents results from being compressed again and again until they are unreadable.

If truncation is still not enough, the algorithm deletes complete rounds, so it always converges.

## Why This Version Is Needed

The v0.12 approach makes several trade-offs around "requests must not exceed the limit, and the task and protocol must not break":

- **Heuristic estimation instead of an exact tokenizer**: keeps zero third-party dependencies; the cost is estimation error, so the output reserve and the ratio budget leave a margin.
- **Ratios instead of a fixed number of history entries**: adapts to different model windows; the cost is that the number of messages that can actually be kept varies with content length.
- **Truncate tool results first, then delete complete rounds**: keeps tool conclusions as long as possible while guaranteeing a complete tool calling protocol; the cost is that old rounds may eventually be lost entirely.
- **Put the strategy in the ContextManager**: the Agent loop only calls the single entry, so changing the strategy later does not touch the loop; the cost is that the loop does not directly know what was trimmed from the context in this round.
- **Keep the protected prefix and the full history**: the task can still run, and the original record can still be audited; the cost is that the prefix itself may exceed the budget, and v0.12 provides no history summary.

### Why not change the original history

`history` keeps the full local execution record, and `prepared_messages` is only a temporary view for one LLM request:

```text
full history ---------------------> keeps growing next round
      |
      +-- copy --> trim --> LLM request
```

If the history were trimmed directly, there would be no way to change strategies, summarize again, or investigate what the Agent actually did. v0.12 also does not inject `AgentState` into messages; these two boundaries keep a reliable data source for later versions.

### Boundaries of this version

An invalid window or ratio in `ContextBudget` raises `ValueError` at construction; when protected content exceeds the limit, a log is recorded, but system or the first user message is not deleted. `_split_rounds()` assumes the history comes from a normal Agent loop and does not repair arbitrarily malformed messages. History summaries and State injection are not part of this version.

## Run and Observe (If Needed)

To observe this flow, construct one tool round with a tiny window; this command only calls `ContextManager` and does not need a real LLM:

```bash
PYTHONPATH=src python - <<'PY'
from mini_agent.context import ContextBudget, ContextManager
from mini_agent.state import AgentState

history = [
    {"role": "system", "content": "system"},
    {"role": "user", "content": "read the log and find the error"},
    {"role": "assistant", "content": None, "tool_calls": [{"id": "call-1"}]},
    {"role": "tool", "tool_call_id": "call-1", "content": "HEAD-" + "x" * 900 + "-TAIL"},
]
context = ContextManager(
    AgentState(task="read the log and find the error"),
    history,
    ContextBudget(window=250, output_reserve_ratio=0, history_ratio=0.8),
)

prepared = context.prepare_messages()
print(prepared[-1]["content"])
print("history unchanged:", len(history[-1]["content"]) == 910)
PY
```

You should see logs similar to:

```text
[Context] token budget exceeded: ...
[Context] truncated tool result call-1, saved ... tokens
[Context] prepared context: ... tokens
```

The last line should be `history unchanged: True`, which shows that the copy sent was shortened while the original record was not touched.

## Version Features, Next Lesson, and Code Index

- Budget check before calling the LLM.
- Tool results support fixed-amount truncation that keeps the beginning and the end.
- Tool calling history is deleted atomically by protocol round.
- Neither the original history nor AgentState is affected by trimming.

The next lesson discusses how to keep compactable history information before old rounds are deleted, while continuing to use the budget and protocol boundaries from this lesson.

### Tag-pinned code index

- [`src/mini_agent/context.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.12/src/mini_agent/context.py) — budget and TrimPolicy
- [`src/mini_agent/config.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.12/src/mini_agent/config.py) — CONTEXT_WINDOW configuration
- [`src/mini_agent/config_example.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.12/src/mini_agent/config_example.py) — configuration template
- [`src/mini_agent/agent.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.12/src/mini_agent/agent.py) — prepare_messages call entry

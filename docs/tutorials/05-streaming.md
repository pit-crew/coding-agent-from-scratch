# Lesson 5: Streaming output

> Version v0.05 | [Previous lesson](04-permission-gate.md) | [Next lesson](06-concurrent-tool-calls.md)

> Code snapshot: `v0.05` · Adjacent diff: `v0.04..v0.05` · Shell: Bash/zsh
>
> Requirements: Python 3.10+. The `pyproject.toml` at this tag still says 3.9, but the source already uses 3.10 syntax.

## Lesson Goals

In the previous version, the terminal showed nothing until the model had generated the full reply. With a long reply, the wait is obvious.
This version makes `call_llm` show the reply as it arrives, and handles the case where `tool_calls` are split across several chunks.

## Prerequisites

- Read [Lesson 4](04-permission-gate.md) and understand the permission gate
- `git checkout v0.05` to switch to this version's code

## What Was Added or Changed

```
 src/mini_agent/
 └── agent.py            # Changed: call_llm becomes streaming (stream=True + SSE parsing + chunk assembly)
```

> This version changes only `agent.py`. Tools, permissions, and config are unchanged.

## Core Concepts

### Non-streaming vs streaming

The previous version was non-streaming (the model returns everything at once after it finishes): the LLM generated the full JSON first, and `call_llm` returned the message only after parsing it.
So the terminal had to wait until the model was completely done, and long replies gave no feedback for a long time.

This version switches to streaming (the model sends a little as soon as it generates it). These small pieces are called chunks, and the transport format is Server-Sent Events (SSE).
`call_llm` reads and prints chunks one by one, so content appears word by word in the terminal; this only changes how it is displayed and does not mean the model finishes faster.

### The SSE protocol (Server-Sent Events)

The problem is that a streaming response is no longer one complete JSON document but a sequence of text lines. Each line is a `data:` event:

```
data: {"choices":[{"delta":{"content":"Hel"}}]}
data: {"choices":[{"delta":{"content":"lo"}}]}
data: {"choices":[{"delta":{"content":"!"}}]}
data: [DONE]
```

The `delta` of each chunk may contain:
- `content`: a small piece of text (printed as it arrives)
- `tool_calls`: fragments of a tool call (assembled across chunks)

The stream is known to be finished only after `data: [DONE]` is received.

### Streaming implementation of call_llm (`src/mini_agent/agent.py:12`)

To make the server return a stream, the request must turn on a switch and declare that it accepts SSE:
```python
body = json.dumps({
    "model": MODEL,
    "messages": messages,
    "stream": True,              # ← New: turn on streaming
    "tools": registry.schemas(),
}, ensure_ascii=False).encode()

headers = {
    ...
    "Accept": "text/event-stream",  # ← New: declare that SSE is accepted
}
```

After the response arrives, the code reads `resp` line by line and parses each `data:` event:

```python
content_parts = []
tool_calls_acc = {}

for raw in resp:
    line = raw.decode("utf-8").strip()
    if not line or not line.startswith("data:"):
        continue
    if line == "data: [DONE]":
        break
    chunk = json.loads(line[6:])
    delta = chunk["choices"][0].get("delta", {})

    # Print content as it arrives (typewriter effect)
    if delta.get("content"):
        content_parts.append(delta["content"])
        print(delta["content"], end="", flush=True)

    # Assemble tool_calls arguments across chunks
    for tc in delta.get("tool_calls", []):
        idx = tc.get("index", 0)
        slot = tool_calls_acc.setdefault(idx, {
            "id": "", "type": "function",
            "function": {"name": "", "arguments": ""},
        })
        if tc.get("id"):
            slot["id"] = tc["id"]
        fn = tc.get("function", {})
        if fn.get("name"):
            slot["function"]["name"] = fn["name"]
        if fn.get("arguments"):
            slot["function"]["arguments"] += fn["arguments"]
```

After the loop ends, the code builds a message in the same format as the non-streaming one, so the rest of the agent loop does not need to know this response was streamed:
```python
message = {"role": "assistant", "content": "".join(content_parts) or None}
if tool_calls_acc:
    message["tool_calls"] = [tool_calls_acc[i] for i in sorted(tool_calls_acc)]
return message
```

### Assembling tool_calls across chunks

Text can be shown piece by piece, but tool calls cannot. During streaming, one tool_call may be split into several chunks:

```
chunk 1: {"tool_calls":[{"index":0, "id":"call_abc", "function":{"name":"calculate"}}]}
chunk 2: {"tool_calls":[{"index":0, "function":{"arguments":"{\"expr"}}]}
chunk 3: {"tool_calls":[{"index":0, "function":{"arguments":"ession\": \"3+5\"}"}}]}
```

The `arguments` here are string fragments that must be joined with `+=`; this is not a merge of several JSON objects. `index` identifies the same tool_call.
The code buffers fragments by `index`, and only after the stream ends does it have the complete tool_calls list.

## Why This Design

### Why http.client instead of requests

In real use, the `your-gateway-host` gateway responds abnormally with 502 to `Accept-Encoding: gzip`.
A compressed SSE stream can also make chunk boundaries hard to detect. `http.client` with `Accept-Encoding: identity` requests the raw uncompressed text, so parsing line by line is reliable.

### Why content is printed as it arrives instead of after it is complete

Printing as it arrives produces a "typewriter effect": the user can see the text that has already been generated instead of waiting a few seconds for the whole block.
`flush=True` flushes output immediately; otherwise the text may stay in the buffer, and the terminal still looks like it shows everything at once.

### Why tool_calls are not printed as they arrive

Content is ordinary text, so printing it word by word makes sense. tool_calls are structured data containing a tool name and argument JSON; printing half an argument only produces unreadable content.
So the code waits until the call is complete and then prints the decision once: `print(f"  Decided call: {name}({arguments})")`.

### Why the print marker in agent_loop moves before call_llm

In v0.04, `agent_loop` called `call_llm` first and then printed `=== [N] LLM reply ===`.
This version must print the marker before calling `call_llm`. Because content is printed immediately inside `call_llm`, a marker printed afterwards would appear after the reply, and the terminal order would be wrong.

## Usage Guide

### Commands available in this version

```bash
# Command-line first task (observe the typewriter effect)
PYTHONPATH=src python -m mini_agent "Introduce yourself in one sentence"

# With a tool call
PYTHONPATH=src python -m mini_agent "calculate 123 * 456"

# Run the smoke test
PYTHONPATH=src python tests/test_tools.py
```

### Typical examples for this version

**Example 1: observe the typewriter effect**
```bash
PYTHONPATH=src python -m mini_agent "Introduce yourself in one sentence"
```
Expected: the LLM reply appears word by word in the terminal, instead of popping up all at once after a few seconds.
Note: the reply is currently printed twice. The first copy comes from the streaming output of `call_llm`, and the second from `print(reply)` in `__main__.py`.
This is a known display problem in v0.05; later versions adjust `__main__.py`.

**Example 2: streaming + tool call**
```bash
PYTHONPATH=src python -m mini_agent "calculate 123 * 456"
```
Expected output:
```
=== [1] LLM reply ===
  Decided call: calculate({"expression": "123 * 456"})
[Executor] Running Tool: calculate
...
  Result: 56088

=== [2] LLM reply ===
123 × 456 equals 56088.
```
Note: round 2 has no tool call, so the final reply is shown word by word by the streaming output.

**Example 3: compare the feel of a long reply**
```bash
# v0.04 (non-streaming): pops up all at once after 3-5 seconds
git checkout v0.04
PYTHONPATH=src python -m mini_agent "Describe the history of Python in detail"

# v0.05 (streaming): starts appearing word by word immediately
git checkout v0.05
PYTHONPATH=src python -m mini_agent "Describe the history of Python in detail"
```

### Features unique to this version

- **Typewriter effect**: the LLM reply appears word by word in the terminal; this is the easiest change to observe in v0.05.
- **SSE parsing**: `call_llm` reads `data:` events line by line, then parses the JSON chunks.
- **Assembling tool_calls across chunks**: `arguments` fragments are joined with `+=` as they arrive and grouped by `index`.
- **Reply printed twice**: after `call_llm` prints the stream, `__main__.py` still runs `print(reply)`; this is a known problem.

## Hands-On Verification

1. **Run the smoke test**:
   ```bash
   PYTHONPATH=src python tests/test_tools.py
   ```
   Expected: 8 PASS lines (tool tests are not affected by streaming).

2. **Observe the typewriter effect**:
   ```bash
   PYTHONPATH=src python -m mini_agent "Introduce yourself in one sentence"
   ```
   Expected: the reply appears word by word in the terminal.

3. **Compare v0.04 vs v0.05**:
   ```bash
   git checkout v0.04
   PYTHONPATH=src python -m mini_agent "Describe the history of Python in detail"
   # Feel: pops up all at once after a few seconds

   git checkout v0.05
   PYTHONPATH=src python -m mini_agent "Describe the history of Python in detail"
   # Feel: starts appearing word by word immediately
   ```

## Full Code for This Version

- [`src/mini_agent/agent.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.05/src/mini_agent/agent.py) — streaming `call_llm` + `agent_loop`

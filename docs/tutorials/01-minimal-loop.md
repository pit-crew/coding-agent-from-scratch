# Lesson 1: Minimal agent loop

> Version v0.01 | [Next lesson](02-first-tool.md)

> Code snapshot: `v0.01` · Adjacent diff: none (first version) · Shell: Bash/zsh
>
> Requirements: Python 3.9+.

## Lesson Goals

This lesson solves the most basic problem first: how a program gives the user's words to an LLM and gets the final answer back.

We build an agent loop from scratch, that is, "a loop that calls the model again and again and handles its replies". v0.01 has no tools yet, so it shows only the loop skeleton: call the LLM → receive the reply → decide whether to stop.

## Prerequisites

- Python 3.9+
- Environment prepared as in the [learning path README](README.md) (clone the repository, fill in config.py, install the package)
- `git checkout v0.01` to switch to this version's code

## What This Version Adds

This version is the starting point; there is no "previous version". All files:

```
src/mini_agent/
├── __init__.py         # Package entry (empty file)
├── __main__.py         # CLI entry: python -m mini_agent
├── agent.py            # agent loop: call_llm + agent_loop
└── config.py           # BASE_URL/API_KEY/MODEL/MAX_ITERATIONS (hard-coded)
tests/
└── test_loop.py        # Import chain smoke test
```

## Core Concepts

### What is an agent loop

An ordinary chat program calls the LLM once and is done. A coding agent is different: the model may first ask to call a tool and can only continue answering after it gets the tool result. So the core of an agent is a **loop**:

1. Send the conversation history (the `messages` list) to the LLM
2. The LLM returns a reply, which is appended to `messages`
3. Check whether the reply contains `tool_calls`
   - No → the LLM has given its final answer, and the loop ends
   - Yes → run the tools, append the results to `messages`, and go back to step 1

`tool_calls` means the model asks the program to call tools. v0.01 gives the model no tools, so the model does not produce such requests and usually finishes after one reply. The branch is still kept here because later versions plug tools in at this point.

### The messages list

The LLM itself does not remember the previous request. To let it understand the conversation, the program must send the existing messages again with every request.

These messages are kept in `messages`. It is a Python list of dictionaries; each dictionary records one message and its sender:

```python
messages = [
    {"role": "system", "content": "You are an assistant."},
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hello! How can I help you?"},
]
```

Each time the program calls the LLM, it sends the full `messages`. After it receives the reply, it uses `append` to add the new message to the end of the list. Because the next round can still see the earlier messages, the model appears to "remember" the conversation.

### call_llm: calling the LLM with http.client

`call_llm` in `src/mini_agent/agent.py:12` turns `messages` into an HTTP request and takes the model message out of the response:

```python
def call_llm(messages):
    p = urlparse(BASE_URL)
    conn = http.client.HTTPConnection(p.hostname, p.port or 80, timeout=120)
    body = json.dumps(
        {"model": MODEL, "messages": messages},
        ensure_ascii=False,
    ).encode()
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "Accept-Encoding": "identity",   # ← Key point, see "Why This Design" below
    }
    conn.request("POST", f"{p.path.rstrip('/')}/chat/completions", body=body, headers=headers)
    resp = conn.getresponse()
    data = json.loads(resp.read().decode("utf-8"))
    conn.close()
    return data["choices"][0]["message"]
```

This uses the OpenAI Chat Completions protocol. The program sends a POST request to `{BASE_URL}/chat/completions`, puts `model` and `messages` in the request body, and passes the API key in the `Authorization` header.

The response is also JSON. `data["choices"][0]["message"]` is the reply for this round, and the caller appends it to `messages`.

### agent_loop: the loop body

`agent_loop` in `src/mini_agent/agent.py:34`:

```python
def agent_loop(messages):
    for i in range(MAX_ITERATIONS):
        msg = call_llm(messages)
        messages.append(msg)

        print(f"\n=== [{i+1}] LLM reply ===")
        print(msg.get("content", ""))

        if not msg.get("tool_calls"):
            return msg.get("content", "")

    return "Maximum iterations reached"
```

There are three key points:
1. **Reuse messages across rounds**: the caller creates `messages`, and `agent_loop` only appends to it. So when `__main__.py` calls the loop several times, the earlier conversation is kept.
2. **Decide when to stop**: `if not msg.get("tool_calls")` means the model did not ask for tools, so the current text is the final answer. v0.01 provides no tools, so the first round usually ends here.
3. **Limit the number of iterations**: `MAX_ITERATIONS = 10` stops the loop from running forever. When the limit is reached, it returns `"Maximum iterations reached"`. This version does not explain further why the task did not finish.

### __main__.py: the CLI entry

`src/mini_agent/__main__.py` supports two modes:

- **Command-line first task**: `PYTHONPATH=src python -m mini_agent "your task"` — handles the argument first, then enters the same interactive loop
- **Interactive mode**: `python -m mini_agent` — shows the `You: ` prompt, calls the loop once per input line, and exits on `exit`/`quit`

Both modes share one `messages` list, so interactive mode keeps context across rounds.

## Why This Design

### Why http.client instead of requests

The gateway the project uses may return 502 when it receives `Accept-Encoding: gzip`. `http.client` is part of the Python standard library and gives precise control over request headers, so the code explicitly sends `Accept-Encoding: identity`, asking the server not to compress the response.

This is a runtime constraint of the project, and later versions keep using `http.client`.

### Why no try/except fallback

`agent_loop` does not wrap `call_llm` in `try/except`. When the network drops, the API key is wrong, or the response cannot be parsed, the exception goes straight to the caller.

This lesson keeps only the main path "call the LLM → check the reply → stop". From the next lesson on, expected errors during tool execution are handled by `ToolExecutor`; LLM calls and top-level CLI exceptions are still not hidden inside the loop.

### Why config is hard-coded

`BASE_URL`, `API_KEY`, and `MODEL` are written directly in `config.py` and are not read from environment variables. This way a beginner only has to edit one file to run the program. The cost is that it does not suit multi-environment deployment, and the real configuration must not be committed to the repository.

## Usage Guide

### Commands available in this version

```bash
# Command-line first task mode
PYTHONPATH=src python -m mini_agent "Hello"

# Interactive mode
PYTHONPATH=src python -m mini_agent

# Run the smoke test (verifies the import chain)
PYTHONPATH=src python tests/test_loop.py
```

> The commands in this lesson are written for Bash/zsh; without `pip install -e .`, set `PYTHONPATH=src` explicitly. After it handles the command-line first task, the program still enters the interactive loop; enter an empty line, `exit`, `quit`, or send EOF to leave.

### Typical examples for this version

**Example 1: command-line first task**
```bash
PYTHONPATH=src python -m mini_agent "Introduce yourself in one sentence"
```
Expected output:
```
=== [1] LLM reply ===
I am an AI assistant that can answer questions and give suggestions.
I am an AI assistant that can answer questions and give suggestions.
```
(The second line comes from `print(reply)` in `__main__.py` and repeats the one above — a small flaw in v0.01 that later versions fix.)

**Example 2: interactive mode**
```bash
PYTHONPATH=src python -m mini_agent
```
After it starts:
```
You: My name is Ming
=== [1] LLM reply ===
Hello, Ming! How can I help you?
You: What did I just say my name was?
=== [1] LLM reply ===
You just said your name is Ming.
You: exit
```
The LLM can answer "Ming" in the second round not because the model keeps memory on the server, but because the program sent `messages` again, including the earlier round.

### Features unique to this version

- **No tools**: the LLM in v0.01 can only generate text and cannot really read files. It may say it cannot do something, or it may generate unverified content.
- **Not streaming**: the LLM reply comes back in one piece and the terminal prints it at once, with no typewriter effect (streaming arrives in v0.05).
- **No permission interaction**: because there are no tools, there is no "allow this?" prompt.

## Hands-On Verification

Run the three steps below to confirm you understand v0.01:

1. **Run the smoke test**:
   ```bash
   PYTHONPATH=src python tests/test_loop.py
   ```
   Expected: three `PASS: ...` lines and a message that all smoke tests passed.

2. **Command-line first task**:
   ```bash
   PYTHONPATH=src python -m mini_agent "What is 1+1"
   ```
   Expected: the LLM answers "2" (it computes this itself, not with a tool — v0.01 has no tools).

3. **Test context in interactive mode**:
   ```bash
   PYTHONPATH=src python -m mini_agent
   ```
   First enter `My name is Zhang San`, then `What is my name?`; the LLM should answer "Zhang San".

## Full Code for This Version

- [`src/mini_agent/agent.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.01/src/mini_agent/agent.py) — `call_llm` + `agent_loop`
- [`src/mini_agent/__main__.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.01/src/mini_agent/__main__.py) — CLI entry
- [`src/mini_agent/config.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.01/src/mini_agent/config.py) — configuration
- [`tests/test_loop.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.01/tests/test_loop.py) — smoke test (expects 3 PASS)

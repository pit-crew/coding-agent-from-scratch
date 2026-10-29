# Lesson 41: Letting the Agent find relevant memories instead of reading every record

Previous: [Giving the Agent a controllable long-term memo](40-persistent-memory.md) · [Tutorial overview](README.md) · Next: [Named local References](42-local-references.md)

> Code snapshot: `v0.41` · Adjacent diff: `v0.40..v0.41` · Shell: Bash/zsh

## Lesson Goals

Lesson 40 let the Agent save information such as "the test command" and "the release convention" into workspace memory. With few records,
paging through them works; once there are many, paging is slow, and putting every body into every model request
wastes context space.

This lesson adds "relevant memory retrieval". "Retrieval" means comparing keywords from the current task against each memory, picking
a few candidates, and ranking them; the "Context" is the messages actually sent to the language model this round. Retrieval results
are only old information for the model to consult; they never automatically become facts or instructions of the current task.

After this lesson, you should be able to answer:

- What the difference is between the explicit `search_memories` and the automatic candidates of each round;
- Why the automatic query is built only from the current task and the latest user message;
- Why "a hit" does not mean "it definitely enters the context";
- How to keep relevant information bounded and explainable, and make a corrupted memory file affect only the current information block.

## Prerequisites

First read [Lesson 40: Giving the Agent a controllable long-term memo](40-persistent-memory.md) to understand
workspace memory, schema 1 JSON, and `MemoryStore`. You need Python 3.10+; the offline commands below use
Bash/zsh and need no real model service.

First switch to this lesson's snapshot and look at the diff from the adjacent version:

```bash
git checkout v0.41
git diff --stat v0.40..v0.41
```

After reading, you can go back to your original branch:

```bash
git checkout -
```

## Problems in the Previous Version: Remembering a Lot Is Not the Same as Finding It

In v0.40, `list_memories` only pages in storage order, and `read_memory` requires knowing the target ID first. Suppose
the workspace has dozens of memories and the current task is "why does CI's type check fail"; the model needs to find information about tests,
CI, and type checking; making it read every record increases the number of calls and pushes irrelevant bodies in at the expense of
the current task and recent tool results.

v0.41 splits the problem into two steps: first use a lightweight lexical method to find "possibly relevant" candidates, then let the context budget
decide which candidates can enter this round's messages. When full details are needed, the model must still explicitly call
`read_memory(memory_id)`.

## What This Version Adds

The main thread of this version:

```text
current task + latest user message
              ↓
        build a bounded query
              ↓
MemoryStore.snapshot() → MemoryRetriever → ranked candidates
              ↓
at most 4 entries, at most 2400 characters, and enough remaining tokens to enter the Context
              ↓
      [Relevant Memory — Untrusted Reference]
```

`Untrusted Reference` means "untrusted reference material": it can help the model recall, but it cannot
override system instructions, project rules, the Plan, permission decisions, or verification results. Candidates exist only in the message view returned by this
`prepare_messages()` and are not written to history or the session.

The main code changes:

## New and Changed Files

| File | Purpose |
|---|---|
| [`retrieval.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.41/src/mini_agent/retrieval.py) | Does lexical matching, weighting, stable ranking, and excerpt trimming with the standard library. |
| [`memory.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.41/src/mini_agent/memory.py) | Provides a read-only `snapshot()` that gives the retrieval layer a consistent snapshot. |
| [`tools/memory.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.41/src/mini_agent/tools/memory.py) | Adds the read-only `search_memories(query, limit)`. |
| [`context.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.41/src/mini_agent/context.py) | Brings candidates into the message budget as a temporary information block. |
| `__main__.py`, `resume.py`, `config.py` | Bind the retriever only in the parent Runtime and provide a switch. |

## Version Change Map

In the diagrams, `[old]` is a capability already in v0.40, `[+]` is new in this lesson, `[~]` is changed in this lesson, `[C]`
marks the main user, and `[B]` marks the boundary of this lesson.

The previous version's entry is paged viewing:

```text
[old][C] parent Agent Runtime
      └─→ [old] MemoryStore
            ├─→ [old] list_memories / read_memory → tool history
            └─→ [old] memory file
      [B] the Context does not pick relevant memories automatically
```

This version adds read-only candidates at the step "prepare the messages sent to the model", while keeping the explicit search tool:

```text
[C] parent Agent Runtime
      ├─→ [~] ContextManager.prepare_messages()
      │       ├─→ [+] MemoryStore.snapshot()
      │       ├─→ [+] MemoryRetriever → ranked candidates
      │       └─→ [+] temporary information block → LLM
      └─→ [~] parent ToolRegistry
              └─→ [+] search_memories → bounded tool result

[B] candidates do not enter history, State, the session, Plan, Trace, or verification evidence;
    no vector retrieval, automatic memory writes, remote material reads, or References.
```

## Key Flow

### 1. Read a read-only snapshot first

`MemoryStore.snapshot()` validates the whole JSON by the rules of Lesson 40 and then returns a deep copy. It
creates no directories, acquires no write lock, and changes no durable state. The retriever depends only on this public snapshot and does not need to know
how MemoryStore locks and replaces atomically.

The snapshot is read only once each time model messages are prepared. So a new memory just committed by another process is visible in the next
`prepare_messages()`; old candidates are not brought back by `/new`, `/reset`, or recovery.

### 2. Rank with an easily explainable lexical method

v0.41 introduces no tokenizer package, vector database, or embeddings (a method that turns text into vectors and then compares semantic similarity).
It first applies Unicode NFKC normalization and `casefold()`, then matches contiguous runs of English letters, digits, and code
identifiers; CJK text also keeps phrases and generates two-character fragments, so a CJK phrase and two-character queries taken from it can match each other.

The model can also search actively instead of waiting for automatic candidates. For example:

```text
search_memories(query="CI type check", limit=5)
```

This call only reads the memory file and returns at most 5 candidates with IDs and short excerpts; if the model wants to confirm the full content,
it still has to call `read_memory`. So there is still an explicit judgment step between "found by search" and "treating the whole memory as fact".

Fields have different weights: titles highest, then tags, then sources, and bodies lowest; a hit on the full query phrase earns extra points.
Ties are further ordered by update time and `memory_id`. This fixed order matters: the same snapshot and the same
query should give the same result, which makes it easy to explain and troubleshoot.

Explicit search returns 5 entries by default and at most 10. Results include the ID, title, body excerpt, source, update time,
score, and matched fields; excerpts are at most 240 characters. `source_status` is always `unverified`, because the `source` of Lesson
40 is free text, and the retriever never follows it to access files or claims that the source is still fresh.

### 3. Automatic candidates are built only from the current user intent

The automatic path uses `AgentState.task` and the latest `role=user` message in the full local history,
joined into a query of at most 1200 characters. It does not use assistant output, tool results, history summaries, or memory bodies already
retrieved. This way old information can only be "recalled" by the current user question and cannot expand into new queries layer by layer.

The automatic path shares the same matching rules as explicit search, but it is not a tool call; it only prepares a small block of system information
temporarily before each LLM request. If the model needs the full body, it must still call
`read_memory(memory_id)` itself.

### 4. "A hit" must still pass the context budget

The Context first finishes the existing history trimming and compaction, then reads the snapshot, adds candidates in rank order, and finally does one more ordinary
trim. A candidate must meet three conditions at once: at most 4 entries, an information block of at most 2400 characters, and enough remaining input tokens.
When the budget is not enough, lower-ranked candidates are dropped as a whole; no candidate is cut in half.

`ContextStats.memory` records the information block's tokens separately, and `tokens` still means the total of all message buckets. Candidates
are only a temporary return value of `prepare_messages()`, so `history`, `AgentState.snapshot()`,
and `ContextManager.export_session()` never contain this information.

### 5. A read failure only degrades the current information block

A missing memory file means an empty collection; if the JSON is corrupted, the schema is unknown, or a record is out of bounds, the parent Context
puts in a bounded "memory retrieval unavailable" notice and keeps building the ordinary LLM messages. The next message preparation
tries again; the system does not turn retrieval off permanently because of one failure, and it does not swallow all real programming errors either.

When `MEMORY_RETRIEVAL_ENABLED` is set to `False`, the Context does not read the Memory file and no information block
appears. This switch only controls automatic candidates; it does not delete memories and does not affect the explicit read-only tool contract.

## Implementation Breakdown

The retrieval layer and the context layer are deliberately separate. `retrieval.py` only answers "which records are more relevant", while `context.py`
answers "how much space is left in this round's messages". This way, adjusting the context budget later does not require rewriting the memory file format;
adjusting the matching method does not accidentally change history or State.

The information block is clearly labeled `[Relevant Memory — Untrusted Reference]` and states that it cannot override
higher-priority instructions, cannot directly prove the current file state, and certainly cannot create verification evidence. Context
events keep only the query character count, hit count, injected count, and token count; failure events record only the exception type, not
bodies or storage paths.

## Why This Design

Standard-library lexical retrieval is small, explainable, and easy to run offline. High weights on titles and tags let users organize memories through
short titles; stable ranking keeps debugging and replay independent of the JSON traversal order. Putting candidates in a temporary information block
keeps both properties: "helpful across tasks" and "does not pollute the task ledger".

The cost is that it does not understand real semantic similarity, so synonyms may not be found; CJK coverage is limited to the phrases and
two-character fragments this lesson needs; and sources have no change detection. v0.41 deliberately does no embeddings, query caching, automatic memory
extraction, remote access, or References; the read boundary for material outside the workspace is defined separately in the next lesson.

## Run and Observe

The point to observe in this lesson is "relevant candidates enter this round's view but do not become durable state". Run:

```bash
PYTHONPATH=src python -m pytest -q tests/test_memory_v040.py tests/test_memory_retrieval_v041.py tests/test_context.py
```

You should observe: memories hit by title or tag rank higher; CJK phrases and two-character queries can match; after another
process commits a new memory, the next `prepare_messages()` uses the new snapshot; the exported Context session
does not contain `[Relevant Memory — Untrusted Reference]`. With the switch off there is no information block; when you corrupt the
Memory JSON by hand, the current request can still build ordinary messages, and after the fix, the next request tries again.

## Version Features, Next Lesson, and Code Index

v0.41 completes explicit relevance search and bounded automatic candidates in the parent Context. Candidates are always untrusted material and cannot
advance the Plan, create verification evidence, or override project instructions. The next lesson separates "long-term memory inside the workspace"
from "local material outside the workspace":
[Lesson 42: Named local References](42-local-references.md).

- [`retrieval.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.41/src/mini_agent/retrieval.py): lexical matching, field weights, stable ranking, and the result structure.
- [`memory.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.41/src/mini_agent/memory.py): the read-only storage boundary of `snapshot()`.
- [`context.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.41/src/mini_agent/context.py): candidate refresh, information block layout, and budget statistics.
- [`tools/memory.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.41/src/mini_agent/tools/memory.py): the explicit `search_memories` tool contract.
- [`test_memory_retrieval_v041.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.41/tests/test_memory_retrieval_v041.py): an executable index of this lesson's behavior boundaries.

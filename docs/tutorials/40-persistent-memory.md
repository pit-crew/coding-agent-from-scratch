# Lesson 40: Giving the Agent a controllable long-term memo

Previous: [Delivering subagent results safely to the parent Agent](39-durable-delegation.md) · [Tutorial overview](README.md) · Next: [Relevant memory retrieval](41-memory-retrieval.md)

> Code snapshot: `v0.40` · Adjacent diff: `v0.39..v0.40` · Shell: Bash/zsh
>
> The `v0.40` tag is created manually by the repository owner; this lesson does not create or push tags.

## Lesson Goals

Start with a very practical scenario: you tell the Agent "this project runs its tests with
`PYTHONPATH=src python -m pytest -q`". If this sentence stays only in the current conversation, in the next task
the Agent may have to ask again; if it rewrites project files without permission, it may pollute the source.

This lesson gives the Agent an independent workspace memo that can be used across tasks. The "workspace" here is
the current project directory; a "memory" is one piece of project information saved explicitly by the user or the Agent. It is not automatic learning,
and not a set of higher-priority instructions.

After this lesson, you should be able to answer:

- What the current conversation, task state, session, and long-term memory are each responsible for;
- How the Agent lists, reads, adds, revises, and forgets memories;
- Why writes must ask for permission, and why a revision must carry `revision`;
- Why, if the file was already changed but the process crashed before returning the result, the system does not redo this write automatically.

## Prerequisites

You need basic Python, Bash/zsh, and Git. Lesson 39 helps you understand "how tool results are committed
safely", but no real API key is needed; this lesson is mainly about understanding behavior through the source and offline tests.

The commands below switch to this lesson's code and look at the size of the adjacent version. Afterwards, switch back to your original branch;
if the workspace has uncommitted changes, first confirm that switching versions does not affect them.

```bash
git checkout v0.39
git diff --stat v0.39..v0.40
git checkout v0.40
```

## Problems in the Previous Version: A Conversation Is Not a Long-Term Knowledge Base

An Agent is "a language model + tools + a run flow": the model proposes the next step, the program runs a tool, and the tool
result goes back to the model. The previous version can already run tools, but this conversation history belongs to the current task and may be compacted;
`AgentState` (the current task ledger) records plans, tool facts, and verification status, and is rebuilt with each new task;
a `/save` session (the recovery file) stores recovery information for one task, not a project knowledge base.

Stuffing long-term information into any of these places blurs responsibilities: old information may be mistaken for current instructions, and ordinary conversation
may change durable data without the user's explicit consent. The fix in v0.40 is simple: long-term information is stored separately,
and it changes only when the parent Agent explicitly calls a memory tool.

## What This Version Adds

This version builds one clear path:

```text
the parent Agent explicitly proposes a memory operation
        ↓
argument checks → PermissionGate → MemoryStore
        ↓                          ↓
  user can review            workspace-specific JSON file
```

The "permission gate" is where the program checks "is this allowed" before actually running a tool; the "memory store" is responsible for
the file format, concurrent writes, and the recovery boundary. The model cannot bypass the tools to change the file directly, and subagents do not get these
tools.

The main code is below. Look at the problem and the flow first, then the file names, and you will know why each module exists.

## New and Changed Files

| File | Responsibility |
|---|---|
| [`memory.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.40/src/mini_agent/memory.py) | Reads, validates, and safely replaces JSON files per workspace. |
| [`tools/memory.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.40/src/mini_agent/tools/memory.py) | Provides five parent Agent tools. |
| [`tools/__init__.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.40/src/mini_agent/tools/__init__.py) | Binds the MemoryStore only to the parent Runtime; subagents cannot see it. |
| [`permission.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.40/src/mini_agent/permission.py) | Makes viewing and changing follow the existing permission rules. |

## Version Change Map

In the diagrams, `[old]` is a capability already in v0.39, `[+]` is new in this lesson, `[~]` is changed in this lesson, `[C]`
marks the main user, and `[B]` marks the boundary of this lesson.

The previous version can run tools but has no long-term information entry across tasks:

```text
[old][C] parent Agent Runtime
      ├─→ [old] ToolExecutor → tool results go back to the current conversation
      ├─→ [old] AgentState / Context → the current task's ledger and message view
      └─→ [old] /save session → optional task recovery file
          [B] no independent long-term memory
```

This version connects long-term information to the parent-side tool entry instead of mixing it into State or the session:

```text
[C] parent Agent Runtime
      └─→ [~] PermissionGate
            ├─→ [+] list_memories / read_memory (read-only)
            └─→ [+] remember / revise_memory / forget_memory
                       │ may change the disk; needs permission and a generation
                       ▼
                 [+] MemoryStore
                       ├─→ reread and validate
                       ├─→ workspace lock, atomic replace, directory sync
                       └─→ workspace-specific JSON file

[B] no automatic extraction from conversation; no relevance retrieval; no References; not added to the subagent allowlist.
```

## Key Flow

### 1. Look at summaries first, then read bodies by ID

`list_memories(limit=20, offset=0)` returns only the memories' IDs, titles, tags, sources, and times,
not their bodies. When there is more than one page of records, the `next_offset` in the result tells the model where to continue; after finding the target,
it calls `read_memory(memory_id)`.

This step has two benefits: browsing many records does not stuff all bodies into the context, and later records can still be found
even when the first batch is large. A memory's `source` is only a source note filled in by the user and returns
`source_status="unverified"`; it cannot prove that the file still exists or that the content is still correct.

### 2. Adding, revising, and forgetting must all be proposed explicitly

The five tools can be understood like this:

| Tool | Purpose | May change durable data? |
|---|---|---|
| `list_memories` | View summaries page by page | No |
| `read_memory` | Read one full memory | No |
| `remember` | Add a memory | Yes |
| `revise_memory` | Revise an existing memory | Yes |
| `forget_memory` | Delete a memory | Yes |

The last three tools are marked `effect_class="possible"` even though they only write text, meaning "may
produce side effects". The PermissionGate shows the proposed title, body, source, target ID, and version number,
and the user can choose `once`, `always`, or `reject`. After a rejection, the handler (the function that actually changes the file)
is not entered. With `/save` on, the system must also commit `handler_admitted` before running the handler; only after every tool result
of this round is committed in model order can the next model round be requested.

### 3. One workspace maps to one memory collection

By default, memory files live in the user's local `~/.mini_agent/memory`, and the file name is a SHA-256 key computed from the workspace's real
path, so the file name does not expose the project path directly. A minimal record looks like
this:

```json
{
  "schema_version": 1,
  "memories": [
    {
      "memory_id": "stable random ID",
      "revision": 1,
      "title": "Test entry",
      "body": "PYTHONPATH=src python -m pytest -q",
      "tags": ["testing"],
      "source": "Confirmed by the user",
      "created_at": "2026-09-20T00:00:00Z",
      "updated_at": "2026-09-20T00:00:00Z"
    }
  ]
}
```

`revision` can be understood as this record's version number. A change must carry "which version I expect it still to be";
if the disk has already been changed to the next version by someone else, the old call fails instead of overwriting the new content. This is optimistic
concurrency control: assume there is no conflict first, then check at commit time.

## Implementation Breakdown

### 1. Writes never overwrite the old file directly

When writing, `MemoryStore` first acquires the current workspace's exclusive lock, then rereads the full collection from disk; next it
validates the records, writes a temporary file in the same directory and `fsync`s it, and finally replaces the old file atomically with `os.replace` and syncs
the directory. This way, when two processes save at the same time, the later writer does not quietly erase the records the earlier process just saved.

A missing file means "no memories yet". Corrupted JSON, an unknown schema, or an oversized file report clear errors and are not
treated as an empty collection to overwrite. The default limits include: at most 256 records, a body of at most 2000 characters, and a whole JSON
of at most 1 MiB; the storage directory permission is `0700`, and the file permission is `0600`. A custom `MEMORY_DIR` must also
be outside the workspace (including when a symlink points into the workspace).

### 2. Subagents only investigate; they do not take over long-term memory

The parent Runtime's registry creates the MemoryStore and registers the memory tools only after binding `AgentState`. Subagents
use the fixed four read-only tools: `calculate`, `read_file`, `list_dir`, and `grep`. So a subagent
cannot save, revise, or delete long-term information for the parent task, and cannot disguise a memory write as an ordinary investigation.

### 3. Crash recovery handles "uncertain" conservatively

A change may already have replaced the memory file, but the parent Agent's tool result may not yet have been written to the session.
At that point the system knows "the call was approved", but cannot be sure whether the caller received the success result. v0.40 keeps the existing
schema 3 tool boundary: the source session stays read-only, recovery marks the call as uncertain, and the
handler is not replayed automatically. The user can first check the current content with read-only tools, then `/resolve` item by item; the memory file is not
rolled back automatically by recovery.

## Why This Design

This version chooses small JSON files and the standard library because the memory collection has a clear limit, and users can back it up, inspect it,
and migrate it directly. Keeping Memory independent of State, Context, and the session satisfies both "saved across tasks" and
"old information never poses as current facts". Stable IDs let revisions not depend on titles, while `revision`, the lock, and atomic
replacement handle concurrency and half-written file risks in the storage layer.

The costs are equally clear: v0.40 has only paging, no relevance search; source text is not verified automatically; write failures or directory
sync failures need checking; with `/save` on, the body of a memory call may still enter the session with ordinary tool history.
This version deliberately does no automatic extraction, automatic context injection, remote sync, or references to material outside the workspace.

## Run and Observe

The point to observe in this lesson is not "it remembered a sentence" but confirming that memory writes really go through boundary control. Run:

```bash
PYTHONPATH=src python -m pytest -q tests/test_memory_v040.py
```

You should see the tests pass and understand these results from their behavior: paging can find the 21st record; two Store
instances do not overwrite each other; an old call's `revision` conflict does not write to disk; a failed atomic write keeps the old file;
recovery does not replay the handler before the parent result is committed; the subagent's filtered view has no Memory tools.

## Version Features, Next Lesson, and Code Index

v0.40 completes explicit viewing, adding, revising, and forgetting of memories across tasks and processes. The next lesson answers another
question: once there are many memories, how does the Agent recall only the small amount relevant to the current task? Continue with
[Lesson 41: Relevant memory retrieval and bounded context](41-memory-retrieval.md).

- [`memory.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.40/src/mini_agent/memory.py): schema, workspace isolation, locking, and atomic commit.
- [`tools/memory.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.40/src/mini_agent/tools/memory.py): the five parent Agent tools.
- [`tools/__init__.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.40/src/mini_agent/tools/__init__.py): the parent registry binding point and subagent isolation entry.
- [`test_memory_v040.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.40/tests/test_memory_v040.py): an executable index of this lesson's behavior boundaries.

# Stage 11: Lightweight Memory, Relevance Retrieval, and Reference Material Implementation Plan

> Status: `v0.40`–`v0.42` implemented
> Suggested version range: `v0.40`–`v0.42`
> Capability prerequisites: State / Context separation from Stage 4, project instructions from Stage 5, durable tool boundaries and crash recovery from Stage 9, parent/child permission boundaries from Stage 10
> Related plans: `context-management-plan.md`, `session-persistence-resume-plan.md`, `subagent-delegation-plan.md`

This plan borrows from OpenCode's separation of project instructions from material read on demand, and from its References' named directories, descriptions, and ordinary tool permission boundaries; it does not claim that OpenCode already provides the same durable Memory as this document. References: [OpenCode Instructions](https://opencode.ai/v2/docs/instructions), [OpenCode References](https://opencode.ai/v2/docs/references). This stage implements only local, standard-library-driven capabilities and introduces no vector database, embedding service, or remote repository cache.

## 1. Goal and Positioning

After Stage 10, `mini_agent` can investigate, delegate, execute, and recover within a single task, but the `history` kept across tasks is not a maintainable long-term knowledge base. History is trimmed and compacted, `AgentState` resets with new tasks, and a session is the recovery record of one session. The project instructions `AGENTS.md` suit rules that must be followed, not ever-growing ordinary findings.

The question Stage 11 answers is: **how can the Agent find a small amount of sourced project knowledge in later tasks, and consult material outside the project on demand, without mistaking old content for current instructions or verification facts?**

One-sentence goal: **build lightweight durable Memory isolated per workspace, provide bounded relevance retrieval, and let named local References be read by the Agent through the existing permission boundaries.**

Target flow:

```text
explicit write request ──→ PermissionGate ──→ workspace Memory file
                                                 │
new task ──→ retrieve relevant entries ──→ a few hit summaries ──→ parent Context
                                └── read the original by ID ──┘

local References configuration ──→ alias, description, real directory
user or model consults by alias ──→ path and permission checks ──→ bounded file fragments and sources
```

Each of the three versions teaches one concept: `v0.40` solves "what is worth saving across sessions and how to change it safely", `v0.41` solves "when to recall and how to explain hit sources", and `v0.42` solves "how to read local material outside the workspace by name". All three versions are implemented.

## 2. Scope and Non-Goals

### 2.1 Scope of this stage

- Each normalized workspace has its own independent, durable memory collection; it is available across tasks and sessions, regardless of whether `/save` is on.
- Memories support viewing, adding, revising, and forgetting. All changes are triggered by explicit tool calls and go through the existing permission and durable tool boundaries; nothing is extracted from conversations and written automatically.
- Each memory contains at least a stable ID, title, body, tags, source description, and update time; the format has a schema version and size limits.
- Use standard-library keyword matching, field weighting, and deterministic ranking to return bounded summaries; read the original by ID when details are needed.
- References mean only configured local directories. Aliases and descriptions help discovery; listing, searching, and reading all give checkable paths and line numbers and follow existing permissions.
- Retrieved and referenced content enters the Context as untrusted material, not the protected project instructions, `verification_evidence`, or parent/child authorization state.

### 2.2 Not in this stage

- No vector store, embeddings, semantic similarity service, full-text index service, or automatic web crawling.
- No automatic memory extraction, automatic conflict resolution, implicit writes, or "self-learning" without a basis visible to the user.
- No bulk import of session history, State snapshots, Trace, or raw tool output into Memory.
- Memory is not a replacement for `AGENTS.md`; imperative text in it cannot override the system prompt, project instructions, Plan, or PermissionGate.
- No remote Git References, background refresh, network downloads, or cached repositories. If needed later, network permissions, pinned versions, and refresh consistency must be defined separately.
- References do not expand the subagent allowlist; in Stage 11, only the parent Agent uses the memory and reference tools by default.

## 3. Architecture Decisions to Freeze First

### D1: Memory is independent durable material, not a new field of State, Context, or the session

Memory is kept long-term per workspace; `AgentState` still represents only current task facts, `ContextManager` still builds a bounded view each round, and the session still stores the State, Context, and tool boundary needed for task recovery. `/save` remains the only entry for session persistence and does not control whether Memory is written to disk.

The default storage root is in the user's local data area, with a directory key derived from the normalized workspace path that contains no plaintext path, and it is not written into the project working tree. Explicit configuration can change the storage root, but the target must be validated when configuration loads, and the real `BASE_URL`, `API_KEY`, `MODEL`, or auth headers must not be written into memory metadata. A moved workspace is treated as a new identity; migration is an explicit user operation, and two memory sets are never merged silently.

### D2: Writes only through explicit tool calls; changes always count as side effects

The parent Agent can propose add, revise, or forget calls; the Executor first checks arguments, phase, and the PermissionGate, and only then enters the handler. `remember`, `revise_memory`, and `forget_memory` are all `effect_class=possible` and cannot be downgraded to read-only just because the content is only text. The user can review the title, body, source, and target ID; the model must not turn a conversation into Memory in bulk automatically.

In the read-only planning `exploring` phase, the observation-only phase during recovery, and subagent Runtimes, memory changes are refused under the existing rules. The first version keeps the generation reservation and verification invalidation rules of `effect_class=possible` with no special case for memory writes; a memory write itself forms no verification evidence, and "remembered" cannot be taken as "the code is verified".

### D3: Use a small versioned JSON store with atomic replacement and protection against lost concurrent updates

The first version uses a single per-workspace JSON file and the standard library. Before writing, validate the schema, ID uniqueness, entry count, field lengths, and the total byte limit; first write a temporary file in the same directory and `fsync` it, then replace atomically, syncing the directory when needed. Multi-process writes need a per-workspace lock with a bounded wait; an in-process `threading.Lock` alone is not enough. A corrupted file or unknown schema should return an explicit error and keep the original file, never silently rebuilding it as an empty collection.

Suggested field contract:

```text
memory_id       # allocated by the Runtime, stable, contains no body text
title           # short title
body            # bounded body
tags            # bounded list of strings
source          # user note or checkable local source; must not pose as verification evidence
created_at
updated_at
```

A revision uses `memory_id` plus an expected version or content digest for optimistic concurrency checks, preventing an old call from overwriting new content; forgetting deletes by ID and returns an explicit result. The durable file does not need to store query caches or retrieval scores.

### D4: Memory writes connect to the schema 3 tool boundary with the existing crash semantics

With `/save` on, Memory changes, like ordinary side-effect tools, must first commit `handler_admitted` before calling the handler; each call's State, matching `role=tool`, and boundary are committed in model order. A commit failure must not enter later calls or the next LLM request.

If the Memory file has been replaced atomically but the parent tool result has not yet been committed durably, on recovery the call is "admitted, result uncertain": the source session stays read-only, it cannot be replayed automatically, and the old call cannot be forged as successful just because the current file happens to contain the new content. The user can check the current facts with read-only memory viewing, then handle the issue with `/resolve`. Stable IDs, content digests, and optional call association information are used only for checking or safe retry design and do not change the recovery rules of v0.33.

### D5: Retrieval provides candidates and sources; it does not promote them automatically to facts or instructions

`v0.41` uses NFKC and case normalization, contiguous token and CJK two-character fragment matching, title and tag weighting, and secondary matching on source and body; it does not depend on a third-party tokenizer package. The same query on the same store snapshot gives a stable order. Explicit search returns 5 entries by default and at most 10; automatic candidates are at most 4 entries with an information block of at most 2400 characters; an empty query does not return all bodies. In v0.41, the free-text `source` of schema 1 always returns `source_status="unverified"`; the source string is not accessed and file freshness is not claimed; source change detection is left to v0.42 References.

Retrieval results include the ID, title, excerpt, source, update time, and score or hit reason. When the model needs specific details, it calls the read-only `read_memory(memory_id)`. v0.41 uniformly returns `source_status="unverified"` for schema 1's free-text `source`, does not access paths that may appear in it, and does not claim the file is still fresh; structured sources, observation digests, and change detection are left to v0.42 References. Memory content is presented in the prompt as an information block and cannot override higher-priority instructions.

### D6: The Context receives only a bounded relevant view; history and State are not polluted by Memory

`v0.40` can first view memories through explicit read-only tools without automatic injection. `v0.41` already retrieves candidates relevant to the current task at the single Context entry before each model request and selects a few summaries into budget management; it does not repeat full text every round or squeeze out recent tool results. A retrieval failure only produces an observable degradation of the current Context and does not change the parent Runtime's top-level LLM exception boundary.

Memory hits belong only to that round's context view; they are not written into the authoritative fact fields of `AgentState`, do not fill `verification_evidence`, and do not rewrite history messages. Trace can show the retrieval operation and a source summary without sensitive content, but it cannot turn read-only Trace & Replay into a real retrieval or file access.

### D7: References are named local directories; an alias grants no permission

Configuration entries define an `alias`, a local `path`, and an optional `description` for each reference. A relative path is resolved based on the location of the configuration file; the normalized real directory is frozen at startup. The `description` can serve as a bounded discovery hint, but the directory contents are not read into the system prompt automatically. Invalid aliases, duplicate aliases, missing paths, and non-directory paths should be refused explicitly.

Reference tools accept only an alias and a relative path inside that directory. Every actual access validates that the real path and symlink target are still inside the approved directory and decides reading through the existing PermissionGate; configuring a reference does not automatically approve reading or editing the directory. The first version of the reference tools provides no writes. If a file changes between listing and reading, the real content, path, line numbers, and optional digest of this read prevail; an old retrieval hit is not treated as a fixed snapshot.

### D8: Subagents and sensitive paths keep narrower boundaries

Stage 11 does not add Memory or References tools to the subagent's fixed allowlist. Even if the parent Agent gets a path through a reference, what it passes to a subagent can still only be bounded investigation material that went through the existing selected facts and scope gate; a child result also cannot upgrade a Memory hit into parent task verification. Memory writes and References reads must both prevent sensitive paths such as credential files, session storage, and memory storage from being bypassed through explicit paths or symlinks. The ScopeGate sensitive path acceptance issue recorded in the Stage 10 plan should be rechecked first; new aliases must not widen the gap.

## 4. Version Slices and Implementation Tasks

### 4.1 `v0.40`: Lightweight durable Memory

The goal is that a piece of project knowledge written through an explicit tool call can still be viewed, revised, and forgotten after a process restart.

1. Add `memory.py`: workspace identity, schema validation, size limits, atomic load/save, a cross-process lock, and error types; no third-party dependencies.
2. Add parent-Runtime-only memory tools; register them in `tools/__init__.py`, executed through the existing Executor, PermissionGate, planning gate, and durable tool boundary. Tool names and arguments are frozen at implementation and written into the tutorial; suggested: `list_memories`, `read_memory`, `remember`, `revise_memory`, `forget_memory`.
3. When the CLI creates or resumes the parent Runtime, it binds the same workspace MemoryStore; the session keeps at most a storage identity summary without sensitive paths and does not copy the full Memory.
4. Cover adding, concurrent revision conflicts, forgetting, reading after restart, file corruption, write failures, permission denials, and recovery when the handler ran but the parent commit failed.

Acceptance: committed memories can be read across processes without `/save`; rejected or invalid calls do not change the file; crash recovery does not automatically replay admitted memory changes.

### 4.2 `v0.41`: Relevance retrieval and bounded context (implemented)

The goal is to find a few candidates relevant to the current task among many memories, instead of stuffing all memories back into the prompt.

1. Implement standard-library retrieval, deterministic ranking, and entry count and character budgets in `memory.py` or a separate `retrieval.py`; support the most basic keyword/phrase queries in both Chinese and English.
2. Provide an explicit `search_memories(query, limit)` that returns the ID, a short excerpt, the source, and a staleness hint; the original is still read with `read_memory`.
3. Connect a switchable relevant candidate view to the budget flow of `ContextManager.prepare_messages()`, running "base Context trim/compact → single retrieval → candidate fitting → final trim", stating explicitly when it refreshes, how it deduplicates, and how low-ranked candidates are dropped when the budget is short. One prepare reads only one Memory snapshot and produces at most one retrieval event; the default limits stay very small, and `history` or `AgentState` must not be changed.
4. Cover relevance, tie ordering, Chinese queries, empty queries, many entries, unverified sources, budget pressure, retrieval failure degradation, and the explainability of results after session recovery.

Implementation boundary: adds `retrieval.py` and `MemoryStore.snapshot()`, registers the read-only
`search_memories` on the parent side, and in `ContextManager.prepare_messages()` refreshes at most 4 candidates from the task description and the latest user message. The information block is an ephemeral system view with its own `memory` token bucket and two kinds of
Context events that leak no bodies/paths; it does not enter history, State, session, Plan, Trace, or
`verification_evidence`. On recovery, the retriever is rebound from the current workspace store, and old candidates are not restored; the child
Runtime binds no retriever. A failure only injects a bounded notice and retries on the next request.

Acceptance boundary: v0.41 does not implement source file change detection, References, vector retrieval, embeddings, automatic memory
extraction, query caching, or remote material reads.

Acceptance: a new task across sessions can see relevant memory summaries and read the original by ID; irrelevant entries do not enter the Context in bulk; when an old file changes, the source marker does not claim it is still fresh.

### 4.3 `v0.42`: Local References (implemented)

The goal is to let local material outside the workspace be discovered and read by stable aliases while keeping tool permission and path boundaries.

1. Add local reference mappings to ordinary configuration; real model service configuration still goes only in `config_local.py`. The real root path of reference configuration is not additionally written into State, session, or Trace metadata; the relative paths actually accessed may still be saved with tool results in the Context and session.
2. Add `references.py` to resolve aliases, descriptions, and real directories; implement named listing, searching, and segmented reading. Reuse the output limits of the file tools or set equivalent limits, and output the alias, relative path, line numbers, and a content digest.
3. Register read-only reference capabilities in the parent tool view; each operation separately goes through the PermissionGate, real path checks, and sensitive path exclusion. Do not connect reference directories to `write_file` / `edit_file`, and do not widen the subagent allowlist.
4. Cover relative path resolution, missing directories, traversal and symlink escape, permission denials, file changes, search limits, and multiple aliases not reading across each other.

Implementation boundary: the configuration entry is `REFERENCES = [{"alias", "path", "description"}]`, resolved relative to the directory of
`config_local.py`, with the real directory frozen when the parent Runtime is created. The parent side provides
`list_references()`, `search_reference(alias, query, path=".", include="*", limit=20)`,
and `read_reference(alias, path, offset=0, limit=200)`; listing is allowed by default, and search and read ask by default;
the permission pattern is `alias:relative_path`, and `always` remembers only the exact pattern. Search is case-insensitive
literal matching, and both read and search return the relative path within the alias, line numbers, and the
SHA-256 computed for this read; a single file is at most 1 MiB, and search accesses at most 2,000 files and 10,000 directory entries and reads 64 MiB of
content, keeping 100 hits, with output trimmed safely by a JSON byte limit; display trimming and `scan_truncated`
separately mean that the result set was trimmed and that the material scan did not finish.

The real roots of References exist only in the in-process `ReferenceCatalog`. `config_local.py`, the Memory
root directory, the default session root directory, out-of-bounds paths, directory symlink escapes, and non-UTF-8/special files are all
refused or skipped; bodies exist only as ordinary tool history results, and State/Trace excerpts keep only source
summaries. Access failures are raised by the handler and recorded by the Executor as `outcome="failed"`,
`error_kind="reference_access_error"`; file opens recheck the canonical
path segment by segment from the frozen root directory fd, and refuse to read on race changes. It does not enter automatic Context retrieval, Memory, verification evidence, or the Subagent allowlist,
and does not change the session schema. The free-text `source` of Memory schema 1 still uniformly returns
`source_status="unverified"`; this version did not migrate that boundary.

Acceptance: configured local material can be found by alias and specific file locations cited; unauthorized directories, out-of-bounds paths, and sensitive files cannot be read through Reference configuration.

## 5. File and Boundary Mapping

| Location | Expected change | Responsibility |
|---|---|---|
| `src/mini_agent/memory.py` | New | Versioned durable storage, concurrency control, record contract, and retrieval basics |
| `src/mini_agent/retrieval.py` | New depending on implementation size | Relevance ranking and bounded results; takes no part in LLM calls |
| `src/mini_agent/references.py` | New in `v0.42` | Local alias configuration, path validation, read sources |
| `src/mini_agent/tools/` | Incremental per version | Tool schemas, handlers, and read-only/side-effect classification |
| `src/mini_agent/context.py` | Changed in `v0.41` | Brings candidates into the budget as a trimmable view |
| `src/mini_agent/__main__.py`, `config.py` | Incremental changes | Parent Runtime assembly, workspace identity, and local reference configuration |
| `src/mini_agent/state.py`, `session.py` | Avoid schema changes | Only reuse the existing side-effect, tool boundary, and recovery contracts; if a field must be added, first prove old sessions stay compatible |
| `docs/tutorials/`, the operation manual, README, CHANGELOG | Synced per version | One teaching thread per version, configuration and recovery notes |

## 6. Cross-Cutting Acceptance and Delivery

- Memory CRUD, retrieval, and reference reads all have related unit tests; side-effect writes have tests for permission denial, durable boundary failure, and crash recovery.
- Memory and reference content cannot be injected into protected instructions, cannot create Plan progress or verification evidence, and cannot make the read-only planning phase perform writes.
- The default install and core paths still depend only on the standard library; the existing `http.client`, `Accept-Encoding: identity`, and parent/child model bindings are unaffected.
- `v0.40`–`v0.42` each have their own tutorial, change record, operation manual notes, and reproducible acceptance scenarios; when completing each version, sync the README, the tutorial index, and the version information. Git tags are operated only manually by the user.
- Each version runs at least the tests related to its changes; before delivery, run `PYTHONPATH=src python -m pytest -q`, `PYTHONPATH=src python scripts/check_tutorials.py`, and `PYTHONPATH=src python scripts/check_readme.py`, or state why they cannot run.

After Stage 11, the Agent can keep a small amount of revisable project knowledge across sessions, recall sourced fragments when relevant to the task, and consult local reference directories by alias. Memories and references are still only material for the model to judge; the current task's permissions, execution facts, and completion verification remain the responsibility of the existing Runtime boundaries.

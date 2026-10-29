# Mini Agent Context Composition: A Dynamic View

> Source of truth: `__main__.py`, `agent.py`, `context.py`, `state.py`, `prompt.py`, `instructions.py`, and `tools/base.py` under `src/mini_agent/`.

## 0. Mental Model: The One-Sentence Version

**The context is not a store but a view recomputed every round**. v0.20 also injects the Repair Loop phase as critical state that must not be lost, and v0.22 puts the bounded execution view of the active Plan Contract on the same semantic track; v0.24 continues by adding the active replan trigger, the revision budget, and LoopStagnationState; v0.33 then adds a protected crash recovery summary: what the model sees is not "what the most recent text said" but the current plan, step dependencies, real trigger sources, unsettled issues, and whether read-only investigation, replanning, or independent verification is required. The full `plan_revisions`, `plan_progress_history`, and crash recovery records are kept in State, and Structured State shows only bounded summaries; v0.21's Trace still degrades safely to empty when `todo_revisions` is missing.

```text
view = Runtime Notice? + read-only base (System Prompt) + [Structured State] (semantic track, including the Repair Loop phase)
     + [Relevant Memory — Untrusted Reference]? + [Historical Summary]? + Task + history rounds (protocol track)
     —— then once more through the budget gate
```

- **One read-only base**: `protected_messages`, built once at startup and never changed.
- **Two write tracks**: the same tool execution is recorded twice — the protocol original in `history` (read directly by the LLM, can be trimmed) and the semantic facts in `AgentState` (immune to trimming, re-rendered every round).
- **One feedback loop**: when the view exceeds the budget, what gets rewritten is the view itself (trim → compact); the `history` itself always stays complete.

The Memory added in v0.41 is not a fourth durable track but an information view generated temporarily every round:

```text
[schema 1 JSON outside the workspace]
            │ snapshot() (read-only validation, deep copy; no directory creation, no write lock)
            ▼
MemoryRetriever (NFKC/casefold, tokens/CJK two-character fragments, field weights, stable ranking)
            │ at most 4 entries, at most 2400 characters; a failure produces only a bounded degradation notice
            ▼
[Relevant Memory — Untrusted Reference] (a single temporary system message)
            │ inserted after [Structured State], before the first user task
            ▼
not written back to history, AgentState, session, Plan, Trace, or verification_evidence
```

The parent Runtime rereads the current snapshot on every `prepare_messages()`. The query consists only of the stable
`AgentState.task` and the latest `role=user` text in the full local history; assistant output,
tool results, history summaries, and Memory bodies never expand the query in reverse. The child Runtime binds no retriever,
so it has neither Memory tools nor automatic candidates.

## 1. Main Diagram: One Round's Context Production Line (Closed Loop)

```text
Startup (__main__.py main(), done only once per process)
│
├─ InstructionLoader.load()      collect AGENTS.md level by level from root→cwd, merge and truncate to ≤12000 characters
├─ build_system_prompt()         header identity + core_rules + <env> environment + project instructions
└─ protected_messages            read-only base: never changes, never touched by trimming


User task (run_task, can happen several times per session)
│
├─ state.begin_task(task)        the semantic track is reset (history is not cleared and persists across tasks)
└─ history += {role:user}        enters the protocol track and becomes the never-deleted Task anchor


Each agent_loop round (agent.py:141, limit MAX_ITERATIONS=50)
│
│  ① Merge projection —— prepare_messages() (context.py:405); the context is born at this moment
│  │    view = [Runtime Notice]?        one-time reminder, inserted at the very top, consumed once sent
│  │         + System Prompt            from protected_messages (copied)
│  │         + [Structured State]       from state.snapshot(), re-rendered this round
│  │         + [Relevant Memory]?        single-snapshot retrieval after base trim/compact, then candidates fitted to the budget
│  │         + [Historical Summary]?    from compact(); exists only if compaction was triggered
│  │         + Task                     the first user message
│  │         + history rounds           assistant + its tool results, grouped atomically
│  │    Budget gate: truncate large tool results → delete the oldest whole rounds → compact-summarize old rounds
│  ▼
│  ② call_llm(view)              streamed send, receive the assistant reply
│  │
│  ③ Branch
│  ├─ No tool_calls: check completion conditions (active plan all complete + verification passed after the latest change; without a plan, take the Direct Path)
│  │     ├─ met → finish and return
│  │     └─ not met and not yet reminded → set_runtime_notice → back to ①
│  │           (reminded only once; if still not met, status=blocked and return)
│  │
│  └─ Has tool_calls: ThreadPoolExecutor runs them concurrently (including PermissionGate interception)
│        │
│        │   ★ The same execution writes both tracks; stagnation is observed after all role=tool results are fed back:
│        │
│        ├─ Protocol track: history += {role:tool} (full original result)
│        │     read directly by the LLM next round; subject to the budget, may be truncated/folded
│        │
│        └─ Semantic facts: structured ExecutionResult → state.record_execution_result (the compatibility callback can still write record_tool)
│              files_changed / errors / active plan / verification evidence
│              immune to trimming, rendered into [Structured State] next round to anchor the facts
│
└──► The two tracks merge again at ① in the next round —— loop until a plain-text finish or the round limit
```

On resume there is another fact that cannot be trimmed: `crash_recovery` issues are inserted into Structured State, and the original arguments and stdin bodies do not enter the summary. While unsettled issues exist, the agent loop allows only read-only investigation; after all issues are settled, it must go through a new plan and verification before it can finish.

The Repair Loop phase constraints are also re-rendered here: `diagnosis_required` requires read-only investigation, an exclusive `recover`, or an exclusive `request_replan`; after a failure trigger enters Explore, only read-only investigation or an exclusive `commit_plan` is allowed; `verification_required` requires that the next round contain only one independent verification. v0.24's stagnation counts, short hashes, active trigger source, and the gate's legal next actions also come from the same State snapshot. v0.33's unsettled crash issues further narrow the gate to side-effect-free observation and cannot be overwritten by history trimming or summaries. Context compaction only handles the protocol history and cannot delete the plan execution view, `repair_loop`, the active failure/recovery, crash recovery, generations, budgets, or stagnation state.

## 2. Key Mechanism 1: Dual-Track Recording (the Core Trade-Off of This Architecture)

Why write two copies of one execution? Because **the protocol history can be damaged by the budget, while the facts must survive**.

| | Protocol track `history` | Semantic facts `AgentState` |
|---|---|---|
| Writer | `agent_loop` feeds back `role=tool` messages | Structured `ExecutionResult → AgentState.record_execution_result`; the compatibility entry can use `on_result → record_tool` |
| Content | Full original result (command output, file fragments) | Brief truncated to ≤200 characters + derived facts |
| Fate under the budget | Can be truncated, deleted as whole rounds, folded into the summary | **Immune to trimming**, fully re-rendered every round |
| How it is read | Enters the view as the original text of history rounds | Rendered as `[Structured State]` (context.py:312) |
| Lifetime | Accumulates across tasks (session level) | Reset by `begin_task` (task level) |

Two special cases serve the same design:

- `commit_plan` / `update_plan_progress`: plan intent is not an environment execution fact; these two state-bound tools write immutable revisions/events directly; they do not advance the generation and produce no verification evidence. Structured State shows only the active plan execution view derived from State.
- `run_shell(purpose="execution"/"verification")`: execution is treated as changing the environment → all verification evidence is invalidated; a passing verification → the evidence is recorded and the "verification required" flag is cleared. Distorted evidence is more dangerous than missing evidence, so it is better to invalidate and start over.

## 3. Key Mechanism 2: The View Evolves With the Rounds

Within one task, the messages sent in round 1 / N / M look like this (top to bottom is the actual order):

```text
Round 1 (task just assigned)
  System Prompt
  [Structured State]        Task=fix the login bug | Tools: 0 | Status: running
  user: fix the login bug
  (no history yet)


Round N (history grows, facts accumulate)
  System Prompt
  [Structured State]        Plan revision=1 | step=inspect | Files: auth.py | Errors: 1
  user: fix the login bug
  assistant(tool_calls: read_file, update_plan_progress)
  tool: <file content>      ┐
  tool: ok                 ├─ round = assistant + all its tool results
  assistant(edit_file)     │  grouped atomically, never producing orphan tool results
  tool: ok                 ┘
  … (history grows round by round, tokens approach the budget)


Round M (over budget, compaction triggered)
  System Prompt
  [Structured State]        semantic facts lossless: what changed and whether verification passed are all there
  [Historical Summary]      ← old rounds folded into a structured summary (incrementally updated along the summarized boundary)
  user: fix the login bug
  assistant(tool_calls: run_shell)
  tool: [exit=0] …          ← only the last keep_rounds=6 rounds of original text are kept
```

Note two things: `[Structured State]` sits **before** the Task (inserted before the first user message); after compaction, the "middle" of the history is replaced by the summary, but **the head (Task) and the tail (last 6 rounds) stay faithful** — the model always knows why it is here and what it just did.

## 4. Key Mechanism 3: The Budget Feedback Loop

```text
window = CONTEXT_WINDOW
├─ reserve   15%              output reserve, not sent
└─ input_limit 85%
   ├─ system / task / state / memory   protected area: candidates are dropped as a whole first; trimming never cuts half an entry
   └─ history / tool_result   compressible area: limit about window × 45% (history_ratio)
```

When over budget, it takes three steps in the order "smallest loss first", all applied only to the view copy (the `history` itself is untouched):

1. **Truncate tool results**: only tool content longer than 120 characters is truncated, keeping the beginning and end + `[... omitted N characters ...]`; protocol fields are unchanged.
2. **Delete whole rounds atomically**: the oldest rounds go first; an assistant message and its tool results live and die together.
3. **compact()**: complete rounds older than the last 6 are given to the LLM for a tool-free summary (task/completed steps/last successful call/changed files/errors/progress/next steps); on failure, it degrades to trimming only.

Exact threshold: `message_limit = max(protected, min(input_limit, protected + history_limit))` (context.py:115) — no matter how large the protected prefix is, it is never deleted by mistake; in extreme cases the limit is simply relaxed.

## 5. Invariants

1. The System Prompt and the first user message are never deleted; rounds are atomic, with no orphan tool results.
2. `history` is append-only and never modified; trim/compact change only the copy — any round's view can be rebuilt from the full history.
3. The next round starts only after all tool results of each round are fed back (no "half state" as in v0.10).
4. Semantic facts are immune to trimming: no matter how much the protocol history is cut, `[Structured State]` is fully re-rendered every round.
5. A Runtime Notice is sent only once, and is consumed only after the final view is built successfully (context.py:429) — rebuilding messages during compaction never swallows a reminder; v0.20's phase Notices state the next legal action explicitly, and v0.24's stagnation Notice also shows the count, the category, and the next actions that satisfy both the Planning and Repair gates.
6. Trace & Replay reads the separate `state.snapshot()` view; it does not enter LLM messages, does not call the execution chain, and does not change the context or State.
7. Observability and result callbacks are pure observers; their exceptions are swallowed (base.py:128, context.py:281) and do not break execution.

8. v0.41's Memory information block follows "base Context trim/compact → single retrieval → candidate fitting → final trim",
   and each request uses only one Memory snapshot; it exists only in the prepared view. `ContextStats.memory` counts it separately,
   and `memory_retrieved` / `memory_retrieval_failed` happen at most once per prepare, recording only bounded metadata, never bodies or real storage paths.
9. v0.33's `crash_recoveries`, `crash_issues`, and `crash_decisions` are recovery facts that cannot be trimmed; Structured State shows only bounded summaries, including the issue ID, tool, classification, admission status, public reason, and next action, never the original arguments, shell commands, or stdin. While unsettled issues exist, only approved side-effect-free observation is allowed, and after all issues are settled, a new plan and independent verification are still required.

## 6. Code Quick Reference

| View component | Produced at | Update frequency |
|---|---|---|
| System Prompt | `prompt.py:112` + `instructions.py:48`, assembled in `__main__.py:30` | Once per process |
| `[Runtime Notice]` | `context.py:414` (set by `set_runtime_notice`) | Single request |
| `[Structured State]` | `context.py:312 _render_state` ← `state.py:171 snapshot` | Every round |
| `[Relevant Memory — Untrusted Reference]` | `retrieval.py` → `context.py:prepare_messages()` | Every parent-side request; temporary view |
| `[Historical Summary]` | `context.py:360 compact` ← `agent.py:136 summarize_messages` | Incrementally after compaction |
| Task / history rounds | appended by `__main__.py:45`, `agent.py:236,304` | Event driven |
| Semantic facts | `agent.py` commits `ExecutionResult` → `state.py record_execution_result` | Every structured tool execution |

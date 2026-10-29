# Stage 4: Context Management Implementation Plan

> Status: v0.11/v0.12/v0.13 implemented and accepted; Context Observability merged into v0.13
> Review conclusion: the original six-Phase plan had the right dependency order and principles but was too fine-grained, so it was merged into three versions; corrections are listed in "Key Architecture Decisions"
> Version mapping: v0.11 / v0.12 / v0.13 (the tag name v0.011 was dropped; see D8 for the reason)
> Related documents: `teaching-repo-plan.md` (version slicing table synced); runtime hard constraints are in `AGENTS.md`

## 1. Goal and Positioning

Make Context Management teaching **Stage 4** (after Stage 1 Agent Loop, Stage 2 Tools and Safety, and Stage 3 Mini Agent Milestone), delivered in three sub-stages:

| Sub-stage | Version | Topic | Merged from original plan | Tutorial |
|---|---|---|---|---|
| 4.1 | v0.11 | Context architecture | Phase 0 + Phase 1 | `11-context-architecture.md` |
| 4.2 | v0.12 | Budget and trimming | Phase 2 + Phase 3 | `12-token-budget-trimming.md` |
| 4.3 | v0.13 | Context compaction | Phase 4 + raising `MAX_ITERATIONS` | `13-context-compaction.md` |

Main thread of the stage: **4.1 is a conceptual revolution (Agent State ≠ LLM Context), 4.2/4.3 are engineering** — change the worldview first, then the code.

The original plan's Phase 5 (Tool Result Management) and Phase 6 (External Memory & Retrieval) are not part of this stage: the minimal subset of Phase 5 (the 2000-character `run_shell` truncation) already landed implicitly in v0.10, and the rest is merged into an optional v0.13 wrap-up or used to open Stage 5, decided at implementation time; Phase 6 belongs to Stage 5.

## 2. Key Architecture Decisions (Review Corrections)

The decisions below are constraints set by the plan review; do not deviate from them during implementation:

| # | Decision | Reason |
|---|---|---|
| D1 | **Agent State ≠ LLM Context**: `AgentState` is an independent object and never takes part in trimming/compaction | State is the anchor that keeps memory after compaction; the PermissionGate's always state already proved this separation works |
| D2 | **Token counting uses the heuristic `len(text) // 3`** (mixed Chinese/English scenarios); no tiktoken | Zero third-party dependency constraint; the estimate only feeds trim decisions, so ±20% error is harmless |
| D3 | **Trimming deletes atomically by round**: a round = assistant(tool_calls) + all its tool results, never split | The OpenAI protocol requires a tool message to follow its tool_calls immediately; an orphan tool result is a straight 400 |
| D4 | **The budget uses ratio configuration**, not a fixed K count | Adapts to different model windows; system/task floor + history/tool by ratio + output reserve |
| D5 | **State is updated by an Executor result callback**; the loop is unaware | Otherwise State would become a second messages list that nobody maintains |
| D6 | **A compaction summary failure degrades to plain trimming** without crashing | Fault tolerance lives in the ContextManager layer, not the loop — keeping the existing constraint "no try/except fallback in the loop" |
| D7 | **The Summary may be lossy; State must be accurate**: acceptance of repeated compaction looks at State and does not demand summary quality | summary-of-summary inevitably drifts; State is the correction anchor |
| D8 | **Tag name v0.11 (v0.011 dropped)** | v0.10 already exists; v0.011 visually looks like a patch of v0.01 and sorts ambiguously; v0.11 is the natural continuation of v0.10 |

## 3. v0.11 Context Architecture (4.1)

### Goal

In one sentence: **Agent State is independent of messages, and ContextManager becomes the single entry before LLM calls.** This version is a pure refactoring; external behavior is exactly the same as v0.10 — concepts before engineering.

### New/changed files

| File | Action | Content |
|---|---|---|
| `src/mini_agent/state.py` | New | `AgentState` dataclass + execution record interface |
| `src/mini_agent/context.py` | New | `ContextManager` |
| `src/mini_agent/agent.py` | Changed | `agent_loop` calls the LLM through `prepare_messages()` |
| `src/mini_agent/tools/base.py` | Changed | Executor adds a result callback (D5) |
| `src/mini_agent/__main__.py` | Changed | Assembles AgentState + ContextManager and injects them into the loop |
| `tests/test_state.py` | New | State unit tests |
| `tests/test_context.py` | New | ContextManager unit tests |

### Interface skeleton

```python
# state.py
@dataclass
class AgentState:
    task: str = ""
    current_goal: str = ""
    tool_history: list[dict] = field(default_factory=list)  # {tool, args, ok, brief}
    files_changed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    status: str = "running"  # running / done / failed

    def record_tool(self, name, args, ok, brief): ...
```

```python
# context.py
class ContextManager:
    def __init__(self, state: AgentState, history: list[dict]): ...

    def prepare_messages(self) -> list[dict]:
        """Single entry before LLM calls. This version returns the full messages as is (sets the boundary, no trimming)."""
```

The internal layers (system / task / history / tool) only get code boundaries in this version; they are not customized separately.

### Task breakdown

1. `state.py` + `test_state.py` (done)
2. `context.py` skeleton + `test_context.py` (`prepare_messages` returns its input unchanged in this version; done)
3. Executor result callback → `state.record_tool` / `files_changed` / `errors` (D5; done)
4. Rework `agent_loop`: `call_llm(cm.prepare_messages())`; along the way, remove the caller contract behind the "MAX_ITERATIONS half state" comment in agent.py (done)
5. Manual regression: run typical v0.10 tasks, behavior unchanged (done; real LLM regression passed)
6. Tutorial `11-context-architecture.md` + CHANGELOG + version information + tag `v0.11` (done)

### Acceptance criteria

- [x] AgentState is an independent object; it does not enter messages and is not operated on directly by the loop
- [x] All LLM requests are built by ContextManager; the loop no longer assembles context directly
- [x] The boundaries of System / Task / History / Tool Result have explicit code locations
- [x] Behavior matches v0.10 (all existing tests green + manual task regression)
- [x] `git diff v0.10..v0.11 --stat` is on the order of "two new files + small changes to three or four files"

## 4. v0.12 Budget and Trimming (4.2)

### Goal

In one sentence: **Context is a limited resource: when over the limit, delete low-value information first instead of failing directly.**

### New/changed files

All extensions are inside `context.py`, plus configuration in `config.py`; no new files:

```python
def count_tokens(text_or_messages) -> int  # D2: len // 3

@dataclass
class ContextBudget:
    window: int                  # config: CONTEXT_WINDOW, default 128_000
    output_reserve_ratio: float  # default 0.15
    history_ratio: float         # default 0.45 (the system/task floor is deducted from it first)

class TrimPolicy:
    def trim(self, messages, budget) -> list[dict]  # returns trimmed messages and prints a trimming log
```

`config.py` adds `CONTEXT_WINDOW`; `prepare_messages()` checks the limit and enters trimming automatically when over it.

### Trimming algorithm (delete from lowest to highest value)

1. **Round splitting**: split messages into rounds per D3; system and the first user task never enter rounds
2. Truncate the content of tool results in old rounds (keep the beginning and end + an omitted-lines hint, replacing content in place)
3. Still over the limit → **delete whole rounds atomically**, starting from the oldest (D3)
4. Print a trimming log at each step (which rounds were deleted and how many tokens each saved) — an observation point for the tutorial

### Task breakdown

1. `count_tokens` + `ContextBudget` + unit tests
2. Round splitter + unit tests (build message sequences with tool_calls and verify the split is correct with no orphans)
3. Tool result truncation strategy + unit tests
4. Whole-round deletion + budget loop convergence + unit tests
5. Connect the limit check to `prepare_messages`; build a long task by hand (for example, have the agent `read_file` a large file repeatedly)
6. Tutorial `12-token-budget-trimming.md` + CHANGELOG + version information + tag `v0.12`

### Acceptance criteria

- [x] The token budget is checked before LLM calls, and trimming starts automatically when over the limit
- [x] Tool results can be truncated; history can be deleted by round
- [x] The system message and the first user task are never deleted under any circumstances (unit test assertion)
- [x] The trimmed message sequence is protocol-valid: no orphan tool results (unit test assertion, the D3 correctness red line)
- [x] The budget is configurable (window and ratios)
- [x] When over the limit, the agent does not crash and can continue the task
- [x] Trimming has an explicit priority and an observable log

## 5. v0.13 Context Compaction (4.3)

### Goal

In one sentence: **History cannot simply be deleted: old history is summarized into a Summary, and State anchors the facts.**

### Context structure after compaction

```
System
+ Current Task
+ Structured State (rendered from AgentState, the anchor of D7)
+ Historical Summary (can stack across compactions, may be lossy)
+ Recent Messages (original text of the last N rounds, default 6)
```

### Implementation points

```python
# context.py
def compact(self, keep_rounds: int = 6) -> None:
    """Old rounds -> a tool-free call_llm summary -> replaced with one summary message."""
```

- The summary prompt uses a fixed template: task / done / changed / conclusions / next steps (aligned with the Structured State fields)
- Trigger: triggered automatically when trimming has deleted down to "only the floor rounds left and still over the limit"
- A summary failure degrades to plain trimming, and the agent does not crash (D6, fault tolerance in the ContextManager layer)
- Structured State is re-rendered from `AgentState` and injected on every compaction (not appended), so repeated compactions do not inflate it
- `config.py`: `MAX_ITERATIONS` 10 → 50

### Task breakdown

1. Summary call (reuse `call_llm` without the tools argument) + fixed prompt template
2. Main `compact` flow + unit tests (mock LLM, zero network dependency)
3. Failure degradation path + unit tests
4. Structured State rendering and injection + unit tests
5. The trimming → compaction automatic trigger chain
6. Raise `MAX_ITERATIONS`; manual end-to-end long task verification (continue the original task after compaction; State stays accurate after repeated compaction)
7. (Optional wrap-up, prerequisite for Phase 5) Connect `read_file`/`grep` results to unified truncation handling
8. Tutorial `13-context-compaction.md` + CHANGELOG + version information + tag `v0.13`

### Acceptance criteria

- [x] Old history can be summarized automatically, and the agent can continue the original task after compaction
- [x] Structured State is always in the compacted context and is maintained by real execution records (not a summary paraphrase)
- [x] Recent history keeps the original text
- [x] On summary failure, it degrades to trimming and the agent does not crash
- [x] Repeated compaction is supported: after 2+ consecutive triggers, the State fields are still accurate (unit test, D7)
- [x] Long tasks (>10 rounds of tool calls) are not silently cut off by MAX_ITERATIONS

## 6. Test and Verification Summary

| Version | New tests | Manual verification |
|---|---|---|
| v0.11 | State record updates / prepare_messages identity build | Typical v0.10 task regression |
| v0.12 | Round splitting without orphans / floor not deleted / budget loop convergence | Read a large file repeatedly to trigger trimming and watch the log |
| v0.13 | compact mock / failure degradation / State accurate after repeated compaction / ContextStats buckets / trim and compact events / observer isolation | A 20+ round long task completes across compaction, while watching the Context, Trim, and Compact logs |

Testing principle: all unit tests mock the LLM (zero network dependency), in the style of the existing `tests/`; protocol validity (no orphan tool results) is the only red-line assertion.

## 7. Context Observability Enhancement

This capability is merged into v0.13 and does not take a separate teaching version. It provides Context token statistics for every LLM request and records trimming/compaction events; the detailed description is in the existing `docs/tutorials/13-context-compaction.md`.

- `ContextStats` uses the mutually exclusive buckets `system` / `task` / `state` / `history` / `tool_result`, with the output `reserve` listed separately.
- `ContextManager` keeps `last_stats` / `stats_snapshot()` and supports an observer callback; the default terminal output can be turned off with `CONTEXT_OBSERVABILITY = False`.
- Trim events include truncated or deleted rounds and the tokens saved; compact events include the compacted rounds, summary size, and recent rounds.
- The observation logic does not change history or the tool calling protocol; observer exceptions are swallowed.

Task breakdown:

1. Add `ContextStats`, `ContextEvent`, and default observer rendering.
2. Make TrimPolicy truncation/whole-round deletion observable events.
3. Emit events for compaction success and failure degradation.
4. Add tests for stats, events, the off switch, and observer isolation.
5. Add the Context Observability description to the v0.13 tutorial, and sync the tests and the operation manual.

Acceptance criteria:

- [ ] Every main LLM request outputs or records the final ContextStats, and the buckets sum up.
- [ ] Trim/compact logs include the object, round range, and token difference.
- [ ] Turning off the log does not affect snapshots, budgets, compaction, or agent behavior.
- [ ] All existing v0.13 tests and protocol validity tests pass.

## 8. Sync with Existing Documents

- `teaching-repo-plan.md`: the version slicing table / directory tree / usage guide table / code difference points are synced to v0.11–v0.13, and the plan guidance moves on to v0.14
- `AGENTS.md`: synced only when runtime constraints change; the version roadmap and teaching stages are maintained by the plans and the tutorial index
- `docs/plans/README.md`: this document has been added to the index
- `docs/tutorials/README.md`: Stage 4 changed to the three-version Context Management table
- `docs/tutorials/13-context-compaction.md`: Context Observability description added
- `README.md`, `README_EN.md`, `docs/operation/manual.md`, `AGENTS.md`, `pyproject.toml`: the enhancement is described as part of v0.13

# Stage 5: Project-Aware Task Orchestration Implementation Plan

> Status: complete (v0.14–v0.16 implemented and accepted)
> Version mapping: v0.14 / v0.15 / v0.16
> Prerequisite stage: `context-management-plan.md` (v0.11–v0.13)
> Related documents: `teaching-repo-plan.md`; runtime hard constraints are in `AGENTS.md`

## 1. Goal and Positioning

Make Project-Aware Task Orchestration teaching **Stage 5**. Stage 4 solved "remembering within a limited Context Window"; Stage 5 goes on to solve "understanding project constraints, being clear about the next step, and continuing until a verifiable completion".

One-sentence goal: **let the Agent first understand the current project's rules, then organize complex work with task state independent of messages, and finally form a closed loop of planning, execution, verification, and finishing.**

Stage 5 is delivered in three sub-stages:

| Sub-stage | Version | Topic | Core question | Tutorial |
|---|---|---|---|---|
| 5.1 | v0.14 | Project Instructions | Which rules must be followed in the current project? | `14-project-instructions.md` |
| 5.2 | v0.15 | Todo / Task State | What is planned, and how far has it got? | `15-task-state.md` |
| 5.3 | v0.16 | Plan-driven Execution | How to advance, adjust, and verify the plan based on results? | `16-plan-driven-execution.md` |

Main thread of the stage:

```text
discover and load project rules
        ↓
Plan: build a dynamic Todo that follows the rules
        ↓
Execute: run tools
        ↓
Observe: read tool results, errors, and environment changes
        ↓
Verify: run verification and record completion evidence
        └── problem found or verification failed → Replan: advance or adjust the Todo based on facts → Execute
```

These three versions are not three independent features: Project Instructions are the constraint input for planning, the Todo is the Agent's dynamic work plan, Execution State is the Runtime's facts, and Verification is the evidence of task completion; Plan-driven Execution makes them take part in the task lifecycle together.

## 2. Scope and Non-Goals

### 2.1 Scope of this stage

- Automatically discover and inject the `AGENTS.md` applicable to the current working directory
- Distinguish Project Instructions, Task State, Execution State, Verification, and the LLM Context
- Represent the dynamic work plan of complex tasks with an explicit Todo
- Let the model update the Todo through a controlled tool, instead of guessing progress from natural language
- Re-inject accurate project rules and task state after Context compaction
- Build a minimal "Plan → Execute → Observe → Verify" loop, and Replan and continue executing when a problem is found or verification fails

### 2.2 Not in this stage

- No separate Plan Agent, Explore Agent, or multi-agent collaboration
- No `--plan` read-only mode or plan approval/handoff protocol
- No loading of multiple instruction files such as `.cursorrules` or `CLAUDE.md`; the first version recognizes only `AGENTS.md`
- No cross-process Todo persistence; state still disappears when the process exits
- Project Instructions cannot change the runtime permissions of `PermissionGate`
- No structured extraction of explicit user constraints; the Todo is generated entirely by the model's own judgment, and verification evidence depends on side effects the model triggers, so the model may judge a task complete without meeting the user's literal requirements
- No automatic failure retry framework, checkpoint, transactional rollback, or sandbox isolation
- The core runtime introduces no third-party dependencies; the peripheral user experience can be enhanced by optional dependencies, but they must have a standard-library fallback and must not change the core protocol, permissions, or state semantics

These capabilities significantly change permissions, the executor, or the agent topology, and are left to later stages to introduce one by one.

## 3. Key Architecture Decisions

The decisions below are fixed before implementation, so the three versions do not each form their own state or rule system:

| # | Decision | Reason |
|---|---|---|
| D1 | **Project Instructions are protected context, not history** | Project rules should not be deleted by trimming or compaction together with old conversation |
| D2 | **The first version loads only `AGENTS.md`, scoped to the working directory at startup** | One version introduces only one concept; dynamic instruction discovery at the target-file level waits until a real need appears |
| D3 | **Multiple instruction levels are merged root → cwd, with closer files later** | The order is clear and lets the model treat more specific rules as higher priority; the code does not try to resolve natural language conflicts |
| D4 | **Project Instructions cannot relax the PermissionGate** | A prompt is a behavior constraint, not a security authorization; permissions are still decided only by `PermissionGate` |
| D5 | **Execution State and Task State share `AgentState`, but field ownership differs** | Avoids building a parallel `PlanState` while preventing the model from tampering with tool execution facts |
| D6 | **Execution State is maintained by the Executor callback; Task State is maintained by the model through the Todo tool** | Facts come from real execution and plans from model intent, so both sources are auditable |
| D7 | **The Todo is the working mechanism for complex tasks and does not force simple tasks to plan first** | Keeps the shortest path for simple tasks, avoiding meaningless calls for a single read or calculation |
| D8 | **At most one `in_progress` Todo at a time** | The current work focus is unique, and rendering and state transitions are easier to understand |
| D9 | **Compaction may re-render or structurally compress Task State, but must preserve meaning** | The current goal, Todo content and status, and blocking reasons must not be lost through lossy summaries like the Conversation History |
| D10 | **The Todo is the Agent's intent, Execution State is the Runtime's facts, and Verification is the evidence of completion** | The three have different, auditable sources; a plan declaration cannot replace execution facts or verification evidence |
| D11 | **Tool execution facts take priority over plan declarations, and verification evidence takes priority over "looks done"** | A Todo marked complete does not mean the task is really complete; file changes, command results, and test results must be recorded separately |
| D12 | **v0.16 first does single-agent plan-driven execution, without a separate Plan Mode** | First verify whether an explicit Todo is enough, then decide whether adding agent roles and a handoff protocol is worth it |

## 4. Context and State Model

The LLM Context after Stage 5:

```text
System Identity + Core Rules
+ Environment
+ Project Instructions       # static constraints, protected
+ Current Task
+ Structured State
  ├── Task State             # current_goal + dynamic todos
  ├── Execution State        # files_changed + errors + runtime facts
  └── Verification           # test/build/check evidence
+ Historical Summary
+ Recent Messages
```

Responsibility boundaries of the five kinds of information:

| Information | Source | Maintained by | Compressible? |
|---|---|---|---|
| Project Instructions | `AGENTS.md` | `InstructionLoader` | No |
| Task State | Todo / current goal / blocking reason | The LLM through the Todo tool | Can be re-rendered or compressed losslessly in structure, must preserve meaning |
| Execution State | Tool results / file changes / errors | The Executor callback | No; facts cannot be replaced by summaries |
| Verification | Completion evidence such as tests, builds, and checks | Tool result records, rendered by ContextManager | No; the evidence content must be accurate |
| Conversation History | user / assistant / tool messages | agent loop | Yes |

`AgentState` is the container for runtime facts, task progress, and verification evidence, but it cannot be opened to the model for modification as a whole. The Todo tool can update only Task State fields, the Executor still exclusively owns the raw execution records of Execution State and Verification; compaction is only responsible for re-rendering this structured information.

## 5. v0.14 Project Instructions (5.1)

### 5.1 Goal

In one sentence: **at startup the Agent automatically discovers the current project's `AGENTS.md` and injects the applicable rules into every LLM request as protected system context.**

### 5.2 New/changed files

| File | Action | Content |
|---|---|---|
| `src/mini_agent/instructions.py` | New | `InstructionLoader`: discover, read, and merge `AGENTS.md` |
| `src/mini_agent/prompt.py` | Changed | Adds layered rendering of `<project_instructions>` |
| `src/mini_agent/__main__.py` | Changed | Loads project instructions once at startup and injects them into the assembly flow |
| `src/mini_agent/context.py` | Changed | Makes Project Instructions explicitly part of the protected context |
| `tests/test_instructions.py` | New | Discovery order, missing files, read failures, boundary tests |
| `tests/test_prompt.py` | Changed | Prompt injection smoke test |

### 5.3 Interface skeleton

```python
class InstructionLoader:
    def __init__(self, cwd: str): ...

    def discover(self) -> list[str]:
        """Return the AGENTS.md paths in root → cwd order."""

    def load(self) -> str:
        """Read and merge by source in sections; return an empty string when none is found."""
```

Keep the sources when rendering, so the model and the user can locate the rules:

```text
<project_instructions>
Source: /repo/AGENTS.md
...

Source: /repo/subdir/AGENTS.md
...
</project_instructions>
```

### 5.4 Discovery and merge rules

1. Use the `cwd` at startup as the end of the scope
2. Inside a git repository, start searching from the repository root; otherwise check only `cwd`
3. Collect the `AGENTS.md` files on the path chain from the root to cwd
4. Merge in root → cwd order, with more specific rules later
5. Do not run commands in instruction files and do not turn them into permission rules
6. Set a simple standard-library limit on the total number of characters; when over it, keep the file sources and mark the truncation explicitly

The first version does not handle "dynamically switching rules when a tool later accesses directories outside or deeper than cwd". The tutorial must state clearly that this is the scope boundary of v0.14, to avoid claiming that target-file-level rule inheritance is implemented.

### 5.5 Task breakdown

1. `InstructionLoader.discover()` + temporary directory unit tests
2. root → cwd merge of multiple `AGENTS.md` levels + source markers
3. Empty files, no files, non-git directories, and read error paths
4. Add the Project Instructions layer to `prompt.py`
5. `ContextManager` treats the instructions as protected context and does not delete them even when over budget
6. Connect CLI assembly and verify by hand that the model can restate and follow repository-specific rules
7. Tutorial, CHANGELOG, README, version number, and tag `v0.14` (sync AGENTS.md when runtime constraints change)

### 5.6 Acceptance criteria

- [ ] The `AGENTS.md` applicable to the current working directory is discovered automatically
- [ ] Multiple levels of files are merged stably root → cwd, keeping source information
- [ ] Without `AGENTS.md`, behavior matches v0.13
- [ ] Project Instructions do not enter history and are not deleted by trimming/compaction
- [ ] Instructions cannot bypass `PermissionGate`
- [ ] The load limit and truncation behavior are tested and observable
- [ ] Unit tests do not depend on the real user directory or the network

## 6. v0.15 Todo / Task State (5.2)

### 6.1 Goal

In one sentence: **turn the dynamic work plan in the model's head into Task State that is independent of messages, verifiable, and recoverable after compaction.**

### 6.2 Data model

```python
@dataclass
class TodoItem:
    content: str
    status: str = "pending"  # pending / in_progress / completed


@dataclass
class AgentState:
    task: str = ""
    current_goal: str = ""
    todos: list[TodoItem] = field(default_factory=list)
    # existing Execution State fields unchanged
```

Have `AgentState.update_todos()` validate the invariants in one place, instead of letting the tool handler change the public list directly:

- `content` must be a non-empty string after trimming leading and trailing whitespace
- `status` can only be `pending / in_progress / completed`
- At most one `in_progress` at a time
- Set small limits on the Todo count and item length to keep Task State from growing without bound
- The tool uses "submit the full list" semantics; updates are atomic, and a validation failure writes no half state

### 6.3 New/changed files

| File | Action | Content |
|---|---|---|
| `src/mini_agent/state.py` | Changed | `TodoItem`, `todos`, atomic updates, and snapshot support |
| `src/mini_agent/tools/todo.py` | New | Creates the `update_todo` tool bound to the current `AgentState` |
| `src/mini_agent/tools/__init__.py` | Changed | Supports registering state-bound tools at startup |
| `src/mini_agent/__main__.py` | Changed | Binds the current state to the Todo tool |
| `src/mini_agent/context.py` | Changed | Structured State renders Task State |
| `src/mini_agent/prompt.py` | Changed | Explains that complex tasks use a Todo and simple tasks need none |
| `tests/test_state.py` | Changed | Todo invariants, deep copies, concurrent consistency |
| `tests/test_tools.py` | Changed | Todo tool schema and state updates |
| `tests/test_context.py` | Changed | Todo injected accurately after compaction |

### 6.4 Tool interface

```json
{
  "name": "update_todo",
  "arguments": {
    "todos": [
      {"content": "Read the project rules and related implementation", "status": "completed"},
      {"content": "Change the context building logic", "status": "in_progress"},
      {"content": "Add and run tests", "status": "pending"}
    ]
  }
}
```

Using full-list replacement instead of several `add/start/complete` commands lets the model express a plan adjustment in one go and keeps state validation in one place. After the tool runs successfully, `current_goal` is derived from the single `in_progress` item; when there is no item in progress, it is empty.

The Todo tool is an in-memory state tool and should not trigger file write permissions; it also cannot change `tool_history`, `files_changed`, `errors`, or the final `status` of the whole task.

### 6.5 Task breakdown

1. `TodoItem` + `AgentState.update_todos()` + invariant unit tests
2. Add Task State to `snapshot()`, and verify callers cannot change the original state through the return value
3. The state-bound `update_todo` tool + schema/handler unit tests
4. Register the tool in the CLI, making sure different `AgentState`s do not share a Todo
5. ContextManager re-renders the latest Task State every round, not appended to history
6. Verify that the Todo and `current_goal` stay accurate after 2+ consecutive compactions
7. Add minimal usage rules to the prompt; run a three-step programming task by hand
8. Tutorial, CHANGELOG, README, version number, and tag `v0.15` (sync AGENTS.md when runtime constraints change)

### 6.6 Acceptance criteria

- [ ] The model can create, advance, and adjust the plan through `update_todo`
- [ ] Todo updates are atomic, and invalid states are never partly written
- [ ] At most one `in_progress` at a time, and `current_goal` matches it
- [ ] Execution State cannot be changed by the Todo tool
- [ ] The Todo does not exist only in messages and stays accurate after trimming/compaction
- [ ] Structured State reflects the latest Todo every round without growing through repetition
- [ ] Simple tasks can finish directly without a Todo

## 7. v0.16 Plan-driven Execution (5.3)

### 7.1 Goal

In one sentence: **upgrade the Todo from a static checklist to a dynamic work protocol, so complex tasks advance by "Plan → Execute → Observe → Verify" and Replan and continue when needed.**

v0.15 solves "where the plan lives"; v0.16 Plan-driven Execution solves "when to build a plan, how to maintain it, and when the task counts as done". This version is still a single agent and adds no new agent roles.

### 7.2 Dynamic task lifecycle

```text
receive the task
  ├── simple task → execute directly → verify (if applicable) → reply
  └── complex task → Plan: build or update the Todo
                   ↓
                Execute: mark the current item and run tools
                   ↓
                Observe: read results, errors, and environment changes
                   ↓
                Verify: run tests/builds/checks and record evidence
                   ├── passed and no unfinished items → final reply
                   └── problem found or not passed → Replan: advance, reorder, delete, or add Todo items
                                             ↓
                                          Execute
```

The Todo is a dynamic work plan, not a one-time checklist. Execution or verification results may complete, fail, reorder, or delete steps, or produce new necessary steps; the model should decide from facts whether to replan, not mechanically tick items in the initial order. Replan is a conditional action, not a stage every round must pass through.

### 7.3 Judging complex tasks

Provide explainable heuristics through the system prompt instead of hard-coding a task classifier in Python. Building a Todo is suggested when any of these holds:

- Several files or several interdependent steps are involved
- Investigation is needed before changes
- Tests or other verification must run after changes
- The user explicitly asks for a plan, a Todo, or progress tracking
- During execution, the original task scope turns out to need splitting

A single read, a single search, a simple calculation, or a question that can be answered directly does not require a Todo.

### 7.4 Execution protocol

- Build a short, result-oriented Todo before starting complex work
- Set a step as the single `in_progress` before executing it
- A successful tool does not complete a Todo automatically; the model judges based on the result
- After a tool fails, update or rewrite the plan first, to avoid repeating the same call unchanged
- Newly discovered necessary work can be added to the Todo; completed items can stay to show progress or be removed when the plan is reordered
- "Change the code" and "verify the change" are usually two steps
- Verification steps must produce citable completion evidence; when all Todos are completed but the necessary verification evidence is missing, the task must not be described as verified complete
- Before the final reply, all Todos should be complete and the verification evidence sufficient; when it cannot be completed, the unfinished/blocked status must be kept and the reason stated honestly

### 7.5 Completion check

This version uses **a lightweight runtime reminder, not an infinite hard block**: when the model is about to give its final text reply while there are still `pending` or `in_progress` Todos, the loop appends a structured reminder at most once, letting the model choose to continue executing, or to explain the block and end the task explicitly.

Put the decision in the Task State and Verification layer, rather than scattering Todo details across the loop:

```python
class AgentState:
    def unfinished_todos(self) -> list[TodoItem]: ...
    def completion_reminder(self) -> str | None: ...
    def has_verification_evidence(self) -> bool: ...
```

Why remind only once: the Todo is intent maintained by the model, and the agent must not become unable to return forever because the model forgot to update state. Whether to allow an explicit finish and how to mark a block can be decided during v0.16 implementation by choosing the minimal protocol based on real model behavior and writing it into the tutorial.

### 7.6 New/changed files

| File | Action | Content |
|---|---|---|
| `src/mini_agent/prompt.py` | Changed | Complex task judgment and plan-driven execution rules |
| `src/mini_agent/state.py` | Changed | Interfaces for querying unfinished items and the completion reminder |
| `src/mini_agent/agent.py` | Changed | At most one unfinished-Todo reminder before the final reply |
| `src/mini_agent/context.py` | Changed | Keeps the Context protocol and budget valid after a reminder |
| `tests/test_loop.py` | Changed | Normal progress, adjustment after failure, one reminder, simple tasks going straight through |
| `tests/test_context.py` | Changed | Validity of reminders across trimming/compaction |

### 7.7 Task breakdown

1. Define the complex task heuristics and the Todo lifecycle prompt
2. `unfinished_todos()` and the one-time completion reminder
3. Connect the reminder in the loop without catching LLM or loop main-path exceptions
4. Unit test: a simple task finishes directly without a Todo
5. Unit test: a complex task creates, advances, and completes all items
6. Unit test: the plan adjusts after a tool failure without polluting Execution State
7. Unit test: a final reply with unfinished Todos triggers only one reminder and no infinite loop
8. End-to-end task: follow project rules, investigate, change, and test; after the first verification fails, adjust the plan and verify again
9. Tutorial, CHANGELOG, README, version number, and tag `v0.16` (sync AGENTS.md when runtime constraints change)

### 7.8 Acceptance criteria

- [ ] Complex tasks build and keep maintaining a Todo; simple tasks keep the short path
- [ ] At most one step is in progress at any time, so the execution focus is clear
- [ ] Tool failures lead to plan adjustments instead of being treated as completion
- [ ] Change tasks include a separate verification step, and the verification result is recorded as real Verification evidence
- [ ] Todo completion status cannot replace verification evidence; the final finish is based on Verification
- [ ] A final reply with unfinished Todos triggers at most one reminder and never loops infinitely
- [ ] When the task cannot be completed, the unfinished status is kept and the finish is honest
- [ ] Project Instructions, Task State, Execution State, and Verification stay accurate after compaction

## 8. Test and Verification Summary

| Version | Focus of new tests | Manual verification |
|---|---|---|
| v0.14 | Instruction discovery order / degradation when missing / protected context / length limit | Start in a repository with `AGENTS.md` and confirm the Agent follows a repository-specific rule |
| v0.15 | Atomic Todo updates / state invariants / State rendering / repeated compaction | Run a three-step task and watch the Todo keep updating across a long context |
| v0.16 | Simple tasks straight through / adjustment after failure / verification step / single completion reminder | Fix a failing test; after the first fix fails, adjust the plan and finally pass |
| Stage E2E | `tests/test_stage5_e2e.py`: rule loading, Todo, replanning after failure, compaction, protocol completeness, and final verification | Scripted model responses drive the full loop in a temporary Git project |

Stage-level end-to-end acceptance task:

> Start the Agent in a temporary project that contains `AGENTS.md` and a failing test. The Agent needs to read and follow the project rules, build a Todo, locate the problem, change the code, and run the tests; after the first change the tests still fail, so the Agent adjusts the Todo based on the real result, changes the code again, and verifies it passes. Build enough history during the task to trigger at least one compaction.

Final assertions:

- The changes follow the Project Instructions
- The Todo stays accurate across many rounds and compaction, and can be reordered or extended as a dynamic plan
- `files_changed`, `errors`, and `tool_history` agree with the actual execution
- Verification records contain real test/build/check results that can support the completion conclusion
- A failure changes the later plan
- An explicit verification happened before the final completion
- The message sequence still satisfies the OpenAI tool calling protocol, with no orphan tool results

Core tests still depend on no third-party runtime: temporary directories use `tempfile`, the LLM is always mocked, and network end-to-end verification is only a manual check, not part of the default test suite. Peripheral optional dependencies must cover their fallback paths separately.

## 9. Version Boundaries and Dependencies

| Capability | v0.14 | v0.15 | v0.16 |
|---|---:|---:|---:|
| Load `AGENTS.md` | Yes | Yes | Yes |
| Project Instructions protected | Yes | Yes | Yes |
| Todo stored in AgentState |  | Yes | Yes |
| Todo tool updates |  | Yes | Yes |
| Structured State renders the Todo |  | Yes | Yes |
| Complex task planning rules |  |  | Yes |
| Plan adjustment rules after failure |  |  | Yes |
| Completion reminder before the final reply |  |  | Yes |

The dependency direction must stay one-way:

```text
v0.14 Project Instructions
    ↓ provide planning constraints
v0.15 Todo / Task State
    ↓ provide a persistable plan
v0.16 Plan-driven Execution
    ↓ form the task loop
```

Do not add the Todo early in v0.14, and do not add the completion block early in v0.15; this keeps each tag's teaching difference focused on only one new concept.

## 10. Sync with Existing Documents

After this plan is confirmed and before starting v0.14, update the following roadmaps together, so the old "v0.14 plan guidance" does not conflict with the new stage:

- `AGENTS.md`
  - Stage 5 changed to v0.14–v0.16
  - The roadmap replaced with Project Instructions / Todo Task State / Plan-driven Execution
  - Update "Current Architecture" and the check status when each version completes
- `docs/plans/teaching-repo-plan.md`
  - Add v0.14–v0.16 to the version slicing table
  - Sync the tutorial directory, usage guide differences, and code difference points
- `docs/tutorials/README.md`
  - Replace "Stage 5: Advanced Capabilities (planned)" with the formal Stage 5 navigation
- `README.md`
  - Sync the learning path with Stage 5's name, goal, and three versions
- `docs/operation/manual.md`
  - v0.14 adds the instruction loading rules
  - v0.15 adds the Todo / Task State description
  - v0.16 adds the complex task lifecycle description
- `docs/plans/README.md`
  - Add this plan to the index

Use the stage name consistently:

- **Project-Aware Task Orchestration**

## 11. Stage Definition of Done

Stage 5 counts as complete only when all the following hold:

- [x] v0.14, v0.15, and v0.16 each have a readable incremental diff and a matching git tag
- [x] All three tutorials follow the repository template, with goals, core concepts, design reasons, and usage guides
- [x] The boundaries between Project Instructions, Task State, Execution State, and Context are consistent in code and documents
- [x] The default test suite passes completely with no third-party dependencies
- [x] The stage-level end-to-end task is complete, including one plan adjustment after a failure and the final verification
- [x] No regression in Stage 4 trimming/compaction or the OpenAI tool calling protocol
- [x] The roadmap, README, operation manual, tutorial index, and CHANGELOG are all synced

After Stage 5, mini_agent has the key working loop of a lightweight coding agent: **understand project rules, maintain an explicit plan, perform real operations, adjust based on results, and finish after verification.** Later stages choose among a separate Plan Mode, failure recovery, durable memory, security isolation, or multiple agents based on the main failure modes seen in real use, rather than designing them in advance in this stage.

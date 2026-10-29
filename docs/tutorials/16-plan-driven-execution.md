# Lesson 16: Plan-driven execution (Plan-driven Execution, v0.16)

Previous: [Task list and state](15-task-state.md) · [Tutorial overview](README.md) · Next: [Failure fact model](17-failure-model.md)

> Code snapshot: `v0.16` · Adjacent diff: `v0.15..v0.16` · Shell: Bash/zsh

> Requirements: Python 3.10+; the runtime uses only the standard library.

## Problems in the Previous Version

Lesson 15 solved "where to put the plan", but not "how to prove the work is really done". The model can mark a Todo as `completed`, but that does not mean it actually ran the tests; a check may have just passed, and a later file write can make that result stale.

So v0.16 handles plans and facts separately: the Todo records the model's intent, tool results record what has already happened, and only verification results for the current environment count as the basis for completion. This version does not make plans for the model or choose test commands for it; the runtime only stores facts and checks, when the model is about to finish, whether any condition is still missing.

## Lesson Goals

This lesson centers on one observable working loop:

```text
Plan -> Execute -> Observe -> Verify -> final reply
                         └─ when a problem is found, Replan -> Execute
```

`Plan` is the plan, `Execute` runs tools, `Observe` reads tool results, and `Verify` checks the result with an independent command. `Replan` happens only when a failure, an omission, or new work is observed; it is not a stage every round must pass through.

After reading, you should be able to explain:

- Why a task cannot always finish even when all Todos are marked `completed`;
- Why an operation that may change the environment invalidates old verification;
- Why `run_shell` distinguishes ordinary execution from verification use;
- Why the completion reminder gives the model one chance to correct itself, and a second time without progress leads to `blocked`.

The main thread of this lesson: **the plan records intent, tool results record facts, and only verification records of the current generation are completion evidence.**

## Prerequisites and Version Checkout

Read Lesson 15 first to understand `AgentState`, the full-replacement rule for Todos, and why state is not written directly into message history. The commands below are for Bash/zsh; they switch to v0.15 to view the adjacent diff, then switch back to v0.16 to read this lesson's implementation:

```bash
git checkout v0.15
git diff --stat v0.15..v0.16
git diff v0.15..v0.16 -- src/mini_agent/state.py src/mini_agent/agent.py src/mini_agent/context.py src/mini_agent/tools/shell.py src/mini_agent/prompt.py
git checkout v0.16
```

`git diff --stat` locates this version's scope; the second diff locates the main call chain. After these commands, later reading and running should take place in the `v0.16` snapshot.

## New and Changed Files

The change in this version is not "one more Todo status"; it connects verification facts to the execution chain and adds a completion check before the final text:

| File | Change | Purpose |
|---|---|---|
| `src/mini_agent/state.py` | Adds verification evidence, generations, and completion conditions | Stores the plan separately from actual execution results |
| `src/mini_agent/tools/shell.py` | `run_shell` adds `purpose` | Distinguishes execution commands from verification commands |
| `src/mini_agent/agent.py` | Checks completion conditions before the final text | Finishes normally or marks blocked after one reminder |
| `src/mini_agent/context.py` | Renders verification status and the Runtime Notice | Hands the latest facts and reminders to the model's next round |
| `src/mini_agent/prompt.py` | Adds plan–verify rules | Tells the model the working protocol for complex tasks |
| `src/mini_agent/__main__.py` | Calls `begin_task()` before each task | Makes the task boundary explicit and resets this task's runtime facts |

## Version Change Map

First look at how v0.15 finishes, then at where v0.16 inserts verification and the completion check. Legend: `[old]` already in v0.15, `[+]` new in v0.16, `[~]` changed in v0.16, `[C]` main consumer, `[B]` boundary of this version.

v0.15 baseline diagram:

The v0.15 entry can already run tools, feed results back to the model, and keep the Todo for the session; after the model gives text without tool calls, the CLI finishes the task directly.

```text
[old] CLI run_task
  -> [old] state.task/status + history
  -> [old] agent_loop
       -> [old] call_llm
       -> [old] ToolExecutor.execute
            -> [old] PermissionGate -> tool handler
            -> [old] state.record_tool
       -> [old] all role=tool results fed back
       -> [old] next LLM round
  -> [old] final text without tool_calls
  -> [old] CLI finishes running as done
```

v0.16 change diagram:

v0.16 inserts "verification facts" and a "completion check" between tool results and the final finish. The normal path finishes after the current generation's verification passes; the important degradation path is entering `blocked` after the model tries twice to finish too early. Replanning is decided by the model from observations or verification results; the runtime does not force a stage order.

```text
[+] CLI run_task -> [C] state.begin_task(task)
                     └-> clear Todo, errors, files, and old verification evidence
  -> [old] agent_loop -> [old] call_llm
       -> [+] update_todo -> [C] state.update_todos()        (plan intent, updated as needed)
       -> [old] ToolExecutor.execute -> handler
            -> [~] state.record_tool()                       (execution facts)
                 ├-> write_file/edit_file or run_shell(execution)
                 │    -> [+] generation +1, old evidence invalid
                 └-> run_shell(verification)
                      -> [+] VerificationEvidence
                      -> [C] pass/fail status of the current generation
       -> [old] all role=tool results fed back -> next LLM round
       -> [C] ContextManager.prepare_messages()
            -> [~] Structured State
            -> [+] Runtime Notice (next request only)
  -> [~] final text without tool_calls
       ├-> conditions met -> CLI finishes as done
       ├-> first gap -> Runtime Notice -> one more LLM request
       └-> still a gap -> status=blocked                     (degradation path)

[B] No automatic Todo generation, verification command choice, retry, rollback, or plan persistence
```

## Core Concepts and Data Structures

### 1. A Todo is intent, not completion evidence

The problem starts with an easily confused case: when the model calls `update_todo` and puts "change the file" in the plan, that does not show the file was changed. v0.16 keeps the Todo updating only the plan, and does not mix it into the tool history, errors, or the list of changed files:

```python
# src/mini_agent/state.py (v0.16)
def record_tool(self, name, args, ok, brief):
    # A Todo is task intent, not an execution fact.
    if name == "update_todo":
        return
    ...
```

The key effect of this code: after a Todo call, only tools that actually ran enter execution state such as `tool_history`. The tool executor hands every tool result to the state through `on_result=state.record_tool`; the agent loop does not need to know how each kind of tool changes state. Tool handler exceptions are still turned into results that can be fed back at the tool boundary, and LLM and top-level CLI exceptions are not swallowed by the loop.

### 2. Making old verification expire automatically with generation

The problem is that "the tests passed once" does not mean "the current workspace still passes". The `generation` is a counter that increments after every operation that may change the environment. A successful `write_file` or `edit_file`, and any `run_shell(purpose="execution")` that actually entered its handler, call `_invalidate_verification()`:

```python
# src/mini_agent/state.py (v0.16)
def _invalidate_verification(self) -> None:
    self._verification_generation += 1
    self.verification_evidence.clear()
    self._last_verified_generation = -1
    self._verification_required = True

if name == "run_shell" and args_copy.get("purpose", "execution") == "execution":
    if "Permission denied" not in brief:
        self._invalidate_verification()
```

The runtime cannot reliably tell whether an arbitrary shell command is read-only, so an execution command invalidates old evidence conservatively, even when it returns nonzero. A permission denial means the handler did not run, so it does not invalidate evidence. This way, "test first, then change a file, then reply directly" is always treated as not yet verified.

`begin_task(task)` clears the Todo, tool history, errors, files, and old verification evidence at the start of every CLI task, resets the status to `running`, and advances the generation. It keeps the session `history`, so after the command-line first task ends, you can still ask follow-up questions in the interactive loop.

### 3. Marking independent verification with `purpose`

An ordinary shell command and "a command used to confirm the final result" mean different things. v0.16 adds `purpose` to `run_shell` with a default of `execution`, so old calls that pass only `command` remain compatible:

```python
# src/mini_agent/tools/shell.py (v0.16)
def run_shell(command: str, purpose: str = "execution"):
    ...

"purpose": {
    "type": "string",
    "enum": ["execution", "verification"],
    "default": "execution",
}
```

When `purpose="verification"`, `record_tool()` reads `[exit=N]` from the tool result. Only when `ok` is true, there is no timeout, and the exit code is 0 does it create passing evidence for the current generation; every other result is recorded as a failure, and verification is still required:

```python
passed = bool(ok and not timeout and code == 0)
evidence = VerificationEvidence(
    command=str(args_copy.get("command", "")),
    outcome="passed" if passed else "failed",
    exit_code=code,
    output=text,
)
```

`VerificationEvidence` stores the command, `passed`/`failed`, the exit code, and truncated output. The shell tool returns `[timeout]` on timeout; a normal exit always carries `[exit=N]`, whether or not the code is 0. This evidence only says the process exited successfully; it does not guarantee sufficient test coverage, a correct verification command, or correct business logic.

### 4. The completion reminder is one correction, not an automatic retrier

If the model outputs its final text while Todos are unfinished or verification is still needed, trusting it completely would end too early; blocking forever would let a model whose state makes no progress loop endlessly. So the state concentrates the gaps into one check:

```python
# src/mini_agent/state.py (v0.16)
def completion_reminder(self) -> dict[str, object] | None:
    missing = [t.content for t in self.todos if t.status != "completed"]
    needs_verify = self._verification_required
    if not missing and not needs_verify:
        return None
    return {
        "unfinished_todos": missing,
        "verification_required": needs_verify,
        "message": "The task does not meet its completion conditions yet; continue executing and verifying.",
    }
```

When the agent loop finds a gap, the first time it sets a Runtime Notice and requests the model again; the second time there is still a gap, it sets `status="blocked"` and returns the current text. The Runtime Notice is not written to `history`; it appears only in the request view built by the next `prepare_messages()`, and even if that build triggers context compaction, it is consumed only after the final view is complete.

## Why This Design

"Verification passed" could be put straight into the Todo, or Python could guess from command text which commands are tests. v0.16 does neither: the first would mix model intent and runtime facts again, and the second is error-prone and would choose project-specific verification for the user.

The current design separates responsibilities: the model maintains a short, adjustable plan and explicitly marks verification commands; the runtime only records conservatively and checks completion. The benefit is that evidence is tied to the latest potential environment change and is still provided by `AgentState` after the message history is trimmed or compacted; the cost is that a simple execution shell that is actually read-only also requires verification again, and the system cannot judge whether verification is thorough enough.

A single reminder is another trade-off. It gives the model a chance to correct an omission without turning small Todo mistakes into an endless loop. It is deliberately not a retry strategy, and it never builds Todos, runs tests, or rolls back changes by itself.

## Design Boundaries

- For complex tasks the prompt suggests building a Todo first; simple questions, a single read, or a simple calculation can finish directly, and the runtime does not force a plan.
- `purpose` on `run_shell` only changes how state is recorded, not permissions. Permissions are still decided by `PermissionGate`.
- A verification failure, a timeout, or a missing exit code all leave failure evidence and require the model to adjust the Todo based on the result; the runtime does not choose the next command.
- The final text can finish directly only when "all Todos are complete" and no potential change awaits verification. Read-only tasks without changes usually need no verification.
- When `MAX_ITERATIONS` (default 50) is reached, the loop returns "Maximum iterations reached" and sets the status to `failed`; the CLI sets `done` only when it returns normally and the status is still `running`.
- State lives only in the current process; drafts already streamed are not withdrawn.

## Key Flow

The flow below shows the normal path of a "change and check" task, and also the loop after a verification failure. Arrows show v0.16 calls or data flow; when you run it, you should see `verification_required` become true after a write or an execution shell, and only a verification of the current generation returning `[exit=0]` clears it.

```text
CLI receives the task
  -> state.begin_task()
  -> LLM calls update_todo: investigate / change / verify
  -> LLM calls read/write tools or run_shell(execution)
  -> ToolExecutor on_result -> state.record_tool()
       -> generation changes, verification_required=true
  -> ContextManager injects the latest Structured State into the next round
  -> LLM updates the Todo as needed, then calls run_shell(verification)
       ├-> [exit=0]: current generation's verification passes
       │    -> all Todos complete -> final text -> done
       └-> nonzero / timeout: failure evidence
            -> Replan: update the Todo
            -> Execute: fix
            -> verification again
```

If the observation stage already shows the plan needs to change, the model can also Replan before verification; this is only an execution path the model chooses, not a state transition hard-coded in the runtime.

If the model gives its final text before verification, you first see that text streamed, and then the next round's request receives a `[Runtime Notice]`. This shows that the reminder is correction information in the request view, not a withdrawal of what was already printed; only when the conditions are still not met the second time does it finish as `blocked`.

## Implementation Breakdown

`ContextManager._render_state()` regenerates the Structured State from `state.snapshot()` every round, including `Verification` and `Verification required: true`. So the state is not a piece of old conversation text: when the context is trimmed or compacted, the latest verification facts are injected again.

The prompt tells the model that complex tasks use `Plan -> Execute -> Observe -> Verify` and that it should adjust the Todo when observation or verification finds a problem; Python implements no complex task classifier and does not force when Replan happens. The Todo tool submits the full list each time, and at most one item can be `in_progress`; these v0.15 rules still apply.

The call order of the final finish also deserves attention: an assistant message with `tool_calls` must first run and feed back all `role=tool` results in the original order before the next round can see the updated State. Only a message without `tool_calls` enters the `completion_reminder()` check, so verification results are never skipped within the same round.

## Run and Observe

After you configure a local LLM, start the program in Bash/zsh with a real task that needs changes and checks:

```bash
PYTHONPATH=src python -m mini_agent "change the implementation, run the checks, and maintain a Todo"
```

The program treats this argument as the "command-line first task", and still enters the interactive loop after handling it. Observe whether the model updates the Todo first; after any write or execution shell, it should go on to call a verification tool instead of finishing directly. Only after the last `run_shell(purpose="verification")` returns `[exit=0]` can the model finish normally. `Verification required: true` is in the internal Structured State sent to the model; by default the CLI does not print this field directly.

## Version Features, Next Lesson, and Code Index

v0.16 adds generation-bound verification evidence, a one-time completion reminder, and three task finish states: `done`, `blocked`, and `failed`. It is still a lightweight single-agent protocol and does not plan automatically or recover from failures automatically.

Next lesson: the [failure fact model](17-failure-model.md) further distinguishes different failure facts such as "the tool did not run", "side effects may have occurred", and "verification failed".

- [src/mini_agent/state.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.16/src/mini_agent/state.py)
- [src/mini_agent/agent.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.16/src/mini_agent/agent.py)
- [src/mini_agent/context.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.16/src/mini_agent/context.py)
- [src/mini_agent/tools/shell.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.16/src/mini_agent/tools/shell.py)
- [src/mini_agent/prompt.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.16/src/mini_agent/prompt.py)
- [src/mini_agent/__main__.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.16/src/mini_agent/__main__.py)

## v0.16.1 Patch: Reopening the Completion Reminder by Progress State

> Patch snapshot: `v0.16.1` · Adjacent diff: `v0.16..v0.16.1` · This patch has no separate lesson

### Why this patch is needed

v0.16 controlled the completion reminder with one global `reminded` boolean, so a task got at most one reminder. This rule stops the model from endlessly outputting unfinished summaries, but it also mistakes a normal interim report for an unrecoverable attempt to finish: after the model reports investigation results, receives a reminder, and continues calling read-only tools, its next interim report goes straight to `blocked` even though it has gained new facts.

v0.16.1 narrows the rule to "at most one reminder per progress state". It fixes the completion protocol and does not introduce `recover`, `FailureEvent`, a planner, or new control tools; `MAX_ITERATIONS=50` is still the global limit of the whole loop.

### Building a progress marker from existing completion facts

The patch does not add another reminder counter; it builds a `progress_marker` from existing facts. The context of the code below: `completion_reminder()` already knows which Todos are unfinished and whether there are tool observations and verification gaps, and the patch combines these facts for the loop to compare:

```python
progress_marker = (
    tuple((todo.content, todo.status) for todo in self.todos),
    len(self.tool_history),
    len(self.verification_evidence),
    self._verification_generation,
    needs_verify,
)
```

It consists of five kinds of facts: the `(content, status)` of the full Todo list, the number of recorded non-Todo tool results, the number of verification evidence records, the current verification generation, and the `verification_required` status. Resubmitting Todos with the same content and status leaves the marker unchanged, so it cannot be used to refresh the reminder forever; real Todo progress, a tool producing a result, more verification evidence, or a changed generation all form a new marker. A tool failure is also a new observed fact, which lets the model re-judge once based on the result.

### How the agent loop decides

`agent_loop()` uses `reminded_progress_marker` instead of the global `reminded`:

- The first time it sees a completion gap, it saves the current marker and injects a Runtime Notice;
- After tool, Todo, or verification facts change the marker, it can remind again for the new state;
- Only when the marker is unchanged and the model outputs text without tools again does the task enter `blocked`;
- When a custom or legacy State does not provide `progress_marker`, it keeps the compatible behavior "only one reminder per task".

The Runtime Notice also becomes an actionable instruction: while the task is unfinished, the model's next reply must carry a tool call that updates the Todo, continues investigating/operating, or runs verification; it cannot just describe "next I will run" in words; only when it really cannot continue should it state the specific blocking reason. Interim text already streamed to the terminal is kept.

A typical investigation report flow becomes:

```text
interim report
  -> Runtime Notice
  -> call a read-only tool (progress_marker changes)
  -> another interim report
  -> another Runtime Notice for the new marker
  -> update the Todo / continue executing / verify
  -> meet the completion conditions, or keep looping in the next progress state
```

The no-progress boundary is still clear:

```text
Runtime Notice
  -> no tool, Todo, or verification progress
  -> text only again
  -> blocked
```

### Boundaries unchanged from v0.16

The normal completion conditions are unchanged: all Todos must be complete, and the latest operation that may change the environment must have a passing verification of the current generation. An assistant message with `tool_calls` must still get a matching `role=tool` result fed back for every call; simple tasks and tasks without Todos can still finish directly; the 50-round limit is unchanged.

The Runtime Notice still enters only the next target request. Even if that request triggers trimming or compaction, it is consumed only after the final request view is built; it is not injected twice and does not withdraw interim text already printed.

### How to observe the patch behavior

First let the model output an interim report while Todos are unfinished, then let it call a read-only tool to gain a new fact. After the patch, the runtime treats this tool result as real progress, lets the model receive another reminder for the new state, and lets it continue. If the model receives a reminder and then does not call a tool, advance the Todo, or add verification, but only outputs text again, the task still enters `blocked`. Resubmitting exactly the same Todo cannot create progress either.

The patch does not change the normal completion conditions, the one-to-one tool-call/result mapping, the 50-round limit, or the context compaction boundary. You can read the implementation in the pinned snapshot: [state.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.16.1/src/mini_agent/state.py), [agent.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.16.1/src/mini_agent/agent.py), and [prompt.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.16.1/src/mini_agent/prompt.py).

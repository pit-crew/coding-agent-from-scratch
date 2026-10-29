# AGENTS.md

## Project Scope

`agent-from-scratch` is a Python coding agent that grows step by step (package name `mini_agent`). The core runtime and key execution flows use only the standard library; peripheral user-experience capabilities may be enhanced with optional dependencies.
This file holds only hard constraints that directly affect agent runtime, authorization, and code changes; the version roadmap, tutorial rules, and full architecture live in `docs/`.

## Execution Rules

- **Investigate before changing**: read the relevant implementation, tests, and plans first, confirm the existing behavior and boundaries, then propose the smallest change.
- **Standard library first for the core**: LLM calls, the agent loop, tool execution, permissions, state, context, and verification flows must not add third-party dependencies; peripheral user-experience capabilities may use optional third-party libraries, but they must have a standard-library fallback and must not become a default install or a hard dependency of core modules.
- **HTTP client constraint**: LLM calls must use `http.client`, and requests must explicitly set `Accept-Encoding: identity`; do not switch to `requests` or `urllib`.
- **Configuration safety**: the real `BASE_URL`, `API_KEY`, and `MODEL` go only in the local `config_local.py` and must not be committed to the repository.
- **Exception boundary**: the tool layer/executor converts handler exceptions into error results and feeds them back to the model; the core agent loop does not catch LLM or top-level CLI exceptions.
- **Protocol completeness**: every tool call must get a matching `role=tool` result fed back; all tool results of one turn are fed back before the next turn starts.
- **Durable tool boundary**: with `/save` on, schema 3/4 must commit `handler_admitted` before the handler; each call's State, its `role=tool` result, and the boundary state must be committed atomically in model order; no new LLM request may be made before the whole turn is committed. A failed commit must not enter the handler, a later call, or the next LLM request; crash recovery must not replay a pending call.
- **Plan Contract**: for complex tasks the model submits a complete immutable revision through `commit_plan` and appends independent step progress events through `update_plan_progress`; simple tasks keep the Direct Path. A plan validation failure only feeds back `plan_rejected`; it must not create a `FailureEvent`, advance the generation, or produce verification evidence. Plan writes do not replace real execution or independent verification.
- **Read-only planning and handoff**: ordinary tasks may enter read-only investigation through `begin_plan`; `--plan` tasks must investigate first and, after submitting, wait for the user to approve the current revision. Side effects, verification, and mixed submissions in `exploring` are rejected at both the whole-turn and executor levels; an approved plan must not bypass the PermissionGate. User rejection or feedback to continue investigating is recorded by the CLI and cannot be forged by the model.
- **Shell side-effect classification**: every `run_shell` call is treated as possibly having side effects and reserves a generation after approval; `purpose=verification` only marks the use as verification evidence and does not downgrade the command to read-only.
- **Parent task cumulative budget**: `PARENT_TASK_TOKEN_BUDGET=None` turns it off by default; when on, parent main requests and summaries with the same binding share one persistent ledger, subagent budgets are independent and not charged twice. A unique reservation is committed before the request, and only a successful settlement after the response may enter the handler; a failed commit stops the task. Recovery of an unknown pending request charges the full reservation and settles only once; the saved task limit must not reset because of recovery or configuration changes. Only the request view is trimmed; the full history and selected reasoning fields stay as they are. Finishing still requires a real reply without tools, all completion conditions, and verification of the current generation; the plan is not advanced or declared complete automatically.
- **Completion and limits**: a task can only finish with no `tool_calls`; with an active Plan Contract, all active steps must be complete and the post-change verification conditions met; the Direct Path without a plan keeps the original completion conditions. The default limit is 50 turns; exceeding it returns an explicit result.
- **Replay is read-only**: Trace & Replay may only consume structured State snapshots of the current process and current task; it must not call the LLM, run tools, pass through permission authorization, or change history, state, budget, or generation. Verification evidence of the current generation is used for the completion decision, and the append-only verification history is used for cross-generation replay; broken chains and cross-generation evidence must be marked incomplete and must not be filled in by guessing.
- **Tutorial readers first**: when writing or changing `docs/tutorials/`, assume the reader has basic Python and command-line skills but is new to Agents and does not know the project's internal architecture. Tutorials are written in English. Explain the problem and intuitive meaning first, then modules, fields, protocols, and implementation; explain terms, abbreviations, and internal project concepts near their first use; do not substitute code, symbols, or file lists for teaching. See the [tutorial authoring rules](docs/governance/tutorial-authoring.md).
- **Main README editing**: before changing the learning path, stage names, or version topics in `README.md`, follow the [main README authoring rules](docs/governance/readme-authoring.md): topics use plain English, and only protocol fields, code identifiers, and well-known technical terms keep their original form; after the change, run `PYTHONPATH=src python scripts/check_readme.py`.
- **Verify after changes**: after changing files, run at least the tests related to the change; before delivery, run the full verification commands below (or state why they cannot run).
- **Destructive operations**: do not delete, reset, overwrite many files, or perform other hard-to-reverse operations without explicit user authorization.
- **Tag operations are user-only**: creating, moving, overwriting, deleting, and remotely pushing Git tags may only be done manually by the user. The assistant must not perform any tag operation, even if the user asks for a tag in the task; if a task involves tags, only describe the steps or provide the commands and wait for the user to do it manually.

## Current Status

The stable baseline is `v0.16.1` (progress-aware completion reminder patch for plan-driven execution); the current mainline development version is `v0.49` (resumable child sessions). New feature intent is recorded in the matching `docs/plans/`; this file is updated only when runtime hard constraints change.

v0.46 MCP hard constraints: only `MCP_SERVERS` entries with explicit `agent_enabled=True` enter the parent Agent Runtime; Servers with the default `False` are still used only by the standalone `python -m mini_agent.mcp` command. Parent-side MCP Tools run through the Tool Registry, ToolExecutor, PermissionGate, and `AgentRuntime.run()`, with default `effect_class="possible"` and default permission `ask`; only the exact `readonly_tools` of the same Server can be downgraded to `none`, still require authorization, and do not automatically become verification evidence. MCP, Resources, and Prompts do not enter Subagents.
Importing configuration does not start a Server, and command argv does not go through a shell. The Client is pinned to MCP `2025-11-25` and must run `initialize → notifications/initialized → tools/list → tools/call` in order, read all pages, and freeze the tool catalog; the standalone CLI sends `tools/call` only after an explicit interactive confirmation before each request. The parent Runtime reconnects and rediscovers the catalog from the current configuration for new and resumed tasks; exit, `/new`, `/reset`, and resume failure must all close connections within bounds.

The HTTP transport accepts only per-request `application/json` responses and uses the standard library `http.client`; HTTPS is required by default, and plaintext HTTP is available only for explicitly allowed loopback addresses. The client rejects SSE, redirects, OAuth, server-initiated requests, and automatic retries; the session ID after initialization is carried only in memory, and a session DELETE is sent on a best-effort, bounded basis. `resources/list`, `resources/read`, `prompts/list`, and `prompts/get` handle all pages and freeze the catalog; Resources allow only bounded UTF-8 text, and Prompts allow only bounded text with raw `user`/`assistant` labels. The four Resource/Prompt commands are triggered only explicitly by the parent CLI, and read/get is authorized by exact `alias:uri` or `alias:name`; Resources enter ordinary history with source and low-trust markers, Prompts must be fully previewed and confirmed before becoming user-side input, and server content must not enter the protected system prompt, State, Trace summaries, or verification evidence.

A frozen tool catalog must not be refreshed from the Server again; only the latest 64 ordinary notifications are kept. The CLI must show the full arguments before confirmation and refuse the call if it cannot show them fully; failure to finish closing a direct child process must be reported. JSON-RPC error codes must be integers, and control characters in terminal output must be escaped.

stdio MCP stdout allows only line-delimited UTF-8 JSON-RPC, with at most 1 MiB per message and at most 64 queued messages; stderr is drained separately and only the last 16 KiB is kept. Startup/handshake, catalog pages, tool calls, and shutdown follow default bounds of 10 seconds, 10 seconds, 30 seconds, and 2 seconds. After bad encoding, bad JSON, protocol desync, EOF, timeout, or exceeded limits, the connection must not be reused and `tools/call` must not be retried automatically; shutdown must close stdin first, then terminate and reap the direct child process within bounds. MCP errors keep only a bounded, redacted category, method, and server error code; `isError=true` in a tool result is still a valid MCP result and is not the same as a JSON-RPC error.

Model binding hard constraints: provider/profile can only be resolved from local configuration; parent and child bindings must be frozen before the corresponding Runtime is created, and the model must not be switched through global variables at runtime. `delegate_task` may only request an approved local `model_profile` alias; unknown or unauthorized aliases must be rejected before the HTTP request; there is no automatic provider fallback. State, Context, session, Trace, tool results, and user-visible errors may only keep credential-free profile/provider/protocol/fingerprint source summaries, and must not persist the real endpoint, model ID, API key, or auth headers. Summary requests must use the same binding and count toward its usage; when provider usage is missing, estimate conservatively and mark the source.

Crash recovery hard constraints: `active + schema 3/4 pending tool_boundary` can only derive a new session; the source session stays read-only, and the same source integrity can only be claimed once. Calls that did not enter the handler get an explicit not-executed result; admitted calls are always recorded as uncertain facts and are not replayed automatically. Every issue must be handled one by one by the user with `/resolve`; investigation allows only approved side-effect-free observation, and after all `continue` the task must replan, reauthorize, and verify independently. During recovery, the old PID, stdin, and current verification eligibility are not inherited.

Completion reminder hard constraints: when active Plan Contract steps are incomplete or still need verification, interim text triggers only one Runtime Notice for the current
`progress_marker`; a new reminder is allowed only after the plan status, non-plan tool facts, verification evidence,
generation, or `verification_required` changes. If the marker is unchanged and text without `tool_calls` is output again, the task must be set to `blocked`. The Runtime Notice requires the next reply
to call a progress tool; only when it really cannot continue does it state the specific blocking reason. Legacy State without `progress_marker` keeps the one-reminder compatible behavior.

Active background processes belong to the current `task_id` and must prevent the task from entering `done`; an in-flight stdin write also prevents completion. When the model has no tool calls but a process is still running or a stdin write is unfinished, control returns to the CLI with `awaiting_process`; before the user resumes, processes are synced first. `/new`, `/reset`, EOF, `exit`, and abnormal exit must first clean up, within bounds, the processes and writer threads registered for the current task; if cleanup is incomplete, keep the old task and report the specific process ID, PID, and reason. Pipe stdin is writable only when explicitly enabled; a single UTF-8 input is at most 4096 bytes, and its body must not enter State, Trace, tool results, authorization prompts, or terminal output; PTY is not a current capability.

`/save` is still the only way to turn on persistence; a complete safe point saves the current task's State, Context, and session metadata. A durable tool turn additionally allows an ordered result prefix of the last turn and an attempt pending settlement, but these are written only to the schema 3/4 `tool_boundary` and are not an ordinary safe point. Unsettled attempts, active processes, or in-flight stdin must not be saved as a safe point; `active + schema 3/4 + pending tool_boundary` can only enter crash recovery and derive a new session. `clean` must be committed after the task's processes are cleaned up within bounds. `write_process.input` is redacted in session arguments; if the body also appears in other persisted text, saving is refused. If sync or lock cleanup fails after replacement, report that the commit status is unconfirmed, with the session ID.

Subagent hard constraints: in v0.36, `delegate_task` can only synchronously create one depth=1 read-only Subagent; the subagent has its own State, Context, run state, prompt, frozen model binding, and fixed allowlist PermissionGate, but parent and child call the same canonical `AgentRuntime.run()`. It can only use `calculate`, `read_file`, `list_dir`, and `grep`, does not inherit the parent's history, permissions, Plan, generation, or verification, and cannot write files, run shell, operate processes, delegate again, or decide parent task completion. Child results are only untrusted investigation material, and their evidence does not enter the parent `verification_evidence`; the parent Agent exclusively owns workspace changes, the main plan, permission interaction, generation, verification, and the completion decision. Fixed budgets, the scope gate, the result contract, and one format correction are enforced by the child Runtime policy.

Memory hard constraints: the parent Agent can use workspace memory only through explicit `list_memories`, `read_memory`, `search_memories`, `remember`, `revise_memory`, and `forget_memory`; by default the parent Context automatically retrieves a few bounded summaries based on the current task and the latest user message, while subagents see no Memory tools and have no automatic memory candidates. The automatic query uses only `AgentState.task` and the latest `role=user` text in the full local history; it does not use assistant output, tool results, history summaries, or Memory content to expand the query. Candidates are only untrusted material and do not enter State, session, Plan, Trace, or `verification_evidence`. Retrieval rereads the current workspace on every `prepare_messages()`; a failure only degrades the current Context and does not turn retrieval off permanently. Memory is isolated by the normalized real workspace path and is written by default to schema 1 JSON in `~/.mini_agent/memory`; limits on record, file, and directory size/permissions, exclusive locks, atomic replacement, and directory sync follow `memory.py`. `remember`, `revise_memory`, and `forget_memory` are `possible` side effects, `search_memories` is a read-only `none` call, and they follow the PermissionGate, generation, planning, and recovery boundaries; a revision conflict must not write to disk. Memory is not part of State, Plan, or verification evidence; schema 1 free-text `source` always returns `source_status="unverified"`, and the source file's freshness is not accessed or claimed. With `/save` on, a single memory argument can still enter the session with the Context; do not claim the session contains no memory body.

References hard constraints: configuration uses the `REFERENCES` list, and the parent Runtime freezes alias, description, and real local directory only through `ReferenceCatalog`; the real root exists only in the process and is not written to State, Context, session, or Trace. The parent side provides only the read-only `list_references`, `search_reference`, and `read_reference`; configured aliases are not authorized automatically; listing is allowed by default, search and read ask by default, permissions match by `alias:relative_path`, and `always` remembers only the exact pattern. Each access revalidates the relative path within the alias, the real symlink target, and fixed resource limits; absolute paths, `..`, out-of-bounds symlinks, `config_local.py`, Memory/session sensitive directories, non-UTF-8, and special files must not leak. The body is only an ordinary tool history result, and State/Trace excerpts keep only body-free alias-relative summaries; a successful result is bounded JSON, an access failure is raised by the handler and recorded by the Executor as `outcome="failed"`, `error_kind="reference_access_error"`, without a new application-level error JSON protocol. File opens recheck the canonical path and file identity segment by segment from the frozen root directory fd, and refuse to read if a race changes them; References do not automatically enter Context, do not enter Memory or verification evidence, do not prove workspace drift, and are not added to the Subagent allowlist. Resume and new tasks both reassemble the catalog from the current local configuration and do not trust the old configuration in the session.

Skills hard constraints: when the Runtime is created it scans only the workspace root `skills/<name>/SKILL.md` and
`~/.mini_agent/skills/<name>/SKILL.md`; a project-level item with the same name takes priority, and an invalid project-level item with the same name blocks the global fallback.
The directory, frontmatter `name`, and `skill(name)` argument must follow the lowercase ID contract; only the two single-line fields `name` and `description` inside `---` are
parsed. The two roots together scan at most 64 direct directory entries, 32 KiB per file, 240 characters per description, and 8 KiB of catalog hints; when the project-level directory exceeds limits, the Catalog stays empty so that a global item with the same name does not
fall back by mistake. The Catalog freezes metadata and file identity, time, and size; loading opens segment by segment from the directory fd with `O_NOFOLLOW`
and rechecks before and after reading; replacement, symlinks, bad encoding, format, and size changes all fail safely. On each request, the parent Context injects, only as untrusted user-level material, the IDs, source levels, and descriptions filtered by the same PermissionPolicy;
the body must first pass the `skill` PermissionGate, which asks by default,
and then enters history as an ordinary untrusted `role=tool` result; it must not enter
State/Trace summaries or verification evidence, and commands or scripts mentioned in the body are not run automatically. Only Skill IDs explicitly listed in
`AGENT_PROFILES` can be requested by the corresponding named role; the parent side must pre-authorize each exact Skill ID with the current PermissionGate before creating the child Runtime.
Denied Skills do not enter the child Runtime;
a nonexistent Skill makes the delegation fail. Approved Skills are read on demand through a separate Catalog that contains only those IDs, and the child PermissionGate allows only
those Skill IDs. A Skill body is still an untrusted tool result and cannot add or change role tool permissions. Legacy delegations without
`agent_profile` do not expose Skills.

Named subagent role hard constraints: `delegate_task.agent_profile` is optional and supports the non-overridable
`explorer`, `reviewer`, `tester`, `general`, and frozen local custom roles. Role IDs, tool sets,
permissions, model aliases, Skill IDs, and text are validated and frozen when the parent Runtime is created. An effective read-only tool must at the same time
be in the four-tool subagent allowlist, the role's tool set, and this call's `requested_tools`, and pass the ScopeGate. Role permissions
accept only `allow`/`deny` on these tools, and the child Runtime does not start interactive authorization. When a role model is not specified, the existing
child model default selection is used; an explicit `model_profile` must match the role's resolved model, and unauthorized or unknown models are rejected before the LLM request with no
fallback. `tester` can only analyze and suggest tests; it cannot run tests or report that tests passed. An explicit
role's ID and the prompt-free configuration fingerprint enter the contract, State, schema 3 results, and Trace; legacy role-free contract
hashes and result/session fields stay unchanged. `delegate_task` stays synchronous, single-level, and read-only; `spawn_subagent` is the separate v0.48 background entry and does not change the synchronous tool contract.
Resume and new tasks reassemble the Catalog from the current disk and do not trust the old catalog snapshot in the session, nor reread bodies already loaded in history;
with `/save` on, ordinary tool history can still save loaded bodies.

In-process background subagent hard constraints: the parent side manages background read-only investigations only through the four Tool Registry tools `spawn_subagent`, `followup_subagent`, `get_subagent_status`,
`get_subagent_result`, and `cancel_subagent`, and all calls still go through
the ToolExecutor, PermissionGate, and parent Runtime phase gates. Starting requires an explicit `agent_profile` and
`purpose="investigation"`; starting is allowed only in `direct`, `exploring`, and `executing`. `diagnosis` and
`crash_investigation` still use only the synchronous `delegate_task`. Background starts are refused in the awaiting-approval, independent verification, terminal, and unsettled
crash recovery phases. Subagents are still depth=1; results are only untrusted investigation material and produce no parent-side
verification evidence.

One model turn can contain only one or more `spawn_subagent` / `followup_subagent` calls and must not mix in other tools. The parent thread admits call by call and commits a unique start confirmation in model
order; under schema 3/4, each call's `handler_admitted` and start result must be committed successfully, and workers can start only after the whole turn's
`tool_boundary` is committed. A partial commit, a commit failure, or a whole-turn commit failure must not start any
worker of that turn. A child worker runs only an independent child Runtime and writes a bounded result into a thread-safe completion queue; the parent thread exclusively owns completion collection,
State updates, usage settlement, notifications, result claiming, and session writes. Synchronous and background calls share `MAX_SUBAGENTS=3`,
`MAX_CONCURRENCY=2` (also limited by a smaller concurrency configuration of the parent task) and aggregate LLM, tool, and token budgets.

`child_session_id` is a UUID within the current parent task, not a cross-process child session. Status queries do not return bodies; only
`get_subagent_result` returns the finished `SubagentResult`. Repeated claims must return the same `result_id` and result, and State
settles only once; cancellation is a cooperative request, and the final result is still read through the result tool. Active tasks or unclaimed results must prevent the parent task
from entering `done` and ordinary safe points; manual `/save` lists the IDs and refuses, and automatic saving is deferred. `/new`, `/reset`, EOF,
exit, and abnormal cleanup cancel first and wait within bounds; if not finished, keep the old task and report the IDs/reasons; results that finished but were not claimed are recorded as `abandoned` before
`clean`.

In `active + schema 3/4 + committed tool_boundary`, background results whose start confirmation was durably committed but that have no safely saved result derive a new session on recovery,
mark the background record as `interrupted`, do not restore the old worker, do not forge result IDs/bodies, and settle unknown usage conservatively at the reservation limit;
the corresponding recovery issue must be handled one by one by the user with `/resolve`. Claiming a result is an ordinary parent tool call, and the session
must check that `child_session_id`, `delegation_id`, `result_id`, and the result hash match State. Trace replays only the parent-side
lifecycle summary in State and does not observe threads or read child history.

Resumable child session hard constraints: v0.49 only allows continuing, under the same parent `task_id`, workspace, role, and model source, a child session whose previous round
is `completed` and has been claimed by the parent. `followup_subagent` must submit a complete new investigation contract; the caller cannot change the
role or model, and Skill permissions are reauthorized by the parent PermissionGate every round. Failed, timed-out, cancelled, or interrupted rounds cannot be continued.
A continuation is still a pure background start like `spawn_subagent`: it can appear in the same turn as other start calls but must not be mixed with queries or ordinary tools; workers can start only after each confirmation
and the whole-turn boundary are committed successfully, and any durable commit failure starts no worker of that turn.

At most 4 rounds (including the initial round); each child session accumulates at most 16 LLM calls, 48 tool calls, 64,000 tokens, and 240 seconds.
Each round is still limited by the original `SubagentBudget`, and the parent task's aggregate budget and concurrency slots still apply; continuations do not increase
`created_subagents`. Only the parent-side State lifecycle saves the child session identity, rounds, budgets, and result ID/hash; it does not save the child history body.
Only claimed successful results can export snapshots. Schema 4 puts the parent State, Context, tool boundary, and all idle child snapshots into one
atomic safe point; active or unclaimed rounds must not be saved. On recovery, roles, models, and the Skill Catalog are rebuilt from the current local configuration and fingerprints are checked;
if snapshot generation fails, the completed report must still be delivered and actual usage settled, and that child session cannot be continued; an in-process followup rechecks the frozen Skill file identity before the child LLM request.
Incompatible child sessions are marked separately with the reason reported; models are not replaced, old workers are not restored, and requests are not replayed. Schema 1/2/3
can still be read; schema 3 does not contain resumable child snapshots.

## Architecture Index

- `src/mini_agent/agent.py`: HTTP/LLM transport, compatibility entry, and parent Runtime policy; `runtime.py`: the canonical `AgentRuntime.run()` shared by parent and child.
- `delegation.py`: v0.34 delegation contract, scope gate, child Runtime policy, and synchronous and in-process background Subagent Runner/Manager.
- `context.py`: per-turn context view, budget trimming, history compaction, and protected instruction injection.
- `state.py`: task, Plan Contract, tool, and verification state independent of message history; `current_goal`, `unfinished_todos()`, and `snapshot()["todos"]` are only read-only projections of the active plan.
- `permission.py`: allow/deny/ask permission gate matched by tool and argument pattern.
- `processes.py`: background process handles for the CLI lifetime, process groups, dual-stream draining, ring buffers, and bounded cleanup; non-snapshottable resources do not enter State.
- `session.py`: schema 1/2/3 sessions, integrity checks, atomic save/load, and tool boundary commits; it does not perform recovery execution.
- `prompt.py`: layered system prompt; `instructions.py`: discovers and merges project `AGENTS.md`.
- `references.py`: configuration freezing, path validation, sensitive directories, and bounded reads for parent-side named local References; `tools/references.py`: the three parent-side read-only tool contracts.
- `skills.py`: fixed directory discovery, frontmatter validation, frozen identity, and safe reads for the parent-side local Skill Catalog; `tools/skill.py`: the on-demand parent-side `skill(name)` Tool.
- `tools/`: standard tool registration and execution, plus file, shell, and calculation capabilities; the executor owns the permission and error result boundaries.

The full directory, parameters, data structures, and runtime flows follow the [operation manual](docs/operation/manual.md), the [context architecture notes](docs/operation/context-architecture.md), and the tutorial for the corresponding version.

## Common Verification

```bash
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python scripts/check_tutorials.py
PYTHONPATH=src python scripts/check_readme.py
```

If pytest is not installed, you can run the smoke tests in `tests/` that have a standard-library entry point directly; see the operation manual for how to run them.

## Documentation Index

- [Operation manual](docs/operation/manual.md): configuration, running, tools, and troubleshooting.
- [Tutorial index](docs/tutorials/README.md): learn, reproduce, and accept by version and stage.
- [Governance documents](docs/governance/README.md): constraints, rules, and decision records (including the [tutorial authoring rules](docs/governance/tutorial-authoring.md) and the [main README authoring rules](docs/governance/readme-authoring.md)).
- [Plan documents](docs/plans/README.md): roadmap, feature plans, and task breakdowns.

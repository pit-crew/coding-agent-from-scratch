# Changelog

## [Unreleased]

- Add an independent schema 1 regression-comparison pipeline with commit-isolated target Runtime workers, frozen 36-slot v0.52/v0.53 and Memory-retrieval plan, per-trial Memory isolation, atomic ledger updates, independent grading, paired reports, and fixture-only offline probes. Live comparison remains unrun pending review and explicit user authorization; existing v0.51/v0.52 live baselines remain incomplete and separate.
- Update package metadata and both learning paths to v0.53. No Git tag was created.

- Keep invalid recovery requests persistable without inventing causal failure references; report the current failure ID and repair phase on rejection. Supply a separate application-owned final reply prompt, preserving project/user/system constraints and authoritative completion facts while avoiding repeated tool rounds. Freeze suite 1.6 with workspace directory/search tools in verification-repair; retain historical suite 1.5 reports and the 64k parent limit. No paid model request or new live batch was run.

- Estimate budgeted OpenAI Chat input from the complete UTF-8 request structure with an explicit 10% margin, including message roles, JSON keys and tool schemas. Version calibration keys, trim optional tool history to the new allowance, and protect every user correction during trimming. Keep response overrun blocking and all archived live reports unchanged; offline tests cover the 13,748-token shape proxy and 19k/27k late recovery paths. No paid probe or new live batch was run.
- Make verification and plan progress funds spendable by the current work request; reserve only the later tool-free final reply using its protected context floor. Preserve numeric floor, allowance, blockers and reservation diagnostics on refusal. Add long-history late-budget regressions.
- Diagnose completed Chat tool-argument JSON failures without retaining argument text; preserve reported usage on failed validation. Count completed non-stream generation errors and explicit length stops as task failures; keep uncertain stream assembly errors separate. Historical live reports remain unchanged; no new live batch or suite version is created by this repair.
- Add the optional production parent-task token controller shared by main requests, summaries and crash recovery, with durable reservations, idempotent settlement, bounded warm calibration and conservative unknown usage.
- Bound task-budget context to two recent complete rounds while preserving user constraints and retained reasoning; reserve closing requests and use a tool-free finalization view only after authoritative completion facts permit it.
- Fix nonpersistent background startup discarding an existing admission and leaving an orphan pending attempt. Freeze suite 1.5 and add completion evidence layers and read-only cost replay. The pre-targeted-repair suite 1.5 batch preserved its 5/14 result. After budget and protocol fixes, one independent batch had 21 HTTP 503 slots; a second had 20 provider connection errors and one pre-injection token-limit stop. Both post-repair batches have a recovery denominator of zero, so they provide no recovery-rate result and the baseline remains incomplete.

## [v0.52.0] - Fault injection and recovery evaluation

- Added the frozen `reliability-boundaries@1.0` matrix with 18 scenarios, 50 offline parameter slots, and a seven-scenario, 21-trial live plan. Runtime invariant results and Agent task grading remain separate; fixture runs do not count as task success.
- Added named, finite fault drivers; schema 1 reliability suite/trial contracts; isolated live Runtime assembly; crash recovery in a fresh Python process; user-action reuse for simulated feedback; bounded evidence references; and read-only report reconstruction with suite and slot verification.
- Added `validate-reliability`, `self-test-reliability`, `run-reliability --live --repeats 3`, and `report-reliability`. The generic report skips the independent result format, preserving coding benchmark schema 1/2 behavior.
- Added the v0.52 evaluation guide, baseline status, tutorial, manual, and synchronized README learning paths. The redaction-fixed candidate passes all 50 offline fault/invariant slots; one restricted-sandbox attempt with eight loopback fixture startup errors is retained separately. The corrected fourth 21-slot live batch recorded 17 trials and 4 infrastructure errors; 9 faults triggered, 7 invariants passed, and 1 grader passed, so the live baseline remains incomplete. The earlier live batches exposed sensitive local provider values in request artifacts; pre-scrub hashes were retained, affected request files were sanitized, and the runner was fixed to keep those values out of artifacts. No failed live slots were retried or replaced. v0.51 suite 1.0 disputed results remain preserved; suite 1.1's live baseline remains incomplete.
- Updated package version to 0.52.0. No Git tag was created.

- Corrected the reliability suite as `reliability-boundaries@1.1`: add nonempty public tests and shared preflight/live calibration, use behavioral grading, score permission refusal as safe termination, keep the process fixture alive until explicit cleanup, reserve incoming request tokens, and preserve sanitized worker/provider diagnostics. Add offline tests through the exact live worker assembly; historical live artifacts remain unchanged and no new live batch has been run.

- Freeze reliability suite 1.4 input calibration and output reservations, inherited across crash phases. Reject handlers and completion after observed provider overrun while preserving actual usage; keep the trial budget unchanged. Its first independent live batch completed 21/21 slots with 21 faults triggered, 19 invariants passed, 15 graders passed and 1/18 recovery successes. No infrastructure errors occurred; conservative admission refused 16 requests before provider dispatch, while none of the 128 observed responses exceeded calibrated input or output allowances. The sample baseline meets its coverage threshold, but repeated context and execution-order issues remain.
- Correct trial-relative process cwd validation before handler admission; unify evaluation prompts across crash phases without changing production instruction discovery. Add bounded tool exception locations and numeric per-request context/schema/usage diagnostics. Freeze suite 1.3; preserve historical runs and budgets. The first independent 21-slot live batch completed with 20 faults triggered, 18 invariants passed, 14 graders passed, and 8/17 recovery successes. No infrastructure errors or provider HTTP 400 occurred; process-wait-timeout triggered only 2/3 times, leaving the baseline incomplete. All three crash-recovery trials preserved the no-replay boundary but exhausted the shared token budget. No slot was retried or replaced.
- Preserve bounded `reasoning_content` through ordinary/streaming Chat responses, tool rounds, Context and session history without displaying it as user-facing content. Correct reliability suite 1.2 crash phase instructions, freeze the timeout child budget, expose parent directory/search tools, and distinguish unobserved invariants from boundary failures. The independent 21-slot suite 1.2 live batch completed with no infrastructure errors, 19 triggered faults, and 5/16 recovery successes; HTTP 400 did not recur, but process-wait-timeout triggered only once, so the baseline remains incomplete. No slot was retried or replaced.

## [v0.51.0] - Frozen coding benchmark suite

- Review fixes: publish the exact receipt format in case/suite 1.1 and mark the original baseline's format failures as disputed; preserve interrupted trials after bounded child cleanup; avoid following symlinks when restoring reference directory permissions; exclude source-inconsistent trials from scored results and baseline completion.

- Added four ordered standard-library Python coding cases for pagination boundaries, multi-file order discounts and receipts, cache expiry with a required regression test, and configuration priority investigation.
- Added independent `initial`/`known_good` grading, pinned suite and fixture digests, schema 2 suite trial metadata, an atomic 12-slot suite ledger, sequential no-retry orchestration, and per-case/aggregate reports rebuilt from referenced raw trials.
- Added `validate-suite`, explicit `run-suite --live --repeats 3`, and `report-suite`; kept fixture and live cohorts separate and cost null without a price snapshot.
- Added lesson 51, suite usage and baseline status documents, synchronized both README learning paths, and aligned package metadata at 0.51.0.
- Initial live baseline is pending user review of all four tasks and success criteria; offline grader checks are not reported as model results.

## [v0.50.0] - Evaluation Harness

- Added strict schema 1 cases, trial requests, and results with bounded fixture validation, explicit tool visibility/authorization, independent grader budgets, and nullable uncollected metrics.
- Added a non-interactive isolated worker that reuses the canonical `AgentRuntime.run()`, `ParentRuntimePolicy`, `ToolExecutor`, a frozen local model binding, and a trial-scoped file-tool surface; shell, processes, MCP, Memory writes, Skills, and Subagents remain unavailable.
- Added an atomic runner with per-trial workspaces and HOME/Memory paths, wall-clock process-group cleanup, grader-after-Agent ordering, bounded logs/diffs/results, redacted model-source summaries, and fixture/live separation.
- Added `validate`, explicit `run --live`, two-run offline `self-test`, and report reconstruction from immutable raw trial JSON. Costs remain `null` without a price snapshot; recovery and invalid-repeat metrics are marked not applicable/uncollected.
- Added the fixed scale repair smoke case, independent grader checks for the broken and known-correct versions, v0.50 tutorial/manual/evaluation docs, and regression coverage for schema, path escape, permission refusal, timeout, infrastructure errors, atomic results, metrics denominator, and secret redaction.
- Live trial acceptance: completed with a successful real model run and an independent grader pass. The first sandbox-restricted connection error is retained as a separate scorable live trial; the recorded live output therefore reports 1/2 success, without broad benchmark claims.

## [v0.49.0] - Resumable child sessions

- Added `followup_subagent` for a complete next-round contract on the same child session after the previous successful result is claimed; each round keeps its own delegation, result identity, and usage while retaining the child Context history.
- Added bounded cumulative limits of four child rounds, 16 LLM calls, 48 tool calls, 64,000 tokens, and 240 seconds. Followups preserve the original child slot and require fresh per-round Skill authorization while keeping parent aggregate budgets and concurrency gates.
- Added atomic schema 4 safe points with bounded idle child snapshots, strict identity/result/Context/usage validation, and resume-time rebind checks for the current role, model, and Skill Catalog. Incompatible snapshots are reported without replaying a worker or request; schema 1/2/3 remain readable.
- Added pure background startup-round handling for spawn and followup, round-indexed status/results, offline lifecycle/resume/failure coverage, lesson 49, and synchronized manuals, plans, README files, and package metadata.
- Preserved provider usage provenance and actual child consumption in resumable-session accounting. A completed report whose snapshot exceeds the limit remains deliverable, with continuation explicitly closed; same-process followups recheck frozen Skill file identity before starting the child.

## [v0.48.0] - In-process background Subagents

- Added parent-only `spawn_subagent`, `get_subagent_status`, `get_subagent_result`, and `cancel_subagent` tools while preserving synchronous `delegate_task` behavior. Background investigations require an explicit named role and run only in the current CLI process.
- Extended `DelegationManager` with queued cross-round workers, shared concurrency and aggregate budgets, cooperative cancellation, bounded completion events, parent-thread settlement, repeatable result claims, and result abandonment at clean task boundaries.
- Added the pure spawn-round gate: handler admission and startup confirmations commit in model order, and no worker starts until the entire durable schema 3 tool round commits. Mixed spawn/tool rounds are rejected.
- Extended State, Trace, session validation, and crash recovery for startup identity, result ID/hash claims, interrupted work, reserved-maximum usage settlement, safe-point refusal, and non-replay of process-local workers. Hardened `ScopeGate` against the actual session root, symlink escape, and path or file-identity changes while reading.
- Added lesson 48 and synchronized `AGENTS.md`, the operation manual, tutorial index, collaboration plan, README files, and package version metadata.

## [v0.47.0] - Named Subagent roles

- Added the optional `delegate_task.agent_profile` selector with frozen `explorer`, `reviewer`, `tester`, `general`, and validated local custom roles; role prompts, tool subsets, static permissions, child model aliases, and configuration fingerprints are fixed when each Runtime is assembled.
- Intersected requested child tools with role tools and the existing read-only allowlist, rejected role/model conflicts before a child LLM request, and preserved the no-role contract hash, result shape, and durable fields.
- Added parent-side exact-ID Skill preauthorization for role-listed Skills and a child catalog/tool view restricted to granted IDs. Skill text stays an untrusted child tool result; `tester` cannot run tests and its report contract rejects claims that tests passed.
- Extended State, schema 3 durable results, and Trace with optional role identity fields; hardened Subagent scope checks for canonical `config_local.py` and workspace session paths. Added lesson 47 and synchronized the runbook and README files.

## [v0.46.0] - Restricted HTTP MCP, text Resources, and Prompts

- Added explicit stdio/JSON-only HTTP MCP transport configuration with HTTPS-by-default URL validation, opt-in loopback HTTP, local headers, bounded responses, session headers, 202 notifications, bounded session DELETE, and no SSE/redirect/OAuth/retry fallback.
- Extended the fixed MCP client with paginated frozen Resource and Prompt directories, text-only reads, prompt argument validation, user/assistant text validation, and capability-only Server support.
- Added parent CLI `/mcp-resources`, `/mcp-resource`, `/mcp-prompts`, and `/mcp-prompt` commands with exact target permissions, complete Prompt previews, explicit confirmation, ordinary untrusted history, Context budgeting, Memory-query exclusion for Resource messages, and Subagent isolation.
- Added an offline HTTP fixture, v0.46 protocol and content-boundary coverage, lesson 46, and synchronized the manual, plans, README files, and version metadata.

## [v0.45.0] - Local Skills discovery and on-demand loading

- Added a standard-library `SkillCatalog` for fixed project and global `skills/<name>/SKILL.md` directories, strict two-field frontmatter, deterministic project precedence, bounded metadata, frozen file identities, and descriptor-based race/symlink checks.
- Added the parent-only `skill(name)` Tool with default `ask` permission, exact-ID `always` approvals, safe failure categories, complete bounded tool results, and metadata-only State/Trace excerpts.
- Added per-request untrusted Skill directory metadata to parent Context with permission filtering and budget fitting; Skill bodies remain ordinary tool history and never enter Subagents, Plan state, or verification evidence.
- Added lesson 45, local Skill fixtures and regression coverage for malformed files, overrides, permissions, replacement races, Context/session boundaries, and the distinction between workflow guidance and later tool authorization.

## [v0.44.0] - MCP Tools in the parent Agent Runtime

- Added explicit `agent_enabled` and exact `readonly_tools` MCP server configuration. Existing servers remain standalone-only unless explicitly enabled.
- Adapted frozen local MCP tools into the parent Tool Registry with strict bounded schemas, normalized names, collision rejection, default `possible` effects, and per-tool PermissionGate prompts that hide credential-like and long values.
- Reused ToolExecutor, Plan gates, schema 3 durable tool boundaries, crash recovery, ordered `role=tool` results, and Runtime lifecycle cleanup without changing the session schema; MCP connections are rebuilt from current local configuration on new and resumed tasks and are never exposed to Subagents.
- Classified MCP JSON-RPC errors, `isError=true`, timeouts, disconnects, protocol errors, and unsupported result content as bounded ExecutionResult failures. Added lesson 44, offline parent-runtime coverage, and synchronized the runbook, plan, README files, and version metadata.

## [v0.43.0] - Minimal stdio MCP client

- Added an independent `mini_agent.mcp` stdio client for the fixed MCP `2025-11-25` lifecycle, paginated tool listing, and one manually confirmed `tools/call`.
- Added bounded JSON-RPC validation, stdout/stderr separation, timeout handling, safe error categories, and direct child-process cleanup.
- Added local `MCP_SERVERS` configuration, an offline fixture, protocol/CLI lifecycle tests, and lesson 43.
- MCP tools remain outside the Agent Runtime, Tool Registry, PermissionGate, State, and session; v0.44–v0.46 remain planned.
- Hardened the review boundaries: frozen tool catalog, bounded notification history, complete call preview, visible cleanup failure, and strict JSON-RPC error codes.

## [v0.42.0] - Named local references

- Added parent-only, standard-library `ReferenceCatalog` with frozen named local directories, bounded UTF-8 reads, literal case-insensitive search, SHA-256 provenance, and deterministic alias-relative results.
- Added `list_references`, `search_reference`, and `read_reference`; listing is allowed by default while search and read remain alias/path-scoped permission prompts.
- Rejected traversal, absolute paths, directory symlink escapes, sensitive configuration/memory/session paths, oversized or non-UTF-8 files, and unsafe reference roots without exposing real roots.
- Unified Reference access failures with Executor failure semantics (`reference_access_error`), hardened canonical descriptor-based opens and race checks, and made line/match truncation metadata self-consistent with bounded search scan budgets.
- Kept References out of Context auto-retrieval, Memory, verification evidence, session schema, and the fixed Subagent whitelist; added lesson 42 and synchronized manuals, plans, README files, and version metadata.

## [v0.41.0] - Relevant memory retrieval

- Added standard-library lexical `MemoryRetriever`, validated read-only snapshots, Unicode normalization, Chinese fragments, weighted fields, phrase scoring, deterministic ordering, bounded snippets, and conservative `source_status="unverified"` results.
- Added parent-only read-only `search_memories(query, limit)` with a complete 16 KiB JSON result limit and default-allow permission; Subagents still cannot access Memory.
- Added per-request parent Context retrieval from the task and latest user message, with at most four candidates and 2400 characters, an independent memory token bucket, ephemeral untrusted system material, and no State/history/session/verification persistence.
- Added retrieval disable configuration, current-workspace rebinding on resume, observable bounded failure degradation with retry-on-next-request, lesson 41, and synchronized manuals, plans, README files, and version metadata.

## [v0.40.0] - Lightweight persistent workspace memory

- Added a standard-library schema 1 `MemoryStore` with workspace SHA-256 isolation, bounded CRUD records, private permissions, exclusive locks, atomic replacement, directory sync, and explicit uncertain-commit halting.
- Added parent-only `list_memories`, `read_memory`, `remember`, `revise_memory`, and `forget_memory` tools; reads are allowed while modifications ask for approval and use optimistic revisions.
- Added paged memory summaries (`offset`, `total`, and `next_offset`) so records after the first 20 remain discoverable, and rejected `MEMORY_DIR` paths inside the workspace, including symlink-resolved paths.
- Kept memory outside `AgentState`, Plan, verification evidence, and session snapshots; durable tool boundaries and crash recovery never replay an admitted memory write, while model history may still contain its call parameters.
- Added the `memory_commit_uncertain` result classification and recovery guidance for a replacement whose directory sync was not confirmed; read-only inspection remains available while later writes stop.
- Added lesson 40, memory storage/manual guidance, navigation updates, v0.40 tests, and the optional `MEMORY_DIR` configuration.

## [v0.39.0] - Durable delegation delivery

- Added a bounded schema 3 `pending_delegation_results` area that stores validated child result JSON and its hash before parent delivery.
- Persisted delegation contracts and `created → running → result_ready → committed` lifecycle facts before starting workers, including out-of-order child completion.
- Committed the parent attempt, State lifecycle, ordered `role=tool` message, and durable boundary together; storage failure stops later parent model requests.
- Extended crash recovery to deliver persisted results in parent call order without invoking child LLMs again, while classifying admitted calls without results as interrupted investigations.
- Added bounded delegation projections to Context and Trace, v0.39 durable delegation tests, lesson 39, and synchronized the manual, plans, README files, and package version.
- Fixed delegation Trace rendering and linked parent attempts to lifecycle events; interrupted investigations now retain a distinct audit status without a synthetic child result or reported actual usage.

## [v0.38.0] - Bounded parallel subagents

- Added a dedicated standard-library `DelegationScheduler` for multiple independent read-only `delegate_task` calls in one parent assistant round.
- Kept parent State, Context, `role=tool` history, and schema 3 tool boundaries in model tool-call order while allowing child workers to finish out of order.
- Split reserved aggregate budget from running slots, added batch reservation and ordered settlement, and preserved actual usage when a provider reports over-reservation.
- Added partial-failure delivery, batch budget and duplicate-contract rejection before child LLM calls, broadcast cancellation, and cleanup reporting for all unfinished subagent IDs.
- Added lesson 38, parallel delegation regression coverage, updated defaults to 3 subagents / 2 concurrent workers / 24 LLM calls / 72 tool calls / 96,000 tokens, and synchronized manuals and navigation.

## [v0.37.0] - Subagent lifecycle and aggregate budgets

- Added parent-side `DelegationRecord` lifecycle facts with ordered `created → running → result_ready → committed` delivery and independent execution outcomes.
- Added bounded parent aggregate budgets for child count, LLM calls, tool calls, and tokens; reservations are made before child execution and settled with actual usage.
- Added cooperative Event cancellation, bounded task-boundary cleanup, timeout/error accounting, output caps, and cancellation-aware child Runtime policy checks.
- Propagated child user interrupts after the parent tool result is committed, and gated auxiliary child summaries against the same call, token, and time budgets.
- Added delegation summaries, remaining aggregate budgets, normalized finding/evidence stagnation hashes, safe-point guards, and schema-3 recovery reservation reconciliation.
- Kept v0.37 synchronous with one child at a time; parallel delegation and durable cross-process result delivery remain future work.

## [v0.36.0] - Multiple providers and unified protocol adapters

- Added standard-library provider catalog, frozen parent/child model bindings, profile allowlists, legacy configuration compatibility, safe binding fingerprints, and redacted provider errors.
- Added OpenAI-compatible Chat Completions and Anthropic Messages adapters with streaming/non-streaming tool-call normalization, ordered tool results, system/tool-result conversion, strict incomplete-stream handling, and provider/estimated/mixed usage accounting.
- Bound Context windows, summaries, Subagent selection, and usage meters to the selected profile while keeping the canonical `AgentRuntime.run()` and v0.35 synchronous depth=1 read-only delegation boundary.
- Kept credentials, real endpoints, model IDs, and authentication headers out of State, Context, session, Trace, tool results, and user-visible errors; lifecycle, cancellation, aggregate budgets, parallel delegation, and durable delegation records remain future work.
- Fixed non-streaming answer display, timeout outcome classification, per-run usage source accounting, and local HTTP integration fixtures; saved parent binding references now reject changed model configuration on resume, while public fingerprints exclude authentication material.

## [v0.35.0] - Shared parent and subagent runtime

- Converged the parent Agent and synchronous read-only Subagent onto one canonical `AgentRuntime.run()` loop.
- Added policy-based parent and child boundaries for planning, repair, processes, durable rounds, budgets, observations, and the child result contract.
- Unified malformed tool-call normalization and ordered `role=tool` closure, while preserving the v0.34 delegation contract and four-tool read-only surface.
- Added shared-runtime protocol and isolation regression coverage; multiple providers, lifecycle/cancellation, parallel delegation, and durable delegation records remain future work.

## [v0.34.0] - Minimal controlled subagent delegation

- Added synchronous, single-level `delegate_task` with isolated child State/Context, fixed read-only capabilities, workspace scope checks, bounded budgets, and a strict structured result contract.
- Added immutable delegation dataclasses, evidence/reference validation, one format-correction attempt, estimated usage accounting, and deterministic single-child busy rejection.
- Kept the parent Agent as the only owner of permissions, Plan, workspace changes, generation, authoritative verification, and completion; parallel delegation, cancellation, aggregate budgets, and durable delegation records remain future work.

## [v0.33.0] - Crash recovery and uncertain-effect handoff

- Added schema 3 crash recovery for active pending tool boundaries. Recovery derives a new session, preserves the source byte-for-byte, and uses a private atomic claim sidecar to prevent duplicate branches.
- Classified interrupted calls as `not_executed`, `uncertain_state_or_result`, or `uncertain_side_effect`; synthesized one ordered tool result per call without replaying handlers.
- Added per-issue `/resolve <issue_id> investigate|continue|block` decisions, read-only investigation gates, crash-recovery replan triggers, fresh generations, and invalidated current verification evidence.
- Added bounded crash facts to Structured State and read-only Trace, including recovery → issue → decision → trigger causal edges, plus v0.33 recovery tests and documentation.

## [v0.32.0] - Durable tool execution boundaries

- Raised new session writes to schema 3 while retaining schema 1 diagnostics and schema 2 clean safe-point resume; claiming a schema 2 session upgrades it atomically.
- Persisted one ordered tool boundary with redacted arguments, permission and handler admission facts, attempt/generation references, and pending/committed results in the same atomic session file as State and Context.
- Committed handler admission before entering a handler, committed each State/history/tool result in model order, and allowed the next LLM request only after the whole round was committed. Storage failures stop subsequent handlers and model requests.
- Kept `run_shell`, including `purpose="verification"`, in the possible-effect class; natural process exits are persisted as State facts without synthetic tool replies. v0.32 records incomplete rounds for diagnosis but does not resume them.
- Added durable-boundary fault-injection coverage and lesson 32.

## [v0.31.0] - Safe resume from complete safe points

- Raised new session writes to JSON `schema_version=2` with a bounded workspace manifest covering structured file facts, changed files, failures, checkpoints, and recursive grep scopes; shell command text is not treated as a path declaration.
- Added `python -m mini_agent --resume <session_id>` for validated `clean` safe points. The CLI checks the workspace, builds a fresh State/Context/Registry/ProcessManager/PermissionGate, claims the session under its exclusive lock, and waits for user input without an automatic LLM request.
- Added strict State and Context restoration, a resume generation, invalidated current verification evidence, preserved verification history, re-discovered project instructions, and fresh permission state.
- Imported old checkpoint and process metadata for audit only: old `ready` checkpoints become unavailable without before-image bytes, old PIDs and process IDs are not controllable, and new process IDs skip historical IDs.
- Kept schema 1 readable for diagnostics only; active, damaged, workspace-changed, incomplete, symlink-dependent, and lock-contended sessions fail before any LLM or handler call. The workspace is checked again when claiming a prepared resume candidate. Added lesson 31 and synchronized the manual, README files, and session-resume plan.

## [v0.30.0] - Session persistence and safe points

- Added explicit `/save` opt-in session persistence with random session IDs and automatic active-point updates after complete agent turns.
- Added JSON `schema_version=1` envelopes under `~/.mini_agent/sessions/`, private permissions, exclusive lock files, canonical SHA-256 integrity checks, bounded reads, and same-directory atomic replacement.
- Added authoritative `AgentState.export_session()` and `ContextManager.export_session()` validation, including private counters, repair/recovery facts, checkpoint metadata, complete tool-call/result pairing, and pending Runtime Notice state.
- Redacted `write_process.input` in saved assistant tool-call arguments while preserving the JSON shape and `tool_call_id`; saving fails if the input also appears in other persisted text. Runtime LLM configuration and checkpoint bytes are not serialized.
- Normal exit, `/new`, and `/reset` commit `clean` only after bounded process cleanup. Cleanup errors, active processes, in-flight stdin, pending attempts, exceptions, corrupt files, and pre-replacement save failures retain or report an `active`/unsaved state; post-replacement failures report an uncertain commit with its session ID.
- Added lesson 30 and documented that v0.30 validates sessions but does not provide cross-process resume; `--resume` remains planned for v0.31.

## [v0.29.0] - Bounded process stdin

- Added optional pipe stdin to `start_process` and the task-owned `write_process` tool for bounded UTF-8 text input and explicit EOF, with a 4096-byte per-call limit and a two-second bounded writer wait.
- Added separate write authorization, ownership and planning prechecks, in-flight write state, bounded cleanup, and process completion guards that wait for stdin writes to settle.
- Confirmed stdin pipe closure after an exit races with write admission; classify Broken Pipe as an execution failure, report uncertain delivery without claiming written bytes, and keep rejected unknown IDs from breaking Trace integrity.
- Kept input bodies out of State, Trace, tool results, authorization prompts, compatibility history, and terminal/debug output; writes still require later process observation and independent verification.
- Added lesson 29 and synchronized the runbook, navigation, process-management plan, and package version. PTY support remains deferred after evaluating terminal echo, control characters, sizing, and cross-platform cleanup boundaries.

## [v0.28.0] - Background process control and task closure

- Added task-owned `terminate_process` and `kill_process` with separate default-ask permissions, pre-permission ownership checks, bounded exit confirmation, and explicit still-running/already-exited results.
- Linked confirmed control exits to unique terminal process events, control attempts, successor generations, and read-only Trace integrity checks. Old verification remains invalid after exit.
- Added lesson 28 and synchronized the manual, navigation, and package version.

## [v0.27.0] - Process observation and bounded waiting

- Added task-scoped `get_process`, `read_process`, `list_processes`, and `wait_process` tools. Reads use separate byte cursors for stdout and stderr, report buffer gaps, preserve UTF-8 boundaries, and return bounded JSON.
- Added asynchronous `FailureEvent` records for natural nonzero exits, linked to the unique terminal process event and launch attempt without rewriting the launch result. Trace validates this cross-generation cause using State snapshots only.
- Made process observations serial within a tool round. A `wait_process` timeout hands the current task to the CLI as `awaiting_process` after its tool result is recorded.
- Added lesson 27 and synchronized the runbook, navigation, package version, and process-management plan.

## [v0.26.0] - Background process start and task boundaries

- Added the standard-library `ProcessManager` and the model-visible `start_process(command, cwd?)` tool. It returns immediately with a task-owned `process_id`, keeps stdin closed, drains both output streams, and bounds each stream at 64 KiB.
- Added task-scoped process records and append-only `started`, natural `exited`, and natural `failed` lifecycle events with generation and launch-attempt references. Process exit invalidates current verification and opens exactly one successor generation.
- Added the `awaiting_process` handoff for text-only model replies while a process is still running. The CLI resumes the original task on the next user input after synchronizing process state.
- Added task-boundary cleanup for `/new`, `/reset`, EOF, `exit`, `KeyboardInterrupt`, and exceptional CLI exits. Completion waits for the direct child, the managed POSIX process group, and both output pipes; incomplete cleanup retains the process ID and PID for a bounded retry. On Windows, confirmed direct-child and pipe cleanup permits task switching while reporting the unverified descendant-tree limit.
- Stream collectors now expose short flushed output promptly and retain started-thread registrations across startup failures. Detached POSIX descendants that close inherited pipes and leave the managed group remain outside this lifecycle boundary.
- Preserved synchronous `run_shell` behavior, its 30-second timeout, output format, and independent command-pattern permission rules.
- Added lesson 26, process lifecycle tests, and synchronized the runbook, navigation, README files, package version, and process-management plan status.

## [v0.25.0] - Plan trace and evaluation

- Added append-only task-local `TraceEvent` ordering for plan, trigger, decision, execution, recovery, verification, and stagnation facts.
- Extended read-only Trace with revision queries, ordered plan timelines, revision fact ownership, plan causal edges, integrity checks, and evidence-backed conclusions.
- Added `/trace revision <revision_id>` while preserving generation queries and v0.21 snapshots.
- Added lesson 25 and synchronized the runbook, navigation, version metadata, and adaptive-planning completion state.

## [v0.24.0] - Evidence-backed replanning and bounded stagnation

- Added source-backed `request_replan` triggers for failures and successful read-only observations, plus CLI-only user feedback and blocked-resume triggers.
- Added task-wide replan revision budgets, per-trigger unchanged-submission budgets, runtime-computed revision differences, and Direct failure/resume first-plan exceptions.
- Added `/resume <feedback>` for blocked tasks while keeping failed tasks and model-driven terminal recovery closed.
- Added deterministic complete-tool-round stagnation detection with protected Runtime Notices, bounded hashes, and explicit blocked reasons.
- Preserved Repair Loop failure, generation, repair-cycle, and verification boundaries across replanning; updated Structured State, compaction, prompt, manual, README navigation, and lesson 24.

## [v0.23.0] - Read-only planning and handoff

- Added `begin_plan`, `cancel_planning`, and `--plan` for Runtime-enforced read-only exploration while retaining the Direct Path.
- Enforced planning admission at tool-round and executor boundaries; rejected calls retain tool results without reaching permission, handlers, generations, or verification.
- Added current-revision approval, rejection, continued investigation, and unchanged-plan review through CLI commands. User feedback remains task-local; plan approval never grants tool permission.
- Added lesson 23 and synchronized the runbook, navigation, and stage-seven plan.

## [v0.22.0] - Plan Contract

- Replaced the model-visible whole-list `update_todo` write protocol with `commit_plan` and `update_plan_progress`.
- Added frozen `PlanStep`, `PlanRevision`, `PlanProgressEvent`, and `PlanningState` models with atomic validation, immutable revision history, dependency checks, status inheritance, and read-only Todo projections.
- Added bounded active-plan rendering to Structured State and kept plan writes out of generation changes and verification evidence.
- Rejected plan submissions return `plan_rejected` without creating a `FailureEvent`; plan tools remain default-allow, effect-free state tools and are excluded from recovery targets.
- Added the Plan Contract tutorial and synchronized the v0.22 runbook, context architecture, README navigation, and stage-seven plan status.

- Added bounded terminal output modes (`quiet`, `normal`, `debug`) with lazy streamed assistant output, grouped tool summaries, structured outcomes, and explicit CLI/permission notices.
- Added the `call_llm` content observer callback while preserving complete tool protocol messages and standard-library-only execution.

## [v0.21.0] - Trace & Replay

- Added immutable task-local `TodoRevision` snapshots for every successful Todo submission, with generation binding and reset/new-task cleanup.
- Added append-only verification history without changing current-generation completion evidence, plus read-only `build_trace()` / `render_trace()` APIs with generation grouping, strict causal validation, terminal conclusions, and unresolved links for damaged snapshots.
- Added `/trace` and `/trace <generation_id>` CLI replay with forced visibility in quiet mode; replay never calls the LLM, tools, permission gate, or mutates task state.
- Added Trace & Replay tutorial, CLI/API documentation, security-boundary tests, and a real registry/file/shell failure-recovery-verification E2E.

## [v0.20.0] - Repair Loop

- Added explicit `idle`, `diagnosis_required`, and `verification_required` repair phases with active failure/recovery references in Structured State.
- Added bounded repair-cycle accounting: only an authorized and activated `retry`, `adjust`, or `rollback` consumes a cycle; rejected actions and the initial failure do not.
- Enforced diagnosis and post-recovery verification admission in both the agent loop and ToolExecutor while preserving one `role=tool` result per model call.
- Added independent post-recovery verification requirements, critical-state rendering, Runtime Notice guidance, and v0.20 Repair Loop tests/tutorial coverage.

## [v0.19.0] - Checkpoint / Rollback

- Added task-local single-file checkpoints for admitted `write_file` and `edit_file` calls.
- Added bounded rollback with before-image bytes, mode restoration, absent tombstones,
  SHA-256 conflict detection, same-directory atomic replacement, and explicit blocked
  outcomes for conflicts or interrupted restores.
- Kept rollback behind the existing recovery quota and PermissionGate; the internal
  `rollback_checkpoint` tool is not exposed in LLM schemas and still records a full
  possible-effect attempt with causal links.
- Added checkpoint metadata to Structured State without exposing original bytes or
  absolute paths, plus reset/new task cleanup and v0.19 tutorial coverage.
- Kept checkpoint metadata visible in file-tool results and compacted or degraded
  Structured State views; ready before/after images keep handler failures recoverable,
  internal tools cannot be retry/adjust targets, and mode `0` is restored exactly.

## [v0.18.1] - Recovery Policy fixes

- Classify edit precondition failures without treating them as unknown writes.
- Record rejected recovery requests exactly once and block when their budget is exhausted.
- Reserve recovery quotas before target authorization using the session permission gate;
  open generations only after approval and release unused execution quotas on rejection.
- Preserve recovery causal links and display failure references and budgets in Structured State.
- Enforce terminal states while returning a result for every pending tool call.
- Update lesson 18 with the patch snapshot; no checkpoint, rollback, repair scheduler, or replay is added.

Previously unreleased mainline changes included in this snapshot:

- Raised the current mainline minimum supported Python version from 3.9 to 3.10.
- Recreated the recommended development environment with Python 3.10.
- Added optional `prompt_toolkit` terminal input via the `interactive` extra:
  multiline paste is supported with Enter to submit and Shift+Enter to insert a
  newline; the standard-library `input()` path remains the fallback.
- Clarified that zero third-party dependencies applies to core runtime flows;
  user-experience integrations may be optional and must provide a fallback.
- Added explicit `/new <task>` and `/reset` task boundaries. Task-local execution,
  Todo, failure, recovery, generation, retry, and verification state are reset in
  place; session permissions and protected project instructions remain available.
- Structured State is rendered on every request with a deterministic size limit.

## [v0.18] - Recovery Policy

- Added schema-validated `recover` actions: retry, adjust, ask, and block.
- Added bounded recovery reservations, successor generations, and explicit causal links.
- v0.18 deliberately rejects rollback and requires independent verification after recovery.

## [v0.16.1] - Completion progress reminders

- Fixed completion reminders so each observable progress state is reminded at
  most once; Todo changes, tool observations, and verification facts reopen a
  new correction opportunity.
- Clarified the Runtime Notice and system rules: after an intermediate report,
  the next response must call a progress-making tool unless the task is
  concretely blocked.
- Added deterministic regression coverage for no-progress blocking,
  investigation reports, Todo marker stability, failed tools, and verification
  closure.

## [v0.16] - Plan-driven Execution

- Added verification evidence, task reset, completion reminders, and blocked/failed task states.
- Added `run_shell` purpose enum with unified exit status output.
- Added stage-five end-to-end acceptance coverage for project instructions, Todo replanning, context compaction, and verification closure.

## [v0.15] - Todo / Task State

- Added state-bound `update_todo` with atomic validation and Structured State rendering.
- Added per-run registries to isolate Todo state between AgentState instances.
- v0.15 does not auto-plan, persist todos, or block completion.

## [v0.14] - Project Instructions

### Added
- `InstructionLoader`: discovers and merges applicable `AGENTS.md` files, keeping sources and limiting length.
- Protected context: project rules are re-injected after trimming/compaction.
- `docs/tutorials/14-project-instructions.md` and instruction loading tests.

### Changed
- The CLI loads project instructions at startup; `build_system_prompt()` supports a `<project_instructions>` block.
- `ContextManager` supports separate protected messages, compatible with old history calls.

### Why
- Give the Agent project constraints before it runs a task, while avoiding treating rules as compactable conversation history.

## [v0.13.1] - Context Observability enhancement

### Added
- `ContextStats` and `ContextManager.stats_snapshot()`: record the total tokens of the actual request, the budget, the output reserve, and mutually exclusive buckets.
- `ContextEvent` observer: observes prepared, trimmed, and compacted events; the default terminal log can be turned off with `CONTEXT_OBSERVABILITY`.
- The v0.13 tutorial adds Context Observability notes; this version adds no separate tutorial.

### Changed
- Trimming logs record the objects and token savings of tool result truncation and complete round deletion.
- Compaction logs record compacted rounds, summary size, and kept rounds; observer callback exceptions do not affect context building.

## [v0.13] - Context compaction

### Added
- `ContextManager.compact()`: old-round summaries, recent-round retention, and Structured State injection
- Summary requests reuse `http.client` and carry no tool schemas; summary failure automatically degrades to trimming
- `docs/tutorials/13-context-compaction.md` and compaction flow unit tests

### Changed
- `MAX_ITERATIONS` changed from 10 to 50
- `prepare_messages()` automatically triggers compaction when the budget is exceeded and old rounds exist

## [v0.12] - Budget and trimming

### Added
- `src/mini_agent/context.py`: `count_tokens` (`len(text) // 3` heuristic), `ContextBudget` (window, output reserve, and history ratio), and `TrimPolicy`
- `CONTEXT_WINDOW = 128_000`: written to `config.py` and `config_example.py`, can be overridden by `config_local.py`
- `docs/tutorials/12-token-budget-trimming.md`: Lesson 12 teaching document
- `tests/test_context.py`: tests for token estimates, budgets, round atomicity, tool result truncation, guaranteed messages, and budget convergence

### Changed
- `ContextManager.prepare_messages()` builds a separate copy from the full history: when over the limit, it first truncates old tool results, and when still over the limit, deletes from the oldest round
- System messages and the first user task do not take part in trimming; assistant messages with `tool_calls` and their consecutive tool results are handled as an indivisible round

### Why
- Context is a finite resource, and long tasks should not fail directly because tokens accumulate.
- OpenAI tool calling requires tool results to directly follow the matching tool call; atomic deletion by round avoids orphan `role=tool` messages that would cause a 400.
- Neither the original history nor AgentState is trimmed, keeping the correct boundary for v0.13 history summaries and Structured State anchoring.

## [v0.11] - Context architecture

### Added
- `src/mini_agent/state.py`: `AgentState` dataclass (task/current_goal/tool_history/files_changed/errors/status) + `record_tool` execution record interface + `snapshot` thread-safe snapshot
- `src/mini_agent/context.py`: `ContextManager`, with `prepare_messages()` as the unified entry before LLM calls (returns identity in this version, only setting the boundary)
- `tests/test_state.py`: State unit tests (10: records/derived fields/deep copy isolation/concurrency safety)
- `tests/test_context.py`: ContextManager unit tests (5: reference kept/identity return/State not injected)
- `tests/test_executor.py`: Executor callback unit tests (14: callbacks on three paths/callback exceptions do not affect execution/brief truncation/concurrent callbacks)
- `docs/tutorials/11-context-architecture.md`: Lesson 11 teaching document

### Changed
- `src/mini_agent/agent.py`: `agent_loop(messages)` changed to `agent_loop(context_manager, tool_executor)`, calling the LLM through `cm.prepare_messages()`; removes the v0.10 "MAX_ITERATIONS half state" contract (all tool results of each round are fed back before entering the next round or returning)
- `src/mini_agent/tools/base.py`: `ToolExecutor` adds an `on_result` result callback (notified on all three paths: permission refusal/handler exception/success; brief truncated to 200 characters; callback exceptions are only printed and do not affect execution)
- `src/mini_agent/__main__.py`: assembles AgentState + ContextManager and injects them into the loop; `run_task` unifies the argv/interactive paths and maintains `state.status`
- `src/mini_agent/agent.py`: `call_llm` chooses `HTTPConnection`/`HTTPSConnection` by the scheme of `BASE_URL` (before this, plaintext HTTP to an https gateway got a 302 and an empty LLM reply)
- `tests/test_tools.py`: fixed `test_run_shell_exit_code` hanging on reading stdin under pytest (an allow policy bypasses the ASK interaction)

### Why
- **Agent State ≠ LLM Context** (D1): messages are consumables (trimmed/compacted sooner or later), and State is the anchor that does not lose memory after compaction. The v0.09 PermissionGate always state already proved that "runtime state independent of messages" works.
- **Pure refactor version**: external behavior is fully the same as v0.10, with no trimming, no compaction, and no token estimates—first set the boundaries of "who can touch messages" (only ContextManager) and "where state lives" (AgentState), so the engineering of v0.12/v0.13 has a place to land.
- **State is updated by the Executor result callback, and the loop is unaware of it** (D5): otherwise State would become a second, unmaintained messages. The callback concentrates records in one place, the Executor, and it is an observer, not a participant (exceptions do not affect execution results).
- **Thread safety**: since v0.06, tool_calls in the same round run concurrently, and callbacks come from thread pool worker threads; `record_tool` takes a Lock, and reads go through a `snapshot()` deep copy.
- **Half state removed**: the v0.10 docs already warned that messages might stop in the protocol-illegal state of "tool_calls without tool results"; this version fixes it at the code level—this also paves the way for v0.12 atomic trimming by round (round integrity is guaranteed from now on).

## [v0.10] - Shell execution

### Added
- `src/mini_agent/tools/shell.py`: `run_shell` tool (`subprocess.run` + `shell=True` + 30 s timeout + output truncated at 2000 characters + exit code prefix)
- `docs/tutorials/10-shell-execution.md`: Lesson 10 teaching document

### Changed
- `src/mini_agent/tools/__init__.py`: registers `run_shell_tool` (7 tools)
- `src/mini_agent/permission.py`: `PERMISSION_RULES` adds two-dimensional `run_shell` permission rules (`git *`/`python *`/`pip *`/`ls *`/`cat *`/`echo *` → allow, `*` → ask); `_from_config` sorts the complex format with `*` first (lowest priority), working with findLast semantics
- `src/mini_agent/prompt.py`: the capability description in `header()` changed from "will later extend to running commands" to "can currently read, write, and edit files, run commands, and do math"
- `tests/test_tools.py`: adds 3 run_shell tests (run echo, non-zero exit code, two-dimensional permission git allow/rm deny)

### Why
- The v0.09 two-dimensional permissions already paved the way for `run_shell` (`_extract_pattern` returns the command string); v0.10 lands the tool itself.
- No BashArity command generalization: the fnmatch `git *` wildcard already matches by command prefix, and teaching simplicity comes first. Introduce it later if separate "command + arguments" matching is needed.
- `shell=True` runs the command string directly, for teaching simplicity; safety is backed by the two-dimensional permission gate (safe commands allow, others ask).
- The 30 s timeout is hard-coded: enough for running tests; long tasks are adjusted in a later Context Management version.
- Output truncated at 2000 characters: prevents long output from blowing up the context, consistent with the `read_file` limit design.
- `_from_config` sorting fix: findLast searches from the end, and `*` matches everything, so it must be placed first (lowest priority); otherwise `*` always matches first and returns ask, shadowing specific patterns.

## [v0.09] - Permission system upgrade

### Changed
- `src/mini_agent/permission.py`: upgraded from one-dimensional `tool_name -> action` to two-dimensional `(tool_name, pattern) -> action`
  - Rules are stored internally as a flat `list[dict]` (Rule triple: permission + pattern + action)
  - `_from_config()` is compatible with the old simple dict format (`{"write_file": "ask"}`) and the new complex format (`{"run_shell": {"git *": "allow"}}`)
  - `check()` does wildcard matching with `fnmatch`, with `findLast` semantics (later rules have higher priority), defaulting to `ask` when nothing matches
  - `approve()` saves `(tool_name, pattern)` instead of only `tool_name`, so "commands of the same kind are not asked again"
  - `_extract_pattern()` extracts the pattern from args (file tools extract path, run_shell extracts command, others return `*`)
- `tests/test_tools.py`: adds 4 two-dimensional permission tests (pattern allow/deny override, always saves pattern, findLast priority)

### Why
- The v0.04 one-dimensional permissions controlled only by tool name and could not distinguish `git status` (safe) from `rm -rf /` (dangerous)—all `run_shell` calls shared the same action, which was too coarse.
- Two-dimensional permissions control by command pattern: `git *` can be allow, `rm *` can be deny, and others ask. This paves the way for command pattern permissions of the v0.10 `run_shell` tool.
- `findLast` semantics let runtime `approved` rules (appended at the end) naturally override earlier `ask` rules, without explicitly deleting old rules.
- Defaulting to `ask` instead of `allow` when nothing matches—safety first, new tools need user confirmation by default.
- Borrows the `evaluate` / `fromConfig` / `findLast` design of OpenCode `PermissionNext`, removing the event bus, pending queue, and persistence—synchronous CLI interaction does not need them.
- `_extract_pattern()` returns the full command string for `run_shell` as a placeholder; v0.10 uses fnmatch wildcards (such as `git *`) directly to match by command prefix, without BashArity command generalization—fnmatch is enough.

## [v0.08] - File operations completed

### Added
- `src/mini_agent/tools/file.py`: adds `edit_file` (exact string replacement, multi-match safety check), `list_dir` (directory listing, 200 entry limit), and `grep` (regex search, 100 entry limit, pure standard library `re`+`os.walk`+`fnmatch`)
- `docs/tutorials/08-file-operations.md`: Lesson 8 teaching document

### Changed
- `src/mini_agent/tools/file.py`: `read_file` adds `offset`/`limit` partial reads + line number prefixes (`00001| `) + a remaining-lines hint
- `src/mini_agent/permission.py`: `list_dir`/`grep` go to ALLOW, `edit_file` goes to ASK
- `src/mini_agent/tools/__init__.py`: registers 6 tools
- `tests/test_tools.py`: expanded from 8 to 15 tests (adds read_file offset/limit, edit_file single/no match/multiple matches, list_dir, grep match/no match)

### Why
- v0.03 had only read_file/write_file; the agent could not see directory structure, could change files only by rewriting whole files, and could not find where content was—adding list_dir/edit_file/grep forms a complete operation chain.
- `edit_file` uses string matching instead of line number editing: LLMs easily miscount line numbers, and copying original text from read_file output is more reliable. Multiple matches report an error instead of silently replacing the first one, to prevent wrong changes.
- `read_file` adds offset/limit: large files do not blow up the context; line number prefixes help the LLM locate the old_string for edit_file.
- `grep` uses the pure standard library instead of ripgrep: the zero third-party dependency convention. Performance is worse but enough for teaching; after v0.10 adds run_shell, the LLM can call rg itself.
- No OpenCode-style 8 fuzzy matching strategies, temporary output files, file locks, or LSP integration—over-design for a teaching project.

## [v0.07] - System prompt engineering

### Added
- `src/mini_agent/prompt.py`: `build_system_prompt(agent_name)` layered assembly (header identity + `_CORE_RULES` behavior rules + `environment` environment info); `_detect_git` detects a git repository by pure directory traversal
- `tests/test_prompt.py`: system prompt smoke test (assembly / header / fallback / environment fields)
- `docs/tutorials/07-system-prompt.md`: Lesson 7 teaching document

### Changed
- `src/mini_agent/__main__.py`: `messages[0]` changed from a one-line hard-coded string to a call to `build_system_prompt()`

### Why
- A one-line system prompt lacks environment info (working directory/platform/date), and the model easily makes mistakes guessing paths and commands.
- Without behavior rules, the model may be verbose, add emoji, restate tool output, or summarize unprompted—polluting the context over many iterations.
- The layered assembly (header/core_rules/environment) borrows OpenCode's four-layer structure and subtracts from it: removes provider adaptation (single model) and custom loading (left for v0.08).
- `header(agent_name)` reserves an interface for multi-agent/sub-agent; currently only build is implemented, and adding explore/plan later needs only one more line in the dict.
- `agent.py` is untouched—the core loop still knows only the messages list; prompt construction is the entry layer's duty, keeping the loop clear.

## [v0.06] - Concurrent tool_calls

### Changed
- `src/mini_agent/agent.py`: tool_calls execution in `agent_loop` changed from a serial for loop to `ThreadPoolExecutor` concurrency; `pool.map` guarantees results are fed back in the original order

### Why
- Several tool_calls in the same round do not depend on each other, and serial execution wastes time.
- `ThreadPoolExecutor` is "minimal change + good enough concurrency"—the whole call chain does not need to become async.
- `pool.map` guarantees the result order matches the original tool_calls order, so feedback order is safe.
- The v0.04 `_ask_lock` takes effect in the concurrent case: it prevents several ASK permission interactions from interleaving.

## [v0.05] - Streaming output

### Changed
- `src/mini_agent/agent.py`: `call_llm` changed to streaming (`stream=True` + SSE parsing + chunk joining + typewriter effect); the print marker in `agent_loop` moved before `call_llm`

### Why
- Without streaming, the LLM returns only after it has fully finished thinking, and long replies cause a visible wait in the terminal.
- Streaming shows text as it arrives, and the typewriter effect makes it feel faster to the user.
- `http.client` + `Accept-Encoding: identity` guarantees an uncompressed raw text stream, so line-by-line parsing is reliable.
- tool_calls arguments are joined across chunks (`+=`) and aggregated by index—the way to handle structured data under streaming.

## [v0.04] - Permission gate

### Added
- `src/mini_agent/permission.py`: `PermissionPolicy` (three states allow/deny/ask) + `PermissionGate` (check + interaction + lock)
- `docs/tutorials/04-permission-gate.md`: Lesson 4 teaching document

### Changed
- `src/mini_agent/tools/base.py`: `ToolExecutor` adds a `gate` parameter, and `execute` first passes `gate.guard` before calling the handler
- `src/mini_agent/tools/__init__.py`: imports PermissionGate (the executor automatically creates a default gate)
- `tests/test_tools.py`: write_file uses an allow policy to bypass ASK; adds a DENY policy test

### Why
- The v0.03 write_file ran directly without asking anyone, with the risk of overwriting important files.
- Three states (allow/deny/ask) cover the three real needs "always allow/always forbid/depends", more flexible than two states.
- A refusal is not an error but a tool result, fed back to the LLM so it adjusts its strategy—fault tolerance is in the tool layer.
- `_ask_lock` is reserved for v0.06 concurrent tool_calls, to prevent several permission prompts from interleaving.

## [v0.03] - File read/write tools

### Added
- `src/mini_agent/tools/file.py`: `read_file`/`write_file` tools
- `examples/input.txt`, `examples/input2.txt`: example files
- `docs/tutorials/03-file-tools.md`: Lesson 3 teaching document

### Changed
- `src/mini_agent/tools/__init__.py`: registers read_file/write_file
- `tests/test_tools.py`: adds read_file/write_file tests

### Why
- An agent that does not change files cannot do programming tasks; file read/write is a basic capability.
- First make "can write files" work; permissions are a separate concept, covered specifically in v0.04.
- Adding a tool needs only a handler + registration, without touching agent.py—proving the benefit of the three-part separation of concerns.

## [v0.02] - First tool

### Added
- `src/mini_agent/tools/base.py`: the `Tool`/`ToolRegistry`/`ToolExecutor` trio
- `src/mini_agent/tools/calc.py`: `calculate` tool (math expression evaluation, regex allowlist against injection)
- `src/mini_agent/tools/__init__.py`: registration center, creates the registry + executor and registers calculate
- `tests/test_tools.py`: tool smoke test (registry/calculate/exception handling)
- `docs/tutorials/02-first-tool.md`: Lesson 2 teaching document

### Changed
- `src/mini_agent/agent.py`: `call_llm` adds a `tools` parameter (function calling protocol); `agent_loop` adds tool_calls execution + `role=tool` feedback
- `src/mini_agent/__main__.py`: system prompt changed to "You are an assistant that completes tasks by calling tools"

### Why
- Introduces the OpenAI function calling protocol, so the LLM can really "do things" instead of only chatting.
- The Tool trio (definition/registration/execution) separates concerns; adding tools later needs only a handler + registration, without touching the loop.
- The Executor catches handler exceptions and returns error messages to the LLM, letting the LLM decide whether to retry or tell the user—fault tolerance is in the tool layer, not the loop layer.

## [v0.01] - Minimal agent loop

### Added
- `src/mini_agent/agent.py`: `call_llm` (non-streaming) + `agent_loop` (tool-free pure conversation loop)
- `src/mini_agent/__main__.py`: CLI entry, supporting single task mode and interactive mode
- `src/mini_agent/config.py`: `BASE_URL`/`API_KEY`/`MODEL`/`MAX_ITERATIONS` (hard-coded)
- `src/mini_agent/__init__.py`: package entry
- `tests/test_loop.py`: import chain smoke test
- `docs/tutorials/01-minimal-loop.md`: Lesson 1 teaching document
- `docs/tutorials/README.md`: teaching path index
- `docs/plans/teaching-repo-plan.md`: complete multi-stage teaching repository plan
- `docs/operation/manual.md`: operation manual (v0.01 version)

### Why
- Start from the minimal usable conversation loop and first make clear "what an agent loop is": the messages list, calling the LLM, and deciding the end condition.
- Introduce no tools, permissions, streaming, or concurrency, so the loop concept of the first lesson is as clean as possible.
- `http.client` + `Accept-Encoding: identity` is the choice after hitting a pitfall (the gateway responds abnormally to gzip) and is set from the first version.
## [v0.17] - Failure Model

- Added auditable `ExecutionGeneration`, `ExecutionAttempt`, `FailureEvent`, and reserved `RecoveryAction` state records.
- Added structured executor results, effect classes, canonical argument fingerprints, bounded budgets, and blocked/failed terminal reasons.
- Possible-effect tool calls now reserve generations before handlers; read-only calls may remain concurrent while mixed verification calls are rejected.
- Structured State renders generation, latest failure, causal attempt, budgets, and recovery notices without raw sensitive arguments.

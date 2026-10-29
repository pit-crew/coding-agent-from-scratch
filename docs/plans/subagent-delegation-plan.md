# Stage 10: Controlled Subagent Delegation Implementation Plan

> Status: `v0.34`, `v0.35`, `v0.36`, `v0.37`, `v0.38`, and `v0.39` are implemented and kept
> Suggested version range: `v0.34`–`v0.39`
> Capability prerequisites: Stage 7 structured planning (`v0.22`–`v0.25`), Stage 8 task and process boundaries (`v0.26`–`v0.29`), and Stage 9 safe recovery and durable tool boundaries (`v0.30`–`v0.32`)
> Related plans: `adaptive-planning-plan.md`, `process-management-plan.md`, `session-persistence-resume-plan.md`

`v0.33 Crash Recovery` is not a hard prerequisite for read-only Subagents. The subagents of `v0.34`–`v0.38` do not change files, run shell, start or control processes, or call other subagents; if the parent process crashes while a subagent runs, the worst result is lost uncommitted investigation results and one extra model cost, not repeated workspace side effects. Only when `v0.39` starts to persist the delegation lifecycle must it align with the incomplete invocation, recovery classification, and user handoff semantics of `v0.33`. If Stage 9 finishes `v0.33` first as planned, Stage 10 reuses its boundaries directly; if they move forward in parallel, `v0.39` follows the final protocol of `v0.33` before merging.

## 1. Goal and Positioning

Before Stage 10, investigation, judgment, changes, and verification in `mini_agent` are all carried by the same model context. `v0.34` added a synchronous read-only subagent, `v0.35` unified the parent and child control loop, and `v0.36` narrowed provider/model selection down to frozen per-instance bindings.

The question Stage 10 answers is: **how can cognitive investigation be split across several controlled subagents while the parent Agent keeps exclusive execution rights, permission boundaries, the main plan, and the completion decision?**

One-sentence goal: **extend the single-Agent Runtime into an execution tree with parent-child relations, capability boundaries, budgets, and result contracts; delegate cognitive work without spreading out ownership of workspace changes.**

Target flow:

```text
User task
   ↓
Parent Agent: owns the main Plan, PermissionGate, execution, and completion decision
   ├── delegate investigation A ──→ read-only Subagent A ──→ structured result A ──┐
   ├── delegate investigation B ──→ read-only Subagent B ──→ structured result B ──┼→ Parent Agent synthesizes
   └── delegate review C ──→ read-only Subagent C ──→ structured result C ──┘       ↓
                                                        Parent Agent changes
                                                            ↓
                                                        Independent verification
                                                            ↓
                                                        Reply to user
```

The six versions solve, in order, the minimal delegation contract, the unified run loop, multiple providers, lifecycle and budget, bounded parallelism, and auditable durable delivery. The implemented behavior of `v0.34` is kept, with no rollback required; the lifecycle, parallelism, and persistence of the original plan move to `v0.37`, `v0.38`, and `v0.39` respectively. These are this plan's later version arrangements; other roadmaps and navigation are synced when the matching versions are implemented.

Two core principles:

1. The Parent Agent and Subagents share the same canonical Agent Runtime / Loop implementation, that is, the single maintained `LLM → Tool → Observation` control loop. Their differences are expressed through Context, State, Tool View, Model, Budget, Permission, and Completion Policy configuration; instance isolation does not mean copying the loop code.
2. Support a multi-provider usage style like the opencoder the user described: configure several model service providers, and parent and child can choose different providers/models; protocol differences are handled by adapters, and no new Agent Loop is created per provider. This plan turns that into the capability contract below and does not aim to copy all features of any external product.

## 2. Scope and Non-Goals

### 2.1 Scope of this stage

- The parent Agent creates a clearly scoped investigation task through the explicit `delegate_task` tool.
- A subagent has its own State, Context, loop run state, and prompt, but from `v0.35` it uses the same loop implementation as the parent Agent; it receives only project instructions, the delegation contract, and facts explicitly selected by the parent Agent.
- `v0.36` provides multi-provider configuration, explicit model binding, and unified message adaptation; parent and child models in the same parent task can come from different services.
- Tool definitions are not copied; immutable tool definitions are shared, and a read-only `FilteredToolRegistryView` exposes an explicitly allowed capability subset.
- Define validatable, size-limited `DelegatedTask`, `SubagentResult`, `Finding`, `EvidenceRef`, and `UsageRecord`.
- Set up per-subagent budgets and a parent-task aggregate budget, limiting rounds, model calls, tool calls, tokens, result size, wall-clock time, total subagents, and concurrency.
- Separate execution results from result delivery: a subagent first produces `result_ready`, and only after the result is in the parent State and the matching parent Context is it `committed`.
- `v0.38` supports bounded parallelism of several read-only subagents; actual completion can be out of order, but parent tool results are still committed in model call order.
- `v0.39` connects delegation state, result summaries, Trace, and session recovery, and aligns with the incomplete invocation classification of Crash Recovery.

### 2.2 Not in this stage

- Subagents are not allowed to write files, run shell, start/observe/control parent task processes, write stdin, create checkpoints, or run recovery or verification.
- Subagents are not allowed to change the parent Plan, advance parent steps, create parent FailureEvents, change the generation, approve permissions, release terminal states, or decide parent task completion.
- Subagents are not allowed to delegate further; the maximum depth in Stage 10 is fixed at `1`.
- The parent Agent's full system prompt, full history, PermissionGate, or runtime `once` / `always` authorizations are not copied to subagents.
- No parallel changes by several subagents, worktree isolation, change ownership, merging, conflict resolution, cross-agent rollback, or distributed transactions.
- No cross-host workers, resident agent pools, message buses, cloud task queues, or unattended background scheduling.
- "Role discussion", "voting", or majority opinion are not treated as proof of correctness; the parent Agent must synthesize and verify on its own.
- The core runtime adds no third-party dependencies; threads, timing, cancellation, serialization, and concurrency control keep using the standard library.

## 3. Architecture Decisions to Freeze First

### D1: `v0.33` is a protocol dependency of durable delegation, not a feature gate for read-only delegation

The subagents of `v0.34`–`v0.38` have only repeatable cognitive investigation capabilities. After an abnormal parent process interruption, a running subagent is not recovered from memory, and its result is not claimed as received; investigating again adds cost but does not repeat workspace side effects. So these versions can build on `v0.31` Safe Resume and `v0.32` Durable Tool Boundaries.

`v0.39` must handle the window where "the subagent has produced a result but the parent Context has not committed it yet", and recognize three facts: running, result pending delivery, and already committed. At that point, either `v0.33` is finished first, or the merge explicitly adopts its crash record, issue, decision, and incomplete invocation classification; no separate recovery semantics may be invented.

### D2: The parent Agent exclusively owns execution and final authority

The parent Agent is the only party that faces the user, holds the main Plan, requests side-effect permissions, changes the workspace, runs authoritative verification, and decides whether the task is complete. Subagents only provide investigation findings and source evidence.

```text
Delegation = spread cognitive work
Execution ownership = concentrated in the parent Agent
```

A subagent's success cannot automatically advance the parent plan. The parent Agent must read the result, judge its relevance, and explicitly update steps through the existing plan tools. A subagent failure also does not automatically produce a parent FailureEvent; only when real parent task execution or verification fails are facts recorded through the existing Failure Model and Repair Loop.

### D3: Share the canonical Runtime / Loop, isolate mutable instances, share immutable tool definitions

Parent and child must call the same `AgentRuntime.run()` control loop. They must not dispatch to two loops through `loop_impl`, and `SubagentRunner` must not orchestrate LLM requests, tool execution, and observation feedback on its own. Sharing class names, HTTP helpers, or protocol parsing functions is not the same as sharing the loop. The transitional implementation of `v0.34` is converged by `v0.35`; later capabilities can only extend that implementation.

Each subagent must have its own:

- `AgentState`
- `ContextManager`
- runtime notices, round counter, and stall counter
- delegation budget counters and cancellation signal
- subagent-specific system prompt

Tool names, schemas, descriptions, and stateless handler definitions do not need to be copied. A read-only filtered view on `ToolRegistry` is suggested:

```python
subagent_registry = registry.filtered_for_subagent(
    allowed={"calculate", "read_file", "list_dir", "grep"},
)
```

The filtered view cannot register, replace, or change underlying Tools, and cannot expose handlers bound to the parent State, ProcessManager, CheckpointStore, or RecoveryRuntime. If the existing `Tool` is still a mutable object, the view can only return immutable schema snapshots and resolve execution to frozen allowed entries; it cannot hand the underlying mutable mapping directly to the child runtime.

### D4: Delegable capabilities must be declared explicitly and cannot be inferred from `effect_class=none`

`effect_class` describes whether a tool may produce execution side effects, not whether a tool can be handed to a subagent. Plan control tools and process observation tools may be `none`, but they touch parent task state or resources, so they cannot automatically enter the subagent allowlist.

Tool definitions add separate capability metadata, or a central policy keeps an explicit set, for example:

```text
delegation_capability: unavailable | readonly_workspace | pure_compute
```

The first version allows only:

- `calculate`
- `read_file`
- `list_dir`
- `grep`

Even if the parent model requests other tools in the contract, the Runtime only takes the intersection of the requested set and the system allowlist; empty sets, unknown tools, or over-scope requests are refused before the subagent is created. Neither project instructions nor the parent plan can relax this policy.

### D5: Subagents use a dedicated identity and minimal context, without copying the parent Context

The subagent system prompt states its duty explicitly: investigate the delegated question, collect evidence, and report according to the contract; it is forbidden to change things, delegate further, change the parent plan, decide parent task completion, or claim authoritative verification.

The child context consists of:

```text
Subagent Identity & Rules
+ freshly rediscovered Project Instructions
+ Delegation Contract
+ Selected Parent Facts
+ the subagent's own Structured State
+ the subagent's own Recent Messages
```

`Selected Parent Facts` can only contain task facts explicitly provided by the parent Agent that pass size and sensitive information checks; the full history, tool outputs, runtime authorizations, hidden prompts, or other subagent contexts are not copied by default. Project instructions are still protected content; tool returns and material provided by the parent Agent are untrusted data and cannot override system rules.

### D6: The Task / Result Contract is a formal protocol from `v0.34`

`delegate_task` does not accept an ambiguous free-text string as its whole meaning. The model provides the goal, scope, constraints, expected findings, and budget request; the Runtime assigns IDs, trims the budget, and freezes the final contract.

A subagent result must pass schema validation before entering `result_ready`. The result contains an explicit outcome, a summary, structured findings, evidence, limitations, and actual usage. Missing fields, out-of-bounds paths, dangling evidence, oversized results, or illegal states are not treated as successful results; within the remaining budget the Runtime can give the subagent one protected chance to correct the format, after which it returns a definite failure result.

### D7: Subagent evidence can support investigation conclusions but is not authoritative completion evidence for the parent task

A subagent can provide evidence, such as the file location of a definition, the behavior covered by a test, or one read-only tool observation. This evidence goes into `SubagentResult.findings[*].evidence` and helps the parent Agent check conclusions.

```text
Subagent evidence
        ≠
Parent authoritative completion evidence
```

Subagent evidence is not written into the parent `verification_evidence` and cannot meet the post-change completion conditions. In particular, a subagent's text claiming "tests passed" is not parent task verification; Stage 10 subagents do not get `run_shell` at all. The parent Agent must establish authoritative facts through its own read-only rechecks or independent verification.

### D8: Budgets are split into per-subagent budgets and parent-task aggregate budgets

A per-subagent budget contains at least:

```text
max_rounds
max_llm_calls
max_tool_calls
max_tokens
max_result_bytes
timeout_seconds
```

A parent-task aggregate budget contains at least:

```text
max_subagents
max_concurrency
max_total_llm_calls
max_total_tool_calls
max_total_tokens
```

All budgets must be authoritative Runtime counts; the model can only request a child budget not above the remaining quota. Quotas are reserved atomically before parallel starts, settled by definite actual usage after the end, and unused reservations released; failures, timeouts, and cancellations also count the calls and tokens already used. The aggregate budget must not be reset by repeated failed delegations, session recovery, or splitting the same task.

Token counts prefer usage returned by the provider; when the provider does not provide it, estimated usage is recorded using the existing conservative estimate of `ContextManager`, with the source marked in the result. The remaining quota is checked before each LLM request and settled after the response completes; if the provider supports a reliable output limit, the remaining quota is also sent down, but whether the provider respects the limit cannot be the only protection.

### D9: Execution outcome and delivery status are two orthogonal dimensions

Delegation delivery lifecycle:

```text
created → running → result_ready → committed
              │            ↑
              └─ any execution outcome forms a bounded result ─┘
              └─ no durable result after a crash → interrupted (audit only)
```

A result's execution outcome is expressed separately:

```text
completed | failed | timed_out | cancelled | budget_exhausted
```

So failures, timeouts, cancellations, and budget exhaustion must also produce a complete, committable `SubagentResult`, instead of stopping outside the parent Context:

- `result_ready`: the subagent's complete result has been produced and passed local validation, but has not yet reliably entered the parent State / Context.
- `committed`: the result, the parent DelegationRecord, and the matching `role=tool` message have been committed together, and the parent Agent can continue requesting the LLM.
- `interrupted`: the investigation in the old process has no durable result; Crash Recovery gives the parent tool call an uncertain result, and the delegation record does not forge a result ID or actual usage.

`committed` does not mean the outcome is `completed`. The parent Agent must be able to receive and handle definite failure results.

### D10: Each parent tool call still matches exactly one ordered `role=tool` result

One `delegate_task` is one tool call of the parent Agent. No matter how many rounds a subagent runs internally or how many read-only tools it calls, the parent Context receives only one bounded structured result; subagent internal messages must not be spliced directly into the parent history.

Several delegations issued in the same parent assistant turn can run in parallel, but the results must follow the existing tool protocol: each call has exactly one result, all results enter the parent Context in model order, and only after the whole turn is committed is the next parent LLM request allowed. A failure of one subagent cannot lose or prematurely commit the results of other calls.

### D11: Delegation errors are closed at the subagent boundary and do not break through the parent Agent Loop

Subagent LLM errors, schema errors, read-only handler exceptions, timeouts, cancellations, and budget exhaustion are converted into a `SubagentResult` by `SubagentRunner`. The parent `ToolExecutor` still converts exceptions outside the `delegate_task` handler boundary into matching tool error results.

The core parent Agent Loop adds no fallback for top-level LLM or CLI exceptions. Converting subagent exceptions is an explicit duty of the child runtime inside the tool handler and does not change the project's existing exception boundary.

### D12: Stage 10 fixes single-level delegation to prevent recursion and budget tree explosion

The subagent Registry does not contain `delegate_task`, the contract's `depth` is fixed at `1` by the Runtime, and the model cannot raise it. Deeper delegation requests appearing in recovery files, the parent Context, or project instructions are all refused. Multi-level agents can only be evaluated after recursive budget inheritance, permission decay, Trace display, and termination propagation are defined separately in the future.

## 4. Runtime and Call Protocol

### 4.1 One loop and a reentrant Runtime

`v0.34` actually had three paths: `agent_loop()` called `_legacy_agent_loop()` through `loop_impl`; `AgentRuntime._run_common()` had a generic loop; `SubagentRunner.run()` looped on its own and used only `runtime.invoke()` to request the model. This is architectural debt of the implemented baseline and cannot be marked as the canonical loop being complete. `v0.35` unifies the three paths on the premise of keeping the full semantics of the parent loop; it cannot replace them with a simplified generic loop and lose the persistence, process, Plan, or completion reminder boundaries.

Suggested boundary:

```python
class AgentRuntime:
    def __init__(self, context, state, tool_view, model, budget,
                 permission, completion_policy, output, integrations): ...
    def run(self) -> RuntimeResult: ...

class SubagentRunner:
    def run(self, task: DelegatedTask, cancel_event) -> SubagentResult: ...
```

The above sketches dependency boundaries and does not require copying the constructor signature. Parent and child each assemble separate instances and call the same `run()`:

| Configuration dimension | Parent Agent | Subagent |
|---|---|---|
| Context | User task, main history, project instructions | Delegation contract, selected facts, own history and identity prompt |
| State | Main task, Plan, generation, verification | Own investigation state and observation records |
| Tool View | Tools approved for the current parent task | Frozen four-tool allowlist and scope gate |
| Model | Parent model binding resolved from local configuration | Child model binding resolved from local configuration, can be a different provider |
| Budget | Parent run limits and the delegation aggregate ledger | Frozen child quota, rounds, and format correction usage |
| Permission | Parent PermissionGate and user authorization interaction | Separate fixed allowlist, not inheriting parent authorizations |
| Completion Policy | Plan, process, verification, and progress marker conditions | Result Contract validation and one format correction |

The unified loop has sole control of requests, adding the assistant to history, whole-turn admission, tool execution, ordered result commits, the next round, and termination. Policies return admission decisions, completion decisions, or protected reminders; they cannot request the LLM, run tools, or start retry loops on their own. When the budget is insufficient or tool calls appear in the correction phase, the unified loop likewise fills in a refusal result for each admitted call before ending.

The parent instance binds existing services such as Plan/Repair/Process/Session through integrations, and the child instance binds no parent resources; the output adapter decides whether to stream. Without persistence, in-memory commits are used; a parent instance with `/save` on still commits `handler_admitted` before the handler and atomically commits State, the tool result, and the boundary in order. A commit failure stops immediately and must not continue to the handler or request the model. The compatibility entry `agent_loop()` can stay as an assembly and return-value conversion layer but does not keep a separate control loop.

`SubagentRunner` is only responsible for building instances, calling `run()`, and converting child exceptions into bounded results at the tool handler boundary; parent top-level LLM exceptions keep propagating up. Separate ContextManagers, counters, and connections belong to instances; the shared implementation must not become shared mutable global state.

### 4.2 Delegation call path

```text
Parent model generates delegate_task
  → parent loop validates the same-turn protocol
  → ToolExecutor validates schema / phase / terminal state
  → DelegationManager atomically reserves the parent aggregate budget and creates the DelegationRecord
  → parent durable boundary commits handler_admitted (when /save is on)
  → SubagentRunner builds the child State / Context / RegistryView / Prompt
  → the child instance enters the same AgentRuntime.run() and calls its Model and read-only tools
  → validate and produce SubagentResult
  → DelegationRecord = result_ready
  → parent State + role=tool + boundary committed atomically
  → DelegationRecord = committed
  → the parent loop continues after the whole turn completes
```

In `v0.34`–`v0.38`, before Durable Delegation is implemented, `result_ready` is mainly an in-memory fact; with `/save` on, it is still protected by the existing durable tool boundary of the parent `delegate_task`, and an active handler cannot become a clean safe point. Only `v0.39` commits to recognizing and coordinating child result delivery state across processes.

### 4.3 Subagent completion protocol

Subagents still follow the core protocol that "a task can only end with no `tool_calls`" and that every tool call must have a matching `role=tool` result. The final plain text must meet the Subagent Result JSON schema; an illegal result is not silently treated as a summary.

The final content is suggested to be validated through the child Runtime's completion policy: on the first illegal result, inject one protected format reminder and continue; on a second illegal result or when the budget is insufficient, produce a Runtime result with `outcome=failed`. A special termination tool that aborts immediately after the call and lacks `role=tool` feedback must not be added.

### 4.4 Multiple providers and model binding (`v0.36`)

A provider is the configuration identity of a model service, a protocol is its request and response format, and a model is the model identifier in that service. Several providers can share the same protocol adapter or use different protocols; only making the global `BASE_URL` a configurable string does not count as completing multi-provider support.

Suggested boundaries:

- `ProviderConfig`: local provider ID, protocol, endpoint, credentials, and timeout configuration.
- `ModelProfile`: local alias, provider ID, model ID, context window, output limit, and capability declarations.
- `ModelBinding`: the profile and client binding resolved and frozen before Runtime creation; module-level configuration is not rewritten during requests.
- `ProviderAdapter`: encodes unified messages and Tool View schemas into requests, and normalizes responses into assistant content, stable tool-call IDs, names, JSON arguments, the finish reason, and usage. Tool result feedback must keep the call ID mapping.

Local configuration provides the provider/profile mapping, the parent default profile, the child default profile, and the allowlist of child-selectable profiles. The selection order is: an approved profile explicitly requested in the contract → the child default profile → the parent profile. Unknown or unauthorized profiles must be refused before the request, with no silent fallback; the parent model can only provide profile aliases, not endpoints, credentials, or custom auth headers. Parent and child use the same model by default, and the old `BASE_URL` / `API_KEY` / `MODEL` triple maps to a default profile so that the original call entry keeps working.

The first adaptation scope is explicitly the OpenAI-compatible Chat Completions and Anthropic Messages protocols, with support for several separate endpoints/providers on the same protocol. Official SDKs are not required; all LLM HTTP requests keep using the standard library `http.client` and explicitly set `Accept-Encoding: identity`. Real endpoints, API keys, and model IDs are stored only in the local `config_local.py`, and committed configuration examples contain only placeholders. Adapters handle auth headers, system messages, tool calls/results, streaming chunks, and error formats; internally the unified `role=tool` protocol is still used and converted to the provider's required format on send.

Capability validation is done before sending requests: the model must support tool calls and the required context/output limits. Report JSON can keep using prompt and Completion Policy validation, without requiring native provider JSON schema. Unsupported protocols, truncated tool arguments, or incomplete streams cannot be handed to the executor as executable calls; child errors are closed in the Runner, and parent errors propagate through the existing top-level exception boundary. Adapters must not run tools, decide completion, change State, or perform hidden retries; this stage has no automatic cross-provider fallback, to avoid implicitly changing the data recipient and double charging.

Context trimming reads the bound model's window; helper LLM requests such as summaries must also bind a model explicitly and count toward the matching budget, and cannot fall back to the global model or become free calls. Usage keeps the provider/estimated/mixed source; when usage is missing from a stream it is estimated conservatively, and on exceptions the sent request and uncertain usage are recorded. Cross-provider token sums are used for resource limits and are not the same as monetary cost; this stage does not commit to price tables or cost settlement. Under concurrency only immutable configuration and adapter definitions are shared, and each request has its own connection, stream buffer, and counters.

Persistence and Trace record only credential-free source summaries such as the profile alias and configuration fingerprint, and do not write the real endpoint, model ID, auth headers, or API key. Recovery resolves bindings again from local configuration; missing or changed configuration is reported explicitly, existing results are not requested again, and no other provider is switched to automatically.

## 5. Data Model

### 5.1 Delegated task contract

```text
DelegatedTask
- delegation_id                 # Assigned by the Runtime, unique within the parent task
- subagent_id                   # Assigned by the Runtime, not mixed with task_id
- parent_task_id
- parent_generation_id          # Parent generation at creation, only a source reference
- goal                          # A single, answerable investigation goal
- scope                         # Workspace-relative paths or topic boundaries allowed for investigation
- constraints                   # Bounded list of strings
- expected_findings             # List of questions the parent Agent wants answered
- requested_tools               # Model request; the Runtime intersects it with the allowlist
- allowed_tools                 # Actual capabilities after the Runtime freezes them
- selected_parent_facts         # Bounded, redacted, explicitly selected parent facts
- budget                        # Per-subagent budget approved by the Runtime
- model_profile?                # From v0.36: requested local alias, checked by the Runtime against the allowlist
- model_binding_ref?            # From v0.36: frozen credential-free binding summary, without real configuration
- depth = 1
- created_at
```

Constraints:

- `goal` must be non-empty and express only one main investigation goal.
- `scope` is normalized to the current workspace; `..` escapes, out-of-bounds symlinks, and arbitrary absolute paths are forbidden.
- `constraints`, `expected_findings`, parent facts, the number of tools, and the length of each item all have limits.
- `allowed_tools` can only be computed by the Runtime and cannot be overridden directly from persisted input.
- The contract is immutable after creation; cancellation, results, and delivery state are written to separate records.

### 5.2 Structured evidence and findings

```text
EvidenceRef
- evidence_id
- kind: file_location | tool_observation
- claim
- path?                         # workspace-relative path
- line?                         # positive integer; only marks the observed position, does not guarantee unchanged content
- tool?                         # only subagent allowlist tools
- observation_hash?             # stable digest of a bounded result, without copying large outputs

Finding
- finding_id
- claim
- evidence_ids: list[evidence_id]
- confidence: observed | inferred
- caveat?
```

`file_location` checks at result creation that the path is within scope and the line number is valid, but the parent Agent should still reread when needed later, because the workspace may change. `inferred` must carry a caveat or supporting evidence and cannot pose as a direct observation. Evidence text and hashes are not PermissionGate or verification facts.

### 5.3 Subagent result contract

```text
SubagentResult
- result_id
- delegation_id
- subagent_id
- outcome: completed | failed | timed_out | cancelled | budget_exhausted
- summary
- findings: list[Finding]
- evidence: list[EvidenceRef]
- limitations: list[string]
- usage: UsageRecord
- started_at, finished_at
- error_kind?, error_detail?
```

```text
UsageRecord
- rounds
- llm_calls
- tool_calls
- input_tokens
- output_tokens
- token_accounting: provider | estimated | mixed
- model_profile?, binding_fingerprint?  # From v0.36: usage source, without credentials or the real model ID
- elapsed_ms
- result_bytes
```

The result limit is checked in UTF-8 bytes. When over the limit, the subagent is first asked to regenerate a shorter result within the remaining budget; if it is still over, `failed/result_too_large` is returned, and the JSON cannot be truncated in the middle. Error details must be bounded and must not contain API keys, the full system prompt, or unselected parent history.

### 5.4 Delegation records in the parent task

```text
DelegationRecord
- delegation_id, subagent_id, parent_task_id, parent_generation_id
- task_contract_hash
- delivery_status: created | running | result_ready | committed | interrupted
- parent_attempt_id? (parent-side call reference, for Trace)
- outcome: pending | completed | failed | timed_out | cancelled | budget_exhausted
- result_id?
- result_hash?
- usage
- created_at, started_at?, result_ready_at?, committed_at?
- cancellation_reason?
- diagnostic_reason?
```

The parent State saves a bounded summary of the contract, a result summary, and references, not the full child Context. The full result enters the Context through the matching parent `role=tool` content and is bound by existing history trimming and size limits; Trace uses the structured summaries in State and does not parse natural-language messages in reverse.

Invariants:

- `delegation_id`, `subagent_id`, and `result_id` are unique within the parent task.
- Delivery status only moves forward; `committed` must have exactly one result.
- Once the outcome changes from `pending` to a final value, it cannot be rewritten.
- `result_ready` must reference a result hash that passed schema validation.
- `committed` must agree with the matching tool call/result in the parent Context, the model order, and the durable commit.
- Every execution outcome must form a result; failure paths cannot lack a parent tool result.
- The number of active delegations, concurrency, and actual usage cannot exceed the parent aggregate budget.

## 6. State, Context, and Ownership

### 6.1 Field ownership

| Information | Writer | Can the parent Agent override it directly |
|---|---|---|
| Delegation goal, scope, constraints, expected findings | Provided by the parent model via `delegate_task`, validated by the Runtime | Cannot change a frozen contract; can only create a new delegation |
| IDs, actual allowed tools, budget reservations, delivery status | `DelegationManager` | No |
| Child tool execution facts and child history | Child `ToolExecutor` / `ContextManager` | No, not merged into the parent State |
| findings, evidence, limitations | Provided by the child model, validated by the child Runtime | The parent can evaluate or recheck, but cannot tamper with the original result |
| Parent Plan progress, generation, verification | Parent Runtime and existing tools | Subagents have no write entry |
| User approvals and PermissionGate | CLI / parent PermissionGate | Subagents have no inheritance or write entry |
| Result commits and protocol mapping | Parent Runtime / SessionBoundary | The model cannot forge them |

### 6.2 Parent Structured State

The parent Context renders only a bounded current delegation view:

```text
delegations
- aggregate budget used / remaining
- active delegation IDs and goals
- recently committed outcomes and short summaries
- cancellation or delivery diagnostic
```

Full findings and evidence are not rendered again; they already exist in the matching tool result. After compaction, bounded delegation summaries and result references that still affect the main task must be kept, and uncommitted results cannot be described as already received by the parent Agent.

### 6.3 Child Structured State

The child State records only its own goal, read-only tool history, budget, format correction reminders, and terminal state. It does not copy the parent PlanRevision, FailureEvent, RecoveryAction, VerificationEvidence, ProcessRecord, or session write rights. A file read by a subagent produces an observation and does not advance the parent generation.

## 7. Permissions, Safety, and Task Boundaries

- `delegate_task` itself does not change the workspace, but it uses model resources and starts a nested runtime. It keeps the workspace meaning of `effect_class=none`, while being managed through a separate `delegation_capability`, the aggregate budget, and lifecycle rules; it cannot be inferred to be "free" or retryable without limit.
- Child read-only tools still pass through the scope gate; the first version can use a fixed refusing PermissionGate or a narrower CapabilityGate, but cannot reuse the parent session's dynamic approvals.
- `read_file`, `list_dir`, and `grep` refuse out-of-scope paths before the handler; the refusal is still fed back to the child model and counts toward the tool budget.
- Subagents cannot read `config_local.py`, session private directories, API keys, or paths explicitly forbidden by project rules; the stricter of the existing file permission rules and the project instructions applies.
- When the parent task is in `awaiting_approval`, `verification_required`, a terminal state, or Crash Recovery that allows only specific investigation actions, whether `delegate_task` is allowed must be decided by an explicit phase matrix and cannot be allowed by default just because it is read-only.
- The first version is recommended to allow: investigation delegation in `direct/executing + idle`, and read-only delegation in `exploring + idle`; `diagnosis_required` is allowed only when the contract is explicitly diagnostic and does not bypass the active failure. `verification_required`, `awaiting_approval`, and terminal states are refused.
- Text and file content returned by subagents are untrusted data; the parent prompt states explicitly that instructions in them must not be treated as system or project rules.
- `/new`, `/reset`, EOF, `exit`, and abnormal exit must send cancellation to the active subagents of the current parent task and wait within bounds. If they have not finished, keep the specific IDs and reasons; a clean handoff cannot be claimed.

## 8. Version Slices

### 8.1 `v0.34` Minimal Delegation (implemented)

Goal: the parent Agent can synchronously hand a clear read-only investigation task to a single, single-level, isolated subagent and receive a structured result that passes formal contract validation.

Main work:

1. Introduced an instantiable `AgentRuntime` protocol shell and model call adaptation helper, keeping parent behavior and child state isolation; the parent legacy loop, the generic loop, and the child loop inside the Runner have not converged yet. Acceptance of the shared canonical loop moves to `v0.35` and is not claimed retroactively as done in this version.
2. Define `DelegatedTask`, `SubagentResult`, `Finding`, `EvidenceRef`, and `UsageRecord`, with strict length, count, enum, and reference validation.
3. Add explicit delegation capability to tool definitions and implement the read-only `FilteredToolRegistryView`; the first version exposes only calculate, read_file, list_dir, and grep.
4. Add `DelegationManager`, `SubagentRunner`, and the state-bound `delegate_task` tool; only one synchronous subagent at a time is allowed, with depth fixed at 1.
5. Add a subagent-specific system prompt that injects the current project instructions, the frozen contract, and bounded selected parent facts, without copying the parent history or authorizations.
6. The child's final plain text must meet the Result Contract; if it is still illegal after one format correction, a definite failure is returned. Each parent delegate call has exactly one bounded tool result.
7. Test that the parent State/Context is not changed by the child, parent tool definitions are not changed by the view, over-scope tools are not visible, evidence references can be validated, and there is no behavior change when simple tasks do not delegate.

Suggested files:

| File | Action | Content |
|---|---|---|
| `src/mini_agent/runtime.py` | New | The landed instance protocol shell and call helper; the single loop converges in v0.35 |
| `src/mini_agent/delegation.py` | New | Contract dataclasses, validation, Manager, and Runner |
| `src/mini_agent/tools/delegation.py` | New | The state-bound `delegate_task` tool |
| `src/mini_agent/tools/base.py` | Change | Delegation capability and the filtered view |
| `src/mini_agent/tools/__init__.py` | Change | Parent Registry registers the delegation tool; the child view forbids recursion |
| `src/mini_agent/prompt.py` | Change | Parent delegation rules and the subagent-specific prompt |
| `src/mini_agent/agent.py` | Change | Reuse the instance Runtime, keeping parent protocol compatibility |
| `tests/test_subagent_v034.py` | New | Contracts, isolation, read-only capabilities, and single delegation E2E |

Acceptance focus: a subagent can answer a cross-file investigation question and provide structured location evidence; it cannot see any write, shell, process, plan, recovery, verification, or delegation tools; its result does not automatically advance the parent Plan or parent verification.

This implementation already supports several synchronously created read-only subagents running in parallel within a fixed concurrency limit; `v0.37` added the parent-task aggregate budget, background cancellation, and lifecycle records, `v0.38` added batch reservation, out-of-order completion, and in-memory result delivery in parent order, and `v0.39` saved validated raw results as bounded `result_ready` and connected schema 3 sessions and v0.33 recovery. `v0.35` converged the single loop, and `v0.36` introduced multiple providers. Existing contract fields and failure results stay compatible; new model binding fields use compatible defaults and do not rewrite historical contract hashes.

Implementation status:

- [x] `v0.34`: single, synchronous, single-level, read-only delegation and the Task / Result Contract.
- [x] `v0.35`: shared canonical Agent Runtime / Loop, with parent/child differences in configuration.
- [x] `v0.36`: multiple providers, protocol adaptation, and separate parent/child model bindings.
- [x] `v0.37`: lifecycle, cancellation, and aggregate budget.
- [x] `v0.38`: bounded parallelism and commits in parent order.
- [x] `v0.39`: durable delegation, Trace, session, and Crash Recovery coordination.

### 8.2 `v0.35` Unified Parent/Child Run Loop

Goal: keep the external behavior of `v0.34`, with parent and child using only one canonical Runtime / Loop.

Main work:

1. First build behavior comparisons for the existing parent and child paths, covering message order, admission refusals, budget exhaustion, format correction, exceptions, completion reminders, and persistence commit failures.
2. Converge the parent loop's full control flow into `AgentRuntime.run()`; extract the instance dependencies and policy interfaces of section 4.1, and forbid policies from writing a separate LLM→Tool→Observation loop internally.
3. Connect the child budget, scope checks, observation collection, and Result Contract to the defined boundaries of the same loop; the Runner only assembles, runs, and converts results and exceptions.
4. Remove the `loop_impl` dual path and the Runner's own loop; keep the `agent_loop()` and `call_llm()` entries and existing test injection methods compatible, but keep no second production control flow.
5. Keep the single synchronous subagent, fixed budget, and four-tool capability; this version introduces no multiple providers, concurrency, or new persistence protocol.

Suggested additions or changes: `runtime.py`, `agent.py`, `delegation.py`, `context.py`, `tests/test_shared_runtime_v035.py`.

Acceptance focus: parent and child both actually enter the same `run()` implementation; parameterized mock LLM/tool tests verify that the same protocol skeleton holds under different configurations, and code review confirms that no second loop remains. Full parent regressions cover Plan/Repair, progress marker, process/stdin, v0.32 commit failures, and v0.33 recovery; child v0.34 contract and isolation tests keep passing. Only sharing HTTP/helpers or switching legacy paths inside the shell cannot pass acceptance.

Implementation record (v0.35): the final interface is `AgentRuntime(*, llm_client, context, executor, policy, max_rounds, output=None, session_boundary=None).run()`, returning a `RuntimeResult` with content, stop reason, rounds, LLM call count, tool call count, and estimated token count. `RuntimePolicy` is only responsible for decisions, refusal results, reminders, and observation formatting; the Runtime exclusively owns LLM requests, appending assistant/tool messages, handler admission, commits in model order, and whole-turn completion. `normalize_tool_calls()` returns `NormalizedToolRound`, assigning a unique `local-error-N` to bad calls and closing the protocol.

Differences from the original suggestion: `output` and `session_boundary` stay optional dependencies; the parent policy connects v0.33's process sync, Plan/Repair gate, progress marker, and terminal semantics to the unified Runtime; the child policy keeps v0.34's fixed budget, scope observation, Result Contract, and one format correction. Pure read-only tools can still run in parallel, but durable admission and result commits are closed uniformly by the Runtime in model order. This version introduces no provider selection, lifecycle/aggregate budget, cancellation, multiple subagents, or new session/State/tool schemas.

### 8.3 `v0.36` Multiple Providers and Model Selection

Goal: through local configuration, let parent and child choose providers/models independently, using the same Runtime and unified tool protocol.

Main work:

1. Implement the ProviderConfig, ModelProfile, ModelBinding, and adapter boundaries of section 4.4; migrate the old triple to a default profile.
2. Implement OpenAI-compatible Chat Completions and Anthropic Messages adaptation, covering streaming/non-streaming responses, tool calls and result mapping, usage, and provider errors.
3. Implement parent default, child default, and contract-selectable profiles with allowlist validation; bindings are frozen before instance creation, and providers cannot be switched through global variables.
4. Connect model windows, output limits, summary requests, and usage to the existing fixed budget; provide unified count inputs for the v0.37 aggregate budget.
5. Unify credential-free source summaries and error redaction, without leaking provider-specific parameters into Runtime control logic.

Suggested additions or changes: `providers/` (standard library implementation), `config.py`, `config_example.py`, `agent.py`, `runtime.py`, `context.py`, `delegation.py`, `tests/test_providers_v036.py`.

Acceptance focus: use a local mock HTTP service to verify configuration isolation of at least two same-protocol providers, and cross-protocol delegation with parent Chat Completions / child Messages; check auth and identity request headers, message conversion, chunked argument reassembly, unique call/result mapping, and usage. Cover missing configuration, unknown model aliases, no tool capability, truncated responses, timeouts, missing usage, and credentials not entering logs/State/session. Default tests do not depend on real API keys or paid requests; old configuration still runs, and switching providers does not change permissions or completion conditions.

Implementation record (v0.36): added `ProviderConfig`, `ModelProfile`, `ModelBindingRef`, `ModelBinding`, and `ProviderCatalog`. The catalog validates configuration and freezes bindings at CLI startup, recovery, and when `DelegationManager` creates subagents; the old `BASE_URL` / `API_KEY` / `MODEL` map to `legacy-default`. Adapters implement the `ProviderResponse`, `ProviderUsage`, and `ProviderAdapter` protocols; the native structures of OpenAI-compatible Chat Completions and Anthropic Messages are both converted in the adapter layer, and the Runtime keeps handling only unified assistant/tool messages.

`ContextManager`'s summary requests explicitly use the current binding and share the `UsageMeter` with ordinary requests; `RuntimeResult` and `UsageRecord` expose input/output tokens and the `provider` / `estimated` / `mixed` source. `delegate_task` accepts only allowlisted `model_profile` aliases, and results and persisted projections keep only the profile, provider, protocol, and fingerprint. The request layer keeps using the standard library `http.client`, separate connections, and `Accept-Encoding: identity`, with no implicit retries or provider fallback.

Differences from the original suggestion: this version keeps `call_llm()` as a compatibility façade and keeps existing patch entries usable; production parent/child Runtimes still enter the same `AgentRuntime.run()` through frozen bindings, while directly injected test LLMs keep using the compatibility path. To keep v0.34/v0.35 contract hashes, `model_profile` and `model_binding_ref` are added metadata fields and do not take part in the historical `contract_hash`. When a restricted execution environment cannot bind local TCP ports, HTTP integration tests skip real listening, but offline configuration, parsing, redaction, and Runtime regressions must still pass.

### 8.4 `v0.37` Lifecycle & Budget

Goal: upgrade one usable delegation into a controlled lifecycle with a task identity, cancellation, and no unbounded resource use.

Main work:

1. Add `DelegationRecord`, the aggregate budget, and atomic state transitions to the parent State; distinguish delivery status from execution outcome.
2. Implement per-subagent rounds, LLM calls, tool calls, tokens, result bytes, and timeout budgets, checking before each boundary and returning an explicit `budget_exhausted`.
3. Implement the parent task's max subagents, total LLM calls, total tool calls, and total tokens budgets; reserve before creation and settle by actual usage after completion.
4. Add standard-library `Event`-driven cooperative cancellation and bounded waits; cancellation cannot kill an in-progress HTTP/socket call, but must stop at the next sync point, and after a timeout conservatively report that it has not finished.
5. Active delegations block parent task `done`, clean save, `/new`, `/reset`, and normal exit, until results are committed or cancellation cleanup completes.
6. Inject delegation summaries and the remaining budget into the parent Structured State; keep them accurate after compaction without copying the full child history.
7. Connect consecutive delegations with the same contract and no new findings to stall detection; new IDs or budget usage by themselves do not count as progress.

Suggested additions or changes: `state.py`, `context.py`, `config.py`, `delegation.py`, `__main__.py`, `tests/test_subagent_lifecycle_v037.py`.

Acceptance focus: timeouts, cancellations, budget exhaustion, illegal results, and LLM exceptions all form a unique result that reaches the parent Context; repeated delegation cannot reset the aggregate budget or create progress by creating new IDs.

### 8.5 `v0.38` Parallel Delegation

Goal: allow several independent read-only investigations to run in parallel while keeping budgets, isolation, and the parent tool protocol deterministic.

Main work:

1. Add a dedicated `DelegationScheduler` and a fixed `max_concurrency`, instead of letting each parent tool-call thread create its own unbounded thread pool.
2. Several `delegate_task` calls in the same parent assistant turn start in parallel after the aggregate budget is atomically reserved; calls that cannot get budget return a definite refusal result before starting the child LLM.
3. Each subagent uses a separate instance of the same Runtime implementation and a frozen ModelBinding; only immutable definitions and a read-only project instructions snapshot are shared, not connections, stream parse buffers, Context, or counters. Parallel acceptance includes child tasks on different providers.
4. Completion order can differ, but the parent State / Context / durable tool results are still committed in model call order; while waiting for earlier calls, later results keep being collected within bounds but are not fed back early.
5. Support partial failure: one subagent failing, timing out, or being cancelled does not cancel the other subagents, unless the parent task as a whole is cancelled or the aggregate budget/safety boundary requires a stop.
6. Aggregate usage is settled thread-safely; reservations and releases do not over-issue token, tool, or concurrency quotas.
7. Parent task termination propagates to all active subagents and reports the subagent IDs that did not finish within the deadline.

Suggested additions or changes: `delegation.py`, `agent.py`, `state.py`, `config.py`, `tests/test_parallel_subagents_v038.py`.

Acceptance focus: at least three investigation tasks finish out of order, and the parent model receives three unique results in the original call order; partial failures do not lose successful results; measured active counts and total usage never exceed configured limits.

### 8.6 `v0.39` Durable Delegation

Goal: make delegation creation, child result production, and parent result commits auditable facts that can be coordinated on recovery, connected to Trace and sessions.

Main work:

1. Persist bounded DelegationRecords, frozen contract summaries, usage, result hashes, and `created/running/result_ready/committed` states; do not save the full child Context, hidden prompts, or unselected parent history.
2. After a child result passes validation, commit `result_ready` first; then commit the result, the parent State, and the matching `role=tool` together as `committed`, keeping the model order of the parent round.
3. Include active or undelivered delegations in safe-point checks. `running` cannot be saved as clean; `result_ready` can be committed through coordination only when the exact parent tool result can be rebuilt from the durable result.
4. Align the recovery classification with `v0.33`: a read-only child task that was running with no result can be marked as a lost investigation, without forging success; rerunning requires re-settling cost and the current phase/budget. When a durable `result_ready` exists, commit the original result first, without calling the child LLM again.
5. On recovery, recompute allowed tools and current project instructions; an old contract cannot relax a new policy. If the scope, project instructions, or workspace identity changed, keep the old result for audit, but the parent Agent decides whether to recheck.
6. Trace shows read-only the parent-child relation, contract summary, lifecycle, outcome, usage, and result commit references; it does not load the full child history, call the LLM, or replay delegations.
7. Inject crashes at `running → result_ready`, `result_ready → committed`, multi-result commits in the same turn, and before and after session replacement, verifying no repeated delivery, missing results, or broken parent tool-call protocol.

Suggested additions or changes: `session.py`, `resume.py`, `state.py`, `context.py`, `trace.py`, `delegation.py`, `tests/test_durable_delegation_v039.py`.

Acceptance focus: when a subagent has already formed a result but the parent process crashes before the Context commit, recovery can recognize and commit the same result; a crash while running does not forge a result or automatically re-charge an investigation; each parent tool call ends with at most one committed result.

## 9. Combination with Existing State Machines

### 9.1 Planning / Repair / Crash Recovery admission matrix

| Parent state | New delegation allowed | Notes |
|---|---|---|
| `direct` / `executing` + `idle` | Allowed | Ordinary investigation or review; cannot replace parent execution and verification |
| `exploring` + `idle` | Allowed | Read-only investigation fits the Explore boundary; `commit_plan` must still own its parent tool turn exclusively |
| `awaiting_approval` | Refused | The model should wait for the user's decision and cannot keep starting work |
| `diagnosis_required` | Conditionally allowed | The contract must be read-only diagnosis; cannot advance the old Plan or call recover |
| `verification_required` | Refused | The next parent tool turn can still only be the existing single independent verification |
| Crash Recovery with unresolved issues | Conditionally allowed | Only when existing recovery rules allow read-only investigation and the delegation result can be linked to the current issue; user decisions cannot be produced by subagents |
| `blocked` / `failed` / `done` | Refused | Subagents cannot release or override parent terminal states |

Both whole-turn admission and the per-call executor must check these boundaries. If the same turn mixes in plan, recovery, or verification calls that must be exclusive, the related calls of the whole turn are refused by the existing stricter rules; delegation cannot become a wrapper that bypasses exclusivity.

### 9.2 Completion decision

New conditions under which the parent task cannot complete:

- There are delegations in `created`, `running`, or `result_ready` that are not committed.
- Some parent `delegate_task` has no matching `role=tool` result yet.
- Aggregate usage or delivery status is not settled yet.
- After task changes, the current-generation authoritative verification produced by the parent Runtime is missing.

All subagent outcomes being `completed` does not automatically meet the parent Plan success criteria. Conversely, a subagent failure does not necessarily block parent task completion: the parent Agent can investigate on its own or use other evidence to complete the goal, but must first receive and handle that committed failure result.

### 9.3 Stall detection

A new delegation can be considered as candidate progress only when it brings a valid finding/evidence hash that appears for the first time in the current progress epoch, or when the parent Agent makes real plan/state progress because of the result. These do not count as progress:

- Only changing the delegation/subagent/result ID.
- Repeating the same contract and getting the same findings.
- Failed, refused, timed-out, or finding-less results.
- Only using budget or adding Trace records.

Stall rules must not treat different but valueless random summary text as new facts; hashes are based on normalized structured findings/evidence, not the full free text.

## 10. Tests and Acceptance

### 10.1 Unit and integration tests

- Parent and child enter the same canonical `AgentRuntime.run()` from different configurations; no legacy/child dual loop or provider-specific loop exists, and common protocol tests cover both kinds of instances.
- Multi-provider same-protocol multi-endpoint, cross-protocol parent/child selection, old configuration compatibility, profile allowlists, capability validation, separate connections, streaming tool arguments, and usage normalization all pass local HTTP tests.
- Helper summary requests use an explicit model binding and count toward the budget; protocol adaptation does no hidden retries or cross-provider fallback, and configuration and errors do not leak credentials.
- The Task Contract refuses empty goals, out-of-bounds scopes, unknown tools, oversize fields, illegal budgets, and depth other than 1.
- The Result Contract refuses duplicate/dangling evidence IDs, out-of-bounds paths, illegal line numbers, unknown outcomes, oversize JSON, and usage going backward.
- `FilteredToolRegistryView` cannot register or change underlying tools; after parent tools update, the view's behavior is explicit according to the frozen policy, and subagents never see state-bound or side-effect tools.
- Plan control and process observation tools with `effect_class=none` are not let through by mistake because of their side-effect classification.
- The child State, Context, stall counter, and history are fully isolated; subagents cannot change the parent Plan, generation, verification, PermissionGate, or terminal state.
- The child prompt contains only project instructions, the contract, and selected facts, not the parent's full history, API keys, runtime authorizations, or other child Contexts.
- Each child tool call has a matching result; it can only end with no tool_calls and a result passing the Result Contract.
- LLM exceptions, tool exceptions, format errors, timeouts, cancellations, and all kinds of budget exhaustion are converted into a unique bounded result.
- Per-subagent and aggregate budgets are reserved and settled atomically under concurrency; recovery, failures, and repeated delegations cannot reset used quotas.
- When provider usage is missing, it is marked estimated; the estimate path can also stop an over-budget loop before the next request.
- When several subagents finish out of order, parent `role=tool` results keep model order; each call has exactly one result, and a half-committed turn cannot request the parent LLM.
- Partial failure does not lose other results; parent cancellation propagates, and unfinished tasks keep IDs and reasons.
- `result_ready` and `committed` transition one way; a repeated commit is refused idempotently or returns the same commit, without producing a second parent tool result.
- After compaction, parent delegation summaries, active state, aggregate budget, and result references are accurate, and the full child Context does not enter the parent summary.
- When the parent task has active/pending delegations, the completion reminder, clean save, and task switching all refuse to close.
- Admission in Explore, awaiting approval, diagnosis, verification, Crash Recovery, and terminal states follows the matrix.
- Child evidence does not enter the parent `verification_evidence`; parent independent verification is still a necessary condition for completion after changes.
- Trace consumes only public parent snapshots, does not read child history, sessions, or tools, and does not rejudge findings.
- Crash injection covers created, running, result_ready, single-result committed, and multi-result half-turn commit positions.
- No regressions in the Direct Path, ordinary tool concurrency, Plan/Repair, process management, v0.32 durable boundary, and v0.33 recovery (where present).

### 10.2 Stage-level E2E scenarios

1. The parent Agent delegates "locate the authentication entry"; the subagent reads several files read-only and returns evidence with paths, line numbers, and claims; the parent Agent rereads the key positions and then makes a plan.
2. A subagent tries to request `write_file`, `run_shell`, plan tools, process tools, or delegate again; the tool schemas are not visible, and the Runtime refuses forged calls before execution.
3. The parent Agent delegates "check the implementation", "check the tests", and "check documentation constraints" at the same time; the three finish out of order, and the parent Context receives structured results in call order and synthesizes them.
4. One subagent times out, one has an illegal result format, and one succeeds; all three parent tool results exist, the successful result is not lost, and aggregate usage is correct.
5. The sum of several subagents' maximum budgets exceeds the parent's remaining budget; the Scheduler deterministically refuses the over-quota tasks before starting, producing no extra LLM requests.
6. The parent task receives `/new` or exit while a subagent runs; it cancels and waits within bounds; when cleanup is incomplete, the old task is kept and cannot be saved as clean.
7. A subagent claims some behavior is correct; the parent Agent cannot complete based on that without independent recheck or verification; it closes only after parent verification passes.
8. The same contract returns the same findings repeatedly, without bypassing the stall guard through new IDs or new summaries; after changing the investigation scope and getting new evidence, it can continue.
9. With `/save` on, kill the runtime between child result production and the parent Context commit; recovery recognizes the durable `result_ready` and commits the original result only once.
10. Crash while a subagent is still running; recovery does not forge success, does not inherit old threads, and does not treat reinvestigation as a zero-cost automatic replay.
11. After at least one parent Context compaction and one session resume, delegation relations, budgets, result references, and parent Plan/verification boundaries stay accurate.
12. `/trace` can show the causal chain "parent delegation—child result ready—parent result committed—parent decision—execution—verification", and shows unresolved for broken chain records.
13. In the same task, the parent uses provider A and the child uses provider B with a different protocol; after the child's read-only investigation returns, the parent continues with its original model, both go through the same loop, and request configurations do not contaminate each other.
14. With only the old triple configured, parent and child still use the default model; requests for unknown or unapproved child profiles are refused before going online, and the parent receives a unique tool result.

### 10.3 Stage definition of done

The checklist below distinguishes "version feature implemented" from "stage acceptance evidence complete". Checked items are backed by implementation and regression tests; unchecked items still need item-by-item review and cannot be assumed passed from the version implementation status in §8.1. v0.39 fault injection now covers after result ready, half-turn commits of several results in the same turn, and retry of derived session write failures; stage-level E2E must still be signed off separately. A security review also found: the current ScopeGate can read local configuration through a symlink pointing to `config_local.py`; if the session directory is inside the delegated workspace, subagent access is not forbidden either. Until fixes and regression tests are done, the sensitive path boundary of §7 must not be treated as passing acceptance.

- [ ] `v0.34`–`v0.39` each have their own tutorial, change record, tests, and reproducible acceptance scenarios.
- [x] The Task / Result Contract is a structured, validatable, bounded protocol from the first version.
- [x] Mutable Runtimes are fully isolated; immutable tool definitions are shared; child capabilities are filtered through an explicit policy.
- [x] Parent and child have only one canonical Runtime / Loop; Context, State, Tool View, Model, Budget, Permission, and Completion Policy express the differences, and the Runner and adapters do not copy the control loop.
- [x] v0.36 multi-provider supports several same-protocol configurations and the two first protocols, parent and child models can bind independently; old single-model configuration stays compatible, and sources are auditable without leaking real configuration.
- [x] Subagents are always read-only and single-level and cannot change parent state, permissions, plan, generation, or verification.
- [x] Per-subagent budgets and the parent aggregate budget are not over-issued on serial, parallel, failure, cancellation, and recovery paths.
- [ ] All execution outcomes form results and go through auditable `result_ready → committed` delivery.
- [x] Several subagents can run in bounded parallel and commit in parent model order, with exactly one result per tool call.
- [x] Child evidence is clearly separate from parent authoritative completion evidence; the parent still exclusively owns changes and verification.
- [x] Active or uncommitted delegations block completion, clean save, and unsafe task switching.
- [x] Durable Delegation and v0.33 Crash Recovery use the same uncertain facts and recovery semantics, without automatically forging, replaying, or committing twice.
- [ ] Read-only Trace, Plan Contract, PermissionGate, Repair Loop, generation, session, and the complete tool result protocol are not bypassed.
- [ ] Default tests, the tutorial check, the README check, and stage-level E2E all pass; the core runtime still depends only on the standard library.
- [ ] Each version tag is created manually only by the user, and the assistant performs no tag operations.

## 11. Version Dependencies

```text
v0.25 Plan Contract / Trace
  + v0.29 task process lifecycle
  + v0.31 Safe Resume
  + v0.32 Durable Tool Boundaries
                ↓
v0.34 Minimal Delegation
Implemented: single synchronous read-only subagent, Runtime protocol shell, Task / Result Contract, depth=1
                ↓
v0.35 Unified parent/child run loop
Single canonical Runtime / Loop, instance configuration, parent safety semantics kept
                ↓
v0.36 Multiple providers and model selection
Unified protocol adaptation, separate parent/child model bindings, old configuration compatibility
                ↓
v0.37 Lifecycle & Budget
Parent/child identity, delivery state, cancellation/timeout, individual and aggregate budgets
                ↓
v0.38 Parallel Delegation
Dedicated scheduler, bounded concurrency, result order, partial failure
                ↓
v0.39 Durable Delegation ←→ v0.33 Crash Recovery
result_ready / committed, session, Trace, crash coordination
```

Keep `v0.34`, with no rollback needed. `v0.35` must first finish loop convergence, then connect multiple providers in `v0.36`; later scheduling and lifecycle only extend the unified implementation. Do not persist running child Contexts early in `v0.37`, do not allow subagents to change the workspace in `v0.38`, and do not automatically restore old threads or unconditionally rerun investigations in `v0.39`. Each version focuses on one main concept, so behavior differences between adjacent versions can be taught.

## 12. Documentation and Release Sync

When each version is implemented, sync:

- The Stage 10 learning path and current version in `README.md` and `README_EN.md`
- The Stage 10 navigation in `docs/tutorials/README.md`
- The matching version tutorials: keep `34-minimal-delegation.md`; add `35-shared-agent-runtime.md`, `36-multi-provider.md`, `37-subagent-lifecycle-budget.md`, `38-parallel-delegation.md`, `39-durable-delegation.md` (suggested later file names)
- The delegation tool, configuration, output, cancellation, and recovery notes in `docs/operation/manual.md`
- `CHANGELOG.md`
- Version information in `pyproject.toml`
- `docs/plans/README.md` and this plan's implementation status
- `AGENTS.md`, when repo-wide run, authorization, or change hard constraints are really added

The v0.39 implementation has synced bounded parallelism, batch budget reservation, persisting results first and then delivering in parent order, recovery not rerunning subagents, Trace, tutorials, the operation manual, README, CHANGELOG, and version information. The `v0.36` provider configuration, Runtime usage, parent/child bindings, and redacted recovery boundaries stay in place.

Tutorials first explain the difference between "tool concurrency" and "subagent delegation", then explain why separate State/Context can share the same loop and how configuration limits capabilities; then they explain the difference between providers, protocols, and models, and then introduce the two budget levels, result order, and durable delivery. When canonical Runtime, provider, ModelBinding, Subagent, delegation, result_ready, committed, aggregate budget, and authoritative verification first appear, they must be explained intuitively nearby, not just listed as fields.

Before each version's delivery, run:

```bash
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python scripts/check_tutorials.py
PYTHONPATH=src python scripts/check_readme.py
```

After the tutorial is complete and the user manually creates the matching tag, run the facts check that depends on local Git objects. The assistant must not create, move, overwrite, delete, or push tags.

## 13. Capability Boundary After the Stage

After Stage 10, parent and child in `mini_agent` share the same canonical Runtime / Loop and can use different providers/models through local configuration. It can hand several independent investigation questions to read-only, budgeted, single-level subagents, collect structured findings and evidence in parallel in isolated contexts, and return them to the parent Agent in a deterministic order across durable boundaries. The parent Agent is still the only changer, permission requester, main plan maintainer, and completion decider.

What this stage builds is "controlled cognitive delegation", not several agents writing code together. If subagents later need to make changes, a separate stage should first solve workspace/worktree isolation, change ownership, permission inheritance and decay, conflict merging, cross-agent verification, rollback, and durable execution; these capabilities cannot be smuggled in by widening `allowed_tools`.

# Stage 12: MCP and Skills Implementation Plan

> Status: `v0.46` implemented
> Suggested version range: `v0.43`–`v0.46`
> Capability prerequisites: unified Tool / PermissionGate / AgentRuntime, durable tool boundaries and crash recovery from Stage 9, parent/child capability isolation from Stage 10, Context and untrusted material boundaries from Stage 11
> Related plans: `reliable-execution-plan.md`, `session-persistence-resume-plan.md`, `subagent-delegation-plan.md`, `memory-retrieval-references-plan.md`

This plan references the [MCP `2025-11-25` lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle), [Tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools), [Resources](https://modelcontextprotocol.io/specification/2025-11-25/server/resources), [Prompts](https://modelcontextprotocol.io/specification/2025-11-25/server/prompts), and [Streamable HTTP](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports), as well as the on-demand capability organization of [OpenCode MCP](https://opencode.ai/v2/docs/mcp-servers) and [OpenCode Skills](https://opencode.ai/v2/docs/skills). It is a deliberately trimmed teaching implementation and does not claim compatibility with all MCP Servers or to replicate OpenCode.

## 1. Goal and Positioning

After Stage 11, `mini_agent` can read workspace Memory and named local References on demand, but external standard capabilities still cannot be connected through the unified Tool boundary; repeated multi-step workflows can only rely on ordinary project instructions or temporary user prompts.

The question Stage 12 answers: **how to connect standard external capabilities and load reusable workflows on demand without bypassing the existing permission, execution, recovery, and Context boundaries?** v0.46 completes the JSON-only HTTP, text Resource, and text Prompt subset this plan defines.

One-sentence goal: **let the parent Agent connect controlled external capabilities through MCP and load local workflow instructions on demand through Skills, while continuing to reuse the existing Tool, PermissionGate, Context, and AgentRuntime.**

The two main threads must stay separate:

```text
MCP Server → MCP Client / Adapter → Tool Registry → ToolExecutor / PermissionGate → AgentRuntime

Skill directory → name + description discovery hints → skill(name) → SKILL.md body
                                                              ↓
                                                   ordinary tool history / Context
                                                              ↓
                                                   run by existing Tools / MCP Tools
```

**MCP gives the Agent new capabilities; a Skill teaches the Agent how to combine approved capabilities.** A Skill body is not a new execution permission and is not upgraded to a system instruction.

Each of the four versions covers one question: `v0.43` introduces the MCP protocol and the stdio lifecycle; `v0.44` has connected external Tools safely to the parent Runtime; `v0.45` has implemented the difference between Skills and Tools and on-demand loading; `v0.46` adds remote transport, Resources, and Prompts within a strictly limited scope.

## 2. Scope and Non-Goals

### 2.1 Scope of this stage

`v0.43` contains only a standalone stdio Client and a demo CLI; on top of that, `v0.44` connects explicitly enabled
local MCP Tools to the parent Runtime; `v0.45` adds fixed-directory discovery and on-demand loading of local Skills; `v0.46`
adds the JSON-only HTTP, Resource, and Prompt subset defined below.

- Pin the handshake-style MCP `2025-11-25` protocol, first implementing `initialize → notifications/initialized → tools/list → tools/call` for local stdio Servers and refusing unsupported negotiated versions.
- MCP Servers are enabled only by local configuration; the tool catalog is frozen when the parent Runtime is created, and external Tools run through the existing Registry, Executor, PermissionGate, Plan gate, Failure, Trace, and durable tool boundary.
- External MCP Tools default to `effect_class="possible"`; only tools named exactly in local configuration can be marked `none`. Server names, descriptions, schemas, annotations, and results do not decide the safety level.
- Discover `SKILL.md` from project-level and global local directories; show the parent model a bounded `name + description`, and load the body on demand through an ordinary read-only `skill(name)` Tool.
- Define deterministic same-name priority, size limits, path boundaries, and permission rules for Skill loading; the body enters ordinary tool history only as untrusted workflow material and is trimmed by the existing Context.
- `v0.46` adds a teaching subset for Streamable HTTP Servers that return JSON responses only, plus explicit application-side/user-side entries for bounded UTF-8 text Resources and text Prompts.

### 2.2 Not in this stage

- No MCP Server framework, Marketplace, plugin system, OAuth management, Skill store, online Skill catalog, automatic Skill generation, or embedding retrieval.
- No `2026-07-28` modern lifecycle, automatic protocol detection, or multi-version fallback; no server-initiated sampling, elicitation, roots, tasks, or similar interactions.
- No MCP catalog hot refresh, subscriptions, change notification handling, resource templates, completion, binary/image/audio content, or Streamable HTTP SSE responses, GET listening, reconnect recovery, and redelivery.
- MCP Resources / Prompts are not disguised as ordinary Tools the model can call autonomously; MCP server instructions are not injected into the protected system prompt automatically.
- Skills do not run scripts automatically, implicitly grant tool permissions, or directly advance the Plan / verification; MCP and Skills are not opened to Subagents by default.
- No third-party core dependencies. MCP stdio, JSON-RPC, the HTTP client, restricted frontmatter parsing, and lifecycle management all use the standard library; LLM transport keeps following the existing `http.client` and `Accept-Encoding: identity` constraints.

## 3. Architecture Decisions to Freeze First

### D1: The protocol version is pinned, and the chosen classic handshake is implemented completely

The client requests only `2025-11-25`. The `initialize` response must have an acceptable version, server information, and capability declarations; a version mismatch, an invalid protocol response, or missing required capabilities fail explicitly with no implicit fallback. After a successful response, `notifications/initialized` must be sent before listing tools or sending calls. The pagination of `tools/list` must be read to the end, bounded by page count, tool count, and response byte limits; the first page must never be mistaken for the complete catalog.

`v0.43` can use a standalone client and a local test Server to demonstrate JSON-RPC request IDs, response pairing, notifications, errors, and shutdown, without exposing MCP Tools that are not yet under permission management to the model. stdio's stdout carries only protocol messages; stderr is drained within bounds and isolated from protocol output. No response, oversized lines/messages, bad JSON, wrong IDs, early exit, and timeouts all produce explicit failures with no infinite waiting.

### D2: The Tool Adapter only connects to the existing execution chain and does not copy the Agent Loop

`v0.44` registers discovered MCP Tools as ordinary `Tool`s, triggered by the existing `AgentRuntime.run()`. The suggested external name is `mcp_<server>_<tool>`; name normalization, length limits, and collision checks are done before registration, and any two external tools, or an external and a built-in tool, that have the same name after normalization are refused, never silently overwritten. Internally the exact original server/tool names are kept for the real `tools/call`; the original name is never guessed back from the external name.

The MCP `inputSchema` is external JSON Schema, while the current `validate_arguments()` supports only a subset. The Adapter must list the supported fields and keywords explicitly; schemas or arguments that cannot be validated correctly are refused at registration/admission, never passed through to the remote side after quietly dropping constraints. The conversion result must keep bounded text and an explainable source; unsupported content types are marked or refused explicitly, and binary data is never treated as text. JSON-RPC errors, `isError=true` from `tools/call`, disconnects, timeouts, and protocol errors must all become distinguishable `ExecutionResult` failure facts, and every model call still gets its matching `role=tool` result.

### D3: External Tools may have side effects by default; only local configuration can downgrade them

All MCP Tools default to `effect_class="possible"` and default permission `ask`. Server `readOnlyHint` and other annotations, names, descriptions, or `outputSchema` are only external metadata and cannot change the local side-effect level or authorization; the MCP specification also requires treating annotations from untrusted servers as untrusted. Only an explicit declaration in local configuration for an **exact server/tool identity** can set it to `none`; read-only status cannot be inferred from free text the server provides or broad wildcards.

Downgrading to `none` only affects the existing planning/generation classification; it does not mean no risk, no permission, or automatically becoming verification evidence. MCP calls with the default `possible` are refused in `exploring`; if read-only planning investigation is really needed, the tool must first be configured exactly and still go through the PermissionGate. Permission rules can be configured by the external server/tool name; the authorization prompt must show the server, the original tool name, and a bounded, redacted argument summary at the same time, so a call is never misidentified by its normalized name alone. `always` must not expand the authorization scope because of wildcards in external arguments.

### D4: The MCP connection is Runtime infrastructure, not a task background Process

stdio Servers are started by explicit local configuration, not created by the model through `start_process`, and not registered as background processes of the current task; the connection itself cannot be reused by the model to write stdin or control the PID. Configuration of process start, environment variables, working directory, and remote URL/headers must have clear boundaries; sensitive values are read only from local configuration or the environment and never enter State, Context, session, Trace, tool results, authorization prompts, or terminal errors. The credential-free server alias, transport, protocol version, and configuration fingerprint can be recorded.

Server connections, PIDs, pipes, and HTTP session IDs are not written to the session. On normal Runtime/CLI exit, abnormal exit, `/new`, `/reset`, and EOF, stdio Servers are closed within bounds; a cleanup failure reports the specific server and reason, never quietly leaving processes behind. When the Runtime is recreated or a task resumes, it reconnects and rediscovers the catalog from the current local configuration; the configuration or catalog in an old session can serve only as historical fact, not as execution authorization. Starting from configuration can itself run external code, so only Servers the user explicitly configured and enabled are allowed; they cannot be started dynamically based on model or Skill text.

### D5: Side effects, durable tool boundaries, and crash recovery stay managed by the parent Runtime

An MCP `tools/call`, like any other Tool, completes argument, phase, and permission checks before the handler. With `/save` on, a `possible` call must first commit schema 3's `handler_admitted` before sending the request to the Server; each call's State, matching `role=tool`, and tool boundary are still committed atomically in model order, and the next LLM round must not be requested before the whole round is committed. A commit failure must not send the remote request, enter later calls, or request the LLM.

When a request has been sent but its result was not recorded durably, recovery classifies it as "admitted, result uncertain"; it cannot be replayed, resent, or guessed as successful just because reconnecting succeeded. A disconnect or timeout cannot prove the remote side did not perform side effects either. Investigation during recovery, per-item `/resolve`, replanning, reauthorization, and independent verification follow the v0.33 contract. External Tool results, Resources, and Skill content cannot create verification evidence or advance the Plan on their own.

### D6: Skills are discovered by metadata and loaded as ordinary Tool results

The first version discovers only the fixed project-level and global local `skills/<name>/SKILL.md`, does not scan arbitrary directories recursively, and does not download from the network. The directory ID, frontmatter `name`, and call argument use the same stable, restricted name contract; on a name conflict, the project level takes priority over the global level, and duplicate sources, invalid names, or inconsistent metadata must be observable, never depending on file traversal order. v0.45's restricted frontmatter parses only the two single-line strings `name` and `description` and does not claim to support full YAML; parsing rules, unknown field handling, and UTF-8/size limits are fixed and tested at implementation.

Normally the parent model sees only bounded ID, `name`, and `description` catalog hints; all bodies must not stay resident in the system prompt. `skill(name)` is a parent-side read-only Tool whose permission pattern is the Skill ID, defaulting to `ask`; a `deny`ed Skill is not shown to the model, and direct calls to it are refused. After authorization, the target file's canonical path, symlink target, file identity, encoding, and size are rechecked, and then the body becomes that call's ordinary `role=tool` result. Loaded results are subject to Context trimming and can be loaded again on demand in later rounds; no authoritative `active_skills` State is added, and the body is not treated as a durable system instruction. With `/save` on, loaded bodies may enter the session with ordinary history, so the only promise is not to copy the whole Skill directory additionally, not that the session contains no bodies.

Scripts, templates, and other files referenced inside a Skill are not run or read automatically in the first version; access still goes through the existing tools and permissions. A Skill cannot override the system prompt, `AGENTS.md`, the PermissionGate, the Plan, or explicit user requests; it provides only low-priority workflow suggestions.

### D7: Resources and Prompts keep their own control

MCP Tools are actions controlled by the model; Resources are material chosen and attached by the application; Prompts are templates chosen by the user. In `v0.46`, Resource listing/reading and Prompt listing/getting are triggered by explicit CLI/Host entries and are not registered as Tools the model can call on its own. Resource bodies enter the current Context as bounded, untrusted material; a Prompt chosen and reviewed by the user enters the session as user-side input but still cannot replace the system/project instructions or approve any tool call. The visible source is the server alias plus the URI/Prompt name; sensitive endpoints or auth headers are not brought into the Context.

Only text Resources and text Prompts are accepted; URIs, arguments, content length, returned message roles, and counts are all limited. Prompt messages returned by the server cannot forge system, tool, or authorization events; unsupported content types or roles are refused explicitly. Resource reads and Prompt gets also go through the local permission policy and source validation and are not authorized automatically just because the Server is connected. Server instructions are not injected into the protected system prompt automatically.

### D8: Remote HTTP is an explicitly limited teaching subset and does not claim full transport compatibility

`v0.46` keeps using the pinned `2025-11-25` handshake. It implements a restricted Streamable HTTP POST on top of the standard library `http.client`: per-request JSON-RPC, the necessary `Accept` and protocol version headers, the session header after initialization, local injection of auth headers, and timeout and response size limits. Only Servers that return `application/json` are supported; if a Server returns `text/event-stream`, it reports explicitly that this is unsupported, never tries to treat SSE as JSON, and never claims compatibility with general Streamable HTTP Servers. HTTP auth failures, redirects, session invalidation, and network interruptions must not trigger automatic retries that would replay `tools/call`.

Remote URLs must be listed explicitly in the user's local configuration, defaulting to HTTPS; if loopback HTTP is allowed, it must be configured separately with its security trade-off recorded. Auth tokens, real endpoints, and HTTP session IDs never enter durable summaries. Remote is only a Transport change; it does not change Tools' default `possible`, permissions, durable boundaries, or subagent isolation.

### D9: Subagents and the Context budget are not relaxed automatically by external capabilities

Stage 12 registers MCP, Skills, and user/application-side content entries only for the parent Runtime; subagents keep the existing four-tool allowlist and do not inherit the parent's MCP connections, Skill catalog, authorizations, Resources, or Prompt content. If the parent Agent wants to pass on external investigation facts, it can do so only through the existing bounded selected facts; child results are not upgraded to parent verification evidence.

MCP tool catalogs, descriptions, Skill catalog hints, ordinary tool results, and explicit Resource/Prompt inputs must each have their own length/count limits and count toward the existing Context budget. An oversized catalog is trimmed deterministically or refused explicitly, never quietly squeezing out protected instructions; all external bodies are untrusted material. Trace & Replay consumes only the structured facts recorded at the time and does not reconnect Servers, load Skills, or read Resources.

## 4. Version Slices and Implementation Tasks

### 4.1 `v0.43`: Minimal stdio MCP Client (implemented)

The goal is to run one restricted, local, closable MCP session independently, not to add tools to the Agent right away.

1. Add an MCP client / stdio transport that uses the standard library to start a single explicitly configured Server and handles JSON-RPC request ID management, response/notification distinction, stderr draining, timeouts, and bounded shutdown.
2. Pin `2025-11-25`: run `initialize → notifications/initialized → tools/list → tools/call` in order and validate capabilities and version; the tool list handles pagination and freezes a snapshot.
3. Provide a minimal local Server fixture for tests, with no MCP SDK as a runtime dependency; cover normal calls, server errors, `isError`, bad protocol, wrong IDs, no response, pagination, early exit, and cleanup.
4. Observe protocol results only through a test/manual demo entry; do not register Tools for the parent model and do not open a permission bypass for server calls.

Acceptance completed: a local stdio Server can complete the handshake, list all paged tools, call one text tool, and exit reliably; unsupported versions and abnormal messages fail explicitly, and the capability did not enter the model's tool catalog.

### 4.2 `v0.44`: MCP Tools connected to the Agent Runtime (implemented)

The goal is that external Tools are still ordinary Tools to the Agent while reusing all existing execution boundaries. The implementation is
complete; the core lands in `mcp/adapter.py`, `mcp/schema.py`, `tools/base.py`,
`tools/__init__.py`, `permission.py`, and the CLI/recovery lifecycle.

1. Connect the frozen MCP catalog during parent Registry assembly; establish naming, original identity mapping, schema subset validation, and conflict refusal. Do not expose unvalidated tool definitions to the model.
2. Route the `tools/call` handler through the ToolExecutor, PermissionGate, Plan gate, and Runtime; default `possible` / `ask`, with read-only downgrade allowed only by exact local configuration. Distinguish protocol errors, server `isError`, timeouts, and disconnects, and keep `role=tool` feedback complete.
3. Connect to the CLI lifecycle and the schema 3 durable tool boundary; connections and PIDs are not written to the session, reassembly happens on recovery, and admitted calls are not replayed automatically. State/Trace excerpts of external results keep only bounded, redacted summaries by default and do not copy large remote bodies.
4. Cover permission denials, the `exploring` gate, the order of parallel tool calls, a commit failure before the handler, a remote call that ran but whose result commit failed, the recovery handoff, invisibility to subagents, and process cleanup; offline acceptance is in `tests/test_mcp_v044.py`.

Acceptance completed: the parent model can call an approved `mcp_<server>_<tool>` just like `read_file`; on denial or commit failure, the remote side receives no call; a call that was sent but whose result is uncertain is not replayed after crash recovery.

### 4.3 `v0.45`: Discovery and on-demand loading of local Skills (implemented)

The goal is to let the model choose workflows by metadata instead of stuffing all Skill bodies into the prompt. Implemented according to this section's contract.

1. Add a project-level/global Skill catalog: fixed directories, restricted frontmatter, deterministic priority, same-name handling, and file identity and size validation; publish only bounded IDs, names, and descriptions.
2. Register the parent-side `skill(name)` read-only Tool; before loading, go through the PermissionGate by Skill ID, do not show denied items, and let the body enter history/Context as an ordinary Tool result. Make the Skill's source, trust level, and trimmable behavior explicit.
3. Cover same-name overrides, missing descriptions, invalid frontmatter, symlink escape, directory changes, read races, oversized bodies, refused loading, session recovery, and invisibility to subagents.
4. Use an example Skill that only guides existing Tools / MCP Tools to demonstrate "workflow guidance is not execution authorization", without letting the Skill run scripts automatically or skip approval.

Acceptance: before loading, the model sees only metadata; only after calling `skill(name)` does it see the full body; even if a Skill contains commands to run, later side-effect Tools still request permission independently, and the Skill body cannot enter the protected system instructions.

### 4.4 `v0.46`: MCP capability extension and stage wrap-up (implemented)

The goal is to show the extension of the same MCP Client to remote transport, material, and templates, without pursuing a production-grade remote MCP platform.

1. Add an explicitly configured remote HTTP transport that handles only `application/json` responses; reuse the handshake, request pairing, session, and Tool adapter, and report SSE responses explicitly as unsupported. Tests use a local HTTP fixture and depend on no public service.
2. Add bounded text `resources/list` / `resources/read` and `prompts/list` / `prompts/get`; provide application-side and user-side selection entries respectively, enforce source, content type, role, and permission validation, and do not register them as autonomous model Tools.
3. Bring Skill catalog hints, the MCP Tool catalog, and explicit Resource/Prompt content into the existing Context budget and safety notices; check remote authentication, session, Trace, recovery, and untrusted content boundaries.
4. Complete the protocol scope notes and cross-version end-to-end examples of the four lessons; make explicit the JSON-only remote subset, unimplemented capabilities, and differences from OpenCode/full MCP implementations.

Acceptance: can connect to a controlled remote test Server that returns JSON, use its Tools, and let the user/application explicitly choose text Resources/Prompts; Servers that return SSE, unsupported content, or require OAuth get explicit capability boundaries, with no automatic fallback or retry of side-effect calls.

## 5. File and Boundary Mapping

| Location | Expected change | Responsibility |
|---|---|---|
| `src/mini_agent/mcp/` | New in `v0.43`–`v0.46` | JSON-RPC, stdio/restricted HTTP transport, protocol client, paged catalog snapshots, and bounded errors |
| `src/mini_agent/tools/` | Incremental in `v0.44`–`v0.46` | MCP Tool adapter and `skill(name)`; Resources/Prompts stay CLI entries and keep using the parent Runtime boundaries |
| `src/mini_agent/skills.py` | New in `v0.45` | Local discovery, restricted frontmatter, priority, and safe reads |
| `src/mini_agent/permission.py` | Incremental changes | MCP server/tool and Skill ID permission patterns, redacted prompts |
| `src/mini_agent/context.py`, `prompt.py` | Incremental changes | Bounded catalog hints, low-priority Skill/Resource/Prompt material, budget and trust notes |
| `src/mini_agent/__main__.py`, `config.py` | Incremental changes | Parent Runtime assembly, explicit local configuration, CLI content entries, and connection cleanup |
| `src/mini_agent/state.py`, `session.py`, `runtime.py` | Avoid protocol changes | Reuse the existing tool boundary, completion decision, and recovery; if a schema change is required, first prove old sessions stay compatible |
| `tests/`, `docs/tutorials/`, the operation manual, `README.md`, `CHANGELOG.md` | Synced per version | Protocol fixtures, failure/security acceptance, one teaching thread per version |

## 6. Cross-Cutting Acceptance and Delivery

- Each version has protocol/behavior tests that do not depend on the external network; besides the success path, cover wrong IDs, abnormal output, pagination limits, timeouts, disconnects, name conflicts, unsupported schemas, permission denials, version mismatches, and cleanup failures.
- The default side-effect level of MCP Tools, the `handler_admitted` commit, ordered feedback, no replay on recovery, the read-only Plan phase, and the subagent allowlist stay consistent throughout the stage; no external result can pose as verification evidence.
- Skills, Resources, Prompts, and Server instructions must not override protected instructions or the PermissionGate; auth headers, real endpoints, PIDs, and HTTP session IDs never enter State, session, Trace, or user-visible errors. Skill/Resource bodies in ordinary tool history may be saved with `/save`, which must be disclosed clearly and kept bounded in size.
- The default install and core runtime still depend only on the standard library; LLM HTTP still uses `http.client` and sets `Accept-Encoding: identity` explicitly, and the MCP HTTP implementation does not change this constraint.
- `v0.43`–`v0.46` each have their own tutorial, change record, operation manual notes, and reproducible acceptance scenarios; when completing each version, sync the README, the tutorial index, and the version information. Git tags are operated only manually by the user.
- After changing the implementation, run at least the related tests; before delivery, run `PYTHONPATH=src python -m pytest -q`, `PYTHONPATH=src python scripts/check_tutorials.py`, and `PYTHONPATH=src python scripts/check_readme.py`, or state why they cannot run.

After v0.46, the parent Agent can use locally authorized MCP Tools, and the main CLI can choose remote text Resources or confirmed Prompts on demand; neither MCP nor Skills changes who has the right to execute, when authorization is required, or which facts can be used for recovery and verification.

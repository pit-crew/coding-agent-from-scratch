# mini_agent Operation Manual

> This manual follows the latest version. Current version: **v0.53** (regression comparison and Memory retrieval ablation; includes the earlier frozen fault matrix, coding benchmark, Evaluation Harness, plan-driven execution, tool permissions, parent-side Memory/References/MCP/Skills, and lightweight subagent collaboration).

## v0.53 Regression Comparison and Memory Retrieval Ablation

Comparison evaluation freezes the v0.52 and v0.53 sources, four coding tasks, the same model alias, and the permission budget. The three groups are `old-off`, `current-off`, and `current-on`; each task is repeated three times, 36 slots in total. It compares only the v0.52→v0.53 version change and the switch of automatic Memory summary retrieval within v0.53. Live has not run yet; the full plan must first be generated and reviewed, and then started explicitly by the user.

```bash
PYTHONPATH=src python -m mini_agent.evaluation validate-comparison /path/to/filled-spec.json
PYTHONPATH=src python -m mini_agent.evaluation plan-comparison /path/to/filled-spec.json --output /private/tmp/v053-review-plan
PYTHONPATH=src python -m mini_agent.evaluation self-test-comparison --output /private/tmp/v053-offline
PYTHONPATH=src python -m mini_agent.evaluation report-comparison /private/tmp/v053-offline
```

`self-test-comparison` runs the real Runtime assembly with fixed responses, sends no provider requests, and marks results as `fixture`. Only after the reviewed plan is explicitly started is `run-comparison <comparison-plan.json> --live --output <new-run-dir>` run; there are no automatic retries or make-up runs. The report rebuilds per-task paired results from the raw trials and relative evidence digests; for details, see the [comparison evaluation notes](../evaluation/comparison.md) and the [v0.53 baseline status](../evaluation/baselines/v0.53/README.md).

## v0.52 Fault Injection and Recovery Evaluation

`reliability-boundaries@1.6` freezes 18 kinds of tool, permission, verification, process, persistence recovery, MCP, and subagent scenarios. `validate-reliability` outputs the full tasks and criteria as JSON, including visible tools, exact PermissionGate rules, budgets, fault targets, recovery steps, the source of simulated user feedback, and the grader. The offline self-test runs all 50 parameter slots by the manifest (two per variant); seven representative scenarios each plan three live runs, 21 slots in total; of these, permission denial accepts only safe termination, and the other six accept full recovery. Before the first request, both public tests and independent behavior grading are calibrated. Crash tasks state the phases before injection and after recovery explicitly; subagent timeouts must use the fixed budget published by the task. When a fault does not trigger, the related invariants are recorded as incomplete evidence.

```bash
PYTHONPATH=src python -m mini_agent.evaluation validate-reliability tests/fixtures/evaluation/reliability/suite.json
PYTHONPATH=src python -m mini_agent.evaluation self-test-reliability --output /private/tmp/mini-agent-reliability-offline
PYTHONPATH=src python -m mini_agent.evaluation report-reliability /private/tmp/mini-agent-reliability-offline
```

Offline probes test runtime boundaries directly and do not run the Agent; so the task grader and recovery success rate stay `null`. Live must be started explicitly after reviewing the tasks; before the first model request, the command checks the local model binding of the seven scenarios. Each trial has at most 20 rounds, 48 parent tool calls, 240 seconds, and 64,000 parent tokens; subagents are still bound by the runtime's existing limits, and scenarios do not relax them. After one model request fails there is no automatic retry, and slots already produced are kept.

```bash
PYTHONPATH=src python -m mini_agent.evaluation run-reliability tests/fixtures/evaluation/reliability/suite.json --live --repeats 3 --output docs/evaluation/baselines/v0.52/live-<run-id>
PYTHONPATH=src python -m mini_agent.evaluation report-reliability docs/evaluation/baselines/v0.52/live-<run-id>
```

`report-reliability` rebuilds results from the frozen material, the ordered ledger, and the raw trials, and reports fault state, invariants, Agent terminal state, grader, recovery steps, cleanup, usage, and missing slots separately. Fixture and live are not combined; unobserved tokens are not treated as zero, and cost is `null` without a price snapshot. After the targeted budget fix, `live-20260929-08` had 21/21 HTTP 503 slots; `live-20260929-09` had 20 connection-type infrastructure errors, and 1 more trial stopped on the token limit before the fault triggered. The recovery denominator of both batches is 0, and the suite 1.5 baseline is not complete. The pre-fix 5/14 of `live-20260929-07` is kept as a historical result and is not merged with the new batches. See the [baseline directory](../evaluation/baselines/v0.52/README.md) for details. Budget estimates cannot guarantee that any provider request never exceeds its quota.

OpenAI Chat protocol compatibility: the optional `reasoning_content` in ordinary and streaming responses is kept with the assistant history and sent back; the field must be a string or null, with strings at most 4 Mi characters; it is not shown in the terminal body and does not enter State/Trace summaries. With `/save` on, it can be saved to the session with the Context. Fields already lost from old history cannot be restored, and continued requests of old thinking sessions are not guaranteed to succeed.

## v0.51 Coding Task Set

The coding baseline runs four pure standard-library Python tasks in a fixed suite order; each task copies the same initial files into a separate trial workspace. The tasks cover the last-page pagination boundary, a two-module change for order discounts and receipts, cache expiry with a regression test, and a configuration priority investigation that does not point out the faulty file in advance. The independent grader runs after the Agent stops.

The suite digest binds the case, task text, initial files, grader, and known-good version. Before running, the tasks, success criteria, time/round limits, and approved tools printed by `validate-suite` must be reviewed. The command requires an explicit `--live`; task review is still a precondition for starting these 12 first real calls:

```bash
PYTHONPATH=src python -m mini_agent.evaluation validate-suite tests/fixtures/evaluation/benchmark/suite.json
PYTHONPATH=src python -m mini_agent.evaluation run-suite tests/fixtures/evaluation/benchmark/suite.json --live --repeats 3 --output ./evaluation-baselines/v0.51
PYTHONPATH=src python -m mini_agent.evaluation report-suite ./evaluation-baselines/v0.51
```

`run-suite` fully pre-checks all tasks and the local model binding before starting; each trial is tried only once and written to `suite-run.json` in suite order. Start failures, interruptions, and unrun slots all stay in the planned denominator; existing raw trials are not overwritten by retries. The result directory saves a copy of the suite manifest, the ledger, and the raw `trials/` evidence. Single-task `TrialResult` schema 1 stays readable, and suite trials use schema 2 and record the Git revision and the runtime code fingerprint.

`report-suite` rebuilds the per-task and total reports from the ledger and the referenced raw trials. Planned count, run, gradable, passed independent acceptance, final success, infrastructure errors, failure categories, observed calls/tokens, and duration are listed separately, and each number keeps its trial references. `live_baseline_complete` shows whether all 12 planned slots have gradable live results; when not, the incomplete status is kept. Live and fixture are separate; without a price snapshot, cost is `null`. The first baseline plan is 3 runs per task, 12 in total; results await task review, and offline checks are not treated as model scores. For detailed fields and counting rules, see the [evaluation notes](../evaluation/README.md) and the [baseline directory](../evaluation/baselines/v0.51/README.md).

## v0.50 Evaluation Harness

The Evaluation Harness copies a fresh workspace from a fixed task, calls the canonical Agent Runtime once, and then an independent grading program checks the files the Agent left when it stopped. Regular tests verify implementation boundaries; the Harness records the result of one concrete Agent task. `self-test` uses fixed responses, verifies only the chain, and does not count toward the real model success rate.

Task validation checks schema 1, fixture/grader relative paths, symlinks, file count and size, Agent rounds, and two kinds of timeouts. The model tool surface is at most `read_file`, `list_dir`, `grep`, `write_file`, `edit_file`, and `calculate`; `authorized_tools` in a task maps to capabilities explicitly allowed when unattended. Unauthorized calls are refused by the non-interactive PermissionGate, without reading stdin.

```bash
PYTHONPATH=src python -m mini_agent.evaluation validate tests/fixtures/evaluation/smoke/case.json
PYTHONPATH=src python -m mini_agent.evaluation self-test --output ./evaluation-results
PYTHONPATH=src python -m mini_agent.evaluation report ./evaluation-results
```

Real model calls can only be started through an explicit `--live`. Before running, the CLI shows the task, rounds, and Agent/grading time limits; without a usable local `config_local.py`, it reports an error before requesting the model.

```bash
PYTHONPATH=src python -m mini_agent.evaluation run tests/fixtures/evaluation/smoke/case.json --live --output ./evaluation-live
PYTHONPATH=src python -m mini_agent.evaluation report ./evaluation-live
```

Each `trial-<case-id>-<uuid>` directory is published through atomic replacement in the same directory and contains `trial.json`, a bounded `diff.patch`, `agent.log`, and `grader.log`. `success` requires the Agent to end with normal text, State `done`, at least one successful model response, the grader passing, and temporary resource cleanup complete. The Agent's own claims and self-verification do not change the independent grade. After an Agent timeout the grader still runs; timed-out trials with a valid grader result count in the denominator. Runner or grader infrastructure errors are counted separately and removed from the grading denominator.

Live and fixture are summarized in separate groups. There is currently no price snapshot, so `cost_usd=null`; the recovery success rate and invalid repetitions are not applicable/not collected in this version and also stay `null`. When the Worker is forcibly stopped, unwritten token/tool counts use `null`.

Workspace isolation guarantees that reruns start from the same fixture, but it is not an operating system security sandbox: the Agent worker and grader still run as the caller's system account. For the full task fields, result contract, denominators, and manual review steps, see the [Evaluation Harness notes](../evaluation/README.md); for the teaching flow, see [Lesson 50](../tutorials/50-evaluation-harness.md).

## v0.43 Standalone stdio MCP Client

v0.43 provides an MCP demo command that does not connect to the Agent Runtime. It connects to one local stdio Server following the fixed
`2025-11-25` lifecycle:
`initialize → notifications/initialized → tools/list → tools/call`. The Server's stdout
carries only line-delimited UTF-8 JSON-RPC; stderr is drained separately and only a bounded tail is kept.

### Configuration

Real commands, paths, and environment values go in the untracked `src/mini_agent/config_local.py`; importing the configuration does not start a process:

```python
MCP_SERVERS = [{
    "alias": "demo",
    "command": ["python", "../../tests/fixtures/mcp_stdio_server.py"],
    "cwd": ".",
    "environment": {},
}]
```

`alias` must be a restricted, unique name starting with a lowercase letter; `command` is a non-empty list of string argv;
`cwd` is an optional string, and relative paths are based on the directory of `config_local.py`;
`environment` is a string mapping. The command does not go through a shell. Only the demo command that explicitly selects an alias starts
the Server.

### Standalone commands

```bash
PYTHONPATH=src python -m mini_agent.mcp demo list
PYTHONPATH=src python -m mini_agent.mcp demo call echo '{"text":"hello"}'
```

`list` reads all pages and shows a bounded tool catalog; later reads on the same connection return only the frozen snapshot.
`call` shows the alias, the raw tool name, and the arguments in full before the request, and sends one `tools/call` only when the interactive terminal input is `yes` or
`y`. Over-long arguments, arguments that cannot be shown fully, EOF, refusal, and non-interactive input all send no
call. The exit path closes stdin, waits for the child process, and terminates and reaps the direct child process when needed;
if cleanup does not finish, it reports an error and returns a non-zero status.

### Troubleshooting

Startup/handshake times out after 10 seconds by default, each catalog page after 10 seconds, tool calls after 30 seconds, and the shutdown grace is 2 seconds. A single
stdout message is at most 1 MiB, the stdout wait queue holds at most 64 messages, only the latest 64 ordinary notifications are kept, stderr keeps only the last 16 KiB, and the catalog
has at most 16 pages and 256 tools. Bad encoding, bad JSON, wrong IDs, messages with both `result`/`error`, EOF,
exceeded limits, and protocol desync all invalidate the connection; `tools/call` is not retried automatically. JSON-RPC `error` and
`isError=true` in tool results are handled separately.

Exceptions show only a limited category and the server error code, not the full command, environment variables, raw arguments, or
the server error body. When the Server does not respond, check that its stdout outputs "one JSON object per line";
do not write logs to stdout, write them to stderr.

The manual confirmation in this version is only interactive protection for the demo command, not the Agent's PermissionGate. MCP Tools
do not enter the model, Tool Registry, State, or session; the connection and PID exist only in the current demo process.
## v0.44 MCP Tools in the Parent Agent Runtime

v0.44 adds a parent-side assembly path on top of the fixed stdio Client of v0.43. Servers are still provided by the local
`MCP_SERVERS` configuration, and only entries with `agent_enabled=True` are started when the parent Runtime is created;
entries that omit the field or set it to `False` keep being used only by the standalone `python -m mini_agent.mcp` command.
Importing the configuration does not start a Server, and argv does not go through a shell.

```python
# src/mini_agent/config_local.py (untracked)
MCP_SERVERS = [{
    "alias": "demo",
    "command": ["python", "../../tests/fixtures/mcp_stdio_server.py"],
    "cwd": ".",
    "environment": {},
    "agent_enabled": True,
    "readonly_tools": ["echo"],
}]
```

`readonly_tools` is an exact list of raw tool names returned by the same Server. Tools in the list only lower
`effect_class` from the default `possible` to `none`; they still pass through the PermissionGate and cannot automatically become
verification evidence. Server annotations, names, descriptions, and schemas cannot change this classification.

The parent side completes the fixed handshake, reads all pages, and freezes the catalog, then exposes the tools as
`mcp_<alias>_<tool>`. Raw tool names accept only up to 64 ASCII letters, digits, `_`, and `-`, are lowercased,
and have `-` replaced with `_`; exposed names are at most 64 characters. When built-in tools, different MCP tools, or normalized names collide,
the whole Runtime assembly fails and already started Servers are closed. MCP input schemas support only a root object,
scalar properties, scalar arrays, `required`, boolean `additionalProperties`, `enum`, string/number bounds, and
array length bounds; nested objects and unknown validation keywords are refused before the model sees the tool.

MCP Tools go through the ordinary Tool Registry, ToolExecutor, PermissionGate, Plan gate, and
`AgentRuntime.run()`. The default permission is `ask`; the authorization prompt shows the alias, the raw tool name, and a bounded argument summary,
hides the values of suspected credential fields, and shows only the length of long values. JSON-RPC errors, `isError=true`, timeouts, disconnects, protocol
errors, and unsupported image/binary/structured results become tool failures with an explicit `error_kind`; a timeout's
`outcome` is `timeout`. Successful text is kept as a bounded `role=tool` body, and State/Trace excerpts keep only metadata such as
the source, alias, raw tool name, category, and length.

With `/save` on, MCP Tools, like other possible Tools, first enter the schema 3/4
`handler_admitted` boundary before the handler; a commit failure sends no `tools/call`. Calls already admitted whose results are not settled are
recorded as uncertain facts on recovery by the existing rules and are never replayed. New tasks, resumed tasks, and task switches all rediscover the catalog from the current local
configuration; connections are not written into State, Trace, session, or Subagents. Exit, `/new`, `/reset`,
EOF, and recovery candidate/claim failures all close connections within bounds and report the unfinished server aliases and reasons.

The parent prompt marks the MCP catalog and results as untrusted external material: they cannot override instructions, permissions, or the Plan, and cannot
act as verification evidence. The MCP scope of v0.44 does not connect to Subagents, Skills, remote HTTP, Resources,
or Prompts; for the v0.45 local Skills, see the next section.

## v0.45 Local Skills

A Skill is a workflow description that helps the model arrange existing tools. It adds no new execution capabilities and does not automatically run commands mentioned in
the body. The parent Agent normally sees only limited metadata from fixed directories; only after the model calls `skill(name)` and
passes the `PermissionGate` is the `SKILL.md` body read.

### Directories and frontmatter

When the Runtime is created, it scans two fixed directories:

```text
<workspace-root>/skills/<name>/SKILL.md
~/.mini_agent/skills/<name>/SKILL.md
```

A project-level Skill takes priority over a global Skill with the same name. If the project-level directory with the same name is invalid, the global item with the same name is not shown as a fallback. Directory
names, the frontmatter `name`, and the tool argument must start with a lowercase letter, contain only lowercase letters, digits, `_`, and `-`,
be at most 64 characters, and the directory name and `name` must match.

The file accepts only two single-line fields surrounded by `---`: `name` and `description`. Unknown fields, duplicate fields, missing
fields, control characters, bad UTF-8, and format errors all invalidate the candidate. The two root directories together scan at most 64 direct
directory entries; a root directory that exceeds the current remaining quota is skipped entirely, and when the project-level directory exceeds the limit, the whole Catalog stays empty, to avoid
being unable to judge whether it shadows a global item with the same name. A single file is at most 32 KiB,
a description at most 240 characters, and the catalog hint sent to the model at most 8 KiB. The catalog is sorted by Skill ID and shows only the ID, name,
description, and source level; it does not show real paths or bodies. Metadata is provided to the model as a user-level message marked untrusted
and is not merged into the protected system message.

### Permissions and loading

The default permission of `skill` is `ask`, and the permission pattern is the Skill ID. The catalog hint uses the same PermissionPolicy to
hide IDs that are currently `deny`, but direct calls still pass through the PermissionGate again. Choosing `always` approves only the current
literal ID; the authorization prompt shows the Skill ID and the project/global source, not the real path.

After approval, the Catalog opens directories and files segment by segment from the frozen root directory fd, refuses symlinks, and rechecks the file
identity, modification time, and size before and after reading. File replacement, race changes, out-of-bounds opens, bad encoding, and exceeded limits all return a bounded
`skill_access_error`, without leaking absolute paths or the Skill body.

A successful result contains the Skill ID, source, byte count, and full body. The full body is only an ordinary `role=tool`
history result of the current call and follows the existing Context trimming; State, Trace, and extra catalog snapshots keep only the ID, source, and byte count.
With `/save` on, a body that has already entered ordinary tool history may be saved with the session. Except for Skills explicitly
listed by v0.47 named roles and pre-authorized by exact ID on the parent side, the Catalog, Skill Tool, bodies, parent permissions, and catalog hints do not
enter Subagents; a role's child Catalog can only load the IDs approved this time. Skills also do not become Plan or verification
evidence.

### Observe a local Skill

You can create the file below in the workspace and then start the parent CLI:

```text
skills/verify-change/SKILL.md
```

```markdown
---
name: verify-change
description: Complete a bounded code change in the order read, change, verify
---
# Verify a change
1. Read the related implementation and tests.
2. Make the smallest change with existing tools.
3. Run verification independently with run_shell.
```

Before the first request, the model can see only the ID, source, and description of `verify-change`. Only after the model calls `skill` and gets one
authorization does the body appear in the tool result; if the body suggests calling `run_shell`, that call is still handled by its own Plan gate and
PermissionGate rules. Only when a new task starts after the Skill file is changed does the Runtime discover the new file identity and content.

## v0.46 Restricted HTTP MCP, Text Resources, and Prompts

v0.46 adds a restricted MCP HTTP subset to the parent Runtime. When the configuration explicitly states
`transport="http"`, the client sends JSON-RPC per request using the standard library `http.client`; by default it accepts only
HTTPS. For offline tests, loopback HTTP is allowed only when `allow_loopback_http=True` is also configured. The client
sends the protocol-required `Accept: application/json, text/event-stream`, but this teaching subset accepts only
`application/json` responses; SSE, redirects, OAuth, server-initiated
requests, and automatic retries are out of this version's scope. This is a teaching subset, not a complete Streamable HTTP client.

### HTTP configuration

Real URLs and auth headers go only in the untracked `src/mini_agent/config_local.py`. Importing the configuration does not connect to the
Server; only entries with `agent_enabled=True` have connections created and catalogs frozen by the parent Runtime. HTTP entries cannot also
contain the stdio `command`, `cwd`, or `environment`:

```python
MCP_SERVERS = [{
    "alias": "remote-demo",
    "transport": "http",
    "url": "https://mcp.example.invalid/mcp",
    "headers": {"Authorization": "Bearer local-token"},
    "allow_loopback_http": False,
    "agent_enabled": True,
    "readonly_tools": [],
}]
```

`url` refuses user info and fragments; plaintext HTTP allows only loopback addresses and requires the explicit switch, and HTTPS can use controlled
remote addresses. The client-managed
`Accept`, `Content-Type`, `Accept-Encoding`, `MCP-Protocol-Version`, and `MCP-Session-Id`
cannot be overridden by configuration. Auth headers stay only in the current process and do not enter State, Trace, session, authorization prompts, or
error text. The `MCP-Session-Id` from the initialization response is carried only in memory; on exit a session
`DELETE` is attempted within bounds.

### Resource and Prompt commands

Resources and Prompts are not registered as model Tools. They are selected explicitly by the main interactive CLI of the current task:

```text
/mcp-resources <alias>
/mcp-resource <alias> <uri>
/mcp-prompts <alias>
/mcp-prompt <alias> <name> <JSON argument object>
```

Listing is allowed by default; reading Resources and getting Prompts ask by default. `always` remembers only the current
`alias:uri` or `alias:name`, and the authorization prompt shows only the alias, target, and a bounded argument summary. Before reading and getting, the URI or name is first
checked against the frozen paged catalog, so targets outside the catalog send no read request.

Resources accept only bounded UTF-8 text. A successful body is added to the current task as a low-trust ordinary history message with its source,
and does not request the LLM immediately; it takes part in the Context only at the next user input and may be saved with `/save`. It does not enter
State, Trace summaries, verification evidence, or automatic Memory queries. The body is trimmed by the Context budget.

Prompts accept only text messages with the two raw roles `user` and `assistant`. The CLI shows the expanded content in full,
keeping the source role with `[message ... original_role=...]` labels; the server's `assistant` text is still inside
one `role=user` input and does not forge a `role=assistant` in the session. When the user cancels the preview, nothing enters
history and the LLM is not requested; after confirmation, the existing `run_task` path runs the parent Agent.

Listing and reading both handle all pages and detect repeated cursors; the URI returned by a Resource must match the request, and blobs,
images, audio, and embedded content are refused. Prompt arguments must match the frozen definition, and expanded results refuse system/tool roles and non-text
content. The catalog, bodies, HTTP auth, and session IDs are not opened to Subagents.

## v0.47 Named Subagent Roles

v0.47 adds an optional `agent_profile` to the existing synchronous `delegate_task`. When the field is not passed, the original
generic subagent contract, model selection, result JSON, and persisted fields keep being used; when a role is passed, the runtime freezes the role's prompt,
tool subset, model alias, static permissions, and requestable Skill IDs. Delegation is still a single-level, synchronous, read-only call.

The four built-in roles are `explorer` (locate files and implementations), `reviewer` (look for concrete defects and risks),
`tester` (analyze tests and make suggestions), and `general` (generic read-only investigation). The default tool set of the first three is
`read_file`, `list_dir`, and `grep`; `general` can also use the pure compute tool `calculate`. Each actually available
tool must be in the subagent master allowlist, the role tool set, and this call's `requested_tools` at the same time, and pass the ScopeGate.
Role `permissions` can only write `allow` or `deny` for role tools; refused tools do not appear in the child model's
tool catalog, and the child Runtime does not prompt the user for authorization.

Custom roles can be added locally in the untracked `config_local.py`; `AGENT_PROFILES` is empty by default. Built-in names
cannot be overridden; role IDs must start with a lowercase letter, followed only by lowercase letters, digits, `_`, and `-`, at most 64
characters. Each role requires `description`, `prompt`, and `tools`, and can set `model_profile`,
`permissions`, and `skills`. The tracked `config_example.py` has a placeholder example without real credentials.

`model_profile` is a model alias in the existing provider catalog; `agent_profile` is a set of role rules.
When a role has no configured model, the subagent default model is used. When both fields are passed explicitly, the model alias must match the child model resolved
from the role; unknown, unauthorized, or conflicting aliases are refused before the subagent sends an LLM request, with no automatic switch.

Skill IDs listed by a role are only requestable local workflow material. Before starting the child Runtime, the parent side calls the current `PermissionGate` for each exact
ID; refused IDs do not enter the child Runtime, and a role referencing a nonexistent ID refuses this delegation. Approved items use a child Catalog containing only these IDs
and a separate allow/deny policy, and the body is read only after the child model calls `skill(name)` on demand.
The body is still an untrusted `role=tool` result; it adds no tool capabilities, does not automatically run commands in it, and does not enter the parent
State, Trace summaries, or verification evidence. Legacy delegations without `agent_profile` have no Skill tool.

`tester` has no shell or test execution tools, and the role prompt requires it to only suggest tests; report validation also refuses claims such as "tests
passed" and requires stating explicitly that no tests were run this time. Whether tests are actually run is still decided by the parent Agent through the original plan and permission
flow.

Delegation records and results of explicit roles save only the role ID and configuration fingerprint, not the role prompt body or child Skill bodies.
The contract hash includes these two role identity fields, so the same investigation with different roles has different identities; the contract
hash and session fields without a role keep the old shape. The ScopeGate also checks, by realpath, `config_local.py`, session-sensitive directories
inside the workspace, the actually used `SessionStore.root`, and the targets of their symlinks.

For example, to let the model use the review role, the call only needs one extra field on the original contract:

```json
{
  "goal": "Check the module's error handling boundaries",
  "scope": ["src/mini_agent"],
  "constraints": [],
  "expected_findings": ["Concrete defects and evidence"],
  "requested_tools": ["read_file", "grep"],
  "selected_parent_facts": [],
  "purpose": "investigation",
  "agent_profile": "reviewer"
}
```

After running, `agent_profile` and the fingerprint can be seen in the structured delegation result, while there is still only the original synchronous JSON result.
v0.49 adds cross-safe-point continuation for background child sessions whose successful results were claimed; the new contract and recovery boundaries are described first below, followed by the original v0.48 background task notes.

## v0.49 Resumable Child Sessions

In v0.48, `child_session_id` identifies background work only within the current CLI process. After the process exits, the parent session can remember only
summaries such as start, completion, and claiming, and cannot restore the subagent's conversation history from this ID. v0.49 adds `followup_subagent`: after
claiming a successful result of some round, the parent model can submit a complete new investigation contract with the same ID. The subagent keeps its own Context history and
the read-only observation facts allowed for continuation, then runs by this round's contract; the parent history and other child sessions stay invisible.

The tool uses the same `goal`, `scope`, `constraints`, `expected_findings`,
`requested_tools`, `selected_parent_facts`, `purpose="investigation"`, and per-round `budget` fields as `spawn_subagent`, and also requires
`child_session_id`. The caller cannot pass or change the role or model. The role and model must match those at child session creation; each round must
reauthorize by exact Skill ID through the parent PermissionGate, and old authorizations do not carry over automatically. Continuation is possible only when the previous round's outcome is `completed` and
the parent side has claimed the result; failed, timed-out, cancelled, interrupted, active, or unclaimed sessions are all refused.

Continuation calls go through the background start gate. One parent model reply can contain one or more `spawn_subagent` / `followup_subagent`,
but cannot mix in queries or ordinary tools. The parent Runtime commits each start confirmation in call order; with `/save` on, only after all confirmations and
the whole-turn schema 4 `tool_boundary` are committed atomically and successfully are the turn's workers released. Any commit failure starts no worker of the turn.
Status queries do not return bodies, and results are still claimed through `get_subagent_result(child_session_id)`; results for the same ID carry
`round_index`, and each round has its own `delegation_id`, `result_id`, and usage. Repeated claims stay idempotent.

The first version allows at most 4 rounds (including the initial round), and each child session accumulates at most 16 LLM calls, 48 tool calls, 64,000 tokens, and
240 seconds. Each round keeps following the existing `SubagentBudget`; the parent task's aggregate budget and concurrency limit apply as usual. Continuation does not increase
`created_subagents`, but reserves this round's LLM, tool, and token budget. After any cumulative session limit is reached, delivered results are still readable,
and the next round's request is refused before the child LLM request is sent.

Safe points use session `schema_version=4`, putting the parent State, Context, tool boundary, and at most three idle child snapshots into the same
atomic JSON file. Snapshots contain only the bounded child Context, read-only observation facts, parent task/workspace identity, frozen role and model source summaries,
Skill file identity, cumulative usage, and the ID/hash of the most recently claimed result; the parent State and Trace save only lifecycle metadata,
not child history bodies. Active workers and pending results still block safe points; the limit per snapshot is 256 KiB, and the limit for all snapshots together
is 720 KiB. When generating a single snapshot fails, the completed report is still delivered and actual usage settled, and that child session loses continuation eligibility; when the total exceeds the limit, saving reports the related child IDs. History or identity fields are not truncated. In-process followups also recheck the frozen Skill file identity before the child LLM request.

`/resume` restores only the idle snapshots in the safe point. The Runtime rebinds the provider, role, and Skill Catalog from the current local configuration,
and checks the frozen source fingerprints and Skill file identity; incompatible child sessions are marked as not resumable with the reason shown, and the parent session and other valid child sessions
can still be restored. Recovery does not replace models, continue old workers, or replay old requests. Schema 1/2/3 can still be read; these old formats have no child session
snapshots, so they cannot provide the cross-process continuation of v0.49.

## v0.48 In-Process Background Subagents

The synchronous `delegate_task` waits for the subagent to finish and then hands one result back to the parent model. Background tasks solve another case:
after the parent Agent starts a read-only investigation, it can first handle its own model rounds and tool calls, and then query and claim the result later.
`child_session_id` is a UUID within the current parent task; it represents a background task only in this CLI process and cannot continue
the same child Context in a new process.

A background start requires an explicitly selected named `agent_profile`, with `purpose` fixed to `investigation`.
It can start only when the parent task is in the `direct`, `exploring`, or `executing` phase; waiting for plan approval, diagnosis, crash investigation,
independent verification, terminal states, and unsettled crash recovery cannot start background investigations. Diagnosis and crash investigation still use
the synchronous `delegate_task` and keep referencing the current failure or recovery issue.

The four parent-side tools and their duties are below. They still pass through the Registry, ToolExecutor, PermissionGate, task phase gates, and the schema 3
tool boundary; the tools' investigation bodies are not automatically inserted into the parent history.

| Tool | Purpose |
|---|---|
| `spawn_subagent` | Starts a named read-only investigation with the `delegate_task` contract and returns a unique start confirmation: child ID, delegation ID, role, acceptance status, and budget summary |
| `get_subagent_status` | Queries bounded states such as `queued`, `running`, `result_ready`, `claimed`, `cancelled`, `interrupted` and the `result_id`, without returning the investigation body |
| `get_subagent_result` | Returns the `SubagentResult` after the child task finishes; before that it returns only the state, and repeated claims still return the same result ID and body |
| `cancel_subagent` | Sends a cooperative cancellation request and returns the current state; the final result is still claimed through `get_subagent_result` |

If one parent model reply contains start calls, it can contain only one or more `spawn_subagent` and cannot mix in other tools. The parent Runtime
admits, records, and feeds back each start confirmation in model call order; with `/save` on, it first commits the handler admission and the per-call results.
Only after the whole-turn tool boundary is committed successfully are the turn's workers started. So even if the whole-turn commit fails, no subagent runs early.
The parent Agent can then request the next model round without waiting for running read-only investigations.

Workers only run the child Runtime and hand bounded results to a thread-safe queue. The parent thread collects completed items at Runtime safe boundaries, updates
State, settles actual usage, and shows notifications that contain only IDs and states; the full result enters the matching ordinary
`role=tool` result only when explicitly claimed. Notifications are not verification evidence, and subagent findings and evidence do not enter the parent
`verification_evidence`. While the CLI waits for user input, input is read by a separate thread, and the CLI main thread keeps collecting completion events,
showing notifications, and starting the next queued child task.

Synchronous and background subagents share the same aggregate budget and concurrency limits: by default at most 3 subagents, 2 running at the same time, and the parent task can set
a smaller concurrency limit. Queued tasks reserve the total subagent count and request quota; only running workers occupy concurrency slots. Completion, failure,
timeout, and cancellation are all settled once under the same child result identity; usage cannot be reset by repeated claims, recovery, or switching to new IDs.

Active background tasks and unclaimed results both block the parent task from entering `done` or saving an ordinary safe point. Manual `/save` lists
the active IDs and refuses; automatic safe point saving is deferred and does not interrupt the parent Agent. `/new`, `/reset`, EOF, `exit`, and abnormal exit
first request cancellation and wait within bounds; if threads still have not finished, the CLI keeps the old task and reports the unfinished IDs. If a task finished but its result was not claimed,
an `abandoned` fact is recorded temporarily before `clean` is committed safely; if saving fails, the fact is revoked and the in-memory result kept, and the body is released only after the commit succeeds.

Crash recovery does not start old workers. A complete start turn leaves an active, committed tool boundary in schema 3; if the result was not safely claimed when the process
exited, recovery derives a new session, marks the background task as `interrupted`, clears the unknown result identity, settles usage conservatively at
the kept budget limit, and adds recovery issues for the user to `/resolve` one by one. If the start result was committed but the whole turn containing
it was not yet committed, the worker never started, and recovery closes that unstarted reservation without forging an executed result. Result claims
are saved as ordinary parent tool calls, with a check that `child_session_id`, the contract identity, the result ID, and the hash match State.

The ScopeGate opens files segment by segment from the workspace root using directory fds that do not follow symlinks; reads, listings, and searches are all based on the actually opened
fd, instead of reopening by path after the path check. Besides common session-sensitive directories, it also excludes the current real
`SessionStore.root`; root directory identity changes, symlinks, or out-of-bounds paths refuse reads.

In the v0.48 baseline, background tasks support only running and querying within the current CLI process; the parent Agent cannot treat child results as authoritative verification.
The v0.49 section adds restricted followup and cross-process safe-point recovery for child sessions whose successful results were claimed, but does not restore active workers.

## v0.42 Named Local References

References are document directories outside the workspace that the user registers in local configuration. They are discovered and read by the parent Agent only through stable aliases,
do not automatically enter Context, Memory, Plan, or verification evidence,
and are not provided to Subagents. Their content is untrusted and cannot override system/project instructions,
the PermissionGate, or user requirements.

### Configuration

The default configuration is an empty list and does not affect users who have not configured it:

```python
# src/mini_agent/config_local.py (untracked)
REFERENCES = [
    {
        "alias": "python-docs",
        "path": "/absolute/or/relative/path",
        "description": "Local Python design material",
    },
]
```

A relative `path` is based on the directory of `src/mini_agent/config_local.py`. When the parent Runtime is created, it
runs `expanduser`, makes the path absolute, and applies `realpath`, freezing the real directory; configuration changes do not affect an already created
catalog. An alias must start with a lowercase letter, contain only lowercase letters, digits, `_`, and `-`, and be at most 64
characters; duplicate aliases, missing fields, missing directories, and non-directory paths prevent the parent Runtime from starting. A description
is at most 240 characters, and at most 32 directories can be registered.

### Tools and return values

The parent side has three read-only tools: successful results are bounded JSON; when path, file, or search access fails, the
Executor records it uniformly as a tool failure, and error JSON is no longer treated as a successful result:

| Tool | Arguments and defaults | Key facts returned |
|---|---|---|
| `list_references()` | No arguments | `alias`, `description`; does not return the real root path |
| `search_reference(alias, query, path=".", include="*", limit=20)` | Case-insensitive literal search within one alias; `limit` at most 100 | Alias-relative file path, line number, line snippet, file SHA-256, `total_matches`, `returned_matches`, `scan_truncated`, `truncated` |
| `read_reference(alias, path, offset=0, limit=200)` | Selects a line slice by 0-based offset; limit at most 200 | Numbered UTF-8 lines, actual `returned_lines`, consistent start and end lines, `omitted_lines`, total lines, file SHA-256, `truncated` |

A single file is read up to 1 MiB; a search visits at most 2,000 files and 10,000 directory entries and reads 64 MiB
of body, keeping 100 matches. Results also report the actual `scanned_files`, `visited_entries`, and
`scanned_bytes`. When the search resource budget is reached, `scan_truncated=true` is set; when result items are removed only because of the match/display JSON
limit, `truncated=true` is set; the two are not confused. Files and directories are sorted by alias-relative path,
and if a file changes after a search, later reads recompute the digest from the new content.

### Permissions, sensitive paths, and recovery

`list_references` defaults to `allow`. `search_reference` and `read_reference` default to `ask`,
and the permission pattern is the exact `alias:relative_path`, for example `python-docs:guide`; `always` remembers only
this one pattern and does not automatically authorize the whole subtree. The query or the read
offset/limit is used only in the prompt and never becomes the real root path. Registering an alias does not automatically approve reads, and permission refusal
happens before the handler.

Absolute paths, empty paths, `.` file reads, `..`, NUL, out-of-bounds symlinks, directory symlink traversal, directories,
device files, non-UTF-8 files, and oversized files are all refused. A target named `config_local.py`, and a Reference root inside the
MemoryStore root or the default `~/.mini_agent/sessions`, refuse to start; when a broader
Reference root contains sensitive subdirectories, recursive search skips that subtree and explicit reads report an error. Errors do not show the real root.

The roots of References are kept only in the in-process `ReferenceCatalog`. The full body can enter the Context with ordinary tool history
and follows the existing `/save` session behavior; the State/Trace `output_excerpt` keeps only
the alias, relative path, line numbers, counts, SHA-256, and truncation status, not the body or the real root. Path and file errors
are raised by the handler and then recorded by the Executor as `outcome="failed"`, `error_kind="reference_access_error"`.
On recovery, the registry
reassembles the catalog from the current local configuration and does not trust the old configuration in the session. References can be used as ordinary read-only investigation in crash
recovery but cannot prove workspace drift; only
`run_shell(purpose="verification")` can produce verification evidence.

## v0.41 Relevant Memory Retrieval

v0.41 adds two read-only paths on top of the v0.40 Memory files. The parent Agent can explicitly call `search_memories(query, limit=5)`, which returns at most 5 entries by default and allows at most 10; the explicit tool refuses a whitespace-only `query`, while the underlying retrieval API interprets an empty query as an empty set and does not degrade into listing all memories. Results contain `memory_id`, title, a snippet of up to 240 characters, source, update time, score, and `matched_fields`, and are always marked `source_status="unverified"`. The source string is not accessed as a path and is not claimed as current file evidence; when the body is needed, call `read_memory(memory_id)`.

By default, before each LLM request, the parent Runtime retrieves again using `AgentState.task` and the latest `role=user` text in history. Candidates are at most 4 and the material area at most 2400 characters, weighted by lexical matches in title, tags, source, and body and sorted stably; low-ranked candidates are dropped as whole entries. Candidates exist only in the temporary system material area of this prepared Context, are explicitly marked untrusted, and do not enter history, State, Plan, Trace, verification evidence, or session. Subagents have neither Memory tools nor automatic candidates.

Automatic retrieval is on by default. When copying `config_example.py`, you can set in the uncommitted `config_local.py`:

```python
MEMORY_RETRIEVAL_ENABLED = False
```

When off, Memory files are not read and no material area is generated; when `ContextManager` has no bound retriever, it also keeps the old message shape. Each message preparation rereads the snapshot, so memories another process just committed or revised take effect on the next LLM request.

A missing Memory file means an empty set; if the file is corrupted, the schema is unknown, or reading fails, the current Context adds a bounded "memory retrieval unavailable" notice and retries on the next request. The error does not bubble up as a top-level LLM exception and does not change Memory, State, history, or session. Retrieval candidates do not bypass the PermissionGate, Plan, or verification boundaries.

## v0.40 Lightweight Durable Memory

Memory is a long-term material collection isolated by the normalized workspace, separate from the current task's `AgentState`, Plan, verification evidence, and `/save` session. It is not extracted from conversations automatically and is not automatically injected into each model request; the parent Agent must call the tools explicitly. `source` is only a source note provided by the user or Agent and does not mean the content has been independently verified.

The parent side provides five tools: `list_memories(limit=20, offset=0)` returns only ID, revision, title, tags, source, and time, plus `total` and `next_offset`; only `read_memory(memory_id)` returns a single body; `remember(title, body, tags, source)` creates; `revise_memory(memory_id, expected_revision, title, body, tags, source)` revises; `forget_memory(memory_id, expected_revision)` forgets. Viewing defaults to `allow`, and the three change tools default to `ask`; the authorization prompt shows the proposed content bounded by schema limits, the target ID, and the revision, and keeps supporting `once/always/reject`.

The default storage root is `~/.mini_agent/memory`, and `MEMORY_DIR` can be set in the uncommitted `config_local.py`. `MEMORY_DIR` is validated by real path and cannot be inside the current workspace or point to the workspace through a symlink; this way the subagent's read-only workspace tools cannot bypass the Memory tool boundary to read bodies. Custom directories outside the workspace keep working. The SHA-256 of each normalized workspace real path is used as the file name, and the JSON uses `schema_version=1`. A single workspace has at most 256 entries; the limits for title, body, tags, and source are 120, 2000, 8×32, and 240 characters, and the whole JSON is at most 1 MiB. Directory permissions are `0700` and file permissions `0600`; a missing file means an empty set, and a corrupted file or unknown schema only reports an error without overwriting.

The change flow runs "reread → validate → change → write and sync a temporary file → atomic replace → directory sync" under a workspace-specific lock. The lock waits at most 2 seconds and does not automatically take over stale locks. If the replacement happened but the directory sync failed, the tool returns a separate `memory_commit_uncertain`, and State classifies it as a failure with an uncertain result that cannot be retried directly; later memory writes in the current process stop, but read-only viewing can still be used for checking. Tool results, State, and recovery notices all state that the file may already have been replaced and that it cannot be asserted as not written. An `expected_revision` conflict does not write to disk.

Memory change tools are still `effect_class=possible`, so they reserve a generation, invalidate old verification, and are bound by the read-only planning and crash recovery gates. With `/save` on, the related tool calls, like other calls, first commit `handler_admitted`, then commit State, the matching `role=tool`, and the boundary; if the Memory file was written but the parent result was not committed, recovery does not replay the handler but marks the call as an uncertain fact. Memory files do not take part in session rollback.

Memory is not added to the fixed subagent allowlist; subagents can still use only `calculate`, `read_file`, `list_dir`, and `grep`. State summaries and ordinary terminal output do not expand bodies, but tool arguments still belong to the current model history; with `/save` on, a single memory body may enter the session with the Context. So this version only avoids copying the whole Memory snapshot and does not promise that the session never contains any memory body. References belong to v0.42.

### v0.40 configuration

```python
MEMORY_DIR = "~/.mini_agent/memory"
```

## v0.39 Durable Delegation Delivery

The v0.38 scheduler allows subagents to finish out of order, but before being written into the parent Context the results exist only in the current process. If the parent process exits in this window, the subagent may already have used model quota while the parent Agent lacks enough facts to rebuild the same `role=tool` result. v0.39 separates these two moments explicitly: after the result contract validation passes, the result is first saved as `result_ready`, then delivered in model call order.

With `/save` on, the schema 3 `tool_boundary` can contain bounded `pending_delegation_results`. Each record saves the `invocation_id`, `delegation_id`, result ID, normalized raw result, summary, and hash; the raw text is counted in UTF-8, and both single records and the total area have limits. It covers only `delegate_task` calls not yet committed and does not save the subagent's full Context, history, hidden prompts, or credentials.

The parent-side commit order is: first save the delegation contract, the quota reservation, and the `created/running` state; after the child result finishes, validate it and save `result_ready`; when that parent call's turn comes, put the parent attempt, the `committed` lifecycle in State, the matching `role=tool`, and the result reference in the boundary into the same atomic session commit. While earlier calls are still running, later results can become `result_ready` first, but are not delivered ahead of the parent model call order.

When recovering an active pending boundary, existing results that pass hash, call identity, State status, and order checks are delivered directly in parent order in the derived session, without calling the child LLM again. Records in `created/running` with no durable result become `interrupted`: no child result ID/hash is generated, and they are not marked `committed`; the matching parent tool call still gets an uncertain result and an issue for the user to handle from v0.33. Actual child usage is unknown, and the aggregate budget is occupied conservatively at the original reservation limit; it is not reset by deriving a new session and is not shown as confirmed actual child usage.

Trace and Structured State show only parent calls, contract summaries, lifecycle, usage, and result references, and do not read child history or raw pending results. The workspace and project instructions are still rechecked on recovery; old results can only be investigation material for the parent Agent and cannot widen new delegation permissions or replace parent verification.

## v0.38 Bounded Parallel Subagents

v0.38 allows the parent model to submit several independent `delegate_task` calls in one assistant turn. Subagents are still synchronously created, depth=1, read-only instances, but `DelegationScheduler` runs reserved contracts with a fixed `MAX_CONCURRENCY`. With three calls A, B, C and a concurrency limit of 2, A/B run first, and C can start after B finishes; the completion order can be out of order, but parent `role=tool` results and the durable boundary are still committed strictly in the order A, B, C.

The parent task aggregate budget is reserved in batch in model order before subagents start, and settled by actual usage after results are produced. Reserved quota and run slots are separate: queued `created` contracts occupy the total subagent count and request quota, but only running workers occupy concurrency slots. The default limits are 3 subagents, concurrency 2, 24 LLM calls, 72 read-only tool calls, and 96,000 tokens. The model can request a smaller per-call quota in `delegate_task.budget` but cannot enlarge the parent ledger; when provider usage is missing, the conservative estimate is used with its source marked, and when actual usage exceeds the reservation, it is recorded as is and later delegations are blocked.

Each worker uses its own State, Context, model binding, connection, stream parse buffer, budget counters, and cancellation event, sharing only immutable tool definitions and a read-only project instructions snapshot. One subagent failing, timing out, or being cancelled does not cancel other tasks in the same batch; when the parent task as a whole is cancelled, the Manager broadcasts to all active and pending tasks. `/new`, `/reset`, EOF, `exit`, and abnormal exit first request cancellation, then wait within bounds; if tasks still have not finished, the CLI keeps the old task and reports all unfinished `subagent_id`s.

When the user interrupts a subagent call, the Runtime first commits each completed or cancelled parent tool result, then stops the parent loop; it does not keep requesting the parent model. If a subagent's context compaction needs an extra model summary request, it must also first check the remaining calls, tokens, and time, and limit the summary output; when the budget is insufficient, it falls back to trimming and ends the child task.

Active or `result_ready` delegations block the parent task from entering `done` and also block safe points. v0.39 added bounded raw-text saving for `result_ready`; old v0.38 sessions without this raw text still hand admitted calls to issues by v0.33 rules and do not rerun subagents automatically.

### v0.38 configuration

```python
MAX_SUBAGENTS = 3
MAX_CONCURRENCY = 2
MAX_TOTAL_LLM_CALLS = 24
MAX_TOTAL_TOOL_CALLS = 72
MAX_TOTAL_TOKENS = 96_000
```

`MAX_CONCURRENCY` must be a positive integer not greater than `MAX_SUBAGENTS`. These values can be overridden by local configuration; the core runtime still uses only standard library threads and locks.

## v0.36 Multiple Providers and Unified Protocol Adaptation

v0.36 separates "model service configuration" and "protocol conversion" from the Agent Runtime. `provider` is a service configuration identity, `protocol` is the request/response format, and `model profile` is a local alias the model is allowed to use. The parent Agent and Subagents each freeze a `ModelBinding` before starting, so they can use different providers/models but still enter the same `AgentRuntime.run()`.

### Configuration format

It is recommended to override the mappings below in the untracked `src/mini_agent/config_local.py`; the repository's `config_example.py` has only placeholder values:

```python
PROVIDERS = {
    "openai-gateway": {
        "protocol": "openai_chat",
        "endpoint": "https://gateway.example.invalid/v1/chat/completions",
        "api_key": "sk-PLACEHOLDER",
    },
    "anthropic-gateway": {
        "protocol": "anthropic_messages",
        "endpoint": "https://gateway.example.invalid/v1/messages",
        "api_key": "key-PLACEHOLDER",
    },
}
MODEL_PROFILES = {
    "parent-default": {
        "provider_id": "openai-gateway",
        "model_id": "model-PLACEHOLDER",
        "context_window": 128000,
        "max_output_tokens": 8192,
    },
    "child-anthropic": {
        "provider_id": "anthropic-gateway",
        "model_id": "model-PLACEHOLDER",
        "context_window": 200000,
        "max_output_tokens": 4096,
    },
}
PARENT_MODEL_PROFILE = "parent-default"
SUBAGENT_MODEL_PROFILE = "child-anthropic"
SUBAGENT_ALLOWED_MODEL_PROFILES = ("child-anthropic",)
```

`openai_chat` uses the full `/chat/completions` endpoint, and `anthropic_messages` uses the full `/v1/messages` endpoint. Both mappings must be defined together; defining only half fails at startup. The model can request approved aliases only through `delegate_task(model_profile="child-anthropic")` and cannot pass endpoints, keys, real model IDs, or auth headers. The selection order is an explicit and approved profile, the child default profile, then the parent profile; unknown or unauthorized aliases do not fall back.

When only the old `BASE_URL`, `API_KEY`, and `MODEL` are configured, the program generates a `legacy-default` provider/profile and appends `/chat/completions` to the OpenAI-compatible base URL. New and old configuration cannot be partly mixed. Real values must not be committed to the repository.

### Protocols, requests, and usage

The first supported protocols are OpenAI-compatible Chat Completions and Anthropic Messages. OpenAI uses Bearer auth and tool schemas; Anthropic uses `x-api-key`, `anthropic-version`, a top-level system, and `tool_use` and `tool_result` blocks. Both protocols are normalized into internal assistant messages and `role=tool` results matched by call ID; the Runtime, tool execution, and completion decision do not read provider-native fields.

All requests keep using the standard library `http.client`, with a separate connection per request, and send `Accept-Encoding: identity`. Adapters do not retry automatically, run tools, change State, decide completion, or do cross-provider fallback. When streaming tool arguments are not closed, the stream breaks before the end marker, or a provider error is received, the response is refused and does not enter the executor.

`ProviderUsage.source` is `provider`, `estimated`, or `mixed`. When the service provides complete usage, it is preferred; missing fields are filled by conservative token estimates. Context summaries also use the current parent/child binding and count toward the same `UsageMeter`, and do not become free calls. The parent and child Context windows and output reserves each come from their own profile.

### Redaction and recovery

State, Context, session, Trace, tool results, and user-visible errors save at most the profile, provider ID, protocol, and fingerprint; they do not save the API key, real endpoint, auth headers, or real model ID. The fingerprint is generated only from non-auth configuration and does not contain the API key or extra request headers, so rotating credentials does not change it. Sessions created by v0.36 with model binding records reload the local catalog on recovery and compare the parent binding; missing configuration or a changed fingerprint is reported as a problem, historical requests are not resent, and profiles are not switched automatically. Old sessions have no model binding records, so the original model source cannot be checked, and the user must check the local configuration before recovery.

v0.36 is the provider baseline of v0.37: it still has only one synchronous, depth=1, read-only Subagent, but none of that lesson's new parent aggregate budget, background cancellation, and lifecycle records. Only v0.38 introduces several subagents in parallel, and only v0.39 handles cross-process delegation result delivery.

## v0.35 Shared Parent/Child Run Loop

The parent Agent and read-only Subagents now both drive the loop "request LLM → normalize tool calls → run or refuse tools → feed back results in model order → decide completion" through the same `AgentRuntime.run()`. The parent side uses `ParentRuntimePolicy` to keep managing Plan, Repair, processes, session, verification, and completion reminders; the child side uses `SubagentRuntimePolicy` to manage the fixed budget, scope observation, the result contract, and one format correction. Policies cannot request the LLM or enter handlers.

This convergence does not change the external delegation capability of v0.34: only one depth=1 subagent can still be created synchronously, the subagent can use only `calculate`, `read_file`, `list_dir`, and `grep`, and the parent Agent still exclusively owns changes, permissions, the main plan, generation, authoritative verification, and the completion decision. Illegal tool calls also get a unique normalized ID and a matching `role=tool` result; durable turns must still commit `handler_admitted` first, and the next LLM request is not made before the whole turn is committed.

## v0.34 Minimal Controlled Subagent Delegation

The parent Agent can synchronously delegate one single-level read-only investigation through `delegate_task`. The subagent has its own State, Context, loop, project prompt, and fixed PermissionGate; it sees only `calculate`, `read_file`, `list_dir`, and `grep`, and cannot write files, run shell, operate processes, call plan/recovery/verification tools, or delegate again. The parent Agent still exclusively owns workspace changes, the main Plan, permissions, generation, authoritative verification, and the completion decision.

The tool arguments are: `goal` (required string), `scope` (1–8 workspace-relative paths), `constraints`, `expected_findings`, `requested_tools` (non-empty and only the four read-only tools), `selected_parent_facts`, `purpose` (`investigation` / `diagnosis` / `crash_investigation`); diagnosis or crash investigation must also carry the correct `source_id`; the optional `budget` contains `max_rounds`, `max_llm_calls`, `max_tool_calls`, `max_tokens`, `max_result_bytes`, and `timeout_seconds`.

The scope refuses absolute paths, `..`, `config_local.py`, symlink escapes, and paths outside the workspace; each child file tool call checks again. Selected facts must not contain obvious API key, Authorization, Bearer, token, secret, or password content. Delegation is refused when the parent task is in `awaiting_approval`, `verification_required`, `blocked`, or `failed`; diagnosis and crash investigation must reference the current active fact exactly.

The fixed guardrails of v0.34 are 8 rounds, 8 LLM calls, 24 tool calls, 32,000 conservatively estimated tokens, 12 KiB of final JSON, and 120 seconds of wall-clock time. Exceeding them returns `budget_exhausted`; timeouts are checked only at sync boundaries and do not forcibly interrupt HTTP requests already sent. Subagent failures, timeouts, or budget exhaustion also return a structured tool result and do not automatically create a parent FailureEvent.

The subagent is finally allowed to output only the report body below:

```json
{"summary":"...","findings":[],"evidence":[],"limitations":[]}
```

The Runtime adds the UUID, parent and child IDs, `outcome`, usage, timestamps, and the contract hash, and validates that evidence IDs are unique, finding references are not dangling, paths are within scope, line numbers are positive, tool names are legal, and observation hashes are SHA-256. An illegal report gets only one protected format correction; another illegal report or another tool call in the correction phase returns `failed/invalid_result`. Child evidence is not written into the parent `verification_evidence` and can only be investigation input for the parent Agent.

v0.34 allows only one `delegate_task` per parent tool turn; after the synchronous wait, the parent Context receives only one `role=tool` JSON result committed in model order. Multi-subagent parallelism, background cancellation, the parent task aggregate budget, persisted DelegationRecords, and cross-session recovery are not implemented; `/new`, `/reset`, and exit continue only after the current synchronous handler returns.

## v0.33 Session Persistence, Crash Recovery, and Safe Handoff

### Turn on, update, and turn off sessions

`/save` is an explicit choice to write to local disk. It can be used only when there is an active task: the first call creates a random `session_id` and shows the ID, and later calls update the same file. Once on, when a complete agent turn returns to the CLI or a state decision such as plan approval completes, the Runtime automatically saves an `active` safe point; a save failure before replacement does not overwrite the old file and does not show "saved". When the file has been replaced but the final sync or lock cleanup fails, the CLI separately reports that the commit status is unconfirmed, with the session ID, and it cannot be asserted from this that the disk still has the old version or that the new version is persisted.

```text
/save
Session saved: <session_id>
```

`/new <task>`, `/reset`, EOF, `exit`, and normal finish first run the existing bounded background process cleanup and then write the old session as `clean`. Cleanup failure, an in-flight stdin write, still active processes, unsettled attempts, or abnormal exit do not commit `clean`; the CLI keeps the old task or reports the specific reason. After a task switch, the old session identity is not carried to the new task automatically, and the new task needs `/save` again.

### File location, format, and privacy boundaries

By default, files are in the current user's `~/.mini_agent/sessions/`; the directory allows access only by the current user, and each session is one JSON file of at most 16 MiB. Writes use a temporary file in the same directory, file `fsync`, and `os.replace`, and a same-name exclusive lock file refuses concurrent writes; stale locks are not taken over automatically. Newly written envelopes use `schema_version=4`, containing `session_id`, package version, normalized workspace root, save time, saved generation, `active/clean`, State, Context, workspace manifest, `tool_boundary`, idle `child_sessions` snapshots, and a SHA-256 integrity value covering the other fields. Schema 1 can still be read for diagnosis, clean safe points of schema 2/3 can still be resumed, and they are upgraded to schema 4 when claimed for resume.

State exports the authoritative plan, execution, failure, recovery, generation, private budget counters, raw recovery arguments, and checkpoint **metadata**; it does not write locks, `ProcessManager`, `Popen`, threads, or checkpoint pre-image bytes. Context exports the ordinary task history, summaries, compaction markers, summary round count, and pending Runtime Notices, but not the protected system prompt. Assistant tool calls must pair one to one with ordered `role=tool` results.

Sessions may contain ordinary conversation, file content, and tool output, and should be treated as local sensitive data. The assistant arguments of `write_process` keep a valid JSON shape and the `tool_call_id`, but `function.arguments.input` is replaced with an explicit redaction placeholder. If the non-empty body also appears in ordinary history text, summaries, or Runtime Notices, this save is refused, instead of writing the body to the file or blindly replacing other text; empty input that sends EOF does not rewrite summaries. Generic history text is not broadly claimed to be "free of sensitive information"; API keys, `BASE_URL`, `MODEL`, and `config_local.py` are not read or serialized by SessionStore.

### Read validation and fault diagnosis

SessionStore provides reading, size checks, schema checks, field/reference checks, tool result pairing checks, and SHA-256 validation. Request a resume with the command below:

```bash
PYTHONPATH=src python -m mini_agent --resume <session_id>
```

Resume accepts only complete committed sessions in schema 2/3/4 with `schema_version`, `save_kind=safe_point`, `handoff_status=clean`, and a workspace manifest that still matches. The CLI first builds a new State, Context, tool registry, ProcessManager, and PermissionGate, then rechecks the original commit and workspace manifest inside the session exclusive lock, and rewrites the session as a schema 4 `active` version of the successor generation; idle child sessions in schema 4 also have their identity rechecked against the current local roles, models, and Skill Catalog. After a successful commit, it shows the original task state and waits for input, without automatically requesting the LLM. Workspace changes, paths that cannot be fully checked, `active` sessions, pending tool boundaries, corrupted files, and lock contention are all refused before calling the LLM or tools. Only a normal exit after resume writes `clean` again; an abnormal exit leaves `active`, which cannot be resumed directly again.

Schema 1 sessions of v0.30 can still be read for diagnosis but cannot continue running. Old verification eligibility is cleared on resume, and `verification_history` is used only for audit and Trace replay; the resumed task needs independent verification. Old PIDs, old `process_id`s, and old `ready` checkpoints without pre-image bytes keep only audit records and cannot control processes or run rollback.

- `session file does not exist`: check `~/.mini_agent/sessions/` and the shown `session_id`; do not hand-build other paths.
- `schema 1 session is for diagnosis only`: use the current code to complete a new `/save` and a normal clean handoff, then use `--resume`.
- `workspace check failed`: restore the files and directories the task touched before resuming; the manifest is built from structured file arguments, `files_changed`, failure, and checkpoint records, and recursive `grep` covers unmatched files within the search scope. When task paths contain symlinks or the search scope exceeds limits, it is kept for diagnosis only; shell command text is not guessed as paths or side effects.
- `only clean sessions can be resumed`: an active session may correspond to an uncertain window after process cleanup or abnormal exit; keep it for diagnosis first.
- `session SHA-256 validation failed`, `JSON` or reference errors: the file may be corrupted or edited by hand; keep the original file for diagnosis, and do not treat it as a task that can continue.
- `session file exceeds the limit`: history or tool output is too large; keep the old commit first, and do not delete or truncate half a tool turn.
- `session is locked by another writer`: another CLI may be writing, or there is a stale lock that needs manual checking; the Runtime does not take the lock automatically.
- `session save failed`: if the failure happened before replacement, the previous file stays unchanged; the CLI does not forge a success message. If cleanup failed, first handle the `process_id`, PID, or stdin reason in the report.
- `session commit status unconfirmed`: the file may already have been replaced with new content, but the directory sync or lock cleanup did not complete; use the shown session ID to check the disk file and the exclusive lock, and do not assume the old commit is still there.

## v0.30 Session Persistence and Safe Points

v0.30 introduces `/save`, local schema 1 sessions, redacted history, atomic safe points, and the `active/clean` lifecycle. v0.31 adds schema 2 and the workspace manifest; v0.32 adds the schema 3 durable tool boundary; v0.33 builds crash recovery handoff on the active pending boundary. Clean safe points still resume through the original flow, while pending half turns derive a new session, without overwriting the source file or automatically completing handlers.

### The two branches of `--resume`

```bash
PYTHONPATH=src python -m mini_agent --resume <session_id>
```

- `clean + safe_point`: check the workspace manifest, claim the original session, create a new resume generation, and wait for user input.
- `active + schema 3/4 + pending tool_boundary`: show the source session, the derived session, workspace changes, and issue categories; after the claim, run only on the new session.
- Schema 1, schema 2 active, sessions without pending evidence, or corrupted sessions: refused before entering the runtime, without calling the LLM, handlers, or the PermissionGate.

Crash recovery uses a private `crash_recovery_claims.json` sidecar, in the same location as the session directory. It saves only the source session ID, the source integrity digest, the derived ID, the recovery ID, and the `preparing/committed` phase, not raw tool arguments, shell commands, stdin, or model configuration. It first commits the `preparing` intent, then writes and validates the derived session, and finally commits `committed`; a failure in the middle can be retried with the same derived ID. When the durability of the sidecar or derived session is unconfirmed, no runnable object is returned to the CLI; a repeated claim of the same already `committed` source integrity reports the existing derived session.

### `/resolve`

Each issue in the recovery report must be handled one by one, and only one issue is accepted at a time:

```text
/resolve <issue_id> investigate <required feedback>
/resolve <issue_id> continue <required feedback>
/resolve <issue_id> block <required feedback>
```

`investigate` only records the user decision and allows read-only investigation; `continue` requires that this recovery generation already has a successful, approved investigation attempt with `effect_class=none`; `block` ends the task immediately and keeps the other issues. After all issues are `continue`, a `crash_recovery` replan trigger is created, and the plan must be resubmitted or reviewed, then reauthorized and independently verified. While unsettled issues exist, side-effect tools, verification, plan submission, ordinary input, and completion are all refused.

Workspace changes cannot prove that a handler ran or did not run, but they create a `workspace-drift` issue that must be investigated and settled by the user; the prepare and claim phases compare structured summaries of path, type, availability, directory members, and content hash. Admitted calls are not replayed: `effect_class=none` is recorded as `uncertain_state_or_result`, and calls that may have side effects are recorded as `uncertain_side_effect`; only calls that did not enter the handler get an explicit not-executed result of `interrupted_before_handler`. Old PIDs, process IDs, and stdin writer threads are not inherited across processes; possibly leftover processes are kept as `orphaned` facts and block task completion through a separate process issue; a user `continue` does not restore PID control.

## v0.29 Bounded Text Input for Background Processes

The `stdin_mode` of `start_process(command, cwd?, stdin_mode?)` defaults to `closed`, keeping the EOF behavior of v0.28 and earlier; only processes explicitly set to `pipe` accept `write_process(process_id, input, close_stdin?)`. Input must be UTF-8 text, at most 4096 bytes per call after encoding; empty input is allowed only with `close_stdin=true`, to send EOF alone.

Writing and closing in `write_process` share one separate permission check, `ask` by default, with effect class `possible`. The authorization prompt shows only the `process_id`, the encoded byte count, and the close flag, not the body; unknown or cross-task IDs are refused before authorization and generation reservation, and argument errors also do not enter authorization. Processes that have stdin enabled but already closed, exited early, or have an in-flight write return an explicit state after authorization and before generation reservation. Each process handles writes serially, and the dedicated thread waits at most 2 seconds; while a previous write is still in flight, `write_pending` is returned, which cannot be used to retry or be treated as written. The `written_bytes` of a successful result is the byte count after the write and flush complete; on pipe errors the field is 0, and `delivery_uncertain=true` means some bytes may have been delivered and no automatic retry is allowed. Results contain only the process ID, written byte count, `stdin_state`, `closed`, and a bounded state reason, without feeding back the body.

A successful write is not verification. Keep observing the response with `read_process` or `wait_process`; process exit, control, and `/new`, `/reset`, EOF, `exit`, or abnormal cleanup all reap writer threads and the stdin pipe within bounds. Active processes or in-flight writes both block the task from entering `done`; when cleanup cannot be confirmed, the old task registration is kept, and the process ID, PID, and reason are reported. This version supports only pipe byte streams, not PTY, terminal echo, control characters, terminal size, or interactive shell semantics.

## v0.28 Background Process Control and Task Closing

`terminate_process(process_id)` requests normal termination of a process registered for the current task; `kill_process(process_id)` forces it to end. The two tools are authorized separately, both `ask` by default, and accept only task-specific IDs, not system PIDs. Unknown, expired, or cross-task IDs return `unknown_process_id` before the permission prompt, reserving no execution attempt or generation. After approval, valid calls reserve a generation as tools that may have side effects; the limits of the read-only planning phase, plans awaiting approval, and the repair phase still apply.

Normal termination and forced kill each wait at most 2 seconds. `terminated` or `killed` means the direct child process, the managed process group, and the output pipes have all been confirmed as exited; `still_running` means exit was not confirmed this time, the process still blocks task completion, and you can keep observing or try `kill_process`. `already_exited` means it had already exited naturally at the time of the call. A control failure returns `control_failed` and produces no final process event. Windows can confirm only the direct child process and pipes, and the result notes that the process tree derived by an arbitrary shell cannot be confirmed.

The foreground sync point commits one `terminated` or `killed` event for a confirmed active exit, referencing the start attempt and the control attempt, and opens the post-exit generation. Old verification becomes invalid with it. Only after the process has exited stably, plan steps are complete, repair obligations are resolved, and `run_shell(purpose="verification")` is run independently in the new generation can the task complete. Process control cannot replace a legal `recover` or `request_replan` in the diagnosis phase.

## v0.27 Background Process Observation and Bounded Waits

The `process_id` returned by `start_process` can be used in later rounds of the same task. `get_process(process_id)` queries the state, the final exit code, and the cumulative **byte** positions of stdout/stderr, without consuming logs; `list_processes()` lists the metadata of processes registered for this task, and when the result is too long, it omits from the earliest records and reports `omitted_count`. Unknown, expired, and cross-task IDs return `unknown_process_id`, and system PIDs cannot be used to query other processes.

`read_process(process_id, max_chars?)` reads the new content of stdout and stderr separately since the last successful read. By default at most 2000 characters in total, with an argument range of 1–4000; the full JSON is at most 8000 characters. It returns `next_stdout_offset`, `next_stderr_offset`, per-stream `*_output_gap`, and `*_lost_bytes`. Positions are counted in raw bytes, and UTF-8 characters that span collected chunks are not repeated or lost; illegal bytes are shown as replacement characters. Each stream keeps only the latest 64 KiB, and when reading too late, the gap markers must be checked. Log bodies appear only in this tool result and do not enter long-term State or Trace.

`wait_process(process_id, timeout_ms?)` must own a tool turn exclusively. It waits 1000 milliseconds by default and can be set to 0–30000 milliseconds; on unread output it returns `output_available`, on confirmed exit it returns `exited`, and neither consumes logs. On timeout it returns `still_running`, and after the full tool result is fed back, the task enters `awaiting_process` and returns to the CLI; the next input first syncs process facts and then continues the original task. A timeout is not a process failure, verification evidence, or a completion state. A natural non-zero exit is recorded once as a separate `FailureEvent`, referencing the start attempt and the exit event, and enters the existing diagnosis flow; the exit also invalidates old verification from while it was running.

## v0.26 Background Process Start and Task Boundaries

Long commands make the synchronous executor wait until the command exits; development servers, file watchers, or continuous builds therefore cannot keep working within the same Agent task. v0.26 adds `start_process(command, cwd?)`: it keeps the shell string semantics of `run_shell`, but returns a task-specific `process_id` immediately after creating the process. `run_shell` keeps synchronous execution, the 30-second timeout, and the original `[exit=N]` return format.

The run state of background processes is held by the `ProcessManager` for the CLI lifetime. State saves only snapshottable `ProcessRecord`s and append-only `ProcessEvent`s: task ID, start attempt, generation, PID, state, time, exit code, cumulative stdout/stderr byte positions, and final event ID; it does not save `Popen`, pipes, threads, full logs, or input bodies. Each task has at most 4 active processes, and each output stream keeps at most 64 KiB; before v0.29, stdin connected to `DEVNULL` at start, and from v0.29 a stdin pipe is created only with an explicit `stdin_mode="pipe"`.

A successful result is bounded JSON, for example:

```json
{"process_id":"proc-1","pid":12345,"status":"running","start_attempt_id":"a-3"}
```

This only means the process has been created. A natural zero exit records `exited`, and a natural non-zero exit records `failed`, both referencing the start attempt; a synced exit invalidates the current verification and opens a new generation. The process state, start result, and buffer positions are not verification evidence; after exit, an independent `run_shell(purpose="verification")` is still needed to verify the final state.

When the model gives text without `tool_calls` while a background process is still running, the Runtime sets the task to `awaiting_process` and returns to the CLI, without judging it `done` and without using an extra LLM round. The CLI shows the task/process ID, cumulative output positions, and the remaining plan, repair, and verification obligations; the next user input first syncs exit facts, then resumes the original task.

`/new`, `/reset`, EOF, `exit`, `KeyboardInterrupt`, and abnormal exit all clean up the current task's processes before clearing State: first request normal termination and wait at most 2 seconds, then force a kill and wait at most 2 seconds; after the process end is confirmed, wait within bounds for the collector threads to read EOF on stdout/stderr before closing the pipes. Processes confirmed as exited only have their handles reaped, and no further signals are sent to the old process group ID, to avoid hurting unrelated processes after the system reuses that ID. POSIX must also confirm that the managed process group is gone; when the outer shell exits first, descendants in the same group or descendants still holding pipes keep blocking task completion and the release of active quota. Windows can confirm only the direct child process and the two pipes and cannot prove that the process tree derived by an arbitrary shell has ended; so when background processes are registered, cleanup is reported as incomplete, `/new` and `/reset` keep the old task, and the user must exit the CLI after no longer needing that task. When cleanup is incomplete, the old task and Manager registration are kept, and the PID, process ID, and reason are reported; POSIX cannot control descendants that left the process group and closed inherited pipes.

## v0.25 Plan Trace Replay and Acceptance

The `trace_events` of `AgentState.snapshot()` is a continuous read-only trace index within the task. Each event saves the `sequence_id`, the `generation_id` / `revision_id` at the time, and the type and ID of an existing record; verification uses the index of `verification_history`. Events do not copy raw tool output, do not advance the generation, do not change the budget, and do not take part in the completion decision.

These three fields have different duties: `generation` is the verification generation after environment side effects or recovery, `revision` is the plan structure version, and `sequence_id` links the order of occurrence across lists. After several revisions are committed within the same generation, the revision that investigation, execution, and verification belong to is decided by events and cannot be inferred only from the generation or array position.

The Trace API keeps the original call style and adds revision queries:

```python
from mini_agent.trace import build_trace, render_trace

report = build_trace(state.snapshot())
revision_report = build_trace(state.snapshot(), revision_id=2)
print(render_trace(revision_report))
```

`generation_id` and `revision_id` cannot be specified together; illegal IDs raise `TraceQueryError`. The full report adds `plan_revisions` and an ordered `plan_timeline`. Each revision view contains the parent, the trigger antecedent, the model-submitted `reason`, the structural diff recomputed by the Runtime, steps and progress, plan-only user decisions, and the investigation, execution, failure, recovery, verification, and generation while it was in effect. `causal_edges` adds parent, trigger, and revision-related edges and marks completeness with `resolved` / `UNRESOLVED`.

```text
/trace
/trace <generation_id>
/trace revision <revision_id>
```

A revision query keeps the trigger source of the selected revision as the antecedent; a generation query shows the revisions committed or in effect in that generation, distinguishing the two with `generation_role`. The conclusion basis of a historical generation is rebuilt from the plan and progress events at the end of that generation, without borrowing later revisions; when there is no ordered terminal record, the historical terminal summary is marked `not_recorded`. When an old snapshot has no plan data, the v0.21 result is kept; when there are plan records but no `trace_events`, directly verifiable structural facts are kept, and the cross-record order and execution attribution are marked incomplete. Trace does not rerun the task and does not infer backward from passing evidence of later generations that the old plan was correct.

## v0.24 Evidence-Driven Replanning and Stall Closing

A plan in execution cannot be silently rewritten just because the model says "needs adjustment". The model can only call `request_replan(kind, source_id, reason)` exclusively: `failure` must reference the current `active_failure_id` exactly, and `observation` must reference a successful and approved read-only `ExecutionAttempt` after the current active revision was committed. After the call passes, the task enters `exploring`, which allows only read-only investigation or an exclusive `commit_plan`; later revisions must reference the current parent revision and the active trigger.

When the Direct Path enters Explore because of a failure or blocked recovery, there may be no parent yet. In that case the first `commit_plan` must carry the active trigger and cannot provide `parent_revision_id`; the initial plan of an ordinary task still carries no trigger and no parent. Valid later revisions use the total replan budget, and the Runtime saves plan differences as `retained`, `added`, `cancelled`, and `replaced`, marking dependency changes of kept steps and changes of the goal, constraints, and success criteria. A submission with no change only increases the no-progress count of the current trigger, and the task blocks the second time the limit is reached.

By default there are at most 3 valid later revisions. The third revision can still run, and requesting a fourth enters `blocked`. A failed revision does not delete the FailureEvent, repair cycle, generation, or old verification records; submitting a new plan only means the diagnosis formed a new path, and the actual changes and independent verification of the current generation must still happen.

The model cannot recover `blocked` or `failed` on its own. The user can enter `/resume <feedback>` for a blocked task; the command records the `resume_blocked` decision and the terminal reason before recovery, then enters `running / exploring`. If the block came from `recover(ask/block)`, the Runtime keeps the independent verification requirement of the successor generation and first restores to `diagnosis_required`, so verification is still required after the new revision is submitted; other block sources follow the ordinary recovery path. If an active plan exists, the revision must reference it; without an active plan, the first submission with a trigger and no parent is used. When the budget is exhausted, the task is failed, or there is already an active recovery trigger, use `/new <task>`.

Stall detection runs after all calls of a complete tool turn are run or refused, State is updated in model order, and results are shown and all `role=tool` messages are fed back. The default is `MAX_STAGNANT_ROUNDS=3`: the second consecutive no-progress turn injects one protected Runtime Notice, and the third records `repeated_action`, `no_new_observation`, `explore_without_commit`, or `execute_without_progress` and enters blocked. It saves only actions, investigation result hashes, and short summaries, without copying full tool output; the legal next action given by the Planning gate and Repair gate takes priority over the reminder text.

New configuration in this version:

| Setting | Default | Description |
| --- | ---: | --- |
| `MAX_ATTEMPT_FINGERPRINTS` | `4` | Execution limit per tool and argument fingerprint; must be at least `MAX_STAGNANT_ROUNDS + 1`. |
| `MAX_REPLAN_REVISIONS` | `3` | Total valid later plan revisions per task. |
| `MAX_NO_PROGRESS_REPLANS` | `2` | Number of submissions with no structural change for the same active trigger. |
| `MAX_STAGNANT_ROUNDS` | `3` | Limit of consecutive no-progress complete tool turns; must be greater than 1. |

## v0.23 Read-Only Planning and User Handoff

Ordinary tasks still start from `direct`. When the model thinks a task needs planning first, it calls `begin_plan` exclusively to enter `exploring`; before a plan is submitted, `cancel_planning` returns to the Direct Path. When the command line uses `PYTHONPATH=src python -m mini_agent --plan "<task>"`, the first task starts from `plan_only / exploring`, and mandatory planning cannot be cancelled. After handling the first task, the command still enters the interactive loop.

`exploring` allows only side-effect-free investigation, an exclusive `commit_plan` call, and `cancel_planning` in ordinary mode when there is no plan yet. Shell, file writes, verification, recovery, and progress updates are refused before the PermissionGate; mixing `commit_plan` with other calls in the same turn is refused as a whole. The first submission in `--plan` also requires at least one successful, approved, executed read-only investigation record, otherwise it returns `plan_rejected`. Each refused call still has a matching tool result, but no handler runs, no generation advances, and no verification evidence is produced.

In ordinary mode, submitting a plan enters `executing`. In `--plan` mode, it stops at `awaiting_approval` after submission; the CLI prints the full pending plan and the current revision ID from `active_plan` in State, then waits for the user's decision; this is shown even with `OUTPUT_MODE=quiet`, and the model does not restate the plan or keep executing. After continued investigation, use `/review`, and the CLI prints the same plan and decision commands again. Handoff commands:

| Command | Effect |
| --- | --- |
| `/approve <revision_id>` | Approve the current pending revision and continue execution. |
| `/reject <revision_id> <feedback>` | Reject the current revision, save the feedback, and return to read-only investigation. |
| `/continue <revision_id> <feedback>` | Keep the current revision and continue read-only investigation with feedback. |
| `/review <revision_id>` | If the plan did not change after continued investigation, hand the original revision over for approval again. |

If a revision is submitted after rejection or continued investigation, `commit_plan` must provide both the current `parent_revision_id` and the `trigger_id`. User decisions, feedback trigger records, and old revisions are all saved in the current task State; `/reset` or `/new <task>` clears them. Approving an old revision, approving twice, rejecting without feedback, or `/review` directly after rejection are all refused. Plan approval only changes the planning phase and does not write PermissionGate allow rules; later tools keep being authorized separately, and independent verification is still required after changes. For replanning triggered by failures/observations, revision budgets, and stall detection, see v0.24 at the start of this manual.

## v0.22 Plan Contract

Complex tasks can submit a structured plan through `commit_plan`. The plan contains `goal`, `constraints`, task-level `success_criteria`, and 1–50 steps with stable `step_id`s; steps can declare `depends_on`, step-level `success_criteria`, and `replaces`. Simple tasks keep using the Direct Path and do not need a plan.

The first `commit_plan` of an ordinary task provides no `parent_revision_id` or trigger and creates revision 1 on success; `--plan` mode enters `awaiting_approval`. When the structure changes, an active trigger must first be created by user feedback, a failure, or an observation, and then a complete new plan with the current active revision as parent is submitted; when a Direct failure or blocked resume has no parent, the first revised plan carries only the trigger. Old revisions are not overwritten. To change only step states, use `update_plan_progress`; states can only advance `pending → in_progress → completed`, and requests are refused when dependencies are incomplete or another step is already in progress.

Plan validation and revision commit happen under the same State lock. Requests with invalid arguments or that violate plan invariants get `plan_rejected`, without creating a `FailureEvent`, entering the Repair Loop, advancing the generation, or producing verification evidence. Both plan tools default to `ALLOW` and `effect_class=none`, and cannot be retry, adjust, or rollback targets of `recover`. Plan writes do not mean the environment is correct, and step completion still cannot replace independent verification.

`AgentState.snapshot()` also provides the full `plan_revisions`, the append-only `plan_progress_history`, the currently derived `active_plan`, and `planning_state`. `current_goal`, `unfinished_todos()`, and `snapshot()["todos"]` are only read-only compatibility projections of the active plan. Structured State shows only a bounded goal, the current step, at most five ready steps, at most ten blocked steps, and a count summary; after compaction it is still rebuilt from State, and the plan is not recovered from history summaries.

The v0.21 `/trace` keeps replaying generation, execution, failure, recovery, and verification facts read-only; this version does not add the full Plan causal chain to Trace.

## v0.21 Task Trace Replay (Trace & Replay, read-only)

`/trace` replays the structured facts already saved for the current process and current task: Todo revisions, generations, execution attempts, failures, recovery actions, verification evidence, and terminal states. `/trace 3` shows only generation 3; for the plan chain and revision queries, see the v0.25 notes above. The command is intercepted before `run_task()`, appends no user history, does not call the LLM, tool handlers, or PermissionGate, and does not change State, budget, or generation.

Replay is also available through a standard library Python API:

```python
from mini_agent.trace import build_trace, render_trace

report = build_trace(state.snapshot(), generation_id=None)
print(render_trace(report))
```

When `report["integrity"]` is `complete`, the currently saved references can be fully accepted; when it is `incomplete`, `issues` explain broken chains, missing historical verification evidence, or cross-generation evidence, and the report still keeps the confirmable raw records, but missing facts must not be guessed from it. Failure diagnosis prefers an existing `cause_hint`, otherwise it shows the `reason` of the linked recovery action, and when neither exists it shows "no diagnosis recorded".

The v0.21 Trace safely degrades to empty for missing `todo_revisions`; v0.22 no longer uses Todo revisions as the plan write source, and plan history is saved instead by the `plan_revisions` and `plan_progress_history` described at the start of this section.

## v0.20 Repair Loop

Execution after a failure cannot jump directly back to ordinary writes. `AgentState.snapshot()["repair_loop"]` shows the current phase, the active failure/recovery, and the cycle budget:

| Phase | Allowed next step |
|---|---|
| `idle` | Normal investigation, execution, and plan progress |
| `diagnosis_required` | Read-only investigation, an exclusive `recover` call to handle the current `active_failure_id`, or an exclusive `request_replan` call |
| `verification_required` | The next tool turn can only be a single `run_shell(purpose="verification")` |

The agent loop checks batched calls at the turn level, and the ToolExecutor checks again before permissions and the handler; non-compliant calls get a protocol error and do not run the handler, ask for permission, or advance the generation. The recovery target carries a reservation protected by the State lock and is the only controlled execution exception in the verification phase; after the recovery result is fed back, independent verification is still required.

`MAX_REPAIR_CYCLES` defaults to 3. The initial failure, schema/argument refusals, permission refusals, and `ask`/`block` use no cycles; `retry`, `adjust`, and `rollback` count only after the target is authorized and the successor generation is activated. A verification failure re-enters `diagnosis_required` instead of directly adding a cycle; when a fourth recovery would be needed, the task closes with an explicit `failed` reason. Recovery success by itself does not mean task completion; only when verification of the current generation passes and the steps of the active Plan Contract are complete does the completion reminder disappear; without an active plan, the Direct Path verification conditions apply.

Structured State and the critical state after context compaction keep `repair_loop`, the latest failure/recovery actions, the generation, and the budget. The completion reminder states the only legal advancing action by phase; outputting only text again under the same `progress_marker` still enters the existing `blocked` protection. v0.24 also keeps the active trigger's source and reason, the remaining replan budget, the counts of `LoopStagnationState`, and the next actions the gate allows.

## v0.19 Checkpoint / Rollback

After permission is granted and the attempt/generation is reserved, `write_file` and `edit_file` save a pre-image for a single ordinary file inside the workspace. A pre-image is at most `MAX_CHECKPOINT_BYTES` (default 1 MiB), and a nonexistent file is recorded as an `absent` tombstone; symlinks, paths outside the workspace, directories/special files, invalid parent directories, and read failures only make the checkpoint `unavailable`, without changing the original file tool behavior.

File tool results and the critical Structured State keep the checkpoint ID, relative path, attempt, generation, state, and hash; these recovery metadata are kept after context compaction or degradation of oversized state. If an approved file handler raises an error but the pre- and post-images are clear, the task stays recoverable and suggests rollback; only when pre- and post-images are unavailable does it block as an unknown side effect. Internal tools cannot be retry/adjust targets, and an original mode of `0` is also restored as is.

The model requests recovery through `recover(action="rollback", checkpoint_id=...)`. `rollback_checkpoint` is an internal tool that does not appear in the LLM schema and refuses direct model calls; RecoveryRuntime uses the normalized relative path saved in the checkpoint for authorization through the same PermissionGate. Before recovery, it recomputes the current file's type and SHA-256, and if an external change is found, it refuses to write and enters `blocked`. Ordinary files are restored atomically using a temporary file in the same directory, the original mode, and `os.replace`; an absent tombstone deletes the target only when the post-image still matches.

A successful recovery only proves the recovery operation itself completed: it opens a new generation, clears old verification evidence, and requires independent verification in the next round. Checkpoint metadata is kept in Structured State, but contains no pre-image content or absolute paths; `/reset` and `/new` clear all checkpoints and private bytes of this task.

Settings:

| Setting | Default | Description |
|---|---:|---|
| `MAX_CHECKPOINT_BYTES` | `1_048_576` | Maximum bytes of a single pre-image; can be overridden in `config_local.py` |

## v0.18 Recovery Policy

`recover` supports retry, adjust, ask, and block. v0.18.1 fixed rejection records and budget boundaries: schema, reference, argument, budget, or permission refusals all record only one rejected action with a `recovery_id` and do not advance the generation. Quota is reserved under the State lock before the target permission check; only after approval are the successor generation and attempt opened. A permission refusal releases unused target execution and retry quota, but the recovery request still counts, and consecutive invalid requests reaching the recovery action limit also block. The recovery target reuses the same PermissionGate of the current session and does not ask again for the same authorization; after recovery, independent verification is required.

No match and multiple matches in `edit_file` are deterministic argument precondition failures (`error_kind=edit_no_match` / `edit_multiple_matches`); they do not change the file or enter the unknown side effect block; other exceptions after being approved into the handler still keep the possible-effect generation advanced. Structured State also shows recovery notices, the latest failure/recovery actions, and the redacted budget while `running`. After entering `blocked` or `failed`, the Executor no longer asks for permissions or runs handlers, and the remaining calls of the current batch are fed back one by one with `task_terminal` results.

## v0.17 Failure Model

Each task starts from generation 0. Tools that may have side effects (file writes, edits, and all shell commands) advance the generation atomically after permission is granted and before the handler; it does not roll back even if the handler fails. `purpose="verification"` only specifies that the command result is used as verification evidence and does not prove the shell command is read-only, so verification commands also open a new generation, and the evidence binds to that generation. The Executor produces a structured `ExecutionResult`, and State saves `ExecutionAttempt`, `FailureEvent`, and generation-bound verification evidence. Arguments are counted by the SHA-256 fingerprint of canonical JSON, and Structured State shows only the hash/redacted summary. All-read-only turns can run concurrently, and turns containing shell are committed serially in model order; verification cannot be in the same turn as other calls that may have side effects.

## v0.16 Plan-driven Execution

Complex tasks usually move forward as Plan → Execute → Observe → Verify; if observation or verification results expose problems, the model then Replans (reorders the Todo) and keeps executing. File changes and all actually executed `run_shell` calls are treated as possibly changing the environment and invalidate old verification; a `run_shell` result with `purpose="verification"` and exit code 0 is used as completion evidence, and it is suggested to make the final test or check the last verification call. The verification command itself should only check results and not take on file changes; the Runtime conservatively accounts for possible side effects but provides no general shell sandbox.

v0.16.1 fixed the completion reminder: when the model outputs interim text while the Todo is incomplete or verification is still required, the runtime injects an explicit Runtime Notice requiring the next reply to call a progress tool (update the Todo, investigate/operate, or verify), instead of only describing the next step in words. The reminder is given at most once per progress state: after the full Todo, non-Todo tool results, the verification evidence count, the generation, or `verification_required` change, it can remind again; only outputting tool-free text again under the same marker marks `blocked`. Old-style State without `progress_marker` keeps the one-reminder compatible behavior. This conservative policy does not depend on third-party libraries or command parsing.

## v0.15 Todo / Task State

The following is historical version behavior; from v0.22, `update_todo` is no longer registered as a model-visible tool, and for current plan writes see the Plan Contract at the start of this manual.

The model can call `update_todo` to submit the complete task list. States are `pending`, `in_progress`, or `completed`, with at most one item in progress; on update failure the old state is unchanged. The Todo belongs to AgentState, while Execution State (tool history, files, errors) is still maintained by the executor; each request injects it through Structured State, and it is restored after compaction. v0.15 does not plan automatically, persist, or block completion.

## v0.14 Project Instructions

At startup, the Agent reads `AGENTS.md` in order from the Git root to the current working directory and injects the content with source markers into each request as protected system context. Non-Git directories check only the current directory; the total length limit is 12,000 characters. Project instructions do not relax permissions and do not disappear through trimming or compaction.

## 1. Environment Setup

### 1.1 Dependencies
- Python 3.10+ (the project uses Python 3.10 or later throughout)
- The core runtime has zero third-party dependencies and uses only the Python standard library
- Optional CLI experience dependency: `prompt_toolkit>=3.0,<4`

### 1.2 Installation

**Option 1: development mode install (recommended)**
```bash
cd agent-from-scratch
pip install -e .
```
After installation, `python -m mini_agent` can be run from any directory.

For multi-line editing, Shift+Enter line breaks, and multi-line paste, also install:

```bash
pip install -e '.[interactive]'
```

Without this extra, the CLI automatically falls back to the standard library `input()`, and core features are not affected.

**Option 2: no install, use PYTHONPATH**
```bash
# Windows PowerShell
$env:PYTHONPATH="src"
python -m mini_agent
```
```bash
# Linux/macOS
PYTHONPATH=src python -m mini_agent
```

### 1.3 Configuration
Configuration has two layers: `config.py` (placeholder template, in git) + `config_local.py` (real configuration, not in git).

First use: copy `src/mini_agent/config_example.py` to `src/mini_agent/config_local.py` and fill in real values. `config.py` automatically runs `import *` to load `config_local.py` and override the placeholder values.

| Setting | Placeholder | Description |
|---|---|---|
| `BASE_URL` | `https://gateway.example.invalid/v1` | LLM gateway address for the old configuration compatibility path |
| `API_KEY` | `sk-PLACEHOLDER_API_KEY` | Gateway key placeholder |
| `MODEL` | `model-PLACEHOLDER` | Model name placeholder for the old configuration compatibility path |
| `PROVIDERS` / `MODEL_PROFILES` | `{}` / `{}` | When both are empty, the old triple compatibility is used; filling in the v0.36 multi-provider mappings is recommended |
| `PARENT_MODEL_PROFILE` | `default` | Parent profile alias in the new configuration |
| `SUBAGENT_MODEL_PROFILE` | `None` | Child default profile; when empty, falls back to the parent profile by the allowlist |
| `SUBAGENT_ALLOWED_MODEL_PROFILES` | `("default",)` | Allowlist of profiles that `delegate_task.model_profile` can request |
| `AGENT_PROFILES` | `{}` | v0.47 local custom named subagent roles; cannot override the four built-in roles |
| `MAX_ITERATIONS` | `50` | Maximum agent loop rounds |
| `CONTEXT_WINDOW` | `128000` | Token estimate of the model context window |
| `OUTPUT_MODE` | `normal` | Terminal output level: `quiet`, `normal`, or `debug` |
| `MAX_SESSION_FILE_BYTES` | `16777216` | Limit of a single session JSON file; default 16 MiB |
| `MAX_SUBAGENTS` | `3` | Maximum subagents one parent task can create |
| `MAX_CONCURRENCY` | `2` | Subagents running at the same time; must not be greater than `MAX_SUBAGENTS` |
| `MAX_TOTAL_LLM_CALLS` | `24` | Total LLM calls subagents delegated by the parent task can use |
| `MAX_TOTAL_TOOL_CALLS` | `72` | Total read-only tool calls subagents delegated by the parent task can use |
| `MAX_TOTAL_TOKENS` | `96000` | Total input and output tokens subagents delegated by the parent task can use |

Process run parameters are fixed implementation defaults and do not need to be written into configuration: each task has at most 4 active processes; each process keeps at most 64 KiB each of stdout and stderr; normal termination and forced kill at task boundaries each wait at most 2 seconds. For the v0.27 read and wait quotas, see the start of this manual.

> Real configuration goes in `config_local.py` (not in git); without `config_local.py`, the `config.py` placeholder values are used.

---

## 2. Running

### 2.1 Single task mode
```bash
python -m mini_agent "hello"
```
After the task completes, it enters interactive mode, where you can keep asking.

### 2.2 Interactive mode
```bash
python -m mini_agent
```
After startup it enters the interactive prompt. With the `interactive` extra installed, Enter submits, Shift+Enter inserts a line break, and after pasting multi-line text, press Enter to submit; without it, standard library single-line input is used. Enter `exit` or `quit` to exit, or press Ctrl+C/Ctrl+D.

Ordinary follow-up input continues the current task by default. Use `/new <task>` to clear the old task and start a new one, and use
`/reset` to clear the current task and task-level state; enter `/save` to explicitly turn on local session saving. The two task boundary commands first clean up the background processes registered for the task, and when cleanup is incomplete they keep the old task and report the reason. Permissions already granted in the session and project instructions are not affected.

---

## 3. Current Capabilities (v0.49, including the v0.18.1 completion reminder fix)

v0.13 adds history compaction and Context Observability on top of the v0.12 budget and trimming. The full `history` is kept locally; before each LLM call, `ContextManager` produces a sendable, protocol-valid copy of the context. When the budget is exceeded and old rounds exist, old history first tries to compact into a summary, and if the summary fails it falls back to the v0.12 trimming. The terminal uses `OUTPUT_MODE = "normal"` by default to show short progress; set it to `debug` to see token buckets, trimming/compaction events, and bounded tool details, or to `quiet` to hide process output. `CONTEXT_OBSERVABILITY = False` can still turn off the default observer.

v0.14 loads the applicable `AGENTS.md` at startup and injects project instructions into each request as protected system context. For details, see [Lesson 14](../tutorials/14-project-instructions.md).

v0.41 automatically retrieves a few relevant Memory candidates before the parent Context requests the LLM, and also provides an explicit `search_memories`. Candidates are a temporary, untrusted system material area, at most 4 entries and 2400 characters, counted separately in `ContextStats.memory`, and do not enter State, history, or session; a failure only degrades the current request and retries next time. v0.42 provides parent-side named local References, the v0.43 MCP Client runs only through a standalone command, v0.44 connects explicitly enabled MCP Tools to the parent Runtime, v0.45 adds metadata hints and on-demand loading of local Skills, v0.46 adds JSON-only HTTP, text Resources, and text Prompts, v0.47 adds named synchronous subagent roles, v0.48 adds in-process background subagents, and v0.49 adds resumable child sessions and schema 4 idle snapshots. For details, see [Lesson 42](../tutorials/42-local-references.md), [Lesson 43](../tutorials/43-stdio-mcp-client.md), [Lesson 44](../tutorials/44-mcp-tools-runtime.md), [Lesson 45](../tutorials/45-local-skills.md), [Lesson 46](../tutorials/46-mcp-http-resources-prompts.md), [Lesson 47](../tutorials/47-agent-profiles.md), [Lesson 48](../tutorials/48-background-subagents.md), and [Lesson 49](../tutorials/49-resumable-child-session.md).

### 3.1 Context architecture

For the full context production line, dual-track records, budget feedback loop, and runtime invariants, see the [context architecture notes](context-architecture.md). This section keeps an operational quick reference of fields and configuration.

`AgentState` saves task execution facts, separate from the `messages` consumed by the LLM:

| State field | Content |
|---|---|
| `task` / `current_goal` | Current task and goal |
| `tool_history` | Tool name, arguments, success status, result summary |
| `files_changed` | Paths of files successfully written or edited |
| `errors` | Permission refusal or tool failure records |
| `status` | `running` / `awaiting_process` / `done` / `blocked` / `failed` |
| `task_id` | Task ID assigned on each `begin_task`, never reused |
| `processes` / `process_events` | Background process projections and append-only lifecycle events of the current task, including stdin capability, state, and in-flight markers |
| `awaiting_process` | Non-terminal CLI handoff information while a process still runs or a stdin write has not finished |
| `todos` | Read-only compatibility projection of the active Plan Contract |
| `plan_revisions` / `plan_progress_history` | Immutable plan structure history and separate step progress events; the full history is not injected directly into the LLM context |
| `planning_state` / `active_plan` | Current plan phase, active revision, and the execution view after applying progress events |
| `replan_triggers` / `user_plan_decisions` | Active triggers, four source kinds, user decisions, and the terminal reason before recovery |
| `loop_stagnation` | Progress epoch, consecutive no-progress turn count, short fingerprints, warning type, and latest reason |
| `verification_evidence` | Latest verification command, exit code, and result; only `[exit=0]` of the current generation counts as passing |
| `verification_history` | Append-only in-task verification audit records; used for cross-generation replay, not for the completion decision or LLM context |
| `failures` / `recovery_actions` | Tool, failure/attempt/generation, classification, and retryability of recent failures, plus recovery action state and causal references |
| `repair_loop` | Current repair phase, active failure/recovery, used/remaining repair cycles, and the required next action |
| `delegations` / `delegation_budget` | Delegation delivery state, outcome, short summary/hash, active delegations, and the parent task's remaining quota; no child history |
| `checkpoints` / `rollback_checkpoints` | Single-file pre/post-image metadata; the latter lists only `ready` checkpoints that can currently be rolled back, without file content |
| `budgets` / `recovery_notice` | Remaining quotas for replans, no-progress, failure retries, argument fingerprints, recovery actions, and repair cycles, plus the current recovery notice |

v0.31 also has a separate session export, which does not change the public `snapshot()` or Trace projection in the table above; the export format is a save and restore protocol, not a Trace replay view.

All LLM requests go through `ContextManager.prepare_messages()`. It estimates tokens as `len(text) // 3`, reserves output space, and when over the limit first truncates the oldest tool result, then deletes the oldest complete history rounds. Tool execution results update State through `ToolExecutor(on_result=state.record_tool)`, and the agent loop does not keep a second copy of state directly.

```python
state = AgentState()
history = [{"role": "system", "content": build_system_prompt()}]
context = ContextManager(state, history)
tool_executor = ToolExecutor(registry, on_result=state.record_tool)
```

For each assistant message with `tool_calls`, all matching `role=tool` messages are appended before entering the next round or returning, to avoid leaving a protocol-incomplete message sequence when the iteration limit is reached.

### 3.2 Durable tool execution boundary

After `/save` is entered, the session file is upgraded to schema 4. It is still a single atomic JSON file that saves State, Context, the `tool_boundary` of the last tool turn, and resumable idle child snapshots together; no extra journal is created. `session_generation` is a sequence number incremented on each commit.

The persistence order of a tool turn is fixed: first write the assistant message and the pending calls in model order; after the permission, argument, and plan precondition checks pass, commit `handler_admitted` before the handler really starts; after the handler returns, first account State, then append the matching `role=tool`, then atomically commit that call's result. For `delegate_task`, the child result first enters the boundary's `result_ready` area; on delivery, the parent attempt, the `committed` lifecycle in State, the `role=tool`, and the boundary state are committed together. Only after all calls are committed may the LLM be requested again. `run_shell`, including `purpose="verification"`, is always recorded as `possible`; `recover` may enter another tool or run a rollback, so the outer boundary is also conservatively recorded as `possible`, while the actual recovery attempt and generation are still managed by `RecoveryRuntime`.

This boundary solves the window where "the tool already ran, but the result is not yet on disk". Serial side-effect tools complete in model order; calls with effect class `none` can produce results concurrently, but admission commits and main-thread result commits still happen in model order. Permission refusals, argument errors, plan validation failures, and handler exceptions each produce a definite tool result; a storage failure stops later handlers and model requests and is not wrapped as an ordinary tool failure.

A natural process exit is an asynchronous State fact and is committed separately, without forging a new tool reply. `write_process.input` is kept only as a placeholder when saving; if the body appears in other persisted text, saving is refused.

v0.33 adds crash recovery handoff for pending boundaries, and v0.39 can directly consume persisted raw delegation results. `--resume` still keeps the v0.31 clean safe point path; when an active pending boundary is found, the new session saves `role=tool` results synthesized in model order and the recovery State, but does not replay old calls. The current verification eligibility of the recovery generation is cleared, while the append-only verification history, FailureEvents, RecoveryActions, and plan history are kept for audit.

### 3.3 Context budget and trimming

`CONTEXT_WINDOW` can be overridden in `config_local.py` according to the model window. `ContextBudget` reserves 15% for model output by default, and the history layer uses at most 45% of the window; system messages and the first user task are guaranteed content and are never deleted.

The trimming order is fixed:

1. Old tool results keep the head and tail and mark the omitted content.
2. When still over the limit, delete from the oldest complete round.
3. Within a round, `assistant(tool_calls)` and all matching `role=tool` results always stay grouped and are never split.

The terminal outputs `[Context]` logs showing the estimated token savings of over-limit handling, truncation, and round deletion. When the guaranteed content itself exceeds the budget, the agent keeps it and keeps requesting, without crashing because of the trimming logic.

### 3.4 Context compaction

When the budget is exceeded and there are old enough history rounds, `ContextManager` makes one summary request without tool schemas and without streaming to the terminal. The summary is injected as a `[Historical Summary]` system message; recent rounds are still kept as complete tool-calling rounds. `AgentState.snapshot()` is re-rendered as `[Structured State]` each time, to anchor real execution facts.

The summary is allowed to be lossy, and State does not depend on the summary for inference. When the summary request fails, returns empty content, or there are no old rounds to compact, ContextManager automatically falls back to trimming; the original `history` is never changed.

### 3.5 System Prompt

At startup, `build_system_prompt()` in `prompt.py` assembles `messages[0]` in three layers:

| Layer | Function/constant | Content |
|---|---|---|
| Identity | `header(agent_name)` | Tells the model which agent it is (currently only build, reserved for multi-agent) |
| Behavior rules | `_CORE_RULES` | Tone, professional objectivity, tool usage, safety constraints |
| Environment info | `environment()` | Working directory, git status, platform, date (generated dynamically) |

View the current system prompt:
```bash
$env:PYTHONPATH="src"; python -c "from mini_agent.prompt import build_system_prompt; print(build_system_prompt())"
```

### 3.6 Tools

| Tool | Arguments | Permission | Description |
|---|---|---|---|
| `calculate` | `expression: str` | allow | Evaluates math expressions (only digits and `+-*/()`) |
| `read_file` | `path: str, offset?: int, limit?: int` | allow | Reads text files, supports partial reads, output has line number prefixes |
| `write_file` | `path: str, content: str` | **ASK** | Writes a file (full overwrite), asks the user before each run |
| `edit_file` | `path: str, old_string: str, new_string: str, replace_all?: bool` | **ASK** | Exact string replacement; with multiple matches, replace_all or more context is needed |
| `list_dir` | `path?: str` | allow | Lists directory content, directories get a `/` suffix, limit 200 entries |
| `grep` | `pattern: str, path?: str, include?: str` | allow | Regex search of file content, returns `file:line: content`, limit 100 entries |
| `list_references` | none | allow | Lists aliases and descriptions, without showing real root paths |
| `search_reference` | `alias, query, path?, include?, limit?` | **ASK** | Literal search within an alias; at most 2,000 files, 10,000 directory entries, 64 MiB of body |
| `read_reference` | `alias, path, offset?, limit?` | **ASK** | Reads a bounded UTF-8 line slice; success is bounded JSON, failure enters the unified tool error protocol |
| `run_shell` | `command: str` | **By command pattern** | Runs a shell command, 30 s timeout, output truncated at 2000 characters |
| `start_process` | `command: str, cwd?: str, stdin_mode?: "closed" / "pipe"` | **Separate ASK by command pattern** | Starts a background shell command and returns a `process_id` immediately; stdin closed by default, at most 4 active processes per task |
| `get_process` | `process_id: str` | allow | Queries the state, exit code, and cumulative positions of both streams of a process of this task |
| `read_process` | `process_id: str, max_chars?: int` | allow | Reads new output of both streams, the next byte positions, and buffer gaps |
| `list_processes` | none | allow | Lists bounded metadata of processes registered for this task |
| `wait_process` | `process_id: str, timeout_ms?: int` | allow | Exclusive turn, bounded wait for unread output or exit; returns to the CLI on timeout |
| `write_process` | `process_id: str, input: str, close_stdin?: bool` | **ASK** | Writes at most 4096 bytes of UTF-8 text to a process with an explicitly enabled pipe; can send EOF alone; waits at most 2 seconds per call |
| `rollback_checkpoint` | internal `checkpoint_id` | **RecoveryRuntime only** | Not in the model schema; restores an authorized, non-conflicting single-file checkpoint |

### 3.7 Permission interaction

In v0.09, the permission system was upgraded to two-dimensional matching: `(tool_name, pattern) -> action`. `PermissionGate` extracts a pattern from tool arguments (file tools extract `path`, `run_shell` and `start_process` each extract `command`, others return `*`) and does wildcard matching with `fnmatch`. `start_process` has its own rule table and does not inherit commands already allowed for `run_shell`. `write_process` uses its own `ask` rule and does not inherit the authorization of the start command or other tools.

**Rule format** (`PERMISSION_RULES` in `permission.py`):

```python
# Simple format (one-dimensional compatible, pattern defaults to "*")
{"write_file": "ask", "read_file": "allow"}

# Complex format (two-dimensional, fine control by pattern)
{"read_file": {"*": "allow", "*.env": "deny", "*.env.example": "allow"}}

# run_shell two-dimensional permissions (controlled by command prefix)
{"run_shell": {"git *": "allow", "python *": "allow", "*": "ask"}}
```

**Matching rules**:
- `findLast` semantics: search from the end for the first matching rule; later rules have higher priority
- In the complex format, `*` is automatically placed first (lowest priority), and specific patterns are placed after it (higher priority)
- When no rule matches, the default is `ask` (safety first)
- An `always` reply saves `(tool_name, pattern)` into approved, and later operations of the same kind are not asked again

**run_shell permission rules** (v0.10):

| Command pattern | Action | Description |
|---|---|---|
| `git *` | allow | git operations allowed |
| `python *` | allow | python scripts/tests allowed |
| `pip *` | allow | pip installs allowed |
| `ls *` | allow | read-only command allowed |
| `cat *` | allow | read-only command allowed |
| `echo *` | allow | read-only command allowed |
| `*` | ask | other commands ask the user each time |

`start_process` asks for all commands by default. After the user chooses `always`, only the command pattern for `start_process` is saved; it does not change the authorization of the same command in `run_shell`.

The authorization prompt of `write_process` shows only safe metadata, for example:

```
Allow write_process(process_id=proc-1, bytes=7, close_stdin=True)? [once/always/reject]
```

The input body does not appear in the prompt. `write_pending` means delivery could not be confirmed within two seconds; wait for the state from the next `get_process` or `wait_process`, and do not deliver the same input again.

Before `write_file`/`edit_file` run, the prompt is:
```
Allow write_file({...})? [once/always/reject]
```
- `once`: allow this time, ask again next time
- `always`: always allow this pattern within this run, without asking again
- Any other input: refuse execution, and the tool returns the refusal reason to the LLM

> Two-dimensional permission example: after configuring `{"read_file": {"*": "allow", "*.env": "deny"}}`, reading `.env` files is refused, and other files are allowed normally.

### 3.8 Tool call flow
1. The LLM returns `tool_calls` (one round can contain several, and the code runs them concurrently in a thread pool)
2. `ToolExecutor` first passes the permission gate (`PermissionGate.guard`)
3. If it passes, the handler is called; on failure, the exception is caught and an error message returned to the LLM
4. The result is fed back as a `role=tool` message and enters the next round; the Executor callback also updates AgentState

A successful result of `start_process` only proves the handle was created. The Runtime syncs processes before each round's context, the full tool result feedback, the completion decision, and user resume; a natural exit records the final event and invalidates old verification. The model can use the v0.27 observation tools to query state and new logs; repeated empty results do not count as new facts. When the model replies only with text while processes are still active or a stdin write is in flight, or `wait_process` times out, the task enters `awaiting_process`, and the CLI shows how to continue without marking the task complete. v0.28 provides model-callable terminate_process/kill_process; v0.29 adds write_process for explicit pipes; task boundary cleanup is still done by the Runtime. After a successful write, observation must continue, and it cannot replace independent verification.

If a batch of calls puts the task into `blocked`/`failed` in the middle, the remaining calls still each produce a refusal result and are all fed back, and the next model round can only explain the terminal reason; they do not trigger permission prompts or handlers again.

### 3.9 Relative path convention
Relative paths of tools (such as `examples/input.txt`) are resolved against the process's **current working directory**, not automatically relative to the installed package directory. When using repository examples, it is suggested to enter the repository root first:
```bash
# Run in the agent-from-scratch/ directory
python -m mini_agent "Read examples/input.txt"
```

### 3.10 Terminal output

The CLI input prompt is fixed as `You › `. When assistant text arrives as an SSE stream, `Assistant › ` is shown only after the first non-empty chunk is received, and the text is then appended directly; so an empty reply leaves no empty heading. The agent loop connects the `on_content` callback of `call_llm` to this layer, and the final text is not replayed as a whole again.

The output mode is controlled by `OUTPUT_MODE`:

| Mode | Content shown |
|---|---|
| `normal` | Assistant text, tool batches (counted by tool name), and structured results in call order |
| `debug` | normal content, plus rounds, tool arguments, and tool results; arguments and results each at most 1200 characters |
| `quiet` | Hides assistant text, tool progress, and runtime state; explicit CLI notices and permission confirmations are still shown |

In normal mode, successful tool results show only the tool name and a safe summary, without expanding the result body. File tool summaries contain only `path`, `run_shell` only `command`, and each summary is at most 100 characters; other arguments such as written content and grep patterns are not shown. Failures, refusals, timeouts, and invalid results show a reason of at most 240 characters. Only debug mode shows the bounded full result. These limits apply only to the terminal; the full tool message is still fed back to the model.

The semantics of `stream_output` and `on_content` in `call_llm` are:

- With `stream_output=True` and `on_content` passed, the callback is called once per text chunk, with no extra writes to standard output; callback exceptions are isolated.
- With `stream_output=True` and no callback, the standard output compatibility behavior of standalone calls is kept.
- With `stream_output=False`, text is not printed and the callback is not called, but the full assistant message is still accumulated and returned. When not specified explicitly, quiet mode defaults to streaming observation off, and the other modes default to on.

Terminal presentation is an observation layer: a closed output stream, redirection, or write failure does not change the tool protocol or make execution fail. Permission prompts are still issued synchronously by `PermissionGate`; even in quiet mode the user must see the prompt and enter `once`, `always`, or `reject`.

---

## 4. Tests

### 4.1 Run the smoke tests
```bash
# Requires PYTHONPATH=src (when not pip installed)
$env:PYTHONPATH="src"; python tests/test_prompt.py   # system prompt
$env:PYTHONPATH="src"; python tests/test_loop.py      # import chain
$env:PYTHONPATH="src"; python tests/test_tools.py     # tools + permissions
$env:PYTHONPATH="src"; python tests/test_state.py      # AgentState
$env:PYTHONPATH="src"; python tests/test_context.py    # budget, trimming, and compaction
$env:PYTHONPATH="src"; python tests/test_executor.py   # Executor result callback
```
Coverage: layered system prompt assembly, import chain, registry registration, AgentState, ContextManager budget/trimming/compaction, Executor result callback, calculate normal/illegal input, read_file partial reads, file read/write, edit_file exact replacement/multi-match safety check, list_dir, grep, run_shell execution/exit code/two-dimensional permissions, and the permission gate.

### 4.2 Quickly verify the import chain
```bash
PYTHONPATH=src python -c "from mini_agent.state import AgentState; from mini_agent.tools import create_registry; print([t.name for t in create_registry(AgentState()).list_tools()])"
# Expected output contains: calculate, read_file, write_file, edit_file, list_dir, grep, run_shell, start_process, write_process
```

---

## 5. FAQ

### Q1: Running reports 502 / failed to connect to the gateway
Confirm that `BASE_URL` and `API_KEY` in `config_local.py` are correct and the configured gateway is reachable on the network.
> Note: `http.client` must be used (the code already does), not requests/urllib—the gateway responds abnormally to `Accept-Encoding: gzip`. `call_llm` explicitly sets `Accept-Encoding: identity` to work around it, and chooses an HTTP or HTTPS connection by the scheme of `BASE_URL`.

### Q2: The task stopped before it was done
The `MAX_ITERATIONS=50` limit may have been hit, and the agent returns `"Maximum iterations reached"`. It can be adjusted in `config_local.py`, but note that long conversations accumulate context.

### Q3: A tool failure exits with an error directly
The agent loop has no fallback for top-level LLM or CLI exceptions; this keeps the core path clear. The tool layer (`ToolExecutor.execute`) catches handler exceptions and feeds error results back to the LLM, but top-level exceptions of the loop itself still propagate up.

### Q4: write_file was refused
Check your input to the permission prompt. Choosing `reject` or mistyping refuses. Just run again.

### Q5: Garbled non-ASCII text (Windows console)
`__main__.py` already sets `sys.stdout.reconfigure(encoding="utf-8")` for win32. If text is still garbled, run `chcp 65001` in PowerShell to switch to UTF-8.

### Q6: A background process shows awaiting_process
This is a non-terminal handoff, meaning the model has paused its reply, `wait_process` timed out, or a stdin write is still in flight, while the processes registered for the task have not fully finished. Just keep typing to resume the original task; before resuming, the Runtime first syncs processes. Use `read_process` to read logs and `get_process` to see the stdin state; use terminate_process or kill_process to control the current task's processes; `/new`, `/reset`, and exiting the CLI clean up the current task's processes and writer threads.

## Optional Cumulative Token Limit for Parent Tasks

Setting `PARENT_TASK_TOKEN_BUDGET = 64000` in the local `config_local.py` enables a cumulative model budget for new parent tasks; the default `None` keeps the original CLI behavior. The limit counts parent main requests and same-model history summaries; subagents are managed by the original separate and aggregate budgets. Evaluation suite 1.5 explicitly enables a fixed 64,000, which is not cancelled by the ordinary CLI's off setting.

With the budget on, the output limits for execution/summary/finishing are 1024/512/512, bound by the smaller model configuration limit. The last two complete tool turns enter the request view; older results can be trimmed or omitted as whole turns, selected reasoning fields keep their original text, and the full local history and existing session evidence are kept. When the task gives an explicit path, it is read directly, to avoid listing directories repeatedly first.

OpenAI Chat budget admission estimates the UTF-8 size from the messages, role fields, tool schemas, keys, and punctuation of the actual request JSON, then uses `ceil(bytes × 1.1 ÷ 3)` to get a local proxy value. It is not a provider tokenizer; real usage is still decided by the provider response, and calibration only absorbs observations with the same estimator version, binding, tool schema, and request category. When the estimate is too large, omittable historical tool turns are trimmed first, without deleting protected instructions, State, or user corrections; if this protected content still does not fit, the request is refused before sending. Other protocols keep the original estimate path. There is no absolute no-overrun guarantee for hidden context of unknown providers, and when a response exceeds the reservation, tool execution is still blocked.

The budget ledger is committed both before the request and after settlement. When a commit fails, the request or later tools stop; unknown calls are charged the full reservation and not treated as zero. When an existing ledger is restored, the saved limit and usage keep being used, and changing configuration cannot add budget to the same task. When an old session lacks this field, no charges are added after the fact and the new configuration is not enabled automatically; a new task created by `/new` can be enabled by the current configuration.

The Runtime includes plan progress and verification in the budget available to the current working request, and separately reserves only the quota for the later tool-free final reply. The finishing reservation is estimated from the current protected instructions, user constraints, and completion facts, without reserving another copy of the current verification request and without deducting repeatedly by the number of unfinished steps. The low-budget reminder still requires the model to prioritize verification and finishing; this does not guarantee that the model chooses the correct order, nor that future State growth or any provider response stays within the estimate. Only when there are actually no completion blockers and current-generation verification or a complete plan exists does it enter the tool-free finish; a real model reply and the original completion conditions must still pass. When protected content cannot fit, it states `token_limit` explicitly, and the refusal diagnostics keep the context floor, available input quota, and finishing reservation, without deleting constraints, cancelling verification, or automatically declaring completion.

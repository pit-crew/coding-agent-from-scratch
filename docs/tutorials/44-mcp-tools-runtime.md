# Lesson 44: Letting the Agent call MCP Tools

Previous: [Connecting an MCP Server over stdio](43-stdio-mcp-client.md) · [Tutorial overview](README.md) · Next: [Local Skills](45-local-skills.md)

Code snapshot: `v0.44` · Adjacent diff: `v0.43..v0.44`

The commands in this lesson use Bash/zsh. The code links and examples below all correspond to `v0.44`.

## Lesson Goals

In the previous lesson, the Client called the MCP Server only after you confirmed manually on the command line. The Agent could not see this tool yet. The problem this lesson solves: how can the model request an external tool while the Agent keeps control of the execution?

First, recall one round of the Agent's work: it hands the task to the model; the model can reply with text or submit a structured tool request; the Agent decides whether to run the request, hands the result back to the model, and continues with the next round. Once MCP Tools are connected, external calls must take the same path. The model can propose a request but cannot bypass local configuration and permission checks to control a Server directly.

After reading, you should be able to explain why `agent_enabled` is off by default, what `readonly_tools` actually allows, and how MCP calls go through the existing Agent execution flow.

## Prerequisites

You only need basic Python, a terminal, and Git; read Lesson 43 first to learn how the MCP Client connects to a Server. A few names are used here: a Tool is one operation the Agent can request; the Tool Registry is the tool catalog the Agent shows to the model; the ToolExecutor is the part of the Agent that actually checks and runs tool requests.

First look at this version's changes relative to v0.43, then switch to the matching source:

```bash
git checkout v0.43
git diff --stat v0.43..v0.44
git checkout v0.44
```

After reading, use `git checkout -` to return to the branch you were on before switching.

## New and Changed Files

This version keeps the MCP communication of Lesson 43 and adds the part that "connects external tools into the Agent's tool catalog":

| File | Responsibility |
|---|---|
| [mcp/adapter.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.44/src/mini_agent/mcp/adapter.py) | Converts Server tools into Tools the Agent can recognize and holds the connection. |
| [mcp/schema.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.44/src/mini_agent/mcp/schema.py) | Checks the argument descriptions the Server gives and the arguments the model actually submits. |
| [tools/__init__.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.44/src/mini_agent/tools/__init__.py) | Loads enabled MCP Tools when creating the parent Agent's tool catalog. |
| [tools/base.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.44/src/mini_agent/tools/base.py) | Brings external tool results back into the project's uniform execution result format. |
| [permission.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.44/src/mini_agent/permission.py) | Explains the call to the user and asks for authorization before it happens. |
| [runtime.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.44/src/mini_agent/runtime.py) | Runs the loop of model requests, tool execution, and result feedback. |

## Version Change Map

v0.43 has only the standalone MCP command; it does not go through the Agent. The two diagrams below first mark this old path, then show where v0.44 connects MCP tools.

```text
[old] already in v0.43:
[old] command line → [old] MCP Client → [old] Server
                 └─ [old] called directly after you confirm on the command line
```

```text
[+] new in v0.44:
[+] local configuration (agent_enabled=True)
  → [C] create_registry connects the Server and freezes the tool catalog
  → [+] the Adapter translates the catalog into Agent Tools
  → [C] the Tool Registry offers them to the model
  → [old] the model proposes a tool request
  → [old] the ToolExecutor checks authorization and runs it
  → [old] the result goes back to the model as a role=tool message
       └─ [B] an assembly failure closes the connected Server; call failures are not retried
```

Legend: `[old]` already in v0.43; `[+]` new in v0.44; `[~]` changed in v0.44; `[C]` main consumer; `[B]` boundary of this version. `role=tool` here is the message category in the conversation protocol meaning "tool execution result". It is not a reply from the model and not a new question from the user. Only after the model gets the result does the Runtime start the next round.

## Key Flow

The path of one call from the model request to the MCP Server:

```text
the model requests mcp_demo_echo
  → the Agent finds the registered tool and checks the arguments
  → checks whether the current task plan allows this step
  → the PermissionGate (permission check) asks you whether to allow it
  → once approved, the Adapter calls the MCP Server with the original name
  → the result goes back to the model, which keeps answering based on it
```

The `Adapter` is a translation layer between two interfaces: the model sees the project's uniform tool names and arguments; the Adapter remembers which Server the tool came from and what the Server originally called it, then translates the request back into MCP format. For example, the Server's `read-only` is shown as `mcp_demo_read_only`, but the original name `read-only` is still used when sending to the Server.

If you deny authorization, or the arguments do not match the tool's declaration, the Server receives no call. If the request was sent but the Server times out or disconnects, the Agent records the failure and hands the result back to the model; it does not guess whether the Server finished and then retry automatically.

## Implementation Breakdown

### 1. Configuration explicitly chooses which Servers may enter the Agent

The entries in `MCP_SERVERS` only describe how a local Server is started. v0.44 adds `agent_enabled`, which defaults to `False`: only after you enable it explicitly do the Server's tools enter the parent Agent's tool catalog. So old configurations do not start automatically after an upgrade.

```python
MCP_SERVERS = [{
    "alias": "demo",
    "command": ["python", "../../tests/fixtures/mcp_stdio_server.py"],
    "cwd": ".",
    "environment": {},
    "agent_enabled": True,
    "readonly_tools": ["echo"],
}]
```

`readonly_tools` must use the original tool names the Server returns, matched exactly including case and hyphens. Listing a tool only means the local configuration classifies it as "does not change external state"; the default permission is still `ask`, and the user still has to approve. The Server claiming a tool is read-only is not enough to change this classification.

### 2. Check external tool descriptions before handing them to the model

The tool names and argument descriptions a Server returns are external data. Before putting them into the Registry, the Adapter checks their format, size, and duplicate names; when the model actually calls, the arguments are checked again. An argument format that cannot be supported rejects the whole assembly, so constraints that are not understood are never quietly handed to the model.

### 3. Requests and results go through the uniform executor

The ToolExecutor is the execution boundary shared by built-in tools and MCP tools: it checks arguments, confirms whether you authorized the call, respects the limits of the current task plan, then records the execution result and hands the `role=tool` message to the model by call ID. On success, bounded text is available for the model to keep working; State (the Agent's structured task record) and Trace (execution events saved in order) record only summaries such as the source, result category, and byte count, not a copy of the whole remote body.

If `/save` (the command that saves the current task as a resumable session) is enabled, a `handler_admitted` boundary record must also be committed before the tool starts running. It means "locally approved to enter the handler". If this commit fails, the Server is not called; if a crash happens later, an admitted MCP call is treated as a fact with an uncertain result, and it is not replayed just because the connection is restored.

### 4. The connection belongs to the current parent Agent

When the Runtime starts, it connects the Server according to the current local configuration, reads the whole tool catalog, and freezes the result. New tasks or resumed tasks reconnect; the connection itself is never reused from a saved session. When the task ends, switches, or exits, the Runtime is responsible for closing the connection.

Subagents (child runtime instances that do read-only investigation for the parent Agent) still have only the fixed four basic tools; they do not inherit MCP Tools, parent permissions, or parent task state.

## Why This Design

Converting MCP tools into ordinary Tools lets the project keep using its existing authorization, plan checks, result recording, and recovery rules. If MCP took a separate execution path, authorization denials, result feedback, and crash recovery could easily follow different rules from built-in tools.

Starting a local Server is also an action that needs explicit control, so connecting it to the parent Agent is off by default. Another trade-off is accepting only restricted argument schemas and bounded text results; images, binary data, or structured returns that cannot be interpreted fail explicitly instead of being disguised as ordinary text.

## Run and Observe

If you already have local LLM configuration, add the `demo` configuration above to the untracked `src/mini_agent/config_local.py`, then start the parent CLI:

```bash
PYTHONPATH=src python -m mini_agent
```

Ask the Agent for something that needs `echo`. The terminal should first show an authorization prompt containing the alias and the original tool name. Only after you choose `once` does the fixture Server receive one call; after you choose `reject`, the Agent receives a rejection result and the Server receives no call. This shows that the model only proposes requests, while execution is still controlled by the parent Agent's permission check.

If you remove `agent_enabled` from the configuration or set it to `False`, the parent Agent does not connect to that Server; the standalone command of Lesson 43 can still use it on its own.

## Design Boundaries

- Only stdio MCP Tools are connected; Resources, Prompts, and HTTP are covered in later versions.
- The tool catalog is not hot-refreshed after it is built. After a connection fails, there is no automatic reconnect and no `tools/call` retry.
- `readonly_tools` is only an exact side-effect classification; it cannot skip the default authorization and does not automatically become verification evidence.
- MCP tools enter only the parent Agent. Server names, descriptions, arguments, and results are all handled as untrusted external data.

## Version Features, Next Lesson, and Code Index

v0.44 lets the parent Agent request MCP Tools enabled by local configuration. Requests go through the Agent's own argument, permission, and execution boundaries, and results come back to the model. The next lesson introduces a different capability: a local Skill that only provides working-step instructions and does not perform actions directly.

Pinned code index: [adapter.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.44/src/mini_agent/mcp/adapter.py), [schema.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.44/src/mini_agent/mcp/schema.py), [tools/__init__.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.44/src/mini_agent/tools/__init__.py), [tools/base.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.44/src/mini_agent/tools/base.py), [permission.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.44/src/mini_agent/permission.py).

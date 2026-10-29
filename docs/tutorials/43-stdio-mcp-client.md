# Lesson 43: Connecting an MCP Server over stdio

Previous: [Named local References](42-local-references.md) · [Tutorial overview](README.md) · Next: [Connecting MCP Tools to the Agent](44-mcp-tools-runtime.md)

Code snapshot: `v0.43` · Adjacent diff: `v0.42..v0.43`

The commands in this lesson use Bash/zsh. The code links and examples below all correspond to `v0.43`.

## Lesson Goals

For one program to use capabilities provided by another, both sides must agree on how messages are written, what is said first, and how to know which request a reply belongs to. MCP (Model Context Protocol) is such an agreement; an MCP Server provides tools, and an MCP Client connects and sends requests.

This lesson first writes a standalone Client: it starts a local Server, lists its tools, and calls a tool after you confirm. It is not yet connected to the Agent, so the language model does not choose tools for you. After reading, you should be able to follow the order of one MCP session and explain why this demo path is not yet the Agent's tool authorization system.

## Prerequisites

You only need basic Python, a terminal, and Git. The Agent here means "the program that asks the model questions based on the user's task and runs the tools the model requests"; this lesson does not run that Agent flow yet but observes on its own how the Client and Server communicate.

First look at the diff between the previous version and this one, then switch to this lesson's code:

```bash
git checkout v0.42
git diff --stat v0.42..v0.43
git checkout v0.43
```

After reading, use `git checkout -` to return to the branch you were on before switching.

## New and Changed Files

What this version adds is a standalone connection path. The table lists only the parts you need to know to understand this path:

| File | Responsibility |
|---|---|
| [mcp/client.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.43/src/mini_agent/mcp/client.py) | Handshakes in MCP order, lists and saves the tool catalog, sends tool calls. |
| [mcp/stdio.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.43/src/mini_agent/mcp/stdio.py) | Starts the local Server and reads protocol messages and diagnostic output separately. |
| [mcp/protocol.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.43/src/mini_agent/mcp/protocol.py) | Checks the JSON-RPC message format of requests, notifications, and responses. |
| [mcp/__main__.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.43/src/mini_agent/mcp/__main__.py) | Provides the `list` command and the `call` command, which asks for confirmation every time. |
| [config.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.43/src/mini_agent/config.py) | Reads local MCP Server configuration; importing the configuration does not start a Server. |

## Version Change Map

First look at the old and new paths separately. The Agent tool flow already in v0.42 is managed by the Runtime; the MCP command added in v0.43 runs independently and does not connect to that flow.

```text
previous version v0.42:
[old] user task → [old] AgentRuntime ↔ [old] model
                          └─ [old] model requests a tool → [old] ToolExecutor → [old] tool result

new in this version v0.43:
[+] command line `python -m mini_agent.mcp`
  → [C] McpClient → [+] StdioTransport → [+] local MCP Server
       └─ [B] standalone demo path; not connected to AgentRuntime or PermissionGate
```

Legend: `[old]` already in v0.42; `[+]` new in v0.43; `[C]` main consumer; `[B]` boundary of this version. This is the most important conclusion of this lesson: a Client being able to call a Server does not mean the Agent can call it yet. Only the next lesson connects external tools to the Agent's existing execution and authorization flow.

The project calls the part responsible for the model and tool loop `AgentRuntime`. It is mentioned below to mark the boundary; this lesson does not need to change or start it.

## Key Flow

stdio is two pipes between processes: the Client writes to the Server's standard input (stdin), the Server writes protocol replies to standard output (stdout), and diagnostic information goes to standard error (stderr). So the program can keep messages for machines separate from logs for people.

A session first confirms the protocol both sides support, then lists the catalog, and only then can call tools:

```text
Client                                      Server
  │── initialize (request id=1) ───────────>│  confirm protocol version and capabilities
  │<─ response (id=1) ──────────────────────│
  │── notifications/initialized (notice) ──>│  handshake complete
  │── tools/list (request id=2) ───────────>│  return the first page of tools
  │<─ response (id=2, may have nextCursor) ─│
  │── tools/list (request id=3, optional) ─>│  return later pages
  │── tools/call (request id=4) ───────────>│  run the named tool
  │<─ response (id=4) ──────────────────────│
  └── close stdin and reap the Server process
```

`initialize`, `tools/list`, and `tools/call` are requests and each carries an ID; the Client uses the same ID to find the matching reply. `notifications/initialized` is a notification that only signals an event and needs no reply, so it has no ID. This version is pinned to MCP `2025-11-25` and does not try to guess or switch protocol versions. JSON-RPC is the format that carries these messages: an `error` in a reply means the protocol request failed; a tool can also return a normal `result` but mark `isError=true` in it, which means the tool ran and reported a business error.

Below is the key order of the handshake in the Client. The ellipsis stands for version and return value checks; the point is that the Server is notified that the handshake is over only after `initialize` completes:

```python
result = self._request(
    "initialize",
    {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": "mini-agent", "version": __version__},
    },
    timeout=self.startup_timeout,
)
# Check the protocol version and capabilities the Server returned
self._send_notification("notifications/initialized", None)
```

This is a simplified excerpt of [`McpClient._connect()`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.43/src/mini_agent/mcp/client.py), with the check code omitted. After the handshake, the Client also reads the whole tool catalog before saving it as a snapshot. MCP can split a long catalog into pages; `nextCursor` is the position marker for "there is a next page". A repeated cursor, a duplicate tool name, or a format mismatch makes the whole catalog fail; the Client does not continue to call with only the first page.

## Implementation Breakdown

### 1. Starting the process does not go through a command interpreter

The command in the configuration is passed as an argument list to `subprocess.Popen` with `shell=False`. This means `python` and the script path run as explicit arguments, without first going through a shell that would interpret `;`, pipes, or variable expansion. The configuration can set the working directory and environment variables, but these values are read only from the local `config_local.py`.

### 2. Protocol output and logs are handled separately

stdout is read line by line as UTF-8 JSON-RPC; stderr is drained separately, and only a small tail of diagnostic content is kept. Single messages, the waiting queue, and the shutdown time all have limits. On bad encoding, bad JSON, a timeout, or a process exit, the connection becomes invalid; a `tools/call` that may already have run is not retried automatically.

On shutdown, stdin is closed first, then the program waits for the Server to end; only after a timeout does it try to terminate and reap the process. This gives the Server a chance to finish cleanly and avoids leaving background child processes behind.

### 3. Manual confirmation only protects the standalone command

Before a call, the standalone command shows the Server alias, the tool's original name, and the full arguments, and asks you to confirm. If the input is not an explicit `yes` or `y`, the arguments cannot be shown in full, or stdin is not an interactive terminal, no call is sent.

This confirmation belongs only to this command-line demo. It has no Agent PermissionGate (tool authorization check), and it saves no authorization for later model calls.

## Why This Design

This lesson first validates the protocol and process boundaries on their own, so you can see clearly the work the Client must take on: handshake in order, pair requests with replies, read the whole catalog, and close the Server on failure. If these behaviors were mixed with Agent authorization from the start, it would be hard to tell whether a failure came from MCP communication or from Agent decisions.

This version uses stdio because the input, output, and shutdown of a local process are easy to observe. It supports only the fixed MCP `2025-11-25`, does not probe other versions, does not retry calls, and does not support HTTP, Resources, or Prompts. A request with an ID initiated by the Server also closes the connection; this lesson implements only the path where the Client initiates requests.

## Run and Observe

To reproduce the results below, configure this lesson's local demo Server in the untracked `src/mini_agent/config_local.py`:

```python
MCP_SERVERS = [{
    "alias": "demo",
    "command": ["python", "../../tests/fixtures/mcp_stdio_server.py"],
    "cwd": ".",
    "environment": {},
}]
```

A relative `command` and `cwd` are resolved from the `src/mini_agent` directory. Then run in the repository root:

```bash
PYTHONPATH=src python -m mini_agent.mcp demo list
PYTHONPATH=src python -m mini_agent.mcp demo call echo '{"text":"hello"}'
```

The first command should list `echo`, `sum`, and `third`. They are split into two pages, so the Client sends `tools/list` twice. The second command first shows the arguments it will send; after you confirm, the text the Server returns should contain `hello`. If you do not confirm, the Client does not send `tools/call`.

## Design Boundaries

- The Client only reads and calls a frozen tool catalog; receiving a catalog change notification does not refresh it during the run.
- `tools/call` is not retried automatically after a timeout or disconnect, because the Server may already have performed the action.
- This lesson does not connect to AgentRuntime, the Tool Registry, the PermissionGate, State, or the session. The standalone command's confirmation cannot replace the later Agent permission check.
- Only bounded text results are allowed; this version does not handle Resources, Prompts, binary results, or Server-initiated requests.

## Version Features, Next Lesson, and Code Index

v0.43 completes a standalone stdio MCP Client. The next lesson turns the frozen external tool catalog into tools the Agent can request, and makes these calls go through the Agent's own authorization and execution flow.

Pinned code index: [client.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.43/src/mini_agent/mcp/client.py), [stdio.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.43/src/mini_agent/mcp/stdio.py), [protocol.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.43/src/mini_agent/mcp/protocol.py), [mcp/__main__.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.43/src/mini_agent/mcp/__main__.py).

# Lesson 46: Restricted HTTP MCP, Resources, and Prompts

Previous: [Local Skills](45-local-skills.md) · [Tutorial overview](README.md) · Next: Stage 12 wrap-up

Code snapshot: `v0.46` · Adjacent diff: `v0.45..v0.46`

The commands in this lesson use Bash/zsh. The code links and examples below all correspond to `v0.46`.

## Lesson Goals

Besides tools the model can request, an MCP Server can also provide material and prompt templates. So control falls into three different cases: the model requests a Tool; the user picks a Resource in the CLI; the user reviews and confirms a Prompt. This lesson explains how each of these three entries works, and why Resources and Prompts are not handed to the model to call on its own.

This version also lets the MCP Client connect to a Server over HTTP. HTTP is a way to send requests and receive replies over the network; this lesson supports only the restricted form where each request returns one JSON message. After reading, you should be able to judge when content enters the later conversation, when user confirmation is needed, and what this HTTP support does not cover.

## Prerequisites

You only need basic Python, a terminal, and Git. Read Lessons 44 and 45 first to learn about Agent Tool authorization, local Skills, and the Context. The Context is the background and conversation sent to the model each round; the CLI is the command-line interface through which the user interacts with the Agent.

View the changes from the adjacent version and switch to this lesson's code:

```bash
git checkout v0.45
git diff --stat v0.45..v0.46
git checkout v0.46
```

After reading, use `git checkout -` to return to the branch you were on before switching.

## New and Changed Files

This version has two kinds of changes: one more HTTP transport, and two content entries controlled by the application and the user.

| File | Responsibility |
|---|---|
| [mcp/http.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.46/src/mini_agent/mcp/http.py) | Sends and receives bounded JSON requests with the standard library `http.client`. |
| [mcp/client.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.46/src/mini_agent/mcp/client.py) | Manages request pairing and reads and freezes the Tools, Resources, and Prompts catalogs. |
| [mcp/adapter.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.46/src/mini_agent/mcp/adapter.py) | Manages connections; connects only Tools to the Agent's model tool catalog. |
| [config.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.46/src/mini_agent/config.py) | Checks stdio/HTTP configuration, the HTTPS default, and the loopback HTTP switch. |
| [permission.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.46/src/mini_agent/permission.py) | Asks for permission to read Resources and get Prompts. |
| [__main__.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.46/src/mini_agent/__main__.py) | Provides four CLI commands, adding material to the conversation, and Prompt preview confirmation. |
| [context.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.46/src/mini_agent/context.py) | Makes Resource bodies take part in conversation length control and excludes them from automatic memory retrieval. |

## Version Change Map

The previous version already has the stdio MCP Tool path. This version adds HTTP to the same Client and provides two paths that do not go through the model's Tool catalog:

```text
[old] already in v0.45:
[old] stdio Server → [old] MCP Client → [old] Adapter → [old] Tool Registry
                                                         → [old] AgentRuntime → [old] ToolExecutor
```

```text
[~] changed and extended in v0.46:
[~] stdio or HTTP Server → [~] MCP Client (frozen after the catalog is fully read)
                               ├─ [old] Tools → [C] Adapter → [old] AgentRuntime → [old] ToolExecutor
                               ├─ [+] Resources → [C] user picks in the CLI → material for the later conversation
                               │                    └─ [B] only bounded text from the catalog is accepted
                               └─ [+] Prompts → [C] user previews and confirms → one new user input
                                                    └─ [B] on cancel, nothing enters the conversation
```

Legend: `[old]` already in v0.45; `[+]` new in v0.46; `[~]` changed in v0.46; `[C]` main consumer; `[B]` boundary of this version. The difference between Tools, Resources, and Prompts is "who decides to use it". A Tool is an operation request proposed by the model and still goes through the Agent's permission check; a Resource is chosen by the user in the CLI and, once read, takes part in the later conversation as untrusted material; a Prompt is also chosen by the user and runs as a new user input only after a full preview and confirmation.

## Key Flow

### 1. HTTP only changes the connection method, not the MCP session order

Both the stdio Client and the HTTP Client follow the same order: initialize, notify that initialization is complete, read the capability catalogs, then send requests as needed. HTTP uses the Python standard library `http.client` to send POST requests and explicitly asks for an uncompressed response (`Accept-Encoding: identity`); after initialization the Server may assign a session ID (a session marker that identifies the same connection), and the Client carries it only in the current in-memory connection.

This version accepts only per-request `application/json` replies. Even if the request header declares that other transfer forms are acceptable, when the Server returns SSE, a redirect, requires OAuth, or disconnects after a request is sent, the Client fails closed; it does not switch to another method or retry a call that may already have run. HTTPS is used by default; only when explicitly allowed can a loopback address use plaintext HTTP.

### 2. A Resource is material the user adds to the conversation

The main CLI lists and reads Resources with these commands:

```text
/mcp-resources <alias>
/mcp-resource <alias> <uri>
```

Before reading, the Resource must already appear in the catalog that was fully read and frozen. Listing Resources and Prompts is allowed by default; reading a Resource and getting a Prompt ask by default; `always` remembers only the matching exact `alias:uri` or `alias:name`. The body must be bounded UTF-8 text, and the returned URI must equal the requested one. Images, audio, binary data, or oversized content are rejected.

After reading, the body becomes an ordinary user-side material message in the current conversation. The code marks the source with `name`, so it is not mistaken for ordinary text the user typed:

```python
context.history.append({"role": "user", "name": "mcp_resource", "content": content})
```

It does not trigger a model request immediately; the model sees it, within the Context budget, the next time you submit a task. The body is not copied into the structured State or Trace summaries and does not serve as verification evidence; summaries such as its source can still be recorded.

A Resource body belongs to ordinary conversation history and may be saved with the session when `/save` is on. State and Trace keep only a source summary.

### 3. A Prompt is one input the user submits after review

The CLI provides two Prompt commands:

```text
/mcp-prompts <alias>
/mcp-prompt <alias> <name> <JSON argument object>
```

Before getting a Prompt, the Prompt catalog must have been listed and frozen. After the program checks the name and the string arguments, it asks the Server to return the template messages; the returned content can only be bounded text, and role labels can only be the raw `user` or `assistant`. `assistant` here means "the role the template originally labeled", not that the Agent has already said this text.

The program previews the full template. On cancel, the content does not enter the conversation, and no model request is made; on confirmation, the whole preview is handed to the existing task flow as one `role=user` input. This keeps the template structure and also keeps a Server from disguising text as real assistant history. The confirmed input belongs to ordinary task history and may be saved with the session when `/save` is on.

The order of one get can be summarized as:

```text
/mcp-prompt → check the frozen catalog → check permission → get and validate the text
            → full preview → user cancels (end)
                           → user confirms → run the Agent with it as user input
```

## Implementation Breakdown

HTTP responses, catalogs, single texts, and accumulated text all have size limits. Tools, Resources, and Prompts are frozen only after all their pages are read; later Resource URIs and Prompt names can only be chosen from their respective frozen catalogs. Nothing is hot-refreshed at runtime because of Server notifications.

Only when a Server declares the `tools` capability at initialization can its tools enter the Agent tool catalog. Servers dedicated to Resources and Prompts can be connected by the connection manager, but they do not gain model-callable Tools because of that. MCP connections are created in the current parent Runtime and closed within bounds on task switches, resume, and exit.

Resources take part in the Context length trimming of the ordinary conversation but do not extend the query of automatic Memory retrieval. Prompts enter the task history only after user confirmation. Neither enters Subagents, and neither produces tool call records or verification evidence.

## Why This Design

Having Resources and Prompts chosen on the application side lets the user decide when to bring external content into a task. The cost is that the user has to list the catalog and choose an entry first, and the model cannot call them on its own. Keeping a Prompt's original roles as preview labels rather than real conversation roles prevents external Servers from forging history.

HTTP implements only per-request JSON, which makes it easier for the code to check status, content type, and reply size within bounds; as a result it is not compatible with Servers that require SSE. This version also does not implement OAuth, redirects, resource templates, subscriptions, Prompt completion, binary content, or Server-initiated requests.

## Run and Observe

If you have configured a local MCP Server with the alias `demo` whose catalog contains Resources and Prompts, first look at the options:

```text
/mcp-resources demo
/mcp-prompts demo
```

Then replace the example URI and name with values actually shown in the lists:

```text
/mcp-resource demo <a URI from the list>
/mcp-prompt demo <a name from the list> {"topic":"example"}
```

When reading a Resource, you should see a permission prompt; once approved, it enters the conversation, but no model request is made at that moment. When getting a Prompt, you should first see the full preview; after cancelling, the conversation is unchanged, and only after confirming does one task start. The latter needs a locally configured model.

## Design Boundaries

- HTTP requires HTTPS by default; plaintext HTTP is available only for explicitly allowed loopback addresses. URLs, auth headers, and session IDs do not enter State, Trace, or the session.
- Only JSON replies are accepted; no SSE, redirects, or OAuth; requests are not retried automatically after a timeout or disconnect.
- Resources and Prompts must come from frozen catalogs, and only bounded text is supported; no template catalogs, binary content, or hot refresh.
- External bodies are handled as untrusted material; they do not override project instructions, authorization, plans, or verification rules, and are not passed to Subagents.

## Version Features, Next Lesson, and Code Index

v0.46 adds a restricted HTTP Client to MCP and lets the user choose text Resources from the CLI and preview and confirm Prompts. Each of the three capabilities has its own control entry: Tools are proposed by the model, Resources are read by the user, and Prompts are submitted by the user after review.

Pinned code index: [client.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.46/src/mini_agent/mcp/client.py), [http.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.46/src/mini_agent/mcp/http.py), [adapter.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.46/src/mini_agent/mcp/adapter.py), [CLI](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.46/src/mini_agent/__main__.py), [context.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.46/src/mini_agent/context.py).

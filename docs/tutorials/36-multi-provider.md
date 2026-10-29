# Lesson 36: Letting parent and child Agents use different model services

Previous: [One run loop shared by the parent Agent and subagents](35-shared-agent-runtime.md) · [Tutorial overview](README.md) · Next: [Subagent lifecycle and aggregate budgets](37-subagent-lifecycle-budget.md)

> Code snapshot: `v0.36` · Adjacent diff: `v0.35..v0.36` · Shell: Bash/zsh

This lesson's source links are pinned to `v0.36`; reading and running this lesson do not require creating a Git tag.

## Lesson Goals

The previous lesson had the parent Agent and subagents share one run loop, but they still used the same `BASE_URL`, `API_KEY`, and `MODEL` by default. If you temporarily changed global variables so the subagent used another model, parent requests could be affected too; if one service's message format were written directly into the Runtime, the core loop would become harder and harder to maintain.

This lesson separates three questions: which service a request is sent to, what message format the service uses, and what local name the project binds to this model. After reading, you should be able to explain:

- What a provider, a protocol, and a model profile each are;
- Why parent and child must freeze their own model binding before their Runtime is created;
- How adapters translate different services into uniform assistant/tool messages;
- Why an unknown or unauthorized child model alias must be rejected before the HTTP request.

## Problems in the Previous Version

The control loop of v0.35 is already unified, but the model source is still global configuration. The parent Agent and the subagent cannot safely each use their own service; switching service providers would also bring auth headers, tool call formats, streaming parsing, and error handling into the Runtime.

The principle of this version: the Runtime only touches a uniform message structure; provider selection and protocol translation stop at the call boundary. This way "switching services" cannot quietly change tool permissions, completion decisions, or parent/child isolation.

## Prerequisites and Version Checkout

You need Lesson 35, basic Python, JSON, and the basics of HTTP requests. Commands use Bash/zsh:

```bash
git checkout v0.35
git diff --stat v0.35..v0.36
git checkout v0.36
```

A real `endpoint`, API key, and model ID can only go in the local untracked `src/mini_agent/config_local.py`; examples committed to the repository may only use placeholder values.

## New and Changed Files

These files together complete the chain "local configuration → frozen binding → protocol adaptation → unified Runtime":

| File | Purpose |
|---|---|
| [`src/mini_agent/providers/catalog.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.36/src/mini_agent/providers/catalog.py) | Validates provider/profile configuration and creates the frozen `ModelBinding`. |
| [`src/mini_agent/providers/base.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.36/src/mini_agent/providers/base.py) | Defines the uniform response, usage, and the adapter boundary. |
| [`src/mini_agent/providers/openai_chat.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.36/src/mini_agent/providers/openai_chat.py) | Handles OpenAI-compatible Chat Completions requests and SSE chunks. |
| [`src/mini_agent/providers/anthropic_messages.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.36/src/mini_agent/providers/anthropic_messages.py) | Handles the system prompt, tool blocks, and streaming events of Anthropic Messages. |
| [`src/mini_agent/providers/http.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.36/src/mini_agent/providers/http.py) | Provides connections and bounded reads with the standard library `http.client`. |
| [`src/mini_agent/runtime.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.36/src/mini_agent/runtime.py) | Consumes the uniform response and records the usage source. |
| [`src/mini_agent/delegation.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.36/src/mini_agent/delegation.py) | Checks the child profile allowlist and freezes the child binding. |

## Version Change Map

Legend: `[old]` already in v0.35, `[+]` new in v0.36, `[~]` changed in v0.36, `[C]` main consumer, `[B]` boundary of this lesson.

The model entry of v0.35 depends on one set of global values:

```text
[C] agent_loop / SubagentRunner
      -> [old] AgentRuntime.run()
           -> [old] call_llm()
                -> [old] BASE_URL / API_KEY / MODEL
```

v0.36 inserts a configuration catalog and protocol adapters at the call boundary, but there is still only one Runtime:

```text
[C] agent_loop ───────────────┐
                              ├─> [~] AgentRuntime.run()
[C] SubagentRunner ───────────┘       -> [~] frozen ModelBinding
                                        -> [+] ProviderCatalog
                                        -> [+] ProviderAdapter
                                             ├─ OpenAI Chat Completions
                                             └─ Anthropic Messages
                                        -> uniform assistant/tool messages
                                        -> [~] UsageMeter

[B] this version adds no lifecycle, aggregate budget, cancellation, parallel delegation, or durable delegation records
```

Parent and child each freeze their binding before their Runtime is created. The binding contains a safe profile/provider/protocol/fingerprint summary; the real endpoint, model ID, key, and auth headers never enter State, Context, the session, or user-visible errors.

## Core Concepts and Data Structures

### 1. Provider, protocol, and profile are three different kinds of names

Start by separating them with three questions:

- **provider**: which model service the request is sent to, including the endpoint, auth method, and timeout;
- **protocol**: how the service requires requests and responses to be organized; this version supports `openai_chat` and `anthropic_messages`;
- **model profile**: a local alias the project gives to a specific configuration, pointing to a provider and a real model, and declaring the context window, output limit, and tool capability.

Only placeholder configuration is shown below. It shows that parent and child can choose different services; it does not ask you to write real keys into the code:

```python
PROVIDERS = {
    "gateway-openai": {"protocol": "openai_chat", "endpoint": "https://api.example.invalid/...", "api_key": "sk-PLACEHOLDER"},
    "gateway-anthropic": {"protocol": "anthropic_messages", "endpoint": "https://api.example.invalid/...", "api_key": "key-PLACEHOLDER"},
}
MODEL_PROFILES = {
    "parent-default": {"provider_id": "gateway-openai", "model_id": "model-PLACEHOLDER", "context_window": 128_000, "max_output_tokens": 8_192},
    "child-anthropic": {"provider_id": "gateway-anthropic", "model_id": "model-PLACEHOLDER", "context_window": 200_000, "max_output_tokens": 4_096},
}
PARENT_MODEL_PROFILE = "parent-default"
SUBAGENT_MODEL_PROFILE = "child-anthropic"
SUBAGENT_ALLOWED_MODEL_PROFILES = ("child-anthropic",)
```

When the parent model issues `delegate_task(model_profile="child-anthropic")`, it can only pass this local alias; it cannot pass an endpoint, API key, real model ID, or custom auth header. When the alias is omitted, the child default profile is used, and failing that, the parent profile; an explicit alias that is unknown or not on the allowlist fails directly, with no quiet fallback (silently switching to another service).

### 2. A binding is a frozen dependency for one run

At startup, `ProviderCatalog` checks configuration completeness, whether the protocol is supported, whether numeric limits are reasonable, and whether the model supports tools. Once that passes, `bind()` creates an immutable `ModelBinding`. During the run, the model cannot be switched through global variables, which guarantees that parent and child requests do not contaminate each other.

The binding's fingerprint comes from non-authentication configuration facts. State, the session, and Trace store only credential-free summaries such as the profile, provider, protocol, and fingerprint; on resume, the binding is resolved again from local configuration, and no key or active connection is restored from the session. If configuration is missing or has changed, the system should report a clear error instead of switching to another provider automatically.

Old configuration still has a compatibility path: empty provider/profile configuration turns the old triple into `legacy-default`. New configuration must define providers and profiles completely; filling in only half of it cannot produce an ambiguous binding.

### 3. Adapters only translate; they do not make decisions for the Runtime

An adapter receives a uniform message list and tool schemas and returns a uniform assistant message, finish reason, and usage:

```python
ProviderResponse(
    message={"role": "assistant", "content": "...", "tool_calls": [...]},
    finish_reason="tool_use",
    usage=ProviderUsage(input_tokens=12, output_tokens=8, source="provider"),
)
```

The OpenAI adapter reassembles SSE chunks that arrive by index; the Anthropic adapter converts the top-level system prompt and `tool_use` and `tool_result` blocks into the internal format. When a response is cut off before `[DONE]` or a complete event sequence, or tool arguments are not a complete JSON object, the adapter returns a protocol error, and the executor never runs half a call.

The Runtime does not need to know these native fields. It still appends one assistant message and then a single `role=tool` result for each tool call in the model's order. Adapters do not run tools, change State, decide completion, or retry silently.

## Key Flow

When parent and child use different protocols, there is still only one run loop:

```text
start the CLI
  -> read the local catalog
  -> freeze the parent binding
  -> create the parent Runtime

parent Runtime
  -> parent binding -> OpenAI Chat Completions
  -> uniform assistant(tool_calls)
  -> delegate_task(model_profile="child-anthropic")
       -> check the profile allowlist before HTTP
       -> freeze the child binding -> Anthropic Messages
       -> independent child Context / usage meter
       -> one structured SubagentResult
  -> the parent Context receives one matching role=tool result
```

Context compaction summaries are model calls too, not free background steps: parent summaries use the parent binding, child summaries use the child binding, and each counts toward its own usage. When a provider returns no usage, a conservative estimate is used and marked `estimated`; when one run mixes both sources, it is marked `mixed`.

## Run and Observe

After you have configured two working providers/profiles locally, start the CLI with Bash/zsh:

```bash
PYTHONPATH=src python -m mini_agent
```

When you observe one delegation, parent requests should use the parent profile, and child requests a profile on the child allowlist; the parent Context still receives only one structured delegation result. When an unknown profile is written into `delegate_task`, it should be rejected clearly before any HTTP request, without contacting any service. After the command-line first task is handled, the CLI still enters the interactive loop.

## Implementation Breakdown

`providers/catalog.py` converts the local mappings into `ProviderConfig`, `ModelProfile`, and `ModelBinding`; `providers/openai_chat.py` and `providers/anthropic_messages.py` each handle auth headers, message conversion, streaming chunks, and protocol errors; `providers/http.py` uses the standard library `http.client`, with a separate connection per request and an explicit `Accept-Encoding: identity`.

`AgentRuntime` is still the only model—tool—observation loop; it only gains the binding and uniform usage fields. `ContextManager` uses the context window of the bound profile, and summaries use the same binding. `DelegationManager` completes the allowlist check and binding freeze before starting the child Runner.

## Why This Design

Putting provider selection in the catalog and protocol translation in adapters lets the Runtime maintain only one set of tool closure, permission, and completion rules. Writing "if Anthropic, then..." inside `run()` would gradually pollute the core control flow with protocol details and make error paths hard to audit.

An explicit profile allowlist and no automatic fallback are safety boundaries, not a sacrifice of usability: a fallback changes who receives the data, the permission environment, and who is billed, and in particular a subagent must not choose an unapproved service on its own. Configuration errors surface before the first HTTP request, so the user can fix them explicitly.

The cost is one more layer of provider/profile configuration, and adapters must handle two streaming protocols strictly; the old triple compatibility path keeps the original entry. This version deliberately does not handle lifecycles, aggregate budgets, cancellation, parallel delegation, or durable delegation records.

## Design Boundaries

- Provider-native messages do not enter the Runtime, Context, ToolExecutor, or State; internally only the normalized structure is used.
- Adapters do not run tools, change State, decide completion, retry, or read "the current global model".
- Parent and child bindings, usage meters, Contexts, and histories are independent; the parent still exclusively owns changes, permissions, plans, generation, verification, and the completion decision.
- State, the session, Trace, tool results, and user-visible errors contain no real endpoint, model ID, auth header, or API key.
- Old configuration maps to `legacy-default`; new configuration must be complete and explicit.
- This version is still a synchronous, depth=1, read-only subagent; later lessons handle aggregate budgets, cancellation, and parallelism.

## Version Features, Next Lesson, and Code Index

This lesson completes multiple providers, adapters for two protocols, independent parent and child profiles, a uniform response, and usage attribution. Parent and child still enter the same `AgentRuntime.run()`, every tool call still has a single `role=tool` result committed in order, and unauthorized profiles are rejected before going online.

The next lesson adds delegation lifecycles, cancellation, and aggregate budgets for the parent task, without changing the subagent's read-only boundary.

Core source:

- [`src/mini_agent/providers/base.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.36/src/mini_agent/providers/base.py)
- [`src/mini_agent/providers/catalog.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.36/src/mini_agent/providers/catalog.py)
- [`src/mini_agent/providers/openai_chat.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.36/src/mini_agent/providers/openai_chat.py)
- [`src/mini_agent/providers/anthropic_messages.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.36/src/mini_agent/providers/anthropic_messages.py)
- [`src/mini_agent/runtime.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.36/src/mini_agent/runtime.py)

For the full design, see [`docs/plans/subagent-delegation-plan.md`](../plans/subagent-delegation-plan.md); for configuration constraints, see [`docs/operation/manual.md`](../operation/manual.md).

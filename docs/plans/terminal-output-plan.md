# Terminal Output Implementation Plan

> Status: complete (A–D implemented and accepted)
> Scope: terminal output, streaming observation, and CLI interaction presentation
> Non-goals: color, Markdown, third-party dependencies, version numbers, changes to `AGENTS.md` or the main README

## 1. Goal

Provide the agent loop and CLI with a stable, readable, redirectable terminal output protocol, while keeping the model message history and tool results from being rewritten by the presentation layer:

- The user input prompt is fixed as `You › `.
- The assistant body lazily loads the `Assistant › ` header per streaming chunk; no empty header is printed when there is no body.
- Normal mode summarizes tool calls per batch and presents structured results in the original call order.
- Debug mode adds rounds, arguments, and bounded results; quiet mode hides the assistant body, progress, and runtime status.
- Explicit CLI notifications and permission confirmations stay visible in quiet mode.

## 2. Behavior Boundaries

`TerminalOutput` is responsible only for observational presentation; write failures must not affect the agent loop. Successful results in normal mode show only the tool name and a safe summary: file tools show only `path`, `run_shell` shows only `command`, and summaries are at most 100 characters; other arguments (including written content) are not shown. Failures, refusals, timeouts, and invalid results show a reason of at most 240 characters. Debug mode shows arguments and results, each at most 1200 characters. When tool results are fed back to the model, the full protocol content is still used, unaffected by terminal truncation.

`call_llm(..., on_content=...)` calls the observation callback per chunk when `stream_output` is in effect; when a callback is provided, the body is not printed additionally. Callback exceptions are isolated and do not affect SSE accumulation. With `stream_output=False`, it neither prints nor calls the callback, but still returns the complete assistant message; standalone streaming calls without a callback keep the standard output compatible behavior. The agent loop connects the callback to `TerminalOutput.assistant_delta()`.

## 3. Task Breakdown and Status

- [x] **A: Output renderer** — Implement the normal/debug/quiet modes, section line breaks, the lazy assistant header, tool batches, and bounded fields.
- [x] **B: agent loop / LLM wiring** — Add the `on_content` observation callback, keep the tool-call protocol history complete, and present results in call order.
- [x] **C: CLI and permission interaction** — Use a short prompt and keep explicit CLI notifications and permission confirmations; redirected or broken output streams must not break execution.
- [x] **D: Documentation and tests** — Add to the manual, CHANGELOG, configuration comments, and regression tests, covering quiet mode, callbacks, batch terminal states, and the protocol body boundary.

## 4. Acceptance Record

- The related pytest tests cover the `call_llm` callback/compatibility semantics, agent loop streaming and quiet mode, tool output boundaries, CLI prompts, and the permission transcript.
- Manual PTY and redirected output verification was done by root with a mock LLM and mock tools; the verification did not call a real API.
- The full repository acceptance commands follow `AGENTS.md`: pytest, the tutorial check, the README check, and `git diff --check`.

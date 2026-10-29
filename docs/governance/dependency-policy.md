# Dependency Policy

## Constraint

The project separates core runtime dependencies from peripheral user-experience dependencies: core flows use only the Python standard library; peripheral capabilities that are necessary and mainly improve the user experience may be enhanced with optional third-party dependencies.

Core flows include LLM HTTP calls, the agent loop, tool execution, the permission gate, AgentState, ContextManager, protocol handling, and the verification loop. Peripheral capabilities include terminal editing, display enhancements, and other interaction features that do not change execution semantics.

## Allowed Conditions

An optional dependency must meet all of these conditions:

- It is not part of the default install dependencies;
- Without it, a standard-library fallback or a degraded feature exists;
- It does not change the tool call protocol, permission boundaries, state model, or core error semantics;
- It is declared in `pyproject.toml` with an explicit extra and version range;
- The operation manual describes how to install it and how the fallback behaves;
- The default test suite does not need a network install of it; the enhanced path is covered by isolated tests.

## Consequences of a Violation

If a core module imports a peripheral dependency directly, or the default install pulls in a third-party dependency for a user-experience feature, this breaks self-contained deployment, offline smoke tests, and the reproducibility of teaching versions. Such a change must first update this policy and `AGENTS.md`, and only then change the code.

## Current Case

`prompt_toolkit` is used only for multiline CLI input. It lives in the input adapter layer and is installed through the `interactive` extra; without it, input falls back to the standard library `input()`, and the core Agent does not know about the dependency.

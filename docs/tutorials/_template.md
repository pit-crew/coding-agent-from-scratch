# Lesson X: Topic (v0.X)

Previous: [Previous lesson](previous-lesson.md) · [Tutorial overview](README.md) · Next: v0.Y (planned)

> Code snapshot: `v0.X` · Adjacent diff: `v0.X-1..v0.X` · Shell: Bash/zsh

> Patch snapshot (if needed): `v0.X.Y` · Patch baseline: `v0.X..v0.X.Y`

Keep the line above only when this lesson also covers a patch version; patch content must declare its own patch tag and baseline, and provide pinned source links for that tag.

> Requirements: Python 3.10+. If historical `pyproject.toml` metadata does not match the source syntax, state it clearly here.

## Lesson Goals

Center on one clear learning outcome. State the only new core concepts in this lesson, and what the reader should be able to explain or do after it. Prefer one teaching thread for the whole text, and do not describe later version behavior in advance.

## Problems in the Previous Version

In one or two plain paragraphs, describe the limits of the previous version, the problem this version solves, and how those problems affect normal use. Discuss only the differences between this version and the previous one.

## Prerequisites and Version Checkout

List the environment, the previous lesson, and reproducible version switch commands.

```bash
git checkout v0.X-1
git diff --stat v0.X-1..v0.X
git diff v0.X-1..v0.X -- <files relevant to this version>
git checkout v0.X
```

## New and Changed Files

First confirm this version's scope with `git diff --stat`, then fill in the file table. List only the files directly related to the lesson's teaching thread; do not use the full change list as tutorial text.

| File | Change | Purpose |
|---|---|---|
| `src/...` | ... | ... |

## Version Change Map

Show the structural change of this version against the previous one in the clearest way. When changes cross modules, change the call chain, or change the runtime flow, use a flow diagram, architecture diagram, sequence diagram, or an equivalent structured view; local changes can use a change table or a real diff. Do not repeat the same change just to satisfy a format.

Cross-module versions use "a baseline diagram of the previous version + a change diagram of this version" by default, with a legend before the diagrams:

```text
[old] in previous version    [+] new in this version    [~] changed in this version
[C] main consumer            [B] boundary of this version / not its responsibility
```

The baseline diagram must stand alone and show the previous version's real entry point, key call chain, data or message flow, and how it finishes. The change diagram must keep the related old nodes and mark this version's insertion points, new capability entry points, main consumers, the normal path, and at least one important failure/degradation path. Nodes must be modules, functions, state fields, or protocol steps that really exist at the corresponding tag, and arrows must show real calls, data flow, or control flow.

After the diagram, you can add a short change mapping table that maps nodes/edges to files and symbols, so that you do not just draw the changed file table as boxes. Use ASCII text diagrams that can be read directly by default, without external images or rendering services.

```text
Previous version:
entry -> existing module -> output

This version:
entry -> existing module -> new module -> output
                                |
                                +-> main consumer
                                +-> boundary/failure path
```

Modules, functions, and call order in the diagram must match the corresponding code tag; do not draw later-version capabilities into this lesson. Authors should check nodes and edges with `git show <tag>` or the real diff.

## Core Concepts and Data Structures

Introduce the concepts new in this version one by one along the teaching thread. Develop each concept in this order:

```text
problem to solve -> intuitive explanation -> minimal code snippet or real diff
                 -> what this code changes -> normal path and boundaries
```

Explain each term in plain English where it first appears. List data structures, inputs, outputs, return values, and related configuration only when they really help the main thread; do not list internal fields and functions first.

## Why This Design

Explain why this version chose the current approach instead of other viable ones; state the benefits, costs, resulting limits, and what this version intentionally does not solve.

## Design Boundaries

State clearly which scenarios this version supports and which it does not; describe the normal path, failure/degradation paths, exception boundaries, and protocol or safety invariants. Do not describe unimplemented capabilities as implemented.

## Key Flow

Use a code block or short flow diagram to show the entry, the main path, and at least one important failure or degradation path. Say what the reader should observe at runtime.

"Version Change Map" says what changed against the previous version; "Key Flow" says how the current version runs. One does not replace the other.

## Implementation Breakdown

Explain only implementation details that the core concepts did not cover, such as call order, default values, exception boundaries, and configuration items, and link to the source at the corresponding tag. Avoid repeating the earlier flow and boundary descriptions.

Give at least one minimal key code snippet or real `git diff` for each core concept, and explain in plain language the specific problem it solves, its inputs, outputs, and invariants; provide the full implementation only through pinned tag links.

## Run and Observe (If Needed)

Only when it helps the reader understand the lesson's concepts, give commands and observable results from a real usage flow. State the shell for each command, and write the key output or state change the reader should observe and how it maps to the lesson's concept. Call a command-line argument a "command-line first task", and state that the program then still enters the interactive loop. Do not add isolated minimal offline examples, test commands, or acceptance checklists.

## Version Features, Next Lesson, and Code Index

Summarize the capabilities unique to this version, preview the next lesson, and list the core implementation files this lesson covers. List test files only when they help understand the implementation. Source links must be pinned to the tag this lesson declares (if there is a patch, also list links for the patch tag):

```markdown
[src/mini_agent/example.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.X/src/mini_agent/example.py)
```

<!--
Author pre-commit self-check (do not keep in the lesson text):
- Sync the README, tutorial index, operation manual, CHANGELOG, and pyproject.toml version.
- Confirm that every command states its shell and uses PYTHONPATH=src python ...; CLI arguments are called a "command-line first task", without suggesting that the process exits right after.
- Confirm that default values, call order, failure paths, return values, configuration items, and protocol fields match the corresponding tag, and that terms are explained where they first appear.
- Confirm that source links are pinned to the declared tag, not to the default branch or local paths.
- Before committing, run:
  PYTHONPATH=src python scripts/check_tutorials.py
  PYTHONPATH=src python scripts/check_tutorial_facts.py
-->

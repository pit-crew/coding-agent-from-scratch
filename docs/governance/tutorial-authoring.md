# Tutorial Authoring Rules

This file defines the writing requirements for version lessons in `docs/tutorials/`. Tutorials are for developers who are new to Agents. They help readers understand how versions evolve and why design trade-offs were made. They are not version update summaries, test descriptions, or delivery checklists. The code is the source of truth for the implementation; plan documents describe intent and acceptance.

## Reader Baseline and Style

The default reader has basic Python and command-line skills but does not know Agents, the project architecture, or internal terms. You may use basic Python syntax, common terminal commands, and the most basic Git operations. Do not assume the reader already understands concepts such as the agent loop, tool calls, context, state, or permissions, and do not assume the reader knows this project's modules, classes, functions, or fields.

- The overall style must be plain, clear, and easy to understand. Prefer common English words and short, direct sentences. Avoid unnecessary jargon, chains of abstract nouns, long sentences, and unexplained internal abbreviations.
- First describe the problem the reader meets and its intuitive meaning, then introduce the precise technical name and the internal implementation. Do not list modules, fields, and functions first and leave the reader to connect them.
- When a technical term, abbreviation, or internal project concept first appears, explain nearby, in one plain sentence, what it is and what problem it solves. Expanding an abbreviation alone does not count as an explanation.
- Before code, a real diff, a command, or a diagram, say why the reader should look at it. After it, point out the key content, the expected result, and what it shows. Do not treat the material itself as the conclusion.
- Each paragraph expresses one main idea and adds only the new concepts needed for the current content. If you remove internal symbol names, the problem, approach, and conclusion must still read coherently.
- Plain does not mean imprecise. Protocols, safety, call chains, and similar topics still use precise terms with explanations. Do not use analogies that hide real behavior or boundaries.

## Content Principles

- Each lesson covers only the core concepts the current version adds over the previous version, and provides `git checkout` / `git diff` entry points. Do not describe later version behavior in advance.
- Each lesson must declare, at the top, its single code snapshot tag, its adjacent diff baseline, and the shell the example commands use. Patch content must declare its own patch tag and baseline.
- First explain the limits of the previous version and the problem this version solves, then the implementation, key trade-offs, and boundaries.
- Default values, call order, failure paths, return values, configuration items, and commands must match the implementation at the corresponding tag.
- Keep one teaching thread. Keep code snippets minimal; for full implementations, use pinned links of the form `https://github.com/liiiiiiiiil/agent-from-scratch/blob/<tag>/<path>`. Do not link to the default branch or to the author's local paths.
- For topics such as protocols, safety, concurrency, budgets, and exception degradation, describe the normal path, the invariants, and the problems the version intentionally does not solve.
- Introduce each core concept in this order: the problem to solve, an intuitive explanation, minimal code or a real diff, then the run result and boundaries. Do not list internal modules, fields, and functions first and leave the reader to connect them.
- The teaching thread is more important than the number of sections. Merge related content. Do not repeat the same fact in "Core Concepts", "Key Flow", "Implementation Breakdown", and "Design Boundaries". When a file table, flow diagram, mapping table, and code snippet express the same content, keep only the one that helps understanding most.
- "Run and Observe" does not only give commands. It also says what key result the reader should see and how that result demonstrates the lesson's concept. Do not give only a start command without expected output or state changes.
- Each lesson centers on one clear learning outcome. Give run commands and observations only when they help the reader understand the concept. Do not make isolated offline examples a fixed section.

## Lesson Structure

In principle a lesson contains: version/previous/next navigation; the code tag and adjacent diff baseline; goals; prerequisites and tag checkout; the changed file table and `git diff --stat`; the version change map; the problem in the previous version; core concepts, flow, and data structures; implementation breakdown; why this design; design boundaries; and version features, a next-lesson preview, and a tag-pinned code index. Sections can be merged or shortened, but the learning thread must not break. Each core concept needs at least one nearby key code snippet or real diff, with an explanation of the specific problem it solves.

The "Version Change Map" answers "what did this version change compared with the previous version, and where". This is different from "Key Flow", which answers "how does the current version run". For versions that cross modules, change the call chain, or change the runtime flow, use by default "a baseline diagram of the previous version + a change diagram of this version". Local function, single tool, or configuration changes can use a change table or a real diff. Diagrams must use a legend that marks `[old]` already in the previous version, `[+]` new in this version, `[~]` changed in this version, `[C]` main consumer, and `[B]` boundary of this version / not its responsibility.

The baseline diagram must stand alone and show the previous version's real entry point, key call chain, data or message flow, and how it finishes. The change diagram must keep the related old nodes and mark this version's insertion points, new capability entry points, main consumers, the normal path, and at least one important failure/degradation path. Nodes must be modules, functions, state fields, or protocol steps that really exist at the corresponding tag. Arrows must show real calls, data flow, or control flow. After the diagram you can add a change mapping table that maps nodes/edges to files and symbols. A diagram must not only repeat the list of changed files. Authors must check nodes and call order with `git show <tag>` or the real diff, and must not draw later-version capabilities into the current lesson.

By default use ASCII text diagrams that can be read directly, without external images, image hosts, or extra rendering services. If you use Mermaid or a similar format, keep the readable source.

"Why This Design" is a required reader-facing section. It explains the alternatives, the current trade-off, the resulting limits, and the problems this version intentionally does not solve. Historical lessons may use "Why This Version Is Needed" as an equivalent title; new lessons use "Why This Design".

Tutorial commands use Bash/zsh by default and are written as `PYTHONPATH=src python ...`. PowerShell equivalents are described only once, in the tutorial overview. A CLI call with a command-line argument is called a "command-line first task"; do not suggest that the process exits right after it handles the argument.

## Sync and Acceptance

When a version is complete, sync the README, the tutorial index, the operation manual, CHANGELOG, and the version in `pyproject.toml`, and check links, code snippets, commands, and protocol descriptions. Test coverage, full verification commands, and version delivery acceptance are kept in plan documents, governance rules, and automation scripts, not in tutorials.

`scripts/check_tutorials.py` checks only tutorial structure and format; `scripts/check_tutorial_facts.py` uses local Git objects to check version/tag mappings, adjacent baselines, and pinned source paths. Run both before you commit a tutorial.

## Pre-Commit Self-Check

- A reader can understand the goal, changes, design trade-offs, and how to run the lesson from this lesson and the previous one alone, without verbal help from a maintainer.
- New terms, abbreviations, and internal project concepts have an intuitive explanation where they first appear; the text lets the reader understand the problem and goal before it introduces internal implementation names.
- Each code block, diff, command, and diagram states its purpose, key content, and the expected result; the reader does not have to derive the conclusion alone.
- The text does not depend on implicit background that only maintainers know; with internal symbol names removed, an Agent beginner can still restate each section's problem, approach, and conclusion.
- All commands state Bash/zsh or another shell; commands, defaults, and protocol fields follow the corresponding code tag, and source links are pinned to that tag.
- Cross-module versions provide both the previous version's baseline diagram and this version's change diagram; the legend, entry points, change insertion points, main consumers, failure/degradation paths, and boundaries are all marked and checked against the tag/diff.
- "Why This Design" explains benefits, costs, and unsolved problems, and does not describe capabilities this version intentionally does not support as implemented.
- Do not add sections such as "Minimal Offline Example", "Tests and Acceptance", or test coverage lists. Test files may be cited in the source index only when they help understand the implementation; that content is maintained by plans, governance, and automated checks.
- Lessons are written in English. The required section headings are those checked by `scripts/check_tutorials.py`, and the version line uses the form ``> Code snapshot: `vX` · Adjacent diff: `vA..vB` · Shell: Bash/zsh``; the first version uses `none (first version)` as its adjacent diff, and patches use `Patch snapshot:`.

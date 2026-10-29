# Plan Documents

This directory holds the roadmap, feature plans, and task breakdowns.

## Index
- This directory is the authoritative source for the roadmap and plan documents. Runtime hard constraints and the condensed architecture index are in `AGENTS.md`.
- [`teaching-repo-plan.md`](teaching-repo-plan.md) — The full plan for turning the repository into a multi-stage teaching repository (version slicing, directory structure, document templates, git operation checklist, acceptance criteria).
- [`context-management-plan.md`](context-management-plan.md) — Stage 4 Context Management implementation plan (v0.11 architecture / v0.12 budget trimming / v0.13 compaction).
- [`project-task-orchestration-plan.md`](project-task-orchestration-plan.md) — Stage 5 project awareness and task orchestration implementation plan (v0.14 project instructions / v0.15 task list and state / v0.16 plan-driven execution; the English identifiers are Project Instructions, Todo / Task State, and Plan-driven Execution).
- [`reliable-execution-plan.md`](reliable-execution-plan.md) — Stage 6 reliable execution implementation plan (v0.17 Failure Model / v0.18 Recovery Policy / v0.19 Checkpoint / Rollback / v0.20 Repair Loop / v0.21 Trace & Replay).
- [`adaptive-planning-plan.md`](adaptive-planning-plan.md) — Stage 7 adaptive planning and replanning implementation plan (v0.22 Plan Contract / v0.23 Plan Mode & Handoff / v0.24 Replanning Policy / v0.25 Plan Trace & Evaluation).
- [`process-management-plan.md`](process-management-plan.md) — Stage 8 process management implementation plan (v0.26 background processes / v0.27 process observation / v0.28 process control / v0.29 bounded pipe stdin; PTY to be evaluated later).
- [`session-persistence-resume-plan.md`](session-persistence-resume-plan.md) — Stage 9 session persistence and resume implementation plan (v0.30 session persistence / v0.31 safe resume / v0.32 durable tool boundaries / v0.33 crash recovery).

Stage 9 is complete: v0.30–v0.33 implement safe point saving, cross-process resume, durable tool boundaries, and the handoff of uncertain calls after a crash; source sessions are not overwritten, and old calls are not replayed automatically.
- [`subagent-delegation-plan.md`](subagent-delegation-plan.md) — Stage 10 controlled subagent delegation implementation plan; v0.34 minimal synchronous read-only delegation, v0.35 shared parent/child run loop, v0.36 multiple providers/unified protocol adaptation, v0.37 lifecycle and aggregate budget, v0.38 bounded parallelism, and v0.39 durable delegation delivery are implemented. Subagents stay read-only and single-level, and the parent Agent exclusively owns changes and the completion decision.
- [`memory-retrieval-references-plan.md`](memory-retrieval-references-plan.md) — Stage 11 lightweight memory, relevance retrieval, and reference material implementation plan; v0.40–v0.42 workspace durable Memory, relevance retrieval, and named local References are implemented.

Stage 11 has completed v0.40–v0.42: workspace Memory supports explicit CRUD and relevance retrieval, the parent Context can temporarily inject untrusted candidates within budget, and the parent Agent can consult permission-protected local material by stable alias.
- [`mcp-skills-plan.md`](mcp-skills-plan.md) — Stage 12 MCP and Skills implementation plan; v0.43–v0.46 implement stdio/restricted HTTP MCP, parent-side MCP Tools, text Resources, text Prompts, and local on-demand Skills.
- [`agent-collaboration-plan.md`](agent-collaboration-plan.md) — Stage 13 lightweight Agent Collaboration implementation plan; v0.47–v0.49 are implemented, keeping single-level read-only subagents and the parent Agent's exclusive execution rights.
- [`evaluation-regression-plan.md`](evaluation-regression-plan.md) — Stage 14 evaluation plan; the v0.50 live chain is complete, the v0.51 suite 1.1 coding baseline is not complete, and the v0.52 suite 1.6 reliability live baseline is not complete; the v0.53 comparison implementation and offline acceptance are listed separately, and live still awaits the user reviewing the manifest and starting it explicitly.
- [`v053-regression-comparison-plan.md`](v053-regression-comparison-plan.md) — The contract, isolated runs, metrics, delivery status, and live authorization boundary of the v0.53 regression comparison and Memory automatic retrieval ablation.
- [`terminal-output-plan.md`](terminal-output-plan.md) — Implementation plan for terminal output, streaming observation, CLI interaction, and the three output modes (A–D complete).

## Document Conventions
- File names use lowercase with hyphens, for example `add-shell-tool.md`.
- Each document should include: goal, approach, task breakdown, and acceptance criteria.
- After completion, update the matching plan, the tutorial index, CHANGELOG, and version information; update `AGENTS.md` only when runtime constraints change.

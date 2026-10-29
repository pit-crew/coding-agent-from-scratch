# How to Use These Tutorials

This directory holds the **authoritative tutorials**, revised continuously on the default branch. The lesson number is the learning order, the package version is the release version, and the Git tag is the code snapshot. Lesson 50 introduces single-task evaluation, lesson 51 a frozen coding task set, lesson 52 separates fault boundaries from Agent recovery results, and lesson 53 covers version regression comparison and Memory retrieval ablation. Each lesson declares its tag and adjacent diff baseline at the top; maintainers create new version tags manually.

The latest lesson is [Lesson 53: How to Compare Two Agent Conditions Fairly](53-regression-comparison.md), in Stage 14. It introduces fixed version sources, three comparison groups, paired slots, and automatic Memory retrieval ablation; the v0.53 live batch still requires the user to review the manifest and start it explicitly.

## Prerequisites

- Reading the lessons requires basic Python and Git; to run examples that need an LLM, also prepare a reachable LLM gateway.
- Read [the full learning path in the main README](../../README.md#learning-path), or choose an entry point from the three routes below.
- Historical tags may not have the current `docs/tutorials/`, and may still use an older way of loading configuration. Prepare the environment as the lesson text says; do not apply the current mainline `config_local.py` mechanism to `v0.01`, and do not write real keys into tracked configuration.

## Three Learning Routes

1. **Full route**: start at [Stage 1](../../README.md#stage-1) and read through lesson 53 in [Stage 14](../../README.md#stage-14).
2. **Build a Mini Agent first**: complete [Stage 1](../../README.md#stage-1) to [Stage 3](../../README.md#stage-3), then do the Stage 3 practice task; after `v0.10` you already have a basic programming task loop.
3. **Look up by capability**: enter a specific lesson from [the lesson table in the main README](../../README.md#learning-path), then go back to the previous stage to fill in prerequisites.

Read each lesson as "problem → diff → run → observe → trade-offs": first the limits of the previous version, then locate the change with tag-pinned source or a real diff, run the lesson commands, observe the result, and finally understand the boundaries and unsolved problems.

## Environment Setup

Clone the repository once, and choose an installed or no-install setup as the current lesson says:

```bash
git clone https://github.com/liiiiiiiiil/agent-from-scratch.git
cd agent-from-scratch
```

The mainline usually keeps local configuration in `src/mini_agent/config_local.py`; historical lessons follow their own text and tag. Lesson commands use Bash/zsh by default; for no-install runs, prefix commands with `PYTHONPATH=src`. In PowerShell, first run `$env:PYTHONPATH="src"`, then run the matching `python ...` command.

## Version Workflow

Read the latest tutorials on the web or the default branch; locally, switch to the lesson's declared tag only to run its code:

```bash
git switch --detach v0.08
git diff v0.07..v0.08
# Run and observe as the lesson describes
git switch -                 # Return to the branch you were on
```

`git tag` shows which snapshots exist. Patch tags also follow the lesson declaration, for example `v0.18` → `v0.18.1`; do not treat lesson numbers, package versions, and tags as the same concept.

> Language note: the code at historical tags uses Chinese prompts, comments, and terminal messages. The lessons show those strings and sample outputs translated into English, so when you run a historical tag, the text you see can be Chinese while its structure matches the lesson.

## Stage 3 Practice Task

After `v0.10`, ask the Agent to examine a failing test, find the cause, change the code, run the tests, and summarize the result. Use it to verify the basic working loop.

## For Learners and Authors

If you have a problem running something, first check the [full manual](../operation/manual.md); if you still cannot tell what is wrong, open an Issue. To add a lesson, start from [`_template.md`](_template.md) and read the [tutorial authoring rules](../governance/tutorial-authoring.md) and the [main README authoring rules](../governance/readme-authoring.md); author acceptance commands and commit rules follow the governance documents.

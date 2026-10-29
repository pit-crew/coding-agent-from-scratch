# Lesson 47: Giving subagents roles

Previous: [Restricted HTTP MCP, text Resources, and Prompts](46-mcp-http-resources-prompts.md) · [Tutorial overview](README.md) · Next: [In-process background subagents](48-background-subagents.md)

Code snapshot: `v0.47` · Adjacent diff: `v0.46..v0.47`

The commands in this lesson use Bash/zsh; the commands, code links, and examples all correspond to `v0.47`.

## Lesson Goals

An Agent is a program that asks a language model questions and calls tools as needed to complete a task. The Agent working on the user's task can hand part of the work to another independent Agent; the former is called the "parent Agent", and the one doing the restricted investigation is called the "subagent".

In the previous version, all subagents used the same general instructions and read-only tools. The parent Agent could say "please review the code" in the task text, but the runtime could not limit the subagent's responsibilities based on that. This lesson adds `agent_profile` to `delegate_task`: the parent Agent can choose a built-in role such as `reviewer`, or load a custom role from local configuration.

After reading, you should be able to explain in your own words: the role decides how the subagent works and which tools it may use; `model_profile` chooses which configured model it uses. Old calls that choose no role still run as before.

## Prerequisites and Version Checkout

You only need basic Python, a terminal, and Git. You do not need to understand the Agent's internals first; for now, think of a "subagent" as an independent helper with narrower permissions that does only read-only investigation. To see how it first appeared, read [Lesson 34: Minimal delegation](34-minimal-delegation.md).

First look at the file changes from the previous version to this one, then switch to the pinned code snapshot:

```bash
git checkout v0.46
git diff --stat v0.46..v0.47
git checkout v0.47
```

After reading, run `git checkout -` to return to the branch you were on before switching.

## Problems in the Previous Version

In v0.46, `delegate_task` is a synchronous delegation: after the parent Agent issues the call, it waits for the subagent to finish before receiving the result. It hands every subagent one fixed list of read-only tools, so there is no explicit role setting to distinguish "find the implementation entry", "review for defects", or "analyze the tests".

Handing the parent Agent's whole set of tools and authorizations directly to a subagent could let it do things the parent task never delegated. v0.47 lets the parent-side configuration list each role's responsibilities and tools explicitly, and checks these limits before creating the subagent.

## New and Changed Files

| File | Change | What you can see here |
|---|---|---|
| [agent_profiles.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.47/src/mini_agent/agent_profiles.py) | New | How built-in and local roles are validated and frozen. |
| [delegation.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.47/src/mini_agent/delegation.py) | Changed | How the role, tool scope, model, and authorization results are handed to the subagent. |
| [tools/delegation.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.47/src/mini_agent/tools/delegation.py) | Changed | How `delegate_task` accepts an optional role. |
| [skills.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.47/src/mini_agent/skills.py) and [tools/skill.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.47/src/mini_agent/tools/skill.py) | Changed | How a subagent sees only approved Skills. A Skill is a local operating instruction the Agent reads on demand. |
| [state.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.47/src/mini_agent/state.py), [session.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.47/src/mini_agent/session.py), [trace.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.47/src/mini_agent/trace.py) | Changed | How State (task facts and progress), the session (the saved task file), and Trace (event records for read-only replay) check the role identity. |
| [config_example.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.47/src/mini_agent/config_example.py) | Changed | What shape local role configuration should take. |

## Version Change Map

First look at the synchronous call path already in v0.46. It shows that this lesson adds role limits on top of the existing delegation entry:

```text
[old] parent Agent
  → delegate_task argument check and authorization
  → the subagent uses the general prompt and fixed read-only tools
  → wait for the investigation to finish
  → hand the result back to the parent Agent
```

v0.47 adds role selection, a tool intersection, and Skill authorization to this path. The "tool intersection" in the diagram means: the tools the subagent can finally use must appear in the project allowlist, the role's allowed list, and this request's tool list at the same time.

```text
[old] parent Agent
  → [~] delegate_task (optional agent_profile)
  → [+] agent_profile: choose a built-in or local role
  → [C] the parent side validates the role, model, and tool scope
  → [C] the parent side checks each Skill the role requests
  → [~] build a restricted subagent → call an independent child Agent → return the report
  → [B] invalid role/model or no common tools → rejected before the child model request
```

Legend: `[old]` already in v0.46, `[+]` new in v0.47, `[~]` changed, `[C]` main validator or user, `[B]` boundary of this version. Arrows show calls or data flow. The most important change here is that the role first becomes explicit limits on the parent side, and only then does the subagent start working.

## Core Concepts and Data Structures

### 1. Roles and models answer different questions

The role answers "how this investigation should be done and which tools can be used"; the model alias answers "which locally configured model runs it". For example, `reviewer` is a role, while `model_profile` chooses an alias from the local model configuration. If the role specifies a model, that model is used; otherwise the existing default subagent model is kept. If the caller also passes a model alias, it must match this final choice, otherwise the call is rejected before the child model request is sent.

The built-in roles are `explorer`, `reviewer`, `tester`, and `general`. All of them can use only tools in the subagent read-only allowlist. Below is a sketch of the key fields in a call; a real call also needs the task goal, scope, constraints, and so on:

```json
{
  "agent_profile": "reviewer",
  "requested_tools": ["read_file", "grep"]
}
```

`requested_tools` is the tool request the parent Agent makes for this one investigation. The runtime also checks whether paths are within the task scope; writing a tool into the request does not by itself bypass that check.

### 2. Custom roles are frozen when the task starts

Custom roles are written in the local untracked `config_local.py`; real keys or private configuration should not be put into example files. Each role needs at least a responsibility description, subagent instructions, and a tool list; the model, permissions, and Skills are optional:

```python
AGENT_PROFILES = {
    "api_reader": {
        "description": "Trace the read-only implementation path of an API",
        "prompt": "Point out the entry, the call relationships, and the file evidence supporting the conclusions.",
        "tools": ["read_file", "grep"],
        "permissions": {"grep": "allow"},
        "skills": [],
    },
}
```

`permissions` can only set `allow` or `deny` on the role's own tools. `deny` removes the matching tool from the tools available this time; a role cannot use configuration to expand the subagent's overall allowlist. When the Agent Runtime (the run loop that arranges model requests, tools, and results) is created, it checks and freezes the local role definitions, so changing the configuration during a run does not quietly change the task in progress.

Only the role ID and a configuration fingerprint are saved for State, the session, and Trace to check. The fingerprint is a digest used to detect whether the configuration changed; the role's prompt text does not enter these summaries because of it.

### 3. Skills are still authorized one by one by the parent Agent

A role listing a Skill only means the subagent "may request to read it", not that it has permission. Before the subagent starts, the parent Agent asks the current permission policy about each exact Skill ID. Skills that are denied or forbidden by policy do not appear in the subagent's catalog or tools; when the configuration references a nonexistent Skill, the delegation fails.

If approved, the subagent reads the body on demand through `skill(name)`. A Skill body is only material returned by an ordinary tool; it cannot grant new tool permissions such as shell, and it cannot override protected system instructions. A Skill body does not enter State or Trace summaries and cannot prove that the parent task passed verification; with `/save` on, a loaded body may still be saved in the session as ordinary tool history, so session files should be protected like task material.

Old delegations that pass no `agent_profile` do not get the role Skill capability.

For example, the field below means the role may request to read the Skill named `api-contracts`; it does not by itself approve that read:

```json
{
  "skills": ["api-contracts"]
}
```

### 4. tester can only analyze tests, not run them

Below is a sketch of the key fields when `tester` is chosen; a real call also includes the goal and file scope:

```json
{
  "agent_profile": "tester",
  "requested_tools": ["read_file", "grep"]
}
```

`tester` can read implementation and test code and suggest which commands to run or which cases to add; it has no tool to run tests and cannot write a suggestion as "the tests already passed". Whether tests are run is still decided by the parent Agent according to its own task flow. The subagent's report is only investigation material and cannot replace verification by the parent Agent.

## Why This Design

Putting roles in local configuration lets the parent Agent choose a fixed set of responsibilities and tool boundaries with one short ID. Keeping the model alias separate avoids merging "what to do" and "which model does it" into one setting.

The cost is stricter configuration: a wrong role, model, or Skill is not replaced by a guessed alternative; the tool list a role gives can only narrow existing permissions. This keeps parent-side authorization as the only entry, and the subagent does not inherit all of the parent Agent's capabilities.

## Design Boundaries

The subagent of v0.47 is still synchronous, single-level, and read-only. The parent Agent must wait for this round's subagent to finish; the subagent cannot change files, run shell, access external tool services, create plans, verify, or decide that the parent task is complete. `tester` can only suggest tests; the parent Agent must still run and check the verification results itself.

This version does not yet have background starts, collecting results later, or continuing the same child session across processes. The first is introduced in the next lesson, and the last waits until Lesson 49.

## Key Flow

Read the steps below as a process of "check permissions first, then start the delegation":

```text
the parent model proposes delegate_task
  → the parent side resolves the role and model
  → take the intersection of the project allowlist, the role's tools, and this request's tools
  → the parent side authorizes each Skill the role requests
  → build a subagent that has only the approved tools/Skills
  → the subagent investigates and returns a structured report
  → the parent side records the role summary and receives the report

invalid role, model, or tool scope: rejected before the child model request
Skill denied: that Skill is not handed to the subagent
```

## Run and Observe

After configuring a local model, start a read-only review task with Bash/zsh:

```bash
PYTHONPATH=src python -m mini_agent "review, read-only, the HTTP retry boundary in src/mini_agent"
```

Observe whether the parent model calls `delegate_task` and chooses `reviewer`. If the call succeeds, the subagent still finishes its investigation first, and only then does the parent Agent continue; the role ID and configuration fingerprint appear in the structured result. If a role Skill was used, the authorization prompt shows the Skill IDs one by one; after you deny an ID, the subagent cannot see it. These observations show, respectively, that the role identity was recorded and that Skill access is still controlled by the parent side.

## Implementation Breakdown

Argument checking resolves the role from the frozen role catalog and checks any explicit model alias; the delegation contract (which records the goal, scope, and limits of this child task) then carries the effective tool subset and the role fingerprint. Calls without a role keep the old contract shape.

Before the child task starts, the delegation manager checks each Skill through the parent-side PermissionGate (the permission check that decides whether a tool may be used). The subagent then receives an independent view containing only the approved tools and Skills and runs the project's shared Agent Runtime. The subagent gets no parent State, parent permissions, or parent verification evidence.

To compare with the implementation, see [role configuration validation](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.47/src/mini_agent/agent_profiles.py), [the delegation run flow](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.47/src/mini_agent/delegation.py), and [role tool registration](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.47/src/mini_agent/tools/delegation.py).

## Version Features, Next Lesson, and Code Index

This version lets the parent Agent carry out synchronous read-only investigations with fixed built-in roles or local custom roles, and the parent side approves, one by one, the Skills a role can request. Old calls that specify no role keep the original behavior.

The next lesson handles "the parent Agent does not have to wait for the subagent to finish": the subagent first runs in the background inside the current process, and the parent Agent later queries its status and collects the result.

Code index pinned at v0.47: [role catalog](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.47/src/mini_agent/agent_profiles.py), [delegation execution](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.47/src/mini_agent/delegation.py), [Skills catalog](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.47/src/mini_agent/skills.py), [parent/child tool views](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.47/src/mini_agent/tools/base.py), [durable result validation](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.47/src/mini_agent/session.py).

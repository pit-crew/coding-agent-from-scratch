# Lesson 45: Giving the Agent a local Skill

Previous: [Letting the Agent call MCP Tools](44-mcp-tools-runtime.md) · [Tutorial overview](README.md) · Next: [MCP HTTP, Resources, and Prompts](46-mcp-http-resources-prompts.md)

Code snapshot: `v0.45` · Adjacent diff: `v0.44..v0.45`

The commands in this lesson use Bash/zsh. The code links and examples below all correspond to `v0.45`.

## Lesson Goals

Sometimes we want the Agent to follow a set of working steps, such as "read the files first, then change them, then verify". Writing the steps into an executable script would let the script bypass the Agent's tool authorization; stuffing all instructions into the model prompt every time would also let irrelevant content take up context.

This lesson solves the problem with a Skill. A Skill is a local working instruction, not executable code, and it adds no new operation permissions. The Agent first sees its name and a short description; when it needs the body, it requests it through `skill(name)` and goes through a permission check. After reading, you should be able to explain how a Skill enters the model's working context, and why it cannot authorize the Agent to run commands.

## Prerequisites

You only need basic Python, a terminal, and Git. Read Lesson 44 first to learn how the Agent receives the model's tool requests and checks authorization.

Two concepts are used here: the Context is the background information and conversation content the Agent prepares for the current model request; the Context has a length limit and is trimmed when exceeded. The PermissionGate is the authorization check before a tool runs; Skills also go through this check by default and cannot bypass it just because they are text.

View the changes from the adjacent version and switch to this lesson's code:

```bash
git checkout v0.44
git diff --stat v0.44..v0.45
git checkout v0.45
```

After reading, use `git checkout -` to return to the branch you were on before switching.

## New and Changed Files

The Skill flow has three parts: discovery, showing the description, and reading the body on demand:

| File | Responsibility |
|---|---|
| [skills.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.45/src/mini_agent/skills.py) | Discovers Skills from two fixed local directories and reads files safely. |
| [tools/skill.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.45/src/mini_agent/tools/skill.py) | Registers the `skill(name)` read entry. |
| [context.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.45/src/mini_agent/context.py) | Adds the Skill descriptions that satisfy the current permission rules to the model request. |
| [permission.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.45/src/mini_agent/permission.py) | Asks for authorization separately for each Skill body read. |
| [tools/base.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.45/src/mini_agent/tools/base.py) | Hands the body to the model while limiting the summary recorded in State and Trace. |

## Version Change Map

The Agent loop already in v0.44 tells the model which Tools are available and runs tools after the model requests them. This version keeps that execution path and adds a Skill description list for the Context to show, plus a tool that reads the body on demand.

```text
[old] already in v0.44:
[old] Tools in the Registry → [old] Context prepares the model request → [old] AgentRuntime
                                                                → [old] ToolExecutor → [old] role=tool result

[+] new in v0.45:
[+] skills/<name>/SKILL.md
  → [+] SkillCatalog discovers and checks the files
  → [~] Context adds Skill descriptions (name, source, description only)
  → [C] the model requests skill(name)
  → [C] the PermissionGate authorizes, then the body is read
  → [old] ToolExecutor hands the body to the model as role=tool material
       ├─ [B] authorization denied or file changed: no body provided
       └─ [B] the body does not authorize later tools and does not enter Subagents
```

Legend: `[old]` already in v0.44; `[+]` new in v0.45; `[~]` changed in v0.45; `[C]` main consumer; `[B]` boundary of this version. `SkillCatalog` can be understood as the current Runtime's Skill directory. It reads the fixed directories at startup and freezes the discovery result; a body is not read into the model request automatically just because it was "discovered".

## Key Flow

### 1. Discovery reads only the description

Skills live in `skills/<name>/SKILL.md` at the workspace root, or in `~/.mini_agent/skills/<name>/SKILL.md` in the user directory. The start of the file needs a simple description block in the format below, called frontmatter:

```markdown
---
name: verify-change
description: Read first, then change, then verify
---
# The body starts here
1. Read the relevant files.
2. Make the change.
3. Explain how to verify it independently.
```

`name` must match the folder name. v0.45 accepts only the two single-line fields `name` and `description`, does not parse full YAML, and never runs code in the body.

When the Agent prepares a model request, the Context puts the names, sources (project or user level), and descriptions of the Skills allowed to be shown into an ordinary information message. This way the model can judge that a Skill might be useful without receiving every body in every round. Skills forbidden by the permission rules do not appear in the descriptions.

### 2. Asking again when the body is read

If the model decides to use `verify-change`, it submits a tool request like this:

```json
{"name":"skill","arguments":{"name":"verify-change"}}
```

The PermissionGate asks by default whether to allow reading this Skill. Choosing `always` remembers only this Skill's exact name and does not authorize other Skills. After the check passes, the program safely reopens the matching `SKILL.md`, confirms the file is still the one seen at discovery, and hands the body to the model as an ordinary `role=tool` result.

The model can see the body because it needs to arrange its work according to the instructions. The Agent's structured task record and execution events store only summaries such as the Skill name, source, and length, without copying the whole body. If `/save` (the command that saves the current session) is on, the body may still be saved with the session as part of ordinary tool history.

### 3. Describing a step is not approving it

A Skill can suggest "run the checks after making the change", but that sentence is not authorization to run a command. The actual command is still a separate tool request and must pass its own argument, plan, and permission checks. A Skill also cannot change files directly, advance the plan for the user, produce verification evidence, or have its content inherited by subagents.

## Implementation Breakdown

The project-level directory takes priority over the user-level directory. A valid project Skill with the same name overrides the user-level version; if a project-level item with the same name has an invalid format, the program blocks falling back to the user-level item with that name, so you never believe you are using the project's instructions while actually reading another one.

Directories, names, and descriptions all have format and size limits. Discovery saves the directory and file identity; reading refuses symlinks, file replacement, encoding errors, and size changes. Skills are discovered only when the Runtime is created, so after editing a file you must start a new task to get the new catalog.

Subagents (read-only investigation instances sent out by the parent Agent) have no Skill tool, catalog hints, or bodies. The parent Agent's tools, permissions, and conversation are not passed to them either.

## Why This Design

Keeping Skills separate from Tools keeps "suggesting how to do it" and "allowing what can be done" as two different things. Putting the body in the protected system prompt would blur the trust boundary; writing the instructions as an automatically run script might bypass existing tool authorization. Loading on demand also reduces the background content the model has to process every round.

Fixed directories, a restricted format, and freezing the catalog when the Runtime starts give up hot updates and complex Skill formats in exchange for stable, easily checked read behavior. This version does not scan accessory files, does not run scripts, and does not support remote Skills or full YAML.

## Run and Observe

The repository at this lesson's version includes the example `skills/verify-change/SKILL.md`. First look at the file content:

```bash
sed -n '1,80p' skills/verify-change/SKILL.md
```

If you have configured a local model, you can explicitly ask the Agent in the parent CLI to read `verify-change`. The expected behavior: the Agent first requests to read the Skill, and the terminal shows a `skill` permission prompt; only after authorization does the model receive the body. If the Agent then requests `run_shell` or a file write, the matching tool's own authorization flow still appears. The two separate authorizations show that a Skill provides working instructions, not operation permission.

## Design Boundaries

- Only the direct subdirectories of the designated `skills` directories in the workspace and user directory are scanned; there is no recursive search, and a Skill's accessory files are not read.
- Skill descriptions and bodies are untrusted material: the model can use them as reference information, but they cannot override user requests, project instructions, the plan, or permission rules.
- Skill bodies enter ordinary tool history; with `/save` on, they may be saved in the session.
- Skills are provided only to the parent Agent; they do not become verification evidence and are not passed to Subagents.

## Version Features, Next Lesson, and Code Index

v0.45 adds discovery of local Skills, display of their descriptions, and safe reading after authorization. The next lesson distinguishes three uses of MCP: Tools the model can request, Resources chosen by the application, and Prompts the user previews and then submits.

Pinned code index: [skills.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.45/src/mini_agent/skills.py), [tools/skill.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.45/src/mini_agent/tools/skill.py), [context.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.45/src/mini_agent/context.py), [permission.py](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.45/src/mini_agent/permission.py).

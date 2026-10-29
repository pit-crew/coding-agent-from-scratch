# Lesson 42: Reading local reference material by stable names

Previous: [Relevant memory retrieval and bounded context](41-memory-retrieval.md) · [Tutorial overview](README.md)

> Code snapshot: `v0.42` · Adjacent diff: `v0.41..v0.42` · Shell: Bash/zsh

## Lesson Goals

Lessons 40 and 41 handle the workspace's own Memory: it suits a small amount of explicitly recorded project knowledge. Now
think of another scenario: the team has an offline design document directory outside the workspace, and you want the Agent to consult it when needed,
without copying the whole directory into the project and without exposing the real local path to the model.

This lesson adds local References (reference material). In local configuration, the user gives a directory a stable alias; the Agent
first sees the alias and its description, then searches or reads files in the directory as needed. It is a read-only information entry, not a remote repository,
and not a second Memory that is injected into the context automatically.

After this lesson, you should be able to answer:

- Why the model sees an alias rather than the real local path;
- Why "can be discovered" does not mean "already approved for reading";
- Why every search and read must recheck the relative path and symlinks;
- Why a Reference read is still only material for the model to judge and cannot replace verification of the current task.

## Prerequisites

First read [Lesson 41: Letting the Agent find relevant memories instead of reading every record](41-memory-retrieval.md)
to understand the difference between Memory, the Context, and ordinary tool history. You need Python 3.10+; this lesson's commands use
Bash/zsh and need no real model service.

First switch to this lesson's snapshot and look at the changes from the adjacent version:

```bash
git checkout v0.42
git diff --stat v0.41..v0.42
```

After reading, you can go back to your original branch:

```bash
git checkout -
```

## Problems in the Previous Version: Memory and Local Reference Material Are Not the Same Thing

Memory suits short, explicitly recorded knowledge such as "this project's test command"; it does not suit replacing
an offline information directory that may contain many files. The automatic retrieval of v0.41 also reads only workspace Memory and never
accesses local paths outside the workspace.

Handing the model an absolute local path directly has two problems: the path may contain unnecessary sensitive information such as the user name or project structure;
and if the model then joins the path into file tools, `..` or symlinks could escape the directory the user originally
meant to open. So v0.42 separates "names the model can discover" from "real directories used inside the process".

## What This Version Adds

This version splits one information access into four steps:

```text
References configuration in config_local.py
              ↓ parsed and frozen at startup
       ReferenceCatalog (in-process catalog)
              ↓
list_references → alias + description       (discover)
search/read     → permission → path check → bounded file content (use)
```

`ReferenceCatalog` is an in-process catalog: it stores aliases, descriptions, and real directories, but the real directories are not written to
State, the Context, the session, or Trace. An `alias` is only "the name used for lookup" and is not by itself read
authorization; search and read still go through the PermissionGate.

The main code changes:

## New and Changed Files

| File | Purpose |
|---|---|
| [`references.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.42/src/mini_agent/references.py) | Freezes aliases and real directories, validates paths, symlinks, and sensitive locations, and performs bounded access. |
| [`tools/references.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.42/src/mini_agent/tools/references.py) | Defines the input and result contracts of three parent-side read-only tools. |
| `config.py`, `config_example.py` | Provide an empty default configuration and state that real configuration goes only in the untracked `config_local.py`. |
| [`tools/__init__.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.42/src/mini_agent/tools/__init__.py) | Binds the ReferenceCatalog only in the parent registry. |
| [`permission.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.42/src/mini_agent/permission.py) | Reviews search and read permissions in the form `alias:relative_path`. |

## Version Change Map

In the diagrams, `[old]` is a capability already in v0.41, `[+]` is new in this lesson, `[~]` is changed in this lesson, `[C]`
marks the main user, and `[B]` marks the boundary of this lesson.

The parent Runtime of the previous version has only temporary retrieval of workspace Memory and ordinary tools:

```text
[old][C] parent Agent Runtime
      ├─→ [old] ContextManager → MemoryRetriever → temporary Memory information block
      └─→ [old] ToolExecutor → parent ToolRegistry → role=tool history
          [B] no stable entry for local material outside the workspace
```

This version adds an in-process catalog at the tool entry of the parent registry, without changing automatic Memory retrieval or the session schema:

```text
[C] parent Agent Runtime
      └─→ [~] create_registry(state=parent)
            ├─→ [old] MemoryStore / Memory tools
            └─→ [+] ReferenceCatalog (real roots stay inside the process)
                  ├─→ [+] list_references → alias + description
                  ├─→ [+] search_reference → permission → path check → search
                  └─→ [+] read_reference → permission → path check → read by line

[old] ToolExecutor → full JSON tool history
[+] State / Trace metadata → alias, relative path, line numbers, summary, and hash
[B] subagents, the automatic Context, Memory, Plan, and verification evidence do not receive References.
```

## Key Flow

### 1. Configure a name instead of writing the path into the prompt

The real `BASE_URL`, `API_KEY`, and `MODEL` still go only in the untracked `config_local.py`. Local
material can be registered in the same file:

```python
REFERENCES = [
    {
        "alias": "python-docs",
        "path": "../../offline/python",
        "description": "Local Python design material",
    },
]
```

A relative `path` is based on the directory that contains `config_local.py`. When the parent Runtime starts, the system expands it,
makes it absolute, resolves it to a real directory, and then freezes this definition; changing the configuration object during a run does not quietly change the running
catalog. An alias must start with a lowercase letter, may use only lowercase letters, digits, `_`, and `-`, and is at most
64 characters long.

### 2. Discovering material and reading material are two different things

The model can first call:

```text
list_references()
```

It returns only `python-docs` and "Local Python design material"; it does not return the real root path and does not scan the directory.
If the model then calls:

```text
search_reference(alias="python-docs", query="dataclass", include="*.py")
```

the PermissionGate asks the user by default. The prompt shows only the alias, the relative path within the alias, the search term, and the limits,
not the real local path. The permission pattern is `python-docs:.` or `python-docs:subdir`; when the user
chooses `always`, only this exact `alias:path` is remembered; another alias or the whole subtree is not opened automatically.

### 3. Search and read both give checkable locations

`search_reference` does case-insensitive literal matching and does not run regular expressions. Results use the relative path within the alias,
the line number, the matched text, and SHA-256, for example:

```json
{
  "alias": "python-docs",
  "matches": [
    {"path": "guide/dataclasses.py", "line": 18,
     "text": "...dataclass...", "sha256": "..."}
  ],
  "total_matches": 1,
  "truncated": false
}
```

When a wider range is needed, the model can call:

```text
read_reference(alias="python-docs", path="guide/dataclasses.py", offset=12, limit=6)
```

The return value carries line numbers, the number actually returned, the start and end lines, the total line count, the file SHA-256, and the truncation status. `limit` is
a requested limit and does not guarantee that many lines will be returned; if the byte limit of the final JSON trims content further, the start and end lines
and `omitted_lines` are updated accordingly. `scan_truncated` in search results means the material was not fully scanned,
which is different from `truncated`, meaning the displayed set was trimmed.

### 4. Every access revalidates the path

The catalog freezes the allowed root directory, not a permanent pass for some file. Every search or read checks:

- The path must be a relative path within the alias; it cannot be absolute, empty, or contain `..` or NUL;
- The target must be an allowed UTF-8 regular file; it cannot be a directory, a device file, or a file over 1 MiB;
- After a file symlink is resolved, its target must still be inside the frozen root; directory symlinks are not traversed by search;
- Sensitive locations such as `config_local.py`, the Memory root directory, and the default `~/.mini_agent/sessions` cannot be read.

Opening a file also rechecks the path components and the file identity; if the file changes in a race between the check and the open,
access fails instead of risking reading an uncertain target. Errors return only an explicit error type and a description without the real root
path.

## Implementation Breakdown

`create_registry(state=...)` creates the catalog only when the parent Agent has its own `AgentState`. The stateless
module-level smoke registry does not register References; the subagent's fixed allowlist is also not expanded because the parent side
adds three tools.

All three tools use strict JSON schemas and reject undeclared arguments. Their `effect_class` is
`none`, so they reserve no generation, create no verification evidence, and change no Memory/State;
but the permission prompts for search and read still happen before the handler.

The full body must stay in ordinary tool history, because the model needs it to judge search results; State and Trace keep only
summaries such as the alias, relative path, line numbers, counts, SHA-256, and truncation status. This way the user can check "which material under which
alias was read", without copying the real root path into state summaries. Access failures are recorded by the Executor
as `outcome="failed"` and `error_kind="reference_access_error"`.

## Why This Design

Aliases separate a stable model interface from local paths that change and may be sensitive; freezing the definitions at startup avoids quietly swapping material roots
during a run; rechecking every time avoids treating an old path decision as a permanent safety guarantee. Relative paths, line numbers, and
SHA-256 make one read easier to recheck and show whether a file changed between two accesses.

Listing is allowed by default because it only shows names and descriptions the user registered; search and read ask by default because
the directory may contain files the user does not want to give to the model. The read-only design and the parent-only scope keep References from becoming an implicit
file write or a subagent privilege escalation entry.

The costs are also clear: v0.42 does not support writes, remote repositories, regex search, binary reads, caching, or automatic Context
injection; a Reference never becomes a Memory source automatically; and it cannot override project instructions, the Plan, or the
PermissionGate, let alone prove on its own that the current workspace has passed verification.

## Design Boundaries

Search accesses at most 2,000 files and 10,000 directory entries and reads at most 64 MiB of content, keeping at most 100 hits;
a single file is at most 1 MiB, and single lines and the final JSON also have fixed limits. `scan_truncated` means the scan stopped
early, and `truncated` means the displayed results were trimmed.

Real roots exist only in the current process's catalog; aliases, relative paths, and bodies may still enter the Context or the session like ordinary tool results.
References do not enter automatic Memory retrieval and are not added to the subagent allowlist beyond
`calculate`, `read_file`, `list_dir`, and `grep`. The parent Agent must judge
Reference content itself; it cannot hand it to a subagent and then upgrade the subagent's report to verification evidence.

## Run and Observe

The point to observe in this lesson is "an alias helps locate material but cannot bypass permission and path boundaries". Run:

```bash
PYTHONPATH=src python -m pytest -q tests/test_references_v042.py
```

You should observe: a legal directory returns stable relative paths, line numbers, and SHA-256; repeated accesses to the same content are in the same
order; reading again after changing a file gives a new digest. When permission for `search_reference` or `read_reference`
is denied, the handler does not run; absolute paths, `..`, or escaping symlinks fail, and the error does not show the
real root path; `list_references` can discover an alias but does not list the root directory's contents.

## Version Features, Next Lesson, and Code Index

v0.42 completes named local References for the parent Agent: they can be discovered, searched, and read by line, with
per-access permission and path checks. They are still untrusted material and do not enter the automatic Context, Memory, Plan,
verification evidence, or Subagents. Later capabilities should be defined in new plans; this lesson's local
read boundary must not be extended into remote material capabilities by default.

- [`references.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.42/src/mini_agent/references.py): frozen configuration, sensitive paths, symlinks, and bounded file access.
- [`tools/references.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.42/src/mini_agent/tools/references.py): the JSON schemas and result contracts of the three parent-side tools.
- [`tools/base.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.42/src/mini_agent/tools/base.py): the boundary between full tool history and the metadata excerpt.
- [`permission.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.42/src/mini_agent/permission.py): alias-relative permission patterns and safe prompts.
- [`test_references_v042.py`](https://github.com/liiiiiiiiil/agent-from-scratch/blob/v0.42/tests/test_references_v042.py): an executable index of this lesson's behavior boundaries.

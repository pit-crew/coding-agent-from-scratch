# Regression Comparison and Memory Retrieval Ablation

Comparison evaluation gives the same tasks to the Agent under different conditions and runs them repeatedly under the same rules. It is used to tell a one-off lucky success from an observable version difference; three repetitions are used only to describe results and do not form a statistical significance conclusion.

This version fixes the four `coding-benchmark@1.1` tasks, with three repetitions per task per group:

| Group | Code source | Automatic Memory retrieval | Comparison question |
|---|---|---|---|
| `old-off` | Fixed v0.52 commit `9d498f91f7ca21caa7f4f842fba0a49075754f20` | Off | Baseline |
| `current-off` | Frozen v0.53 commit | Off | Compared with v0.52 |
| `current-on` | Same v0.53 commit | On | Compared with the v0.53 off group |

The two edges are `old-off → current-off` and `current-off → current-on`. The model alias, tasks, initial files, grader, permissions, and budget stay the same; only the source revision or retrieval switch declared by the edge changes. The full batch plans 36 independent slots, and the execution order rotates the group order by task and repetition number.

## Memory material and isolation

The four memory seeds describe only interface conventions, project background, and investigation methods, and contain no fix patches, answers, hidden tests, or grader content. Each trial creates a target-version `MemoryStore` fresh from the same semantic snapshot, then uses the target-version `MemoryRetriever` and the existing Context retrieval logic. The on group retrieves at most four entries, with a total injection limit of 2,400 characters. The off group runs no retrieval.

Memory files are placed outside the trial workspace, and each trial uses a new workspace identity, HOME, Memory, and temporary directory. Seeds are not carried from one trial to another. Reports record only the fixed material digest, whether retrieval happened, the attempt count, and failure categories, without saving injected bodies. A retrieval failure is handled by the existing Context degradation, but that sample is marked as a condition anomaly and cannot be interpreted as a normal on-group sample.

The comparison worker uses `AgentRuntime.run()`, the tool executor, and the permission gate from the target checkout. Visible tools follow the six file/compute tools of the coding benchmark, without opening shell, Memory CRUD, MCP, Skills, References, or subagents. After the Agent stops, the independent grader checks the workspace; neither the Agent's own claims nor Runtime verification evidence replaces independent grading.

If a task contract requires submitting a regression test, the runner pre-creates an empty `tests/` directory in the clean copy. The six tools include no directory creation tool, so this empty directory lets the Agent add test files per the contract; no test code or answers are pre-placed, and all comparison groups use the same workspace preparation rules.

## Metrics and missing values

- **Independent acceptance pass rate**: grader passes / gradable trials, also reporting planned slots, terminal states, infrastructure errors, and unrun count.
- **Strict task success**: the Agent ends with normal text, the State terminal state is `done`, there are no run errors, the grader passes, and cleanup is complete.
- **Calls**: model requests, successful responses, tool calls, permission refusals, and tool success/failure/refusal are counted separately; subagent calls are fixed at 0.
- **Tokens and cost**: input/output are separate, marked with the provider, estimated, mixed, or unavailable source. Cost uses a frozen price snapshot and `Decimal`; when prices or usage are missing it stays `null` and is not treated as an exact bill.
- **Duration**: Agent and grader list the observation count, median, and p95 separately; `null` when there are no observations.
- **Invalid repetitions**: counted when the same tool with the same normalized arguments is called again within the same progress phase, the result is also the same, and there is no new structured State fact. Path arguments are normalized to workspace-relative paths; bodies are hashed only in memory and do not enter reports.
- **Recovery success rate**: not applicable to coding comparison and always `null`; historical reliability reports are referenced separately.

The report shows per task the pass count, denominator, percentage-point difference, and usage and duration differences, and provides the result and relative evidence paths for each paired slot. When the source, permissions, budget, task set, grader, or slots do not match, the report lists the specific reasons it is not comparable, and it cannot shrink the denominator and still claim the original comparison is complete.

## Grading eligibility and connection diagnostics (report rule 2)

Whether the raw grader returned and passed is recorded separately from whether the trial can be used for ability comparison. Provider connection, timeout, HTTP/protocol failures, and worker, grader, or cleanup faults are excluded from the ability denominator; Agent code exceptions, execution timeouts, permission refusals, and budget exhaustion are still kept as task failures. Each slot counts at most one infrastructure error.

The group summary gives the raw grader counts, valid ability samples, and exclusion reasons separately. Paired differences use only samples valid on both sides; without valid pairs, the difference is `null`. `batch_complete` only means all slots have terminal states, while `comparison_complete` also requires all predeclared pairs to be valid and the contract conditions to be consistent. Raw tokens and failure durations stay visible for diagnosis; conservative estimates do not represent incurred usage or the cost of a normal model run.

The optional `agent.error_diagnostic` of new results contains only an allowlisted category, the underlying exception category, an integer errno, and a TLS verification code; the exception cause chain is read at most four levels deep, and exception messages, URLs, auth headers, or bodies are not saved. Old results without diagnostics stay unknown. This diagnostic does not change HTTP transport, proxy support, or retry behavior.

To generate a separate corrected report for an old batch, use a brand-new directory outside the source archive:

```bash
PYTHONPATH=src python -m mini_agent.evaluation report-comparison <run-dir> --output <new-derived-dir>
```

The derived report carries the report rule version, the source run ID, and the input evidence digests. An existing target directory is refused; the original trials, ledger, and report stay as they are. Without `--output`, the derived report is still rebuilt in the original run directory, keeping the existing command behavior. An incomplete comparison or a found regression returns 1, and configuration/evidence errors return 2; an output report does not mean a new trial was started.

## Commands

Command examples use Bash/zsh. The current revision, model profile alias, and prices in the template are placeholders; first copy the template and fill in the reviewed local conditions. If a price cannot be confirmed, fill in `null` and state the snapshot source explicitly. Real endpoints, model IDs, and API keys stay only in local configuration.

```bash
PYTHONPATH=src python -m mini_agent.evaluation validate-comparison /path/to/filled-spec.json
PYTHONPATH=src python -m mini_agent.evaluation plan-comparison /path/to/filled-spec.json --output /private/tmp/v053-review-plan
PYTHONPATH=src python -m mini_agent.evaluation self-test-comparison --output /private/tmp/v053-offline-comparison
```

The plan manifest freezes the current full commit, run environment, task and grader digests, model binding digest, Memory material, and the 36-slot order. After the manifest is generated, review all tasks, model aliases, budgets, price snapshots, and sources. This document does not authorize real model calls.

Run only after the user explicitly approves the currently reviewed manifest:

```bash
PYTHONPATH=src python -m mini_agent.evaluation run-comparison /path/to/review-plan/comparison-plan.json --live --output /path/to/new-run
PYTHONPATH=src python -m mini_agent.evaluation report-comparison /path/to/new-run
```

Live does not automatically retry, make up, or replace slots; after an interruption, the current ledger and unrun slots are kept, and a new attempt needs a new run ID. The report command rebuilds the report from the plan, ledger, and evidence digests, without connecting to the provider, rerunning the grader, or changing raw trial evidence.

## Scope of this version

This ablation studies only automatic summary retrieval of fixed Memory material within the same task. It does not measure cross-task memory learning and does not generalize to other task sets, models, or memory strategies. The first three groups use the same model binding; model/provider comparison is not part of these 36 live slots. The v0.51 coding and v0.52 reliability historical baselines are still marked not complete separately.

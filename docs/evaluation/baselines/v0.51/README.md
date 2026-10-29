# v0.51 First Coding Baseline

This directory saves the redacted raw trials of the first real model run, the report rebuilt from the raw results, per-task observations, and the manual review queue.

The tasks and grading criteria are frozen as `coding-benchmark@1.0` (SHA-256: `bf728faf8cff54e173a73c21946499b48b81fccce73a2b187f3d7b20b7e12d16`), reviewed and approved by the user on 2026-09-27. The 12 live trials completed in order on 2026-09-27, and no samples were rerun or replaced. Raw records and the rebuilt report are saved in [`live-20260927/`](live-20260927/). Offline grader checks and fixture trials do not count toward model scores.

## First-round results

**Review correction (2026-09-28)**: the following is still the raw automatic grading of suite 1.0. The receipt task did not state to the Agent the exact text format the grader required, so the three format failures are a grading contract dispute and cannot be interpreted directly as coding ability failures; the totals of 8 acceptance passes and 6 final successes carry the same limitation. The raw trials and report stay unchanged and are not regraded retroactively. The current suite has been raised to 1.1, which publishes the exact three-line format in the task text; 1.1 has no real model baseline yet, and the scores here are not carried over.

| Task | Run / gradable | Passed independent acceptance | Final success | Observation |
|---|---:|---:|---:|---|
| `pagination-boundary` | 3 / 3 | 3 | 3 | All three runs fixed the last-page boundary and passed independent grading. |
| `orders-discount-receipt` | 3 / 3 | 0 | 0 | In all three runs, behavior checks such as discount calculation and amount due passed; the receipt format did not match the frozen exact display standard. See each trial's `grader.log` and `diff.patch` for the differences. |
| `cache-expiry-regression` | 3 / 3 | 2 | 1 | Two runs hit the 120-second limit; in one of them, the submitted fix and regression test passed grading, but the Agent did not finish normally. The other made no file changes before the timeout and failed grading. The third passed fully. |
| `config-priority-investigation` | 3 / 3 | 3 | 2 | The priority behavior submitted in all three runs passed grading; one had a correct change but hit the 120-second limit. |

In total: 12 planned, 12 run, 12 gradable; 8 passed independent acceptance and 6 final successes. Failure categories are `task_failed=3` and `agent_timeout=3`, with 0 infrastructure errors. Passing grading and final success are different metrics: a timed-out sample is not recorded as a final success even if it passes the grader.

## Frozen sources and observation limits

- Code revision: `95c533793ff1af0242ba3124ae6b33590c51b4d5`; the code digest was consistent during the run.
- Model source summary: provider/profile `legacy-default`, protocol `openai_chat`, fingerprint `f5d29d7d52439c419e672fd0a4d7007a8197e4afe7b24083d4d0116fb4fc4cf6`. Real endpoints, model IDs, and credentials do not enter the archive.
- 9 trials have usage observations: 56 model calls, 59 tool calls, 124,975 input tokens, and 10,016 output tokens in total; call and token usage of the 3 timed-out trials is unavailable. The totals above do not represent 12 separate HTTP requests; each trial can contain several model calls.
- The Agent duration median is 8,445.5 ms, and p95 is 120,017 ms. There is no price snapshot, so `cost_usd` is `null`.
- Each task has only 3 samples; the results only describe observations on this frozen task set and model source and do not represent general coding ability.

## Manual review queue

The `manual_review_queue` of the rebuilt report lists the following 5 trials:

- `orders-discount-receipt`: `04268614`, `60549c61`, `51ffeed7`. Review the differences between the discount label, percentage, and minus sign format in the receipt and the grader's requirements.
- `cache-expiry-regression`: `f9d35ed5`. The independent grader passed and the fix/regression test were submitted, but the Agent timed out; check its diff and end state.
- `config-priority-investigation`: `1acd4694`. The priority fix passed the grader, but the Agent timed out; check the diff and end state.

Another timed-out sample, `cache-expiry-regression-f0f441ee`, changed no files and failed the grader; it is not in the automatic review queue and is still kept as raw failure evidence.

Full per-trial evidence, the suite ledger, and the rebuildable report are in [`live-20260927/`](live-20260927/). Run `PYTHONPATH=src python -m mini_agent.evaluation report-suite docs/evaluation/baselines/v0.51/live-20260927` to regenerate the report view.

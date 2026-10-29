# Targeted Budget and Protocol Fixes After Suite 1.5

## Problem and changes

In live-20260929-07, the 11 budget refusals happened while about 11k–27k of balance remained. The old Runtime held back quota for the current verification, plan progress, and the future final reply at the same time, and then limited the current input by the number of future rounds; verification requests still went through the work path and could not use the quota held back for themselves. Balance is not the same as sendable quota, and the original refusal logs also lost the protected context size, so the post-fix model results cannot be computed one by one from the old evidence.

This round lets the current working request use the quota needed for plan progress and verification, and separately reserves only the later tool-free final reply. The reservation is a local estimate from the current protected instructions, all user constraints, and completion facts, using the finishing request's own calibration rules, plus a 256 input margin and at most 512 output quota. Historical tool rounds do not enter this finishing floor estimate; actual working and finishing requests can still carry the last two complete tool rounds, trimmed by quota. Verification is not run automatically, the plan is not advanced, and completion is not declared.

| File | Change in this round |
|---|---|
| `src/mini_agent/runtime.py` | Removes the unusable duplicate phase reservations and the current input limit split by assumed future rounds; reserves by the real finishing floor; on refusal keeps the non-zero input floor, quota, blockers, and phase. |
| `src/mini_agent/context.py` | Outputs a body-free context floor and pre-trim size; allows read-only computation of the finishing floor without tool history; keeps all user corrections. |
| `src/mini_agent/evaluation/reliability_diagnostics.py` | Observes the production Runtime's budget decisions as is, keeps diagnostics for failed requests too, and creates no second admission rule set. |
| `src/mini_agent/providers/base.py`, `openai_chat.py` | Tool argument JSON errors record a safe category, argument length, parse position, normalized stop reason, response mode, and reported usage; argument or reasoning bodies are not kept. |
| `src/mini_agent/providers/catalog.py` | When argument validation of a complete response fails, the usage already reported by the provider is still settled; unknown usage is still settled conservatively at the budget reservation. |
| `src/mini_agent/evaluation/reliability_worker.py` | Illegal JSON arguments of complete non-streaming responses and argument errors with an explicit length stop stay in recovery grading as generation failures; streaming assembly errors of unknown source are still classified as unconfirmed protocol errors. |
| `tests/test_task_budget_v052.py` | Long investigation history, protected instructions of about 2k, tool schemas of about 1k, and a warm calibration positive error of 3k; balances of 19k/27k complete verification + reply and plan progress + verification + reply respectively; at 11k it refuses with no model I/O. |
| `tests/test_reasoning_content_v052.py`, `test_evaluation_worker_v052.py` | Regressions for classification, redaction, usage, and recovery denominators of complete/streaming responses, length limits, illegal JSON, and non-objects. |

`budget_stage` is a diagnostic marker and does not replace the State phase gate or tool permissions. Available budget does not guarantee that the model stops investigating and chooses verification; the final reply reservation is also only an estimate, and future growth of State, user input, and provider error can still make a request inadmissible. The refusal in the 11k regression only shows that that fixed input cannot fit the request, not that all historical 11k refusals were reasonable.

## Evidence boundary of protocol classification

The stacks of the two errors in the old batch both fell in tool argument JSON parsing, but there is no stop reason or raw length evidence, so it cannot be confirmed whether it was truncation, a model generation error, or a transport/assembly problem, nor can it be identified as HTTP 400. The classification of this round applies only to new evidence: illegal arguments of a complete non-streaming message are scored as output failures; a `length` stop of a completed stream shows that an output limit stop happened, but does not prove the limit was the only cause; other streaming argument errors keep an unconfirmed source. JSON is not closed automatically, bad arguments are not run, and there are no retries or model fallback.

Old trials, frozen material, review manifests, reports, and statistics stay as they are; the new classification does not change old denominators retroactively. The current source already differs from the Runtime fingerprint in the suite 1.5 review manifest, so the old manifest cannot be reused directly to start a new live.

## Acceptance and next steps

This round only does implementation and offline acceptance; it creates no suite 1.6, runs no new paid live, and creates no Git tag. The full verification results are saved separately in `stage-budget-repair-validation.json`.

Offline regressions prove these paths can complete under fixed inputs and deterministic responses, not the real model recovery rate. After the candidate implementation passes offline acceptance, re-freeze the manifest and classification rules before the next live, run only one separate batch, and keep the failures. If there are still reproducible implementation defects, handle them in a targeted way; if the remaining failures are about model investigation and execution order, record them as ability limits, and do not keep changing the evaluation or rerunning whole batches for the recovery rate.

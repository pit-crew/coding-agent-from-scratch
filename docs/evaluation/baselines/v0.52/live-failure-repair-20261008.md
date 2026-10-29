# 2026-10-08: Fixing the Execution Breakpoints Exposed by the Latest Live

This round implements fixes based on the archived facts of `live-20260930-01`, sending no model requests and making up no old slots. The current executable candidate is `reliability-boundaries@1.6`, with digest `376170c1721cf6862c2c9faa3bc99195ff2c7a008afc0e7e89910bcbdd3502db`. The old suite 1.5's 6/14 is still the score of that historical batch; the new candidate has no live recovery rate yet.

## Confirmed causes

1. In crash scenario r01, before the real crash injection, the model submitted `recover.caused_by_failure_id=""`. The rejection record still used the empty string as a causal reference, the State export reported `recovery action reference invalid`, and the outer layer wrapped it as `SessionValidationError`. It was reproduced in memory using the archived session; the original tool was not replayed and the original session was not changed.
2. Several tasks were refused at admission while about 19k–22k of the 64k total quota remained. The full working prompt entered the final reply budget reservation again; the final category had no provider observations yet and was reserved by the cold-start rule. When the files were already correct but independent verification was still needed, the two input reservations made the remaining quota unusable.
3. Verification repair scenarios r01/r03 had 9/10 file-not-found errors respectively. The frozen tool table had no `list_dir` or `grep`, so the model lacked read-only means to locate files; the model also did not promptly make the fix the task explicitly required. Insufficient directory capability and model execution efficiency together amplified invalid investigation.

## File-level changes

| File | Change and boundary |
|---|---|
| `state.py` | Rejection records reference only failures that really exist; unknown IDs are recorded as null, without redirecting to the active failure or forging failures. Only rejected records allow an explicit null; other states are still validated strictly; missing fields and unknown or non-string references are still refused. |
| `recovery.py`, `agent.py`, `tools/base.py` | Handler refusals, argument schema refusals, and turn phase refusals return the active failure ID and repair phase. The refusal notice points to the legal recovery entry and does not advance the generation. |
| `prompt.py` | Adds an application-generated `build_completion_prompt` for phases that allow only a final text reply; keeps the full project instructions. Corrects the outdated description in the original prompt that "tool failures end the loop directly". |
| `context.py` | The application can provide a protected prompt for the final reply separately; without configuration the original prompt is still used. Working requests still use the full prompt. The final view keeps the task, all user/system constraints, and authoritative completion facts, and omits old investigation tool rounds; history, selected reasoning, and the original protected prompt are not rewritten. |
| `__main__.py`, `resume.py` | New and resumed tasks both regenerate the working/finishing prompt pair from the current local project instructions; the finishing prompt is not imported from old sessions. |
| `evaluation/reliability_worker.py` | Both the initial live and the new-process crash recovery assemble the dedicated finishing prompt; evaluation rules and recovery constraints are still kept. |
| `evaluation/reliability_schema.py`, `reliability.py` | The current executable suite is upgraded to 1.6 with updated fixed digests; historical 1.5 can still be rebuilt read-only, keeping its original budget contract. |
| `tests/fixtures/evaluation/reliability/verification-repair/scenario.json`, `suite.json` | Adds directory/search tools limited to the trial workspace with explicit permissions; recomputes material and suite digests. Other scenario material and the 21/50 slot counts are unchanged. |
| `tests/test_live_failure_repairs_v052.py` | Adds regressions for persistence and recovery validation of illegal IDs, late verification/plan progress/final reply under the full parent prompt, constraint retention, and the new tool table. |

This round did not raise the 64,000 limit, lower cold-start or calibration reservations, or remove attempt limits. Finishing still requires a real model text reply; the completion gates for active plans, current-generation verification, processes, subagents, and recovery issues stay in effect. Only the request view shrinks, and the full task history can still be saved.

## Offline acceptance

Targeted regressions: 112 passed. In a controlled late task with the full parent prompt and 19,520 tokens remaining, the finishing reservation dropped from about 10,128 to 2,966, the working input reservation was about 14,976, the verification request could be admitted, and independent verification and a real tool-free mock reply could be completed. Plan progress with 27k remaining is also covered; the ledger had no overrun. This is offline flow evidence with fixed model responses, not a prediction of the real model recovery rate.

For the final results of full tests, the offline matrix, and documentation checks, see the [machine-readable acceptance record](live-failure-repair-20261008-validation.json). In the first verification inside the sandbox, the local loopback HTTP fixture could not start; a full independent verification was run outside the sandbox with approval, the original failure output is kept, and no live slots are replaced.

The old batches `live-20260929-08`, `live-20260929-09`, and `live-20260930-01` are all rebuilt from frozen material, ledgers, and original trials, byte-identical to the archived reports.

## Still awaiting real model verification

The offline results prove that the located save defect and the controlled late budget breakpoint are fixed, but cannot guarantee that the model no longer repeats investigation, nor that protected project instructions of any size fit into the remaining budget. When they cannot fit, it still stops explicitly; this cannot be solved by trimming user constraints or forging completion.

Next, first run a small number of separate targeted lives with explicit cost caps, observing continued execution after illegal recovery requests and verification/finishing after the fix. They do not count toward the old 21-slot batch. Only if the targeted chain passes should the suite 1.6 candidate be re-frozen and a full live considered; this round started none of these paid operations.

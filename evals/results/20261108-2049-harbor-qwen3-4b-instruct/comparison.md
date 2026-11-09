# Eval: `local/qwen3-4b-instruct`

Run `20261108-2049-harbor-qwen3-4b-instruct` · Harbor 0.25.0 agent `terminus-2` on the holdout-id + holdout-ood tasks: the model reads the PDFs, runs `benefits-calc` and writes `/app/answer.json` · up to 40 turns · 30 min per task · temperature 0.0 · answers from policyengine-us 2.50.1 · cost $0.0000

Changes are OOD minus ID, with 95% bootstrap intervals over households in brackets. With about 67 households per OOD family, small gaps can be noise.

**Read the floors first.** Mean reward and plain accuracy depend on how many households qualify, and the OOD set has more eligible households than the ID set. Answering "no" to everything already scores differently on the two sets (see the floor rows). Balanced accuracy averages accuracy on truly eligible and truly ineligible decisions, so blanket answers score 50% on any set; use it to judge the ID → OOD change.

## Overall

| | ID | OOD | Change |
|---|---|---|---|
| Households scored | 173 | 179 | |
| Mean reward (0–1) | 0.22 | 0.14 | -0.08 (-0.13 to -0.03) |
| Eligibility score | 0.24 | 0.17 | -0.07 |
| Amount score | 0.01 | 0.00 | -0.01 |
| Malformed answers | 32% | 32% | -1 pts |
| Cut off at the token limit | 0 | 0 | |
| Floor: always "no" | 0.34 | 0.21 | |
| Floor: always "yes", $0 | 0.21 | 0.30 | |

48 cases got no answer from the API and aren't scored; see the result files.

## The agent

The task's own reward adds the missing-information list (weights 0.60 eligibility, 0.25 amount, 0.15 missing information), as the task verifier scores it. The mean reward above uses the evals scorer, so it compares directly with one-shot runs.

| | ID | OOD |
|---|---|---|
| Task reward, with missing information (0–1) | 0.20 | 0.13 |
| Missing-information score | 0.09 | 0.07 |
| Timed out | 25 | 28 |
| Wrote no answer file | 32 | 39 |
| Errors before the verifier (not scored) | 0 | 0 |
| Not run (shard out of time; not scored) | 27 | 21 |
| Median turns | 6 | 5 |
| Median minutes per task | 12.8 | 11.8 |

Harbor's verifier and the stored answer agree on every task's reward.

## Against the one-shot run `20261031-0030-local-qwen3-4b-instruct-docs`

The same households: there the model read the documents as text in one prompt and answered in one reply. Changes are agent minus one-shot, with 95% bootstrap intervals over households.

| | ID | OOD |
|---|---|---|
| Households in both | 173 | 179 |
| Mean reward | 0.46 → 0.22: -0.24 (-0.29 to -0.18) | 0.32 → 0.14: -0.18 (-0.23 to -0.13) |
| SNAP balanced accuracy | 60% → 11%: -49 pts (-59 to -38) | 58% → 11%: -47 pts (-55 to -38) |
| EITC balanced accuracy | 55% → 7%: -48 pts (-55 to -41) | 52% → 10%: -42 pts (-50 to -34) |
| Medicaid balanced accuracy | 62% → 28%: -34 pts (-44 to -23) | 53% → 35%: -18 pts (-27 to -9) |
| WIC balanced accuracy | 70% → 33%: -37 pts (-49 to -26) | 68% → 34%: -34 pts (-42 to -25) |

## By program

| Program | Measure | ID | OOD | Change |
|---|---|---|---|---|
| SNAP | **Balanced accuracy** | 11% | 11% | +0 pts (-7 to +7) |
| SNAP | Accuracy | 22% | 18% | -4 pts |
| SNAP | False denials (of truly eligible) | 5% | 7% | +3 pts |
| SNAP | False approvals (of truly ineligible) | 8% | 16% | +8 pts |
| SNAP | Amount within ±5% or ±$10 (of truly eligible) | 0% | 0% | +0 pts |
| EITC | **Balanced accuracy** | 7% | 10% | +3 pts (-3 to +9) |
| EITC | Accuracy | 20% | 13% | -6 pts |
| EITC | False denials (of truly eligible) | 5% | 7% | +1 pts |
| EITC | False approvals (of truly ineligible) | 6% | 5% | -1 pts |
| EITC | Amount within ±5% or ±$10 (of truly eligible) | 0% | 0% | +0 pts |
| Medicaid | **Balanced accuracy** | 28% | 35% | +7 pts (-2 to +14) |
| Medicaid | Accuracy | 26% | 31% | +5 pts |
| Medicaid | False denials (of truly eligible) | 39% | 46% | +7 pts |
| Medicaid | False approvals (of truly ineligible) | 9% | 11% | +2 pts |
| WIC | **Balanced accuracy** | 33% | 34% | +2 pts (-7 to +10) |
| WIC | Accuracy | 51% | 50% | -1 pts |
| WIC | False denials (of truly eligible) | 38% | 61% | +23 pts |
| WIC | False approvals (of truly ineligible) | 3% | 2% | -0 pts |

Medicaid and WIC accuracy count one decision per household member.

## OOD by shift family

| Group | n | Mean reward | SNAP balanced acc. | EITC balanced acc. | Medicaid balanced acc. | WIC balanced acc. | False denials | Malformed |
|---|---|---|---|---|---|---|---|---|
| ID (reference) | 173 | 0.22 | 11% | 7% | 28% | 33% | 25% | 32% |
| Rare household shapes | 60 | 0.13 | 9% | 13% | 39% | 34% | 44% | 25% |
| Threshold edge cases | 55 | 0.14 | 16% | 11% | 33% | 36% | 32% | 35% |
| Held-out states | 64 | 0.15 | 9% | 7% | 27% | 34% | 34% | 36% |

## OOD by twist

Rare-shape households have one or two twists, so a household can appear in two rows.

| Group | n | Mean reward | SNAP balanced acc. | EITC balanced acc. | Medicaid balanced acc. | WIC balanced acc. | False denials | Malformed |
|---|---|---|---|---|---|---|---|---|
| ID (reference) | 173 | 0.22 | 11% | 7% | 28% | 33% | 25% | 32% |
| college_student | 12 | 0.07 | 0% | 12% | 25% | 29% | 38% | 33% |
| disabled_member | 12 | 0.14 | 17% | 12% | 34% | 33% | 43% | 25% |
| edge_eitc | 16 | 0.16 | 0% | 0% | 32% | 39% | 61% | 25% |
| edge_medicaid | 19 | 0.08 | 16% | 11% | 27% | 27% | 34% | 42% |
| edge_snap | 20 | 0.19 | 18% | 23% | 37% | 43% | 17% | 35% |
| large_household | 15 | 0.13 | 21% | 33% | 45% | 30% | 41% | 33% |
| mixed_citizenship | 9 | 0.19 | 0% | – | 46% | 34% | 43% | 22% |
| multigenerational | 14 | 0.11 | 0% | 8% | 37% | 45% | 51% | 14% |
| pregnant_member | 11 | 0.06 | 33% | 17% | 46% | 35% | 51% | 36% |
| self_employment | 13 | 0.17 | 0% | 0% | 65% | 38% | 33% | 8% |

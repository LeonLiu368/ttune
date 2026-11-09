# Eval: `local/qwen3-4b-instruct`

Run `20261109-0653-harbor-qwen3-4b-instruct` · Harbor 0.25.0 agent `terminus-2` on the holdout-id + holdout-ood tasks: the model reads the PDFs, runs `benefits-calc` and writes `/app/answer.json` · up to 40 turns · 30 min per task · temperature 0.0 · answers from policyengine-us 2.50.1 · cost $0.0000

Changes are OOD minus ID, with 95% bootstrap intervals over households in brackets. With about 67 households per OOD family, small gaps can be noise.

**Read the floors first.** Mean reward and plain accuracy depend on how many households qualify, and the OOD set has more eligible households than the ID set. Answering "no" to everything already scores differently on the two sets (see the floor rows). Balanced accuracy averages accuracy on truly eligible and truly ineligible decisions, so blanket answers score 50% on any set; use it to judge the ID → OOD change.

## Overall

| | ID | OOD | Change |
|---|---|---|---|
| Households scored | 200 | 200 | |
| Mean reward (0–1) | 0.23 | 0.14 | -0.09 (-0.14 to -0.04) |
| Eligibility score | 0.25 | 0.16 | -0.08 |
| Amount score | 0.02 | 0.00 | -0.02 |
| Malformed answers | 32% | 32% | -1 pts |
| Cut off at the token limit | 0 | 0 | |
| Floor: always "no" | 0.34 | 0.21 | |
| Floor: always "yes", $0 | 0.21 | 0.30 | |

## The agent

The task's own reward adds the missing-information list (weights 0.60 eligibility, 0.25 amount, 0.15 missing information), as the task verifier scores it. The mean reward above uses the evals scorer, so it compares directly with one-shot runs.

| | ID | OOD |
|---|---|---|
| Task reward, with missing information (0–1) | 0.21 | 0.13 |
| Missing-information score | 0.09 | 0.09 |
| Timed out | 25 | 29 |
| Wrote no answer file | 36 | 44 |
| Errors before the verifier (not scored) | 0 | 0 |
| Not run (shard out of time; not scored) | 0 | 0 |
| Median turns | 6.0 | 6.0 |
| Median minutes per task | 12.1 | 12.7 |

Harbor's verifier and the stored answer agree on every task's reward.

## Against the one-shot run `20261031-0030-local-qwen3-4b-instruct-docs`

The same households: there the model read the documents as text in one prompt and answered in one reply. Changes are agent minus one-shot, with 95% bootstrap intervals over households.

| | ID | OOD |
|---|---|---|
| Households in both | 200 | 200 |
| Mean reward | 0.45 → 0.23: -0.22 (-0.28 to -0.18) | 0.31 → 0.14: -0.17 (-0.22 to -0.13) |
| SNAP balanced accuracy | 58% → 12%: -45 pts (-55 to -35) | 59% → 12%: -47 pts (-55 to -39) |
| EITC balanced accuracy | 54% → 8%: -47 pts (-54 to -39) | 50% → 9%: -42 pts (-50 to -33) |
| Medicaid balanced accuracy | 63% → 27%: -36 pts (-45 to -27) | 54% → 33%: -21 pts (-29 to -13) |
| WIC balanced accuracy | 75% → 32%: -43 pts (-54 to -31) | 69% → 34%: -35 pts (-43 to -27) |

## By program

| Program | Measure | ID | OOD | Change |
|---|---|---|---|---|
| SNAP | **Balanced accuracy** | 12% | 12% | -1 pts (-7 to +6) |
| SNAP | Accuracy | 23% | 17% | -6 pts |
| SNAP | False denials (of truly eligible) | 5% | 7% | +1 pts |
| SNAP | False approvals (of truly ineligible) | 6% | 12% | +6 pts |
| SNAP | Amount within ±5% or ±$10 (of truly eligible) | 0% | 0% | +0 pts |
| EITC | **Balanced accuracy** | 8% | 9% | +1 pts (-4 to +7) |
| EITC | Accuracy | 20% | 12% | -8 pts |
| EITC | False denials (of truly eligible) | 4% | 4% | -0 pts |
| EITC | False approvals (of truly ineligible) | 7% | 4% | -2 pts |
| EITC | Amount within ±5% or ±$10 (of truly eligible) | 1% | 0% | -1 pts |
| Medicaid | **Balanced accuracy** | 27% | 33% | +6 pts (-2 to +14) |
| Medicaid | Accuracy | 24% | 30% | +6 pts |
| Medicaid | False denials (of truly eligible) | 34% | 50% | +16 pts |
| Medicaid | False approvals (of truly ineligible) | 10% | 10% | +1 pts |
| WIC | **Balanced accuracy** | 32% | 34% | +2 pts (-7 to +9) |
| WIC | Accuracy | 50% | 51% | +1 pts |
| WIC | False denials (of truly eligible) | 33% | 63% | +30 pts |
| WIC | False approvals (of truly ineligible) | 2% | 2% | +0 pts |

Medicaid and WIC accuracy count one decision per household member.

## OOD by shift family

| Group | n | Mean reward | SNAP balanced acc. | EITC balanced acc. | Medicaid balanced acc. | WIC balanced acc. | False denials | Malformed |
|---|---|---|---|---|---|---|---|---|
| ID (reference) | 200 | 0.23 | 12% | 8% | 27% | 32% | 22% | 32% |
| Rare household shapes | 67 | 0.13 | 11% | 10% | 39% | 36% | 49% | 22% |
| Threshold edge cases | 67 | 0.13 | 15% | 10% | 30% | 35% | 32% | 37% |
| Held-out states | 66 | 0.15 | 10% | 6% | 26% | 30% | 35% | 36% |

## OOD by twist

Rare-shape households have one or two twists, so a household can appear in two rows.

| Group | n | Mean reward | SNAP balanced acc. | EITC balanced acc. | Medicaid balanced acc. | WIC balanced acc. | False denials | Malformed |
|---|---|---|---|---|---|---|---|---|
| ID (reference) | 200 | 0.23 | 12% | 8% | 27% | 32% | 22% | 32% |
| college_student | 13 | 0.05 | 17% | 6% | 35% | 38% | 56% | 15% |
| disabled_member | 14 | 0.12 | 8% | 5% | 27% | 26% | 36% | 36% |
| edge_eitc | 22 | 0.15 | 2% | 0% | 27% | 30% | 42% | 41% |
| edge_medicaid | 22 | 0.09 | 13% | 10% | 26% | 29% | 30% | 41% |
| edge_snap | 23 | 0.15 | 15% | 24% | 33% | 44% | 28% | 30% |
| large_household | 15 | 0.13 | 21% | 33% | 48% | 35% | 47% | 27% |
| mixed_citizenship | 10 | 0.17 | 0% | – | 46% | 31% | 55% | 20% |
| multigenerational | 17 | 0.12 | 8% | 4% | 35% | 41% | 54% | 18% |
| pregnant_member | 13 | 0.08 | 22% | 7% | 47% | 38% | 60% | 23% |
| self_employment | 14 | 0.18 | 0% | 0% | 65% | 40% | 35% | 7% |

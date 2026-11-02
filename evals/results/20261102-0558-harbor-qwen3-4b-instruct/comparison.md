# Eval: `local/qwen3-4b-instruct`

Run `20261102-0558-harbor-qwen3-4b-instruct` · Harbor 0.25.0 agent `terminus-2` on the holdout-id + holdout-ood tasks: the model reads the PDFs, runs `benefits-calc` and writes `/app/answer.json` · up to 40 turns · 30 min per task · temperature 0.0 · answers from policyengine-us 2.50.1 · cost $0.0000

Changes are OOD minus ID, with 95% bootstrap intervals over households in brackets. With about 67 households per OOD family, small gaps can be noise.

**Read the floors first.** Mean reward and plain accuracy depend on how many households qualify, and the OOD set has more eligible households than the ID set. Answering "no" to everything already scores differently on the two sets (see the floor rows). Balanced accuracy averages accuracy on truly eligible and truly ineligible decisions, so blanket answers score 50% on any set; use it to judge the ID → OOD change.

## Overall

| | ID | OOD | Change |
|---|---|---|---|
| Households scored | 131 | 145 | |
| Mean reward (0–1) | 0.18 | 0.12 | -0.06 (-0.12 to -0.01) |
| Eligibility score | 0.19 | 0.14 | -0.05 |
| Amount score | 0.02 | 0.00 | -0.02 |
| Malformed answers | 35% | 37% | +2 pts |
| Cut off at the token limit | 0 | 0 | |
| Floor: always "no" | 0.34 | 0.21 | |
| Floor: always "yes", $0 | 0.21 | 0.30 | |

124 cases got no answer from the API and aren't scored; see the result files.

## The agent

The task's own reward adds the missing-information list (weights 0.60 eligibility, 0.25 amount, 0.15 missing information), as the task verifier scores it. The mean reward above uses the evals scorer, so it compares directly with one-shot runs.

| | ID | OOD |
|---|---|---|
| Task reward, with missing information (0–1) | 0.17 | 0.12 |
| Missing-information score | 0.11 | 0.09 |
| Timed out | 20 | 30 |
| Wrote no answer file | 33 | 36 |
| Errors before the verifier (not scored) | 0 | 0 |
| Not run (shard out of time; not scored) | 69 | 55 |
| Median turns | 5 | 6 |
| Median minutes per task | 12.6 | 13.6 |

Harbor's verifier and the stored answer agree on every task's reward.

## Against the one-shot run `20261031-0030-local-qwen3-4b-instruct-docs`

The same households: there the model read the documents as text in one prompt and answered in one reply. Changes are agent minus one-shot, with 95% bootstrap intervals over households.

| | ID | OOD |
|---|---|---|
| Households in both | 131 | 145 |
| Mean reward | 0.44 → 0.18: -0.26 (-0.32 to -0.21) | 0.29 → 0.12: -0.17 (-0.22 to -0.12) |
| SNAP balanced accuracy | 57% → 6%: -51 pts (-62 to -40) | 58% → 13%: -45 pts (-54 to -35) |
| EITC balanced accuracy | 54% → 3%: -51 pts (-59 to -43) | 48% → 5%: -43 pts (-51 to -35) |
| Medicaid balanced accuracy | 59% → 21%: -38 pts (-48 to -27) | 54% → 25%: -29 pts (-37 to -21) |
| WIC balanced accuracy | 73% → 25%: -48 pts (-60 to -35) | 70% → 30%: -40 pts (-49 to -30) |

## By program

| Program | Measure | ID | OOD | Change |
|---|---|---|---|---|
| SNAP | **Balanced accuracy** | 6% | 13% | +7 pts (-1 to +14) |
| SNAP | Accuracy | 15% | 17% | +2 pts |
| SNAP | False denials (of truly eligible) | 4% | 4% | +1 pts |
| SNAP | False approvals (of truly ineligible) | 25% | 16% | -10 pts |
| SNAP | Amount within ±5% or ±$10 (of truly eligible) | 2% | 0% | -2 pts |
| EITC | **Balanced accuracy** | 3% | 5% | +2 pts (-2 to +7) |
| EITC | Accuracy | 11% | 10% | -0 pts |
| EITC | False denials (of truly eligible) | 7% | 4% | -3 pts |
| EITC | False approvals (of truly ineligible) | 17% | 12% | -5 pts |
| EITC | Amount within ±5% or ±$10 (of truly eligible) | 0% | 0% | +0 pts |
| Medicaid | **Balanced accuracy** | 21% | 25% | +4 pts (-5 to +13) |
| Medicaid | Accuracy | 19% | 22% | +2 pts |
| Medicaid | False denials (of truly eligible) | 42% | 47% | +5 pts |
| Medicaid | False approvals (of truly ineligible) | 18% | 14% | -5 pts |
| WIC | **Balanced accuracy** | 25% | 30% | +5 pts (-2 to +12) |
| WIC | Accuracy | 44% | 46% | +2 pts |
| WIC | False denials (of truly eligible) | 52% | 52% | +0 pts |
| WIC | False approvals (of truly ineligible) | 4% | 3% | -1 pts |

Medicaid and WIC accuracy count one decision per household member.

## OOD by shift family

| Group | n | Mean reward | SNAP balanced acc. | EITC balanced acc. | Medicaid balanced acc. | WIC balanced acc. | False denials | Malformed |
|---|---|---|---|---|---|---|---|---|
| ID (reference) | 131 | 0.18 | 6% | 3% | 21% | 25% | 28% | 35% |
| Rare household shapes | 51 | 0.09 | 7% | 2% | 22% | 31% | 46% | 41% |
| Threshold edge cases | 44 | 0.08 | 9% | 4% | 24% | 26% | 32% | 39% |
| Held-out states | 50 | 0.19 | 24% | 7% | 29% | 33% | 25% | 32% |

## OOD by twist

Rare-shape households have one or two twists, so a household can appear in two rows.

| Group | n | Mean reward | SNAP balanced acc. | EITC balanced acc. | Medicaid balanced acc. | WIC balanced acc. | False denials | Malformed |
|---|---|---|---|---|---|---|---|---|
| ID (reference) | 131 | 0.18 | 6% | 3% | 21% | 25% | 28% | 35% |
| college_student | 11 | 0.04 | 0% | 17% | 22% | 24% | 48% | 55% |
| disabled_member | 11 | 0.09 | 8% | 0% | 26% | 28% | 32% | 36% |
| edge_eitc | 10 | 0.13 | – | 0% | 29% | 37% | 62% | 10% |
| edge_medicaid | 17 | 0.00 | 0% | 3% | 7% | 14% | 18% | 65% |
| edge_snap | 17 | 0.12 | 21% | 7% | 31% | 32% | 35% | 29% |
| large_household | 9 | 0.05 | 20% | 0% | 24% | 45% | 68% | 22% |
| mixed_citizenship | 8 | 0.12 | 0% | – | 24% | 26% | 33% | 50% |
| multigenerational | 15 | 0.04 | 0% | 0% | 12% | 10% | 13% | 73% |
| pregnant_member | 10 | 0.05 | 0% | 0% | 29% | 37% | 57% | 30% |
| self_employment | 9 | 0.16 | – | 0% | 22% | 58% | 32% | 22% |

# Eval: `local/qwen3-4b-instruct`

Run `20261102-0340-harbor-qwen3-4b-instruct-n5` · Harbor 0.25.0 agent `terminus-2` on the holdout-id + holdout-ood tasks: the model reads the PDFs, runs `benefits-calc` and writes `/app/answer.json` · up to 40 turns · 30 min per task · temperature 0.0 · answers from policyengine-us 2.50.1 · cost $0.0000

Changes are OOD minus ID, with 95% bootstrap intervals over households in brackets. With about 67 households per OOD family, small gaps can be noise.

**Read the floors first.** Mean reward and plain accuracy depend on how many households qualify, and the OOD set has more eligible households than the ID set. Answering "no" to everything already scores differently on the two sets (see the floor rows). Balanced accuracy averages accuracy on truly eligible and truly ineligible decisions, so blanket answers score 50% on any set; use it to judge the ID → OOD change.

## Overall

| | ID | OOD | Change |
|---|---|---|---|
| Households scored | 5 | 5 | |
| Mean reward (0–1) | 0.15 | 0.07 | -0.08 (-0.38 to +0.13) |
| Eligibility score | 0.15 | 0.10 | -0.05 |
| Amount score | 0.00 | 0.00 | +0.00 |
| Malformed answers | 20% | 60% | +40 pts |
| Cut off at the token limit | 0 | 0 | |
| Floor: always "no" | 0.25 | 0.00 | |
| Floor: always "yes", $0 | 0.32 | 0.42 | |

## The agent

The task's own reward adds the missing-information list (weights 0.60 eligibility, 0.25 amount, 0.15 missing information), as the task verifier scores it. The mean reward above uses the evals scorer, so it compares directly with one-shot runs.

| | ID | OOD |
|---|---|---|
| Task reward, with missing information (0–1) | 0.15 | 0.10 |
| Missing-information score | 0.15 | 0.30 |
| Timed out | 2 | 1 |
| Wrote no answer file | 1 | 2 |
| Errors before the verifier (not scored) | 0 | 0 |
| Not run (shard out of time; not scored) | 0 | 0 |
| Median turns | 6 | 5 |
| Median minutes per task | 16.8 | 11.5 |

Harbor's verifier and the stored answer agree on every task's reward.

## Against the one-shot run `20261031-0030-local-qwen3-4b-instruct-docs`

The same households: there the model read the documents as text in one prompt and answered in one reply. Changes are agent minus one-shot, with 95% bootstrap intervals over households.

| | ID | OOD |
|---|---|---|
| Households in both | 5 | 5 |
| Mean reward | 0.32 → 0.15: -0.17 (-0.37 to +0.00) | 0.00 → 0.07: +0.07 (+0.00 to +0.20) |
| SNAP balanced accuracy | 17% → 0%: -17 pts (-50 to +0) | 50% → 0%: -50 pts (-50 to -50) |
| EITC balanced accuracy | 50% → 0%: -50 pts (-50 to -50) | – → –: – |
| Medicaid balanced accuracy | 50% → 32%: -18 pts (-50 to +14) | 67% → 9%: -58 pts (-83 to -22) |
| WIC balanced accuracy | 67% → 29%: -38 pts (-81 to -8) | 50% → 20%: -30 pts (-50 to -7) |

## By program

| Program | Measure | ID | OOD | Change |
|---|---|---|---|---|
| SNAP | **Balanced accuracy** | 0% | 0% | +0 pts (+0 to +0) |
| SNAP | Accuracy | 20% | 0% | -20 pts |
| SNAP | False denials (of truly eligible) | 0% | 0% | +0 pts |
| SNAP | False approvals (of truly ineligible) | 0% | 0% | +0 pts |
| SNAP | Amount within ±5% or ±$10 (of truly eligible) | 0% | 0% | +0 pts |
| EITC | **Balanced accuracy** | 0% | – | – |
| EITC | Accuracy | 20% | 0% | -20 pts |
| EITC | False denials (of truly eligible) | 0% | 0% | +0 pts |
| EITC | False approvals (of truly ineligible) | 0% | – | – |
| EITC | Amount within ±5% or ±$10 (of truly eligible) | 0% | 0% | +0 pts |
| Medicaid | **Balanced accuracy** | 32% | 9% | -23 pts (-57 to +12) |
| Medicaid | Accuracy | 20% | 12% | -8 pts |
| Medicaid | False denials (of truly eligible) | 71% | 36% | -35 pts |
| Medicaid | False approvals (of truly ineligible) | 0% | 0% | +0 pts |
| WIC | **Balanced accuracy** | 29% | 20% | -9 pts (-36 to +15) |
| WIC | Accuracy | 40% | 38% | -3 pts |
| WIC | False denials (of truly eligible) | 100% | 0% | -100 pts |
| WIC | False approvals (of truly ineligible) | 14% | 0% | -14 pts |

Medicaid and WIC accuracy count one decision per household member.

## OOD by shift family

| Group | n | Mean reward | SNAP balanced acc. | EITC balanced acc. | Medicaid balanced acc. | WIC balanced acc. | False denials | Malformed |
|---|---|---|---|---|---|---|---|---|
| ID (reference) | 5 | 0.15 | 0% | 0% | 32% | 29% | 50% | 20% |
| Rare household shapes | 2 | 0.17 | – | – | 50% | – | 0% | 50% |
| Threshold edge cases | 2 | 0.00 | 0% | – | 0% | 0% | 0% | 100% |
| Held-out states | 1 | 0.00 | – | – | – | – | 57% | 0% |

## OOD by twist

Rare-shape households have one or two twists, so a household can appear in two rows.

| Group | n | Mean reward | SNAP balanced acc. | EITC balanced acc. | Medicaid balanced acc. | WIC balanced acc. | False denials | Malformed |
|---|---|---|---|---|---|---|---|---|
| ID (reference) | 5 | 0.15 | 0% | 0% | 32% | 29% | 50% | 20% |
| edge_eitc | 1 | 0.00 | – | – | 0% | – | 0% | 100% |
| edge_snap | 1 | 0.00 | – | – | 0% | 0% | 0% | 100% |
| multigenerational | 1 | 0.00 | – | – | – | – | 0% | 100% |
| self_employment | 1 | 0.33 | – | – | – | – | 0% | 0% |

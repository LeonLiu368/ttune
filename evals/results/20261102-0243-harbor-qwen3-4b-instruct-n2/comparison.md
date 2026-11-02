# Eval: `local/qwen3-4b-instruct`

Run `20261102-0243-harbor-qwen3-4b-instruct-n2` · Harbor 0.25.0 agent `terminus-2` on the holdout-id + holdout-ood tasks: the model reads the PDFs, runs `benefits-calc` and writes `/app/answer.json` · up to 40 turns · 30 min per task · temperature 0.0 · answers from policyengine-us 2.50.1 · cost $0.0000

Changes are OOD minus ID, with 95% bootstrap intervals over households in brackets. With about 67 households per OOD family, small gaps can be noise.

**Read the floors first.** Mean reward and plain accuracy depend on how many households qualify, and the OOD set has more eligible households than the ID set. Answering "no" to everything already scores differently on the two sets (see the floor rows). Balanced accuracy averages accuracy on truly eligible and truly ineligible decisions, so blanket answers score 50% on any set; use it to judge the ID → OOD change.

## Overall

| | ID | OOD | Change |
|---|---|---|---|
| Households scored | 1 | 2 | |
| Mean reward (0–1) | 0.06 | 0.00 | -0.06 (-0.06 to -0.06) |
| Eligibility score | 0.08 | 0.00 | -0.08 |
| Amount score | 0.00 | 0.00 | +0.00 |
| Malformed answers | 0% | 50% | +50 pts |
| Cut off at the token limit | 0 | 0 | |
| Floor: always "no" | 0.50 | 0.00 | |
| Floor: always "yes", $0 | 0.28 | 0.42 | |

1 cases got no answer from the API and aren't scored; see the result files.

## The agent

The task's own reward adds the missing-information list (weights 0.60 eligibility, 0.25 amount, 0.15 missing information), as the task verifier scores it. The mean reward above uses the evals scorer, so it compares directly with one-shot runs.

| | ID | OOD |
|---|---|---|
| Task reward, with missing information (0–1) | 0.05 | 0.04 |
| Missing-information score | 0.00 | 0.25 |
| Timed out | 0 | 1 |
| Wrote no answer file | 0 | 1 |
| Errors before the verifier (not scored) | 0 | 0 |
| Not run (shard out of time; not scored) | 1 | 0 |
| Median turns | 4 | 7.0 |
| Median minutes per task | 8.7 | 18.5 |

Harbor's verifier and the stored answer agree on every task's reward.

## Against the one-shot run `20261031-0030-local-qwen3-4b-instruct-docs`

The same households: there the model read the documents as text in one prompt and answered in one reply. Changes are agent minus one-shot, with 95% bootstrap intervals over households.

| | ID | OOD |
|---|---|---|
| Households in both | 1 | 2 |
| Mean reward | 0.00 → 0.06: +0.06 (+0.06 to +0.06) | 0.00 → 0.00: +0.00 (+0.00 to +0.00) |
| SNAP balanced accuracy | – → –: – | – → –: – |
| EITC balanced accuracy | – → –: – | – → –: – |
| Medicaid balanced accuracy | 50% → 0%: -50 pts (-50 to -50) | 88% → 12%: -75 pts (-75 to -50) |
| WIC balanced accuracy | 50% → 50%: +0 pts (+0 to +0) | 50% → 20%: -30 pts (-30 to +0) |

## By program

| Program | Measure | ID | OOD | Change |
|---|---|---|---|---|
| SNAP | **Balanced accuracy** | – | – | – |
| SNAP | Accuracy | 0% | 0% | +0 pts |
| SNAP | False denials (of truly eligible) | 0% | 0% | +0 pts |
| SNAP | False approvals (of truly ineligible) | – | – | – |
| SNAP | Amount within ±5% or ±$10 (of truly eligible) | 0% | 0% | +0 pts |
| EITC | **Balanced accuracy** | – | – | – |
| EITC | Accuracy | 0% | 0% | +0 pts |
| EITC | False denials (of truly eligible) | 0% | 0% | +0 pts |
| EITC | False approvals (of truly ineligible) | – | – | – |
| EITC | Amount within ±5% or ±$10 (of truly eligible) | 0% | 0% | +0 pts |
| Medicaid | **Balanced accuracy** | 0% | 12% | +12 pts (+12 to +50) |
| Medicaid | Accuracy | 0% | 17% | +17 pts |
| Medicaid | False denials (of truly eligible) | 0% | 100% | +100 pts |
| Medicaid | False approvals (of truly ineligible) | 0% | 0% | +0 pts |
| WIC | **Balanced accuracy** | 50% | 20% | -30 pts (-30 to +0) |
| WIC | Accuracy | 33% | 33% | +0 pts |
| WIC | False denials (of truly eligible) | 0% | 100% | +100 pts |
| WIC | False approvals (of truly ineligible) | 0% | 0% | +0 pts |

Medicaid and WIC accuracy count one decision per household member.

## OOD by shift family

| Group | n | Mean reward | SNAP balanced acc. | EITC balanced acc. | Medicaid balanced acc. | WIC balanced acc. | False denials | Malformed |
|---|---|---|---|---|---|---|---|---|
| ID (reference) | 1 | 0.06 | – | – | 0% | 50% | 0% | 0% |
| Rare household shapes | 1 | 0.00 | – | – | – | – | 0% | 100% |
| Threshold edge cases | 1 | 0.00 | – | – | 50% | 50% | 60% | 0% |

## OOD by twist

Rare-shape households have one or two twists, so a household can appear in two rows.

| Group | n | Mean reward | SNAP balanced acc. | EITC balanced acc. | Medicaid balanced acc. | WIC balanced acc. | False denials | Malformed |
|---|---|---|---|---|---|---|---|---|
| ID (reference) | 1 | 0.06 | – | – | 0% | 50% | 0% | 0% |
| edge_snap | 1 | 0.00 | – | – | 50% | 50% | 60% | 0% |
| multigenerational | 1 | 0.00 | – | – | – | – | 0% | 100% |

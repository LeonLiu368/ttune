# Eval: `local/qwen3-4b-instruct`

Run `20261030-2220-local-qwen3-4b-instruct-docs-n20` · prompt v1 (`8f738e993b5ac884`) · answers from policyengine-us 2.50.1 · max tokens 6000 · cost $0.0000

Changes are OOD minus ID, with 95% bootstrap intervals over households in brackets. With about 67 households per OOD family, small gaps can be noise.

**Read the floors first.** Mean reward and plain accuracy depend on how many households qualify, and the OOD set has more eligible households than the ID set. Answering "no" to everything already scores differently on the two sets (see the floor rows). Balanced accuracy averages accuracy on truly eligible and truly ineligible decisions, so blanket answers score 50% on any set; use it to judge the ID → OOD change.

## Overall

| | ID | OOD | Change |
|---|---|---|---|
| Households scored | 20 | 20 | |
| Mean reward (0–1) | 0.44 | 0.19 | -0.25 (-0.42 to -0.06) |
| Eligibility score | 0.49 | 0.23 | -0.26 |
| Amount score | 0.11 | 0.00 | -0.11 |
| Malformed answers | 5% | 0% | -5 pts |
| Cut off at the token limit | 1 | 0 | |
| Floor: always "no" | 0.32 | 0.08 | |
| Floor: always "yes", $0 | 0.27 | 0.34 | |

## By program

| Program | Measure | ID | OOD | Change |
|---|---|---|---|---|
| SNAP | **Balanced accuracy** | 33% | 45% | +12 pts (-21 to +46) |
| SNAP | Accuracy | 35% | 45% | +10 pts |
| SNAP | False denials (of truly eligible) | 33% | 50% | +17 pts |
| SNAP | False approvals (of truly ineligible) | 56% | 50% | -6 pts |
| SNAP | Amount within ±5% or ±$10 (of truly eligible) | 11% | 0% | -11 pts |
| EITC | **Balanced accuracy** | 54% | 41% | -13 pts (-49 to +21) |
| EITC | Accuracy | 45% | 25% | -20 pts |
| EITC | False denials (of truly eligible) | 33% | 93% | +60 pts |
| EITC | False approvals (of truly ineligible) | 33% | 25% | -8 pts |
| EITC | Amount within ±5% or ±$10 (of truly eligible) | 0% | 0% | +0 pts |
| Medicaid | **Balanced accuracy** | 66% | 49% | -17 pts (-40 to +6) |
| Medicaid | Accuracy | 74% | 51% | -24 pts |
| Medicaid | False denials (of truly eligible) | 4% | 44% | +41 pts |
| Medicaid | False approvals (of truly ineligible) | 50% | 50% | +0 pts |
| WIC | **Balanced accuracy** | 71% | 83% | +12 pts (-29 to +43) |
| WIC | Accuracy | 87% | 96% | +9 pts |
| WIC | False denials (of truly eligible) | 33% | 33% | +0 pts |
| WIC | False approvals (of truly ineligible) | 0% | 0% | +0 pts |

Medicaid and WIC accuracy count one decision per household member.

## OOD by shift family

| Group | n | Mean reward | SNAP balanced acc. | EITC balanced acc. | Medicaid balanced acc. | WIC balanced acc. | False denials | Malformed |
|---|---|---|---|---|---|---|---|---|
| ID (reference) | 20 | 0.44 | 33% | 54% | 66% | 71% | 19% | 5% |
| Rare household shapes | 7 | 0.24 | 33% | 33% | 43% | 100% | 50% | 0% |
| Threshold edge cases | 7 | 0.08 | 38% | – | 37% | 75% | 73% | 0% |
| Held-out states | 6 | 0.26 | 38% | 50% | 71% | 50% | 35% | 0% |

## OOD by twist

Rare-shape households have one or two twists, so a household can appear in two rows.

| Group | n | Mean reward | SNAP balanced acc. | EITC balanced acc. | Medicaid balanced acc. | WIC balanced acc. | False denials | Malformed |
|---|---|---|---|---|---|---|---|---|
| ID (reference) | 20 | 0.44 | 33% | 54% | 66% | 71% | 19% | 5% |
| college_student | 2 | 0.22 | – | 50% | 17% | 100% | 83% | 0% |
| disabled_member | 1 | 0.17 | – | – | – | – | 33% | 0% |
| edge_eitc | 2 | 0.19 | – | – | 29% | – | 67% | 0% |
| edge_medicaid | 2 | 0.00 | – | – | – | – | 100% | 0% |
| edge_snap | 3 | 0.06 | 50% | – | 70% | 75% | 50% | 0% |
| large_household | 2 | 0.58 | – | – | 51% | 100% | 50% | 0% |
| mixed_citizenship | 1 | 0.72 | – | – | 75% | 100% | 0% | 0% |
| multigenerational | 1 | 0.00 | – | – | – | – | 100% | 0% |
| pregnant_member | 2 | 0.19 | – | 0% | 25% | 100% | 33% | 0% |
| self_employment | 2 | 0.08 | – | – | – | – | 50% | 0% |

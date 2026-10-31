# Eval: `local/qwen3-4b-instruct`

Run `20261031-0030-local-qwen3-4b-instruct-docs` · document cases (application and paperwork, data/documents) · document prompt v1 (`8f738e993b5ac884`) · answers from policyengine-us 2.50.1 · max tokens 6000 · cost $0.0000

Changes are OOD minus ID, with 95% bootstrap intervals over households in brackets. With about 67 households per OOD family, small gaps can be noise.

**Read the floors first.** Mean reward and plain accuracy depend on how many households qualify, and the OOD set has more eligible households than the ID set. Answering "no" to everything already scores differently on the two sets (see the floor rows). Balanced accuracy averages accuracy on truly eligible and truly ineligible decisions, so blanket answers score 50% on any set; use it to judge the ID → OOD change.

## Overall

| | ID | OOD | Change |
|---|---|---|---|
| Households scored | 200 | 200 | |
| Mean reward (0–1) | 0.45 | 0.31 | -0.14 (-0.20 to -0.08) |
| Eligibility score | 0.50 | 0.36 | -0.14 |
| Amount score | 0.05 | 0.03 | -0.02 |
| Malformed answers | 2% | 2% | +1 pts |
| Cut off at the token limit | 4 | 6 | |
| Floor: always "no" | 0.34 | 0.21 | |
| Floor: always "yes", $0 | 0.21 | 0.30 | |

## By program

| Program | Measure | ID | OOD | Change |
|---|---|---|---|---|
| SNAP | **Balanced accuracy** | 58% | 59% | +1 pts (-10 to +11) |
| SNAP | Accuracy | 61% | 57% | -4 pts |
| SNAP | False denials (of truly eligible) | 30% | 36% | +6 pts |
| SNAP | False approvals (of truly ineligible) | 36% | 33% | -3 pts |
| SNAP | Amount within ±5% or ±$10 (of truly eligible) | 4% | 1% | -3 pts |
| EITC | **Balanced accuracy** | 54% | 50% | -4 pts (-13 to +5) |
| EITC | Accuracy | 48% | 42% | -5 pts |
| EITC | False denials (of truly eligible) | 65% | 69% | +3 pts |
| EITC | False approvals (of truly ineligible) | 12% | 15% | +3 pts |
| EITC | Amount within ±5% or ±$10 (of truly eligible) | 1% | 1% | -0 pts |
| Medicaid | **Balanced accuracy** | 63% | 54% | -9 pts (-17 to -1) |
| Medicaid | Accuracy | 64% | 55% | -9 pts |
| Medicaid | False denials (of truly eligible) | 19% | 34% | +15 pts |
| Medicaid | False approvals (of truly ineligible) | 44% | 48% | +4 pts |
| WIC | **Balanced accuracy** | 75% | 69% | -6 pts (-18 to +5) |
| WIC | Accuracy | 88% | 84% | -5 pts |
| WIC | False denials (of truly eligible) | 31% | 46% | +15 pts |
| WIC | False approvals (of truly ineligible) | 2% | 3% | +1 pts |

Medicaid and WIC accuracy count one decision per household member.

## OOD by shift family

| Group | n | Mean reward | SNAP balanced acc. | EITC balanced acc. | Medicaid balanced acc. | WIC balanced acc. | False denials | Malformed |
|---|---|---|---|---|---|---|---|---|
| ID (reference) | 200 | 0.45 | 58% | 54% | 63% | 75% | 33% | 2% |
| Rare household shapes | 67 | 0.30 | 50% | 54% | 47% | 68% | 44% | 3% |
| Threshold edge cases | 67 | 0.22 | 54% | 38% | 61% | 64% | 54% | 1% |
| Held-out states | 66 | 0.41 | 66% | 57% | 54% | 76% | 26% | 3% |

## OOD by twist

Rare-shape households have one or two twists, so a household can appear in two rows.

| Group | n | Mean reward | SNAP balanced acc. | EITC balanced acc. | Medicaid balanced acc. | WIC balanced acc. | False denials | Malformed |
|---|---|---|---|---|---|---|---|---|
| ID (reference) | 200 | 0.45 | 58% | 54% | 63% | 75% | 33% | 2% |
| college_student | 13 | 0.21 | 55% | 44% | 49% | 63% | 43% | 0% |
| disabled_member | 14 | 0.23 | 46% | 43% | 64% | 73% | 34% | 0% |
| edge_eitc | 22 | 0.33 | 33% | 34% | 57% | 65% | 69% | 0% |
| edge_medicaid | 22 | 0.23 | 76% | 64% | 61% | 55% | 48% | 0% |
| edge_snap | 23 | 0.11 | 41% | 24% | 59% | 77% | 54% | 4% |
| large_household | 15 | 0.40 | 55% | 83% | 38% | 69% | 51% | 0% |
| mixed_citizenship | 10 | 0.44 | 42% | – | 58% | 56% | 50% | 10% |
| multigenerational | 17 | 0.22 | 55% | 44% | 57% | 54% | 44% | 0% |
| pregnant_member | 13 | 0.31 | 55% | 61% | 35% | 63% | 53% | 0% |
| self_employment | 14 | 0.32 | 70% | 54% | 39% | 75% | 43% | 7% |

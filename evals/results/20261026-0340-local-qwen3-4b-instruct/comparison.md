# Eval: `local/qwen3-4b-instruct`

Run `20261026-0340-local-qwen3-4b-instruct` · prompt v1 (`99462b99b4b17c82`) · answers from policyengine-us 2.50.1 · max tokens 6000 · cost $0.0000

Changes are OOD minus ID, with 95% bootstrap intervals over households in brackets. With about 67 households per OOD family, small gaps can be noise.

**Read the floors first.** Mean reward and plain accuracy depend on how many households qualify, and the OOD set has more eligible households than the ID set. Answering "no" to everything already scores differently on the two sets (see the floor rows). Balanced accuracy averages accuracy on truly eligible and truly ineligible decisions, so blanket answers score 50% on any set; use it to judge the ID → OOD change.

## Overall

| | ID | OOD | Change |
|---|---|---|---|
| Households scored | 200 | 200 | |
| Mean reward (0–1) | 0.44 | 0.35 | -0.10 (-0.17 to -0.02) |
| Eligibility score | 0.50 | 0.39 | -0.11 |
| Amount score | 0.05 | 0.08 | +0.03 |
| Malformed answers | 6% | 2% | -3 pts |
| Cut off at the token limit | 12 | 5 | |
| Floor: always "no" | 0.35 | 0.22 | |
| Floor: always "yes", $0 | 0.26 | 0.32 | |

## By program

| Program | Measure | ID | OOD | Change |
|---|---|---|---|---|
| SNAP | **Balanced accuracy** | 63% | 60% | -4 pts (-13 to +6) |
| SNAP | Accuracy | 64% | 60% | -4 pts |
| SNAP | False denials (of truly eligible) | 42% | 54% | +12 pts |
| SNAP | False approvals (of truly ineligible) | 19% | 20% | +1 pts |
| SNAP | Amount within ±5% or ±$10 (of truly eligible) | 2% | 2% | -0 pts |
| EITC | **Balanced accuracy** | 62% | 61% | -0 pts (-9 to +8) |
| EITC | Accuracy | 59% | 56% | -3 pts |
| EITC | False denials (of truly eligible) | 54% | 53% | -1 pts |
| EITC | False approvals (of truly ineligible) | 13% | 19% | +6 pts |
| EITC | Amount within ±5% or ±$10 (of truly eligible) | 0% | 2% | +2 pts |
| Medicaid | **Balanced accuracy** | 63% | 62% | -1 pts (-10 to +7) |
| Medicaid | Accuracy | 63% | 61% | -2 pts |
| Medicaid | False denials (of truly eligible) | 29% | 43% | +14 pts |
| Medicaid | False approvals (of truly ineligible) | 27% | 30% | +3 pts |
| WIC | **Balanced accuracy** | 69% | 67% | -2 pts (-13 to +9) |
| WIC | Accuracy | 84% | 85% | +1 pts |
| WIC | False denials (of truly eligible) | 33% | 60% | +26 pts |
| WIC | False approvals (of truly ineligible) | 4% | 2% | -2 pts |

Medicaid and WIC accuracy count one decision per household member.

## OOD by shift family

| Group | n | Mean reward | SNAP balanced acc. | EITC balanced acc. | Medicaid balanced acc. | WIC balanced acc. | False denials | Malformed |
|---|---|---|---|---|---|---|---|---|
| ID (reference) | 200 | 0.44 | 63% | 62% | 63% | 69% | 37% | 6% |
| Rare household shapes | 67 | 0.33 | 58% | 63% | 60% | 67% | 54% | 3% |
| Threshold edge cases | 67 | 0.28 | 54% | 47% | 58% | 61% | 55% | 3% |
| Held-out states | 66 | 0.43 | 64% | 68% | 68% | 74% | 35% | 2% |

## OOD by twist

Rare-shape households have one or two twists, so a household can appear in two rows.

| Group | n | Mean reward | SNAP balanced acc. | EITC balanced acc. | Medicaid balanced acc. | WIC balanced acc. | False denials | Malformed |
|---|---|---|---|---|---|---|---|---|
| ID (reference) | 200 | 0.44 | 63% | 62% | 63% | 69% | 37% | 6% |
| college_student | 13 | 0.23 | 39% | 65% | 54% | 55% | 53% | 15% |
| disabled_member | 14 | 0.33 | 79% | 65% | 61% | 45% | 45% | 7% |
| edge_eitc | 22 | 0.42 | 45% | 47% | 58% | 58% | 69% | 0% |
| edge_medicaid | 22 | 0.19 | 54% | 74% | 50% | 57% | 46% | 9% |
| edge_snap | 23 | 0.22 | 34% | 32% | 60% | 66% | 59% | 0% |
| large_household | 15 | 0.31 | 62% | 70% | 58% | 71% | 62% | 0% |
| mixed_citizenship | 10 | 0.56 | 50% | – | 79% | 68% | 47% | 0% |
| multigenerational | 17 | 0.28 | 58% | 61% | 50% | 58% | 68% | 0% |
| pregnant_member | 13 | 0.41 | 61% | 52% | 54% | 82% | 40% | 0% |
| self_employment | 14 | 0.24 | 62% | 62% | 79% | 64% | 54% | 0% |

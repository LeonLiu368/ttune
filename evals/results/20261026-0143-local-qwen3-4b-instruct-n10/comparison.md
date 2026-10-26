# Eval: `local/qwen3-4b-instruct`

Run `20261026-0143-local-qwen3-4b-instruct-n10` · prompt v1 (`99462b99b4b17c82`) · answers from policyengine-us 2.50.1 · max tokens 3000 · cost $0.0000

Changes are OOD minus ID, with 95% bootstrap intervals over households in brackets. With about 67 households per OOD family, small gaps can be noise.

**Read the floors first.** Mean reward and plain accuracy depend on how many households qualify, and the OOD set has more eligible households than the ID set. Answering "no" to everything already scores differently on the two sets (see the floor rows). Balanced accuracy averages accuracy on truly eligible and truly ineligible decisions, so blanket answers score 50% on any set; use it to judge the ID → OOD change.

## Overall

| | ID | OOD | Change |
|---|---|---|---|
| Households scored | 10 | 10 | |
| Mean reward (0–1) | 0.22 | 0.04 | -0.17 (-0.46 to +0.04) |
| Eligibility score | 0.23 | 0.05 | -0.17 |
| Amount score | 0.00 | 0.03 | +0.03 |
| Malformed answers | 60% | 50% | -10 pts |
| Cut off at the token limit | 6 | 5 | |
| Floor: always "no" | 0.19 | 0.00 | |
| Floor: always "yes", $0 | 0.37 | 0.41 | |

## By program

| Program | Measure | ID | OOD | Change |
|---|---|---|---|---|
| SNAP | **Balanced accuracy** | 50% | 14% | -36 pts (-50 to -17) |
| SNAP | Accuracy | 30% | 20% | -10 pts |
| SNAP | False denials (of truly eligible) | 14% | 43% | +29 pts |
| SNAP | False approvals (of truly ineligible) | 0% | 0% | +0 pts |
| SNAP | Amount within ±5% or ±$10 (of truly eligible) | 0% | 0% | +0 pts |
| EITC | **Balanced accuracy** | 50% | – | – |
| EITC | Accuracy | 30% | 0% | -30 pts |
| EITC | False denials (of truly eligible) | 14% | 50% | +36 pts |
| EITC | False approvals (of truly ineligible) | 0% | – | – |
| EITC | Amount within ±5% or ±$10 (of truly eligible) | 0% | 0% | +0 pts |
| Medicaid | **Balanced accuracy** | 45% | 16% | -30 pts (-52 to +7) |
| Medicaid | Accuracy | 25% | 17% | -8 pts |
| Medicaid | False denials (of truly eligible) | 5% | 42% | +37 pts |
| Medicaid | False approvals (of truly ineligible) | 0% | 0% | +0 pts |
| WIC | **Balanced accuracy** | 16% | 40% | +24 pts (-12 to +75) |
| WIC | Accuracy | 25% | 45% | +20 pts |
| WIC | False denials (of truly eligible) | 17% | 0% | -17 pts |
| WIC | False approvals (of truly ineligible) | 0% | 0% | +0 pts |

Medicaid and WIC accuracy count one decision per household member.

## OOD by shift family

| Group | n | Mean reward | SNAP balanced acc. | EITC balanced acc. | Medicaid balanced acc. | WIC balanced acc. | False denials | Malformed |
|---|---|---|---|---|---|---|---|---|
| ID (reference) | 10 | 0.22 | 50% | 50% | 45% | 16% | 10% | 60% |
| Rare household shapes | 4 | 0.11 | 33% | – | 33% | 14% | 17% | 50% |
| Threshold edge cases | 3 | 0.00 | 0% | – | 38% | 78% | 50% | 33% |
| Held-out states | 3 | 0.00 | 0% | – | 0% | – | 54% | 67% |

## OOD by twist

Rare-shape households have one or two twists, so a household can appear in two rows.

| Group | n | Mean reward | SNAP balanced acc. | EITC balanced acc. | Medicaid balanced acc. | WIC balanced acc. | False denials | Malformed |
|---|---|---|---|---|---|---|---|---|
| ID (reference) | 10 | 0.22 | 50% | 50% | 45% | 16% | 10% | 60% |
| college_student | 1 | 0.00 | – | – | 0% | 0% | 0% | 100% |
| disabled_member | 1 | 0.26 | – | – | – | – | 33% | 0% |
| edge_eitc | 1 | 0.00 | – | – | 0% | – | 0% | 100% |
| edge_medicaid | 1 | 0.00 | – | – | – | – | 100% | 0% |
| edge_snap | 1 | 0.00 | – | – | 100% | 100% | 40% | 0% |
| multigenerational | 1 | 0.00 | – | – | – | – | 0% | 100% |
| pregnant_member | 1 | 0.00 | – | – | 0% | 0% | 0% | 100% |
| self_employment | 2 | 0.21 | – | – | – | – | 33% | 0% |

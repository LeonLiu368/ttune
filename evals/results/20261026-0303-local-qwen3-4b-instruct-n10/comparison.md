# Eval: `local/qwen3-4b-instruct`

Run `20261026-0303-local-qwen3-4b-instruct-n10` · prompt v1 (`99462b99b4b17c82`) · answers from policyengine-us 2.50.1 · max tokens 6000 · cost $0.0000

Changes are OOD minus ID, with 95% bootstrap intervals over households in brackets. With about 67 households per OOD family, small gaps can be noise.

**Read the floors first.** Mean reward and plain accuracy depend on how many households qualify, and the OOD set has more eligible households than the ID set. Answering "no" to everything already scores differently on the two sets (see the floor rows). Balanced accuracy averages accuracy on truly eligible and truly ineligible decisions, so blanket answers score 50% on any set; use it to judge the ID → OOD change.

## Overall

| | ID | OOD | Change |
|---|---|---|---|
| Households scored | 10 | 10 | |
| Mean reward (0–1) | 0.39 | 0.17 | -0.22 (-0.50 to +0.03) |
| Eligibility score | 0.44 | 0.22 | -0.23 |
| Amount score | 0.10 | 0.06 | -0.04 |
| Malformed answers | 0% | 10% | +10 pts |
| Cut off at the token limit | 0 | 1 | |
| Floor: always "no" | 0.19 | 0.00 | |
| Floor: always "yes", $0 | 0.37 | 0.41 | |

## By program

| Program | Measure | ID | OOD | Change |
|---|---|---|---|---|
| SNAP | **Balanced accuracy** | 71% | 29% | -43 pts (-69 to -17) |
| SNAP | Accuracy | 60% | 40% | -20 pts |
| SNAP | False denials (of truly eligible) | 57% | 43% | -14 pts |
| SNAP | False approvals (of truly ineligible) | 0% | 67% | +67 pts |
| SNAP | Amount within ±5% or ±$10 (of truly eligible) | 0% | 0% | +0 pts |
| EITC | **Balanced accuracy** | 93% | – | – |
| EITC | Accuracy | 90% | 20% | -70 pts |
| EITC | False denials (of truly eligible) | 14% | 70% | +56 pts |
| EITC | False approvals (of truly ineligible) | 0% | – | – |
| EITC | Amount within ±5% or ±$10 (of truly eligible) | 0% | 0% | +0 pts |
| Medicaid | **Balanced accuracy** | 71% | 31% | -40 pts (-68 to -4) |
| Medicaid | Accuracy | 57% | 34% | -23 pts |
| Medicaid | False denials (of truly eligible) | 57% | 42% | -15 pts |
| Medicaid | False approvals (of truly ineligible) | 0% | 70% | +70 pts |
| WIC | **Balanced accuracy** | 73% | 92% | +20 pts (-12 to +43) |
| WIC | Accuracy | 86% | 86% | +0 pts |
| WIC | False denials (of truly eligible) | 50% | 0% | -50 pts |
| WIC | False approvals (of truly ineligible) | 5% | 0% | -5 pts |

Medicaid and WIC accuracy count one decision per household member.

## OOD by shift family

| Group | n | Mean reward | SNAP balanced acc. | EITC balanced acc. | Medicaid balanced acc. | WIC balanced acc. | False denials | Malformed |
|---|---|---|---|---|---|---|---|---|
| ID (reference) | 10 | 0.39 | 71% | 93% | 71% | 73% | 49% | 0% |
| Rare household shapes | 4 | 0.27 | 50% | – | 58% | 100% | 25% | 0% |
| Threshold edge cases | 3 | 0.00 | 0% | – | 38% | 78% | 50% | 33% |
| Held-out states | 3 | 0.19 | 25% | – | 19% | – | 62% | 0% |

## OOD by twist

Rare-shape households have one or two twists, so a household can appear in two rows.

| Group | n | Mean reward | SNAP balanced acc. | EITC balanced acc. | Medicaid balanced acc. | WIC balanced acc. | False denials | Malformed |
|---|---|---|---|---|---|---|---|---|
| ID (reference) | 10 | 0.39 | 71% | 93% | 71% | 73% | 49% | 0% |
| college_student | 1 | 0.00 | – | – | 50% | 100% | 25% | 0% |
| disabled_member | 1 | 0.26 | – | – | – | – | 33% | 0% |
| edge_eitc | 1 | 0.00 | – | – | 0% | – | 0% | 100% |
| edge_medicaid | 1 | 0.00 | – | – | – | – | 100% | 0% |
| edge_snap | 1 | 0.00 | – | – | 100% | 100% | 40% | 0% |
| multigenerational | 1 | 0.68 | – | – | – | – | 0% | 0% |
| pregnant_member | 1 | 0.00 | – | – | 50% | 100% | 25% | 0% |
| self_employment | 2 | 0.21 | – | – | – | – | 33% | 0% |

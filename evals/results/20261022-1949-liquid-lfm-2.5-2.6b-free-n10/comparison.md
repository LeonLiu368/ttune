# Eval: `liquid/lfm-2.5-2.6b:free`

Run `20261022-1949-liquid-lfm-2.5-2.6b-free-n10` · prompt v1 (`99462b99b4b17c82`) · answers from policyengine-us 2.50.1 · max tokens 8000 · reasoning effort low · cost $0.0000

Changes are OOD minus ID, with 95% bootstrap intervals over households in brackets. With about 67 households per OOD family, small gaps can be noise.

**Read the floors first.** Mean reward and plain accuracy depend on how many households qualify, and the OOD set has more eligible households than the ID set. Answering "no" to everything already scores differently on the two sets (see the floor rows). Balanced accuracy averages accuracy on truly eligible and truly ineligible decisions, so blanket answers score 50% on any set; use it to judge the ID → OOD change.

## Overall

| | ID | OOD | Change |
|---|---|---|---|
| Households scored | 10 | 10 | |
| Mean reward (0–1) | 0.00 | 0.00 | +0.00 (+0.00 to +0.00) |
| Eligibility score | 0.00 | 0.00 | +0.00 |
| Amount score | 0.00 | 0.00 | +0.00 |
| Malformed answers | 100% | 90% | -10 pts |
| Cut off at the token limit | 0 | 0 | |
| Floor: always "no" | 0.19 | 0.00 | |
| Floor: always "yes", $0 | 0.37 | 0.41 | |

## By program

| Program | Measure | ID | OOD | Change |
|---|---|---|---|---|
| SNAP | **Balanced accuracy** | 0% | 0% | +0 pts (+0 to +0) |
| SNAP | Accuracy | 0% | 0% | +0 pts |
| SNAP | False denials (of truly eligible) | 0% | 14% | +14 pts |
| SNAP | False approvals (of truly ineligible) | 0% | 0% | +0 pts |
| SNAP | Amount within ±5% or ±$10 (of truly eligible) | 0% | 0% | +0 pts |
| EITC | **Balanced accuracy** | 0% | – | – |
| EITC | Accuracy | 0% | 0% | +0 pts |
| EITC | False denials (of truly eligible) | 0% | 10% | +10 pts |
| EITC | False approvals (of truly ineligible) | 0% | – | – |
| EITC | Amount within ±5% or ±$10 (of truly eligible) | 0% | 0% | +0 pts |
| Medicaid | **Balanced accuracy** | 0% | 5% | +5 pts (+0 to +25) |
| Medicaid | Accuracy | 0% | 3% | +3 pts |
| Medicaid | False denials (of truly eligible) | 0% | 11% | +11 pts |
| Medicaid | False approvals (of truly ineligible) | 0% | 0% | +0 pts |
| WIC | **Balanced accuracy** | 0% | 21% | +21 pts (+0 to +62) |
| WIC | Accuracy | 0% | 10% | +10 pts |
| WIC | False denials (of truly eligible) | 0% | 0% | +0 pts |
| WIC | False approvals (of truly ineligible) | 0% | 0% | +0 pts |

Medicaid and WIC accuracy count one decision per household member.

## OOD by shift family

| Group | n | Mean reward | SNAP balanced acc. | EITC balanced acc. | Medicaid balanced acc. | WIC balanced acc. | False denials | Malformed |
|---|---|---|---|---|---|---|---|---|
| ID (reference) | 10 | 0.00 | 0% | 0% | 0% | 0% | 0% | 100% |
| Rare household shapes | 4 | 0.00 | 0% | – | 0% | 0% | 0% | 100% |
| Threshold edge cases | 3 | 0.00 | 0% | – | 25% | 61% | 29% | 67% |
| Held-out states | 3 | 0.00 | 0% | – | 0% | – | 0% | 100% |

## OOD by twist

Rare-shape households have one or two twists, so a household can appear in two rows.

| Group | n | Mean reward | SNAP balanced acc. | EITC balanced acc. | Medicaid balanced acc. | WIC balanced acc. | False denials | Malformed |
|---|---|---|---|---|---|---|---|---|
| ID (reference) | 10 | 0.00 | 0% | 0% | 0% | 0% | 0% | 100% |
| college_student | 1 | 0.00 | – | – | 0% | 0% | 0% | 100% |
| disabled_member | 1 | 0.00 | – | – | – | – | 0% | 100% |
| edge_eitc | 1 | 0.00 | – | – | 0% | – | 0% | 100% |
| edge_medicaid | 1 | 0.00 | – | – | – | – | 0% | 100% |
| edge_snap | 1 | 0.00 | – | – | 50% | 100% | 80% | 0% |
| multigenerational | 1 | 0.00 | – | – | – | – | 0% | 100% |
| pregnant_member | 1 | 0.00 | – | – | 0% | 0% | 0% | 100% |
| self_employment | 2 | 0.00 | – | – | – | – | 0% | 100% |

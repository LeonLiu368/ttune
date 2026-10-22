# Eval: `google/gemma-4-26b-a4b-it:free`

Run `20261022-1747-google-gemma-4-26b-a4b-it-free-n10` · prompt v1 (`99462b99b4b17c82`) · answers from policyengine-us 2.50.1 · cost $0.0000

Changes are OOD minus ID, with 95% bootstrap intervals over households in brackets. With about 67 households per OOD family, small gaps can be noise.

**Read the floors first.** Mean reward and plain accuracy depend on how many households qualify, and the OOD set has more eligible households than the ID set. Answering "no" to everything already scores differently on the two sets (see the floor rows). Balanced accuracy averages accuracy on truly eligible and truly ineligible decisions, so blanket answers score 50% on any set; use it to judge the ID → OOD change.

## Overall

| | ID | OOD | Change |
|---|---|---|---|
| Floor: always "no" | 0.19 | 0.00 | |
| Floor: always "yes", $0 | 0.37 | 0.41 | |

20 cases got no answer from the API and aren't scored; see the result files.

## By program

| Program | Measure | ID | OOD | Change |
|---|---|---|---|---|

Medicaid and WIC accuracy count one decision per household member.

## OOD by shift family

| Group | n | Mean reward | SNAP balanced acc. | EITC balanced acc. | Medicaid balanced acc. | WIC balanced acc. | False denials | Malformed |
|---|---|---|---|---|---|---|---|---|

## OOD by twist

Rare-shape households have one or two twists, so a household can appear in two rows.

| Group | n | Mean reward | SNAP balanced acc. | EITC balanced acc. | Medicaid balanced acc. | WIC balanced acc. | False denials | Malformed |
|---|---|---|---|---|---|---|---|---|

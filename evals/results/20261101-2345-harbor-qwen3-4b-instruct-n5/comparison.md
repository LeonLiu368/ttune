# Eval: `local/qwen3-4b-instruct`

Run `20261101-2345-harbor-qwen3-4b-instruct-n5` · Harbor 0.25.0 agent `terminus-2` on the holdout-id + holdout-ood tasks: the model reads the PDFs, runs `benefits-calc` and writes `/app/answer.json` · up to 40 turns · 30 min per task · temperature 0.0 · answers from policyengine-us 2.50.1 · cost $0.0000

Changes are OOD minus ID, with 95% bootstrap intervals over households in brackets. With about 67 households per OOD family, small gaps can be noise.

**Read the floors first.** Mean reward and plain accuracy depend on how many households qualify, and the OOD set has more eligible households than the ID set. Answering "no" to everything already scores differently on the two sets (see the floor rows). Balanced accuracy averages accuracy on truly eligible and truly ineligible decisions, so blanket answers score 50% on any set; use it to judge the ID → OOD change.

## Overall

| | ID | OOD | Change |
|---|---|---|---|
| Floor: always "no" | 0.25 | 0.00 | |
| Floor: always "yes", $0 | 0.32 | 0.42 | |

10 cases got no answer from the API and aren't scored; see the result files.

## The agent

The task's own reward adds the missing-information list (weights 0.60 eligibility, 0.25 amount, 0.15 missing information), as the task verifier scores it. The mean reward above uses the evals scorer, so it compares directly with one-shot runs.

| | ID | OOD |
|---|---|---|
| Task reward, with missing information (0–1) | – | – |
| Missing-information score | – | – |
| Timed out | 0 | 0 |
| Wrote no answer file | 0 | 0 |
| Errors before the verifier (not scored) | 0 | 0 |
| Not run (shard out of time; not scored) | 5 | 5 |
| Median turns | – | – |
| Median minutes per task | – | – |

Harbor's verifier and the stored answer agree on every task's reward.

## Against the one-shot run `20261031-0030-local-qwen3-4b-instruct-docs`

The same households: there the model read the documents as text in one prompt and answered in one reply. Changes are agent minus one-shot, with 95% bootstrap intervals over households.

| | ID | OOD |
|---|---|---|
| Households in both | 0 | 0 |
| Mean reward | – → –: – | – → –: – |
| SNAP balanced accuracy | – → –: – | – → –: – |
| EITC balanced accuracy | – → –: – | – → –: – |
| Medicaid balanced accuracy | – → –: – | – → –: – |
| WIC balanced accuracy | – → –: – | – → –: – |

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

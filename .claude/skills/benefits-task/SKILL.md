---
name: benefits-task
description: Build Harbor tasks for ttune's public-benefits eligibility environment — synthetic household generation, messy document rendering, PolicyEngine ground truth, the answer contract, and the asymmetric reward. Use whenever working on the benefits/eligibility env, SNAP/Medicaid/EITC/WIC tasks, the household generator, PolicyEngine-backed verifiers, or turning docs/04 into code, even if the user just says "the env" or "next task".
---

# Benefits eligibility tasks

The environment: an agent reads a household's messy paperwork, uses PolicyEngine as a calculator, and reports which programs the household qualifies for and how much. The design rationale is in `docs/04-benefits-eligibility-plan.md`. Read it first; this skill is the how.

For generic Harbor mechanics (scaffolding, task.toml fields, Oracle runs) use the `create-task` skill. For verifier criteria syntax use the `rewardkit` skill. This skill covers what is specific to this domain.

## What the agent is actually being trained on

The agent has PolicyEngine available inside its container. That's deliberate: caseworkers use calculators, and the hard, realistic skill is everything around the calculation:

1. Extracting the right facts from documents that disagree with each other.
2. Noticing missing information and flagging it instead of guessing.
3. Reporting results in a form a person can act on.

Keep this in mind when making tasks harder. Add difficulty to the documents (contradictions, missing pages, irregular income), not by hiding the calculator.

## Pipeline: one generator, many tasks

Write a generator, never hand-write tasks. Each generated task goes through these stages:

1. **Sample a household** with a seeded RNG: members, ages, relationships, state, income sources (wages, gig, SSI, child support), housing costs, childcare, disability, immigration status where it matters. Skew toward the hard cases (self-employed, multi-generational, mid-year changes), since that's where caseworkers err and where the fairness checks in docs/04 look.
2. **Compute ground truth** with PolicyEngine for every program in scope.
3. **Render documents** from the household: pay stubs, lease, benefit letters, an application form. Then inject noise from a known list: a stale pay stub, a lease with a different rent than the application, a missing page, a handwritten-looking scan. Record every injected issue, because the verifier needs to know what "missing information" should have been flagged.
4. **Write the Harbor task directory** (layout below).

Record the seed, the PolicyEngine package version and the rules year in every task's `task.toml` `[metadata]`. Rules change yearly; without this you can't tell which tasks are stale.

## PolicyEngine usage

Use the `policyengine-us` Python package and pin its version in both images. Build a situation dict (people, tax units, SPM units, households, families, marital units) and call `Simulation(situation=...).calculate(<variable>, <year>)`.

Variable names change between releases, so don't hard-code them from memory. Before using a name, confirm it exists in the installed version:

```python
from policyengine_us import CountryTaxBenefitSystem
names = CountryTaxBenefitSystem().variables
for v in ["snap", "eitc", "wic", "is_medicaid_eligible"]:
    print(v, v in names)
```

If a name is missing, search `names` for the program and use the right one. Write the mapping into the generator as a single table so it's updated in one place.

## Task layout

```
benefits-<seed>/
├── task.toml
├── instruction.md
├── environment/
│   ├── Dockerfile        # python + pinned policyengine-us; copies docs/ into /app/case/
│   └── case/             # rendered documents only — never ground truth
├── tests/
│   ├── Dockerfile        # verifier image: python + rewardkit + ground truth baked in
│   ├── test.sh
│   ├── truth.json        # PolicyEngine output + injected-issue list
│   └── checks.py
└── solution/solve.sh     # writes the correct answer.json (for Oracle)
```

Use a **separate verifier** with a dedicated image (`tests/Dockerfile`) so `truth.json` never enters the agent's container. Declare the answer as an artifact so Harbor copies it across:

```toml
artifacts = ["/app/answer.json"]

[verifier.environment]
network_mode = "no-network"
```

## Answer contract

State this schema in `instruction.md`. It's the output format, not the rubric, so it's fine to show:

```json
{
  "programs": {
    "snap":     {"eligible": true,  "monthly_amount": 412.0},
    "medicaid": {"eligible": false, "monthly_amount": null},
    "eitc":     {"eligible": true,  "annual_amount": 3995.0},
    "wic":      {"eligible": "unknown", "monthly_amount": null}
  },
  "missing_information": ["2nd pay stub for March", "..."],
  "documents_to_submit": ["..."],
  "explanation": "plain-language summary for the household"
}
```

`"unknown"` is a legitimate answer when the documents truly don't determine eligibility. That's what makes asking for missing information rewardable.

## Reward

Emit separate dimensions in `reward.json` so training can weight them and you can see what the model learns:

| Dimension | Scoring |
|---|---|
| `eligibility` | `max(0, (correct − 2 × false_denials) / n_programs)`. **A false "not eligible" when truly eligible costs double**, because that's the error that costs people food or healthcare; a false "eligible" just earns nothing. Clipping keeps it in Reward Kit's 0–1 range. |
| `amount` | Per eligible program: 1 within ±5% (or ±$10), linear decay to 0 at ±25%. |
| `missing_info` | Recall of injected missing-info issues, minus a small penalty for each spurious flag, so flagging everything doesn't pay. |
| `unknown_use` | "unknown" scores 0.5 when the truth list says the documents were insufficient, and 0 otherwise. Blanket hedging doesn't pay. |

Aggregate with a weighted mean into a top-level `reward` key. Start with eligibility 0.5, amount 0.25, missing_info 0.15, unknown_use 0.10, and record the weights in docs/04 whenever they change.

Keep the `explanation` field ungraded at first. If it gets graded later, use a separate judge dimension so it can't mask calculation errors.

## Before calling a task done

1. Oracle run scores ~1.0: `harbor run -p <task> -a oracle`.
2. Run the `reward-hack-audit` skill on the task. Degenerate answers (all eligible, all unknown, flag everything) must score low.
3. Sanity-check difficulty with one real agent run. If every model gets 1.0, add document noise.

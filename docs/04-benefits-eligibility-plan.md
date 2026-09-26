# 04 – Benefits eligibility plan

**Domain:** public-benefits eligibility. The agent reads a household's messy paperwork and works out which programs they qualify for (SNAP, Medicaid, EITC, WIC and similar) and for how much.

## Why this domain

- **Real impact.** Billions of dollars in benefits go unclaimed every year; the IRS estimates about 1 in 5 EITC-eligible households don't claim it. The rules are complicated enough that people and caseworkers regularly get them wrong.
- **A free, exact verifier.** [PolicyEngine](https://github.com/PolicyEngine) is an open-source engine encoding US and UK tax and benefit rules. Give it a household and it returns eligibility and amounts, so there's ground truth with no human grading.
- **Low compute.** Text plus CPU-side verification; a 4–8B model is enough.
- **Fits the trends** ([03](03-trends-2026.md)): underserved government/enterprise work, procedurally generatable, outcomes hard to game.

## Key design choice

Give the model PolicyEngine **as a tool**, the way a caseworker uses a calculator. Then the skill it has to learn is the realistic hard part:

- pulling the right facts out of pay stubs, leases and letters,
- noticing when something is missing and asking for it instead of guessing,
- explaining the result and listing the documents to submit.

## Build plan

### 1. Environment (Harbor task)
- Generate synthetic households from PolicyEngine's data or my own sampler.
- Render them as messy documents: irregular pay, a partner who moved out, a lease that contradicts the application.
- Verifier compares the agent's answer to PolicyEngine's output.
- Synthetic households only, so no privacy exposure.

### 2. Reward
- Partial credit per program for eligibility and amount, within a tolerance.
- Large penalty for a confidently wrong "not eligible" (the harmful error).
- Reward for correctly flagging missing information.
- Ground truth lives outside the container so the agent can't read it.

### 3. Model
- Small open-weight instruct model (4–8B) with LoRA.
- Measure a baseline first.
- SFT warm-start on ~1–2k good trajectories from a stronger model (check that its license allows training on outputs).
- GRPO in the environment using TRL, verl or SkyRL on one rented GPU, or a hosted service like Tinker to skip GPU management.

### 4. Evaluation
- Hold out whole states or programs to test generalization, not memorization.
- Track wrong denials separately from overall accuracy.
- Red-team the verifier myself.

## Risks to handle up front

- **Errors hurt real people.** A false "not eligible" can mean someone goes without food or healthcare. Treat the model as a screening assistant that sends people to apply, never the decision-maker, and bias it toward "you may qualify, apply".
- **Rules change yearly and differ by state.** Record the PolicyEngine version used to generate each task, or the model learns outdated rules.
- **Fairness across households.** Check that accuracy doesn't drop for immigrant, self-employed or multi-generational households, where caseworkers also make the most mistakes.

## Runner-up

**Insurance claim denial appeals:** draft an appeal from a denial letter plus the policy. Very high impact, but there's no deterministic verifier, so it would need a rubric grader, which is easier to game.

## Next step

Scaffold v0: a household generator, one PolicyEngine-backed Harbor task, and the reward script.

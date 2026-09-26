# ttune

Notes and plans for building RL environments (in the [Harbor](https://github.com/laude-institute/harbor) format) and using them to fine-tune / RL a small model of my own, on little compute.

## Current direction

**Public-benefits eligibility.** An agent reads a household's messy documents and determines eligibility and amounts for SNAP, Medicaid, EITC, WIC and similar programs, using [PolicyEngine](https://github.com/PolicyEngine) as an exact, open-source verifier. Full plan: [docs/04-benefits-eligibility-plan.md](docs/04-benefits-eligibility-plan.md).

## Docs

| Doc | What's in it |
|---|---|
| [01 – Niche exploration](docs/01-niche-exploration.md) | Early ideas: why plain terminal tasks were rejected, AI-safety-flavored envs, automated interpretability envs |
| [02 – Realistic environments](docs/02-realistic-environments.md) | 8 realistic, CPU-only environment ideas across different domains |
| [03 – 2026 trends](docs/03-trends-2026.md) | What people on X and in papers are saying about RL environments, and what it means for these ideas |
| [04 – Benefits eligibility plan](docs/04-benefits-eligibility-plan.md) | The chosen domain: environment design, reward, training pipeline, risks |

## Constraints I'm working under

- Little compute: CPU-side verification, small open-weight models (4–8B), LoRA, a single rented GPU or a hosted fine-tuning API.
- Rewards should come from a deterministic verifier where possible, not an LLM judge.
- Environments should be procedurally generated, so one generator yields many tasks.

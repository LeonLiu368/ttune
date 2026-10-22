# ttune

Notes and plans for building RL environments (in the [Harbor](https://github.com/laude-institute/harbor) format) and using them to fine-tune / RL a small model of my own, on little compute.

**What's next:** see [ROADMAP.md](ROADMAP.md) for what's done, in progress and next.

## Current direction

**Public-benefits eligibility.** An agent reads a household's messy documents and determines eligibility and amounts for SNAP, Medicaid, EITC, WIC and similar programs, using [PolicyEngine](https://github.com/PolicyEngine) as an exact, open-source verifier. Full plan: [docs/04-benefits-eligibility-plan.md](docs/04-benefits-eligibility-plan.md).

## Research: where ttune fits

Earlier work shows language models still get benefits and tax rules wrong often, and none of it trains a model to do better. The best model answers about 77% of SNAP questions correctly ([Public Benefits Bench](https://www.vals.ai/benchmarks/public-benefits-bench)). The best gets 78% of full tax returns right, and only with web search ([TaxCalcBench](https://github.com/column-tax/tax-calc-bench)). These benchmarks use small, fixed, hand-written test sets, and each covers one program.

ttune adds what's missing:

| What we plan to hit | Closest earlier work | How ttune does it |
|---|---|---|
| Exact answers from a rules engine | TaxCalcBench, τ-bench | PolicyEngine's answer for every household |
| Generated, unlimited cases | Reasoning Gym, GSM-Symbolic | A seeded household generator ([#2](https://github.com/LeonLiu368/ttune/issues/2)) |
| A planned in- vs out-of-distribution test | GSM-Symbolic | Typical vs unusual households, one kind of shift each ([#4](https://github.com/LeonLiu368/ttune/issues/4)) |
| Wrongful denials cost more than other errors | None found | Counted double in the score ([#5](https://github.com/LeonLiu368/ttune/issues/5)) |
| An RL environment to train on | Reasoning Gym (no benefits programs) | A Harbor environment, then fine-tuning and RL |
| Rules checked against official sources | None found | A monthly scraper and `python -m scraper check` |

**Goals, in order:** build two household sets of 200 with exact answers; measure how much worse a small open model (4–8B) does on the unusual set; find which kind of household causes the drop; package it as an environment that shortcut answers can't game; then train to close the gap without losing ground on typical households.

## Docs

| Doc | What's in it |
|---|---|
| [01 – Niche exploration](docs/01-niche-exploration.md) | Early ideas: why plain terminal tasks were rejected, AI-safety-flavored envs, automated interpretability envs |
| [02 – Realistic environments](docs/02-realistic-environments.md) | 8 realistic, CPU-only environment ideas across different domains |
| [03 – 2026 trends](docs/03-trends-2026.md) | What people on X and in papers are saying about RL environments, and what it means for these ideas |
| [04 – Benefits eligibility plan](docs/04-benefits-eligibility-plan.md) | The chosen domain: environment design, reward, training pipeline, risks |
| [05 – Skills](docs/05-skills.md) | Claude Code skills in `.claude/skills/`: 4 written for ttune, 4 pulled in (3 from Harbor, plus plain-language), plus relevant account skills |
| [06 – Research report](docs/06-research-report.md) | Earlier work on benefits, tax and legal reasoning, verifiable RL environments and robustness; what it did well, where it falls short, ttune's checklist, goals and methods |

## Data

[`data/`](data/README.md) holds raw inputs for the benefits environment: PolicyEngine's rule parameters and about 1,300 example households for SNAP, WIC, EITC and Medicaid. [`data/sources.json`](data/sources.json) lists every source. The official government sources are fetched by [`scraper/`](scraper/), which runs monthly on GitHub Actions and opens a PR with new snapshots; see [data/README.md](data/README.md#scraper). [`data/households/`](data/households/README.md) holds two generated sets of 200 households, typical (ID) and unusual (OOD), each with PolicyEngine's correct answers; [`envgen/`](envgen/) generates them, and [`evals/`](evals/README.md) scores a model on both and compares the results.

## Constraints I'm working under

- Little compute: CPU-side verification, small open-weight models (4–8B), LoRA, a single rented GPU or a hosted fine-tuning API.
- Rewards should come from a deterministic verifier where possible, not an LLM judge.
- Environments should be procedurally generated, so one generator yields many tasks.

# ttune Research Report

Benefits-eligibility RL environments: earlier work, gaps, goals and methods

October 21, 2026 · Leon Liu

## Summary

Language models still get benefits and tax math wrong often, and no earlier work trains them on it with exact answers. The best SNAP benchmark grades about 460 hand-written questions with expert rubrics. The best tax benchmark checks only 50 returns against a tax engine. Neither generates new cases, tests unusual households on purpose, or weighs a wrongful denial more than other errors.

ttune fills that gap. We generate households, get the exact answer for each from PolicyEngine (an open-source rules engine), and compare a model's accuracy on typical households with unusual ones. The first target is a small open model (4–8B). Next we turn the households into an RL training environment and check whether training closes the gap.

## The field today

Work on this problem falls into four areas: benefits and tax benchmarks, legal reasoning, environments that generate checkable tasks, and tests of how models cope with change. The table lists the key work in each area.

| Work | Area | What it tests | How answers are checked | Headline result |
| --- | --- | --- | --- | --- |
| [Public Benefits Bench](https://www.vals.ai/benchmarks/public-benefits-bench) (Vals AI, 2026) | Benefits | 459 SNAP scenarios | Rubrics written by SNAP policy experts | Best model about 77% correct, so about 1 in 4 answers is wrong |
| [SNAP caseworker study](https://arxiv.org/abs/2603.11213) (2026) | Benefits | 770 SNAP questions built from Quality Control error data; 125 caseworkers | Known answers; caseworker accuracy with and without a chatbot | Chatbot suggestions made caseworkers more accurate |
| [Propel SNAP eval](https://www.propel.app/insights/building-a-snap-llm-eval-part-3-testing-nuanced-capabilities/) (2025) | Benefits | A small SNAP test set, by Propel's own account not representative | Automated tests and AI judges | 48% to 80% pass rates across 7 models |
| [TaxCalcBench](https://github.com/column-tax/tax-calc-bench) (Column Tax, 2025; v2 2026) | Tax | Full federal returns (51 cases for 2024); v2 adds state returns (50 cases for 2025) | Compared line by line with a tax engine | 2024: best model under a third of returns right. 2025: best 78% right with web search |
| [Reasoners or Translators?](https://arxiv.org/abs/2605.16052) (2026) | Tax law | Tax-law cases, with rules and facts varied | Known answers, plus a check for leaked test data | Leaked data inflates scores; models that hand logic to a solver hold up better |
| [Language models and logic programs for tax](https://arxiv.org/abs/2508.21051) (2025) | Tax law | SARA tax cases | Model translates the case into Prolog, a logic language that computes the answer | Translation into logic makes answers more trustworthy |
| [LegalBench](https://github.com/HazyResearch/legalbench) (2023) | Legal | 162 legal reasoning tasks from 40 contributors | Known answers per task | Broad coverage; skews toward US law |
| [SARA](https://arxiv.org/abs/2302.06100) (2020) | Tax law | 9 sections of the tax code, 376 hand-written cases | Hand-coded Prolog solves every case | A symbolic program solves it; GPT-3 made clear mistakes |
| [Reasoning Gym](https://github.com/open-thought/reasoning-gym) (2025) | Generated tasks | Over 100 generators: algebra, logic, games and more | Each task has its own automatic checker | Unlimited training data with adjustable difficulty |
| [τ-bench](https://github.com/sierra-research/tau-bench) (Sierra, 2024) | Generated tasks | Agents following a written policy in airline and retail chats | Final database state compared with the goal state | gpt-4o solved 37% of airline tasks once, and only 14% on all 4 tries |
| [Hack-Verifiable Environments](https://github.com/MajoRoth/hack-verifiable-environments) (2026) | Reward hacking | Environments with known shortcuts planted in them | Automatic detection when a model takes a planted shortcut | Reward hacking measured directly instead of found by reading transcripts |
| [SFT memorizes, RL generalizes](https://github.com/LeslieTrue/SFTvsRL) (2025) | Robustness | A card arithmetic game and street navigation, with unseen rule variants | Known answers | Reinforcement learning (RL) carried over to new variants; supervised fine-tuning (SFT) mostly memorized |
| [GSM-Symbolic](https://github.com/apple/ml-gsm-symbolic) (Apple, 2024) | Robustness | Grade-school math from templates, 50 versions of each question | Known answers | Scores drop when only the numbers change, and by up to 65% when one irrelevant sentence is added |

## What earlier papers did well

Six ideas from earlier work are worth copying, and ttune already uses or plans to use each one.

- **Check answers with a rules engine, not a judge.** TaxCalcBench compares each return with a tax engine, and τ-bench checks the final database state rather than the chat text. Both give an exact score no one can argue with. ttune uses PolicyEngine the same way.
- **Build cases from real mistakes.** The caseworker study drew its 770 questions from SNAP Quality Control error data, so the test targets errors that actually happen. Public Benefits Bench had SNAP policy experts write its rubrics. ttune's out-of-distribution twists follow the same idea.
- **Generate tasks instead of writing them by hand.** Reasoning Gym and GSM-Symbolic make many versions of each task from a template, with a dial for difficulty. That gives unlimited fresh data and makes memorizing answers useless.
- **Measure the drop under change, not just the score.** GSM-Symbolic showed that changing only the numbers lowers scores. "SFT memorizes, RL generalizes" tested models on rule variants they never trained on. That drop is the number ttune cares about most.
- **Reward consistency.** τ-bench's pass^k counts a task as solved only if the model gets it right on all k tries. A screener that is right only sometimes is not safe to use.
- **Plant shortcuts to catch reward hacking.** Hack-Verifiable Environments hides known shortcuts in the environment and detects when a model takes one. ttune's reward-hack audit takes the same stance: it tries known shortcuts, such as answering "eligible" every time, and requires them to score low.

## Where earlier work falls short

The biggest gap: no earlier benefits work generates cases, trains a model, or tests on purpose how it handles unusual households. The table pairs each gap with what ttune does about it.

| Gap | Where we saw it | What ttune does |
| --- | --- | --- |
| Small, fixed test sets that leak into training data over time | TaxCalcBench (50–51 cases), SARA (376), Propel; leaked data inflated tax-law scores in Reasoners or Translators? | Generates fresh households from a seed, so a new test set costs nothing and can't have leaked |
| Answers graded by rubrics or AI judges | Public Benefits Bench, Propel | Exact numbers from PolicyEngine for every household |
| Built only to test, not to train | Every benefits benchmark above | A Harbor RL environment, then supervised fine-tuning and RL on a small model |
| One program at a time | The SNAP benchmarks | SNAP, EITC, WIC and Medicaid for the same household |
| No planned out-of-distribution test | The benefits and tax benchmarks (only the robustness papers test planned shifts) | Two sets: typical households and unusual ones, with one kind of shift per household so a drop has one cause |
| Every error counts the same | The benefits and tax benchmarks, as far as their public write-ups show | A wrongful "not eligible" costs double, because that error can leave a family without food or health care |
| Rules go stale each year | Fixed answer keys in every benchmark | Versioned rules, a monthly scraper, and a check against official sources. It already found that Medicaid.gov's eligibility file is 2018 data, and 21 real differences in SNAP utility allowances |
| Reward hacking left unchecked | Every benefits benchmark above | An audit before any training: shortcut answers must score low |

## Checklist: what ttune plans to hit

ttune aims to hit all 11 items below; no earlier work fully hits more than 3. "Not stated" means the public write-up doesn't say. Update the Status column as work lands.

| What we plan to hit | Public Benefits Bench | TaxCalcBench | τ-bench | Reasoning Gym | GSM-Symbolic | ttune status | Tracked in |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Exact answers from a rules engine | No (expert rubrics) | Yes | Yes | Yes | Yes | In progress | [#3](https://github.com/LeonLiu368/ttune/issues/3) |
| Benefits programs covered | SNAP | EITC, inside full tax returns | No | No | No | In progress | [#3](https://github.com/LeonLiu368/ttune/issues/3): SNAP, EITC, WIC, Medicaid |
| Generated, unlimited cases | No | No | No | Yes | Yes | Planned | [#2](https://github.com/LeonLiu368/ttune/issues/2) |
| Planned in- vs out-of-distribution test | No | No | No | Partly (difficulty dial) | Yes | Planned | [#4](https://github.com/LeonLiu368/ttune/issues/4) |
| Incomes right at a program cutoff | Not stated | Not stated | No | No | No | Planned | [#4](https://github.com/LeonLiu368/ttune/issues/4) |
| Wrongful denials cost more than other errors | Not stated | No | No | No | No | Planned | [#5](https://github.com/LeonLiu368/ttune/issues/5) |
| Consistency over repeated tries (pass^k) | Not stated | No | Yes | No | No | Planned | [#5](https://github.com/LeonLiu368/ttune/issues/5) |
| An RL environment to train on | No | No | No | Yes | No | Planned | Roadmap stage 3: Harbor task |
| Rules checked against official sources | Not stated | Not stated | No | No | No | Done | `python -m scraper check` |
| Reward-hack audit before training | Not stated | Not stated | No | Not stated | No | Planned | `reward-hack-audit` skill |
| Realistic, messy documents as input | No | Partly (PDF tax forms) | No | No | No | Later | Roadmap stage 3: document renderer |

Reasoning Gym comes closest, with an automatic checker, generated cases and an RL setup, but it covers no benefits programs. TaxCalcBench is the closest in subject. None of the five says it weighs wrongful denials more or audits for reward hacking.

## Our goals

We have five goals, in order; each ends in a result we can check. Number targets for training wait until the baseline exists, because a target set before that would be a guess.

1. **Two household sets with exact answers.** 200 typical households and 200 unusual ones, each with PolicyEngine's answer for SNAP, EITC, WIC and Medicaid. Done when both sets generate with no engine errors, and every program has both eligible and ineligible cases in each set.
2. **A measured gap.** How much worse a small open model (4–8B) does on the unusual set than on the typical one. Done when we have, per program and per set: eligibility accuracy, wrongful-denial rate, amounts within ±5% or ±$10, and pass^k.
3. **A gap with known causes.** Which kind of unusual household causes the drop: rare household shapes, incomes near a cutoff, or states the model never saw. Done when the out-of-distribution results are broken down by those three groups.
4. **An environment that can't be gamed.** The household sets packaged as a Harbor RL environment. Done when shortcut answers ("eligible" every time, "unknown" every time, random amounts) score far below a correct solution.
5. **Training that closes part of the gap.** Supervised fine-tuning, then RL, on the small model. Done when the unusual-set scores and the wrongful-denial rate improve with no loss on the typical set. The size of the improvement we aim for is set after goal 2.

## Methods

Each goal has a method borrowed from earlier work. The rows follow build order, and goals 1–3 are open GitHub issues.

| Goal | Method | Borrowed from | Tracked in |
| --- | --- | --- | --- |
| 1. Household sets | Generate each household from a seed, so the same seed always gives the same household. Run each one through PolicyEngine for the exact answer. Typical households: 1–5 people, working-age adults on wages, in a fixed list of states. | Reasoning Gym and GSM-Symbolic (generate from templates); TaxCalcBench (check with a rules engine) | [#2](https://github.com/LeonLiu368/ttune/issues/2), [#3](https://github.com/LeonLiu368/ttune/issues/3) |
| 3. Known causes | Give each unusual household exactly one kind of shift, split evenly across the set: rare shapes (a 65+ member, gig income, 8–12 people, mixed citizenship), income within 1% of a real cutoff, or a state the typical set never uses (incl. Alaska, New York, Hawaii). | GSM-Symbolic (change one thing at a time); the caseworker study (target real error patterns) | [#4](https://github.com/LeonLiu368/ttune/issues/4) |
| 2. Measured gap | Show the model a plain-text case summary and ask for a set answer format. Score eligibility, wrongful denials (counted double), amounts and pass^k. Count a broken answer as wrong, never skip it. Run on OpenRouter through GitHub Actions. | τ-bench (pass^k); ttune's own reward design | [#5](https://github.com/LeonLiu368/ttune/issues/5), [#6](https://github.com/LeonLiu368/ttune/issues/6) |
| 4. Can't be gamed | Keep the answer key out of the agent's container. Before training, check that shortcut answers score low. | Hack-Verifiable Environments | `reward-hack-audit` skill; roadmap stage 3 |
| 5. Training | Supervised fine-tuning first, to fix the answer format; then RL against PolicyEngine's answers, with the typical set as a check against losing ground. | "SFT memorizes, RL generalizes" (SFT steadies the format, RL carries over to new variants) | `rl-train` skill; roadmap stage 4 |

The data work under all of this is done. The scraper pulls official rules monthly, and `check` compares them with PolicyEngine. That check already caught a stale Medicaid file, so the rules the generator uses are checked, not assumed.

## Sources and coverage

This is a best-effort survey of 13 works, not a complete one. It followed Exa Agent's research method: a set scope, a coverage check, and evidence for each claim. It used ordinary web search, because the Exa Deep Research plugin isn't enabled yet. From the research environment only GitHub pages would open, so about half of the figures come from search summaries and should be checked against the papers.

| Source | How it was checked |
| --- | --- |
| [TaxCalcBench repo](https://github.com/column-tax/tax-calc-bench) | Opened: 2025 edition, 50 cases, leaderboard. The 2024 "under a third" result is from a search summary of the [paper](https://arxiv.org/abs/2507.16126) |
| [τ-bench repo](https://github.com/sierra-research/tau-bench) | Opened: airline pass^k results for gpt-4o |
| [Reasoning Gym repo](https://github.com/open-thought/reasoning-gym) | Opened: over 100 tasks, automatic checkers |
| [LegalBench repo](https://github.com/HazyResearch/legalbench) | Opened: 162 tasks, 40 contributors |
| [Hack-Verifiable Environments repo](https://github.com/MajoRoth/hack-verifiable-environments) | Opened: method and released environments |
| [GSM-Symbolic repo](https://github.com/apple/ml-gsm-symbolic) | Opened: templates, 50 versions per question. The "up to 65%" drop is from a search summary of the [paper](https://arxiv.org/abs/2410.05229) |
| [SFT vs RL repo](https://github.com/LeslieTrue/SFTvsRL) | Opened: test environments. The findings are from a search summary of the [paper](https://arxiv.org/abs/2501.17161) |
| [Public Benefits Bench](https://www.vals.ai/benchmarks/public-benefits-bench) | Search summary only (459 scenarios, about 77% top score) |
| [SNAP caseworker study](https://arxiv.org/abs/2603.11213) | Search summary only (770 questions, 125 caseworkers) |
| [Propel SNAP eval, part 3](https://www.propel.app/insights/building-a-snap-llm-eval-part-3-testing-nuanced-capabilities/) | Search summary only (48–80% pass rates) |
| [Reasoners or Translators?](https://arxiv.org/abs/2605.16052) | Search summary only |
| [Language models and logic programs for tax](https://arxiv.org/abs/2508.21051) | Search summary only |
| [Can GPT-3 perform statutory reasoning?](https://arxiv.org/abs/2302.06100) (SARA) | Search summary only (9 code sections, 376 cases) |

Gaps: no published model evaluation was found for Medicaid or WIC eligibility. Before citing this report outside the project, re-run the search with Exa Deep Research and open each paper.

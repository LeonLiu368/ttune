# Roadmap

What's done, in progress and next for the benefits-eligibility environment. Update this file whenever something changes state.

## 1. Get the data

- [x] PolicyEngine rules and ~1,300 example households (`data/raw/policyengine-us`)
- [x] Scraper: fetch, dated snapshots, monthly GitHub Actions run, `import` for hand downloads
- [x] Merge [PR #1](https://github.com/LeonLiu368/ttune/pull/1): SNAP utility allowances, EITC Rev. Proc., Medicaid levels, W-2 template
- [x] HHS poverty guidelines, 2026: from HHS's Federal Register notice, which GitHub's runners can reach (aspe.hhs.gov blocks them)
- [x] SNAP FY27 COLA tables: the four FY27 PDFs on fna.usda.gov's COLA page (www.usda.gov blocks the scraper)
- [x] Document templates: W-2, 1099-NEC, 1099-G, Schedule EIC, HUD-90105a model lease. Pay stubs and benefit notices have no public-domain template, so the document renderer will draw its own
- [x] A current Medicaid source: Medicaid.gov's eligibility-levels table, as of December 1, 2023

## 2. Parse and verify

- [x] Extract framework: one shared row format, `python -m scraper extract`
- [x] Parser: Medicaid/CHIP eligibility levels (476 rows, 50 states + DC)
- [x] Parser: SNAP standard utility allowances FY26 (935 rows; 762 of the comparable values match PolicyEngine exactly)
- [x] Parser: EITC from Rev. Proc. 2025-32 (25 rows; every value PolicyEngine stores directly matches)
- [x] Parser: HHS poverty guidelines 2026 (30 rows; all match PolicyEngine)
- [x] Parser: SNAP FY27 COLA tables (186 rows: max allotments, deductions, asset and income limits; 158 match, 1 differs)
- [x] Parser: current Medicaid/CHIP eligibility levels (441 rows; 271 match PolicyEngine as of the table's date)
- [x] `check` command: every parsed value vs PolicyEngine, in `data/processed/checks/`; runs in the monthly workflow

## 3. Build the environment

- [ ] Household sets and evals, tracked as issues:
  - [x] [#2](https://github.com/LeonLiu368/ttune/issues/2) Household schema, in-distribution sampler and case text
  - [x] [#3](https://github.com/LeonLiu368/ttune/issues/3) PolicyEngine ground truth and `python -m envgen generate` (ID set of 200)
  - [x] [#4](https://github.com/LeonLiu368/ttune/issues/4) Out-of-distribution set of 200: rare shapes, threshold edges, held-out states ([data/households](data/households/README.md))
  - [x] [#5](https://github.com/LeonLiu368/ttune/issues/5) Eval harness: scoring, OpenRouter client, run and compare ([evals/](evals/README.md); tested against a local mock server)
  - [x] [#6](https://github.com/LeonLiu368/ttune/issues/6) Eval workflows and first ID vs OOD results: Qwen3 4B Instruct, self-hosted on GitHub's runners for $0 ([results](evals/results/20261026-0340-local-qwen3-4b-instruct/comparison.md); findings below)
- [ ] Messy document renderer
- [ ] First Harbor task and reward (`benefits-task` skill)
- [ ] Reward-hack audit (`reward-hack-audit` skill)
- [ ] Generated task set with train / holdout splits

## 4. Train

- [ ] Baseline eval
- [ ] SFT warm-start
- [ ] GRPO
- [ ] Publish to Harbor Hub

## Findings so far

From `python -m scraper check` (full list in [`data/processed/checks/summary.md`](data/processed/checks/summary.md)):

| Source | Match | Differ | Not in PolicyEngine | No official value |
|---|---|---|---|---|
| HHS poverty guidelines 2026 | 30 | 0 | 0 | 0 |
| SNAP FY27 COLA tables | 158 | 1 | 27 | 0 |
| EITC, Rev. Proc. 2025-32 | 25 | 0 | 0 | 0 |
| SNAP utility allowances FY26 | 762 | 21 | 109 | 8 |
| Medicaid/CHIP levels, Medicaid.gov table (Dec 2023) | 271 | 35 | 102 | 0 |
| Medicaid/CHIP levels, 2018 CSV (superseded) | 235 | 71 | 102 | 0 |

- **Poverty guidelines and EITC:** everything matches, including the 12 EITC amounts PolicyEngine computes from rates instead of storing.
- **SNAP FY27 COLA:** max allotments, standard deductions, asset limits and the net and gross income limits all match (the income limits are derived: rate × poverty guideline ÷ 12, rounded up). The one difference is Hawaii's excess shelter cap: FNS's table says $1,306, PolicyEngine has $1,036. PolicyEngine's Hawaii series rises smoothly ($959, $1,003, $1,036), so FNS's table may have swapped two digits. Check FNS's AK/HI/GU/VI memo before trusting either. The 27 "not in PolicyEngine" are the 165% limit for elderly/disabled members who buy food separately.
- **SNAP utility allowances:** the 21 differences are real. Maryland's allowances run on the calendar year (the FNS table footnotes this); North Carolina is given in cents; Wisconsin ($870 vs $553) and New York's basic allowances look out of date in PolicyEngine. Louisiana's basic allowance ($0 officially vs $258) and Maine's phone allowance need a closer look: a $0 may mean the state doesn't offer it. The 109 "not in PolicyEngine" are mostly the SMD offset column.
- **Medicaid (Medicaid.gov table):** compared with PolicyEngine as of the table's date, December 1, 2023. Of the 35 differences, 26 are parent/caretaker limits in states that set dollar amounts by household size; CMS converts those to a % of the poverty line, so small gaps are expected, except North Carolina (36% vs 138%), which expanded Medicaid on that same date. The other 9 need a look: Minnesota and New York show 200% for adults (that includes their Basic Health Program; PolicyEngine's 138% is Medicaid alone); Tennessee children; Rhode Island pregnant women; Missouri children (153% vs 155%); Wisconsin adults ("No/95%", a waiver). CHIP limits aren't in the downloaded PolicyEngine files.
- **Medicaid (2018 CSV):** stale; kept only for the record. Idaho shows no expansion, which it adopted in 2020.

### Eval smoke runs (free models, $0)

| Model | What happened | What changed |
|---|---|---|
| `google/gemma-4-26b-a4b-it:free` | All 20 requests: "temporarily rate-limited upstream" | Runs now stop after the first 3 cases fail |
| `thinkingmachines/inkling-small:free` | 403: only answers "agentic harnesses" | Dropped from the free list |
| `liquid/lfm-2.5-2.6b:free`, 3,000 tokens | All 20 replies cut off while reasoning | Cut-off replies counted separately; `max_tokens` (default 8,000) and `reasoning_effort` inputs |
| `liquid/lfm-2.5-2.6b:free`, 8,000 tokens, low effort | Answers, but writes its reasoning as a made-up `think(...)` tool call and stops without JSON. 1 of 20 parsed, and it scored 0 (false denials) | Nothing: the harness parsed and scored correctly; the model can't follow the format |

The harness works end to end against a real model. None of the free 2–8B models that answer plain API calls could follow the answer format, so evals now serve an open model ourselves: the **Eval (self-hosted model)** workflow runs llama.cpp on GitHub's runner CPUs, so no tokens are bought.

### First ID vs OOD eval: Qwen3 4B Instruct, self-hosted ($0)

All 200 + 200 households, Q4_K_M weights on CPU, temperature 0, 6,000-token cap. Full tables in [comparison.md](evals/results/20261026-0340-local-qwen3-4b-instruct/comparison.md). Every case got an answer; 16 of 400 replies were malformed, 17 cut off at the token limit counted among them. 20 parallel jobs took 1.5–3.5 hours each, about 40 runner-hours, free on a public repo.

| | ID | OOD | Change (95% interval) |
|---|---|---|---|
| Mean reward | 0.44 | 0.35 | −0.10 (−0.17 to −0.02) |
| Floor: always "no" | 0.35 | 0.22 | |
| Floor: always "yes", $0 | 0.26 | 0.32 | |

| Program | Balanced accuracy, ID → OOD | False denials, ID → OOD |
|---|---|---|
| SNAP | 63% → 60% | 42% → 54% |
| EITC | 62% → 61% | 54% → 53% |
| Medicaid | 63% → 62% | 29% → 43% |
| WIC | 69% → 67% | 33% → 60% |

- **Barely above the floors.** Mean reward is 0.44 on ID, where always answering "no" already scores 0.35. On OOD it's 0.35, and always answering "yes" scores 0.32. Balanced accuracy is 60–69%, against 50% for any blanket answer.
- **Part of the reward drop is the base rate.** The OOD set has more eligible households, which moves the floors too. Balanced accuracy barely changes from ID to OOD for any program (−0 to −4 points, every interval includes 0). The model is about equally weak on both sets.
- **The clear OOD shift is false denials,** the harmful direction. Unusual households get told "not eligible" more often when they qualify: SNAP +12 points, Medicaid +14, WIC +26.
- **Threshold edge cases are the hardest family:** reward 0.28. Balanced accuracy is 54% for SNAP and 47% for EITC, so the model can't tell which side of a cutoff a household is on.
- **Held-out states don't hurt:** reward 0.43, and balanced accuracy at or above ID's. The gap comes from household shapes and cutoffs, not from unfamiliar states.
- **Amounts are almost never right:** 0–2% of SNAP and EITC amounts are within 5% or $10. The model reasons from remembered thresholds (often wrong or out of date) instead of computing.
- Twists have only 10 to 23 households each, so treat their rows in comparison.md as hints. The college-student and `edge_snap` households look worst for SNAP: 39% and 34% balanced accuracy, below what a blanket answer gets.

What this means for training: the model needs exact rules and arithmetic, and the reward should focus on false denials for unusual households. The next steps on this roadmap (the document renderer, Harbor tasks, then SFT and GRPO) aim at exactly that.

## Known blockers

| Source | Problem | Workaround |
|---|---|---|
| aspe.hhs.gov (poverty guidelines) | Returns 403 to GitHub's runners | Use HHS's Federal Register notice instead; point it at the new notice each January |
| www.usda.gov (COLA guidance page) | Returns 403 to the scraper everywhere | Use the PDFs on fna.usda.gov's COLA page instead |
| ssa.gov (SSA-1099 form) | Returns 403 to GitHub's runners | Not fetched; Social Security income is described in the case text for now |

The scraper doesn't spoof a browser to get past these. If a site blocks it, the source is fetched by hand.

## Housekeeping

- Fetch FNS's FY2027 standard utility allowance table when it's published (ttune has FY2026; the household answers use PolicyEngine's FY2027 allowances).
- Model SSI: let a case say a member receives SSI without conflicting with PolicyEngine's own SSI calculation.
- Refresh `data/raw/policyengine-us` (commit from 2026-09-29) to match the installed policyengine-us 2.50.1, so `check` and the household answers use the same rules.

- Bump `actions/checkout`, `actions/setup-python` and `peter-evans/create-pull-request` off Node 20 (read their changelogs first).
- Test the ttune skills in `.claude/skills/` with skill-creator once the first Harbor task exists.

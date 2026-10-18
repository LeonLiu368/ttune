# Roadmap

What's done, in progress and next for the benefits-eligibility environment. Update this file whenever something changes state.

## 1. Get the data

- [x] PolicyEngine rules and ~1,300 example households (`data/raw/policyengine-us`)
- [x] Scraper: fetch, dated snapshots, monthly GitHub Actions run, `import` for hand downloads
- [x] Merge [PR #1](https://github.com/LeonLiu368/ttune/pull/1): SNAP utility allowances, EITC Rev. Proc., Medicaid levels, W-2 template
- [ ] HHS poverty guidelines: `python -m scraper fetch --source hhs-poverty-guidelines` from a home connection, then commit
- [ ] SNAP FY27 COLA memo: download in a browser, `python -m scraper import fns-snap-cola-fy27 <files> --url <pdf link>`, then commit
- [ ] Document templates: public-domain pay stubs, leases, benefit notices (`kind: ["templates"]`)
- [ ] A current Medicaid eligibility source (the Medicaid.gov CSV is April 2018 data; see Findings)

## 2. Parse and verify

- [x] Extract framework: one shared row format, `python -m scraper extract`
- [x] Parser: Medicaid/CHIP eligibility levels (476 rows, 50 states + DC)
- [x] Parser: SNAP standard utility allowances FY26 (935 rows; 762 of the comparable values match PolicyEngine exactly)
- [x] Parser: EITC from Rev. Proc. 2025-32 (25 rows; every value PolicyEngine stores directly matches)
- [ ] Parser: HHS poverty guidelines (needs the fetched page)
- [ ] Parser: SNAP FY27 COLA memo (needs the imported PDF)
- [x] `check` command: every parsed value vs PolicyEngine, in `data/processed/checks/`; runs in the monthly workflow

## 3. Build the environment

- [ ] Household generator, seeded by PolicyEngine's example households
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
| EITC, Rev. Proc. 2025-32 | 25 | 0 | 0 | 0 |
| SNAP utility allowances FY26 | 762 | 21 | 109 | 8 |
| Medicaid/CHIP eligibility levels | 235 | 71 | 102 | 0 |

- **EITC:** everything matches, including the 12 amounts PolicyEngine computes from rates instead of storing.
- **SNAP utility allowances:** the 21 differences are real. Maryland's allowances run on the calendar year (the FNS table footnotes this); North Carolina is given in cents; Wisconsin ($870 vs $553) and New York's basic allowances look out of date in PolicyEngine. Louisiana's basic allowance ($0 officially vs $258) and Maine's phone allowance need a closer look: a $0 may mean the state doesn't offer it. The 109 "not in PolicyEngine" are mostly the SMD offset column.
- **Medicaid:** the Medicaid.gov CSV is stale. It has no date, and against PolicyEngine as of April 2018 it matches 294 values instead of 235 (PolicyEngine cites it as April 2018 data). Idaho shows no expansion, which it adopted in 2020. It needs replacing with a current source before the generator uses Medicaid rules. CHIP limits aren't in the downloaded PolicyEngine files.

## Known blockers

| Source | Problem | Workaround |
|---|---|---|
| `hhs-poverty-guidelines` | aspe.hhs.gov returns 403 to GitHub's runners; works from a home connection | `where: local`, so CI skips it; fetch by hand |
| `fns-snap-cola-fy27` | www.usda.gov returns 403 to the scraper from GitHub and from a home connection | `where: manual`; download in a browser, then `import` |
| `medicaid-eligibility-levels` | The CSV is April 2018 data with no date on it | Don't use it for current rules; find a current source |

The scraper doesn't spoof a browser to get past these. If a site blocks it, the source is fetched by hand.

## Housekeeping

- Bump `actions/checkout`, `actions/setup-python` and `peter-evans/create-pull-request` off Node 20 (read their changelogs first).
- Test the ttune skills in `.claude/skills/` with skill-creator once the first Harbor task exists.

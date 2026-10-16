# Roadmap

What's done, in progress and next for the benefits-eligibility environment. Update this file whenever something changes state.

## 1. Get the data

- [x] PolicyEngine rules and ~1,300 example households (`data/raw/policyengine-us`)
- [x] Scraper: fetch, dated snapshots, monthly GitHub Actions run, `import` for hand downloads
- [ ] Merge [PR #1](https://github.com/LeonLiu368/ttune/pull/1): SNAP utility allowances, EITC Rev. Proc., Medicaid levels, W-2 template
- [ ] HHS poverty guidelines: `python -m scraper fetch --source hhs-poverty-guidelines` from a home connection, then commit
- [ ] SNAP FY27 COLA memo: download in a browser, `python -m scraper import fns-snap-cola-fy27 <files> --url <pdf link>`, then commit
- [ ] Document templates: public-domain pay stubs, leases, benefit notices (`kind: ["templates"]`)

## 2. Parse and verify

- [x] Extract framework: one shared row format, `python -m scraper extract`
- [x] Parser: Medicaid/CHIP eligibility levels (476 rows, 50 states + DC)
- [x] Parser: SNAP standard utility allowances FY26 (935 rows; 762 of the comparable values match PolicyEngine exactly)
- [x] Parser: EITC from Rev. Proc. 2025-32 (25 rows; every value PolicyEngine stores directly matches)
- [ ] Parser: HHS poverty guidelines (needs the fetched page)
- [ ] Parser: SNAP FY27 COLA memo (needs the imported PDF)
- [ ] `check` command: compare parsed values with PolicyEngine and report differences

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

A first hand comparison of the FY26 utility allowances with PolicyEngine found 21 differences. They're for `check` to report properly, not parser bugs:

- **Maryland:** its allowances run on the calendar year (the FNS table footnotes this), so PolicyEngine's October value differs.
- **North Carolina:** FNS gives cents ($636.74, $42.11); PolicyEngine has whole dollars.
- **Wisconsin:** heating/cooling $870 vs $553 and basic $436 vs $385, so PolicyEngine looks out of date.
- **New York, Louisiana, Maine:** basic allowance or phone amounts differ; Maine's phone allowance is folded into its medical deduction offset.

Medicaid.gov's CSV leaves out the 5-point income disregard that PolicyEngine includes (133% vs 1.38), so `check` must add it before comparing.

## Known blockers

| Source | Problem | Workaround |
|---|---|---|
| `hhs-poverty-guidelines` | aspe.hhs.gov returns 403 to GitHub's runners; works from a home connection | `where: local`, so CI skips it; fetch by hand |
| `fns-snap-cola-fy27` | www.usda.gov returns 403 to the scraper from GitHub and from a home connection | `where: manual`; download in a browser, then `import` |
| `medicaid-eligibility-levels` | The CSV has no "as of" date | Check freshness against the dataset page on data.medicaid.gov before relying on it |

The scraper doesn't spoof a browser to get past these. If a site blocks it, the source is fetched by hand.

## Housekeeping

- Bump `actions/checkout`, `actions/setup-python` and `peter-evans/create-pull-request` off Node 20 (read their changelogs first).
- Test the ttune skills in `.claude/skills/` with skill-creator once the first Harbor task exists.

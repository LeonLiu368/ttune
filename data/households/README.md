# Household sets

Two sets of 200 synthetic households, each with the correct SNAP, EITC, WIC and Medicaid answers from PolicyEngine. The **in-distribution (ID)** set holds typical households. The **out-of-distribution (OOD)** set holds households that differ from the ID set in one planned way each. Running the same model on both shows how much worse it does on unusual cases, and which kind of case causes the drop.

| Set | Folder | Households | What's in it |
|---|---|---|---|
| ID | [`id/`](id/) | 200 | Typical households in 41 states |
| OOD | [`ood/`](ood/) | 200 | Three shift families, about 67 households each |

Each folder has `households.jsonl` (one household per line) and `manifest.json` (seed, PolicyEngine version, periods, and counts by state, size, shift, twist and eligibility).

## Regenerate

```bash
pip install -r requirements-envgen.txt
python -m envgen generate --set id --n 200 --seed 1
python -m envgen generate --set ood --n 200 --seed 1
```

The same seed and PolicyEngine version always give byte-identical files. The command prints a balance report and fails if any program comes out all-eligible or all-ineligible, since a set like that can't measure the program. The ID set takes about a minute. The OOD set takes about 7 minutes, mostly spent searching for the threshold cutoffs.

## One line of `households.jsonl`

```json
{"id": "ood-1-0001", "case": "Case ood-1-0001\nLives in: California\n...", "household": {...}, "truth": {...}}
```

- **`case`**: the plain-text case summary a model reads. It lists every member, every income and every expense, and nothing about eligibility. There are no messy documents yet, so the eval measures eligibility reasoning, not document reading.
- **`household`**: the same facts as data (`envgen/household.py`):
  - `state` and, in Alaska and New York, `county` and `area` (SNAP utility allowances vary within those states).
  - `members`: `name`, `age`, `relationship` (`head`, `spouse`, `child`, or `parent` of the head), `pregnant`, `disabled`, `student` (full-time college), `citizenship` (`citizen` or `undocumented`), and `income` by type, in whole dollars a month: `wages`, `self_employment`, `social_security`, `child_support`, and so on.
  - `expenses`, all monthly: `rent`, `heating_cooling` (paid separately from rent or not), `childcare`, and `medical` costs by member (only for members 60 or older or disabled).
  - `shift`, `twists` and, for threshold cases, `edge`: see below.
- **`truth`**: PolicyEngine's answers:
  - `snap`: `eligible` and `monthly_benefit`, for October 2026 (FY2027 rules).
  - `eitc`: `eligible` and `annual_amount`, for tax year 2026.
  - `wic`: `eligible_members` and the household's `monthly_value`, for October 2026.
  - `medicaid` and `chip`: `eligible_members`, for 2026.

## How the two sets differ

**ID households** have 1 to 5 people in one of four common shapes: a single adult, a couple, a single parent, or two parents. Adults are 18 to 64 and work for wages. Total wages fall between 50% and 250% of the 2026 poverty line for the household's size (from [`data/processed/hhs-poverty-guidelines.csv`](../processed/hhs-poverty-guidelines.csv)). Some single parents receive child support. ID states are all states except the 10 held out below.

**OOD households** each get exactly one shift family, assigned in turn (index 0, 3, 6, ... are rare shapes, and so on):

1. **Rare household shapes** (67, in ID states). One or two of these twists, cycled so every twist appears:
   - `multigenerational`: one or two grandparents, 65 or older, on Social Security
   - `self_employment`: the head is self-employed (gig work) instead of earning wages
   - `disabled_member`: someone has a disability; a disabled adult usually draws Social Security disability instead of wages
   - `college_student`: a full-time college student aged 18 to 22 lives with their parents
   - `large_household`: two parents and 6 to 10 children (8 to 12 people)
   - `pregnant_member`: a pregnant adult, 44 or younger
   - `mixed_citizenship`: one adult is undocumented; everyone else is a citizen
2. **Threshold edge cases** (67, typical shapes in ID states). Wages sit 0.3% to 1% above or below a real cutoff, on a random side. One third each:
   - `edge_snap`: where the SNAP benefit drops to $0. In most states that is the 130% gross income limit. In states with broad-based categorical eligibility it is the state's higher limit (California's is 200%) or the point where the benefit runs out.
   - `edge_eitc`: where the EITC is fully phased out.
   - `edge_medicaid`: where the head (or, if the head can't qualify at any income, the youngest child who can) loses Medicaid.

   The cutoff isn't hard-coded. `envgen/edges.py` finds it by raising the household's wages in PolicyEngine until the answer flips, so it includes every state rule. `edge` records `program`, `side`, `cutoff_monthly_wages` (the first total that gets "no"), `monthly_wages`, `actual_offset` and, for Medicaid, the `target` member.
3. **Held-out states** (66, typical shapes): AK, HI, NY, DC, ME, MS, ND, NM, OR and VT, which the ID set never uses. Alaska and New York have sub-state SNAP regions, so their households also have a county. Alaska and Hawaii have their own poverty guidelines.

## How the answers are computed

`envgen/truth.py` builds one PolicyEngine situation for many households at once and reads off the answers. Incomes and expenses are entered for calendar 2026 as 12 times the monthly amount. Some choices keep the answers tied to what the case text says:

- **Everyone in the household buys and prepares food together**, so there is one SNAP unit. The head files taxes with their spouse and children (under 19, or students under 24). Grandparents file separately.
- **Only income the case lists counts.** PolicyEngine can work out benefits a household might also get (SSI, state SSI supplements, Colorado's Old Age Pension, TANF cash). Those are set to $0, and every run checks that the SNAP income PolicyEngine counts equals the income the case declares.
- **No assets.** The case says no one has savings, which matches PolicyEngine's default of $0.
- **Eligibility, not enrollment.** Medicaid, CHIP and WIC record who qualifies. SNAP and the EITC assume the household applies.

## Spot checks

Five ID households, worked by hand from the official FNS FY2027 tables and IRS Rev. Proc. 2025-32, then compared with PolicyEngine:

| Household | State, size | SNAP by hand | PolicyEngine | EITC by hand | PolicyEngine |
|---|---|---|---|---|---|
| `id-1-0001` | NC, 3 | $66 | $66 | $3,855.86 | $3,855.84 |
| `id-1-0004` | CT, 2 | $333 | $333 | $4,427.00 | $4,427.00 |
| `id-1-0008` | ID, 5 | $847 | $847 | $5,091.83 | $5,091.80 |
| `id-1-0009` | CA, 4 | $521 | $521 | $6,829.94 | $6,829.94 |
| `id-1-0019` | LA, 1 | $55 | $55 | $67.32 | $67.30 |

- **SNAP by hand:** gross income − 20% of earnings − the standard deduction − childcare = adjusted income. The shelter deduction is rent plus the utility allowance, minus half of adjusted income, capped at $769. Then net income = adjusted income − shelter deduction, and benefit = max allotment − 30% of net income, rounded up. The max allotment, standard deduction and shelter cap come from FNS's FY2027 tables. The utility allowance comes from PolicyEngine, because ttune only has FNS's FY2026 allowance table so far.
- **`id-1-0001` earns more than SNAP's 130% gross limit** ($3,360 vs $2,960 for 3 people) and still gets $66. North Carolina uses broad-based categorical eligibility, which raises the limit to 200%.
- **EITC by hand:** the credit rises with earnings up to the maximum, then falls between the phase-out amounts in the Rev. Proc. table. The few cents of difference come from the IRS rounding its table amounts.

## Limits

- No sampler gives anyone SSI yet. PolicyEngine computes SSI from its own rules, so an SSI amount in the case text would conflict with what PolicyEngine works out.
- There are no messy documents yet (pay stubs, leases, letters). That's the next stage on the [roadmap](../../ROADMAP.md).
- The answers are only as right as PolicyEngine 2.50.1. Known differences from official sources are in [`data/processed/checks/summary.md`](../processed/checks/summary.md).

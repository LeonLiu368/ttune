# data

Raw data for the benefits-eligibility environment ([docs/04](../docs/04-benefits-eligibility-plan.md)). This first batch was fetched by hand; a scraper will take over later, using [`sources.json`](sources.json) as its target list.

## Layout

```
data/
├── README.md
├── sources.json          # every source: URL, license, status, retrieval date, commit
└── raw/                  # unmodified copies, one folder per source
    └── policyengine-us/
        ├── LICENSE       # AGPL-3.0
        ├── parameters/   # the rules
        └── tests/        # example households with known correct answers
```

Nothing in `raw/` is edited by hand. Cleaned or derived data goes in a separate `data/processed/` folder once there is some.

## What's here so far

All from [PolicyEngine US](https://github.com/PolicyEngine/policyengine-us), the same engine the environment uses as its verifier, at commit `79be99f` (retrieved 2026-09-29).

| Program | Rule parameters | Example test cases |
|---|---|---|
| Federal poverty guidelines | `parameters/gov/hhs/fpg.yaml` (1992–2026) | n/a |
| SNAP | 98 files: max allotments, income limits, deductions, asset tests, utility allowances, work requirements | 80 files |
| WIC | 7 files | 12 files |
| EITC | 11 files | 14 files |
| Medicaid eligibility | 54 files: income limits and categories by state | 28 files |

Across the four programs there are about 1,300 test cases in total.

**Why these two kinds of data:**
- **Parameters** are the actual thresholds and amounts, with `reference` links back to the official source (USDA, IRS, HHS, CMS). Useful for writing task instructions, checking the generator's ranges, and cross-checking the official sources once the scraper can reach them.
- **Tests** are small household scenarios with the correct output, written by PolicyEngine's maintainers. They're a ready-made seed set for the household generator: realistic edge cases already worked out. They're also a sanity check that the engine version we install reproduces them.

A handful of parameter files use `0000-01-01` as a "since forever" date, which plain `yaml.safe_load` rejects. Load them with PolicyEngine itself, or with a YAML loader that keeps dates as strings.

These tests are public, so models may have seen them during pretraining. Use them as seeds and for checks, not as held-out evaluation tasks.

## Not fetched yet

The official government sources (USDA FNS, IRS, HHS/ASPE, Medicaid.gov) were blocked from the environment that built this folder; only GitHub and PyPI were reachable. They're listed in `sources.json` with `"status": "todo"`. The scraper's first job is to fetch those and cross-check them against the PolicyEngine parameters.

Still needed and not yet sourced: templates for realistic documents (pay stubs, leases, benefit notices). Only the blank W-2 form is listed so far.

## Licensing

- PolicyEngine files are **AGPL-3.0**. The license is included next to them. Keep it there, and keep this repo's use of them consistent with the AGPL if the repo is ever distributed.
- US government publications are public domain.
- Record the license for every new source in `sources.json` before committing its data.

## Refreshing

Until the scraper exists, re-fetch with a sparse clone of `policyengine-us` using the `paths` listed in `sources.json`, copy them into `raw/policyengine-us/`, and update `commit`, `retrieved` and `pypi_version_at_retrieval`.

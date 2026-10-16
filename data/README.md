# data

Raw data for the benefits-eligibility environment ([docs/04](../docs/04-benefits-eligibility-plan.md)). The PolicyEngine files were fetched by hand; the government sources are fetched by the scraper in [`scraper/`](../scraper/), driven by [`sources.json`](sources.json).

## Layout

```
data/
├── README.md
├── sources.json          # every source: URL, license, status, retrieval date, fetch settings
├── processed/            # parsed rows, one CSV per source (python -m scraper extract)
└── raw/                  # unmodified copies, one folder per source
    ├── policyengine-us/  # fetched by hand
    │   ├── LICENSE       # AGPL-3.0
    │   ├── parameters/   # the rules
    │   └── tests/        # example households with known correct answers
    └── <source-id>/      # fetched by the scraper
        └── <date>/       # one snapshot per change in content
            ├── <files>
            └── _fetch.json   # URL, final URL, HTTP status, content type, size, SHA-256, method
```

Nothing in `raw/` is edited by hand. Everything in `processed/` is regenerated from `raw/` by `extract`.

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

## Scraper

The government sources (HHS/ASPE, USDA FNS, IRS, Medicaid.gov) are fetched by `python -m scraper`. Each entry in `sources.json` with a `fetch` block is one of:

- `direct`: download the first URL in `urls` that returns 200 (later URLs are fallbacks).
- `page`: download the page, then any links on it whose URL matches `follow.pattern`, on `follow.hosts` (default: the page's own host), up to `follow.max`.

`fetch.where` says where it can run from:

| `where` | Meaning | Who fetches it |
|---|---|---|
| `anywhere` (default) | Works from GitHub's runners | The monthly workflow |
| `local` | The site blocks cloud IPs (e.g. aspe.hhs.gov) | You, from a home connection: `fetch --source <id>` |
| `manual` | The site blocks the scraper everywhere (e.g. www.usda.gov) | You, in a browser, then `import` |

Each run writes a new dated snapshot only when content changed, and updates the source's `status`, `retrieved`, `latest_snapshot` and `last_error`. A run where nothing changed leaves the repo untouched, so no PR is opened. It waits 1 second between requests to a host, retries transient errors, follows robots.txt per RFC 9309 (a 4xx robots.txt means no restrictions, a 5xx or unreachable one means stay away), caps files at 50 MB, and never executes anything it downloads.

```bash
pip install -r requirements.txt
python -m scraper status                       # what's fetched, what isn't
python -m scraper fetch                        # all fetchable sources
python -m scraper fetch --source irs-form-w2   # just one (works for any `where`)
python -m scraper fetch --ci                   # what the workflow runs: skips local and manual
python -m scraper import fns-snap-cola-fy27 ~/Downloads/memo.pdf --url <where you downloaded it>
python -m scraper extract                      # parse latest snapshots into processed/
```

`import` stores hand-downloaded files as a normal snapshot, with `"method": "manual"` in `_fetch.json`.

**On GitHub:** the `Scrape sources` workflow runs on the 3rd of each month and on demand (Actions → Scrape sources → Run workflow, optionally with one source id). It opens or updates a single PR from the `scrape/update` branch with any new snapshots, and the run summary lists each source's result. Creating that PR needs the repo setting **Settings → Actions → General → "Allow GitHub Actions to create and approve pull requests"**. Without it the branch is still pushed and the PR can be opened by hand.

## Extract

`python -m scraper extract` runs one parser per source over its latest snapshot and writes `processed/<source-id>.csv`. Every parser emits the same columns, so the upcoming `check` step can compare any source against PolicyEngine:

| Column | Meaning |
|---|---|
| `source_id`, `snapshot` | which raw snapshot the row came from |
| `program` | snap, medicaid, chip, eitc, wic, fpg |
| `parameter` | dotted name, e.g. `income_limit.infant` |
| `region` | state code, a federal region like `CONTIGUOUS_US`, or blank for national |
| `household_size`, `period` | when the source gives them |
| `value`, `unit` | number and unit (`pct_fpl`, `usd_per_month`, `text`, ...); blank value for N/A |
| `raw`, `location` | the original text and where it is in the file, for checking by hand |

Parsers live in `scraper/parsers/` and are registered in `scraper/parsers/__init__.py`. Each one checks the file's structure and fails loudly on anything unexpected, so a format change on the government side shows up as an error instead of silently wrong numbers.

| Source | Parser |
|---|---|
| `medicaid-eligibility-levels` | done: income limits by state and category (% FPL), plus notes |
| `fns-snap-sua-fy26`, `irs-eitc-rp-25-32`, `hhs-poverty-guidelines`, `fns-snap-cola-fy27` | not yet; see [ROADMAP.md](../ROADMAP.md) |

Still needed and not yet sourced: templates for realistic documents (pay stubs, leases, benefit notices). Only the blank W-2 form is listed so far.

## Licensing

- PolicyEngine files are **AGPL-3.0**. The license is included next to them. Keep it there, and keep this repo's use of them consistent with the AGPL if the repo is ever distributed.
- US government publications are public domain.
- Record the license for every new source in `sources.json` before committing its data.

## Refreshing

Government sources: run the scraper (above). PolicyEngine: re-fetch with a sparse clone of `policyengine-us` using the `paths` listed in `sources.json`, copy them into `raw/policyengine-us/`, and update `commit`, `retrieved` and `pypi_version_at_retrieval`.

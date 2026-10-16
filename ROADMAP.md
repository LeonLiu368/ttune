# Roadmap

What's built, what's in progress, and what's next for the benefits-eligibility environment. Update this file whenever a box changes state.

```mermaid
flowchart TD
    classDef done fill:#c8e6c9,stroke:#2e7d32,color:#1b1b1b
    classDef now fill:#ffe0b2,stroke:#ef6c00,color:#1b1b1b
    classDef next fill:#bbdefb,stroke:#1565c0,color:#1b1b1b
    classDef later fill:#eeeeee,stroke:#757575,color:#1b1b1b

    subgraph S1["1 · Get the data"]
        A1["PolicyEngine rules +<br/>~1,300 example households"]:::done
        A2["Scraper: fetch, snapshots,<br/>monthly GitHub Actions run"]:::done
        A3["4 government sources via CI<br/>(merge PR 1)"]:::now
        A4["HHS poverty guidelines<br/>(fetch locally)"]:::now
        A5["SNAP FY27 COLA memo<br/>(browser download + import)"]:::now
        A6["Document templates:<br/>pay stubs, leases, notices"]:::next
    end

    subgraph S2["2 · Parse and verify"]
        B1["Extract framework +<br/>Medicaid levels parser"]:::done
        B2["Parsers: SNAP utility allowances,<br/>EITC, poverty guidelines, COLA"]:::next
        B3["check: official values<br/>vs PolicyEngine"]:::next
    end

    subgraph S3["3 · Build the environment"]
        C1["Household generator<br/>(seeded by PolicyEngine tests)"]:::later
        C2["Messy document renderer"]:::later
        C3["First Harbor task + reward<br/>(benefits-task skill)"]:::later
        C4["Reward-hack audit"]:::later
        C5["Generated task set +<br/>train / holdout splits"]:::later
    end

    subgraph S4["4 · Train"]
        D1["Baseline eval"]:::later
        D2["SFT warm-start"]:::later
        D3["GRPO"]:::later
        D4["Publish to Harbor Hub"]:::later
    end

    A2 --> A3 & A4 & A5
    A3 & A4 & A5 --> B2
    B1 --> B2 --> B3
    A1 --> C1
    B3 --> C1
    A6 --> C2
    C1 --> C2 --> C3 --> C4 --> C5 --> D1 --> D2 --> D3 --> D4
```

Legend: green = done, orange = in progress, blue = next up, grey = later.

## In progress

- [ ] Merge [PR #1](https://github.com/LeonLiu368/ttune/pull/1) (first CI snapshot: SNAP utility allowances, EITC Rev. Proc., Medicaid levels, W-2 template).
- [ ] HHS poverty guidelines: fetch from a home connection and commit (`python -m scraper fetch --source hhs-poverty-guidelines`).
- [ ] SNAP FY27 COLA memo: download in a browser and `python -m scraper import fns-snap-cola-fy27 <files> --url <pdf link>`.

## Next up

1. **Parsers** for the remaining rule sources, one module each in `scraper/parsers/`:
   SNAP utility allowances (xlsx), EITC Rev. Proc. 2025-32 (pdf), poverty guidelines (html), COLA memo (pdf).
2. **`check` command:** compare each parsed value with the matching PolicyEngine parameter and report mismatches.
3. **Document template sources:** find public-domain or permissively licensed pay stub, lease and benefit-notice layouts; add them to `sources.json` as `kind: ["templates"]`.

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

# benefits-145a2b74d9

Screen one household for SNAP, EITC, Medicaid and WIC from its paperwork: an application and 6 documents as PDFs in `/app/case/`. The agent writes `/app/answer.json` ([instruction.md](instruction.md)).

- **Built from:** `ood-1-0000` in `data/documents/ood/cases.jsonl` by `python -m harbortask build`. Don't edit by hand.
- **Household:** 3 people in Georgia; shift `rare_shape`, twists multigenerational; injected issues: stale_stub.
- **Missing information a perfect answer lists:** 0.

## Environment

- **Agent image:** `python:3.12-slim` with `poppler-utils` (for `pdftotext`), `jq`, `tmux` (for terminal agents) and `policyengine-us==2.50.1`.
- **Calculator:** `benefits-calc` turns the household's facts into PolicyEngine's answers. It runs the code that wrote the answer key, so correct facts give the right answer.
- **No network.** The image holds only the PDFs and the calculator; the answer key and grading code are in the verifier's separate image.

## Verifier

A separate container (`tests/Dockerfile`, harbor-rewardkit 0.2.3, offline) scores `/app/answer.json`, which Harbor copies over as an artifact. The scoring lives in `/opt/ttune/verify.py`, a copy of ttune's `harbortask/verify.py` and `evals/score.py`.

| Dimension | What it measures | Weight |
|---|---|---|
| `eligibility` | Each program's yes/no (per member for Medicaid and WIC). A wrong "not eligible" costs double; "unknown" is right only where a missing document leaves the answer open | 0.6 |
| `amount` | SNAP and EITC amounts when truly eligible: full credit within 5% or $10, none at 25% off. With no amount to score, it equals eligibility | 0.25 |
| `missing_info` | Share of truly missing documents listed, minus 0.25 per wrong item | 0.15 |
| `reward` | Weighted mean | |

A missing or unreadable answer scores 0 on every dimension.

## Layout

```
benefits-145a2b74d9/
├── task.toml            # config; [metadata] records the source case and policyengine-us version
├── instruction.md       # what the agent reads
├── environment/         # agent image: Dockerfile, calc/ (benefits-calc), case/ (the PDFs)
├── tests/               # verifier image: Dockerfile, test.sh, criteria/<dimension>/, support/, truth.json
└── solution/solve.sh    # the reference answer, for the Oracle
```

## Running

```bash
harbor run -p tasks/benefits-145a2b74d9 -a oracle -e docker        # should score reward 1.0
harbor run -p tasks/benefits-145a2b74d9 -a terminus-2 -m <model>   # a real agent
```

## Reward-hack audit (2026-10-31)

Run over all 400 document cases with `python -m harbortask audit`; the full report is in [tasks/README.md](../README.md#reward-hack-audit).

| Check | Result | Notes |
|---|---|---|
| Leakage | pass | The agent image holds only the PDFs and benefits-calc; the answer key, grading code and solution are in the verifier's image or solution/. No network in either. Task ids are hashed, not case ids. |
| Tampering | pass | Separate verifier container built from tests/; only /app/answer.json crosses over, as data. |
| Degenerate policies | pass | empty: 0.00; malformed: 0.00; all no, flag nothing: 0.33; all yes, flag nothing: 0.33; all unknown, flag everything: 0.08; random values, right format: 0.28 (mean reward over 400 cases; oracle 1.00) |
| Verifier logic | pass | Scores outcomes (answers vs PolicyEngine), not format. Unreadable answers and grading errors score 0. Deterministic. |

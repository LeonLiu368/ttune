# Harbor tasks

Each task gives an agent one household's paperwork and a PolicyEngine calculator, and scores the `/app/answer.json` it writes. Tasks are built from the document cases in [`data/documents`](../data/documents/README.md) by `harbortask/`. Don't edit them by hand.

This folder holds 6 hand-checked sample tasks:

| Task | Case | What it tests |
|---|---|---|
| [benefits-5e5278f3df](benefits-5e5278f3df/) | id-1-0001 | A typical household, no injected issue |
| [benefits-3111a2acb3](benefits-3111a2acb3/) | id-1-0003 | A partner who moved out, still named on the lease |
| [benefits-ca5c448e40](benefits-ca5c448e40/) | id-1-0002 | Missing pay stubs (a gap) |
| [benefits-e41833f6c8](benefits-e41833f6c8/) | id-1-0008 | The lease page with the rent is missing (a gap) |
| [benefits-ad9f0b012e](benefits-ad9f0b012e/) | id-1-0079 | No childcare receipt (a gap) |
| [benefits-145a2b74d9](benefits-145a2b74d9/) | ood-1-0000 | A multigenerational household with a stale pay stub |

The full generated set, with train and holdout splits, is the next step on the [roadmap](../ROADMAP.md).

## How a task works

- **The agent's container:**
  - `/app/case/*.pdf` holds the application and documents, and `pdftotext` can read them.
  - `benefits-calc` is PolicyEngine as a calculator: the household's facts as JSON in, SNAP, EITC, Medicaid and WIC out. It runs the same code that wrote the answer key, so correct facts give the right answer. The skill is reading the paperwork, applying the stated rules, and spotting what's missing.
  - No network. The agent runs as a non-root user.
- **The verifier:**
  - A separate, offline container built from `tests/` (Reward Kit 0.2.3) holds the answer key and the grading code.
  - Only `/app/answer.json` crosses over.
- **The answer:** each program's eligibility and amounts, `unknown` where a missing document could change the answer, and `missing_information`, a list of documents to request, each from a fixed list of 8 kinds.

| Dimension | Weight | Scoring |
|---|---|---|
| `eligibility` | 0.60 | As in the evals (`evals/score.py`): a wrong "not eligible" costs double; "unknown" is right only where a gap leaves the decision open |
| `amount` | 0.25 | SNAP and EITC amounts when truly eligible: full credit within 5% or $10, zero at 25% off. With no amount to score, it equals eligibility |
| `missing_info` | 0.15 | Share of the truly missing documents listed, minus 0.25 per wrong item |
| `reward` | | Weighted mean |

## Commands

```bash
pip install -r requirements-docgen.txt
python -m harbortask audit                              # degenerate answers over all 400 cases -> tasks/audit.json
python -m harbortask build --samples                    # the 6 tasks here
python -m harbortask build --set ood --out /tmp/tasks   # every case in a set
harbor run -p tasks/benefits-5e5278f3df -a oracle -e docker    # needs Docker; reward should be 1.0
```

The **Harbor tasks** workflow does the last step for every task on each change, in Docker, and checks that a copy with an empty answer scores 0. It also checks that `tasks/` matches what the generator writes.

## Reward-hack audit

Run on 2026-10-31 over all 400 document cases (`python -m harbortask audit`), scoring each policy with the verifier's own code:

| Policy | Mean reward | Max | Eligibility | Amount | Missing info |
|---|---|---|---|---|---|
| Reference answer | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Empty (no answer file) | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| Malformed JSON | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| All "no", flag nothing | 0.33 | 1.00 | 0.28 | 0.26 | 0.69 |
| All "yes", flag nothing | 0.33 | 0.71 | 0.37 | 0.02 | 0.69 |
| All "unknown", flag everything | 0.08 | 0.77 | 0.10 | 0.09 | 0.00 |
| Right format, random values | 0.28 | 1.00 | 0.26 | 0.16 | 0.52 |

- **Blanket answers sit at the same floor as in the evals (about 0.33).** Their maximum hits 1.0 only on households that truly qualify for nothing and have nothing missing, where "no" is the right answer.
- **Flagging nothing is right 69% of the time,** because 69% of packets have no gap. That's why those policies keep their missing-info score. Flagging everything, or hedging everything as "unknown", scores 0.08.

| Check | Result | Notes |
|---|---|---|
| Leakage | pass | The agent image holds only the PDFs and `benefits-calc`. The answer key, grading code and reference solution are in the verifier image or `solution/`. Neither container has network. Task ids are hashes, not case ids. Checked by `tests/test_harbortask.py`. |
| Tampering | pass | Separate verifier container; only `/app/answer.json` crosses over, and it's read as data. |
| Degenerate policies | pass | The table above. |
| Verifier logic | pass | It scores outcomes (answers against PolicyEngine), not format. Missing or unreadable answers and grading errors score 0. Deterministic. |

**Findings:**

- **Base images aren't pinned by digest yet.** `harbor lint --select ALL` reports `unpinned-image`. Pin `python:3.12-slim` to a digest once one is chosen in CI.
- **The case data is public in this repo.** That's safe only because both containers are offline and task ids are hashed. A harness that gives the agent network access would let it look answers up, so tasks used for training should come from households that aren't published.

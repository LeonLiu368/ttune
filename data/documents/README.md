# Document cases

The same 400 households as [`data/households`](../households/README.md), but as paperwork instead of a clean summary: an application, plus pay stubs, benefit letters, a lease and bills. Some packets disagree with themselves or leave something out on purpose. The right answers come from PolicyEngine, applied to what the documents actually establish.

| Set | Folder | Packets | With a gap |
|---|---|---|---|
| ID | [`id/`](id/) | 200 | 77 |
| OOD | [`ood/`](ood/) | 200 | 48 |

Each folder has:

- **`cases.jsonl`**: one case per line, in the shape the eval harness reads.
- **`manifest.json`**: counts of issues, documents and answers.

[`samples/`](samples/) has the PDFs for three packets, so you can see what an agent would be handed.

## Build

```bash
pip install -r requirements-docgen.txt -r requirements-envgen.txt
python -m docgen build --set id                         # about a minute per set
python -m docgen build --set ood
python -m docgen pdf --set id --out data/documents/pdf  # every PDF, about 11 MB for both sets; not committed
```

The same household always gives the same packet. The build fails if the documents don't give back the household's own figures, or if a program comes out all one answer.

## What's in a packet

| Fact | Document |
|---|---|
| Who lives there; their ages, citizenship, pregnancy, disability, student status | The application (the household's own account) |
| Wages | The two most recent pay stubs: weekly, every two weeks, twice a month or monthly; hours that vary; deductions, net pay and year-to-date totals |
| Self-employment | A three-month earnings log: payouts, business costs, net |
| Social Security, SSI | A benefit letter |
| Child support | A three-month payment history, sometimes two payments a month |
| Unemployment | An award letter with the weekly benefit amount |
| Rent and utilities | A three-page lease. There's also a utility bill when heat or cooling is paid separately. |
| Childcare, medical costs | A provider invoice; a three-month pharmacy payment history |
| Pregnancy, disability, college | A clinic letter, a disability determination, an enrollment letter |

All the businesses and people are made up. Every document is drawn by ttune, because the official templates don't fit:

- **The IRS forms already fetched are 2026 revisions.** A 2026 W-2 can't exist in October 2026, when the application is dated.
- **HUD's model lease (90105a) is for subsidized housing only.** Using it would mean every household gets a HUD rent subsidy.

## How the documents become numbers

The model is told these rules (`docgen/rules.py`). Every printed amount is chosen so that the rules give back the household's exact monthly figure:

- **Wages:** average the gross on the two most recent stubs, then convert to a month: weekly × 4.3, every two weeks × 2.15, twice a month × 2.
- **Self-employment, child support, medical costs:** average the last three months.
- **Unemployment:** the weekly amount × 4.3.
- **Social Security:** the benefit before deductions.
- **Round to the nearest dollar.**
- **Conflicts:** a document beats the application, and the newest document wins.

## Injected issues

0 to 2 per packet: at most one gap, and at most one distractor. Threshold-edge households never get a gap, since it would blur the cutoff they were placed at.

| Issue | ID | OOD | What the packet shows | Effect |
|---|---|---|---|---|
| `stale_stub` | 26 | 34 | An older pay stub beside the current two | None, if the reader uses the newest stubs |
| `rent_mismatch` | 32 | 28 | The application's rent differs from the lease | None: the lease wins |
| `partner_moved_out` | 11 | 7 | The lease and an old pay stub name a partner the application says moved out in August | None: they aren't in the household |
| `name_variant` | 21 | 43 | A document says "Sam" or "A. Patel" for a member | None |
| `missing_income_doc` | 38 | 19 | The application names a job or benefit, but there's no stub or letter for it | **Gap** |
| `missing_lease_page` | 36 | 24 | Page 2 of the lease, with the rent, is missing, and the application leaves rent blank | **Gap** |
| `missing_childcare_receipt` | 3 | 5 | The application says childcare is paid, with no amount and no invoice | **Gap** |

## The answers, with gaps

For a packet with a gap, the missing fact is tried at 9 values across a plausible range:

- income: $0 to 300% of the poverty line for the household's size, a month;
- rent: $0 to $4,000;
- childcare: $0 to $2,000.

Each value, plus the real one, goes through PolicyEngine:

- **A decision that comes out the same every time stands.**
- **One that changes is `"unknown"`,** and the gap goes into `truth.missing_information`.
- **An amount that changes isn't scored.**

The grid matters because the EITC rises and then falls with income, so $0 and the top of the range can both say "no" while the middle says "yes".

| Program | ID yes / no / unknown | OOD yes / no / unknown |
|---|---|---|
| SNAP | 76 / 84 / 40 | 92 / 86 / 22 |
| EITC | 89 / 76 / 35 | 121 / 67 / 12 |
| Medicaid (any member) | 79 / 88 / 33 | 136 / 54 / 10 |
| WIC (any member) | 31 / 155 / 14 | 79 / 117 / 4 |

## One line of `cases.jsonl`

```json
{"id": "id-1-0002", "case": "Case id-1-0002\nLives in: ...\n=====\nDocument 1 of 5: Application for benefits ...",
 "household": {...}, "packet": {"documents": [...], "issues": [...]},
 "truth": {"snap": {"eligible": "unknown", "monthly_benefit": null}, "medicaid": {"eligible_members": ["p2"], "unknown_members": ["p1"]}, ...,
           "missing_information": ["Pay stubs for Imani Clark"]}}
```

- **`case`**: the cover note and every document's text twin. This is what a text-only model reads.
- **`household`**: the facts behind the paperwork, the same as in `data/households`.
- **`packet`**: the documents as structured blocks (the PDF renderer draws these) and the issues, each with what a careful reader should notice.
- **`truth`**: PolicyEngine's answers as above. `"unknown"` and `unknown_members` mark undetermined decisions.

## Scoring

`evals/score.py` scores these cases like the text cases, plus one rule:

- **On an undetermined decision,** answering "unknown" is right.
- **"Yes" or "no" there is a guess:** it earns nothing, but it isn't counted as a false denial.

Blanket answers stay low:

| Blanket answer | ID | OOD |
|---|---|---|
| "unknown" to everything | 0.14 | 0.06 |
| "no" to everything | 0.34 | 0.21 |
| "yes" to everything | 0.21 | 0.30 |

Flagging the missing documents themselves is scored later, in the Harbor task.

To run a model on these cases:

```bash
python -m evals run --set id --households data/documents/id/cases.jsonl --model ...
```

Or use the **Eval (self-hosted model)** workflow with `cases: documents`.

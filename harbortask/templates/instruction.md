# Screen a household for benefits

You are a public-benefits caseworker in the United States. A household in $state has applied for help and handed in the paperwork in `/app/case/` ($n_documents PDF files, starting with their application). Work out which programs they qualify for, and how much, and write your answer to `/app/answer.json`.

## The programs and periods

- **SNAP:** October 2026 (federal fiscal year 2027 rules, plus the state's rules). Give the monthly benefit.
- **EITC:** federal earned income tax credit for tax year 2026. Give the annual credit for the household (add up all tax filers in it).
- **Medicaid:** 2026, under the state's rules. Medicaid only, not CHIP. List each member who qualifies.
- **WIC:** October 2026. List each member who qualifies.

Assume the household applies for every program.

## Tools

- `pdftotext -layout /app/case/01-application.pdf -` prints a document's text.
- `benefits-calc household.json` runs PolicyEngine on the household's facts, like a caseworker's calculator. It needs the facts as monthly dollar amounts. `benefits-calc --help` describes the input; `benefits-calc --example` prints one to start from. The calculator is exact, so the work is in getting the facts right.

$rules

## Answer

Write `/app/answer.json` like this:

```json
{
  "snap": {"eligible": true, "monthly_benefit": 0},
  "eitc": {"eligible": true, "annual_amount": 0},
  "medicaid": {"eligible_members": ["First name"], "unknown_members": []},
  "wic": {"eligible_members": [], "unknown_members": []},
  "missing_information": [{"document": "pay_stubs", "member": "First name"}],
  "explanation": "A short, plain-language summary for the household."
}
```

- `eligible` is `true`, `false` or `"unknown"`. Say `"unknown"` only when a missing document could change the answer, and give an amount of 0 then.
- `unknown_members` lists members whose Medicaid or WIC answer a missing document could change.
- Amounts are in US dollars. Give 0 when not eligible.
- Name members by first name, as the application does.
- `missing_information` lists the documents the household still needs to bring, if any. Use an empty list if nothing is missing. Each `document` is one of: $categories. For pay stubs, self-employment records and benefit letters, also give the `member` they're for; for the others, give `"member": null`.

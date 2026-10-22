# evals

Runs a model over a household set, scores each answer against PolicyEngine's, and compares typical (ID) households with unusual (OOD) ones. The household sets are in [`data/households/`](../data/households/README.md).

## Run it

Runs that call a model go through GitHub Actions, because openrouter.ai can't be reached from the Claude Code cloud sandbox. Open **Actions → Eval → Run workflow** and fill in:

| Input | Meaning |
|---|---|
| `model` | OpenRouter model id. The default is a free (`:free`) model. |
| `limit` | Households per set. Default 10 (a smoke test); blank runs all 200. |
| `allow_paid` | Off by default. While it's off, the job checks the model's price on OpenRouter and stops before any request unless it's $0. |
| `max_tokens` | Reply length cap, reasoning included. Default 8,000. |
| `reasoning_effort` | For thinking models: `none`, `minimal`, `low`, `medium` or `high`. Blank uses the model's default. |

The job runs both sets and `compare`, then opens a PR with `evals/results/<run-id>/`. It needs the `OPENROUTER_API_KEY` repo secret.

Locally, against OpenRouter or any OpenAI-compatible server:

```bash
export OPENROUTER_API_KEY=...            # not needed for a local --base-url
python -m evals run --set id  --model <model> --limit 10 --run-id test
python -m evals run --set ood --model <model> --limit 10 --run-id test
python -m evals compare test             # writes evals/results/test/comparison.md
```

`--base-url http://localhost:8000/v1` points it at a local server, such as vLLM or llama.cpp. `--resume` re-runs only the cases that are missing or got no answer.

## What the model sees

The system prompt sets the rule periods: SNAP for October 2026 (FY2027), the EITC for tax year 2026, Medicaid (not CHIP) for 2026, and WIC for October 2026. The user message is the household's case text plus the answer format (see [`prompt.py`](prompt.py)). The model may reason first, but must end with one JSON block:

```json
{"snap": {"eligible": true, "monthly_benefit": 412},
 "eitc": {"eligible": false, "annual_amount": 0},
 "medicaid": {"eligible_members": ["Maria", "Luis"]},
 "wic": {"eligible_members": ["Luis"]}}
```

Every run records the prompt version and a hash of its text, so results from different prompts are never mixed by accident.

## How answers are scored

[`score.py`](score.py) holds the rules as pure functions, so the Harbor verifier can reuse them.

- **Decisions.** SNAP and the EITC are one yes/no each. Medicaid and WIC are one per household member.
- **Eligibility score.** Each program weighs the same, and its weight is split across its decisions. A wrong "not eligible" for someone who qualifies costs **double**, because that's the error that costs people food or health care. A wrong "eligible" just earns nothing. So does `"unknown"`, since every case lists everything needed.
- **Amount score.** This covers SNAP and EITC amounts when the household truly qualifies. An amount within 5% or $10 (whichever is larger) gets full credit. Credit falls to zero at 25% off.
- **Reward.** Two-thirds eligibility plus one-third amount, or eligibility alone when neither SNAP nor the EITC applies.
- **Malformed replies.** A reply with no readable JSON, a missing program or a wrong type scores 0. It's counted, never skipped.
- **Replies cut off at the token limit.** These are malformed too, but counted separately so you can tell them apart. Thinking models can spend the whole budget reasoning and never write the answer. If many replies are cut off, raise `max_tokens` or lower `reasoning_effort`.
- **API failures.** A case the API never answered, even after retries, isn't the model's fault. It's listed separately and not scored. If the first three cases all fail, the run stops, because the endpoint is down or rate-limited.

## Reading `comparison.md`

- **Overall:** mean reward, eligibility and amount scores, and the malformed rate for each set, with the OOD minus ID change.
- **Floors:** what answering "no" to everything, or "yes" with $0 amounts, would score on each set. A model has to clear these to have learned anything.
- **By program:** balanced accuracy, accuracy, false-denial and false-approval rates, and how often amounts are within tolerance.
- **OOD by shift family and by twist:** the same measures for rare household shapes, threshold edge cases and held-out states, and for each twist (pregnant member, self-employment, `edge_snap`, ...).

**Judge the ID → OOD change by balanced accuracy, not plain accuracy or mean reward.** The OOD set has more eligible households than the ID set. That alone moves accuracy and reward: answering "no" to everything scores 0.35 on ID and 0.22 on OOD. Balanced accuracy averages accuracy on truly eligible and truly ineligible decisions, so a blanket answer scores 50% on any set.

Intervals are 95% bootstrap intervals over households (2,000 resamples). OOD families have about 67 households each and some twists only 10 to 17, so treat small gaps as noise.

## Tests

- [`tests/test_evals_score.py`](../tests/test_evals_score.py): scoring rules and answer parsing, plus blanket answers on the real sets.
- [`tests/test_evals_run.py`](../tests/test_evals_run.py): `run` and `compare` end to end against a local mock server. The mock plays a perfect model, an always-"no" model, a model that never answers in JSON, a flaky server and a bad API key. No network or key is needed.

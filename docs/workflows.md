# GitHub Actions workflows

Everything heavy runs on GitHub's free runners: evals, task builds, the agentic baseline and the SFT data. The public repo makes those runners free. To start a manual workflow, open Actions, choose it, then Run workflow. Workflows that produce results open a PR. Merging it records the result; closing it discards it.

## At a glance

| Workflow | File | Starts | Cost | Secrets | Output |
|---|---|---|---|---|---|
| Tests | `tests.yml` | Every push and PR | $0 | none | Pass or fail |
| Harbor tasks | `harbor.yml` | Pushes and PRs that touch tasks or scoring; by hand | $0 | none | The Oracle scores 1.0 and an empty answer scores 0 on every sample task, in Docker |
| Viewer site | `pages.yml` | Pushes that touch results, households or the viewer; by hand | $0 | none | The [eval viewer](https://leonliu368.github.io/ttune/) on GitHub Pages |
| Scrape sources | `scrape.yml` | Monthly (06:17 UTC on the 3rd); by hand | $0 | none | A PR with new source snapshots and the PolicyEngine check |
| Eval (self-hosted model) | `eval-local.yml` | By hand | $0 | none | A PR with an evals run |
| Eval | `eval.yml` | By hand | $0 unless `allow_paid` | `OPENROUTER_API_KEY` | A PR with an evals run |
| Baseline (Harbor agent, self-hosted model) | `baseline.yml` | By hand | $0 | none | A PR with an agentic evals run on the holdout |
| Task splits | `splits.yml` | By hand | $0 | `TTUNE_TRAIN_SEED` | An encrypted artifact with all 1,600 tasks; a PR with the manifests |
| Scripted demonstrations | `scripted.yml` | By hand | $0 | `TTUNE_TRAIN_SEED` | An encrypted artifact with the SFT data; a PR with counts |
| Teacher trajectories | `teacher.yml` | By hand | Paid, capped by `budget_usd` | `OPENROUTER_API_KEY`, `TTUNE_TRAIN_SEED` | An encrypted artifact with trajectories and SFT data; a PR with a summary |

## The workflows

### Tests

This workflow runs `python -m pytest` twice:
- once without PolicyEngine, so those tests skip;
- once with PolicyEngine and `pdftotext`, for the tests that need them (household answers, document truth, the calculator, the splits and the scripted demonstrations).

### Harbor tasks

This workflow first checks that `tasks/` matches what `python -m harbortask build --samples` writes. It then runs Harbor's Oracle agent on each sample task in Docker; each must score 1.0. A copy of one task with an empty answer must score 0.

### Viewer site

This workflow builds the static viewer from `evals/results/` and publishes it to GitHub Pages.

### Scrape sources

| Input | Default | Meaning |
|---|---|---|
| `source` | blank | One source id from `data/sources.json`; blank fetches every fetchable source |

The workflow fetches each source, parses it and runs `scraper check`. If anything changed, it opens a PR. The scraper never spoofs a browser: a site that blocks it is fetched by hand and added with `python -m scraper import`.

### Eval (self-hosted model)

This workflow serves an open model with llama.cpp on the runner's CPU and runs both household sets against it.

| Input | Default | Meaning |
|---|---|---|
| `preset` | `qwen3-4b-instruct` | A model from [`evals/local_models.json`](../evals/local_models.json), pinned to a commit and SHA-256 |
| `limit` | 10 | Households per set, or `all` for 200 |
| `shards` | 1 | Parallel jobs, up to 20. A full run with 20 shards takes 3–4 hours. |
| `max_tokens` | 6000 | Reply length cap |
| `cases` | `text` | `text` for written summaries, `documents` for the paperwork |
| `model_repo` | blank | A Hugging Face repo (`owner/name`) with a GGUF fine-tuned from `preset`, served in its place. A private repo needs `HF_TOKEN`. |

### Eval

This workflow runs both sets against a model on OpenRouter. The **cost guard** (`python -m evals preflight`) stops the job before any request, unless the model is free or `allow_paid` is ticked.

| Input | Default | Meaning |
|---|---|---|
| `model` | `free` | An OpenRouter id, or `free` for the first available free 3–8B instruct model |
| `limit` | 10 | Households per set, or `all` |
| `allow_paid` | off | Allow a model that costs money |
| `max_tokens` | 8000 | Reply length cap, reasoning included |
| `reasoning_effort` | blank | For thinking models |

### Baseline (Harbor agent, self-hosted model)

This workflow runs an open model, served by llama.cpp on the runner's CPU, as Harbor's `terminus-2` agent on the holdout tasks. Each task runs offline in Docker.

| Input | Default | Meaning |
|---|---|---|
| `preset` | `qwen3-4b-instruct` | As above |
| `limit` | 5 | Tasks per holdout set, or `all` for 200 |
| `shards` | 1 | Parallel jobs, up to 60 (20 run at once) |
| `agent_timeout_minutes` | 30 | Time per task |
| `max_turns` | 40 | Agent turns per task |
| `model_repo` | blank | As above: a fine-tuned GGUF on Hugging Face, served in place of `preset` |
| `compare_to` | the one-shot document run | The run to compare with. For a fine-tuned model, use the base model's baseline run. |

- **Sizing a full run:** a 4B model takes about 13 minutes per task, and a job stops starting tasks 275 minutes in, so use about 30 shards for all 400. Tasks a job runs out of time for are counted as "not run" and aren't scored.
- **The log:** each task's answer file and agent turns are printed (`python -m harbortask agentic show`). The holdout is public, so this is safe.
- **Memory:** the model server runs with `--logits_all False`. Without it, llama-cpp-python keeps every token's logits, about 20 GB at a 32k context, which once shut a runner down.

### Task splits

This workflow builds all four splits, runs the Oracle on sampled training and validation tasks, and uploads every task encrypted. It then opens a PR with the [manifests](../tasks/splits/), which hold counts, audit results and task digests, and no answers.

| Input | Default |
|---|---|
| `n_train` | 1000 |
| `n_validation` | 200 |

The same secret always gives the same households, so a rebuild changes only task files, for example after an instruction change.

### Scripted demonstrations

This workflow writes the SFT data with `python -m harbortask scripted`: one checked terminus-2 conversation per training and validation case. It uses no model and no API, and takes about 5 minutes. Each conversation's answer must score 1.0, or it's dropped and counted. The output is the artifact `ttune-scripted-<run>`: `bundle/train.jsonl` and `bundle/validation.jsonl`, encrypted, kept 90 days.

| Input | Default |
|---|---|
| `n_train` | 1000 |
| `n_validation` | 200 |

### Teacher trajectories

This optional, paid route has a stronger open model drive terminus-2 on the training tasks through OpenRouter.

| Input | Default | Meaning |
|---|---|---|
| `model` | `qwen/qwen3-235b-a22b-2507` | Its license must allow training on its outputs |
| `start`, `limit` | 0, 50 | Which training cases |
| `shards` | 5 | Parallel jobs |
| `budget_usd` | 2 | A hard cap for the run, split evenly across shards. At most 30. |
| `max_turns`, `agent_timeout_minutes` | 40, 20 | Per task |

The run has several safeguards:
- **Price ceiling.** The run refuses a model priced above $1 per million input tokens or $4 per million output tokens.
- **Budget check.** Before every task, a shard checks that its share of the budget still covers the most one task can cost.
- **Stop on errors.** A shard stops after two API errors in a row; HTTP 402 means the OpenRouter account is out of credit.
- **Private output.** Harbor's own output goes into the encrypted bundle, not the public log.

## Secrets

Set these under Settings → Secrets and variables → Actions. GitHub can't show a secret's value after it's saved, so keep your own copy.

| Secret | Used by | What it is |
|---|---|---|
| `TTUNE_TRAIN_SEED` | Task splits, Scripted demonstrations, Teacher trajectories, the Colab notebook | Any long random string. It seeds the training households and encrypts every artifact that holds training answers. Changing it gives new training households, so rebuild the splits and the SFT data afterwards; the holdout doesn't change. |
| `OPENROUTER_API_KEY` | Eval, Teacher trajectories | An OpenRouter key. With the cost guard on, only free models run. |
| `HF_TOKEN` | Eval (self-hosted model), Baseline, when `model_repo` is private | A Hugging Face read token. It's passed only to the steps that look up and download the model. |

## Privacy rules

The training split's answers must stay private, and the repo and its Actions logs are public. So:

- **Artifacts.** Anything that holds training cases, answers or trajectories is uploaded only encrypted with `TTUNE_TRAIN_SEED`. Any GitHub user can download a public repo's artifacts.
- **Public logs.** For training tasks they show only task ids, rewards, turn counts and error types. Never answers, conversations or the API's raw error text.
- **PRs.** These commit only aggregate numbers: counts, means, audit results, digests.
- **Holdout runs.** These are public by design, since their answers are already in the repo, so the baseline logs print full trials.

To open an encrypted artifact, download it from the run's page, unzip it, and then:

```bash
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:TTUNE_TRAIN_SEED -in <file>.tar.gz.enc | tar -xzf -
```

## Costs

| | Spent |
|---|---|
| Evals, task builds, baseline, scripted demonstrations | $0 (GitHub's free runners) |
| Teacher pilot, November 2, 2026 | $0.11 (stopped when OpenRouter credit ran out) |
| Fine-tuning | $0 planned (free Colab T4) |

Workflows that run in parallel share GitHub's limit of 20 concurrent jobs for the account.
